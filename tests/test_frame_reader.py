import gc
from threading import Lock
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.vlc_player.rgb_buffer import FrameReader, InProcessRgbBuffer
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _buffer_with(data):
    buffer = InProcessRgbBuffer()
    buffer.allocate(len(data))
    buffer.memory.buf[: len(data)] = data
    return buffer


def _pixels(image):
    bits = image.constBits()
    bits.setsize(image.bytesPerLine() * image.height())
    return bytes(bits)


def test_reads_the_frame():
    data = bytes(range(256)) * 2
    reader = FrameReader()

    frame = reader.read(_buffer_with(data), 8, 16)

    assert bytes(frame) == data


def test_reads_only_the_frame_from_a_bigger_buffer():
    buffer = _buffer_with(b"\x01" * 64 + b"\x02" * 1000)

    frame = FrameReader().read(buffer, 4, 4)

    assert bytes(frame) == b"\x01" * 64


def test_skips_frame_bigger_than_the_buffer():
    reader = FrameReader()
    buffer = _buffer_with(b"\x01" * 64)
    frame = reader.read(buffer, 4, 4)

    buffer.memory.buf[:] = b"\x02" * 64

    assert reader.read(buffer, 4, 5) is None
    assert bytes(frame) == b"\x01" * 64


def test_skips_closed_buffer():
    buffer = _buffer_with(b"\x01" * 64)
    buffer.close()

    assert FrameReader().read(buffer, 4, 4) is None


def test_reuses_its_buffer_for_frames_of_one_size():
    reader = FrameReader()
    buffer = _buffer_with(b"\x01" * 64)

    first = reader.read(buffer, 4, 4)
    buffer.memory.buf[:] = b"\x02" * 64
    second = reader.read(buffer, 4, 4)

    assert second is first
    assert bytes(second) == b"\x02" * 64


def test_new_size_gets_a_new_buffer_and_leaves_the_old_one_alone():
    reader = FrameReader()
    buffer = _buffer_with(b"\x01" * 64)
    old = reader.read(buffer, 4, 4)

    buffer.allocate(128)
    buffer.memory.buf[:] = b"\x02" * 128
    new = reader.read(buffer, 8, 4)

    assert new is not old
    assert bytes(old) == b"\x01" * 64
    assert len(new) == 128


def test_shared_memory_closes_right_after_a_read():
    name = f"test-fr-{uuid4().hex[:12]}"
    writer = SafeSharedMemory(name, Lock())
    writer.allocate(64)
    reader_side = SafeSharedMemory(name, Lock())
    reader_side.attach(64)

    FrameReader().read(reader_side, 4, 4)

    # nothing of the read may still hold the mapping open, or closing it
    # has to wait for a collection
    gc.disable()
    try:
        reader_side.memory.close()
    finally:
        gc.enable()
        writer.close()


def test_closed_shared_memory_raises_for_the_driver_to_catch():
    name = f"test-fr-{uuid4().hex[:12]}"
    memory = SafeSharedMemory(name, Lock())
    memory.allocate(64)
    memory.close()

    with pytest.raises(RuntimeError):
        FrameReader().read(memory, 4, 4)


def test_screenshot_is_not_changed_by_the_next_frame():
    surface = SoftwareVideoSurface()
    reader = FrameReader()
    buffer = _buffer_with(b"\x01\x02\x03\xff" * 16)

    surface.present_rgb32(reader.read(buffer, 4, 4), 4, 4)
    shot = surface.frame_image()

    buffer.memory.buf[:] = b"\x09\x08\x07\xff" * 16
    surface.present_rgb32(reader.read(buffer, 4, 4), 4, 4)

    assert _pixels(shot) == b"\x01\x02\x03\xff" * 16
    assert _pixels(surface.frame_image()) == b"\x09\x08\x07\xff" * 16
