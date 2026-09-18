"""Following the pane's size with the stream quality, once it has settled."""

import logging
from functools import partial
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.stream import (
    STREAM_QUALITY_AUDIO_ONLY,
    STREAM_QUALITY_AUTO,
    STREAM_QUALITY_BEST,
    Stream,
    Streams,
)
from gridplayer.models.video import Video
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _streams(with_audio=False, audio_name="Audio 129kbps"):
    streams = {
        quality: Stream(url=f"http://host/{quality}", protocol="http")
        for quality in ("360p", "720p", "1080p")
    }

    if with_audio:
        streams[audio_name] = Stream(
            url="http://host/audio", protocol="http", is_audio_only=True
        )

    return Streams(streams)


DELAY_MS = 15000


def _block(mocker, quality=STREAM_QUALITY_AUTO, playing="360p", pane_height=300):
    block = mocker.Mock()
    block._log = logging.getLogger("test")
    block._is_closing = False
    block._is_error = False
    block._is_state_change_in_progress = False
    block.streams = _streams()
    # these streams name no language, so narrowing by one changes nothing
    block.stream_ladder = block.streams
    block._stream_quality_playing = playing
    block._pane_height_px = pane_height
    block.video_params = Video(uri="http://example.com/a.mp4")
    block.video_params.stream_quality = quality
    block._quality_adapt_delay_ms = DELAY_MS
    return block


def test_the_delay_is_taken_from_the_video_in_milliseconds(mocker):
    block = _block(mocker)
    block.video_params.quality_adapt_delay_sec = 20

    assert VideoBlock._quality_adapt_delay_ms.fget(block) == 20000


def test_a_new_delay_restarts_a_pane_that_is_already_waiting(mocker):
    block = _block(mocker)
    block._quality_adapt_timer.isActive.return_value = True
    block._quality_adapt_delay_ms = 30000

    VideoBlock.set_quality_adapt_delay(block, 30)

    assert block.video_params.quality_adapt_delay_sec == 30
    block._quality_adapt_timer.start.assert_called_once_with(30000)


def test_a_new_delay_does_not_start_a_pane_that_was_not_waiting(mocker):
    block = _block(mocker)
    block._quality_adapt_timer.isActive.return_value = False

    VideoBlock.set_quality_adapt_delay(block, 30)

    assert block.video_params.quality_adapt_delay_sec == 30
    block._quality_adapt_timer.start.assert_not_called()


def test_a_resize_starts_the_wait_before_anything_is_switched(mocker):
    block = _block(mocker)

    VideoBlock._schedule_quality_adapt(block)

    block._quality_adapt_timer.start.assert_called_once_with(DELAY_MS)


def test_a_pane_on_a_rung_the_user_picked_is_left_alone(mocker):
    block = _block(mocker, quality="1080p")

    VideoBlock._schedule_quality_adapt(block)

    block._quality_adapt_timer.start.assert_not_called()


def test_a_pane_with_nothing_playing_has_no_ladder_to_move_on(mocker):
    block = _block(mocker)
    block.streams = Streams()

    VideoBlock._schedule_quality_adapt(block)

    block._quality_adapt_timer.start.assert_not_called()


def test_a_settled_pane_switches_to_the_rung_that_now_fits(mocker):
    block = _block(mocker, playing="360p", pane_height=700)

    VideoBlock._adapt_stream_quality(block)

    block.reset.assert_called_once()
    block.load_stream_quality.assert_called_once_with(STREAM_QUALITY_AUTO)


def test_a_pane_that_still_fits_its_rung_is_not_reloaded(mocker):
    block = _block(mocker, playing="360p", pane_height=300)

    VideoBlock._adapt_stream_quality(block)

    block.reset.assert_not_called()
    block.load_stream_quality.assert_not_called()


def test_a_pane_in_the_middle_of_loading_is_asked_again_later(mocker):
    block = _block(mocker, playing="360p", pane_height=700)
    block._is_state_change_in_progress = True

    VideoBlock._adapt_stream_quality(block)

    block.load_stream_quality.assert_not_called()
    block._quality_adapt_timer.start.assert_called_once_with(DELAY_MS)


def test_a_failing_pane_is_left_to_the_retry_timer(mocker):
    block = _block(mocker, playing="360p", pane_height=700)
    block._is_error = True

    VideoBlock._adapt_stream_quality(block)

    block.load_stream_quality.assert_not_called()
    block._quality_adapt_timer.start.assert_not_called()


