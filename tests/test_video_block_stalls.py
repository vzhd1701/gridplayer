"""A network video that was playing and stopped moving, or started over long before
its end, which neither player says: loaded again soon once the proxy was turned away
fetching it, else after the buffering timeout; started over, at once."""

import logging

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.models.video import Video
from gridplayer.params.static import VideoInitialState
from gridplayer.settings import Settings
from gridplayer.utils.video_errors import ProxyFailure
from gridplayer.widgets import video_block_recovery
from gridplayer.widgets.video_block_recovery import (
    STALLED_AFTER_FAILURE_S,
    RecoveryControl,
)

LENGTH_MS = 600_000


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(
        str(tmp_path / "test.ini"), QSettings.Format.IniFormat
    )


@pytest.fixture(autouse=True)
def _timers(mocker):
    # a stand-in block is no QObject for the part's timers to belong to
    mocker.patch("gridplayer.widgets.video_block_recovery.QTimer")


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(mocker):
    clock = _Clock()
    mocker.patch.object(video_block_recovery.time, "monotonic", clock)
    return clock


@pytest.fixture
def block(mocker):
    block = mocker.Mock()
    block._log = logging.getLogger("test")
    block.video_params = Video(uri="http://example.com/a.mp4")
    block.video_driver.length = LENGTH_MS
    block.loop_end = LENGTH_MS
    block.time = 60_000
    block.is_video_initialized = True
    block.is_error = False
    block.is_stopped = False
    block.is_live = False
    block.is_seek_on_its_way = False
    block.stream.proxy_failure.return_value = None
    block.stream.sound_failure.return_value = None

    block.recovery = RecoveryControl(block)
    block.recovery._stall_timer.isActive.return_value = False

    return block


def _after(clock, block, seconds):
    """Checked once a second, as the timer would."""

    for _ in range(seconds):
        clock.now += 1
        block.recovery._check_stall()


def _told(block) -> bool:
    return block.video_driver_error.called


def test_loading_starts_the_watch(block, clock):
    block.recovery.watch_stalls()

    block.recovery._stall_timer.start.assert_called_once()


def test_turned_away_it_is_tried_again_soon(block, clock):
    block.recovery.watch_stalls()
    block.stream.proxy_failure.return_value = ProxyFailure(url="u", status=403)

    _after(clock, block, STALLED_AFTER_FAILURE_S - 1)
    assert not _told(block)

    _after(clock, block, 1)
    block.video_driver_error.assert_called_once_with("Buffering timeout")
    block.recovery._stall_timer.stop.assert_called()


def test_with_nothing_said_it_waits_the_buffering_timeout(block, clock):
    block.recovery.watch_stalls()

    _after(clock, block, 29)
    assert not _told(block)

    _after(clock, block, 1)
    assert _told(block)


def test_the_buffering_timeout_is_the_settings(block, clock):
    Settings().set("network/buffering_timeout", 60)
    block.recovery.watch_stalls()

    _after(clock, block, 59)
    assert not _told(block)

    _after(clock, block, 1)
    assert _told(block)


def test_a_second_on_is_a_move(block, clock):
    block.recovery.watch_stalls()

    for _ in range(5):
        _after(clock, block, 9)
        block.time += 9000
        block.recovery.note_time(block.time)

    _after(clock, block, 29)
    assert not _told(block)


def test_creeping_on_is_no_move(block, clock):
    """VLC with a file whose connection was cut: 1.8 s in two minutes."""

    block.recovery.watch_stalls()

    for _ in range(30):
        _after(clock, block, 1)
        block.time += 15
        block.recovery.note_time(block.time)

    assert _told(block)


def test_slowed_down_a_move_is_less(block, clock):
    block.video_params.rate = 0.25
    block.recovery.watch_stalls()

    for _ in range(40):
        _after(clock, block, 1)
        block.time += 250
        block.recovery.note_time(block.time)

    assert not _told(block)


def test_a_seek_back_is_a_move(block, clock):
    block.recovery.watch_stalls()
    _after(clock, block, 25)

    block.recovery.note_time(10_000)
    _after(clock, block, 25)

    assert not _told(block)


def test_paused_it_is_not_stalled(block, clock):
    block.video_params.playback_state = VideoInitialState.PAUSED
    block.recovery.watch_stalls()
    _after(clock, block, 100)

    # and played again, it is watched from then
    block.video_params.playback_state = VideoInitialState.PLAYING
    _after(clock, block, 29)

    assert not _told(block)


def test_at_the_end_it_stops_of_itself(block, clock):
    block.time = LENGTH_MS - 500
    block.recovery.watch_stalls()
    _after(clock, block, 100)

    assert not _told(block)


