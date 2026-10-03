"""The bookmarks manager, on a real block.

A real block, on a stand-in frame that reports only the times a test tells
it to; the dialog shown off screen, and its edits made on the block.
"""

import dataclasses
import re
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QPoint, QSettings, Qt, QTimer
from PyQt5.QtGui import QColor, QContextMenuEvent, QIcon, QKeySequence
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QLineEdit,
    QWidget,
)

from gridplayer.dialogs import bookmarks as dialog_module
from gridplayer.dialogs.bookmarks import (
    DEFAULT_NAME_ROLE,
    BookmarksDialog,
    Column,
)
from gridplayer.models.bookmark import Bookmark
from gridplayer.models.seek_mark import SeekMarkKind
from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_overlay_elements import OverlayProgressBar

LENGTH = 60000

BOOKMARKS = (
    Bookmark(time_ms=10000),
    Bookmark(time_ms=30000, name="Goal & Run"),
    Bookmark(time_ms=50000, name="Late"),
)


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


@pytest.fixture(autouse=True)
def _own_clipboard():
    clipboard = QApplication.clipboard()
    kept = clipboard.text()

    clipboard.setText("")

    yield

    clipboard.setText(kept)


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
def make_block(tmp_path):
    made = []

    def _make(bookmarks=BOOKMARKS):
        # held on to: a parent collected out from under it takes the block
        parent = QWidget()

        video_file = tmp_path / "movie.mkv"
        video_file.touch()

        block = VideoBlock(video_driver=_Frame, context=_context(), parent=parent)
        block.set_video(
            Video(
                uri=video_file,
                playback_state=VideoInitialState.PAUSED,
                end_action=VideoEndAction.LOOP_FILE,
            )
        )
        block.set_bookmarks(bookmarks)

        # the time goes where a test says and nowhere else
        block.video_driver._fake_player_timer.stop()

        made.append((block, parent))

        return block

    yield _make

    for block, _parent in made:
        block.cleanup()
        block.url_resolver.cleanup()


@pytest.fixture
def block(make_block):
    return make_block()


@pytest.fixture
def open_dialog():
    opened = []

    def _open(block, selected=()):
        dialog = BookmarksDialog(block, selected=selected)
        dialog.setAttribute(Qt.WA_DontShowOnScreen)
        dialog.show()
        QApplication.processEvents()

        opened.append(dialog)

        return dialog

    yield _open

    for dialog in opened:
        if dialog.isVisible():
            dialog.reject()
        dialog.deleteLater()

    QApplication.processEvents()


@pytest.fixture
def dialog(block, open_dialog):
    return open_dialog(block)


def _times(block):
    return [bookmark.time_ms for bookmark in block.bookmarks]


def _cell(dialog, row, column, role=Qt.DisplayRole):
    return dialog._model.index(row, column).data(role)


def _picked(dialog):
    return dialog._picked_rows()


def _settle():
    """Let what is queued happen: an editor's text handed on once it is
    closed, and the edit made from it after that."""

    for _ in range(3):
        QApplication.processEvents()


def _edit(dialog, row, column, text):
    """Type into a row as the viewer would, and let the edit be made."""

    dialog._model.setData(dialog._model.index(row, column), text)
    _settle()


def _status(dialog):
    return dialog._hint.text()


def _marker_times(dialog):
    return [marks[0].time_ms for _x, marks in dialog._player.markers.markers]


class TestTheList:
    def test_a_row_each_with_where_it_is_to_a_tenth(self, make_block, open_dialog):
        block = make_block((Bookmark(time_ms=10400), Bookmark(time_ms=30000)))
        dialog = open_dialog(block)

        assert dialog._model.rowCount() == 2
        assert _cell(dialog, 0, Column.TIME) == "00:10.400"

    def test_one_without_a_name_goes_by_its_number_in_italics(self, dialog):
        assert _cell(dialog, 0, Column.NAME) == "Bookmark 1"
        assert _cell(dialog, 0, Column.NAME, Qt.FontRole).italic()

    def test_its_name_to_edit_is_its_own_the_number_left_to_show_under_it(self, dialog):
        assert _cell(dialog, 0, Column.NAME, Qt.EditRole) == ""
        assert _cell(dialog, 0, Column.NAME, DEFAULT_NAME_ROLE) == "Bookmark 1"
        assert _cell(dialog, 1, Column.NAME, Qt.EditRole) == "Goal & Run"

    def test_the_one_the_video_is_at_has_the_play_mark(self, block, dialog):
        def marks():
            return [
                _cell(dialog, row, Column.TIME, Qt.DecorationRole).cacheKey()
                for row in range(3)
            ]

        block.seek(30000)
        at_the_second = marks()

        block.seek(10000)
        at_the_first = marks()

        assert at_the_second[1] != at_the_second[0] == at_the_second[2]
        assert at_the_first[0] == at_the_second[1]

    def test_the_picked_ones_are_picked_out(self, block, open_dialog):
        dialog = open_dialog(block, selected=(0, 2))

        assert _picked(dialog) == [0, 2]
        assert dialog._player.markers._picked == {10000, 50000}

    def test_with_none_there_is_nothing_but_adding_and_pasting(
        self, make_block, open_dialog
    ):
        dialog = open_dialog(make_block(bookmarks=()))

        assert dialog._add_button.isEnabled()
        assert not dialog._remove_button.isEnabled()
        assert not dialog._copy_button.isEnabled()
        assert not dialog._remove_all_button.isEnabled()


