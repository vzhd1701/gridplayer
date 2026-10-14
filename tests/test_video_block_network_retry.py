"""Reloading a network video that failed, instead of giving up on it."""

import logging
from unittest.mock import call

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.params.static import NetworkRetryMode
from gridplayer.settings import Settings
from gridplayer.utils.video_errors import ShownError
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_recovery import RecoveryControl


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


@pytest.fixture(autouse=True)
def _timers(mocker):
    # a stand-in block is no QObject for the part's timers to belong to,
    # and what matters is only whether they were started or stopped
    mocker.patch("gridplayer.widgets.video_block_recovery.QTimer")


def _set_retries(mode, times=3):
    # a fresh Video takes these on, which is where a block reads them from
    Settings().set("video_defaults/network_retry_mode", mode)
    Settings().set("video_defaults/network_retry_times", times)


def _block(mocker, retries=0, countdown=0):
    block = mocker.Mock()
    block._log = logging.getLogger("test")
    block._is_closing = False
    block._has_item_played = True
    block.media_list = None
    block.video_params = Video(uri="http://example.com/a.mp4")
    block._last_error = ShownError(title="Connection lost", is_network=True)

    block.recovery = RecoveryControl(block)
    block.recovery._retries = retries
    block.recovery._countdown = countdown
    return block


def test_no_retry_when_the_setting_says_show_the_error(mocker):
    _set_retries(NetworkRetryMode.OFF)
    block = _block(mocker)

    assert block.recovery.schedule_retry() is False
    block.recovery._retry_timer.start.assert_not_called()


def test_a_retry_is_scheduled_counted_and_waited_for(mocker):
    _set_retries(NetworkRetryMode.TIMES, times=3)
    block = _block(mocker)

    assert block.recovery.schedule_retry() is True

    assert block.recovery.retries == 1
    assert block.recovery._countdown == 1
    assert block._is_error is False

    # the player is of no use until the video comes back, and holding it
    # keeps a VLC process busy for the whole wait
    block.cleanup.assert_called_once()
    block.recovery._retry_timer.start.assert_called_once()


def test_retries_stop_at_the_configured_number(mocker):
    _set_retries(NetworkRetryMode.TIMES, times=2)

    assert _block(mocker, retries=1).recovery.schedule_retry() is True
    assert _block(mocker, retries=2).recovery.schedule_retry() is False


def test_infinite_never_stops_retrying(mocker):
    _set_retries(NetworkRetryMode.INFINITE)

    assert _block(mocker, retries=999).recovery.schedule_retry() is True


def test_each_retry_waits_longer_than_the_last(mocker):
    _set_retries(NetworkRetryMode.INFINITE)

    delays = []
    for retries in (0, 1, 2, 3, 4, 20):
        block = _block(mocker, retries=retries)
        block.recovery.schedule_retry()
        delays.append(block.recovery._countdown)

    assert delays == [1, 2, 5, 15, 30, 30]


def test_the_error_is_shown_once_there_is_nothing_left_to_try(mocker):
    _set_retries(NetworkRetryMode.TIMES, times=2)
    block = _block(mocker, retries=2)

    VideoBlock.network_error(block)

    assert block._is_error is True
    assert block._error_tries == 2
    assert block.recovery.retries == 0
    block.set_status.assert_called_once_with("network-error")


def test_no_error_is_shown_while_a_retry_is_pending(mocker):
    _set_retries(NetworkRetryMode.TIMES, times=3)
    block = _block(mocker)

    VideoBlock.network_error(block)

    assert block._is_error is False
    assert call("network-error") not in block.set_status.call_args_list
    block.recovery._retry_timer.start.assert_called_once()


def test_the_video_is_reloaded_when_the_countdown_runs_out(mocker):
    block = _block(mocker, retries=1, countdown=1)

    block.recovery._retry_tick()

    block.recovery._retry_timer.stop.assert_called_once()
    block.reload.assert_called_once()


def test_the_countdown_is_shown_until_it_runs_out(mocker):
    block = _block(mocker, retries=1, countdown=3)

    block.recovery._retry_tick()

    assert block.recovery._countdown == 2
    block.reload.assert_not_called()
    block.video_status.show_reconnect.assert_called_once()


def test_a_closing_block_is_not_reloaded(mocker):
    block = _block(mocker, retries=1, countdown=1)
    block._is_closing = True

    block.recovery._retry_tick()

    block.reload.assert_not_called()


def _limit(mocker):
    return _block(mocker).recovery.retry_limit


def test_the_retry_limit_follows_the_video(mocker):
    _set_retries(NetworkRetryMode.OFF)
    assert _limit(mocker) == 0

    _set_retries(NetworkRetryMode.TIMES, times=5)
    assert _limit(mocker) == 5

    _set_retries(NetworkRetryMode.INFINITE)
    assert _limit(mocker) == -1


def test_two_videos_can_disagree_about_retrying(mocker):
    _set_retries(NetworkRetryMode.OFF)
    stubborn = _block(mocker)
    stubborn.video_params.network_retry_mode = NetworkRetryMode.INFINITE

    giving_up = _block(mocker)

    assert stubborn.recovery.retry_limit == -1
    assert giving_up.recovery.retry_limit == 0


def test_a_block_with_no_video_yet_has_nothing_to_retry(mocker):
    _set_retries(NetworkRetryMode.INFINITE)
    block = _block(mocker)
    block.video_params = None

    assert block.recovery.retry_limit == 0


def test_a_mode_change_with_nothing_pending_just_records_it(mocker):
    block = _block(mocker, retries=2)
    block.recovery._retry_timer.isActive.return_value = False

    block.recovery.set_retry_mode(NetworkRetryMode.INFINITE)

    assert block.video_params.network_retry_mode == NetworkRetryMode.INFINITE
    assert block.recovery.retries == 0
    block.network_error.assert_not_called()


def test_calling_off_a_pending_reload_shows_the_error_instead(mocker):
    block = _block(mocker, retries=1)
    block.recovery._retry_timer.isActive.return_value = True

    block.recovery.set_retry_mode(NetworkRetryMode.OFF)

    block.recovery._retry_timer.stop.assert_called_once()
    block.network_error.assert_called_once()


def test_a_pending_reload_survives_a_switch_to_another_retrying_mode(mocker):
    block = _block(mocker, retries=1)
    block.recovery._retry_timer.isActive.return_value = True

    block.recovery.set_retry_mode(NetworkRetryMode.INFINITE)

    block.recovery._retry_timer.stop.assert_not_called()
    block.network_error.assert_not_called()


def test_a_new_attempt_count_gives_the_video_a_fresh_budget(mocker):
    block = _block(mocker, retries=2)
    mocker.patch(
        "gridplayer.widgets.video_block_recovery.QCustomSpinboxInput.get_int",
        return_value=7,
    )

    block.recovery.retry_times_dialog()

    assert block.video_params.network_retry_times == 7
    assert block.recovery.retries == 0


def test_the_attempt_count_is_what_the_menu_shows(mocker):
    block = _block(mocker)
    block.video_params.network_retry_times = 5

    assert block.recovery.get_retry_times() == "5"
