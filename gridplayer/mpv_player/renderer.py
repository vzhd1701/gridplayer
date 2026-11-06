"""The one thread that talks to libmpv's render API, and what hangs off it.

    mpv core threads --update_cb--> render thread: its own GL context, a video
                                    at a time into a texture sized for its
                                    cell, the pixels read back
                                        |
                                    triple buffer per video (a lock, no GL,
                                    no waiting)
                                        |
    GUI thread: a surface paints the newest finished frame with QPainter

There is no GL in the window. Painted like any other widget, a frame arrives
with the size change it goes with, where a GL one reaches the screen in its
own time, sometimes for a size the window no longer has: that vibrates during a
real window resize, and nothing on the GL side fixed it.

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
import sys
import threading
import time

from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QGuiApplication, QOffscreenSurface, QSurfaceFormat

from gridplayer.mpv_player.gl_context import GLContextError, create_gl_context
from gridplayer.mpv_player.libmpv import load_mpv
from gridplayer.params import env

GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_NEAREST = 0x2600
GL_RGBA = 0x1908
GL_BGRA = 0x80E1
GL_RGBA8 = 0x8058
GL_UNSIGNED_BYTE = 0x1401
GL_FRAMEBUFFER = 0x8D40
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

# How often frames go up to the window at most when the screen doesn't say
_MIN_REFRESH_HZ = 30


class _GLFunctions:
    """The GL calls used here. ctypes lets go of the GIL for each."""

    def __init__(self, context):
        for name, signature in _GL_FUNCS.items():
            address = context.get_proc_address(name.encode())
            if not address:
                raise GLContextError(f"OpenGL function {name} is not available")

            setattr(self, name, _GL_PROTO(*signature)(address))


class FrameSlot:
    """A finished frame's pixels, BGRA with the top row first."""

    __slots__ = ("_pixels_ctypes", "height", "pixels", "width")

    def __init__(self):
        self.width = 0
        self.height = 0
        self.pixels = None
        self._pixels_ctypes = None

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

    def __init__(self, player):
        self.player = player

        self.render_context = None
        self.needs_update = False
        # mpv has said there's a frame, and it hasn't been rendered yet
        self.has_new_frame = False
        self.rendered_size = None
        self.texture = 0

        self._lock = threading.Lock()
        self.back, self._ready, self._front = FrameSlot(), FrameSlot(), FrameSlot()
        self.has_fresh_frame = False

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

    def __init__(self, mpv_module, parent=None):
        super().__init__(parent)

        self._mpv = mpv_module
        self._log = logging.getLogger(self.__class__.__name__)

        self._wake = threading.Event()
        self._is_stopping = False
        self._videos: list[RenderedVideo] = []
        # One queue for opening and closing: a video closed right after it was
        # added has to be seen in that order, whenever this thread gets to look.
        self._jobs = collections.deque()

        self._gl = None
        self._fbo = 0
        self._context = None
        self._context_error = None
        self._platform = QGuiApplication.platformName()

        # Set as frames_ready goes out, cleared by the GUI as it comes to look:
        # videos make many more rounds than the screen has refreshes.
        self.is_present_due = False

        # Qt wants it made on its own thread, for where it comes to Qt's context
        self._qt_surface = None
        if env.IS_MACOS:
            self._qt_surface = QOffscreenSurface()
            self._qt_surface.setFormat(QSurfaceFormat())
            self._qt_surface.create()

        # called by libmpv for GL functions, for as long as any video is open
        self._proc_address_fn = self._mpv.MpvGlGetProcAddressFn(self._get_proc_address)

    def add(self, video: RenderedVideo) -> None:
        self._jobs.append((self._init_video, video))
        self.wake()

    def remove(self, video: RenderedVideo) -> None:
        self._jobs.append((self._release_video, video))
        self.wake()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._is_stopping = True
        self.wake()
        self.wait()

    def run(self):
        try:
            self._context = create_gl_context(self._platform, self._qt_surface)
            self._gl = _GLFunctions(self._context)
        except GLContextError as e:
            self._log.exception("No GL context")
            self._context_error = str(e)

        if self._context_error is None:
            fbo = ctypes.c_uint()
            self._gl.glGenFramebuffers(1, ctypes.byref(fbo))
            self._fbo = fbo.value

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

    def _get_proc_address(self, _ctx, name) -> int:
        return self._context.get_proc_address(name) if self._context else 0

    def _init_video(self, video: RenderedVideo) -> None:
        if self._context_error is not None:
            self.failed.emit(video, self._context_error)
            return

        try:
            video.render_context = self._mpv.MpvRenderContext(
                video.player.mpv,
                "opengl",
                opengl_init_params={"get_proc_address": self._proc_address_fn},
                # Direct rendering for software decoding, and an update() that
                # says whether there is really a new frame. In exchange this
                # thread must never wait on the mpv core, which is why the
                # video isn't started here.
                advanced_control=True,
                **self._context.native_params(),
            )
        except Exception as e:
            self._log.exception("No render context")
            self.failed.emit(video, str(e))
            return

        def on_update():
            video.needs_update = True
            self._wake.set()

        # Set once. python-mpv frees the old callback as it sets a new one,
        # and an mpv thread could be inside it. After free() nothing calls it.
        video.render_context.update_cb = on_update

        video.texture = self._new_texture()

        self._videos.append(video)

        video.player.on_render_context_ready()

    def _new_texture(self) -> int:
        gl = self._gl

        texture = ctypes.c_uint()
        gl.glGenTextures(1, ctypes.byref(texture))
        gl.glBindTexture(GL_TEXTURE_2D, texture.value)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

        return texture.value

    def _render_round(self) -> None:
        is_any_rendered = False

        for video in list(self._videos):
            # one thread for every video: what goes wrong with one stays with it
            try:
                is_any_rendered |= self._render_if_due(video)
            except Exception as e:  # noqa: PERF203
                self._log.exception("A video failed to render")
                self._videos.remove(video)
                self._free_video(video)
                self.failed.emit(video, str(e))

        if is_any_rendered and not self.is_present_due:
            self.is_present_due = True
            self.frames_ready.emit()

    def _render_if_due(self, video: RenderedVideo) -> bool:
        if video.needs_update:
            video.needs_update = False
            # required on every update_cb in advanced control mode
            if video.render_context.update():
                video.has_new_frame = True

        size = video.player.render_size()

        if size is None:
            return False

        # Not before the first frame: with nothing to draw mpv gives a black
        # picture, which the cell would take for the video having loaded.
        is_resized = video.rendered_size is not None and size != video.rendered_size

        if not video.has_new_frame and not is_resized:
            return False

        self._render(video, size)
        video.has_new_frame = False
        video.publish()

        return True

    def _render(self, video: RenderedVideo, size: tuple[int, int]) -> None:
        gl = self._gl
        width, height = size

        gl.glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)

        gl.glBindTexture(GL_TEXTURE_2D, video.texture)
        if video.rendered_size != size:
            gl.glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA8,
                width,
                height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                None,
            )

        gl.glFramebufferTexture2D(
            GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, video.texture, 0
        )

        # block_for_target_time defaults to on: render() sleeps until the
        # frame's display time, up to video-timing-offset per video. Off here,
        # with the offset at 0 so frames aren't early: see MpvPlayer.
        video.render_context.render(
            opengl_fbo={"w": width, "h": height, "fbo": self._fbo},
            flip_y=False,
            block_for_target_time=False,
        )

        # render() may have left anything bound
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)
        gl.glReadPixels(
            0,
            0,
            width,
            height,
            GL_BGRA,
            GL_UNSIGNED_BYTE,
            video.back.writable(width, height),
        )

        video.rendered_size = size

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

        texture = ctypes.c_uint(video.texture)
        self._gl.glDeleteTextures(1, ctypes.byref(texture))
        video.texture = 0

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


