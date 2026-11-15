"""The one thread that talks to libmpv's render API, and what hangs off it.

    mpv core threads --update_cb--> render thread: its own GL context, a video
                                    at a time into a texture sized for its
                                    cell, the pixels read back
                                        |
                                    triple buffer per video (a lock, no GL,
                                    no waiting)
                                        |
    GUI thread: a surface paints the newest finished frame with QPainter

That is the "Copy" output, with no GL in the window. Painted like any other
widget, a frame arrives with the size change it goes with, where a GL one
reaches the screen in its own time, sometimes for a size the window no longer
has: that vibrates during a real window resize, and nothing on the GL side
fixed it.

The "Shared" output reads nothing back. The render thread's context shares with
Qt's (QtShareGroup), the triple buffer holds textures, finished once a round,
and a QOpenGLWidget draws the newest: much less CPU, the vibration and all.

Software MPV has no GL at all. A thread of its own has libmpv's software
renderer scale and convert each frame on the CPU, straight into the triple
buffer's pixels, painted as the Copy output's are.

What each thread may do, most bugs here being one of these broken:

GUI thread: nothing that can wait on mpv. It sends async commands, and reads
what observers have stored.

Render thread: never waits on the mpv core. That is the deal for
advanced_control, which gives direct rendering and an update() that says
whether there is really a new frame.

A video goes away in three steps, in this order:

    GUI       stop drawing it, stop sending it commands
    renderer  free its render context with the GL context current
    other     terminate mpv, which can block, so neither of the two above
"""

import collections
import ctypes
import logging
import re
import sys
import threading
import time
from contextlib import suppress
from functools import partial

from PyQt5.QtCore import QElapsedTimer, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QGuiApplication, QOffscreenSurface
from PyQt5.QtWidgets import QWidget

from gridplayer.mpv_player import abilities
from gridplayer.mpv_player.gl_context import (
    GLContextError,
    QtShareGroup,
    create_gl_context,
    macos_gl_format,
)
from gridplayer.mpv_player.libmpv import load_mpv
from gridplayer.params import env
from gridplayer.utils.qt import paint_interval_s

GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_NEAREST = 0x2600
GL_LINEAR = 0x2601
GL_RGBA = 0x1908
GL_BGRA = 0x80E1
GL_RGBA8 = 0x8058
GL_UNSIGNED_BYTE = 0x1401
GL_FRAMEBUFFER = 0x8D40
GL_EXTENSIONS = 0x1F03
GL_COLOR_ATTACHMENT0 = 0x8CE0

_c = ctypes
_GL_FUNCS = {
    "glGenTextures": (None, _c.c_int, _c.c_void_p),
    "glDeleteTextures": (None, _c.c_int, _c.c_void_p),
    "glBindTexture": (None, _c.c_uint, _c.c_uint),
    "glTexParameteri": (None, _c.c_uint, _c.c_uint, _c.c_int),
    "glTexImage2D": (
        None,
        _c.c_uint,
        _c.c_int,
        _c.c_int,
        _c.c_int,
        _c.c_int,
        _c.c_int,
        _c.c_uint,
        _c.c_uint,
        _c.c_void_p,
    ),
    "glGenFramebuffers": (None, _c.c_int, _c.c_void_p),
    "glDeleteFramebuffers": (None, _c.c_int, _c.c_void_p),
    "glBindFramebuffer": (None, _c.c_uint, _c.c_uint),
    "glFramebufferTexture2D": (
        None,
        _c.c_uint,
        _c.c_uint,
        _c.c_uint,
        _c.c_uint,
        _c.c_int,
    ),
    "glFinish": (None,),
    "glGetString": (_c.c_char_p, _c.c_uint),
    "glReadPixels": (
        None,
        _c.c_int,
        _c.c_int,
        _c.c_int,
        _c.c_int,
        _c.c_uint,
        _c.c_uint,
        _c.c_void_p,
    ),
}
_GL_PROTO = ctypes.WINFUNCTYPE if sys.platform == "win32" else ctypes.CFUNCTYPE
_FENCE_SYNC_PROTO = _GL_PROTO(_c.c_void_p, _c.c_uint, _c.c_uint)
_DELETE_SYNC_PROTO = _GL_PROTO(None, _c.c_void_p)

# mpv's fix, f74adc4, came 113 commits after the v0.41.0 tag: see FrameFences
_FENCES_FIXED_AFTER_041 = 113
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-(\d+)-g[0-9a-f]+)?")

# mpv waits 200 ms for a frame to be rendered and then lets it go, with nothing
# left to say so. It's still what it draws if asked to draw. What's lost is the
# word that there's something new: paused, no other is coming. A little less, as
# the wait can come up short by a tick of the system's clock.
_FRAME_LET_GO_S = 0.15