class TestOutOfReach:
    def test_those_outside_the_loop_say_so(self, block, open_dialog):
        block.seek(30000)
        block.set_loop_start_time(20000)
        block.set_loop_end_time(40000)
        dialog = open_dialog(block)

        tooltips = [_cell(dialog, row, Column.NAME, Qt.ToolTipRole) for row in range(3)]

        assert tooltips == ["Outside the loop", None, "Outside the loop"]

    def test_the_loop_s_edges_are_drawn_across_the_list(self, block, open_dialog):
        block.seek(30000)
        block.set_loop_start_time(20000)
        block.set_loop_end_time(40000)
        dialog = open_dialog(block)

        edges = [(row, text) for row, text, _ in dialog._list.edges]

        assert edges == [(1, "loop start 00:20"), (2, "loop end 00:40")]

    def test_a_loop_with_none_inside_is_drawn_where_it_sits(self, block, open_dialog):
        block.seek(22000)
        block.set_loop_start_time(20000)
        block.set_loop_end_time(25000)
        dialog = open_dialog(block)

        edges = [(row, text) for row, text, _ in dialog._list.edges]

        assert edges == [(1, "loop 00:20-00:25")]

    def test_without_a_loop_there_are_no_edges(self, dialog):
        assert dialog._list.edges == ()

    def test_those_past_the_end_are_under_a_line_of_their_own(
        self, make_block, open_dialog
    ):
        block = make_block((Bookmark(time_ms=10000), Bookmark(time_ms=LENGTH + 5000)))
        dialog = open_dialog(block)

        edges = [(row, text) for row, text, _ in dialog._list.edges]

        assert edges == [(1, "end 01:00")]
        assert _cell(dialog, 1, Column.NAME, Qt.ToolTipRole) == (
            "Past the end of the video"
        )

    def test_one_out_of_reach_is_nowhere_to_jump(self, block, open_dialog):
        block.seek(30000)
        block.set_loop_start_time(20000)
        dialog = open_dialog(block, selected=(0,))

        dialog._jump()

        assert block.time == 30000


class TestAdding:
    def test_it_goes_where_the_video_is_picked_out_and_named_at_once(
        self, block, dialog
    ):
        block.seek(20000)

        QTest.mouseClick(dialog._add_button, Qt.LeftButton)

        assert _times(block) == [10000, 20000, 30000, 50000]
        assert _picked(dialog) == [1]
        assert dialog._list.state() == QAbstractItemView.EditingState

        editor = dialog._list.findChild(QLineEdit)
        assert editor.placeholderText() == "Bookmark 2"

    def test_the_name_typed_is_its_own(self, block, dialog):
        block.seek(20000)
        dialog._add()

        editor = dialog._list.findChild(QLineEdit)
        editor.setText("Kick-off")
        QTest.keyClick(editor, Qt.Key_Return)
        _settle()

        assert block.bookmarks[1] == Bookmark(time_ms=20000, name="Kick-off")
        assert _picked(dialog) == [1]

    def test_where_there_is_one_already_that_one_is_picked_out(self, block, dialog):
        block.seek(30200)

        dialog._add()

        assert _times(block) == [10000, 30000, 50000]
        assert _picked(dialog) == [1]
        assert _status(dialog) == "Already bookmarked"


class TestRenaming:
    def test_a_name_typed_is_its_own(self, block, dialog):
        _edit(dialog, 0, Column.NAME, "  Start  ")

        assert block.bookmarks[0] == Bookmark(time_ms=10000, name="Start")
        assert _picked(dialog) == [0]

    def test_a_name_left_empty_goes_back_to_its_number(self, block, dialog):
        _edit(dialog, 1, Column.NAME, "")

        assert block.bookmarks[1].name is None
        assert _cell(dialog, 1, Column.NAME) == "Bookmark 2"

    def test_f2_edits_the_name_of_the_current_one(self, block, open_dialog):
        dialog = open_dialog(block, selected=(1,))

        QTest.keyClick(dialog._list, Qt.Key_F2)

        assert dialog._list.state() == QAbstractItemView.EditingState
        assert dialog._list.findChild(QLineEdit).text() == "Goal & Run"


class TestMoving:
    def test_a_time_typed_moves_it_to_its_place_among_the_rest(self, block, dialog):
        _edit(dialog, 0, Column.TIME, "0:40.5")

        assert _times(block) == [30000, 40500, 50000]
        assert _picked(dialog) == [1]

    def test_it_is_shown_and_edited_to_the_ms(self, make_block, open_dialog):
        block = make_block((Bookmark(time_ms=10437),))
        dialog = open_dialog(block)

        assert _cell(dialog, 0, Column.TIME, Qt.EditRole) == "00:10.437"

        _edit(dialog, 0, Column.TIME, "00:10.438")

        assert _times(block) == [10438]

    def test_left_as_it_was_it_stays(self, make_block, open_dialog):
        block = make_block((Bookmark(time_ms=10437),))
        dialog = open_dialog(block)

        _edit(dialog, 0, Column.TIME, "00:10.437")

        assert _times(block) == [10437]

    @pytest.mark.parametrize(
        ("time_txt", "said"),
        [
            ("soon", "Not a time: soon"),
            ("1:30", "Past the end of the video"),
            ("0:30.3", "Another bookmark is there already"),
        ],
    )
    def test_a_time_it_cannot_go_to_leaves_it_and_says_why(
        self, block, dialog, time_txt, said
    ):
        _edit(dialog, 0, Column.TIME, time_txt)

        assert _times(block) == [10000, 30000, 50000]
        assert _status(dialog) == said

    def test_it_can_be_moved_to_where_the_video_is(self, block, open_dialog):
        dialog = open_dialog(block, selected=(0,))
        block.seek(20000)

        dialog._move_here()

        assert _times(block) == [20000, 30000, 50000]
        assert _picked(dialog) == [0]


class TestRemoving:
    def test_the_picked_ones_go_and_the_next_is_picked(self, block, open_dialog):
        dialog = open_dialog(block, selected=(0, 1))

        QTest.mouseClick(dialog._remove_button, Qt.LeftButton)

        assert _times(block) == [50000]
        assert _picked(dialog) == [0]

    def test_delete_does_the_same(self, block, open_dialog):
        dialog = open_dialog(block, selected=(2,))

        QTest.keyClick(dialog._list, Qt.Key_Delete)

        assert _times(block) == [10000, 30000]
        assert _picked(dialog) == [1]

    def test_all_of_them_go_without_asking(self, block, dialog):
        QTest.mouseClick(dialog._remove_all_button, Qt.LeftButton)

        assert block.bookmarks == ()
        assert dialog._model.rowCount() == 0


