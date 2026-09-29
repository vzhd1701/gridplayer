"""Chapters on a video block: jumping between them, looping one, and the bar.

A real block, on a stand-in frame that loads at once with the chapters it
was given.
"""

import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QObject, QSettings, pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.models.chapter import Chapter
from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.models.stream import Stream, Streams
from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.settings import Settings
from gridplayer.utils.url_resolve.static import ResolvedVideo
from gridplayer.widgets import video_block as video_block_module
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy

LENGTH = 60000

CHAPTERS = (
    Chapter(0, "Opening"),
    Chapter(10000, None),
    Chapter(25000, "Tom & Jerry"),
    Chapter(40000, "Credits"),
)

# where VLC reports the time after a seek to a chapter's start
LANDED_SHORT_MS = 10


class _ChapterFrame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=LENGTH, chapters=CHAPTERS
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
def block(tmp_path):
    # held on to: a parent collected out from under it takes the block
    parent = QWidget()

    video_file = tmp_path / "movie.mkv"
    video_file.touch()

    block = VideoBlock(video_driver=_ChapterFrame, context=_context(), parent=parent)

    block.set_video(
        Video(
            uri=video_file,
            playback_state=VideoInitialState.PAUSED,
            end_action=VideoEndAction.LOOP_FILE,
        )
    )

    assert block.is_video_initialized

    yield block

    block.cleanup()
    block.url_resolver.cleanup()


def _marks(block):
    return block.overlay.progress_bar.marks


class TestTheBar:
    def test_every_chapter_is_marked_with_its_name(self, block):
        assert _marks(block) == (
            SeekMark(0, "Opening", SeekMarkKind.CHAPTER),
            SeekMark(10000, "Chapter 2", SeekMarkKind.CHAPTER),
            SeekMark(25000, "Tom & Jerry", SeekMarkKind.CHAPTER),
            SeekMark(40000, "Credits", SeekMarkKind.CHAPTER),
        )

    def test_the_hover_label_names_them_too(self, block):
        assert block.overlay.floating_progress.marks == _marks(block)

    def test_chapters_the_file_lists_late_are_marked_when_they_come(self, block):
        late = (Chapter(0, "A"), Chapter(30000, "B"))

        block.video_driver._on_chapters_changed(late)

        assert block.chapters == late
        assert [mark.label for mark in _marks(block)] == ["A", "B"]

    def test_stopping_takes_the_marks_away(self, block):
        block.stop_playback()

        assert block.chapters == ()
        assert _marks(block) == ()


class TestJumping:
    def test_next_goes_from_chapter_to_chapter(self, block):
        block.next_chapter()
        assert block.time == 10000

        block.next_chapter()
        assert block.time == 25000

    def test_next_from_a_seek_that_landed_short_moves_on(self, block):
        block.seek(25000 - LANDED_SHORT_MS)

        block.next_chapter()

        assert block.time == 40000

    def test_past_the_last_chapter_is_the_end_arriving(self, block):
        block.seek(45000)
        block.loop_end_action = MagicMock()

        block.next_chapter()

        block.loop_end_action.assert_called_once_with()

    def test_the_end_of_a_looping_file_starts_it_over(self, block):
        block.seek(45000)

        block.next_chapter()

        assert block.time == 0

    def test_previous_near_a_chapter_start_goes_to_the_one_before(self, block):
        block.seek(26000)

        block.previous_chapter()

        assert block.time == 10000

    def test_previous_well_into_a_chapter_starts_it_over(self, block):
        block.seek(30000)

        block.previous_chapter()

        assert block.time == 25000

    def test_a_jump_names_the_chapter_it_lands_in(self, block):
        shown = []
        block.info_change.connect(shown.append)

        block.seek(12000)
        block.next_chapter()

        assert shown == ["Tom & Jerry"]

    def test_a_jump_from_the_menu_is_a_seek_the_others_can_follow(self, block):
        synced = []
        block.sync_time.connect(synced.append)

        block.manual_seek("seek_chapter", 3)

        assert block.time == 40000
        assert synced == [40000]

    def test_a_video_without_chapters_goes_nowhere(self, block):
        block.video_driver._on_chapters_changed(())
        block.loop_end_action = MagicMock()

        block.next_chapter()
        block.previous_chapter()

        assert block.time == 0
        block.loop_end_action.assert_not_called()


