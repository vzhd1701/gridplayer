from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _block(mocker, **video_kwargs):
    block = mocker.Mock()
    block.video_params = Video(uri="http://example.com/a.mp4", **video_kwargs)
    return block


def test_loop_end_stop_without_explicit_loop(mocker):
    block = _block(mocker, end_action=VideoEndAction.STOP, loop_end=None)

    VideoBlock.loop_end_action(block)

    block.stop_playback.assert_called_once()
    block._loop_to_start.assert_not_called()
    block.next_video.assert_not_called()


def test_loop_end_close_schedules_close(mocker):
    block = _block(mocker, end_action=VideoEndAction.CLOSE, loop_end=None)
    single_shot = mocker.patch("gridplayer.widgets.video_block.QTimer.singleShot")

    VideoBlock.loop_end_action(block)

    single_shot.assert_called_once_with(0, block.close)
    block.stop_playback.assert_not_called()
    block._loop_to_start.assert_not_called()


def test_loop_end_loop_file_still_loops(mocker):
    block = _block(mocker, end_action=VideoEndAction.LOOP_FILE, loop_end=None)

    VideoBlock.loop_end_action(block)

    block._loop_to_start.assert_called_once()
    block.stop_playback.assert_not_called()


def test_loop_end_next_file(mocker):
    block = _block(mocker, end_action=VideoEndAction.NEXT_FILE, loop_end=None)

    VideoBlock.loop_end_action(block)

    block.next_video.assert_called_once()
    block._loop_to_start.assert_not_called()


def test_loop_end_previous_file(mocker):
    block = _block(mocker, end_action=VideoEndAction.PREVIOUS_FILE, loop_end=None)

    VideoBlock.loop_end_action(block)

    block.previous_video.assert_called_once()
    block.next_video.assert_not_called()


def test_loop_end_shuffle_file(mocker):
    block = _block(mocker, end_action=VideoEndAction.SHUFFLE_FILE, loop_end=None)

    VideoBlock.loop_end_action(block)

    block.shuffle_video.assert_called_once()


def test_loop_end_pause_at_start(mocker):
    block = _block(mocker, end_action=VideoEndAction.PAUSE, loop_end=None)

    VideoBlock.loop_end_action(block)

    block._pause_at_start.assert_called_once()
    block.stop_playback.assert_not_called()
    block._destroy_video_driver.assert_not_called()


def test_pause_at_start_seeks_and_pauses(mocker):
    block = mocker.Mock()
    block.loop_start = 0

    VideoBlock._pause_at_start(block)

    block.seek.assert_called_once_with(0)
    block.set_pause.assert_called_once_with(True)
    block.stop_playback.assert_not_called()
    block._destroy_video_driver.assert_not_called()


def test_loop_end_stop_with_segment_still_loops(mocker):
    block = _block(mocker, end_action=VideoEndAction.STOP, loop_end=5000)

    VideoBlock.loop_end_action(block)

    block._loop_to_start.assert_called_once()
    block.stop_playback.assert_not_called()
    block.close.assert_not_called()


def test_loop_start_without_end_loops_when_stop(mocker):
    block = _block(
        mocker, end_action=VideoEndAction.STOP, loop_start=1500, loop_end=None
    )

    VideoBlock.loop_end_action(block)

    block._loop_to_start.assert_called_once()
    block.stop_playback.assert_not_called()
    block.close.assert_not_called()


def test_loop_start_without_end_loops_when_close(mocker):
    block = _block(
        mocker, end_action=VideoEndAction.CLOSE, loop_start=1500, loop_end=None
    )
    single_shot = mocker.patch("gridplayer.widgets.video_block.QTimer.singleShot")

    VideoBlock.loop_end_action(block)

    block._loop_to_start.assert_called_once()
    single_shot.assert_not_called()
    block.stop_playback.assert_not_called()