class TestJumping:
    def test_enter_goes_to_the_current_one(self, block, open_dialog):
        dialog = open_dialog(block, selected=(1,))

        QTest.keyClick(dialog._list, Qt.Key_Return)

        assert block.time == 30000
        # the dialog stays up
        assert dialog.isVisible()

    def test_it_is_a_seek_the_others_can_follow(self, block, open_dialog):
        dialog = open_dialog(block, selected=(2,))
        synced = []
        block.sync_time.connect(synced.append)

        QTest.keyClick(dialog._list, Qt.Key_Return)

        assert synced == [50000]

    def test_a_double_click_goes_to_the_one_clicked(self, block, dialog):
        dialog._list.setCurrentIndex(dialog._model.index(2, Column.NAME))

        dialog._list.doubleClicked.emit(dialog._model.index(2, Column.NAME))

        assert block.time == 50000

    def test_a_marker_clicked_picks_its_one_out_and_goes_there(self, block, dialog):
        dialog._player.markers.marker_clicked.emit((30000,))

        assert _picked(dialog) == [1]
        assert block.time == 30000


class TestCopyAndPaste:
    def test_copy_puts_them_on_the_clipboard_as_timestamps(self, dialog):
        QTest.mouseClick(dialog._copy_button, Qt.LeftButton)

        assert QApplication.clipboard().text() == ("0:10\n0:30 Goal & Run\n0:50 Late")
        assert _status(dialog) == "Bookmarks copied: 3"

    def test_paste_waits_for_timestamps_in_the_clipboard(self, dialog):
        assert not dialog._paste_button.isEnabled()

        QApplication.clipboard().setText("0:20 Kick-off")
        QApplication.processEvents()

        assert dialog._paste_button.isEnabled()

    def test_paste_adds_the_new_ones_and_picks_them_out(self, block, dialog):
        QApplication.clipboard().setText(
            "0:20 Kick-off\n0:30 Goal again\n1:30 Past the end\n0:55"
        )
        QApplication.processEvents()

        dialog._paste()

        assert block.bookmarks == (
            Bookmark(time_ms=10000),
            Bookmark(time_ms=20000, name="Kick-off"),
            Bookmark(time_ms=30000, name="Goal & Run"),
            Bookmark(time_ms=50000, name="Late"),
            Bookmark(time_ms=55000),
        )
        assert _picked(dialog) == [1, 4]
        assert _status(dialog) == "Bookmarks added: 2"

    def test_what_was_copied_pasted_back_adds_nothing(self, make_block, open_dialog):
        # a tenth of a second is dropped on the way out, and more than the
        # half second that makes two bookmarks one
        block = make_block((Bookmark(time_ms=21900), Bookmark(time_ms=51020)))
        dialog = open_dialog(block)

        dialog._copy_all()
        QApplication.processEvents()
        dialog._paste()

        assert _times(block) == [21900, 51020]
        assert _status(dialog) == "Nothing new to add"

    def test_one_a_second_on_from_another_is_added(self, make_block, open_dialog):
        block = make_block((Bookmark(time_ms=21900),))
        dialog = open_dialog(block)
        QApplication.clipboard().setText("0:23 Next")
        QApplication.processEvents()

        dialog._paste()

        assert _times(block) == [21900, 23000]

    def test_with_nothing_new_it_says_so(self, block, dialog):
        QApplication.clipboard().setText("0:30 Goal again")
        QApplication.processEvents()

        dialog._paste()

        assert _times(block) == [10000, 30000, 50000]
        assert _status(dialog) == "Nothing new to add"


class TestOkAndCancel:
    def test_cancel_puts_back_the_bookmarks_there_were(self, block, dialog):
        _edit(dialog, 0, Column.NAME, "Start")
        dialog._remove_all()

        dialog.reject()

        assert block.bookmarks == BOOKMARKS

    def test_ok_keeps_them(self, block, dialog):
        dialog._remove_all()

        dialog.accept()

        assert block.bookmarks == ()

    def test_with_it_closed_the_video_carries_on_without_it(self, block, dialog):
        shown = dialog._player.time_label.text

        dialog.accept()
        block.seek(30000)

        assert dialog._player.time_label.text == shown

    def test_what_is_said_goes_back_to_the_count(self, dialog):
        dialog._say("Something")
        dialog._status_timer.timeout.emit()

        assert _status(dialog) == "Bookmarks: 3"

    def test_an_edit_still_on_its_way_once_it_is_closed_is_not_made(
        self, block, dialog
    ):
        dialog._model.setData(dialog._model.index(0, Column.NAME), "Start")

        dialog.accept()
        _settle()

        assert block.bookmarks == BOOKMARKS


class TestTheVideo:
    def test_its_time_is_shown_as_over_the_video(self, block, dialog):
        block.seek(25000)

        assert dialog._player.time_label.text == "00:25.000 / 01:00"
        assert dialog._player.bar.position == pytest.approx(25000 / LENGTH)

    def test_a_click_on_the_bar_seeks_as_one_on_the_video_s_does(self, block, dialog):
        synced = []
        block.sync_time.connect(synced.append)

        dialog._player.bar.position_changed.emit(0.5)

        assert block.time == 30000
        assert synced == [30000]

    def test_play_pause_plays_and_pauses_it(self, block, dialog):
        dialog._player.play_pause.clicked.emit()

        assert not block.video_params.is_paused
        assert dialog._player.play_pause.is_off

    def test_space_does_too(self, block, dialog):
        QTest.keyClick(dialog._list, Qt.Key_Space)

        assert not block.video_params.is_paused

    def test_bookmarks_changed_meanwhile_are_shown(self, block, dialog):
        block.set_bookmarks([*BOOKMARKS, Bookmark(time_ms=40000)])

        assert dialog._model.rowCount() == 4

    def test_its_markers_are_the_bar_s(self, block, dialog):
        assert [
            x_marks[1][0].time_ms for x_marks in dialog._player.markers.markers
        ] == [
            10000,
            30000,
            50000,
        ]


