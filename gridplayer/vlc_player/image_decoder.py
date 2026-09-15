import contextlib
import ctypes
import logging
import zlib

from gridplayer.multiprocess.safe_shared_memory import releasing
from gridplayer.vlc_player.libvlc import vlc

# vendored VideoFormatCb uses c_char_p for chroma, which ctypes converts to
# bytes so writes never reach VLC. Keep a raw pointer instead.
_VideoFormatCb = ctypes.CFUNCTYPE(
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
)

# Frames are only deduplicated while paused, so this sampling never runs in
# the playing hot path. Stripes are spread over the whole buffer: sampling
# just the start of it only covered the top row of the image, so any source
# with a static top edge (sky, a letterbox bar, a fixed camera) looked
# unchanged and its frames were dropped.
_FRAME_SAMPLE_STRIPES = 64
_FRAME_SAMPLE_STRIPE_SIZE = 1024


class ImageDecoder:
    def __init__(self, shared_memory, frame_ready_cb=None, size_ready_cb=None):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)

        self.is_paused = True

        self.lock_cb = self.libvlc_lock_callback()
        self.unlock_cb = self.libvlc_unlock_callback()
        self.format_cb = self.libvlc_format_callback()
        self.cleanup_cb = self.libvlc_cleanup_callback()

        self._stopped = False

        self._row_size = None
        self._width = None
        self._height = None

        self._shared_memory = shared_memory
        self._frame_ready_cb = frame_ready_cb
        self._size_ready_cb = size_ready_cb

        self._prev_frame_digest = None

    def set_frame(self, width, height):
        if width == self._width and height == self._height and self._row_size:
            return

        self._log.debug(f"Allocating shared memory for {width}x{height} frame")

        if self._row_size is not None:
            self._shared_memory.close()

        self._width = width
        self._height = height
        self._row_size = self._width * 4
        self._shared_memory.allocate(self._height * self._row_size)

    def attach_media_player(self, media_player):
        # display=None: VLC 3 vmem copies into our buffer in Prepare (lock/
        # unlock). A Python display callback races that copy on live streams
        # (multiple pooled pictures, one app buffer) and can access-violate.
        media_player.video_set_callbacks(self.lock_cb, self.unlock_cb, None, None)
        media_player.video_set_format_callbacks(self.format_cb, self.cleanup_cb)

    def libvlc_format_callback(self):
        @_VideoFormatCb
        def _cb(opaque, chroma, width, height, pitches, lines):
            if chroma:
                ctypes.memmove(chroma, b"RV32", 4)

            frame_w = width[0]
            frame_h = height[0]
            if not frame_w or not frame_h:
                return 0

            for i in range(5):
                pitches[i] = 0
                lines[i] = 0
            pitches[0] = frame_w * 4
            lines[0] = frame_h

            self.set_frame(frame_w, frame_h)
            if self._size_ready_cb is not None:
                self._size_ready_cb(frame_w, frame_h)
            # VLC's internal vout pool size; lock still uses one app buffer.
            return 3

        return _cb

    def libvlc_cleanup_callback(self):
        @vlc.CallbackDecorators.VideoCleanupCb
        def _cb(opaque):
            self._log.debug("vmem format cleanup")

        return _cb

    def libvlc_lock_callback(self):
        @vlc.CallbackDecorators.VideoLockCb
        def _cb(opaque, planes):
            self._shared_memory.lock.acquire()
            planes[0] = self._shared_memory.ptr
            for i in range(1, 5):
                planes[i] = None

        return _cb

    def libvlc_unlock_callback(self):
        @vlc.CallbackDecorators.VideoUnlockCb
        def _cb(opaque, picta, planes):
            skip = True
            with releasing(self._shared_memory.lock):
                if self._stopped:
                    skip = True
                elif self.is_paused and not self._is_frame_changed():
                    skip = True
                else:
                    skip = False
            if not skip:
                self._on_unlock()

        return _cb

    def _on_unlock(self):
        if self._stopped:
            return

        if self._frame_ready_cb is not None:
            self._frame_ready_cb()

    def stop(self):
        self._log.debug("Stopping image decoder")

        self._stopped = True

        # make sure that memory lock released in case it was locked mid-callback.
        # multiprocessing.Lock raises ValueError; threading.Lock raises RuntimeError.
        with contextlib.suppress(ValueError, RuntimeError):
            self._shared_memory.lock.release()

        with self._shared_memory:
            self._shared_memory.close()

    def _is_frame_changed(self):
        # Called from unlock while the memory lock is already held.
        try:
            new_frame_digest = self._frame_digest()
        except (AttributeError, RuntimeError):
            return False

        if new_frame_digest == self._prev_frame_digest:
            return False

        self._prev_frame_digest = new_frame_digest
        return True

    def _frame_digest(self):
        frame = self._shared_memory.memory.buf
        frame_size = len(frame)

        if frame_size <= _FRAME_SAMPLE_STRIPES * _FRAME_SAMPLE_STRIPE_SIZE:
            return zlib.crc32(frame)

        step = frame_size // _FRAME_SAMPLE_STRIPES

        digest = 0
        for offset in range(0, frame_size - _FRAME_SAMPLE_STRIPE_SIZE, step):
            stripe = frame[offset : offset + _FRAME_SAMPLE_STRIPE_SIZE]
            digest = zlib.crc32(stripe, digest)

        return digest
