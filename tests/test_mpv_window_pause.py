"""MPV's Direct output, a live stream paused: mpv's window shows nothing once
the stream is let go of, so its picture is put up over it first
(widgets/video_frame_mpv_window.py)."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QImage

from gridplayer.widgets.video_frame_mpv_window import (
    VideoDriverMpvWindow,
    VideoFrameMpvWindow,
)


@pytest.fixture
def driver(mocker):
    mocker.patch.object(VideoDriverMpvWindow, "snapshot_image")
    driver = VideoDriverMpvWindow.__new__(VideoDriverMpvWindow)
    driver._player = MagicMock(is_picture_held=False, is_pause_asked=True)
    driver._is_pause_due = False
    return driver


def test_a_live_stream_loaded_paused_is_let_go_of_once_its_picture_is_up(driver):
    player = driver._player

    driver._pause_live_at_load(player)

    player.set_pause.assert_not_called()
    player.take_screenshot.assert_called_once()

    picture = QImage(4, 4, QImage.Format.Format_RGB32)
    driver._on_picture_taken(picture, False)

    driver.snapshot_image.emit.assert_called_once_with(picture)
    player.set_pause.assert_called_once_with(True)

    # and only then
    driver._on_picture_taken(picture, False)
    player.set_pause.assert_called_once_with(True)


def test_a_live_stream_played_before_its_picture_came_plays_on(driver):
    player = driver._player

    driver._pause_live_at_load(player)
    player.is_pause_asked = False
    driver._on_picture_taken(QImage(4, 4, QImage.Format.Format_RGB32), False)

    # its picture not put up either, which would be taken for a pause asked
    driver.snapshot_image.emit.assert_not_called()
    player.set_pause.assert_not_called()


@pytest.fixture
def frame(mocker):
    for name in ("size", "_shown_picture_rect"):
        mocker.patch.object(VideoFrameMpvWindow, name)
    mocker.patch.object(VideoFrameMpvWindow, "_cut_to_view", side_effect=lambda i: i)
    frame = VideoFrameMpvWindow.__new__(VideoFrameMpvWindow)
    frame.pause_snapshot = MagicMock()
    frame.video_clip = MagicMock()
    frame.video_driver = MagicMock()
    frame._is_status_change_in_progress = True
    return frame


def test_paused_again_before_it_was_back_keeps_the_picture_up(frame):
    picture = QImage(4, 4, QImage.Format.Format_RGB32)
    frame.pause_snapshot.isVisible.return_value = False
    frame._on_snapshot_image(picture)

    # played, and paused again before mpv showed it: no picture to take
    frame.pause_snapshot.isVisible.return_value = True
    frame.pause_snapshot.reset_mock()
    frame._on_snapshot_image(None)

    assert frame._paused_picture is picture
    frame.pause_snapshot.set_snapshot_file.assert_not_called()
    frame.pause_snapshot.set_pixmap.assert_called_once()
    frame.video_driver.set_pause.assert_called_with(True)


def test_no_picture_and_none_up_shows_none(frame):
    frame.pause_snapshot.isVisible.return_value = False
    frame._paused_picture = None

    frame._on_snapshot_image(None)

    frame.pause_snapshot.set_snapshot_file.assert_called_once_with("")


def test_a_restart_on_its_way_as_it_closes_shows_nothing(driver):
    driver._player = None
    driver.playback_started_emit = MagicMock()

    driver._on_playback_restarted()

    driver.playback_started_emit.assert_not_called()