class TestWithNothingPlaying:
    """Stopped at its end, failed, or loaded again: the video has no player
    for a while, and its bookmarks are still there to see and edit."""

    @pytest.fixture
    def stopped(self, block, dialog):
        block.stop_playback()

        return dialog

    def test_the_list_reads_as_it_did(self, stopped):
        assert stopped._model.rowCount() == 3
        assert _cell(stopped, 0, Column.TIME) == "00:10.000"
        assert _cell(stopped, 1, Column.NAME, Qt.ForegroundRole) is None
        assert stopped._list.edges == ()

    def test_the_bar_is_back_at_the_start_with_its_markers(self, stopped):
        assert stopped._player.time_label.text == "00:00.000 / 01:00"
        assert _marker_times(stopped) == [10000, 30000, 50000]

    def test_there_is_nowhere_to_jump_or_add_one(self, block, stopped):
        stopped._pick_rows([1])

        assert not stopped._add_button.isEnabled()

        stopped._jump()

        assert not block.is_video_initialized

    def test_they_can_be_named_moved_and_removed(self, block, stopped):
        _edit(stopped, 0, Column.NAME, "Start")
        _edit(stopped, 2, Column.TIME, "0:55")
        stopped._pick_rows([1])
        stopped._remove()

        assert block.bookmarks == (
            Bookmark(time_ms=10000, name="Start"),
            Bookmark(time_ms=55000, name="Late"),
        )
        assert _marker_times(stopped) == [10000, 55000]

    def test_not_past_the_end_it_had(self, block, stopped):
        _edit(stopped, 2, Column.TIME, "1:05")

        assert _times(block) == [10000, 30000, 50000]
        assert _status(stopped) == "Past the end of the video"

    def test_pasted_ones_are_added(self, block, stopped):
        QApplication.clipboard().setText("0:45 Later\n2:00 Too far")

        stopped._paste()

        assert _times(block) == [10000, 30000, 45000, 50000]

    def test_copied_ones_read_as_they_did(self, stopped):
        stopped._copy_all()

        assert QApplication.clipboard().text() == ("0:10\n0:30 Goal & Run\n0:50 Late")

    def test_play_starts_it_again(self, block, stopped):
        stopped._player.play_pause.clicked.emit()
        block.video_driver._fake_player_timer.stop()

        assert block.is_video_initialized
        assert stopped._add_button.isEnabled()
        assert stopped._player.play_pause.is_off

    def test_failed_there_is_nothing_to_play(self, block, dialog):
        block.error()

        assert not dialog._player.play_pause.isEnabled()

        dialog._player.play_pause.clicked.emit()
        QTest.keyClick(dialog._list, Qt.Key_Space)

        assert not block.is_video_initialized
        assert dialog._model.rowCount() == 3

    def test_loaded_again_it_is_all_back(self, block, dialog):
        block.seek(30000)
        block.set_loop_start_time(20000)

        block.reload()

        assert dialog._add_button.isEnabled()
        assert _marker_times(dialog) == [10000, 30000, 50000]
        assert [row for row, _, _ in dialog._list.edges] == [1]


def _manage_and(block, action):
    """Open the manager as the menus do, and do this with it once it is up.

    The dialog, and whether it was left open: shut half a second on, in case
    the test fails, rather than waited on for ever.
    """

    opened = {"left_open": False}

    give_up = QTimer()
    give_up.setSingleShot(True)
    give_up.setInterval(500)

    def act():
        opened["dialog"] = QApplication.activeModalWidget()
        action(opened["dialog"])
        give_up.start()

    def leave_it():
        opened["left_open"] = True
        opened["dialog"].reject()

    give_up.timeout.connect(leave_it)
    QTimer.singleShot(0, act)

    block.manage_bookmarks()
    give_up.stop()

    return opened


class TestHeldAtTheEnd:
    """An end action that would take the video out of its cell waits while
    the manager is open: the video is paused at its start instead, and the
    manager says so until it plays again."""

    @pytest.mark.parametrize(
        ("end_action", "action_txt"),
        [
            (VideoEndAction.NEXT_FILE, "Play Next File"),
            (VideoEndAction.PREVIOUS_FILE, "Play Previous File"),
            (VideoEndAction.SHUFFLE_FILE, "Random In Folder"),
            (VideoEndAction.CLOSE, "Close"),
        ],
    )
    def test_one_taking_it_away_waits(self, block, tmp_path, end_action, action_txt):
        (tmp_path / "other.mkv").touch()
        block.video_params.end_action = end_action
        seen = {}

        def play_to_the_end(dialog):
            block.set_pause(False)
            block.video_driver._fake_player_timer.stop()

            block.loop_end_action()
            # where a close would land, if it was not held
            QApplication.processEvents()

            seen["said"] = _status(dialog)
            seen["is_paused"] = block.video_params.is_paused

        opened = _manage_and(block, play_to_the_end)

        assert opened["left_open"]
        assert seen["said"] == (
            f"Paused at the start instead of “{action_txt}” while this is open."
        )
        assert seen["is_paused"]
        assert block.video_params.uri == tmp_path / "movie.mkv"
        assert not block._is_closing

    def test_closing_it_does_not_make_up_for_the_end(self, block, tmp_path):
        (tmp_path / "other.mkv").touch()
        block.video_params.end_action = VideoEndAction.NEXT_FILE

        _manage_and(block, lambda _dialog: block.loop_end_action())
        QApplication.processEvents()

        assert block.video_params.uri == tmp_path / "movie.mkv"
        assert block.video_params.is_paused

    def test_once_closed_it_ends_as_set(self, block, tmp_path):
        (tmp_path / "other.mkv").touch()
        block.video_params.end_action = VideoEndAction.NEXT_FILE

        _manage_and(block, lambda _dialog: block.loop_end_action())
        block.loop_end_action()

        assert block.video_params.uri == tmp_path / "other.mkv"

    def test_the_note_goes_once_it_plays_again(self, block, dialog):
        dialog.hold_end(VideoEndAction.NEXT_FILE)

        # said until then, not for a while as the rest is
        assert not dialog._status_timer.isActive()
        assert _status(dialog).startswith("Paused at the start")

        block.set_pause(False)
        block.video_driver._fake_player_timer.stop()

        assert _status(dialog) == "Bookmarks: 3"

    def test_stopping_is_not_held(self, block):
        block.video_params.end_action = VideoEndAction.STOP

        opened = _manage_and(block, lambda _dialog: block.loop_end_action())

        assert opened["left_open"]
        assert block.is_stopped
        assert block.bookmarks == BOOKMARKS


