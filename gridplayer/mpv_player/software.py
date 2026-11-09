"""Frames out of libmpv's software renderer, into memory the window reads.

python-mpv has no names for the parameters of mpv's software render API, so
they are put together here from libmpv/render.h.
"""

import ctypes
import logging
import traceback
from threading import Event, Thread

from gridplayer.mpv_player.rgb_buffer import holding

_PARAM_SW_SIZE = 17
_PARAM_SW_FORMAT = 18
_PARAM_SW_STRIDE = 19
_PARAM_SW_POINTER = 20

# What Qt's Format_RGB32 is in memory on a little-endian machine.
_FRAME_FORMAT = b"bgr0"

_BYTES_PER_PIXEL = 4


class MpvSoftwareRenderer:
    """Renders each new frame into shared memory, on a thread of its own.

    The size is the one the video is stored at, turned where the file says
    to show it on its side, as the widget expects of a frame. A rotation
    picked by the viewer is left in the frame, squeezed into that same size,
    which is what the widget works its view out from.
    """

    def __init__(self, player, shared_memory, frame_ready_cb, size_ready_cb, crash_cb):
        self._log = logging.getLogger(self.__class__.__name__)

        self._crash_cb = crash_cb

        self._player = player
        self._shared_memory = shared_memory
        self._frame_ready_cb = frame_ready_cb
        self._size_ready_cb = size_ready_cb

        self._context = None
        self._thread = None
        self._wake = Event()
        self._is_stopped = False

        self._stored: tuple[int, int] | None = None
        self._is_turned = False
        self._source: tuple[int, int] | None = None
        self._size: tuple[int, int] | None = None
        self._is_frame_due = False

    def start(self):
        import mpv

        self._context = mpv.MpvRenderContext(self._player, "sw")
        self._context.update_cb = self._wake.set

        self._thread = Thread(target=self._run, name="mpv-software-render")
        self._thread.start()

    def stop(self):
        """Stop rendering. Has to come before the player is terminated."""

        self._is_stopped = True
        self._wake.set()

        if self._thread is not None:
            self._thread.join()
            self._thread = None

        if self._context is not None:
            self._context.update_cb = None
            self._context.free()
            self._context = None

    def set_picture(self, width, height):
        """The decoded picture's size, as it is stored."""

        self._stored = (width, height)
        self._update_source()

    def set_turned(self, is_turned: bool):
        """Whether the file says to show the picture on its side."""

        self._is_turned = is_turned
        self._update_source()

    def _update_source(self):
        if self._stored is None:
            return

        width, height = self._stored

        self._source = (height, width) if self._is_turned else (width, height)
        self._wake.set()

    def _run(self):
        try:
            self._render_loop()
        except Exception:
            # an error kept to this thread would be a pane that stays black
            text = traceback.format_exc()
            self._log.critical(text)
            self._crash_cb(text)

    def _render_loop(self):
        while True:
            self._wake.wait()
            self._wake.clear()

            if self._is_stopped:
                return

            if self._context.update():
                self._is_frame_due = True

            if self._is_frame_due and self._render():
                self._is_frame_due = False
                self._frame_ready_cb()

    def _render(self) -> bool:
        if self._source is None or not all(self._source):
            return False

        if self._source != self._size and not self._resize(*self._source):
            return False

        width, height = self._size

        with holding(self._shared_memory.lock) as is_locked:
            if not is_locked:
                self._log.warning("Frame lock was not given back, dropping a frame")
                return False

            self._render_into(self._shared_memory.ptr, width, height)

        return True

    def _resize(self, width, height) -> bool:
        size = width * height * _BYTES_PER_PIXEL

        try:
            with self._shared_memory:
                self._shared_memory.allocate(size)
        except (OSError, RuntimeError, MemoryError, ValueError) as err:
            self._log.error(f"Failed to allocate {width}x{height} frame: {err}")
            return False

        self._size = (width, height)
        self._size_ready_cb(width, height, self._shared_memory.size)

        return True

    def _render_into(self, pointer, width, height):
        import mpv

        size = (ctypes.c_int * 2)(width, height)
        stride = ctypes.c_size_t(width * _BYTES_PER_PIXEL)
        pixel_format = ctypes.create_string_buffer(_FRAME_FORMAT)

        # one past the last, all zero, is what says the list has ended
        params = (mpv.MpvRenderParam * 5)()

        for index, (type_id, data) in enumerate(
            (
                (_PARAM_SW_SIZE, size),
                (_PARAM_SW_FORMAT, pixel_format),
                (_PARAM_SW_STRIDE, ctypes.byref(stride)),
                (_PARAM_SW_POINTER, pointer),
            )
        ):
            params[index].type_id = type_id
            params[index].data = ctypes.cast(data, ctypes.c_void_p)

        mpv._mpv_render_context_render(self._context.handle, params)