class TestLooping:
    def test_loop_chapter_loops_the_one_the_video_is_in(self, block):
        block.seek(12000)

        block.loop_chapter()

        assert block.video_params.loop_start == 10000
        assert block.video_params.loop_end == 25000
        assert block.overlay.progress_bar.loop_start == 10000 / LENGTH
        assert block.overlay.progress_bar.loop_end == 25000 / LENGTH

    def test_the_last_chapter_loops_to_the_end_of_the_file(self, block):
        block.seek(45000)

        block.loop_chapter()

        assert block.video_params.loop_start == 40000
        assert block.video_params.loop_end is None

    def test_a_loop_further_on_replaces_the_one_before(self, block):
        """Its start lies past the old end, which the loop setters refuse."""

        block.seek(12000)
        block.loop_chapter()

        # a seek would be held inside the loop, so the video is simply put
        # where a loop left some other way would leave it
        block.video_params.current_position = 30000

        block.loop_chapter()

        assert block.video_params.loop_start == 25000
        assert block.video_params.loop_end == 40000

    def test_chapters_outside_the_loop_are_out_of_reach(self, block):
        block.seek(12000)
        block.loop_chapter()

        reachable = [block.is_chapter_reachable(i) for i in range(len(CHAPTERS))]

        assert reachable == [False, True, False, False]

    def test_a_jump_to_one_out_of_reach_goes_nowhere(self, block):
        block.seek(12000)
        block.loop_chapter()

        block.seek_chapter(2)

        assert block.time == 12000

    def test_next_inside_a_loop_comes_back_round_to_its_start(self, block):
        block.seek(12000)
        block.loop_chapter()

        block.next_chapter()

        assert block.time == 10000


# where VLC reports a stream to be while a seek to 25000 lands: the start of
# the segment before it, the way a YouTube stream reported it
LANDING_ON_A_STREAM_MS = 25000 - 2300


def _reported(block, time_ms):
    block.video_driver.time_changed.emit(time_ms)


class TestJumpingOnAStream:
    def test_next_while_a_jump_is_still_landing_moves_on(self, block):
        block.seek_chapter(2)
        _reported(block, LANDING_ON_A_STREAM_MS)

        block.next_chapter()

        assert block.time == 40000

    def test_a_jump_still_landing_is_in_the_chapter_it_was_aimed_at(self, block):
        block.seek_chapter(2)
        _reported(block, LANDING_ON_A_STREAM_MS)

        assert block.chapter_playing == 2

    def test_a_seek_from_the_bar_counts_the_same(self, block):
        block.seek(25000)
        _reported(block, LANDING_ON_A_STREAM_MS)

        assert block.chapter_playing == 2

    def test_loop_chapter_while_a_jump_is_landing_loops_that_one(self, block):
        block.seek_chapter(2)
        _reported(block, LANDING_ON_A_STREAM_MS)

        block.loop_chapter()

        assert (block.loop_start, block.loop_end) == (25000, 40000)

    def test_once_seen_past_its_aim_the_time_is_taken_as_it_comes(self, block):
        block.seek_chapter(2)
        _reported(block, 25000)
        _reported(block, 25400)
        _reported(block, LANDING_ON_A_STREAM_MS)

        assert block.chapter_playing == 1

    def test_far_short_of_its_aim_the_video_is_somewhere_else(self, block):
        # a seek that never happened, while the video played on elsewhere
        block.seek_chapter(3)
        _reported(block, 12000)

        assert block.chapter_playing == 1

    def test_a_looped_chapter_coming_round_is_sent_back_once(self, block, mocker):
        block.seek_chapter(2)
        _reported(block, 25400)
        block.loop_chapter()

        set_time = mocker.spy(block.video_driver, "set_time")

        # past its end, back to its start, where the stream lands short
        _reported(block, 40100)
        _reported(block, LANDING_ON_A_STREAM_MS)
        _reported(block, LANDING_ON_A_STREAM_MS + 5)
        _reported(block, 25400)

        assert [call.args for call in set_time.call_args_list] == [(25000,)]
        assert block.time == 25400


class _Manager(ActiveBlockManager):
    """The manager's menu methods, without the rest of the player behind them."""

    def __init__(self, block):
        self._ctx = SimpleNamespace(active_block=block)


