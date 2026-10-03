"""The playlist's bookmarks as the viewer meets them: sharing switched on and
off, with the questions it asks, and Bookmarks in Playlist."""

import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PyQt5.QtCore import QPoint, QSettings, Qt
from PyQt5.QtGui import QContextMenuEvent, QKeySequence
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.dialogs import playlist_bookmarks as viewer_module
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.playlist_bookmarks import Column, PlaylistBookmarksDialog
from gridplayer.models.bookmark import Bookmark
from gridplayer.models.file_bookmarks import FileBookmarks
from gridplayer.models.video import Video
from gridplayer.player.managers.bookmarks import BookmarksManager, BookmarksRegistry
from gridplayer.player.managers.settings import SettingsManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings

URL = "https://example.com/watch?v=1"

A = [Bookmark(time_ms=10000), Bookmark(time_ms=30000, name="Goal")]
B = [Bookmark(time_ms=20000, name="Kick-off")]


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)
    PlaylistSettings().clear()

    yield

    PlaylistSettings().clear()
    settings.settings = real_settings


class _Blocks(list):
    """The cells open, first to last in the grid."""

    def blocks_for_ids(self, _ids):
        return list(self)


def _cell(uri, title=None):
    return SimpleNamespace(video_params=Video(uri=uri), title=title)


@pytest.fixture
def movie(tmp_path):
    path = tmp_path / "movie.mkv"
    path.touch()
    return path


@pytest.fixture
def other(tmp_path):
    path = tmp_path / "other.mkv"
    path.touch()
    return path


@pytest.fixture
def blocks():
    return _Blocks()


@pytest.fixture
def manager(blocks):
    context = SimpleNamespace(
        video_blocks=blocks,
        commands=SimpleNamespace(layout_order=list, add_videos_to_layout=None),
    )

    parent = QWidget()
    made = BookmarksManager(context=context, parent=parent)
    made.registry = context.bookmarks
    # held on to: a parent collected out from under it takes the manager
    made.kept_parent = parent

    return made


@pytest.fixture
def answers(mocker):
    """The questions asked, answered with the button named, one by one."""

    asked = []
    to_give = []

    def _exec(box):
        asked.append(box.text())
        answer = to_give.pop(0)
        next(button for button in box.buttons() if answer in button.text()).click()
        return 0

    mocker.patch.object(QCustomMessageBox, "exec_", _exec)

    return SimpleNamespace(asked=asked, give=to_give.append)


class TestStoppingSharing:
    def test_it_asks_first_saying_what_comes_of_it(self, manager, movie, answers):
        manager.registry.set(movie, None, A)
        answers.give("Stop Sharing")

        manager.cmd_toggle_bookmarks_shared()

        assert "removed with it when it is closed" in answers.asked[0]
        assert not manager.registry.is_shared
        assert PlaylistSettings().get("playlist/bookmarks_shared") is False

    def test_thought_better_of_nothing_changes(self, manager, movie, answers):
        manager.registry.set(movie, None, A)
        answers.give("Cancel")

        manager.cmd_toggle_bookmarks_shared()

        assert manager.registry.is_shared
        assert not PlaylistSettings().is_overridden("playlist/bookmarks_shared")

    def test_with_no_bookmarks_there_is_nothing_to_ask(self, manager, answers):
        manager.cmd_toggle_bookmarks_shared()

        assert answers.asked == []
        assert not manager.registry.is_shared

    def test_every_cell_playing_a_file_gets_its_list(
        self, manager, blocks, movie, answers
    ):
        blocks.extend([_cell(movie), _cell(movie)])
        manager.registry.set(movie, None, A)
        answers.give("Stop Sharing")

        manager.cmd_toggle_bookmarks_shared()

        assert [
            manager.registry.get(movie, block.video_params.id) for block in blocks
        ] == [tuple(A), tuple(A)]


