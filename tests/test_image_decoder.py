import contextlib
import ctypes
from multiprocessing import Lock as MPLock
from multiprocessing.shared_memory import SharedMemory
from threading import Lock as ThreadLock
from uuid import uuid4

import pytest

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
        size_ready_cb=lambda w, h, buf: sizes.append((w, h, buf)),
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
    assert sizes == [(320, 240, 320 * 240 * 4)]
    assert decoder._width == 320
    assert decoder._height == 240
    decoder.stop()


def test_a_new_frame_size_moves_both_sides_to_a_new_segment():
    name = f"test-imgdec-resize-{uuid4().hex[:12]}"
    writer = SafeSharedMemory(name, ThreadLock())
    reader = SafeSharedMemory(name, ThreadLock())
    try:
        writer.allocate(2 * 2 * 4)
        reader.attach(2 * 2 * 4)
        assert reader.memory.size >= 2 * 2 * 4

        # the reader is still on the old segment, as it would be until the
        # size change reaches it
        writer.allocate(4 * 4 * 4)
        reader.attach(4 * 4 * 4)

        assert reader.memory.size >= 4 * 4 * 4
    finally:
        reader.close()
        writer.close()


def test_a_segment_left_behind_is_taken_over_rather_than_fought_over():
    name = f"test-imgdec-leftover-{uuid4().hex[:12]}"
    writer = SafeSharedMemory(name, ThreadLock())
    leftover = SharedMemory(name=f"{name}-16", create=True, size=16)
    try:
        writer.allocate(16)

        assert writer.memory.size >= 16
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            leftover.close()
            leftover.unlink()


def test_attaching_to_a_frame_nobody_allocated_says_so():
    reader = SafeSharedMemory(f"test-imgdec-missing-{uuid4().hex[:12]}", ThreadLock())

    with pytest.raises(RuntimeError):
        reader.attach(16)


def test_the_frame_buffer_is_locked_while_it_is_swapped():
    class _Buffer:
        def __init__(self):
            self.lock = ThreadLock()
            self.locked_during_allocate = None

        def allocate(self, size):
            self.locked_during_allocate = self.lock.locked()

        def __enter__(self):
            return self.lock.acquire()

        def __exit__(self, *args):
            return self.lock.release()

    buffer = _Buffer()
    ImageDecoder(buffer).set_frame(2, 2)

    assert buffer.locked_during_allocate is True


def test_a_frame_that_cannot_be_allocated_is_refused():
    sizes = []

    class _Buffer(InProcessRgbBuffer):
        def allocate(self, size):
            raise MemoryError("nope")

    decoder = ImageDecoder(
        _Buffer(), size_ready_cb=lambda w, h, buf: sizes.append((w, h))
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

    assert count == 0
    assert sizes == []
    assert decoder._width is None


def test_the_buffer_never_shrinks_under_an_output_on_its_way_out():
    buffer = InProcessRgbBuffer()
    buffer.allocate(1920 * 1152 * 4)
    big = buffer.ptr

    buffer.allocate(1920 * 1080 * 4)

    assert buffer.size == 1920 * 1152 * 4
    assert buffer.ptr is big


def test_a_shared_buffer_never_shrinks_either():
    name = f"test-imgdec-shrink-{uuid4().hex[:12]}"
    writer = SafeSharedMemory(name, ThreadLock())
    try:
        writer.allocate(1920 * 1152 * 4)
        writer.allocate(1920 * 1080 * 4)

        assert writer.size == 1920 * 1152 * 4
    finally:
        writer.close()
