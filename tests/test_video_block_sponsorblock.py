"""SponsorBlock's segments in a playing video: what is marked and what skipped.

A real block, on a stand-in frame that reports only the times a test tells it
to, as a YouTube video would once SponsorBlock has been asked about it.
"""

import dataclasses
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.seek_mark import SeekMarkKind
from gridplayer.models.sponsor_segment import SponsorSegment
from gridplayer.models.stream import Streams
from gridplayer.models.video import Video
from gridplayer.params.static import (
    SponsorBlockMode,
    VideoEndAction,
    VideoInitialState,
)
from gridplayer.settings import Settings
from gridplayer.utils import sponsorblock
from gridplayer.utils.sponsorblock import SKIP_JOIN_MS, SKIP_MIN_MS
from gridplayer.utils.url_resolve.static import ResolvedVideo
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy

# ten minutes, about what a YouTube video with a sponsor read runs to
LENGTH = 600000

VIDEO_ID = "dQw4w9WgXcQ"

SPONSOR = SponsorSegment(60000, 90000, "sponsor")


class _Frame(VideoFrameDummy):
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
    settings.set("sponsorblock/enabled", True)

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
def make_block(tmp_path, mocker):
    made = []

    def _make(end_action=VideoEndAction.STOP):
        # held on to: a parent collected out from under it takes the block
        parent = QWidget()

        video_file = tmp_path / "movie.mp4"
        video_file.touch()

        block = VideoBlock(video_driver=_Frame, context=_context(), parent=parent)

        block.set_video(
            Video(
                uri=video_file,
                playback_state=VideoInitialState.PLAYING,
                end_action=end_action,
            )
        )

        assert block.is_video_initialized

        # the time goes where a test says and nowhere else
        block.video_driver._fake_player_timer.stop()

        block.set_time = mocker.spy(block.video_driver, "set_time")

        block.notices = []
        block.info_change.connect(block.notices.append)

        block.marks = ()
        block.seek_marks_change.connect(lambda marks: setattr(block, "marks", marks))

        made.append((block, parent))

        return block

    yield _make

    for block, _parent in made:
        block.cleanup()
        block.url_resolver.cleanup()


@pytest.fixture
def block(make_block):
    return make_block()


def _found(block, *segments, site_length_ms=LENGTH):
    """SponsorBlock answering for the video the block is playing."""

    block._youtube_id = VIDEO_ID
    block._site_length_ms = site_length_ms

    block._sponsor_segments_fetched(VIDEO_ID, segments)


def _reported(block, time_ms):
    """VLC reporting the time, well after any seek has settled."""

    block._seek_settle_timer.stop()
    block.video_driver.time_changed.emit(time_ms)

    QApplication.processEvents()


def _seeks(block):
    return [call.args[0] for call in block.set_time.call_args_list]


def _segment_marks(block):
    return [
        mark
        for mark in block.marks
        if mark.kind in {SeekMarkKind.SEGMENT, SeekMarkKind.HIGHLIGHT}
    ]