# How long a cleanup waits for the render thread to finish: a round and the
# freeing of every video, well under a second. Past it the thread is taken to
# be stuck in a GL driver's call, which nothing can take it out of, and left
# behind rather than holding the app up for good.
STOP_WAIT_MS = 5000

# Render threads that didn't stop. A QThread destroyed while it runs takes the
# app down with it, so they're kept for as long as the app is.
_left_behind: list["VideoRenderer"] = []


class _GLFunctions:
    """The GL calls used here. ctypes lets go of the GIL for each."""

    def __init__(self, context):
        for name, signature in _GL_FUNCS.items():
            address = context.get_proc_address(name.encode())
            if not address:
                raise GLContextError(f"OpenGL function {name} is not available")

            setattr(self, name, _GL_PROTO(*signature)(address))


def leaks_frame_fences(mpv_version: str | None) -> bool:
    """Whether this libmpv leaves a GL fence behind for every frame drawn.

    0.40 and 0.41 make one at the end of each, for a swap of buffers that the
    render API never asks for, which is what would delete them (mpv's issue
    17217). Fixed by f74adc4, first in 0.42. A git build says how far past
    its tag it is, as "v0.41.0-1044-g14f2d48cb".
    """

    found = _VERSION_RE.match(mpv_version or "")
    if found is None:
        return False

    major, minor, patch, past_tag = found.groups()
    version = (int(major), int(minor), int(patch))

    if version[:2] == (0, 40):
        return True

    if version == (0, 41, 0):
        return past_tag is None or int(past_tag) < _FENCES_FIXED_AFTER_041

    return False


class FrameFences:
    """The fence libmpv makes at the end of a frame, deleted once it's drawn.

    Left alone, on libmpv 0.40 and 0.41 (see leaks_frame_fences), they pile
    up: 1.4 GB an hour with 9 videos on Intel's Mesa, the same leak smaller on
    other drivers. mpv is given its glFenceSync through this, and the last
    fence made while a frame is drawn is that one: nothing in mpv looks at it
    again. Not from 0.42 on, where the last can be one mpv waits on.

    Render thread only, as mpv's GL calls are.
    """

    def __init__(self, fence_sync: int, delete_sync: int):
        self._fence_sync = _FENCE_SYNC_PROTO(fence_sync)
        self._delete_sync = _DELETE_SYNC_PROTO(delete_sync)
        self._last = None

        # kept for as long as mpv may call it
        self._given = _FENCE_SYNC_PROTO(self._made)
        self.address = ctypes.cast(self._given, ctypes.c_void_p).value

    def _made(self, condition, flags):
        fence = self._fence_sync(condition, flags)
        self._last = fence

        return fence

    def forget(self) -> None:
        """Before a frame is drawn: none made yet is the frame's."""

        self._last = None

    def delete_last(self) -> None:
        """After a frame is drawn: its fence, if mpv made one, deleted."""

        if self._last:
            self._delete_sync(self._last)
            self._last = None


class RenderCalls:
    """A video's render() calls, their parameters made once.

    python-mpv makes them anew on every call, some microseconds of Python with
    the GIL held, for every frame of every video. Here only the size changes,
    in place.
    """

    def __init__(self, mpv_module, render_context, fbo: int):
        self._render = mpv_module._mpv_render_context_render
        self._handle = render_context.handle

        param_type = mpv_module.MpvRenderParam

        # what the parameters point at, kept for as long as they are used
        self._fbo = mpv_module.MpvOpenGLFBO(0, 0, fbo)
        self._off = ctypes.c_int(0)
        self._on = ctypes.c_int(1)

        # block_for_target_time off: see VideoRenderer._render
        self._draw = _param_array(
            param_type,
            (
                ("opengl_fbo", self._fbo),
                ("flip_y", self._off),
                ("block_for_target_time", self._off),
            ),
        )
        self._skip = _param_array(
            param_type,
            (("skip_rendering", self._on), ("block_for_target_time", self._off)),
        )

    def draw(self, width: int, height: int) -> None:
        """The next frame drawn into the framebuffer, at this size."""

        self._fbo.w, self._fbo.h = width, height
        self._render(self._handle, self._draw)

    def skip(self) -> None:
        """The next frame taken and not drawn."""

        self._render(self._handle, self._skip)