class TestSharing:
    @pytest.fixture
    def by_cell(self, manager, blocks, movie):
        blocks.extend([_cell(movie), _cell(movie)])
        manager.set_bookmarks_shared(False)
        return blocks

    def test_lists_that_differ_are_merged_if_the_viewer_says_so(
        self, manager, by_cell, movie, answers
    ):
        manager.registry.set(movie, by_cell[0].video_params.id, A)
        manager.registry.set(movie, by_cell[1].video_params.id, B)
        answers.give("Merge")

        manager.cmd_toggle_bookmarks_shared()

        assert "movie.mkv — 2 cells" in answers.asked[0]
        assert manager.registry.is_shared
        assert len(manager.registry.get(movie, None)) == 3

    def test_or_kept_separate(self, manager, by_cell, movie, answers):
        manager.registry.set(movie, by_cell[0].video_params.id, A)
        manager.registry.set(movie, by_cell[1].video_params.id, B)
        answers.give("Keep Separate")

        manager.cmd_toggle_bookmarks_shared()

        assert not manager.registry.is_shared
        assert manager.registry.get(movie, by_cell[1].video_params.id) == tuple(B)

    def test_with_one_list_to_a_file_there_is_nothing_to_ask(
        self, manager, by_cell, movie, answers
    ):
        manager.registry.set(movie, by_cell[0].video_params.id, A)

        manager.cmd_toggle_bookmarks_shared()

        assert answers.asked == []
        assert manager.registry.get(movie, None) == tuple(A)


def _settings_manager(is_confirmed):
    parent = QWidget()
    manager = SettingsManager(
        context=SimpleNamespace(
            commands=SimpleNamespace(confirm_bookmarks_shared=lambda _: is_confirmed)
        ),
        parent=parent,
    )
    manager.kept_parent = parent
    return manager


class TestFromTheSettings:
    def test_a_new_default_thought_better_of_leaves_the_playlist_as_it_was(
        self, mocker
    ):
        manager = _settings_manager(is_confirmed=False)

        told = []
        manager.set_bookmarks_shared.connect(told.append)
        previous = Settings().get_all()

        Settings().set("playlist/bookmarks_shared", False)
        manager._apply_settings(previous)

        assert told == []
        assert PlaylistSettings().get("playlist/bookmarks_shared") is True

    def test_one_gone_on_with_is_told(self):
        manager = _settings_manager(is_confirmed=True)

        told = []
        manager.set_bookmarks_shared.connect(told.append)
        previous = Settings().get_all()

        Settings().set("playlist/bookmarks_shared", False)
        manager._apply_settings(previous)

        assert told == [False]


# Bookmarks in Playlist


