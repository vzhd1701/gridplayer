from threading import Lock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.params.static import VideoAspect, VideoCrop
from gridplayer.widgets.video_frame_vlc_sw import VideoDriverVLCSW, VideoFrameVLCSW
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubSWFrame(VideoFrameVLCSW):
    def driver_setup(self, vlc_options):
        return MagicMock()


def test_software_surface_fit_covers_widget():
    surface = SoftwareVideoSurface()
    surface.resize(200, 100)
    surface.present_rgb32(b"\x00\x00\x00\xff" * 4, 2, 2)
    surface.set_view(VideoAspect.FIT, 1.0, VideoCrop(0, 0, 0, 0))
    dest = surface._dest_rect(surface._source_rect())
    assert dest.width() >= 200
    assert dest.height() >= 100


def test_sw_frame_cleanup_clears_media():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])
    frame.media = MagicMock()

    frame.cleanup()

    assert frame.media is None
    frame.video_driver.cleanup_start.assert_called_once()
    frame.video_driver.cleanup_wait.assert_called_once()


def _driver_with_mocked_player():
    surface = SoftwareVideoSurface()
    driver = VideoDriverVLCSW(
        image_dest=surface,
        process_manager=MagicMock(),
        vlc_options=[],
    )
    return driver, surface


def test_process_image_copies_shared_memory_into_pixmap():
    driver, surface = _driver_with_mocked_player()
    try:
        mem = SafeSharedMemory(f"test-sw-copy-{uuid4().hex[:12]}", Lock())
        mem.allocate(2 * 2 * 4)
        mem.memory.buf[:] = b"\x00\x00\xff\xff" * 4
        driver._shared_memory = mem
        driver._width = 2
        driver._height = 2

        driver.process_image()
        driver._show_frame()

        assert surface.has_frame()
        assert surface.frame_size() == (2, 2)
    finally:
        driver.cleanup()


def test_process_image_handles_closed_mapping():
    driver, surface = _driver_with_mocked_player()
    try:
        mem = SafeSharedMemory(f"test-sw-closed-{uuid4().hex[:12]}", Lock())
        mem.allocate(2 * 2 * 4)
        driver._shared_memory = mem
        driver._width = 2
        driver._height = 2
        mem.close()

        driver.process_image()
        driver._show_frame()

        assert not surface.has_frame()
    finally:
        driver.cleanup()