@pytest.mark.parametrize(
    "unwatched",
    [
        {"is_live": True},
        {"is_error": True},
        {"is_stopped": True},
        {"is_video_initialized": False},
    ],
)
def test_where_a_stop_is_no_stall_it_is_not_watched(block, clock, unwatched):
    for name, value in unwatched.items():
        setattr(block, name, value)

    block.recovery.watch_stalls()
    _after(clock, block, 100)

    assert not _told(block)
    block.recovery._stall_timer.stop.assert_called()


def test_a_local_file_is_not_watched(block, clock, tmp_path):
    file = tmp_path / "a.mp4"
    file.touch()
    block.video_params = Video(uri=file)
    block.recovery.watch_stalls()
    _after(clock, block, 100)

    assert not _told(block)


def test_with_no_length_known_it_is_not_watched(block, clock):
    block.video_driver.length = 0
    block.recovery.watch_stalls()
    _after(clock, block, 100)

    assert not _told(block)


def test_letting_the_player_go_stops_the_watch(block, clock):
    block.recovery.watch_stalls()

    block.recovery.stop()

    block.recovery._stall_timer.stop.assert_called()


def _started_over(block) -> bool:
    """Told on the way out of the time report, as the timer would."""

    told = video_block_recovery.QTimer.singleShot.call_args_list

    for args, _ in told:
        args[1]()

    return block.video_driver_error.call_args_list == [
        (("Video stopped unexpectedly",),)
    ]


def test_starting_over_far_from_the_end_is_told(block, clock):
    block.recovery.watch_stalls()
    block.recovery.note_time(66_000)

    block.recovery.note_time(601)

    assert _started_over(block)


def test_it_is_loaded_again_from_where_it_got_to(block, clock):
    block.recovery.watch_stalls()
    block.recovery.note_time(66_000)
    block.recovery.note_time(601)

    # the time the block kept meanwhile
    block.video_params.current_position = 1601

    assert _started_over(block)
    assert block.video_params.current_position == 66_000


def test_and_told_once(block, clock):
    block.recovery.watch_stalls()
    block.recovery.note_time(66_000)

    block.recovery.note_time(601)
    block.recovery.note_time(1601)
    block.recovery.note_time(66_000)
    block.recovery.note_time(601)

    assert video_block_recovery.QTimer.singleShot.call_count == 1


def test_a_seek_to_the_start_is_not(block, clock):
    block.recovery.watch_stalls()
    block.recovery.note_time(66_000)

    block.is_seek_on_its_way = True
    block.recovery.note_time(0)

    assert not _started_over(block)


def test_going_round_at_the_end_is_not(block, clock):
    block.recovery.watch_stalls()
    block.recovery.note_time(LENGTH_MS - 2000)

    block.recovery.note_time(400)

    assert not _started_over(block)


def test_a_small_step_back_is_not(block, clock):
    block.time = 3000
    block.recovery.watch_stalls()
    block.recovery.note_time(4000)

    block.recovery.note_time(100)

    assert not _started_over(block)


def test_a_local_file_starting_over_is_not(block, clock, tmp_path):
    file = tmp_path / "a.mp4"
    file.touch()
    block.video_params = Video(uri=file)
    block.recovery.watch_stalls()
    block.recovery.note_time(66_000)

    block.recovery.note_time(601)

    assert not _started_over(block)


def test_gone_by_the_time_it_is_told_it_is_not(block, clock):
    """The cell let go of its player in between: nothing left to tell."""

    block.recovery.watch_stalls()
    block.recovery.note_time(66_000)
    block.recovery.note_time(601)

    block.is_error = True

    assert not _started_over(block)


def _plays(block, ms, step=250):
    for _ in range(ms // step):
        block.time += step
        block.recovery.note_time(block.time)


def test_reloads_are_remembered_until_it_has_played_on(block, clock):
    block.recovery._retries = 2

    block.recovery.note_played()
    block.recovery.watch_stalls()
    _plays(block, 29_000)

    assert block.recovery.retries == 2

    _plays(block, 1000)

    assert block.recovery.retries == 0


def test_a_seek_on_is_not_playing_on(block, clock):
    block.recovery._retries = 2
    block.recovery.watch_stalls()

    block.recovery.note_time(block.time + 60_000)

    assert block.recovery.retries == 2


def test_its_sound_turned_away_it_is_loaded_again_at_once(block, clock):
    """MPV plays the picture on, silent, and says nothing."""

    block.recovery.watch_stalls()
    block.stream.sound_failure.return_value = ProxyFailure(url="u", status=403)

    _after(clock, block, 1)

    block.video_driver_error.assert_called_once_with("Can't play the sound")
    block.recovery._stall_timer.stop.assert_called()


def test_a_live_stream_losing_its_sound_is_told_too(block, clock):
    block.is_live = True
    block.recovery.watch_stalls()
    block.stream.sound_failure.return_value = ProxyFailure(url="u", status=403)

    _after(clock, block, 1)

    assert _told(block)


def test_with_its_sound_it_is_left_playing(block, clock):
    block.recovery.watch_stalls()

    _after(clock, block, 5)

    assert not _told(block)