def _settle(until=lambda: True, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if until():
            return
        time.sleep(0.01)


@pytest.fixture
def registry():
    return BookmarksRegistry()


@pytest.fixture
def opened():
    return []


@pytest.fixture
def grid():
    """Whether the grid is full, and turns away the files opened."""

    return {"is_full": False}


@pytest.fixture
def open_viewer(registry, blocks, opened, grid):
    made = []

    def open_files(videos):
        if grid["is_full"]:
            return []

        opened.extend(videos)

        return list(videos)

    def _open():
        dialog = PlaylistBookmarksDialog(
            registry=registry,
            cells=lambda: list(blocks),
            open_files=open_files,
        )
        dialog.setAttribute(Qt.WA_DontShowOnScreen)
        dialog.show()
        QApplication.processEvents()

        made.append(dialog)

        return dialog

    yield _open

    for dialog in made:
        if dialog.isVisible():
            dialog.reject()
        dialog.deleteLater()

    QApplication.processEvents()


def _rows(dialog):
    model = dialog._model

    return [
        (
            model.index(row, Column.FILE).data(),
            model.index(row, Column.COUNT).data(),
            model.index(row, Column.STATUS).data(),
        )
        for row in range(model.rowCount())
    ]


def _pick(dialog, row, child=None):
    index = dialog._model.index(row, 0)
    if child is not None:
        dialog._list.expand(index)
        index = dialog._model.index(child, 0, index)

    selection = dialog._list.selectionModel()
    selection.setCurrentIndex(index, selection.ClearAndSelect | selection.Rows)


class TestTheViewer:
    def test_every_file_is_listed_with_how_it_stands(
        self, registry, blocks, open_viewer, movie, other, tmp_path
    ):
        gone = tmp_path / "gone.mkv"
        blocks.extend([_cell(movie), _cell(movie)])
        registry.set(movie, None, A)
        registry.set(other, None, B)
        registry.set(gone, None, B)
        registry.set(URL, None, A)

        dialog = open_viewer()
        _settle(lambda: ("gone.mkv", "1", "File missing") in _rows(dialog))

        assert _rows(dialog) == [
            ("movie.mkv", "2", "Open in 2 cells"),
            ("other.mkv", "1", "Not open"),
            ("gone.mkv", "1", "File missing"),
            ("example.com/watch?v=1", "2", "Stream, not open"),
        ]

    def test_a_file_opens_on_its_bookmarks(self, registry, open_viewer, movie):
        registry.set(movie, None, A)
        dialog = open_viewer()

        dialog._list.expand(dialog._model.index(0, 0))

        parent = dialog._model.index(0, 0)
        assert [
            dialog._model.index(row, 0, parent).data(Qt.UserRole + 1)
            for row in range(dialog._model.rowCount(parent))
        ] == [
            ("00:10.000", "Bookmark 1", False, None),
            ("00:30.000", "Goal", True, None),
        ]

    def test_shared_it_says_so_and_shows_no_cells(self, registry, open_viewer):
        registry.set(URL, None, A)

        dialog = open_viewer()

        assert "shared by every cell" in dialog._mode.text()
        assert dialog._list.isColumnHidden(Column.CELL)

    def test_by_cell_it_warns_of_what_goes_with_a_cell(
        self, registry, blocks, open_viewer, movie
    ):
        playing = _cell(movie, title="Left half")
        blocks.append(playing)
        registry.set_shared(False, ())
        registry.set(movie, playing.video_params.id, A)
        closed = uuid4()
        registry.set(movie, closed, B)
        registry.remember_cell(closed, "Right half", "#3d8be0")

        dialog = open_viewer()

        assert "removed when the playlist is saved" in dialog._mode.text()
        assert not dialog._list.isColumnHidden(Column.CELL)
        assert [
            (
                dialog._model.index(row, Column.CELL).data(),
                dialog._model.index(row, Column.STATUS).data(),
            )
            for row in range(2)
        ] == [("1 · Left half", "Playing"), ("Right half", "Closed cell")]

    def test_under_the_list_it_counts_them(self, registry, open_viewer, movie, other):
        registry.set(movie, None, A)
        registry.set(other, None, B)

        dialog = open_viewer()

        assert dialog._hint.text() == "Bookmarks: 3 · Files: 2"

    def test_by_cell_it_counts_the_cells(self, registry, blocks, open_viewer, movie):
        registry.set_shared(False, ())
        registry.set(movie, uuid4(), A)
        registry.set(movie, uuid4(), B)

        dialog = open_viewer()

        assert dialog._hint.text() == "Bookmarks: 3 · Cells: 2"

    def test_what_is_being_said_stays_over_them(
        self, registry, open_viewer, movie, other
    ):
        registry.set(movie, None, A)
        dialog = open_viewer()
        _pick(dialog, 0)
        dialog._copy()

        # a file's check come back, say
        registry.set(other, None, B)
        dialog._reload()

        assert dialog._hint.text() == "Bookmarks copied: 2"

        dialog._status_timer.timeout.emit()

        assert dialog._hint.text() == "Bookmarks: 3 · Files: 2"

    def test_with_none_it_says_so(self, open_viewer):
        dialog = open_viewer()

        assert dialog._model.rowCount() == 0
        assert dialog._list.empty_txt[0] == "No bookmarks in this playlist"

    def test_a_file_whose_folder_is_not_there_is_told_apart(
        self, registry, open_viewer, tmp_path
    ):
        # on a drive not connected, say
        registry.set(tmp_path / "unplugged" / "far.mkv", None, A)

        dialog = open_viewer()
        _settle(lambda: ("far.mkv", "2", "Folder not found") in _rows(dialog))

        assert _rows(dialog) == [("far.mkv", "2", "Folder not found")]
        assert dialog._unreachable_button.isEnabled()


class TestRemovingInTheViewer:
    def test_a_file_s_go_and_cancel_puts_them_back(self, registry, open_viewer):
        registry.set(URL, None, A)
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._remove()

        assert registry.entries() == []

        dialog.reject()

        assert registry.get(URL, None) == tuple(A)

    def test_ok_keeps_them_gone(self, registry, open_viewer):
        registry.set(URL, None, A)
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._remove()
        dialog.accept()

        assert registry.entries() == []

    def test_one_bookmark_of_a_file_goes_alone(self, registry, open_viewer):
        registry.set(URL, None, A)
        dialog = open_viewer()

        _pick(dialog, 0, child=1)
        QTest.keyClick(dialog._list, Qt.Key_Delete)

        assert registry.get(URL, None) == (A[0],)

    def test_the_unreachable_go_at_once(
        self, registry, blocks, open_viewer, movie, tmp_path
    ):
        registry.set_shared(False, ())
        playing = _cell(movie)
        blocks.append(playing)
        registry.set(movie, playing.video_params.id, A)
        registry.set(movie, uuid4(), B)
        registry.put_entries(
            [FileBookmarks(uri=tmp_path / "gone.mkv", bookmarks=list(B))]
        )

        dialog = open_viewer()
        _settle(lambda: "File missing" in [status for *_, status in _rows(dialog)])

        dialog._remove_unreachable()

        assert registry.entries() == [
            FileBookmarks(uri=movie, cell=playing.video_params.id, bookmarks=A)
        ]
        assert dialog._hint.text() == "Files removed: 2"

    def test_those_whose_folder_is_not_there_go_too(
        self, registry, open_viewer, tmp_path
    ):
        far = tmp_path / "unplugged" / "far.mkv"
        registry.set(far, None, A)
        registry.set(tmp_path / "gone.mkv", None, B)

        dialog = open_viewer()
        _settle(
            lambda: (
                {"File missing", "Folder not found"}
                <= {status for *_, status in _rows(dialog)}
            )
        )

        dialog._remove_unreachable()

        assert registry.entries() == []
        assert dialog._hint.text() == "Files removed: 2"

    def test_cancel_puts_nothing_in_a_playlist_opened_meanwhile(
        self, registry, open_viewer, movie
    ):
        registry.set(URL, None, A)
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._remove()

        registry.load([FileBookmarks(uri=movie, bookmarks=B)])
        dialog.reject()

        assert registry.entries() == [FileBookmarks(uri=movie, bookmarks=B)]


class TestOpeningInTheViewer:
    def test_a_file_not_open_opens_in_a_new_cell(
        self, registry, open_viewer, opened, other
    ):
        registry.set(other, None, A)
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._open()

        assert [video.uri for video in opened] == [other]

    def test_a_closed_cell_s_go_to_the_new_one(
        self, registry, open_viewer, opened, other
    ):
        registry.set_shared(False, ())
        registry.set(other, uuid4(), A)
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._open()

        assert registry.get(other, opened[0].id) == tuple(A)

    def test_turned_away_by_a_full_grid_a_closed_cell_s_stay(
        self, registry, open_viewer, grid, other
    ):
        registry.set_shared(False, ())
        closed = uuid4()
        registry.set(other, closed, A)
        grid["is_full"] = True
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._open()
        dialog.reject()

        assert registry.entries() == [
            FileBookmarks(uri=other, cell=closed, bookmarks=list(A))
        ]

    def test_one_open_is_not_opened_again(
        self, registry, blocks, open_viewer, opened, movie
    ):
        blocks.append(_cell(movie))
        registry.set(movie, None, A)
        dialog = open_viewer()

        _pick(dialog, 0)

        assert not dialog._open_button.isEnabled()

        dialog._open()

        assert opened == []


@pytest.fixture
def shown(mocker):
    """The menus shown, left open to look at."""

    menus = []

    def _exec(menu, _pos):
        menus.append(menu)

    mocker.patch.object(viewer_module.CustomMenu, "exec_", _exec)

    return menus


def _titles(menu):
    return [
        "---" if action.isSeparator() else action.text().split("\t")[0]
        for action in menu.actions()
    ]


def _item(menu, title):
    return next(
        action for action in menu.actions() if action.text().split("\t")[0] == title
    )


def _pick_more(dialog, row):
    selection = dialog._list.selectionModel()
    selection.select(dialog._model.index(row, 0), selection.Select | selection.Rows)


def _right_click(dialog, pos):
    """As the viewer would: the press picks the row under it, unless it is
    picked already, then the menu is asked for."""

    viewport = dialog._list.viewport()
    QTest.mouseClick(viewport, Qt.RightButton, Qt.NoModifier, pos)
    QApplication.sendEvent(viewport, QContextMenuEvent(QContextMenuEvent.Mouse, pos))


def _row_center(dialog, row):
    return dialog._list.visualRect(dialog._model.index(row, 0)).center()


def _under_the_rows(dialog):
    return QPoint(10, dialog._list.viewport().height() - 5)


@pytest.fixture
def clipboard():
    kept = QApplication.clipboard().text()
    QApplication.clipboard().setText("")

    yield QApplication.clipboard()

    QApplication.clipboard().setText(kept)


class TestCopyingInTheViewer:
    def test_a_file_s_are_copied_as_timestamps(self, registry, open_viewer, clipboard):
        registry.set(URL, None, A)
        dialog = open_viewer()

        _pick(dialog, 0)
        dialog._copy()

        assert clipboard.text() == "0:10\n0:30 Goal"
        assert dialog._hint.text() == "Bookmarks copied: 2"

    def test_bookmarks_picked_alone_go_alone(self, registry, open_viewer, clipboard):
        registry.set(URL, None, A)
        dialog = open_viewer()

        _pick(dialog, 0, child=1)
        dialog._copy()

        assert clipboard.text() == "0:30 Goal"

    def test_several_files_go_each_under_its_name(
        self, registry, open_viewer, clipboard, movie
    ):
        registry.set(movie, None, A)
        registry.set(URL, None, B)
        dialog = open_viewer()

        _pick(dialog, 0)
        _pick_more(dialog, 1)
        dialog._copy()

        assert clipboard.text() == (
            "movie.mkv\n0:10\n0:30 Goal\n\nhttps://example.com/watch?v=1\n0:20 Kick-off"
        )
        assert dialog._hint.text() == "Bookmarks copied: 3"

    def test_kept_by_cell_each_says_its_cell(
        self, registry, blocks, open_viewer, clipboard, movie
    ):
        left = _cell(movie, title="Left half")
        right = _cell(movie, title="Right half")
        blocks.extend([left, right])
        registry.set_shared(False, ())
        registry.set(movie, left.video_params.id, A)
        registry.set(movie, right.video_params.id, B)
        dialog = open_viewer()

        dialog._copy_all()

        assert clipboard.text() == (
            "movie.mkv (1 · Left half)\n0:10\n0:30 Goal"
            "\n\nmovie.mkv (2 · Right half)\n0:20 Kick-off"
        )

    def test_with_nothing_picked_there_is_nothing_to_copy(self, registry, open_viewer):
        registry.set(URL, None, A)
        dialog = open_viewer()

        assert not dialog._copy_button.isEnabled()

        _pick(dialog, 0)

        assert dialog._copy_button.isEnabled()

    def test_ctrl_c_copies_the_picked_ones(self, registry, open_viewer, clipboard):
        registry.set(URL, None, A)
        dialog = open_viewer()
        _pick(dialog, 0)

        QTest.keySequence(dialog._list, QKeySequence(QKeySequence.Copy))

        assert clipboard.text() == "0:10\n0:30 Goal"

    def test_to_the_millisecond_from_the_row_s_menu(
        self, registry, open_viewer, clipboard, shown
    ):
        registry.set(URL, None, [Bookmark(time_ms=10400, name="Start")])
        dialog = open_viewer()
        _pick(dialog, 0)
        dialog._list.menu_requested.emit(QPoint(10, 10))

        _item(shown[0], "Copy with Milliseconds").trigger()

        assert clipboard.text() == "0:10.400 Start"


class TestTheViewersMenus:
    def test_a_row_s_offers_what_can_be_done_with_the_picked(
        self, registry, open_viewer, shown, movie
    ):
        registry.set(movie, None, A)
        dialog = open_viewer()

        _right_click(dialog, _row_center(dialog, 0))

        assert _titles(shown[0]) == [
            "Open",
            "---",
            "Copy",
            "Copy with Milliseconds",
            "---",
            "Remove",
        ]
        assert [action.text().partition("\t")[2] for action in shown[0].actions()] == [
            "",
            "",
            "Ctrl+C",
            "",
            "",
            "Del",
        ]

    def test_open_is_for_a_file_not_open(
        self, registry, open_viewer, opened, shown, movie
    ):
        registry.set(movie, None, A)
        dialog = open_viewer()
        _right_click(dialog, _row_center(dialog, 0))

        _item(shown[0], "Open").trigger()

        assert [video.uri for video in opened] == [movie]

    def test_remove_removes_the_picked(self, registry, open_viewer, shown, movie):
        registry.set(movie, None, A)
        dialog = open_viewer()
        _right_click(dialog, _row_center(dialog, 0))

        _item(shown[0], "Remove").trigger()

        assert registry.entries() == []

    def test_under_the_rows_it_offers_what_can_be_done_with_them_all(
        self, registry, open_viewer, shown, clipboard, movie
    ):
        registry.set(movie, None, A)
        registry.set(URL, None, B)
        dialog = open_viewer()

        _right_click(dialog, _under_the_rows(dialog))

        assert _titles(shown[0]) == [
            "Copy All",
            "Copy All with Milliseconds",
            "---",
            "Remove Unreachable",
        ]

        _item(shown[0], "Copy All with Milliseconds").trigger()

        assert clipboard.text() == (
            "movie.mkv\n0:10.000\n0:30.000 Goal"
            "\n\nhttps://example.com/watch?v=1\n0:20.000 Kick-off"
        )

    def test_right_clicked_among_the_picked_they_stay_picked(
        self, registry, open_viewer, shown, clipboard, movie
    ):
        registry.set(movie, None, A)
        registry.set(URL, None, B)
        dialog = open_viewer()
        _pick(dialog, 0)
        _pick_more(dialog, 1)

        _right_click(dialog, _row_center(dialog, 1))
        _item(shown[0], "Copy").trigger()

        assert dialog._hint.text() == "Bookmarks copied: 3"


class TestColoursInTheViewer:
    def test_each_bookmark_s_row_has_its_colour(self, registry, open_viewer, movie):
        registry.set(
            movie,
            None,
            (Bookmark(time_ms=10000), Bookmark(time_ms=30000, color="#3d8bff")),
        )
        viewer = open_viewer()

        file_index = viewer._model.index(0, 0)
        rows = [
            viewer._model.index(row, 0, file_index).data(viewer_module.BOOKMARK_ROLE)
            for row in range(2)
        ]

        assert [row[3] for row in rows] == [None, "#3d8bff"]