class SoftwareRenderCalls:
    """A video's render() calls with libmpv's software renderer: the frame is
    scaled and converted on the CPU, straight into the pixels it's given."""

    # render.h's numbers, which python-mpv doesn't know
    _SW_SIZE = 17
    _SW_FORMAT = 18
    _SW_STRIDE = 19
    _SW_POINTER = 20

    def __init__(self, mpv_module, render_context):
        self._render = mpv_module._mpv_render_context_render
        self._handle = render_context.handle

        param_type = mpv_module.MpvRenderParam

        self._size = (ctypes.c_int * 2)()
        # B, G, R and A, as the painted frames are, opaque. Not "bgr0": zimg
        # leaves its fourth byte at 0, and Qt's RGB32 painting carries that
        # through as alpha, a picture to see through. A libmpv with no zimg
        # (MPVKit's, on macOS) can't draw subtitles onto "bgra" ("osd: Failed
        # rendering OSD"), and its libswscale fills "bgr0"'s fourth byte in.
        known = abilities.known()
        is_zimg_missing = known is not None and not known.has_zimg
        self._format = ctypes.create_string_buffer(
            b"bgr0" if is_zimg_missing else b"bgra"
        )
        self._stride = ctypes.c_size_t()
        self._off = ctypes.c_int(0)
        self._on = ctypes.c_int(1)

        self._draw = (param_type * 6)()
        for slot, (type_id, value) in zip(
            self._draw,
            (
                (self._SW_SIZE, self._size),
                (self._SW_FORMAT, self._format),
                (self._SW_STRIDE, self._stride),
                (param_type.TYPES["block_for_target_time"][0], self._off),
            ),
            strict=False,
        ):
            slot.type_id = type_id
            slot.data = ctypes.addressof(value)

        # the pixels themselves, not where their address is kept
        self._pointer = self._draw[4]
        self._pointer.type_id = self._SW_POINTER

        self._skip = _param_array(
            param_type,
            (("skip_rendering", self._on), ("block_for_target_time", self._off)),
        )

    def draw(self, width: int, height: int, pixels: int) -> None:
        """The next frame drawn into the pixels at this address, BGRA, rows
        one after the other."""

        self._size[0], self._size[1] = width, height
        self._stride.value = width * 4
        self._pointer.data = pixels
        self._render(self._handle, self._draw)

    def skip(self) -> None:
        """The next frame taken and not drawn."""

        self._render(self._handle, self._skip)


def _param_array(param_type, params):
    """Render parameters as libmpv takes them, ending with an empty one."""

    # made zeroed, which leaves the last one the end
    array = (param_type * (len(params) + 1))()

    for slot, (name, value) in zip(array, params, strict=False):
        slot.type_id = param_type.TYPES[name][0]
        slot.data = ctypes.addressof(value)

    return array


class FrameSlot:
    """A finished frame: its pixels, BGRA with the top row first, or with GL
    output its texture, RGBA with the top row first."""

    __slots__ = ("_pixels_ctypes", "height", "is_rgba", "pixels", "texture", "width")

    def __init__(self):
        self.width = 0
        self.height = 0
        self.pixels = None
        # read from OpenGL ES that only gives RGBA
        self.is_rgba = False
        self._pixels_ctypes = None
        self.texture = 0

    def writable(self, width: int, height: int):
        """A ctypes view of the pixels to write a frame this size into.

        A new buffer rather than one resized where the size changed: a
        picture on show can still hold on to the old one. See
        SoftwareVideoSurface.present_rgb32.
        """

        if (self.width, self.height) != (width, height):
            byte_count = width * height * 4
            self.pixels = bytearray(byte_count)
            self._pixels_ctypes = (ctypes.c_ubyte * byte_count).from_buffer(self.pixels)
            self.width, self.height = width, height

        return self._pixels_ctypes


class RenderedVideo:
    """What the render thread keeps of a video, its side of the triple buffer.

    `back` belongs to the renderer and `_front` to the GUI. They only ever
    trade through `_ready`, under the lock. Neither side waits for the other
    and no GL happens under the lock.

    The player says what size to render at and when there is work; see
    MpvPlayer.
    """

    def __init__(self, player, is_software=False):
        self.player = player
        # drawn by libmpv's software renderer, on a thread of its own
        self.is_software = is_software

        self.render_context = None
        self.render_calls: RenderCalls | None = None
        self.needs_update = False
        # when mpv first said there was an update, since it was last looked at
        self.update_said_at = 0.0
        # mpv has said there's a frame, and it hasn't been rendered yet
        self.has_new_frame = False
        # a frame that came may have been let go: see _FRAME_LET_GO_S
        self.is_frame_lost = False
        # frames were taken and not drawn while it was out of sight
        self.is_out_of_date = False
        self.rendered_size = None
        self.texture = 0

        self._lock = threading.Lock()
        self.back, self._ready, self._front = FrameSlot(), FrameSlot(), FrameSlot()
        self.has_fresh_frame = False

    def slots(self) -> tuple[FrameSlot, FrameSlot, FrameSlot]:
        return self.back, self._ready, self._front

    def take_shown_texture(self, texture: int) -> bool:
        """The texture on show, taken out of the renderer's hands as the video
        goes, so it can stay on show: GUI thread, once nothing more is shown.
        """

        with self._lock:
            if not texture or self._front.texture != texture:
                return False

            self._front.texture = 0
            return True

    def publish(self) -> None:
        with self._lock:
            self.back, self._ready = self._ready, self.back
            self.has_fresh_frame = True

    def latest(self) -> FrameSlot:
        """The newest finished frame: GUI thread."""

        with self._lock:
            if self.has_fresh_frame:
                self._front, self._ready = self._ready, self._front
                self.has_fresh_frame = False

            return self._front