def test_a_closing_pane_does_not_start_loading_a_new_stream(mocker):
    block = _block(mocker, playing="360p", pane_height=700)
    block._is_closing = True

    VideoBlock._adapt_stream_quality(block)

    block.load_stream_quality.assert_not_called()


def test_auto_survives_the_rung_it_picked(mocker):
    block = _block(mocker, pane_height=700)

    VideoBlock.load_stream_quality(block, STREAM_QUALITY_AUTO)

    assert block.video_params.stream_quality == STREAM_QUALITY_AUTO
    assert block._stream_quality_playing == "720p"


def test_a_rung_picked_by_hand_is_recorded_as_the_choice(mocker):
    block = _block(mocker)

    VideoBlock.load_stream_quality(block, "720p")

    assert block.video_params.stream_quality == "720p"
    assert block._stream_quality_playing == "720p"


def test_best_survives_the_rung_it_picked(mocker):
    block = _block(mocker)

    VideoBlock.load_stream_quality(block, STREAM_QUALITY_BEST)

    assert block.video_params.stream_quality == STREAM_QUALITY_BEST
    assert block._stream_quality_playing == "1080p"


def test_audio_only_survives_the_rung_it_picked(mocker):
    block = _block(mocker)
    block.streams = _streams(with_audio=True)
    block.stream_ladder = block.streams

    VideoBlock.load_stream_quality(block, STREAM_QUALITY_AUDIO_ONLY)

    assert block.video_params.stream_quality == STREAM_QUALITY_AUDIO_ONLY
    assert block._stream_quality_playing == "Audio 129kbps"


def test_best_is_asked_again_of_a_ladder_that_has_since_changed(mocker):
    """The point of keeping the instruction rather than the rung it named.

    A service renames and drops formats between one resolve and the next,
    and a rung name that is no longer on the ladder falls through to
    whatever _guess_quality can make of it.
    """

    block = _block(mocker)

    VideoBlock.load_stream_quality(block, STREAM_QUALITY_BEST)

    block.streams = Streams(
        {
            quality: Stream(url=f"http://host/{quality}", protocol="http")
            for quality in ("480p", "1440p")
        }
    )
    block.stream_ladder = block.streams

    VideoBlock.load_stream_quality(block, block.video_params.stream_quality)

    assert block._stream_quality_playing == "1440p"


def test_audio_only_is_not_answered_with_video_after_a_reload(mocker):
    """The same, where falling back to the best rung is a mode change.

    An audio-only pane whose format name went missing used to come back
    playing video, which is not a worse answer to the question but an
    answer to a different one.
    """

    block = _block(mocker)
    block.streams = _streams(with_audio=True)
    block.stream_ladder = block.streams

    VideoBlock.load_stream_quality(block, STREAM_QUALITY_AUDIO_ONLY)

    block.streams = _streams(with_audio=True, audio_name="Audio 92kbps [opus]")
    block.stream_ladder = block.streams

    VideoBlock.load_stream_quality(block, block.video_params.stream_quality)

    assert block._stream_quality_playing == "Audio 92kbps [opus]"


def _adapt_delay_action(stream_quality, delay_txt="15 second(s)"):
    """Build the submenu entry the way the action manager really does."""

    from gridplayer.player.manager import Commands
    from gridplayer.player.managers.actions import ActionsManager
    from gridplayer.player.managers.active_block import (
        _quality_adapt_delay_menu_item,
    )

    commands = Commands()
    commands.update(
        {
            "active": lambda name: delay_txt,
            "is_active_param_set_to": lambda attr, value: stream_quality == value,
        }
    )

    manager = Mock(spec=ActionsManager)
    manager._ctx = Mock()
    manager._ctx.commands = commands
    manager.parent = Mock(return_value=None)
    manager._map_dynamic_functions = partial(
        ActionsManager._map_dynamic_functions, manager
    )

    return ActionsManager._make_action(manager, _quality_adapt_delay_menu_item())


def test_the_delay_entry_spells_out_the_wait_it_is_set_to():
    action = _adapt_delay_action(STREAM_QUALITY_AUTO)
    action.adapt()

    assert action.text() == "Adapt after: 15 second(s)"
    assert action.is_skipped is False


def test_the_delay_entry_stays_out_of_sight_on_a_hand_picked_rung():
    assert _adapt_delay_action("1080p").is_skipped is True
