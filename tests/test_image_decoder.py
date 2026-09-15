import ctypes
from multiprocessing import Lock as MPLock
from threading import Lock as ThreadLock
from uuid import uuid4

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory, releasing
from gridplayer.vlc_player.image_decoder import ImageDecoder
from gridplayer.vlc_player.rgb_buffer import InProcessRgbBuffer


def test_in_process_rgb_buffer_allocate_and_close():
    buf = InProcessRgbBuffer()
    buf.allocate(16)
    assert len(buf.memory.buf) == 16
    buf.memory.buf[:] = b"\x01" * 16
    assert buf.ptr is not None
    buf.close()
    assert len(buf.memory.buf) == 0


def test_stop_unlocked_threading_lock():
    decoder = ImageDecoder(SafeSharedMemory("test-imgdec-thread", ThreadLock()))
    decoder.stop()


def test_stop_unlocked_multiprocessing_lock():
    decoder = ImageDecoder(SafeSharedMemory("test-imgdec-mp", MPLock()))
    decoder.stop()


def test_stop_after_allocate_threading_lock():
    name = f"test-imgdec-alloc-{uuid4().hex[:12]}"
    decoder = ImageDecoder(SafeSharedMemory(name, ThreadLock()))
    decoder.set_frame(2, 2)
    decoder.stop()


def test_releasing_unlocked_threading_lock():
    lock = ThreadLock()
    with releasing(lock):
        pass


def test_unlock_notifies_when_playing():
    ready = []
    decoder = ImageDecoder(
        SafeSharedMemory("test-imgdec-unlock", ThreadLock()),
        frame_ready_cb=lambda: ready.append(True),
    )
    decoder.is_paused = False

    decoder._on_unlock()
    decoder._on_unlock()
    assert ready == [True, True]


def test_unlock_skipped_when_stopped():
    ready = []
    decoder = ImageDecoder(
        SafeSharedMemory("test-imgdec-stopped", ThreadLock()),
        frame_ready_cb=lambda: ready.append(True),
    )
    decoder.is_paused = False
    decoder._stopped = True

    decoder._on_unlock()
    assert ready == []


def test_attach_uses_format_callbacks():
    decoder = ImageDecoder(SafeSharedMemory("test-imgdec-attach", ThreadLock()))

    calls = {}

    class _Player:
        def video_set_callbacks(self, lock, unlock, display, opaque):
            calls["cbs"] = (lock, unlock, display, opaque)

        def video_set_format_callbacks(self, setup, cleanup):
            calls["fmt"] = (setup, cleanup)

        def video_set_format(self, chroma, width, height, pitch):
            calls["fixed_fmt"] = (chroma, width, height, pitch)

    decoder.attach_media_player(_Player())

    assert calls["cbs"][0] is decoder.lock_cb
    assert calls["cbs"][1] is decoder.unlock_cb
    assert calls["cbs"][2] is None
    assert calls["fmt"] == (decoder.format_cb, decoder.cleanup_cb)
    assert "fixed_fmt" not in calls


def test_format_callback_allocates_and_notifies_size():
    sizes = []
    decoder = ImageDecoder(
        SafeSharedMemory(f"test-imgdec-fmt-{uuid4().hex[:12]}", ThreadLock()),
        size_ready_cb=lambda w, h: sizes.append((w, h)),
    )

    chroma = (ctypes.c_char * 5)(*b"I420\x00")
    width = ctypes.c_uint(320)
    height = ctypes.c_uint(240)
    pitches = (ctypes.c_uint * 5)()
    lines = (ctypes.c_uint * 5)()
    opaque = ctypes.c_void_p()

    count = decoder.format_cb(
        ctypes.byref(opaque),
        ctypes.addressof(chroma),
        ctypes.byref(width),
        ctypes.byref(height),
        pitches,
        lines,
    )

    assert count == 3
    assert bytes(chroma[:4]) == b"RV32"
    assert pitches[0] == 320 * 4
    assert lines[0] == 240
    assert sizes == [(320, 240)]
    assert decoder._width == 320
    assert decoder._height == 240
    decoder.stop()