class VideoRenderer(QThread):
    frames_ready = pyqtSignal()
    # the render context failed to come up, for the one video or for all
    failed = pyqtSignal(object, str)

    def __init__(self, mpv_module, gl_share=None, is_software=False, parent=None):
        super().__init__(parent)

        self._mpv = mpv_module
        # a context of Qt's to share textures with, for frames drawn by GL in
        # the window rather than read back
        self._gl_share = gl_share
        self.is_gl_output = gl_share is not None
        # libmpv's software renderer, with no GL at all
        self.is_software = is_software
        self._log = logging.getLogger(self.__class__.__name__)

        self._wake = threading.Event()
        self._is_stopping = False
        self._videos: list[RenderedVideo] = []
        # One queue for opening and closing: a video closed right after it was
        # added has to be seen in that order, whenever this thread gets to look.
        self._jobs = collections.deque()

        self._gl = None
        self._fbo = 0
        # what frames are read back as, and their textures made as: see
        # _pick_formats
        self._read_format = GL_BGRA
        self._texture_format = GL_RGBA8
        self._context = None
        self._context_error = None
        self._platform = QGuiApplication.platformName()
        # for a libmpv that leaks them, once it asks for glFenceSync
        self._frame_fences: FrameFences | None = None

        # Set as frames_ready goes out, cleared by the GUI as it comes to look:
        # videos make many more rounds than the screen has refreshes.
        self.is_present_due = False

        # Qt wants it made on its own thread, for where it comes to Qt's context
        self._qt_surface = None
        if env.IS_MACOS:
            self._qt_surface = QOffscreenSurface()
            # the group's own, where it shares with Qt's: two can't share
            self._qt_surface.setFormat(
                gl_share.qt_context.format()
                if gl_share is not None
                else macos_gl_format()
            )
            self._qt_surface.create()

        # called by libmpv for GL functions, for as long as any video is open
        self._proc_address_fn = self._mpv.MpvGlGetProcAddressFn(self._get_proc_address)

    def add(self, video: RenderedVideo) -> None:
        self._jobs.append((self._init_video, video))
        self.wake()

    def videos_held(self) -> list[RenderedVideo]:
        """Every video it has, or has yet to take: read from another thread
        only once this one is stuck."""

        queued = [video for _job, video in list(self._jobs)]

        return list(dict.fromkeys([*list(self._videos), *queued]))

    def remove(self, video: RenderedVideo) -> None:
        self._jobs.append((self._release_video, video))
        self.wake()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> bool:
        """Finish, freeing every video; False if it didn't in time."""

        self._is_stopping = True
        self.wake()

        return self.wait(STOP_WAIT_MS)

    def run(self):
        if not self.is_software:
            self._start_gl()

        while not self._is_stopping:
            self._wake.wait()
            # cleared before looking at anything, so a wake during the work
            # below means one more round rather than a lost frame
            self._wake.clear()

            while self._jobs:
                job, video = self._jobs.popleft()
                job(video)

            self._render_round()

        self._cleanup()

    def _start_gl(self) -> None:
        try:
            self._context = create_gl_context(
                self._platform, self._qt_surface, share=self._gl_share
            )
            self._gl = _GLFunctions(self._context)
        except GLContextError as e:
            self._log.exception("No GL context")
            self._context_error = str(e)

        if self._context_error is None:
            self._pick_formats()

            fbo = ctypes.c_uint()
            self._gl.glGenFramebuffers(1, ctypes.byref(fbo))
            self._fbo = fbo.value

    def _pick_formats(self) -> None:
        """OpenGL ES takes a texture's format as its pixels' in ES 2, and
        reads back BGRA only by an extension, which Mesa's has. Without it,
        RGBA, which is slower to paint."""

        if not self._context.is_gles:
            return

        self._texture_format = GL_RGBA

        extensions = (self._gl.glGetString(GL_EXTENSIONS) or b"").split()
        if b"GL_EXT_read_format_bgra" not in extensions:
            self._log.info("OpenGL ES reads frames back as RGBA")
            self._read_format = GL_RGBA

    def _get_proc_address(self, _ctx, name) -> int:
        if not self._context:
            return 0

        address = self._context.get_proc_address(name)

        if name == b"glFenceSync" and address:
            return self._fence_sync_for_mpv(address)

        return address

    def _fence_sync_for_mpv(self, address: int) -> int:
        """glFenceSync as mpv is to have it: see FrameFences."""

        if self._frame_fences is None:
            if not leaks_frame_fences(env.MPV_VERSION):
                return address

            delete_sync = self._context.get_proc_address(b"glDeleteSync")
            if not delete_sync:
                return address

            self._log.info(
                "libmpv %s leaves a GL fence for every frame: deleted here",
                env.MPV_VERSION,
            )
            self._frame_fences = FrameFences(address, delete_sync)

        return self._frame_fences.address

    def _new_render_context(self, player):
        if self.is_software:
            return self._mpv.MpvRenderContext(player.mpv, "sw", advanced_control=True)

        return self._mpv.MpvRenderContext(
            player.mpv,
            "opengl",
            opengl_init_params={"get_proc_address": self._proc_address_fn},
            # Direct rendering for software decoding, and an update() that
            # says whether there is really a new frame. In exchange this
            # thread must never wait on the mpv core, which is why the
            # video isn't started here.
            advanced_control=True,
            **self._context.native_params(),
        )

    def _init_video(self, video: RenderedVideo) -> None:
        if self._context_error is not None:
            self.failed.emit(video, self._context_error)
            return

        try:
            video.render_context = self._new_render_context(video.player)
        except Exception as e:
            self._log.exception("No render context")
            self.failed.emit(video, str(e))
            return

        def on_update():
            if not video.needs_update:
                video.update_said_at = time.monotonic()

            video.needs_update = True
            self._wake.set()

        # Set once. python-mpv frees the old callback as it sets a new one,
        # and an mpv thread could be inside it. After free() nothing calls it.
        video.render_context.update_cb = on_update

        if self.is_software:
            video.render_calls = SoftwareRenderCalls(self._mpv, video.render_context)
        else:
            video.render_calls = RenderCalls(self._mpv, video.render_context, self._fbo)
            self._new_textures(video)

        self._videos.append(video)

        video.player.on_render_context_ready()

    def _new_textures(self, video: RenderedVideo) -> None:
        if self.is_gl_output:
            # drawn at whatever size the cell has while it's being resized
            for slot in video.slots():
                slot.texture = self._new_texture(GL_LINEAR)
        else:
            video.texture = self._new_texture()

    def _new_texture(self, scaling=GL_NEAREST) -> int:
        gl = self._gl

        texture = ctypes.c_uint()
        gl.glGenTextures(1, ctypes.byref(texture))
        gl.glBindTexture(GL_TEXTURE_2D, texture.value)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, scaling)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, scaling)

        return texture.value

    def _render_round(self) -> None:
        rendered = []

        for video in list(self._videos):
            # one thread for every video: what goes wrong with one stays with it
            try:
                if self._render_if_due(video):
                    rendered.append(video)
            except Exception as e:  # noqa: PERF203
                self._log.exception("A video failed to render")
                self._videos.remove(video)
                self._free_video(video)
                # its cell stops showing its frame, gone, as it hears of it
                self.failed.emit(video, str(e))

        # Drawn by other contexts, a texture has to be finished first, which GL
        # says takes a finish or a fence: one finish a round does them all.
        if rendered and self.is_gl_output:
            self._gl.glFinish()

        for video in rendered:
            video.publish()

        if rendered and not self.is_present_due:
            self.is_present_due = True
            self.frames_ready.emit()

    def _render_if_due(self, video: RenderedVideo) -> bool:
        if video.needs_update:
            video.needs_update = False
            # required on every update_cb in advanced control mode
            if video.render_context.update():
                video.has_new_frame = True
                video.is_frame_lost = False
            elif time.monotonic() - video.update_said_at >= _FRAME_LET_GO_S:
                video.is_frame_lost = True

        size = video.player.render_size()

        if size is None:
            return False

        # Out of sight, a frame is taken as it comes, or mpv waits on it and the
        # video crawls, but it isn't drawn or read back. Not before the first: the
        # cell has loaded once it has a picture. mpv keeps the last one taken,
        # and draws that when asked again, so it's back at once on show.
        if video.rendered_size is not None and not video.player.is_drawn():
            if video.has_new_frame:
                video.render_calls.skip()
                video.has_new_frame = False
                video.is_out_of_date = True

            return False

        # Not before the first frame: with nothing to draw mpv gives a black
        # picture, which the cell would take for the video having loaded.
        is_resized = video.rendered_size is not None and size != video.rendered_size

        # and it's not a frame that's lost till the video has had one to lose
        is_lost = video.is_frame_lost and video.player.has_restarted

        if not (video.has_new_frame or is_resized or is_lost or video.is_out_of_date):
            return False

        self._render(video, size)
        video.has_new_frame = False
        video.is_frame_lost = False
        video.is_out_of_date = False

        return True

    def _render(self, video: RenderedVideo, size: tuple[int, int]) -> None:
        gl = self._gl
        width, height = size

        if self.is_software:
            pixels = video.back.writable(width, height)
            video.render_calls.draw(width, height, ctypes.addressof(pixels))
            video.rendered_size = size
            return

        gl.glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)

        if self.is_gl_output:
            # the GUI may be drawing the others
            texture = video.back.texture
            is_new_size = (video.back.width, video.back.height) != size
        else:
            texture = video.texture
            is_new_size = video.rendered_size != size

        gl.glBindTexture(GL_TEXTURE_2D, texture)
        if is_new_size:
            gl.glTexImage2D(
                GL_TEXTURE_2D,
                0,
                self._texture_format,
                width,
                height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                None,
            )

        gl.glFramebufferTexture2D(
            GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0
        )

        # block_for_target_time defaults to on: render() sleeps until the
        # frame's display time, up to video-timing-offset per video. Off here,
        # with the offset at 0 so frames aren't early: see MpvPlayer.
        fences = self._frame_fences
        if fences is not None:
            fences.forget()

        video.render_calls.draw(width, height)
        video.rendered_size = size

        if fences is not None:
            fences.delete_last()

        if self.is_gl_output:
            video.back.width, video.back.height = size
            return

        # render() may have left anything bound
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)
        gl.glReadPixels(
            0,
            0,
            width,
            height,
            self._read_format,
            GL_UNSIGNED_BYTE,
            video.back.writable(width, height),
        )
        video.back.is_rgba = self._read_format == GL_RGBA

    def _release_video(self, video: RenderedVideo) -> None:
        # not there if the render context never came up
        if video in self._videos:
            self._videos.remove(video)
            self._free_video(video)

        video.player.on_render_context_gone()

    def _free_video(self, video: RenderedVideo) -> None:
        try:
            video.render_context.free()
        except Exception:
            self._log.exception("A render context failed to free")

        video.render_context = None
        video.render_calls = None

        for owner in (video, *video.slots()):
            if owner.texture:
                texture = ctypes.c_uint(owner.texture)
                self._gl.glDeleteTextures(1, ctypes.byref(texture))
                owner.texture = 0

    def _cleanup(self) -> None:
        # What was queued and never got here: a video not opened yet has
        # nothing to free, one waiting to be closed is still in the list.
        while self._jobs:
            job, video = self._jobs.popleft()
            if job == self._release_video:
                job(video)

        for video in self._videos:
            self._free_video(video)
            video.player.on_render_context_gone()

        self._videos.clear()

        if self._fbo:
            fbo = ctypes.c_uint(self._fbo)
            self._gl.glDeleteFramebuffers(1, ctypes.byref(fbo))

        if self._context is not None:
            self._context.close()
            self._context = None