class TestTheMenu:
    def test_every_chapter_is_listed_with_where_it_starts(self, block):
        titles = [row["title"] for row in _Manager(block).menu_generator_chapters()]

        assert titles == [
            "Opening\t00:00",
            "Chapter 2\t00:10",
            "Tom && Jerry\t00:25",
            "Credits\t00:40",
        ]

    def test_a_row_jumps_as_a_seek_the_others_can_follow(self, block):
        rows = _Manager(block).menu_generator_chapters()

        assert rows[2]["func"] == ("active", "manual_seek", "seek_chapter", 2)
        assert hasattr(VideoBlock, rows[2]["func"][2])

    def test_the_chapter_playing_is_ticked(self, block):
        manager = _Manager(block)

        block.seek(25000 - LANDED_SHORT_MS)

        ticked = [manager.is_active_chapter_playing(i) for i in range(len(CHAPTERS))]

        assert ticked == [False, False, True, False]

    def test_rows_outside_the_loop_are_grayed_out(self, block):
        manager = _Manager(block)

        block.seek(12000)
        block.loop_chapter()

        enabled = [manager.is_active_chapter_reachable(i) for i in range(len(CHAPTERS))]

        assert enabled == [False, True, False, False]

    def test_no_chapters_no_menu(self, block):
        block.video_driver._on_chapters_changed(())

        manager = _Manager(block)

        assert not manager.is_active_has_chapters()
        assert manager.menu_generator_chapters() == []


SITE_CHAPTERS = (Chapter(0, "Intro"), Chapter(20000, "Build"), Chapter(45000, "Outro"))


class _BareFrame(VideoFrameDummy):
    """A file that lists no chapters of its own, as a site's stream never does."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=LENGTH
        )


class _LiveFrame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(self._fake_media_track, length=-1)


def _resolved(**kwargs):
    return ResolvedVideo(
        **{
            "title": "Site video",
            "is_live": False,
            "streams": Streams(
                {
                    "720p": Stream(url="https://cdn/720.mp4", protocol="direct"),
                    "360p": Stream(url="https://cdn/360.mp4", protocol="direct"),
                }
            ),
            "chapters": SITE_CHAPTERS,
            "duration_ms": LENGTH,
            **kwargs,
        }
    )


@pytest.fixture
def url_block(monkeypatch):
    """A block playing a URL, which the site resolves at once to what it's told."""

    blocks = []

    def make(resolved, frame=_BareFrame):
        class _SiteResolver(QObject):
            url_resolved = pyqtSignal(ResolvedVideo)
            error = pyqtSignal()
            update_status = pyqtSignal(str)

            def resolve(self, url):
                self.url_resolved.emit(resolved)

            def cleanup(self): ...

        monkeypatch.setattr(video_block_module, "VideoURLResolver", _SiteResolver)

        parent = QWidget()
        block = VideoBlock(video_driver=frame, context=_context(), parent=parent)
        blocks.append((parent, block))

        block.set_video(
            Video(
                uri="https://site/watch?v=1",
                stream_quality="720p",
                playback_state=VideoInitialState.PAUSED,
            )
        )

        assert block.is_video_initialized

        return block

    yield make

    for _, block in blocks:
        block.cleanup()
        block.url_resolver.cleanup()


class TestSiteChapters:
    def test_a_url_whose_file_lists_none_gets_the_sites(self, url_block):
        block = url_block(_resolved())

        assert block.chapters == SITE_CHAPTERS
        assert [mark.label for mark in _marks(block)] == ["Intro", "Build", "Outro"]

    def test_the_files_own_come_first(self, url_block):
        block = url_block(_resolved(), frame=_ChapterFrame)

        assert block.chapters == CHAPTERS

    def test_a_site_out_on_the_length_is_left_out(self, url_block):
        block = url_block(_resolved(duration_ms=LENGTH + 30000))

        assert block.chapters == ()

    def test_a_site_that_gives_no_length_is_taken_at_its_word(self, url_block):
        block = url_block(_resolved(duration_ms=0))

        assert block.chapters == SITE_CHAPTERS

    def test_a_live_stream_has_none(self, url_block):
        block = url_block(_resolved(), frame=_LiveFrame)

        assert block.chapters == ()

    def test_they_last_through_a_switch_of_quality(self, url_block):
        block = url_block(_resolved())

        block.switch_stream_quality("360p")

        assert block.is_video_initialized
        assert block.stream_quality_playing == "360p"
        assert block.chapters == SITE_CHAPTERS

    def test_a_file_put_in_the_urls_place_brings_none_of_them(
        self, url_block, tmp_path
    ):
        block = url_block(_resolved())

        video_file = tmp_path / "movie.mkv"
        video_file.touch()

        block.set_video(Video(uri=video_file, playback_state=VideoInitialState.PAUSED))

        assert block.is_video_initialized
        assert block.chapters == ()