def test_stopped_overlay_uses_hide_timer(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block._ctx.is_overlay_hide_on_timeout = True
    block._ctx.overlay_timeout = 3
    block.is_stopped = True
    block.is_loading = False
    block._is_error = False
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.overlay.show.assert_called_once()
    block.overlay_hide_timer.start.assert_called_once_with(3000)

    VideoBlock.hide_overlay(block)

    block.overlay.hide.assert_called_once()


def test_stop_playback_destroys_driver(mocker):
    block = mocker.Mock()
    block.video_params = Video(uri="http://example.com/a.mp4")

    VideoBlock.stop_playback(block)

    block._set_playback_state.assert_called_once_with(VideoInitialState.STOPPED)
    block._destroy_video_driver.assert_called_once()
    block.video_status.hide.assert_called_once()
    block.show_overlay.assert_called()


def test_stop_playback_resets_position_and_segment_loop(mocker):
    block = mocker.Mock()
    block.video_params = Video(
        uri="http://example.com/a.mp4",
        current_position=12345,
        loop_start=1000,
        loop_end=5000,
        is_paused=False,
    )

    VideoBlock.stop_playback(block)

    assert block.video_params.current_position == 0
    assert block.video_params.loop_start is None
    assert block.video_params.loop_end is None
    block.loop_start_change.emit.assert_called_with(0)
    block.loop_end_change.emit.assert_called_with(100.0)


def test_set_playback_state_syncs_overlay_when_already_playing(mocker):
    block = _block(mocker, playback_state=VideoInitialState.PLAYING)

    VideoBlock._set_playback_state(block, VideoInitialState.PLAYING)

    block.is_paused_change.emit.assert_called_once_with(False)
    block.is_stopped_change.emit.assert_not_called()
    block.show_overlay.assert_not_called()


def test_set_playback_state_syncs_overlay_when_already_stopped(mocker):
    block = _block(mocker, playback_state=VideoInitialState.STOPPED)

    VideoBlock._set_playback_state(block, VideoInitialState.STOPPED)

    block.is_paused_change.emit.assert_called_once_with(True)
    block.is_stopped_change.emit.assert_called_once_with(True)
    block.show_overlay.assert_called_once()


def test_set_video_stopped_defers_load(mocker):
    block = mocker.Mock()
    block.video_params = None
    block.is_video_initialized = False
    video = Video(uri="http://example.com/a.mp4", is_paused=True, is_stopped=True)

    VideoBlock.set_video(block, video)

    assert block.video_params is video
    block._present_stopped.assert_called_once()
    block._start_load.assert_not_called()
    block.reset.assert_not_called()


def test_apply_snapshot_stopped_destroys_driver(mocker):
    block = mocker.Mock()
    snapshot = Video(uri="http://example.com/a.mp4", is_paused=True, is_stopped=True)
    block.video_params = Video(uri=snapshot.uri, is_paused=False, is_stopped=False)
    block._default_title = "a.mp4"

    VideoBlock.apply_snapshot(block, snapshot)

    assert block.video_params.is_stopped is True
    block._destroy_video_driver.assert_called_once()
    block._present_stopped.assert_called_once()
    block._start_load.assert_not_called()


def test_apply_snapshot_playing_on_stopped_starts_load(mocker):
    block = mocker.Mock()
    snapshot = Video(uri="http://example.com/a.mp4", is_paused=False, is_stopped=False)
    block.video_params = Video(uri=snapshot.uri, is_paused=True, is_stopped=True)
    block.is_video_initialized = False
    block._default_title = "a.mp4"

    VideoBlock.apply_snapshot(block, snapshot)

    assert block.video_params.is_stopped is False
    block._start_load.assert_called_once()
    block._present_stopped.assert_not_called()
    block._destroy_video_driver.assert_not_called()


def test_set_video_playing_starts_load(mocker):
    block = mocker.Mock()
    block.video_params = None
    block.is_video_initialized = False
    video = Video(uri="http://example.com/a.mp4", is_paused=False, is_stopped=False)

    VideoBlock.set_video(block, video)

    block._present_stopped.assert_not_called()
    block._start_load.assert_called_once()


def test_set_pause_uninitialized_stopped_loads(mocker):
    block = mocker.Mock()
    block._is_state_change_in_progress = False
    block.is_video_initialized = False
    block.video_params = mocker.Mock()

    VideoBlock.set_pause(block, False)

    block._load_and_play.assert_called_once()
    block.video_driver.play.assert_not_called()
    block.video_driver.set_pause.assert_not_called()


def test_set_pause_uninitialized_pause_is_noop(mocker):
    block = mocker.Mock()
    block._is_state_change_in_progress = False
    block.is_video_initialized = False
    block.video_params = mocker.Mock()

    VideoBlock.set_pause(block, True)

    block._load_and_play.assert_not_called()
    block.video_driver.set_pause.assert_not_called()


def test_switch_video_stopped_same_file_loads(mocker):
    uri = Path("/tmp/a.mp4")
    block = mocker.Mock()
    block.is_local_file = True
    block.video_params = mocker.Mock(uri=uri)
    block.is_video_initialized = False

    VideoBlock.switch_video(block, uri)

    block._load_and_play.assert_called_once()
    block.seek.assert_not_called()
    block.set_video.assert_not_called()


def test_switch_video_initialized_same_file_seeks(mocker):
    uri = Path("/tmp/a.mp4")
    block = mocker.Mock()
    block.is_local_file = True
    block.video_params = mocker.Mock(uri=uri)
    block.is_video_initialized = True
    block.loop_start = 0

    VideoBlock.switch_video(block, uri)

    block.seek.assert_called_once_with(0)
    block._load_and_play.assert_not_called()


def test_switch_video_stopped_other_file_starts_playback(mocker):
    block = mocker.Mock()
    block.is_local_file = True
    block.video_params = mocker.Mock(uri=Path("/tmp/a.mp4"))
    block.is_video_initialized = False

    VideoBlock.switch_video(block, Path("/tmp/b.mp4"))

    assert block.video_params.uri == Path("/tmp/b.mp4")
    assert block.video_params.playback_state is VideoInitialState.PLAYING
    block.set_video.assert_called_once_with(block.video_params)


def test_loop_end_is_the_actual_end(mocker):
    """No margin cut off the end, VLC wraps the input around on its own."""
    block = _block(mocker, loop_end=None)
    block.video_driver.length = 400

    assert VideoBlock.loop_end.fget(block) == 400


def test_loop_end_without_driver(mocker):
    block = _block(mocker, loop_end=None)
    block.video_driver = None

    assert VideoBlock.loop_end.fget(block) == 0


def test_loop_end_explicit_wins(mocker):
    block = _block(mocker, loop_end=1500)
    block.video_driver.length = 2000

    assert VideoBlock.loop_end.fget(block) == 1500


def _wrap_block(mocker, last_time, is_settling=False, length=10000):
    block = mocker.Mock()
    block._last_time = last_time
    block._seek_settle_timer.isActive.return_value = is_settling
    block.video_driver.length = length

    return block


def test_first_time_update_is_not_a_wrap(mocker):
    block = _wrap_block(mocker, None)

    assert VideoBlock._is_loop_wrapped(block, 150) is False
    assert block._last_time == 150


def test_time_moving_forward_is_not_a_wrap(mocker):
    block = _wrap_block(mocker, 150)

    assert VideoBlock._is_loop_wrapped(block, 400) is False
    assert block._last_time == 400


def test_time_falling_back_to_the_start_is_a_wrap(mocker):
    block = _wrap_block(mocker, 9655)

    assert VideoBlock._is_loop_wrapped(block, 401) is True
    assert block._last_time == 401


def test_time_jitter_is_not_a_wrap(mocker):
    """A stream reports its time a few ms backwards now and then."""
    block = _wrap_block(mocker, 2318)

    assert VideoBlock._is_loop_wrapped(block, 2317) is False


def test_short_video_wrap(mocker):
    """A 400ms video hands back only what it has."""
    block = _wrap_block(mocker, 391, length=400)

    assert VideoBlock._is_loop_wrapped(block, 291) is True


def test_no_wrap_without_a_length(mocker):
    block = _wrap_block(mocker, 9655, length=0)

    assert VideoBlock._is_loop_wrapped(block, 401) is False


def test_settling_seek_is_not_a_wrap(mocker):
    """Time updates sent before a seek landed are not a finished pass."""
    block = _wrap_block(mocker, 100, is_settling=True)

    # a stale update from before the seek, then the player settling on it
    assert VideoBlock._is_loop_wrapped(block, 1950) is False
    assert VideoBlock._is_loop_wrapped(block, 150) is False

    assert block._last_time == 100


def test_wrapped_plain_loop_lets_vlc_be(mocker):
    block = _block(mocker, end_action=VideoEndAction.LOOP_FILE)

    VideoBlock._loop_wrapped(block)

    block.loop_end_action.assert_not_called()


def test_wrapped_random_start_acts(mocker):
    block = _block(mocker, end_action=VideoEndAction.LOOP_FILE, is_start_random=True)

    VideoBlock._loop_wrapped(block)

    block.loop_end_action.assert_called_once()


def test_wrapped_with_loop_start_acts(mocker):
    block = _block(mocker, end_action=VideoEndAction.LOOP_FILE, loop_start=1500)

    VideoBlock._loop_wrapped(block)

    block.loop_end_action.assert_called_once()


def test_wrapped_stop_acts(mocker):
    block = _block(mocker, end_action=VideoEndAction.STOP)

    VideoBlock._loop_wrapped(block)

    block.loop_end_action.assert_called_once()


def _playing_block(mocker, is_wrapped):
    block = mocker.Mock()
    block.is_video_initialized = True
    block.is_live = False
    block.is_stopped = False
    block.loop_start = 0
    block.loop_end = 2000
    block._is_loop_wrapped.return_value = is_wrapped

    return block


def test_time_changed_plays_up_to_the_end(mocker):
    """The last stretch of a video is not cut off any more."""
    block = _playing_block(mocker, is_wrapped=False)

    VideoBlock.time_changed(block, 1903)

    block._loop_wrapped.assert_not_called()
    block.seek.assert_not_called()
    block.loop_end_action.assert_not_called()


def test_time_changed_picks_up_the_wrap(mocker):
    block = _playing_block(mocker, is_wrapped=True)

    VideoBlock.time_changed(block, 100)

    block._loop_wrapped.assert_called_once()
    block.seek.assert_not_called()
    block.loop_end_action.assert_not_called()


def test_seek_holds_off_wrap_detection(mocker):
    block = mocker.Mock()
    block.is_video_initialized = True
    block.is_live = False
    block.loop_start = 0
    block.loop_end = 2000

    VideoBlock.seek(block, 1500)

    block.video_driver.set_time.assert_called_once_with(1500)
    assert block._last_time == 1500
    block._seek_settle_timer.start.assert_called_once()


def test_seek_marks_itself_before_it_is_made(mocker):
    """The mark has to be down before libVLC is asked to move.

    The single process drivers call libVLC on this very thread, and it
    reports the new time from inside the call. A wheel seek past the end
    lands back at the start, and marked afterwards that update reads as a
    finished pass -- running the end action from inside the seek itself.
    """
    block = mocker.Mock()
    block.is_video_initialized = True
    block.is_live = False
    block.loop_start = 0
    block.loop_end = 10000
    seen = {}

    def _set_time(seek_ms):
        seen["last_time"] = block._last_time
        seen["is_settling"] = block._seek_settle_timer.start.called

    block.video_driver.set_time.side_effect = _set_time

    VideoBlock.seek(block, 50)

    assert seen == {"last_time": 50, "is_settling": True}


def _shift_block(mocker, end_action, time=9950, length=10000, **video_kwargs):
    block = _block(mocker, end_action=end_action, **video_kwargs)
    block.is_video_initialized = True
    block.is_live = False
    block.time = time
    block.video_driver.length = length
    block.loop_start = VideoBlock.loop_start.fget(block)
    block.loop_end = VideoBlock.loop_end.fget(block)
    block.is_end_a_loop = VideoBlock.is_end_a_loop.fget(block)

    return block


def test_seek_past_the_end_runs_the_end_action(mocker):
    """A video meant to move on at the end moves on when seeked there."""
    block = _shift_block(mocker, VideoEndAction.NEXT_FILE)

    VideoBlock.seek_shift_ms(block, 100)

    block.loop_end_action.assert_called_once_with()
    block.seek.assert_not_called()


def test_seek_past_the_end_of_a_looping_video_carries_on(mocker):
    """Wheeling through a looping video stays continuous."""
    block = _shift_block(mocker, VideoEndAction.LOOP_FILE)

    VideoBlock.seek_shift_ms(block, 100)

    block.seek.assert_called_once_with(50)
    block.loop_end_action.assert_not_called()


def test_seek_past_the_end_of_a_segment_carries_on(mocker):
    """A segment loops whatever the end action says, so the seek wraps."""
    block = _shift_block(
        mocker, VideoEndAction.STOP, time=4950, loop_start=1000, loop_end=5000
    )

    VideoBlock.seek_shift_ms(block, 100)

    block.seek.assert_called_once_with(1050)
    block.loop_end_action.assert_not_called()


def test_seek_within_the_video_is_left_alone(mocker):
    block = _shift_block(mocker, VideoEndAction.STOP, time=5000)

    VideoBlock.seek_shift_ms(block, 100)

    block.seek.assert_called_once_with(5100)
    block.loop_end_action.assert_not_called()


def test_seek_before_the_start_still_wraps_to_the_end(mocker):
    """Only the end has an end action; the start keeps wrapping."""
    block = _shift_block(mocker, VideoEndAction.STOP, time=50)

    VideoBlock.seek_shift_ms(block, -100)

    block.seek.assert_called_once_with(9950)
    block.loop_end_action.assert_not_called()


@pytest.mark.parametrize("left_behind", [None, "loading"])
def test_manual_seek_past_the_end_that_takes_the_player_away(mocker, left_behind):
    """Stopped and closed leave no player, and the next file leaves a new one.

    Neither has a position left to report.
    """
    block = mocker.Mock()
    block.is_video_initialized = True
    block.is_live = False

    def _seek_shift_percent(shift_percent):
        block.video_driver = None if left_behind is None else mocker.Mock()
        block.is_video_initialized = False

    block.seek_shift_percent = _seek_shift_percent

    VideoBlock.manual_seek(block, "seek_shift_percent", 1)

    block.sync_time.emit.assert_not_called()
    block.sync_percent.emit.assert_not_called()