# Direct's mpvs make their outputs one at a time, the next when the last one's
# is up, or when it's had this long: see MpvRenderService.add_own_window. Only
# on Windows, where NVIDIA's driver crashed; elsewhere all together.
OWN_WINDOW_START_TURN_MS = 1000
OWN_WINDOWS_START_IN_TURN = env.IS_WINDOWS
# None starts while one closed is still going, for at most this long: see
# MpvRenderService.add_own_window
OWN_WINDOW_GONE_WAIT_MS = 3000


class MpvRenderService(QObject):
    """The render thread and when frames go up to the window: one per app.

    N videos at 24 fps come in at random times, and one compose per screen
    refresh is all anyone can see. The thread is there for as long as there are
    videos: it goes with cleanup() and comes back with the next, for OpenGL or
    libmpv's software renderer as that video is. A driver change always reloads,
    which cleans up first, so it's never wanted for both.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._log = logging.getLogger(self.__class__.__name__)

        self.mpv = load_mpv()

        self._renderer: VideoRenderer | None = None

        # Frames drawn by GL in the window, see QtShareGroup. Asked before any
        # cell is made, as each makes its surface for one or the other. Not
        # for software ones, which have no GL.
        self._share_group = self._join_qt_share_group()
        self.is_gl_output = self._share_group is not None

        self._last_present = 0.0

        # what is on the grid, each told when it has a frame to show
        self._listeners: dict[RenderedVideo, object] = {}
        # and what draws into a window of its own, with no render thread
        self._own_window_players: set = set()

        # A QObject goes on the thread it belongs to, which isn't the one that
        # terminates it, so this holds on to them until that is done, and to
        # the window one draws into, which it can still be drawing into then.
        self._players_alive: dict = {}

        # Direct's players held before making their outputs, in turn, and the
        # one making its own: see add_own_window
        self._starts_due: dict = {}
        self._starting = None
        # what tells of the one starting, let go of once its turn is over: mpv
        # says its playback restarted on every seek too
        self._turn_signals: list = []

        self._start_turn = QTimer(self)
        self._start_turn.setSingleShot(True)
        self._start_turn.timeout.connect(self._start_next)
        # how long the starts due have waited for one closed to go
        self._gone_wait = QElapsedTimer()

    def _join_qt_share_group(self) -> QtShareGroup | None:
        if not env.MPV_GL_OUTPUT:
            return None

        try:
            share_group = QtShareGroup()
            # The render thread's context shares with it, made as that one is
            # here, now: some drivers won't share, and no cell can take frames
            # drawn by GL once it's made for them.
            create_gl_context(QGuiApplication.platformName(), share=share_group).close()
        except GLContextError:
            self._log.exception("No GL output, frames read back instead")
            return None

        return share_group

    def delete_textures(self, textures: list[int]) -> None:
        """Frames drawn by GL that a cell kept on show, gone: GUI thread."""

        self._share_group.delete_textures(textures)

    def _start_renderer(self, is_software: bool) -> VideoRenderer:
        renderer = VideoRenderer(
            self.mpv,
            None if is_software else self._share_group,
            is_software=is_software,
            parent=self,
        )
        renderer.frames_ready.connect(self._on_frames_ready, Qt.QueuedConnection)
        renderer.failed.connect(self._on_failed, Qt.QueuedConnection)
        renderer.start()

        return renderer

    def add(self, video: RenderedVideo, listener) -> None:
        if (
            self._renderer is not None
            and self._renderer.is_software != video.is_software
        ):
            # what a reload does first, see the class
            self._log.error("A video of another kind came without a cleanup")
            self.cleanup()

        if self._renderer is None:
            self._renderer = self._start_renderer(video.is_software)

        self._keep_alive(video.player)

        self._listeners[video] = listener
        self._renderer.add(video)

    def add_own_window(self, player) -> None:
        """A player drawing into a window of its own: told of settings, kept
        alive until it's terminated, as one the render thread draws. It opens
        its file at once, and is held as it has, before it makes its output
        (output_due), until its turn here. So is its video track turned on
        with none shown, making an output again, or off, letting go of it.

        NVIDIA's Direct3D 11 driver crashed the app (an access violation on a
        thread of its own, in nvwgf2umx.dll) about once in 250 times three
        mpvs started together, their outputs coming up at once. Started 0.4 s
        apart, none in 1440. So each waits for the one before it to have its
        output up, or to play, or to fail, or for OWN_WINDOW_START_TURN_MS,
        whichever comes first. Not under X11 (OWN_WINDOWS_START_IN_TURN), which
        never crashed: all go on together there.

        Everywhere they wait too for every one closed to be gone, or for
        OWN_WINDOW_GONE_WAIT_MS. glibc aborted the app on a heap broken as one
        mpv let go of its X11 output and another's set its own up (in libXext's
        and libXrandr's lists of X displays, and EGL's), about once in 3 runs
        of mpv_subtitles' reloads on Ubuntu 24.04. On an AMD GPU under Windows
        the heap broke in Direct3D 11 the same way: 6 in 24 runs of opening
        three and closing them, in turn, 60 times a run; 0 in 48 once they
        waited.

        The first waits too, for what's being done now: a reload or a driver
        change lays its cells out and shows them after making their players.
        Under X11, mpv mistakes its window's parent being shown, as it starts,
        for its own window being shown, and never shows it: the cell went on
        showing what was there before.
        """

        self._keep_alive(player)
        self._own_window_players.add(player)

        player.output_due.connect(self._queue_output, Qt.QueuedConnection)

    def _queue_output(self, player) -> None:
        # closed as it came
        if player not in self._own_window_players:
            return

        # in the order they came: a dict for taking one closed out
        self._starts_due[player] = None

        if self._starting is None and not self._start_turn.isActive():
            self._start_turn.start(0)

    def remove_own_window(self, player, window: QWidget) -> None:
        """Its window kept until mpv is done with it, then deleted."""

        self._own_window_players.discard(player)
        self._starts_due.pop(player, None)

        self._players_alive[player] = window

        # the next once what closed it is done: a reload or a driver change,
        # whose cells are to be shown first, as for the first (see above)
        if player is self._starting:
            self._end_turn()
            self._start_turn.start(0)

    def _start_next(self) -> None:
        self._end_turn()

        if self._is_waiting_for_gone():
            return

        if not OWN_WINDOWS_START_IN_TURN:
            # all of them, once what made them is done
            while self._starts_due:
                self._next_due().let_output_start()
            return

        while self._starts_due:
            player = self._next_due()
            self._starting = player
            self._start_turn.start(OWN_WINDOW_START_TURN_MS)

            # before it's let go on: it can say so at once, from mpv's thread.
            # A video track turned on or off is waited for only by its output:
            # playing, it says it has restarted or ended for its own reasons
            on_started = partial(self._on_started, player)
            signals = [player.output_done]
            if player.is_output_held:
                signals += [
                    player.playback_restarted,
                    player.failed,
                    player.end_reached,
                ]
            for signal in signals:
                self._turn_signals.append(
                    (signal, signal.connect(on_started, Qt.QueuedConnection))
                )

            if player.let_output_start():
                self._log.debug(
                    f"Starting an mpv, {len(self._starts_due)} more waiting"
                )
                return

            # stopped meanwhile, or nothing made: nothing to wait for
            self._end_turn()

    def _next_due(self):
        player = next(iter(self._starts_due))
        del self._starts_due[player]

        return player

    def _is_waiting_for_gone(self) -> bool:
        """Whether the starts due wait on for one closed to go: started again as
        it does (_forget_player), or once they've waited long enough."""

        is_one_going = any(
            window is not None for window in self._players_alive.values()
        )

        if not (self._starts_due and is_one_going):
            self._gone_wait.invalidate()
            return False

        if not self._gone_wait.isValid():
            self._gone_wait.start()

        left = OWN_WINDOW_GONE_WAIT_MS - self._gone_wait.elapsed()

        if left > 0:
            self._start_turn.start(left)
            return True

        self._log.warning("An mpv closed hasn't gone, starting the next all the same")
        self._gone_wait.invalidate()

        return False

    def _on_started(self, player, *_) -> None:
        if player is self._starting:
            self._start_next()

    def _end_turn(self) -> None:
        self._start_turn.stop()
        self._starting = None

        for signal, connection in self._turn_signals:
            # its player can be gone already
            with suppress(TypeError, RuntimeError):
                signal.disconnect(connection)

        self._turn_signals.clear()

    def _keep_alive(self, player) -> None:
        self._players_alive[player] = None
        player.terminated.connect(self._forget_player, Qt.QueuedConnection)

    def _forget_player(self, player) -> None:
        window = self._players_alive.pop(player, None)

        # gone already with what it was last put in
        if window is not None:
            with suppress(RuntimeError):
                window.deleteLater()

        # the starts waiting for it to go (see add_own_window)
        if self._gone_wait.isValid():
            self._start_turn.start(0)

    def remove(self, video: RenderedVideo) -> None:
        self._listeners.pop(video, None)

        if self._renderer is not None:
            self._renderer.remove(video)

    def wake(self) -> None:
        if self._renderer is not None:
            self._renderer.wake()

    def _players(self) -> list:
        return [video.player for video in self._listeners] + list(
            self._own_window_players
        )

    def set_log_level(self, log_level: int) -> None:
        for player in self._players():
            player.set_log_level(log_level)

    def set_skip_frames(self, is_skipping: bool) -> None:
        for player in self._players():
            player.set_skip_frames(is_skipping)

    def set_picture_quality(self, quality) -> None:
        for player in self._players():
            player.set_picture_quality(quality)

    def set_subtitle_style(self, style: dict) -> None:
        for player in self._players():
            player.set_subtitle_style(style)

    def cleanup(self) -> None:
        self._listeners.clear()

        self._starts_due.clear()
        self._end_turn()
        self._gone_wait.invalidate()

        if self._renderer is None:
            return

        renderer, self._renderer = self._renderer, None

        if renderer.stop():
            renderer.deleteLater()
            return

        # Its videos' mpvs stay too: one can't go before its render context
        # does. Stopped, at least, so none plays on with no cell to show it;
        # should the thread come through after all, it lets them go. The next
        # video gets a new thread.
        self._log.error(
            "The render thread didn't stop in %.0f s, left behind",
            STOP_WAIT_MS / 1000,
        )
        renderer.setParent(None)
        _left_behind.append(renderer)

        for video in renderer.videos_held():
            video.player.stop_playing()

    def _on_failed(self, video, message: str) -> None:
        listener = self._listeners.get(video)

        if listener is not None:
            listener.render_failed(message)

    def _on_frames_ready(self) -> None:
        elapsed_ms = (time.perf_counter() - self._last_present) * 1000

        QTimer.singleShot(
            int(max(0.0, self._frame_interval_ms() - elapsed_ms)),
            Qt.PreciseTimer,
            self._present,
        )

    def _frame_interval_ms(self) -> float:
        return 1000 * paint_interval_s(QGuiApplication.primaryScreen())

    def _present(self) -> None:
        # before looking at the frames: one finished after this says so again
        if self._renderer is not None:
            self._renderer.is_present_due = False

        self._last_present = time.perf_counter()

        for video, listener in list(self._listeners.items()):
            if video.has_fresh_frame:
                listener.show_frame(video.latest())