class TestPlayingIntoOne:
    def test_it_is_skipped_to_its_end(self, block):
        _found(block, SPONSOR)

        _reported(block, 59800)
        _reported(block, 60100)

        assert _seeks(block) == [SPONSOR.end_ms]

    def test_it_says_what_it_skipped(self, block):
        _found(block, SPONSOR)

        _reported(block, 60100)

        assert block.notices == ["Skipped: Sponsor"]

    def test_landing_a_hair_short_of_the_end_is_not_skipped_again(self, block):
        _found(block, SPONSOR)

        _reported(block, 60100)
        _reported(block, SPONSOR.end_ms - 10)
        _reported(block, SPONSOR.end_ms + 300)

        assert _seeks(block) == [SPONSOR.end_ms]

    def test_landing_seconds_short_on_a_stream_is_not_skipped_again(self, block):
        block._is_adaptive = True
        _found(block, SPONSOR)

        _reported(block, 60100)
        # the segment before the aim, inside the sponsor still
        _reported(block, SPONSOR.end_ms - 6000)
        _reported(block, SPONSOR.end_ms + 400)

        assert _seeks(block) == [SPONSOR.end_ms]

    def test_landing_short_for_good_is_not_skipped_again(self, block):
        """Where a stream plays on from short of the end, rather than get there.

        Skipped again, it would land in the same place, over and over.
        """

        block._is_adaptive = True
        _found(block, SPONSOR)

        _reported(block, 60100)
        _reported(block, SPONSOR.end_ms - 6000)
        _reported(block, SPONSOR.end_ms - 4800)

        assert _seeks(block) == [SPONSOR.end_ms]

    def test_ones_that_run_into_each_other_are_one_seek(self, block):
        Settings().set("sponsorblock/selfpromo", SponsorBlockMode.SKIP)
        plug = SponsorSegment(SPONSOR.end_ms + SKIP_JOIN_MS // 2, 100000, "selfpromo")
        _found(block, SPONSOR, plug)

        _reported(block, 60100)

        assert _seeks(block) == [plug.end_ms]

    def test_one_with_hardly_any_of_it_left_is_let_play(self, block):
        _found(block, SPONSOR)

        _reported(block, SPONSOR.end_ms - SKIP_MIN_MS + 100)

        assert _seeks(block) == []

    def test_nothing_is_skipped_while_paused(self, block):
        _found(block, SPONSOR)

        block.set_pause(True)
        _reported(block, 60100)

        assert _seeks(block) == []

    def test_it_is_skipped_again_on_the_next_pass(self, block):
        _found(block, SPONSOR)

        _reported(block, 60100)
        _reported(block, SPONSOR.end_ms + 300)

        block.seek(50000)
        _reported(block, 50000)
        _reported(block, 50300)
        _reported(block, 60200)

        assert _seeks(block) == [SPONSOR.end_ms, 50000, SPONSOR.end_ms]


class TestSeekingIntoOne:
    def test_a_seek_of_the_viewers_into_one_plays_it(self, block):
        _found(block, SPONSOR)

        block.seek(70000)
        _reported(block, 70000)
        _reported(block, 70400)
        _reported(block, 75000)

        assert _seeks(block) == [70000]

    def test_played_into_again_after_leaving_it_is_skipped(self, block):
        _found(block, SPONSOR)

        block.seek(70000)
        _reported(block, 70400)
        _reported(block, SPONSOR.end_ms + 300)

        block.seek(50000)
        _reported(block, 50300)
        _reported(block, 60200)

        assert _seeks(block) == [70000, 50000, SPONSOR.end_ms]

    def test_a_seek_past_one_landing_inside_it_on_a_stream_is_let_land(self, block):
        """The stream says where the keyframe before the aim is, first."""

        block._is_adaptive = True
        _found(block, SPONSOR)

        block.seek(95000)
        _reported(block, 88000)
        _reported(block, 95400)

        assert _seeks(block) == [95000]


class TestAtTheEnd:
    def test_one_that_runs_to_the_end_ends_the_video(self, block):
        Settings().set("sponsorblock/outro", SponsorBlockMode.SKIP)
        _found(block, SponsorSegment(LENGTH - 20000, LENGTH, "outro"))

        _reported(block, LENGTH - 19800)

        assert block.is_stopped

    def test_a_looping_video_skips_its_intro_coming_round(self, make_block):
        block = make_block(end_action=VideoEndAction.LOOP_FILE)
        Settings().set("sponsorblock/intro", SponsorBlockMode.SKIP)
        Settings().set("sponsorblock/outro", SponsorBlockMode.SKIP)
        _found(
            block,
            SponsorSegment(0, 15000, "intro"),
            SponsorSegment(LENGTH - 20000, LENGTH, "outro"),
        )

        _reported(block, LENGTH - 19800)
        _reported(block, 0)
        _reported(block, 300)

        assert _seeks(block) == [0, 15000]

    def test_one_that_is_all_there_is_is_let_play(self, make_block):
        """Skipping it would go round into it again, over and over."""

        block = make_block(end_action=VideoEndAction.LOOP_FILE)
        Settings().set("sponsorblock/selfpromo", SponsorBlockMode.SKIP)
        _found(block, SponsorSegment(0, LENGTH, "selfpromo"))

        _reported(block, 5000)

        assert _seeks(block) == []
        assert not block.is_stopped


class TestInALoop:
    def test_a_loop_inside_one_plays_it(self, block):
        _found(block, SPONSOR)
        block.set_loop_start_time(65000)
        block.set_loop_end_time(80000)

        _reported(block, 70000)

        assert _seeks(block) == []

    def test_a_loop_starting_inside_one_plays_it_every_pass(self, block):
        _found(block, SPONSOR)
        block.set_loop_start_time(70000)
        block.set_loop_end_time(120000)

        _reported(block, 119900)
        _reported(block, 120100)
        _reported(block, 70000)
        _reported(block, 70400)

        assert _seeks(block) == [70000]

    def test_one_that_runs_past_the_loop_end_ends_the_pass(self, block):
        _found(block, SPONSOR)
        block.set_loop_start_time(40000)
        block.set_loop_end_time(80000)

        _reported(block, 60100)

        assert _seeks(block) == [40000]


class TestWhatIsMarked:
    def test_a_skipped_one_is_marked_in_its_colour(self, block):
        _found(block, SPONSOR)

        (mark,) = _segment_marks(block)

        assert mark.kind is SeekMarkKind.SEGMENT
        assert (mark.time_ms, mark.end_ms) == (SPONSOR.start_ms, SPONSOR.end_ms)
        assert mark.label == "Sponsor"
        assert mark.color == "#00d400"

    def test_one_only_shown_is_marked_and_played(self, block):
        plug = SponsorSegment(60000, 90000, "selfpromo")
        _found(block, plug)

        _reported(block, 60100)

        assert [mark.label for mark in _segment_marks(block)] == [
            "Unpaid/Self Promotion"
        ]
        assert _seeks(block) == []

    def test_one_switched_off_is_neither(self, block):
        _found(block, SponsorSegment(60000, 90000, "filler"))

        _reported(block, 60100)

        assert _segment_marks(block) == []
        assert _seeks(block) == []

    def test_a_highlight_is_a_place(self, block):
        _found(block, SponsorSegment(120000, 120000, "poi_highlight"))

        (mark,) = _segment_marks(block)

        assert mark.kind is SeekMarkKind.HIGHLIGHT
        assert mark.time_ms == 120000

    def test_they_go_along_with_the_chapters(self, block):
        block._set_chapters(())
        _found(block, SPONSOR)

        assert block.marks == tuple(_segment_marks(block))

    def test_none_where_the_site_is_out_about_the_length(self, block):
        """SponsorBlock's times are for the video the site has."""

        _found(block, SPONSOR, site_length_ms=LENGTH + 60000)

        _reported(block, 60100)

        assert _segment_marks(block) == []
        assert _seeks(block) == []

    def test_a_stopped_video_marks_nothing(self, block):
        _found(block, SPONSOR)

        block.stop_playback()

        assert _segment_marks(block) == []

    def test_an_answer_about_another_video_is_not_this_ones(self, block):
        block._youtube_id = VIDEO_ID
        block._site_length_ms = LENGTH

        block._sponsor_segments_fetched("another", (SPONSOR,))

        assert _segment_marks(block) == []


class TestTheSettings:
    def test_switched_off_nothing_is_marked_or_skipped(self, block):
        _found(block, SPONSOR)

        Settings().set("sponsorblock/enabled", False)
        block.apply_sponsorblock_settings()
        _reported(block, 60100)

        assert _segment_marks(block) == []
        assert _seeks(block) == []

    def test_a_category_changed_is_taken_up_at_once(self, block):
        _found(block, SPONSOR)

        Settings().set("sponsorblock/sponsor", SponsorBlockMode.SHOW)
        block.apply_sponsorblock_settings()
        _reported(block, 60100)

        assert _seeks(block) == []
        assert len(_segment_marks(block)) == 1

    def test_switched_on_a_video_already_playing_is_looked_up(self, block, mocker):
        Settings().set("sponsorblock/enabled", False)
        block._youtube_id = VIDEO_ID
        block._site_length_ms = LENGTH

        fetch = mocker.patch.object(
            sponsorblock.sponsorblock_fetcher(), "fetch", return_value=(SPONSOR,)
        )

        block.apply_sponsorblock_settings()
        fetch.assert_not_called()

        Settings().set("sponsorblock/enabled", True)
        block.apply_sponsorblock_settings()

        fetch.assert_called_once_with(VIDEO_ID, LENGTH)
        assert len(_segment_marks(block)) == 1


class TestLookingItUp:
    def _resolved(self, youtube_id=VIDEO_ID):
        return ResolvedVideo(
            title="video",
            is_live=False,
            streams=Streams(),
            duration_ms=LENGTH,
            youtube_id=youtube_id,
        )

    def test_a_youtube_video_is_looked_up_as_it_resolves(self, block, mocker):
        mocker.patch.object(block, "load_stream_quality")
        fetch = mocker.patch.object(
            sponsorblock.sponsorblock_fetcher(), "fetch", return_value=None
        )

        block.set_video_url(self._resolved())

        fetch.assert_called_once_with(VIDEO_ID, LENGTH)

    def test_anything_else_is_not(self, block, mocker):
        mocker.patch.object(block, "load_stream_quality")
        fetch = mocker.patch.object(sponsorblock.sponsorblock_fetcher(), "fetch")

        block.set_video_url(self._resolved(youtube_id=None))

        fetch.assert_not_called()

    def test_nor_anything_with_it_switched_off(self, block, mocker):
        Settings().set("sponsorblock/enabled", False)
        mocker.patch.object(block, "load_stream_quality")
        fetch = mocker.patch.object(sponsorblock.sponsorblock_fetcher(), "fetch")

        block.set_video_url(self._resolved())

        fetch.assert_not_called()

    def test_the_answer_arriving_later_is_taken_up(self, block, mocker):
        mocker.patch.object(block, "load_stream_quality")
        mocker.patch.object(
            sponsorblock.sponsorblock_fetcher(), "fetch", return_value=None
        )

        block.set_video_url(self._resolved())
        sponsorblock.sponsorblock_fetcher().fetched.emit(VIDEO_ID, (SPONSOR,))

        assert len(_segment_marks(block)) == 1