class TestTheVideoGoing:
    """Closed, or another file put in its place, from outside the manager:
    the manager closes with it, keeping what was done in it."""

    def test_closed_it_takes_the_manager_with_it(self, block):
        def remove_one_and_close(dialog):
            dialog._pick_rows([0])
            dialog._remove()
            block.close()

        opened = _manage_and(block, remove_one_and_close)

        assert not opened["left_open"]
        assert opened["dialog"].result() == QDialog.Accepted
        assert block.bookmarks == BOOKMARKS[1:]

    def test_another_file_in_its_place_takes_it_too(self, block, tmp_path):
        (tmp_path / "other.mkv").touch()

        opened = _manage_and(block, lambda _dialog: block.next_video())

        assert not opened["left_open"]
        assert opened["dialog"].result() == QDialog.Accepted
        assert block.video_params.uri == tmp_path / "other.mkv"


@pytest.fixture
def shown(mocker):
    """The menus shown, left open to look at."""

    menus = []

    def _exec(menu, _pos):
        menus.append(menu)

    mocker.patch.object(dialog_module.CustomMenu, "exec_", _exec)

    return menus


def _titles(menu):
    return [
        "---" if action.isSeparator() else action.text().split("	")[0]
        for action in menu.actions()
    ]


def _keys(menu):
    return [
        action.text().partition("	")[2]
        for action in menu.actions()
        if not action.isSeparator()
    ]


def _item(menu, title):
    return next(
        action for action in menu.actions() if action.text().split("	")[0] == title
    )


def _right_click(dialog, pos):
    QApplication.sendEvent(
        dialog._list.viewport(), QContextMenuEvent(QContextMenuEvent.Mouse, pos)
    )


def _row_center(dialog, row):
    return dialog._list.visualRect(dialog._model.index(row, Column.NAME)).center()


def _under_the_rows(dialog):
    return QPoint(10, dialog._list.viewport().height() - 5)


