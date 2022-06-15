import contextlib
import logging

from gridplayer.multiprocess.safe_shared_memory import releasing
from gridplayer.vlc_player.libvlc import vlc


class ImageDecoder(object):
    def __init__(self, shared_memory, frame_ready_cb=None):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)

        self.is_paused = True

        self.lock_cb = self.libvlc_lock_callback()
        self.unlock_cb = self.libvlc_unlock_callback()

        self._stopped = False

        self._row_size = None
        self._width = None
        self._height = None

        self._shared_memory = shared_memory
        self._frame_ready_cb = frame_ready_cb

        self._prev_frame_head = None

    def set_frame(self, width, height):
        self._log.debug(f"Allocating shared memory for {width}x{height} frame")

        self._width = width
        self._height = height

        self._row_size = self._width * 4

        buf_size = self._height * self._row_size

        self._shared_memory.allocate(buf_size)

    def attach_media_player(self, media_player):
        media_player.video_set_callbacks(self.lock_cb, self.unlock_cb, None, None)
        media_player.video_set_format("RV32", self._width, self._height, self._row_size)

    def libvlc_lock_callback(self):
        @vlc.CallbackDecorators.VideoLockCb
        def _cb(opaque, planes):  # noqa: WPS430
            self._shared_memory.lock.acquire()
            planes[0] = self._shared_memory.ptr

        return _cb

    def libvlc_unlock_callback(self):
        @vlc.CallbackDecorators.VideoUnlockCb
        def _cb(opaque, picta, planes):  # noqa: WPS430
            with releasing(self._shared_memory.lock):
                if self._stopped:
                    return

                # Callback is firing while on pause,
                # so check if the frame content actually changed
                if self.is_paused and not self._is_frame_changed():
                    return

                self._frame_ready_cb()

        return _cb

    def stop(self):
        self._log.debug("Stopping image decoder")

        self._stopped = True

        # make sure that memory lock released in case it was locked mid-callback
        with contextlib.suppress(ValueError):
            self._shared_memory.lock.release()

        with self._shared_memory:
            self._shared_memory.close()

    def _is_frame_changed(self):
        new_frame_head = bytes(self._shared_memory.memory.buf[:1024])

        if new_frame_head == self._prev_frame_head:
            return False

        self._prev_frame_head = new_frame_head
        return True
