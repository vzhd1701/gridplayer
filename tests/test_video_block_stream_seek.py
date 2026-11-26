"""Seeking a stream, the way VLC's adaptive demuxer reports it back.

A seek there lands on the segment before its aim and says so first -- seconds
short, up to 10.5s measured on YouTube -- and a seek made while the one before
it is still restarting the stream is turned down, the video playing on from
where that one took it. A real block, on a stand-in frame that reports only
what a test tells it to.

A seek of the viewer's made while the one before is landing waits for it now,
so two meet only when the stream said nothing for SEEK_HOLD_MAX_MS: _no_word.
"""

import dataclasses
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import (
    SEEK_HOLD_MAX_MS,
    SEEK_HOLD_PAUSED_MS,
    SEEK_RETRIES,
    VideoBlock,
)
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy

# short enough that a landing seconds short falls back as far as a pass
# coming round would: an eighth of it
LENGTH = 20000


class _ShortFrame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=LENGTH
        )


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(
        str(tmp_path / "test.ini"), QSettings.Format.IniFormat
    )

    yield

    settings.settings = real_settings


def _context():
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1
    context.synced_view = None
    context.lists = MediaListsRegistry()

    return context


@pytest.fixture
def block(tmp_path, mocker):
    # held on to: a parent collected out from under it takes the block
    parent = QWidget()

    video_file = tmp_path / "movie.mp4"
    video_file.touch()

    block = VideoBlock(video_driver=_ShortFrame, context=_context(), parent=parent)

    block.set_video(
        Video(
            uri=video_file,
            playback_state=VideoInitialState.PAUSED,
            end_action=VideoEndAction.STOP,
        )
    )

    assert block.is_video_initialized

    # what a stream's stand-in would have said, where a file's cannot
    block.stream.is_adaptive = True

    block.set_time = mocker.spy(block.video_driver, "set_time")

    yield block

    block.cleanup()
    block.url_resolver.cleanup()


def _reported(block, time_ms):
    """VLC reporting the time, well after the seek has settled."""

    block._seek_settle_timer.stop()
    block.video_driver.time_changed.emit(time_ms)

    # where a retry is made from
    QApplication.processEvents()


def _seeks(block):
    return [call.args[0] for call in block.set_time.call_args_list]


def _no_word(block):
    """SEEK_HOLD_MAX_MS gone by with no time reported since the last seek."""

    if block._seek_hold_timer.isActive():
        block._seek_hold_timer.stop()
        block._seek_hold_timer.timeout.emit()


class TestLanding:
    def test_landing_short_is_no_pass_coming_round(self, block):
        block.seek(15000)
        _reported(block, 8847)

        assert not block.is_stopped
        assert _seeks(block) == [15000]

    def test_landing_short_of_a_loop_is_not_sent_back(self, block):
        block.loop.set_start_time(12000)
        block.seek(12000)
        _reported(block, 12000 - 2300)
        _reported(block, 12000 - 2290)
        _reported(block, 12400)

        assert _seeks(block) == [12000]

    def test_having_landed_the_time_is_taken_as_it_comes(self, block):
        block.seek(15000)
        _reported(block, 8847)
        _reported(block, 15400)
        _reported(block, 15700)
        _reported(block, 300)

        assert block.is_stopped

    def test_going_round_while_landing_ends_the_pass(self, block):
        block.seek(LENGTH - 500)
        _reported(block, LENGTH - 1200)
        _reported(block, 300)

        assert block.is_stopped


class TestTurnedDown:
    def test_one_made_before_the_last_landed_is_made_again(self, block):
        block.seek(3000)
        _no_word(block)
        block.seek(12000)

        # the first one landing: the second never happened
        _reported(block, 2800)

        assert _seeks(block) == [3000, 12000, 12000]

    def test_where_it_was_turned_down_is_left_alone(self, block):
        block.seek(3000)
        _no_word(block)
        block.seek(12000)

        # as far back as a pass coming round
        _reported(block, 2800)

        assert not block.is_stopped

    def test_the_one_before_repeated_back_says_nothing_yet(self, block):
        block.seek(3000)
        _no_word(block)
        block.seek(12000)

        # a driver in a process of its own passes the repeat on late
        _reported(block, 3000)
        _reported(block, 2800)

        assert _seeks(block) == [3000, 12000, 12000]

    def test_one_made_after_the_last_landed_is_taken_at_its_word(self, block):
        block.seek(3000)
        _reported(block, 2800)
        block.seek(12000)
        _reported(block, 11000)

        assert _seeks(block) == [3000, 12000]

    def test_one_seen_arriving_is_not_made_again(self, block):
        block.seek(3000)
        _no_word(block)
        block.seek(12000)
        _reported(block, 12400)

        assert _seeks(block) == [3000, 12000]

    def test_it_is_made_again_only_so_often(self, block):
        block.seek(3000)

        # nowhere this seek could have taken it
        for _ in range(SEEK_RETRIES + 2):
            _reported(block, 12000)

        assert _seeks(block) == [3000] * (SEEK_RETRIES + 1)

    def test_one_into_the_end_is_not_made_again(self, block):
        block.seek(3000)
        _no_word(block)
        block.seek(LENGTH - 1000)
        _reported(block, 2800)

        assert _seeks(block) == [3000, LENGTH - 1000]

    def test_one_on_a_file_is_not_made_again(self, block):
        block.stream.is_adaptive = False

        block.seek(3000)
        _no_word(block)
        block.seek(12000)
        _reported(block, 2800)

        assert _seeks(block) == [3000, 12000]


