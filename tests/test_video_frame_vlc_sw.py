from threading import Lock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QApplication, QGraphicsPixmapItem

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.widgets.video_frame_vlc_sw import VideoDriverVLCSW, VideoFrameVLCSW


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubSWFrame(VideoFrameVLCSW):
    def driver_setup(self, vlc_options):
        return MagicMock()


def test_sw_frame_cleanup_clears_media():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])
    frame.media = MagicMock()

    frame.cleanup()

    assert frame.media is None
    frame.video_driver.cleanup.assert_called_once()


def _driver_with_mocked_player():
    item = QGraphicsPixmapItem()
    driver = VideoDriverVLCSW(
        image_dest=item,
        process_manager=MagicMock(),
        vlc_options=[],
    )
    return driver, item


def test_process_image_copies_shared_memory_into_pixmap():
    driver, item = _driver_with_mocked_player()
    try:
        mem = SafeSharedMemory(f"test-sw-copy-{uuid4().hex[:12]}", Lock())
        mem.allocate(2 * 2 * 4)
        mem.memory.buf[:] = b"\x00\x00\xff\xff" * 4
        driver._shared_memory = mem
        driver._width = 2
        driver._height = 2

        driver.process_image()

        pix = item.pixmap()
        assert pix.width() == 2
        assert pix.height() == 2
        assert not pix.isNull()
    finally:
        driver.cleanup()


def test_process_image_handles_closed_mapping():
    driver, item = _driver_with_mocked_player()
    try:
        mem = SafeSharedMemory(f"test-sw-closed-{uuid4().hex[:12]}", Lock())
        mem.allocate(2 * 2 * 4)
        driver._shared_memory = mem
        driver._width = 2
        driver._height = 2
        mem.close()

        driver.process_image()

        assert item.pixmap().isNull()
    finally:
        driver.cleanup()
