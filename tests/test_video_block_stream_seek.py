"""Seeking a stream, the way VLC's adaptive demuxer reports it back.

A seek there lands on the segment before its aim and says so first -- seconds
short, up to 10.5s measured on YouTube -- and a seek made while the one before
it is still restarting the stream is turned down, the video playing on from
where that one took it. A real block, on a stand-in frame that reports only
what a test tells it to.
"""

import dataclasses
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import SEEK_RETRIES, VideoBlock
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

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _context():
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1

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
    block._is_adaptive = True

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


class TestLanding:
    def test_landing_short_is_no_pass_coming_round(self, block):
        block.seek(15000)
        _reported(block, 8847)

        assert not block.is_stopped
        assert _seeks(block) == [15000]

    def test_landing_short_of_a_loop_is_not_sent_back(self, block):
        block.set_loop_start_time(12000)
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
        block.seek(12000)

        # the first one landing: the second never happened
        _reported(block, 2800)

        assert _seeks(block) == [3000, 12000, 12000]

    def test_where_it_was_turned_down_is_left_alone(self, block):
        block.seek(3000)
        block.seek(12000)

        # as far back as a pass coming round
        _reported(block, 2800)

        assert not block.is_stopped

    def test_the_one_before_repeated_back_says_nothing_yet(self, block):
        block.seek(3000)
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
        block.seek(LENGTH - 1000)
        _reported(block, 2800)

        assert _seeks(block) == [3000, LENGTH - 1000]

    def test_one_on_a_file_is_not_made_again(self, block):
        block._is_adaptive = False

        block.seek(3000)
        block.seek(12000)
        _reported(block, 2800)

        assert _seeks(block) == [3000, 12000]