class TestHeldBack:
    def test_one_made_while_the_last_is_landing_waits(self, block):
        block.seek(3000)
        block.seek(12000)

        assert _seeks(block) == [3000]
        assert block.is_seek_on_its_way

    def test_its_time_is_where_it_goes(self, block):
        block.seek(3000)
        block.seek(12000)

        # for the bar, and for the others following this one
        assert block.time == 12000
        assert block.arriving_time == 12000

    def test_the_newest_takes_the_place_of_one_waiting(self, block):
        block.seek(3000)
        block.seek(12000)
        block.seek(9000)
        _reported(block, 3100)

        assert _seeks(block) == [3000, 9000]

    def test_it_goes_once_the_last_says_where_it_is(self, block):
        block.seek(3000)
        block.seek(12000)
        # a stream landing short has made it all the same
        _reported(block, 2800)

        assert _seeks(block) == [3000, 12000]

    def test_the_last_said_back_as_it_is_made_is_no_word(self, block):
        block.seek(3000)
        block.seek(12000)
        _reported(block, 3000)

        assert _seeks(block) == [3000]

    def test_it_goes_after_a_while_with_no_word(self, block):
        block.seek(3000)
        block.seek(12000)
        _no_word(block)

        assert _seeks(block) == [3000, 12000]

    def test_a_while_is_shorter_paused(self, block, mocker):
        start = mocker.spy(block._seek_hold_timer, "start")

        block.seek(3000)
        block._seek_hold_timer.stop()
        block.video_params.playback_state = VideoInitialState.PLAYING
        block.seek(5000)

        assert [call.args[0] for call in start.call_args_list] == [
            SEEK_HOLD_PAUSED_MS,
            SEEK_HOLD_MAX_MS,
        ]

    def test_a_frame_step_does_not_wait(self, block):
        block.seek(3000)
        block.next_frame()

        assert len(_seeks(block)) == 2

    def test_the_players_own_does_not_wait(self, block):
        block.seek(3000)
        block.seek(12000)
        block.seek(5000, is_viewers=False)
        _reported(block, 5100)

        assert _seeks(block) == [3000, 5000]

    def test_one_waiting_goes_with_the_player(self, block):
        block.seek(3000)
        block.seek(12000)
        block._destroy_video_driver()

        assert block._held_seek is None
        assert not block._seek_hold_timer.isActive()

    def test_the_time_stays_where_it_goes_while_it_waits(self, block):
        block.seek(3000)
        block.seek(12000)
        # the one before still on its way
        _reported(block, 1000)

        assert block.time == 12000

    def test_a_loop_going_round_does_not_wait(self, block):
        block.loop.set_start_time(1000)
        block.seek(3000)
        block._seek_loop_start()

        assert _seeks(block) == [3000, 1000]

    def test_where_it_was_said_again_is_no_word(self, block):
        block.stream.is_adaptive = False
        _reported(block, 10000)

        block.seek(8000)
        block.seek(7500)
        # still where it was, played on a little
        _reported(block, 10250)

        assert _seeks(block) == [8000]

    def test_where_it_was_short_of_one_on_a_stream_is_no_word(self, block):
        _reported(block, 2000)

        block.seek(12000)
        block.seek(15000)
        _reported(block, 2300)

        assert _seeks(block) == [12000]

    def test_one_waiting_keeps_to_the_loop_as_it_is_when_it_goes(self, block):
        block.seek(3000)
        block.seek(12000)
        block.loop.set_end_time(8000)
        _no_word(block)

        assert _seeks(block) == [3000, 0]

    def test_not_on_a_player_keeping_only_the_newest(self, block, mocker):
        mocker.patch.object(block.video_driver, "makes_every_seek", return_value=False)

        block.seek(3000)
        block.seek(12000)

        assert _seeks(block) == [3000, 12000]