class MpvRenderService(QObject):
    """The render thread and when frames go up to the window: one per app.

    N videos at 24 fps come in at random times, and one compose per screen
    refresh is all anyone can see. The thread is there for as long as there are
    videos: it goes with cleanup() and comes back with the next.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mpv = load_mpv()

        self._renderer: VideoRenderer | None = None

        self._last_present = 0.0

        # what is on the grid, each told when it has a frame to show
        self._listeners: dict[RenderedVideo, object] = {}

        # A QObject goes on the thread it belongs to, which isn't the one that
        # terminates it, so this holds on to them until that is done.
        self._players_alive = set()

    def _start_renderer(self) -> VideoRenderer:
        renderer = VideoRenderer(self.mpv, parent=self)
        renderer.frames_ready.connect(self._on_frames_ready, Qt.QueuedConnection)
        renderer.failed.connect(self._on_failed, Qt.QueuedConnection)
        renderer.start()

        return renderer

    def add(self, video: RenderedVideo, listener) -> None:
        if self._renderer is None:
            self._renderer = self._start_renderer()

        self._players_alive.add(video.player)
        video.player.terminated.connect(self._forget_player, Qt.QueuedConnection)

        self._listeners[video] = listener
        self._renderer.add(video)

    def _forget_player(self, player) -> None:
        self._players_alive.discard(player)

    def remove(self, video: RenderedVideo) -> None:
        self._listeners.pop(video, None)
        self._renderer.remove(video)

    def wake(self) -> None:
        if self._renderer is not None:
            self._renderer.wake()

    def set_skip_frames(self, is_skipping: bool) -> None:
        for video in self._listeners:
            video.player.set_skip_frames(is_skipping)

    def cleanup(self) -> None:
        self._listeners.clear()

        if self._renderer is not None:
            self._renderer.stop()
            self._renderer.deleteLater()
            self._renderer = None

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
        screen = QGuiApplication.primaryScreen()
        refresh = screen.refreshRate() if screen is not None else 0

        return 1000 / max(refresh, _MIN_REFRESH_HZ)

    def _present(self) -> None:
        # before looking at the frames: one finished after this says so again
        if self._renderer is not None:
            self._renderer.is_present_due = False

        self._last_present = time.perf_counter()

        for video, listener in list(self._listeners.items()):
            if video.has_fresh_frame:
                listener.show_frame(video.latest())
