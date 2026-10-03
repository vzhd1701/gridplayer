"""Bookmarks on a video block: adding them, jumping to them, and the bar.

A real block, on a stand-in frame that reports only the times a test tells
it to.
"""

import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QPoint, QSettings
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.bookmark import Bookmark
from gridplayer.models.chapter import Chapter
from gridplayer.models.file_bookmarks import FileBookmarks
from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Snapshot
from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.player.managers.actions import QDynamicAction
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.settings import Settings
from gridplayer.utils.bookmarks import default_bookmark_name
from gridplayer.utils.sponsorblock import SkipSpan
from gridplayer.widgets import video_block as video_block_module
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy

LENGTH = 60000

BOOKMARKS = (Bookmark(time_ms=10000), Bookmark(time_ms=30000, name="Goal & Run"))

# where VLC reports the time after a seek to a bookmark
LANDED_SHORT_MS = 10

# where VLC reports a stream to be while a seek to 25000 lands
LANDING_ON_A_STREAM_MS = 25000 - 2300

BLUE = "#3d8bff"


def _icon_color(icon, size=24):
    """The colour at the middle of an icon's marker, a little above its
    point."""

    image = icon.pixmap(size, size).toImage()

    return image.pixelColor(image.width() // 2, image.height() // 2 - 1).name()


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

    yield

    settings.settings = real_settings


def _context():
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1
    context.bookmarks = BookmarksRegistry()

    return context


@pytest.fixture
def make_block(tmp_path, mocker):
    made = []

    def _make(bookmarks=BOOKMARKS, context=None):
        # held on to: a parent collected out from under it takes the block
        parent = QWidget()

        video_file = tmp_path / "movie.mkv"
        video_file.touch()

        block = VideoBlock(
            video_driver=_Frame, context=context or _context(), parent=parent
        )

        block.set_video(
            Video(
                uri=video_file,
                playback_state=VideoInitialState.PAUSED,
                end_action=VideoEndAction.LOOP_FILE,
            )
        )

        # None leaves those the file has: another cell's, shared
        if bookmarks is not None:
            block.set_bookmarks(bookmarks)

        assert block.is_video_initialized

        # the time goes where a test says and nowhere else
        block.video_driver._fake_player_timer.stop()

        block.set_time = mocker.spy(block.video_driver, "set_time")

        block.notices = []
        block.info_change.connect(block.notices.append)

        made.append((block, parent))

        return block

    yield _make

    for block, _parent in made:
        block.cleanup()
        block.url_resolver.cleanup()


@pytest.fixture
def block(make_block):
    return make_block()


def _marks(block):
    return block.overlay.progress_bar.marks


def _bookmark_marks(block):
    return [mark for mark in _marks(block) if mark.kind == SeekMarkKind.BOOKMARK]


def _times(block):
    return [bookmark.time_ms for bookmark in block.bookmarks]


def _reported(block, time_ms):
    block.video_driver.time_changed.emit(time_ms)


def _seeks(block):
    return [call.args[0] for call in block.set_time.call_args_list]


class TestAdding:
    def test_one_is_added_where_the_video_is(self, make_block):
        block = make_block(bookmarks=())

        block.seek(12000)
        block.add_bookmark()

        assert block.bookmarks == (Bookmark(time_ms=12000),)
        assert block.notices == ["Bookmark added"]

    def test_it_is_kept_by_the_playlist_with_its_file(self, make_block, tmp_path):
        block = make_block(bookmarks=())

        block.seek(12000)
        block.add_bookmark()

        assert block._ctx.bookmarks.entries() == [
            FileBookmarks(
                uri=tmp_path / "movie.mkv", bookmarks=[Bookmark(time_ms=12000)]
            )
        ]

    def test_it_goes_in_its_place_among_the_rest(self, block):
        block.seek(20000)
        block.add_bookmark()

        assert _times(block) == [10000, 20000, 30000]

    def test_one_where_there_is_one_already_is_not_added(self, block):
        block.seek(30200)
        block.add_bookmark()

        assert _times(block) == [10000, 30000]
        assert block.notices == ["Already bookmarked"]

    def test_while_a_seek_on_a_stream_lands_it_goes_where_it_was_aimed(
        self, make_block
    ):
        block = make_block(bookmarks=())

        block.seek(25000)
        _reported(block, LANDING_ON_A_STREAM_MS)
        block.add_bookmark()

        assert _times(block) == [25000]

    def test_a_live_stream_takes_none(self, make_block):
        block = make_block(bookmarks=())
        block.is_live = True

        block.add_bookmark()

        assert block.bookmarks == ()

    def test_at_the_very_end_it_goes_just_before_it(self, make_block):
        block = make_block(bookmarks=())

        block.seek(LENGTH)
        block.add_bookmark()

        assert _times(block) == [LENGTH - 1]
        assert block.is_bookmark_reachable(0)

    def test_one_added_now_would_go_where_the_video_is(self, block):
        block.seek(25000)
        _reported(block, LANDING_ON_A_STREAM_MS)

        assert block.time_to_bookmark == 25000


class TestSettingThemAll:
    def test_they_are_put_in_order_one_to_a_place(self, block):
        block.set_bookmarks(
            [
                Bookmark(time_ms=50000),
                Bookmark(time_ms=20000, name="First"),
                Bookmark(time_ms=20000, name="Second"),
            ]
        )

        assert block.bookmarks == (
            Bookmark(time_ms=20000, name="First"),
            Bookmark(time_ms=50000),
        )

    def test_the_bar_shows_them_at_once(self, block):
        block.set_bookmarks([Bookmark(time_ms=45000)])

        assert [mark.time_ms for mark in _bookmark_marks(block)] == [45000]

    def test_what_the_bar_marks_can_be_read_back(self, block):
        assert block.seek_marks == _marks(block)


class TestTheBar:
    def test_each_is_marked_by_its_name_or_its_number(self, block):
        assert _bookmark_marks(block) == [
            SeekMark(10000, "Bookmark 1", SeekMarkKind.BOOKMARK),
            SeekMark(30000, "Goal & Run", SeekMarkKind.BOOKMARK),
        ]

    def test_the_hover_label_has_them_too(self, block):
        assert block.overlay.floating_progress.marks == _marks(block)

    def test_one_added_is_marked_at_once(self, block):
        block.seek(45000)
        block.add_bookmark()

        assert [mark.time_ms for mark in _bookmark_marks(block)] == [
            10000,
            30000,
            45000,
        ]

    def test_they_are_marked_along_with_the_chapters(self, block):
        block.video_driver._on_chapters_changed((Chapter(0), Chapter(20000)))

        kinds = [mark.kind for mark in _marks(block)]

        assert kinds.count(SeekMarkKind.CHAPTER) == 2
        assert kinds.count(SeekMarkKind.BOOKMARK) == 2

    def test_one_past_the_end_is_kept_but_not_marked(self, make_block):
        block = make_block(bookmarks=(*BOOKMARKS, Bookmark(time_ms=LENGTH + 5000)))

        assert len(block.bookmarks) == 3
        assert len(_bookmark_marks(block)) == 2

    def test_stopping_takes_them_off_the_bar_and_keeps_them(self, block):
        block.stop_playback()

        assert _bookmark_marks(block) == []
        assert block.bookmarks == BOOKMARKS

    def test_a_live_stream_marks_none(self, block):
        block.is_live = True
        block.video_driver._on_chapters_changed(())

        assert _bookmark_marks(block) == []


class TestJumping:
    def test_next_goes_from_one_to_the_next(self, block):
        block.next_bookmark()
        assert block.time == 10000

        block.next_bookmark()
        assert block.time == 30000

    def test_a_jump_names_the_bookmark_it_lands_on(self, block):
        block.next_bookmark()
        block.next_bookmark()

        assert block.notices == ["Bookmark 1", "Goal & Run"]

    def test_next_from_a_jump_that_landed_short_moves_on(self, block):
        block.seek(10000 - LANDED_SHORT_MS)

        block.next_bookmark()

        assert block.time == 30000

    def test_next_while_a_jump_on_a_stream_lands_moves_on(self, make_block):
        block = make_block(bookmarks=(Bookmark(time_ms=25000), Bookmark(time_ms=40000)))

        block.seek_bookmark(0)
        _reported(block, LANDING_ON_A_STREAM_MS)
        block.next_bookmark()

        assert block.time == 40000

    def test_next_at_the_last_goes_nowhere_and_says_so(self, block):
        block.seek(35000)
        block.loop_end_action = MagicMock()

        block.next_bookmark()

        assert block.time == 35000
        assert _seeks(block) == [35000]
        assert block.notices == ["No next bookmark"]
        block.loop_end_action.assert_not_called()

    def test_previous_well_past_one_goes_back_to_it(self, block):
        block.seek(35000)

        block.previous_bookmark()

        assert block.time == 30000

    def test_previous_just_past_one_goes_to_the_one_before(self, block):
        block.seek(30500)

        block.previous_bookmark()

        assert block.time == 10000

    def test_previous_at_the_first_goes_nowhere_and_says_so(self, block):
        block.seek(10000)

        block.previous_bookmark()

        assert block.time == 10000
        assert block.notices == ["No previous bookmark"]

    def test_ones_close_together_are_each_gone_to(self, make_block):
        block = make_block(bookmarks=(Bookmark(time_ms=20000), Bookmark(time_ms=20600)))

        block.seek(20600)
        block.previous_bookmark()
        assert block.time == 20000

        block.next_bookmark()
        assert block.time == 20600

        assert block.notices == ["Bookmark 1", "Bookmark 2"]

    def test_a_video_without_any_goes_nowhere_and_says_nothing(self, make_block):
        block = make_block(bookmarks=())

        block.next_bookmark()
        block.previous_bookmark()

        assert block.time == 0
        assert block.notices == []

    def test_a_jump_from_the_menu_is_a_seek_the_others_can_follow(self, block):
        synced = []
        block.sync_time.connect(synced.append)

        block.manual_seek("seek_bookmark", 1)

        assert block.time == 30000
        assert synced == [30000]

    def test_one_that_goes_nowhere_gives_the_others_nothing_to_follow(self, block):
        block.seek(35000)

        synced = []
        block.sync_time.connect(synced.append)
        block.sync_percent.connect(synced.append)

        block.manual_seek("next_bookmark")

        assert synced == []

    def test_one_inside_a_sponsor_is_played_not_skipped(self, block):
        block._skip_spans = (SkipSpan(25000, 40000, "sponsor"),)
        block.set_pause(False)

        block.seek_bookmark(1)
        _reported(block, 30000)
        _reported(block, 30400)
        _reported(block, 31000)

        assert _seeks(block) == [30000]


class TestTheLoop:
    @pytest.fixture
    def looped(self, make_block):
        block = make_block(
            bookmarks=(
                Bookmark(time_ms=10000),
                Bookmark(time_ms=30000),
                Bookmark(time_ms=50000),
            )
        )

        block.seek(25000)
        block.set_loop_start_time(20000)
        block.set_loop_end_time(40000)

        return block

    def test_those_outside_it_are_out_of_reach(self, looped):
        reachable = [looped.is_bookmark_reachable(i) for i in range(3)]

        assert reachable == [False, True, False]

    def test_next_and_previous_pass_them_over(self, looped):
        looped.next_bookmark()
        assert looped.time == 30000

        looped.next_bookmark()
        assert looped.time == 30000
        assert looped.notices[-1] == "No next bookmark"

        looped.previous_bookmark()
        assert looped.notices[-1] == "No previous bookmark"

    def test_a_jump_to_one_out_of_reach_goes_nowhere(self, looped):
        assert looped.seek_bookmark(0) is False
        assert looped.time == 25000


class TestRenaming:
    @pytest.fixture
    def answer(self, mocker):
        return mocker.patch.object(
            video_block_module.QBookmarkRenameDialog, "get_edits"
        )

    def test_one_told_which_is_renamed_wherever_the_video_is(self, block, answer):
        answer.return_value = ("First", None)
        block.seek(20000)

        block.rename_bookmark(0)

        assert block.bookmarks[0] == Bookmark(time_ms=10000, name="First")
        assert _bookmark_marks(block)[0].label == "First"

    def test_the_name_it_has_is_the_one_to_edit(self, block, answer):
        answer.return_value = ("Goal & Run", None)

        block.rename_bookmark(1)

        assert answer.call_args.kwargs["name"] == "Goal & Run"

    def test_a_name_left_empty_goes_back_to_its_number(self, block, answer):
        answer.return_value = ("   ", None)

        block.rename_bookmark(1)

        assert block.bookmarks[1].name is None
        assert block.bookmark_name(1) == "Bookmark 2"
        assert default_bookmark_name(1) == "Bookmark 2"


class TestRemoving:
    def test_one_told_which_is_removed_wherever_the_video_is(self, block):
        block.seek(20000)

        block.remove_bookmark(1)

        assert _times(block) == [10000]
        assert block.notices == ["Bookmark removed"]
        assert [mark.time_ms for mark in _bookmark_marks(block)] == [10000]


class TestManaging:
    @pytest.fixture
    def dialog(self, mocker):
        return mocker.patch.object(video_block_module, "BookmarksDialog")

    def test_the_one_the_video_is_at_is_picked_out(self, block, dialog):
        block.seek(30000 - LANDED_SHORT_MS)

        block.manage_bookmarks()

        assert dialog.call_args.kwargs["selected"] == (1,)
        dialog.return_value.exec_.assert_called_once()

    def test_away_from_any_none_is(self, block, dialog):
        block.seek(20000)

        block.manage_bookmarks()

        assert dialog.call_args.kwargs["selected"] == ()

    def test_those_told_are(self, block, dialog):
        block.manage_bookmarks([0, 1])

        assert dialog.call_args.kwargs["selected"] == [0, 1]

    def test_it_opens_over_the_player(self, block, dialog):
        block.manage_bookmarks()

        assert dialog.call_args.args == (block,)
        assert dialog.call_args.kwargs["parent"] is block.parent()

    def test_a_live_stream_has_none_to_manage(self, block, dialog):
        block.is_live = True

        block.manage_bookmarks()

        dialog.assert_not_called()


class TestKeptWithTheFile:
    def test_the_next_file_in_the_folder_has_its_own(self, block, tmp_path):
        other = tmp_path / "other.mkv"
        other.touch()
        block._ctx.bookmarks.set(other, None, [Bookmark(time_ms=5000)])

        block.next_video()

        assert block.video_params.uri == other
        assert _times(block) == [5000]
        assert [mark.time_ms for mark in _bookmark_marks(block)] == [5000]

    def test_coming_back_to_the_file_brings_them_back(self, block, tmp_path):
        (tmp_path / "other.mkv").touch()

        block.next_video()
        block.previous_video()
        block.video_driver._fake_player_timer.stop()

        assert block.bookmarks == BOOKMARKS
        assert [mark.time_ms for mark in _bookmark_marks(block)] == [10000, 30000]

    def test_two_cells_with_the_file_share_them(self, make_block):
        context = _context()
        first = make_block(context=context)
        second = make_block(bookmarks=None, context=context)

        first.seek(45000)
        first.add_bookmark()

        assert _times(second) == [10000, 30000, 45000]
        assert [mark.time_ms for mark in _bookmark_marks(second)] == [
            10000,
            30000,
            45000,
        ]

    def test_kept_by_cell_each_has_its_own(self, make_block):
        context = _context()
        context.bookmarks.set_shared(False, ())
        first = make_block(context=context)
        second = make_block(bookmarks=None, context=context)

        first.seek(45000)
        first.add_bookmark()

        assert _times(first) == [10000, 30000, 45000]
        assert second.bookmarks == ()

    def test_a_snapshot_leaves_them_as_they_are(self, block):
        snapshot = Snapshot(
            grid_state=GridState(), videos=[block.video_params.model_copy()]
        )

        block.seek(45000)
        block.add_bookmark()

        block.apply_snapshot(snapshot.videos[0])

        assert _times(block) == [10000, 30000, 45000]

    def test_a_snapshot_that_stops_the_video_leaves_them_too(self, block):
        stopped = block.video_params.model_copy(
            update={"playback_state": VideoInitialState.STOPPED}
        )
        snapshot = Snapshot(grid_state=GridState(), videos=[stopped])

        block.apply_snapshot(snapshot.videos[0])

        assert block.bookmarks == BOOKMARKS

    def test_a_video_dragged_to_another_player_takes_them_along(self, block):
        assert block.drag_data.bookmarks == list(BOOKMARKS)

    def test_a_closed_cell_is_remembered_by_its_look(self, block):
        block.title = "Left half"

        block.close()

        assert block._ctx.bookmarks.cell_look(block.video_params.id) == (
            "Left half",
            block.video_params.color.as_hex(),
        )


class _Manager(ActiveBlockManager):
    """The manager's menu methods, without the rest of the player behind them."""

    def __init__(self, block):
        self._ctx = SimpleNamespace(active_block=block)


class TestTheMenu:
    def test_every_bookmark_is_listed_with_where_it_is(self, block):
        titles = [row["title"] for row in _Manager(block).menu_generator_bookmarks()]

        assert titles == ["Bookmark 1\t00:10", "Goal && Run\t00:30"]

    def test_each_has_its_marker_in_its_colour(self, make_block):
        block = make_block(
            bookmarks=(Bookmark(time_ms=10000), Bookmark(time_ms=30000, color=BLUE))
        )

        icons = [row["icon"] for row in _Manager(block).menu_generator_bookmarks()]

        assert [_icon_color(icon) for icon in icons] == ["#ffab00", BLUE]

    def test_and_shows_it_in_the_menu(self, make_block):
        block = make_block(bookmarks=(Bookmark(time_ms=30000, color=BLUE),))
        row = _Manager(block).menu_generator_bookmarks()[0]

        action = QDynamicAction(title=row["title"], icon_id=row["icon"])

        assert _icon_color(action.to_menu_action(None).icon()) == BLUE

    def test_a_row_jumps_as_a_seek_the_others_can_follow(self, block):
        rows = _Manager(block).menu_generator_bookmarks()

        assert rows[1]["func"] == ("active", "manual_seek", "seek_bookmark", 1)
        assert hasattr(VideoBlock, rows[1]["func"][2])

    def test_the_one_the_video_is_at_is_ticked(self, block):
        manager = _Manager(block)

        block.seek(30000 - LANDED_SHORT_MS)

        ticked = [manager.is_active_bookmark_here(i) for i in range(2)]

        assert ticked == [False, True]

    def test_rows_outside_the_loop_are_grayed_out(self, block):
        manager = _Manager(block)

        block.seek(25000)
        block.set_loop_start_time(20000)

        enabled = [manager.is_active_bookmark_reachable(i) for i in range(2)]

        assert enabled == [False, True]

    def test_one_past_the_end_is_listed_but_grayed_out(self, make_block):
        block = make_block(bookmarks=(Bookmark(time_ms=LENGTH + 5000),))
        manager = _Manager(block)

        assert len(manager.menu_generator_bookmarks()) == 1
        assert not manager.is_active_bookmark_reachable(0)

    def test_no_bookmarks_no_list(self, make_block):
        manager = _Manager(make_block(bookmarks=()))

        assert not manager.is_active_has_bookmarks()
        assert manager.menu_generator_bookmarks() == []

    def test_a_live_stream_has_no_list(self, block):
        block.is_live = True

        assert not _Manager(block).is_active_has_bookmarks()


class TestClickingAMarker:
    def test_it_goes_to_its_bookmark_and_names_it(self, block):
        block.overlay.bookmark_clicked.emit((30000,))

        assert block.time == 30000
        assert block.notices == ["Goal & Run"]

    def test_it_is_a_seek_the_others_can_follow(self, block):
        synced = []
        block.sync_time.connect(synced.append)

        block.overlay.bookmark_clicked.emit((30000,))

        assert synced == [30000]

    def test_one_outside_the_loop_goes_nowhere(self, block):
        block.seek(25000)
        block.set_loop_start_time(20000)

        synced = []
        block.sync_time.connect(synced.append)

        block.overlay.bookmark_clicked.emit((10000,))

        assert block.time == 25000
        assert synced == []

    def test_one_inside_a_sponsor_is_played_not_skipped(self, block):
        block._skip_spans = (SkipSpan(25000, 40000, "sponsor"),)
        block.set_pause(False)

        block.overlay.bookmark_clicked.emit((30000,))
        _reported(block, 30000)
        _reported(block, 30400)

        assert _seeks(block) == [30000]

    def test_one_gone_meanwhile_goes_nowhere(self, block):
        block.overlay.bookmark_clicked.emit((12345,))

        assert block.time == 0


class TestAMarkersMenu:
    ITEMS = [
        "Jump to Bookmark",
        "---",
        "Rename Bookmark…",
        "Color",
        "Remove Bookmark",
    ]
    MANAGE = ["---", "Manage Bookmarks…"]

    def _titles(self, menu):
        return [
            "---" if action.isSeparator() else action.text()
            for action in menu.actions()
        ]

    def _item(self, menu, title):
        return next(action for action in menu.actions() if action.text() == title)

    def test_it_offers_jump_to_rename_and_remove_then_the_manager(self, block):
        menu = block.bookmark_menu((30000,))

        assert self._titles(menu) == self.ITEMS + self.MANAGE

    def test_rename_has_the_bookmarks_own_icon(self, block, mocker):
        named = mocker.patch.object(
            video_block_module.QIcon, "fromTheme", side_effect=lambda _name: QIcon()
        )

        block.bookmark_menu((30000,))

        assert mocker.call("bookmark-rename") in named.call_args_list

    def test_the_manager_opens_with_its_bookmark_picked_out(self, block, mocker):
        dialog = mocker.patch.object(video_block_module, "BookmarksDialog")
        block.seek(20000)

        self._item(block.bookmark_menu((30000,)), "Manage Bookmarks…").trigger()

        assert dialog.call_args.kwargs["selected"] == [1]

    def test_jump_to_goes_there_as_a_seek_the_others_can_follow(self, block):
        synced = []
        block.sync_time.connect(synced.append)

        self._item(block.bookmark_menu((30000,)), "Jump to Bookmark").trigger()

        assert block.time == 30000
        assert synced == [30000]
        assert block.notices == ["Goal & Run"]

    def test_jump_to_one_outside_the_loop_is_grayed_out(self, block):
        block.seek(25000)
        block.set_loop_start_time(20000)

        jump = self._item(block.bookmark_menu((10000,)), "Jump to Bookmark")

        assert not jump.isEnabled()

    def test_remove_takes_that_one_away_wherever_the_video_is(self, block):
        block.seek(20000)

        self._item(block.bookmark_menu((30000,)), "Remove Bookmark").trigger()

        assert _times(block) == [10000]

    def test_rename_names_that_one(self, block, mocker):
        mocker.patch.object(
            video_block_module.QBookmarkRenameDialog,
            "get_edits",
            return_value=("Win", None),
        )
        block.seek(20000)

        self._item(block.bookmark_menu((30000,)), "Rename Bookmark…").trigger()

        assert block.bookmarks[1] == Bookmark(time_ms=30000, name="Win")

    def test_a_shared_marker_has_a_menu_for_each_it_stands_for(self, block):
        menu = block.bookmark_menu((10000, 30000))

        submenus = [action.menu() for action in menu.actions() if action.menu()]

        # with where each is, as in the list; an ampersand doubled, to show
        # as one
        assert self._titles(menu) == [
            "Bookmark 1	00:10",
            "Goal && Run	00:30",
            *self.MANAGE,
        ]
        assert [self._titles(submenu) for submenu in submenus] == [self.ITEMS] * 2

    def test_its_manager_opens_with_all_of_them_picked_out(self, block, mocker):
        dialog = mocker.patch.object(video_block_module, "BookmarksDialog")

        menu = block.bookmark_menu((10000, 30000))
        self._item(menu, "Manage Bookmarks…").trigger()

        assert dialog.call_args.kwargs["selected"] == [0, 1]

    def test_each_of_those_jumps_to_its_own(self, block):
        menu = block.bookmark_menu((10000, 30000))

        self._item(menu.actions()[0].menu(), "Jump to Bookmark").trigger()

        assert block.time == 10000

    def test_and_removes_its_own(self, block):
        menu = block.bookmark_menu((10000, 30000))

        self._item(menu.actions()[1].menu(), "Remove Bookmark").trigger()

        assert _times(block) == [10000]

    def test_with_its_bookmarks_gone_there_is_none(self, block):
        assert block.bookmark_menu((12345,)) is None

    def test_left_open_while_another_file_came_it_leaves_that_one_be(
        self, block, tmp_path, mocker
    ):
        dialog = mocker.patch.object(video_block_module, "BookmarksDialog")
        (tmp_path / "other.mkv").touch()
        menu = block.bookmark_menu((30000,))

        block.next_video()
        block.video_driver._fake_player_timer.stop()
        theirs = (Bookmark(time_ms=5000), Bookmark(time_ms=20000))
        block.set_bookmarks(theirs)

        for title in ("Remove Bookmark", "Jump to Bookmark", "Manage Bookmarks…"):
            self._item(menu, title).trigger()

        assert block.bookmarks == theirs
        assert block.time != 20000
        dialog.assert_not_called()

    def test_a_name_typed_while_another_file_came_is_dropped(
        self, block, tmp_path, mocker
    ):
        (tmp_path / "other.mkv").touch()
        theirs = (Bookmark(time_ms=5000), Bookmark(time_ms=20000))

        def typed(**_kwargs):
            block.next_video()
            block.set_bookmarks(theirs)

            return "Win", "#ff3d3d"

        mocker.patch.object(
            video_block_module.QBookmarkRenameDialog, "get_edits", side_effect=typed
        )

        self._item(block.bookmark_menu((30000,)), "Rename Bookmark…").trigger()

        assert block.bookmarks == theirs

    @pytest.mark.parametrize(
        ("end_action", "action_txt"),
        [
            (VideoEndAction.NEXT_FILE, "Play Next File"),
            (VideoEndAction.CLOSE, "Close"),
        ],
    )
    def test_the_end_reached_while_a_name_is_typed_waits(
        self, block, tmp_path, mocker, end_action, action_txt
    ):
        (tmp_path / "other.mkv").touch()
        block.video_params.end_action = end_action
        block.set_pause(False)

        def typed(**_kwargs):
            block.loop_end_action()
            # where a close would land, if it was not held
            QApplication.processEvents()

            return "Win", None

        mocker.patch.object(
            video_block_module.QBookmarkRenameDialog, "get_edits", side_effect=typed
        )

        self._item(block.bookmark_menu((30000,)), "Rename Bookmark…").trigger()

        assert block.video_params.uri == tmp_path / "movie.mkv"
        assert not block._is_closing
        assert block.video_params.is_paused
        assert block.notices[-1] == f"Paused at the start instead of “{action_txt}”"
        assert block.bookmarks[1] == Bookmark(time_ms=30000, name="Win")

    def test_once_named_the_end_is_as_set_again(self, block, tmp_path, mocker):
        (tmp_path / "other.mkv").touch()
        block.video_params.end_action = VideoEndAction.NEXT_FILE
        mocker.patch.object(
            video_block_module.QBookmarkRenameDialog,
            "get_edits",
            return_value=("Win", None),
        )

        block.rename_bookmark(1)
        block.loop_end_action()

        assert block.video_params.uri == tmp_path / "other.mkv"

    def test_the_overlay_opens_it_where_it_was_asked_for(self, block, mocker):
        shown = mocker.patch.object(video_block_module.CustomMenu, "exec_")

        block.overlay.bookmark_menu_requested.emit(QPoint(40, 50), (30000,))

        shown.assert_called_once_with(QPoint(40, 50))


class TestClickingAMarkerAgainAndAgain:
    SHARED = (
        Bookmark(time_ms=30000, name="Goal"),
        Bookmark(time_ms=30600, name="Replay"),
        Bookmark(time_ms=31200, name="Again"),
    )

    def _click(self, block):
        block.overlay.bookmark_clicked.emit(
            tuple(bookmark.time_ms for bookmark in self.SHARED)
        )

        return block.time

    def test_it_goes_to_each_in_turn_and_round(self, make_block):
        block = make_block(self.SHARED)

        assert [self._click(block) for _ in range(4)] == [30000, 30600, 31200, 30000]
        assert block.notices == ["Goal", "Replay", "Again", "Goal"]

    def test_from_one_played_past_it_goes_to_the_next(self, make_block):
        block = make_block(self.SHARED)
        self._click(block)

        _reported(block, 30300)

        assert self._click(block) == 30600

    def test_away_from_them_it_starts_at_the_first(self, make_block):
        block = make_block(self.SHARED)
        self._click(block)
        self._click(block)

        block.seek(45000)

        assert self._click(block) == 30000

    def test_those_outside_the_loop_are_passed_over(self, make_block):
        block = make_block(self.SHARED)
        # past the one at 30.6, not near enough the next to be on it
        block.seek(30800)
        block.set_loop_start_time(30500)

        assert [self._click(block) for _ in range(3)] == [31200, 30600, 31200]


class TestColouring:
    COLORS = [
        "Default",
        "---",
        "Red",
        "Pink",
        "Purple",
        "Blue",
        "Cyan",
        "Green",
        "White",
        "---",
        "Custom…",
    ]

    def _menu(self, block, times=(30000,)):
        menu = block.bookmark_menu(times)

        return next(
            action.menu() for action in menu.actions() if action.text() == "Color"
        )

    def _titles(self, menu):
        return [
            "---" if action.isSeparator() else action.text()
            for action in menu.actions()
        ]

    def _item(self, menu, title):
        return next(action for action in menu.actions() if action.text() == title)

    def _ticked(self, menu):
        return [action.text() for action in menu.actions() if action.isChecked()]

    def test_the_menu_offers_default_the_bright_ones_and_any_other(self, block):
        assert self._titles(self._menu(block)) == self.COLORS

    def test_one_given_none_has_default_ticked(self, block):
        assert self._ticked(self._menu(block)) == ["Default"]

    def test_a_colour_picked_is_that_bookmarks_wherever_the_video_is(self, block):
        block.seek(5000)

        self._item(self._menu(block), "Blue").trigger()

        assert block.bookmarks[1] == Bookmark(
            time_ms=30000, name="Goal & Run", color=BLUE
        )
        assert block.bookmarks[0].color is None
        assert _bookmark_marks(block)[1].color == BLUE

    def test_and_ticked_from_then_on(self, block):
        self._item(self._menu(block), "Blue").trigger()

        assert self._ticked(self._menu(block)) == ["Blue"]

    def test_default_gives_it_back_the_bookmarks_own(self, block):
        block.set_bookmarks(
            (Bookmark(time_ms=10000), Bookmark(time_ms=30000, color=BLUE))
        )

        self._item(self._menu(block), "Default").trigger()

        assert block.bookmarks[1].color is None

    def test_the_menu_shows_its_colour(self, block):
        block.set_bookmarks((Bookmark(time_ms=30000, color=BLUE),))
        menu = block.bookmark_menu((30000,))

        color_item = self._item(menu, "Color")

        assert _icon_color(color_item.icon()) == BLUE

    def test_any_other_is_picked_by_hand(self, block, mocker):
        picker = mocker.patch.object(
            video_block_module, "color_picked_by_hand", return_value="#123456"
        )

        self._item(self._menu(block), "Custom…").trigger()

        assert block.bookmarks[1].color == "#123456"
        # starting from the one it has
        assert picker.call_args.args[1] is None

    def test_and_then_custom_is_ticked_in_that_colour(self, block):
        block.set_bookmarks((Bookmark(time_ms=30000, color="#123456"),))

        menu = self._menu(block)

        assert self._ticked(menu) == ["Custom…"]
        assert _icon_color(self._item(menu, "Custom…").icon()) == "#123456"

    def test_picking_by_hand_given_up_leaves_it(self, block, mocker):
        mocker.patch.object(
            video_block_module, "color_picked_by_hand", return_value=None
        )

        self._item(self._menu(block), "Custom…").trigger()

        assert block.bookmarks[1].color is None

    def test_the_end_reached_while_picking_waits(self, block, tmp_path, mocker):
        (tmp_path / "other.mkv").touch()
        block.video_params.end_action = VideoEndAction.NEXT_FILE
        block.set_pause(False)

        def picked(*_args):
            block.loop_end_action()
            QApplication.processEvents()

            return BLUE

        mocker.patch.object(
            video_block_module, "color_picked_by_hand", side_effect=picked
        )

        self._item(self._menu(block), "Custom…").trigger()

        assert block.video_params.uri == tmp_path / "movie.mkv"
        assert block.bookmarks[1].color == BLUE

    def test_left_open_while_another_file_came_it_leaves_that_one_be(
        self, block, tmp_path
    ):
        (tmp_path / "other.mkv").touch()
        menu = self._menu(block)

        block.next_video()
        block.video_driver._fake_player_timer.stop()
        theirs = (Bookmark(time_ms=5000), Bookmark(time_ms=30000))
        block.set_bookmarks(theirs)

        self._item(menu, "Blue").trigger()

        assert block.bookmarks == theirs

    def test_a_shared_marker_s_bookmarks_are_each_in_their_own_colour(self, block):
        block.set_bookmarks(
            (Bookmark(time_ms=30000), Bookmark(time_ms=30400, color=BLUE))
        )

        menu = block.bookmark_menu((30000, 30400))
        icons = [action.icon() for action in menu.actions() if action.menu()]

        assert [_icon_color(icon) for icon in icons] == ["#ffab00", BLUE]

    def test_each_has_a_colour_menu_of_its_own(self, block):
        block.set_bookmarks((Bookmark(time_ms=30000), Bookmark(time_ms=30400)))

        menu = block.bookmark_menu((30000, 30400))
        second = [action.menu() for action in menu.actions() if action.menu()][1]
        color_menu = next(
            action.menu() for action in second.actions() if action.text() == "Color"
        )

        self._item(color_menu, "Blue").trigger()

        assert [bookmark.color for bookmark in block.bookmarks] == [None, BLUE]


class TestTheRenameBoxColours:
    @pytest.fixture
    def answer(self, mocker):
        return mocker.patch.object(
            video_block_module.QBookmarkRenameDialog, "get_edits"
        )

    def test_it_starts_from_the_colour_it_has(self, block, answer):
        block.set_bookmarks((Bookmark(time_ms=30000, color=BLUE),))
        answer.return_value = None

        block.rename_bookmark(0)

        assert answer.call_args.kwargs["color"] == BLUE

    def test_the_name_and_colour_given_are_its(self, block, answer):
        answer.return_value = ("Win", BLUE)

        block.rename_bookmark(1)

        assert block.bookmarks[1] == Bookmark(time_ms=30000, name="Win", color=BLUE)

    def test_given_up_it_is_left_as_it_was(self, block, answer):
        answer.return_value = None

        block.rename_bookmark(1)

        assert block.bookmarks[1] == Bookmark(time_ms=30000, name="Goal & Run")


class TestTheRenameBox:
    """The box itself: the name, and the colour picked from circles."""

    def test_it_starts_on_default_for_one_with_no_colour(self, mocker):
        dialog_class = video_block_module.QBookmarkRenameDialog
        seen = {}

        def run(dialog):
            seen["color"] = dialog.colors.color
            return True

        mocker.patch.object(dialog_class, "exec", new=run)

        edits = dialog_class.get_edits(
            parent=None, title="t", name="Goal", placeholder="Bookmark 1", color=None
        )

        assert seen["color"] is None
        assert edits == ("Goal", None)

    def test_one_picked_is_given(self, mocker):
        dialog_class = video_block_module.QBookmarkRenameDialog

        def run(dialog):
            dialog.colors._presets[BLUE].setChecked(True)
            return True

        mocker.patch.object(dialog_class, "exec", new=run)

        edits = dialog_class.get_edits(
            parent=None, title="t", name="Goal", placeholder="", color=None
        )

        assert edits == ("Goal", BLUE)

    def test_one_picked_by_hand_before_is_there_to_keep(self, mocker):
        dialog_class = video_block_module.QBookmarkRenameDialog

        mocker.patch.object(dialog_class, "exec", return_value=True)

        edits = dialog_class.get_edits(
            parent=None, title="t", name="", placeholder="", color="#123456"
        )

        assert edits == ("", "#123456")

    def test_given_up_it_gives_nothing(self, mocker):
        dialog_class = video_block_module.QBookmarkRenameDialog

        mocker.patch.object(dialog_class, "exec", return_value=False)

        assert (
            dialog_class.get_edits(
                parent=None, title="t", name="", placeholder="", color=BLUE
            )
            is None
        )
