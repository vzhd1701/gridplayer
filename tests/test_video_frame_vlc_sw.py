from threading import Lock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PyQt5.QtCore import QRect, QSize
from PyQt5.QtWidgets import QApplication

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.params.static import VideoAspect, VideoTransform, ViewParams
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets.video_frame_vlc_sw import VideoDriverVLCSW, VideoFrameVLCSW
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubSWFrame(VideoFrameVLCSW):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _surface(width, height, frame_w, frame_h):
    surface = SoftwareVideoSurface()
    surface.resize(width, height)
    surface.present_rgb32(bytes(frame_w * frame_h * 4), frame_w, frame_h)
    return surface


def test_software_surface_fit_covers_widget():
    surface = _surface(200, 100, 2, 2)
    surface.set_view(ViewParams(VideoAspect.FIT))

    placement = surface.placement()

    assert placement.target == (0, 0, 200, 100)
    assert placement.source == pytest.approx((0, 0.5, 2, 1))


def test_software_surface_zooms_in_the_middle():
    surface = _surface(200, 100, 200, 100)
    surface.set_view(ViewParams(VideoAspect.FIT, 2.0))

    assert surface.placement().source == pytest.approx((50, 25, 100, 50))


def test_software_surface_shows_a_scaled_up_frame_in_its_own_shape():
    """VLC scales a 640x360 picture up to fill a 640x386 frame for the decoder."""

    surface = _surface(640, 360, 640, 386)
    surface.set_view(ViewParams(VideoAspect.NONE), track_size=(640, 360))

    assert surface.picture_size() == (640, 360)
    assert surface.placement().source == pytest.approx((0, 0, 640, 386))
    assert surface.placement().target == pytest.approx((0, 0, 640, 360))
    assert surface.frame_image().size() == QSize(640, 386)


def test_software_surface_zooms_a_scaled_up_frame_in_video_pixels():
    surface = _surface(640, 360, 640, 386)
    surface.set_view(ViewParams(VideoAspect.FIT, 2.0), track_size=(640, 360))

    # the middle 320x180 of the picture, in the frame's own rows
    assert surface.placement().source == pytest.approx((160, 96.5, 320, 193))


@pytest.mark.parametrize("track_size", [(1920, 1080), (640, 360), (0, 0), None])
def test_software_surface_keeps_the_frame_shape_for_a_track_size_that_is_not_it(
    track_size,
):
    """A stream that changed size since still has the old one on its track."""

    surface = _surface(1280, 736, 1280, 736)
    surface.set_view(ViewParams(), track_size=track_size)

    assert surface.picture_size() == (1280, 736)


def test_software_surface_shapes_a_rotated_frame():
    """VLC hands a rotated frame over squeezed into its unrotated size."""

    surface = _surface(640, 640, 640, 386)
    surface.set_view(
        ViewParams(VideoAspect.NONE), VideoTransform.ROTATE_90, track_size=(640, 360)
    )

    assert surface.placement().target == pytest.approx((140, 0, 360, 640))
    assert surface.placement().source == pytest.approx((0, 0, 640, 386))


def test_sw_frame_views_the_frame_in_video_pixels():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])
    frame.resize(640, 360)
    frame.media = MagicMock()
    frame.media.is_audio_only = False
    frame.media.cur_video_track = VideoTrack(
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        video_dimensions=(640, 360),
        fps=None,
    )
    frame.video_surface.present_rgb32(bytes(640 * 386 * 4), 640, 386)

    frame.set_scale(2.0)

    assert frame.video_surface.picture_size() == (640, 360)

    view = frame.screenshot_view()

    assert view.frame_size == (640, 360)
    assert view.view == ViewParams(scale=2.0)
    assert view.cut(640, 386) == (QRect(160, 96, 320, 193), QSize(320, 180))


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
        # macOS rounds a segment up to a whole page
        mem.memory.buf[:16] = b"\x00\x00\xff\xff" * 4
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


def test_frame_is_copied_when_shown_not_when_delivered(mocker):
    driver, surface = _driver_with_mocked_player()
    try:
        mem = SafeSharedMemory(f"test-sw-late-{uuid4().hex[:12]}", Lock())
        mem.allocate(2 * 2 * 4)
        driver._shared_memory = mem
        driver._width = 2
        driver._height = 2
        read = mocker.spy(driver._frame_reader, "read")

        mem.memory.buf[:16] = b"\x01\x01\x01\xff" * 4
        driver.process_image()
        mem.memory.buf[:16] = b"\x02\x02\x02\xff" * 4
        driver.process_image()
        assert read.call_count == 0

        driver._show_frame()
        assert read.call_count == 1
        assert surface.frame_image().pixel(0, 0) == 0xFF020202
    finally:
        driver.cleanup()
