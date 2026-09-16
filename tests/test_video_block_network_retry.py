"""Reloading a network video that failed, instead of giving up on it."""

import logging

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.params.static import NetworkRetryMode
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock, network_retry_limit


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _set_retries(mode, times=3):
    Settings().set("streaming/network_retry_mode", mode)
    Settings().set("streaming/network_retry_times", times)


def _block(mocker, retries=0, countdown=0):
    block = mocker.Mock()
    block._log = logging.getLogger("test")
    block._network_retries = retries
    block._network_retry_countdown = countdown
    block._is_closing = False
    block.video_params = Video(uri="http://example.com/a.mp4")
    return block


def test_no_retry_when_the_setting_says_show_the_error(mocker):
    _set_retries(NetworkRetryMode.OFF)
    block = _block(mocker)

    assert VideoBlock._schedule_network_retry(block) is False
    block._network_retry_timer.start.assert_not_called()


def test_a_retry_is_scheduled_counted_and_waited_for(mocker):
    _set_retries(NetworkRetryMode.TIMES, times=3)
    block = _block(mocker)

    assert VideoBlock._schedule_network_retry(block) is True

    assert block._network_retries == 1
    assert block._network_retry_countdown == 1
    assert block._is_error is False

    # the player is of no use until the video comes back, and holding it
    # keeps a VLC process busy for the whole wait
    block.cleanup.assert_called_once()
    block._network_retry_timer.start.assert_called_once()


def test_retries_stop_at_the_configured_number(mocker):
    _set_retries(NetworkRetryMode.TIMES, times=2)

    assert VideoBlock._schedule_network_retry(_block(mocker, retries=1)) is True
    assert VideoBlock._schedule_network_retry(_block(mocker, retries=2)) is False


def test_infinite_never_stops_retrying(mocker):
    _set_retries(NetworkRetryMode.INFINITE)

    assert VideoBlock._schedule_network_retry(_block(mocker, retries=999)) is True


def test_each_retry_waits_longer_than_the_last(mocker):
    _set_retries(NetworkRetryMode.INFINITE)

    delays = []
    for retries in (0, 1, 2, 3, 4, 20):
        block = _block(mocker, retries=retries)
        VideoBlock._schedule_network_retry(block)
        delays.append(block._network_retry_countdown)

    assert delays == [1, 2, 5, 15, 30, 30]


def test_the_error_is_shown_once_there_is_nothing_left_to_try(mocker):
    block = _block(mocker, retries=2)
    block._schedule_network_retry.return_value = False

    VideoBlock.network_error(block)

    assert block._is_error is True
    assert block._network_retries == 0
    block.set_status.assert_called_once_with("network-error")


def test_no_error_is_shown_while_a_retry_is_pending(mocker):
    block = _block(mocker)
    block._schedule_network_retry.return_value = True

    VideoBlock.network_error(block)

    block.set_status.assert_not_called()
    block.cleanup.assert_not_called()


def test_the_video_is_reloaded_when_the_countdown_runs_out(mocker):
    block = _block(mocker, retries=1, countdown=1)

    VideoBlock._network_retry_tick(block)

    block._network_retry_timer.stop.assert_called_once()
    block.reload.assert_called_once()


def test_the_countdown_is_shown_until_it_runs_out(mocker):
    block = _block(mocker, retries=1, countdown=3)

    VideoBlock._network_retry_tick(block)

    assert block._network_retry_countdown == 2
    block.reload.assert_not_called()
    block._show_network_retry_status.assert_called_once()


def test_a_closing_block_is_not_reloaded(mocker):
    block = _block(mocker, retries=1, countdown=1)
    block._is_closing = True

    VideoBlock._network_retry_tick(block)

    block.reload.assert_not_called()


def test_the_retry_limit_follows_the_setting():
    _set_retries(NetworkRetryMode.OFF)
    assert network_retry_limit() == 0

    _set_retries(NetworkRetryMode.TIMES, times=5)
    assert network_retry_limit() == 5

    _set_retries(NetworkRetryMode.INFINITE)
    assert network_retry_limit() == -1