class TestTheRowMenu:
    ITEMS = [
        "Jump to Bookmark",
        "---",
        "Rename",
        "Edit Time",
        "Move to Current Position",
        "Color",
        "---",
        "Copy",
        "Copy with Milliseconds",
        "---",
        "Remove",
    ]

    def test_it_offers_what_can_be_done_with_a_row(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))

        dialog._list.menu_requested.emit(QPoint(10, 10))

        assert _titles(shown[0]) == self.ITEMS

    def test_each_says_its_key(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))

        dialog._list.menu_requested.emit(QPoint(10, 10))

        assert _keys(shown[0]) == [
            "Enter",
            "F2",
            "Shift+F2",
            "Ctrl+M",
            "",
            "Ctrl+C",
            "",
            "Del",
        ]

    def test_a_row_right_clicked_has_it(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))

        _right_click(dialog, _row_center(dialog, 1))

        assert _titles(shown[0]) == self.ITEMS

    def test_from_the_keyboard_it_is_the_current_one_s(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))

        QApplication.sendEvent(
            dialog._list,
            QContextMenuEvent(QContextMenuEvent.Keyboard, QPoint(0, 0)),
        )

        assert _titles(shown[0]) == self.ITEMS

    def test_rename_has_the_bookmarks_own_icon(self, block, open_dialog, shown, mocker):
        dialog = open_dialog(block, selected=(1,))
        named = mocker.patch.object(
            dialog_module.QIcon, "fromTheme", side_effect=lambda _name: QIcon()
        )

        dialog._list.menu_requested.emit(QPoint(10, 10))

        assert mocker.call("bookmark-rename") in named.call_args_list

    def test_edit_time_opens_the_time_to_type_over(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(shown[0], "Edit Time").trigger()

        assert dialog._list.state() == QAbstractItemView.EditingState
        assert dialog._list.findChild(QLineEdit).text() == "00:30.000"

    def test_a_marker_s_is_the_same_for_its_bookmark(self, block, dialog, shown):
        dialog._player.markers.marker_menu_requested.emit(QPoint(10, 10), (50000,))

        assert _picked(dialog) == [2]
        assert _titles(shown[0]) == self.ITEMS

    def test_jump_to_is_grayed_out_for_one_out_of_reach(
        self, block, open_dialog, shown
    ):
        block.seek(30000)
        block.set_loop_start_time(20000)
        dialog = open_dialog(block, selected=(0,))

        dialog._list.menu_requested.emit(QPoint(10, 10))

        assert not _item(shown[0], "Jump to Bookmark").isEnabled()


class TestTheListMenu:
    """Right-clicked under the rows: what can be done with the list."""

    ITEMS = [
        "Add",
        "---",
        "Copy All",
        "Copy All with Milliseconds",
        "Paste",
        "---",
        "Remove All",
    ]

    def test_it_offers_what_can_be_done_with_the_list(self, dialog, shown):
        _right_click(dialog, _under_the_rows(dialog))

        assert _titles(shown[0]) == self.ITEMS
        assert _keys(shown[0]) == ["Ins", "", "", "Ctrl+V", ""]

    def test_paste_waits_for_timestamps_in_the_clipboard(self, dialog, shown):
        _right_click(dialog, _under_the_rows(dialog))
        QApplication.clipboard().setText("0:20 Kick-off")
        _right_click(dialog, _under_the_rows(dialog))

        assert not _item(shown[0], "Paste").isEnabled()
        assert _item(shown[1], "Paste").isEnabled()

    def test_with_none_there_is_nothing_but_adding_and_pasting(
        self, make_block, open_dialog, shown
    ):
        dialog = open_dialog(make_block(bookmarks=()))
        QApplication.clipboard().setText("0:20 Kick-off")

        _right_click(dialog, _under_the_rows(dialog))

        enabled = {
            title: _item(shown[0], title).isEnabled()
            for title in ("Add", "Copy All", "Paste", "Remove All")
        }
        assert enabled == {
            "Add": True,
            "Copy All": False,
            "Paste": True,
            "Remove All": False,
        }

    def test_add_adds_one_where_the_video_is(self, block, dialog, shown):
        block.seek(20000)
        _right_click(dialog, _under_the_rows(dialog))

        _item(shown[0], "Add").trigger()

        assert _times(block) == [10000, 20000, 30000, 50000]

    def test_remove_all_removes_them_all(self, block, dialog, shown):
        _right_click(dialog, _under_the_rows(dialog))

        _item(shown[0], "Remove All").trigger()

        assert block.bookmarks == ()


class TestTheKeys:
    def test_shift_f2_opens_the_time_to_type_over(self, block, open_dialog):
        dialog = open_dialog(block, selected=(1,))

        QTest.keyClick(dialog._list, Qt.Key_F2, Qt.ShiftModifier)

        assert dialog._list.state() == QAbstractItemView.EditingState
        assert dialog._list.findChild(QLineEdit).text() == "00:30.000"

    def test_f2_alone_opens_the_name(self, block, open_dialog):
        dialog = open_dialog(block, selected=(1,))

        QTest.keyClick(dialog._list, Qt.Key_F2)

        assert dialog._list.findChild(QLineEdit).text() == "Goal & Run"

    def test_ctrl_m_moves_it_where_the_video_is(self, block, open_dialog):
        dialog = open_dialog(block, selected=(1,))
        block.seek(40000)

        QTest.keyClick(dialog._list, Qt.Key_M, Qt.ControlModifier)

        assert _times(block) == [10000, 40000, 50000]

    def test_insert_adds_one_where_the_video_is(self, block, dialog):
        block.seek(20000)

        QTest.keyClick(dialog._list, Qt.Key_Insert)

        assert _times(block) == [10000, 20000, 30000, 50000]

    def test_copy_copies_the_picked_ones(self, block, open_dialog):
        dialog = open_dialog(block, selected=(1, 2))

        QTest.keySequence(dialog._list, QKeySequence(QKeySequence.Copy))

        assert QApplication.clipboard().text() == "0:30 Goal & Run\n0:50 Late"
        assert _status(dialog) == "Bookmarks copied: 2"

    def test_paste_adds_those_in_the_clipboard(self, block, dialog):
        QApplication.clipboard().setText("0:20 Kick-off")

        QTest.keySequence(dialog._list, QKeySequence(QKeySequence.Paste))

        assert _times(block) == [10000, 20000, 30000, 50000]

    def test_paste_with_no_timestamps_says_so(self, block, dialog):
        QApplication.clipboard().setText("just some words")

        QTest.keySequence(dialog._list, QKeySequence(QKeySequence.Paste))

        assert _times(block) == [10000, 30000, 50000]
        assert _status(dialog) == "No timestamps to paste"


class TestTheCount:
    def test_it_says_how_many_there_are(self, dialog):
        assert _status(dialog) == "Bookmarks: 3"

    def test_it_follows_them(self, block, open_dialog):
        dialog = open_dialog(block, selected=(0,))

        QTest.keyClick(dialog._list, Qt.Key_Delete)

        assert _status(dialog) == "Bookmarks: 2"

    def test_with_none_it_says_nothing(self, make_block, open_dialog):
        dialog = open_dialog(make_block(bookmarks=()))

        assert _status(dialog) == ""

    def test_what_is_being_said_stays_over_it(self, block, dialog):
        dialog._copy_all()

        block.set_bookmarks(BOOKMARKS[:1])
        QApplication.processEvents()

        assert _status(dialog) == "Bookmarks copied: 3"

    def test_long_text_goes_on_a_line_more_not_off_the_edge(self, dialog):
        line_height = dialog._hint.fontMetrics().height()

        dialog._say(" ".join(["Wortreich"] * 30))
        QApplication.processEvents()

        assert dialog._hint.height() >= 2 * line_height
        assert dialog._hint.geometry().right() <= dialog._list.geometry().right()


class TestCopyingToTheMillisecond:
    def test_the_picked_ones_from_their_menu(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(shown[0], "Copy with Milliseconds").trigger()

        assert QApplication.clipboard().text() == "0:30.000 Goal & Run"

    def test_all_of_them_from_under_the_rows(self, make_block, open_dialog, shown):
        block = make_block((Bookmark(time_ms=10400), Bookmark(time_ms=21950)))
        dialog = open_dialog(block)
        _right_click(dialog, _under_the_rows(dialog))

        _item(shown[0], "Copy All with Milliseconds").trigger()

        assert QApplication.clipboard().text() == "0:10.400\n0:21.950"

    def test_pasted_into_another_they_are_exactly_where_they_were(
        self, make_block, open_dialog
    ):
        copied = (Bookmark(time_ms=10400, name="Start"), Bookmark(time_ms=21950))
        dialog = open_dialog(make_block(copied))
        dialog._copy_all(is_precise=True)

        other = make_block(bookmarks=())
        other_dialog = open_dialog(other)
        other_dialog._paste()

        assert other.bookmarks == copied

    def test_pasted_back_they_add_nothing(self, make_block, open_dialog):
        block = make_block((Bookmark(time_ms=10400), Bookmark(time_ms=21950)))
        dialog = open_dialog(block)

        dialog._copy_all(is_precise=True)
        dialog._paste()

        assert _times(block) == [10400, 21950]
        assert _status(dialog) == "Nothing new to add"

    def test_one_later_in_a_bookmark_s_second_is_a_place_of_its_own(
        self, make_block, open_dialog
    ):
        # in whole seconds, 0:21 would stand for the one at 21.3
        block = make_block((Bookmark(time_ms=21300),))
        dialog = open_dialog(block)
        QApplication.clipboard().setText("0:21.900 Later")

        dialog._paste()

        assert _times(block) == [21300, 21900]


class TestThePlayerRow:
    def test_button_time_and_bar_are_set_apart(self, dialog):
        player = dialog._player

        assert player.time_label.x() > player.play_pause.geometry().right() + 1
        assert player.bar.x() > player.time_label.geometry().right() + 1

    def test_the_bar_is_in_quieter_colours_than_over_a_video(self, dialog):
        bar = dialog._player.bar
        over_a_video = OverlayProgressBar()
        over_a_video.color = bar.color

        assert over_a_video.color_progress == QColor(Qt.red)
        assert over_a_video.color_select == QColor(Qt.blue)
        assert bar.color_progress.name() == "#d14747"
        assert bar.color_select.name() == "#4775d1"

    def test_the_grey_ahead_of_it_is_half_as_far_from_the_bar(self, dialog):
        bar = dialog._player.bar
        ahead = bar.color_ahead
        loud = bar.color_contrast_mid

        assert ahead.lightness() == pytest.approx(
            (bar.color.lightness() + loud.lightness()) / 2, abs=2
        )

    @pytest.mark.parametrize(("hover", "x"), [(0.9, 0.1), (0.9, 0.7), (0.3, 0.1)])
    def test_hovered_it_is_painted_in_them(self, block, dialog, hover, x):
        block.seek(30000)
        bar = dialog._player.bar
        bar.progress_select_x = int(bar.width() * hover)
        bar.underMouse = lambda: True

        image = bar.grab().toImage()
        pixel = QColor(image.pixel(int(image.width() * x), image.height() // 2))

        expected = {
            (0.9, 0.1): bar.color_select,
            (0.9, 0.7): bar.color_ahead,
            (0.3, 0.1): bar.color_select,
        }[(hover, x)]
        assert pixel.name() == expected.name()


class TestToTheMillisecond:
    def test_the_time_shown_is_to_the_millisecond(self, block, dialog):
        block.seek(25432)

        assert dialog._player.time_label.text == "00:25.432 / 01:00"

    def test_jumped_to_a_bookmark_it_reads_its_time_not_a_hair_short(
        self, block, dialog
    ):
        dialog._pick_rows([1])
        dialog._jump()

        # VLC's time a hair short of where the seek landed
        block.time = 29990

        assert dialog._player.time_label.text == "00:30.000 / 01:00"


class TestTheHoverTip:
    @pytest.fixture
    def mouse_at(self, mocker):
        at = {"x": 0}

        mocker.patch.object(
            dialog_module.QCursor, "pos", side_effect=lambda: QPoint(at["x"], 0)
        )

        def _move(x):
            at["x"] = x

        return _move

    def _hover(self, dialog, mouse_at, x, fraction):
        mouse_at(x)
        bar = dialog._player.bar
        bar.mouse_over.emit(QPoint(), fraction, bar.width())

        return dialog._hover_tip

    def test_it_tells_the_time_to_the_millisecond(self, dialog, mouse_at):
        tip = self._hover(dialog, mouse_at, 500, 0.5)

        assert tip.isVisible()
        assert tip.text() == "00:30.000"

    def test_it_follows_every_move_the_text_the_same_or_not(self, dialog, mouse_at):
        tip = self._hover(dialog, mouse_at, 500, 0.5)
        first_x = tip.x()

        tip = self._hover(dialog, mouse_at, 503, 0.5)

        assert tip.x() == first_x + 3

    def test_it_is_under_the_bar_centred_on_the_mouse(self, dialog, mouse_at):
        tip = self._hover(dialog, mouse_at, 500, 0.5)
        bar = dialog._player.bar
        bar_bottom = bar.mapToGlobal(QPoint(0, bar.height())).y()

        assert tip.y() > bar_bottom
        assert tip.x() + tip.width() // 2 == pytest.approx(500, abs=1)

    def test_a_marker_s_names_its_bookmarks(self, dialog, mouse_at):
        mouse_at(500)
        marks = tuple(m for m in dialog._block.seek_marks if m.time_ms == 30000)

        dialog._player.markers.marker_over.emit(QPoint(), marks, 100)

        assert re.search(
            r"00:30\.000 <img [^>]*>Goal &amp; Run", dialog._hover_tip.text()
        )

    def test_it_goes_once_the_mouse_leaves(self, dialog, mouse_at):
        tip = self._hover(dialog, mouse_at, 500, 0.5)

        dialog._player.bar.mouse_left.emit()

        assert not tip.isVisible()

    def test_it_goes_with_the_dialog(self, dialog, mouse_at):
        tip = self._hover(dialog, mouse_at, 500, 0.5)

        dialog.accept()

        assert not tip.isVisible()


class TestASharedMarker:
    SHARED = (
        Bookmark(time_ms=30000, name="Goal"),
        Bookmark(time_ms=30600, name="Replay"),
    )

    @pytest.fixture
    def shared(self, make_block, open_dialog, mocker):
        block = make_block(self.SHARED)
        mocker.patch.object(
            dialog_module.QCursor, "pos", side_effect=lambda: QPoint(500, 0)
        )

        return block, open_dialog(block)

    def _times(self):
        return tuple(bookmark.time_ms for bookmark in self.SHARED)

    def _marks(self, block):
        return tuple(mark for mark in block.seek_marks if mark.time_ms in self._times())

    def test_clicked_again_and_again_it_goes_to_each_in_turn(self, shared):
        block, dialog = shared
        visited = []

        for _ in range(3):
            dialog._player.markers.marker_clicked.emit(self._times())
            visited.append((block.time, _picked(dialog)))

        assert visited == [(30000, [0]), (30600, [1]), (30000, [0])]

    def test_its_tip_has_the_one_the_video_is_on_in_bold(self, shared):
        block, dialog = shared
        block.seek(30600)

        dialog._player.markers.marker_over.emit(QPoint(), self._marks(block), 100)

        tip_txt = dialog._hover_tip.text()
        assert re.search(r"<b>00:30\.600 <img [^>]*>Replay</b>", tip_txt)
        assert "<b>00:30.000" not in tip_txt

    def test_a_click_moves_the_bold_to_where_it_went(self, shared):
        block, dialog = shared
        dialog._player.markers.marker_over.emit(QPoint(), self._marks(block), 100)

        assert "<b>" not in dialog._hover_tip.text()

        dialog._player.markers.marker_clicked.emit(self._times())

        assert re.search(r"<b>00:30\.000 <img [^>]*>Goal</b>", dialog._hover_tip.text())

    def test_over_the_bar_again_there_is_none(self, shared):
        block, dialog = shared
        block.seek(30600)
        dialog._player.markers.marker_over.emit(QPoint(), self._marks(block), 100)

        bar = dialog._player.bar
        bar.mouse_over.emit(QPoint(), 0.1, bar.width())
        block.seek(30000)

        assert "<b>" not in dialog._hover_tip.text()


BLUE = "#3d8bff"
RED = "#ff3d3d"


def _color_menu(menu):
    return _item(menu, "Color").menu()


def _ticked(menu):
    return [action.text() for action in menu.actions() if action.isChecked()]


def _colors(block):
    return [bookmark.color for bookmark in block.bookmarks]


def _icon_color(icon, size=12):
    image = icon.pixmap(size, size).toImage()

    return image.pixelColor(image.width() // 2, image.height() // 2 - 1).name()


class TestColouringInTheManager:
    def test_the_picked_ones_are_coloured_together(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(0, 2))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(_color_menu(shown[0]), "Blue").trigger()

        assert _colors(block) == [BLUE, None, BLUE]

    def test_and_stay_picked_the_current_one_with_them(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(0, 2))
        dialog._pick_rows([0, 2], current=2)
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(_color_menu(shown[0]), "Blue").trigger()

        assert _picked(dialog) == [0, 2]
        assert dialog._current_row() == 2

    def test_their_colour_is_ticked_where_they_share_it(
        self, make_block, open_dialog, shown
    ):
        block = make_block(
            (Bookmark(time_ms=10000, color=BLUE), Bookmark(time_ms=30000, color=BLUE))
        )
        dialog = open_dialog(block, selected=(0, 1))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        assert _ticked(_color_menu(shown[0])) == ["Blue"]

    def test_none_where_they_differ(self, make_block, open_dialog, shown):
        block = make_block(
            (Bookmark(time_ms=10000, color=BLUE), Bookmark(time_ms=30000))
        )
        dialog = open_dialog(block, selected=(0, 1))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        assert _ticked(_color_menu(shown[0])) == []

    def test_default_gives_them_back_the_bookmarks_own(
        self, make_block, open_dialog, shown
    ):
        block = make_block(
            (Bookmark(time_ms=10000, color=BLUE), Bookmark(time_ms=30000, color=RED))
        )
        dialog = open_dialog(block, selected=(0, 1))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(_color_menu(shown[0]), "Default").trigger()

        assert _colors(block) == [None, None]

    def test_any_other_is_picked_by_hand(self, block, open_dialog, shown, mocker):
        picker = mocker.patch.object(
            dialog_module, "color_picked_by_hand", return_value="#123456"
        )
        dialog = open_dialog(block, selected=(1, 2))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(_color_menu(shown[0]), "Custom…").trigger()

        assert _colors(block) == [None, "#123456", "#123456"]
        assert picker.call_args.args[0] is dialog

    def test_picking_by_hand_given_up_leaves_them(
        self, block, open_dialog, shown, mocker
    ):
        mocker.patch.object(dialog_module, "color_picked_by_hand", return_value=None)
        dialog = open_dialog(block, selected=(1,))
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(_color_menu(shown[0]), "Custom…").trigger()

        assert _colors(block) == [None, None, None]

    def test_a_marker_s_menu_colours_its_bookmarks(self, dialog, block, shown):
        dialog._player.markers.marker_menu_requested.emit(QPoint(10, 10), (50000,))

        _item(_color_menu(shown[0]), "Blue").trigger()

        assert _colors(block) == [None, None, BLUE]

    def test_cancel_takes_the_colours_back(self, block, open_dialog, shown):
        dialog = open_dialog(block, selected=(1,))
        dialog._list.menu_requested.emit(QPoint(10, 10))
        _item(_color_menu(shown[0]), "Blue").trigger()

        dialog.reject()

        assert _colors(block) == [None, None, None]

    def test_each_row_shows_its_marker_in_its_colour(self, make_block, open_dialog):
        block = make_block(
            (Bookmark(time_ms=10000), Bookmark(time_ms=30000, color=BLUE))
        )
        dialog = open_dialog(block)

        icons = [_cell(dialog, row, Column.NAME, Qt.DecorationRole) for row in (0, 1)]

        assert [_icon_color(icon) for icon in icons] == ["#ffab00", BLUE]

    def test_the_markers_above_the_bar_are_in_theirs(self, make_block, open_dialog):
        block = make_block((Bookmark(time_ms=30000, color=BLUE),))
        dialog = open_dialog(block)
        markers = dialog._player.markers

        image = markers.grab().toImage()
        x = markers.markers[0][0]

        assert image.pixelColor(x, markers.height() - 3).name() == BLUE


class TestTheMarkersInTheTip:
    """Over a marker, each line of the tip has its bookmark's marker between
    its time and its name, striped or not, as over the video."""

    @pytest.fixture
    def over(self, make_block, open_dialog, mocker):
        mocker.patch.object(
            dialog_module.QCursor, "pos", side_effect=lambda: QPoint(500, 0)
        )

        def _over(*bookmarks):
            block = make_block(bookmarks)
            dialog = open_dialog(block)
            marks = tuple(
                mark for mark in block.seek_marks if mark.kind == SeekMarkKind.BOOKMARK
            )

            dialog._player.markers.marker_over.emit(QPoint(), marks, 100)

            return block, dialog

        return _over

    MIXED = (
        Bookmark(time_ms=30000, name="Goal", color=RED),
        Bookmark(time_ms=30600, name="Replay", color=BLUE),
    )

    def test_each_has_its_marker_between_its_time_and_its_name(self, over):
        _block, dialog = over(*self.MIXED)

        tip_txt = dialog._hover_tip.text()

        assert re.search(r"00:30\.000 <img [^>]*>Goal", tip_txt)
        assert re.search(r"00:30\.600 <img [^>]*>Replay", tip_txt)

    def test_the_one_the_video_is_on_is_still_in_bold(self, over):
        block, dialog = over(*self.MIXED)

        block.seek(30600)
        dialog._player.markers.marker_over.emit(QPoint(), dialog._tip_marks, 100)

        assert re.search(
            r"<b>00:30\.600 <img [^>]*>Replay</b>", dialog._hover_tip.text()
        )

    def test_of_one_colour_they_have_them_too(self, over):
        _block, dialog = over(
            Bookmark(time_ms=30000, name="Goal", color=BLUE),
            Bookmark(time_ms=30600, name="Replay", color=BLUE),
        )

        assert dialog._hover_tip.text().count("<img") == 2

    def test_one_alone_has_it_too_in_its_colour(self, over):
        _block, dialog = over(Bookmark(time_ms=30000, name="Goal", color=BLUE))
        tip = dialog._hover_tip

        assert re.search(r"00:30\.000 <img [^>]*>Goal", tip.text())

        image = tip.grab().toImage()

        assert any(
            image.pixelColor(x, y).name() == BLUE
            for x in range(image.width())
            for y in range(image.height())
        )

    def test_they_show_in_their_colours(self, over):
        _block, dialog = over(*self.MIXED)
        tip = dialog._hover_tip

        image = tip.grab().toImage()
        seen = {
            image.pixelColor(x, y).name()
            for x in range(image.width())
            for y in range(image.height())
        }

        assert RED in seen
        assert BLUE in seen
