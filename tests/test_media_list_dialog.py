"""The List window: the items of a list, edited as they go, Cancel putting
the list back; a stand-in cell for the one it was opened from."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import (
    QEvent,
    QMimeData,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QSettings,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QLineEdit

from gridplayer.dialogs import media_list as dialog_module
from gridplayer.dialogs.bookmarks import ROW_HEIGHT
from gridplayer.dialogs.media_list import (
    DETAILS_ROLE,
    DRAG_IMAGE_MAX_PX,
    KEYS_MIME,
    LOCATION_ROLE,
    SECOND_LINE_PX,
    THUMBNAIL_ROW_HEIGHT,
    THUMBNAIL_SIZE,
    TWO_LINE_ROW_HEIGHT,
    Column,
    ListReading,
    MediaListDialog,
    published_txt,
    short_count_txt,
    views_txt,
)
from gridplayer.main.init_resources import init_resources
from gridplayer.models.media_list import ItemDetails, ListItem, ListSource, MediaList
from gridplayer.params.static import ListSourceKind, ListView
from gridplayer.player.managers.list_info import LookupState
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.list_progress import ReadingStopped

ROOT = Path("/shows/season")


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


class _Cell(QObject):
    """The cell the window is opened from, playing an item of the list."""

    list_place_change = pyqtSignal(str)
    closing = pyqtSignal()

    def __init__(self, registry, list_id, key):
        super().__init__()

        self._registry = registry
        self.video_params = SimpleNamespace(list_id=list_id)
        self.key = key
        self.played = []
        # the cell's navigation part, done by the fake itself
        self.navigation = self

    @property
    def list_item(self):
        return self._registry.get(self.video_params.list_id).item_by_key(self.key)

    def play_list_item(self, place):
        self.played.append(place)


class _Reading:
    """Reads the way a test says, as the app's does off the thread."""

    def __init__(self):
        self.fresh = ()
        self.added = {}
        self.failed = ()
        # held until set, to look at the window while it reads: before it
        # says how far it has got, and after
        self.gate = None
        self.gate_after = None
        self.expand_gate = None
        # what reading says of how far it has got, in turn
        self.progress = ()
        self.told = None
        # the videos' pictures by their links; None for none to be fetched
        self.pictures = None
        self.pictures_asked = []
        # each picture fetched held until set
        self.picture_gate = None
        # what is known of items, looked up; None for nothing to look up
        self.lookups = None
        # the sources read, in turn
        self.read_from = []

    def expand(self, uris, progress=None):
        self.told = progress
        if self.expand_gate is not None:
            self.expand_gate.wait(5)
        items = tuple(
            item for uri in uris for item in self.added.get(uri, (ListItem(uri=uri),))
        )
        return items, self.failed

    def read_source(self, source, progress=None):
        self.read_from.append(source)
        self.told = progress
        if self.gate is not None:
            self.gate.wait(5)
        if progress is not None:
            for count in self.progress:
                progress(*count)
        if self.gate_after is not None:
            self.gate_after.wait(5)
        if isinstance(self.fresh, Exception):
            raise self.fresh
        return self.fresh

    def fetch_thumbnail(self, url):
        self.pictures_asked.append(url)
        if self.picture_gate is not None:
            self.picture_gate.wait(5)
        if url not in self.pictures:
            raise OSError("HTTP 404")
        return self.pictures[url]

    def as_reading(self):
        return ListReading(
            expand=self.expand,
            read_source=self.read_source,
            name_filters=["All (*)"],
            fetch_thumbnail=None if self.pictures is None else self.fetch_thumbnail,
            lookups=self.lookups,
        )


def _file(name):
    return ROOT / name


@pytest.fixture
def registry():
    return MediaListsRegistry()


@pytest.fixture
def season(registry):
    return registry.add(
        MediaList(
            name="Season",
            items=(
                ListItem(uri=_file("01.mkv"), duration_ms=60_000),
                ListItem(uri=_file("02.mkv"), title="Crossing", duration_ms=60_000),
                ListItem(uri=_file("Extras/03.mkv"), duration_ms=30_000),
            ),
            source=ListSource(kind=ListSourceKind.FOLDER, location=ROOT),
        )
    )


@pytest.fixture
def reading():
    return _Reading()


@pytest.fixture
def make_dialog(registry, reading):
    made = []

    def _make(media_list, cell_at=None, cells=(), open_in_new_cell=None):
        cell = None
        if cell_at is not None:
            cell = _Cell(registry, media_list.id, media_list.items[cell_at].key)

        dialog = MediaListDialog(
            registry=registry,
            list_id=media_list.id,
            reading=reading.as_reading(),
            block=cell,
            cells=lambda: [cell, *cells] if cell else list(cells),
            open_in_new_cell=open_in_new_cell,
        )
        dialog.cell = cell
        made.append(dialog)
        return dialog

    yield _make

    for dialog in made:
        dialog.done(0)
        dialog.deleteLater()


def _rows(dialog):
    model = dialog._model
    return [
        model.data(model.index(row, Column.TITLE)) for row in range(model.rowCount())
    ]


def _titles(registry, media_list):
    return [item.title or item.uri.name for item in registry.get(media_list.id).items]


def _pick(dialog, *rows):
    keys = [dialog._model.item_at(row).key for row in rows]
    dialog._pick_keys(keys)


def _taking_a_while(dialog):
    """Reading gone on for long enough to be shown going on."""

    assert dialog._reading_timer.isActive()

    dialog._reading_timer.stop()
    dialog._reading_timer.timeout.emit()


def _wait_until(condition, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if condition():
            return True
    return False


class TestShowing:
    def test_each_item_by_its_name_or_its_files(self, make_dialog, season):
        dialog = make_dialog(season)

        assert _rows(dialog) == ["01.mkv", "Crossing", str(Path("Extras/03.mkv"))]

    def test_named_whole_on_hover_then_where_it_is(self, make_dialog, channels):
        dialog = make_dialog(channels)
        model = dialog._model

        tip = model.data(model.index(0, Column.TITLE), Qt.ToolTipRole)

        assert tip.index("<b>One</b>") < tip.index("http://tv/1")

    def test_a_name_in_its_hover_said_as_it_is(self, make_dialog, registry):
        media_list = registry.add(
            MediaList(
                name="Shows",
                items=(ListItem(uri="http://tv/1?a=1&b=2", title="<Tom & Jerry>"),),
            )
        )
        dialog = make_dialog(media_list)
        model = dialog._model

        tip = model.data(model.index(0, Column.TITLE), Qt.ToolTipRole)

        assert "&lt;Tom &amp; Jerry&gt;" in tip
        assert "http://tv/1?a=1&amp;b=2" in tip

    def test_the_sort_menu_s_rows_lined_up(self, make_dialog, channels):
        """With no icon of their own, Qt sizes them as if no row had one,
        and their names run off the menu's edge."""

        init_resources()
        theme = QIcon.themeName()
        QIcon.setThemeName("dark")
        dialog = make_dialog(channels)

        try:
            dialog._fill_sort_menu()
            actions = [a for a in dialog._sort_menu.actions() if not a.isSeparator()]
            # looked up in the theme as they are asked for
            has_icons = [not action.icon().isNull() for action in actions]
        finally:
            QIcon.setThemeName(theme)

        assert has_icons
        assert all(has_icons)

    def test_view_and_sort_have_icons_and_there_is_no_remove_button(
        self, make_dialog, season
    ):
        """Taking off is the row menu's and the Delete key's."""

        init_resources()
        theme = QIcon.themeName()
        QIcon.setThemeName("dark")
        dialog = make_dialog(season)

        try:
            has_icons = [
                not button.icon().isNull()
                for button in (dialog._view_button, dialog._sort_button)
            ]
        finally:
            QIcon.setThemeName(theme)

        assert has_icons == [True, True]
        assert not hasattr(dialog, "_remove_button")

    def test_numbered_and_timed(self, make_dialog, season):
        model = make_dialog(season)._model

        assert model.data(model.index(1, Column.NUMBER)) == "2"
        assert model.data(model.index(2, Column.LENGTH)) == "0:30"

    def test_the_cells_item_marked(self, make_dialog, season):
        model = make_dialog(season, cell_at=1)._model

        assert model.data(model.index(1, Column.TITLE), Qt.FontRole).bold()
        assert model.data(model.index(0, Column.TITLE), Qt.FontRole) is None

    def test_named_after_the_list(self, make_dialog, season):
        assert make_dialog(season).windowTitle() == "List — Season"

    def test_counted_with_the_whole_length(self, make_dialog, season):
        assert make_dialog(season)._hint.text() == "Items: 3 · 2:30"

    def test_no_length_until_every_items_is_known(self, make_dialog, registry):
        media_list = registry.add(
            MediaList(items=(ListItem(uri=_file("a.mkv")), ListItem(uri="http://x")))
        )

        assert make_dialog(media_list)._hint.text() == "Items: 2"

    def test_where_it_was_read_from(self, make_dialog, season):
        dialog = make_dialog(season)

        assert dialog._source_title.text() == "Source: Folder"
        assert dialog._source_label.text() == str(ROOT)
        assert not dialog._source_panel.isHidden()
        assert dialog._source_button.text() == "Refresh"
        assert not dialog._source_button.isHidden()

    @pytest.mark.parametrize(
        ("source", "title"),
        [
            (ListSource(kind=ListSourceKind.URL, location="http://tv/l"), "Link"),
            (
                ListSource(kind=ListSourceKind.FILE, location=ROOT / "tv.m3u"),
                "Playlist file",
            ),
            (
                ListSource(
                    kind=ListSourceKind.FOLDER, location=ROOT, is_recursive=True
                ),
                "Folder, with subfolders",
            ),
        ],
    )
    def test_what_it_was_read_from(self, make_dialog, registry, source, title):
        media_list = registry.add(MediaList(source=source))

        dialog = make_dialog(media_list)

        assert dialog._source_title.text() == f"Source: {title}"
        assert dialog._source_label.text() == str(source.location)

    def test_no_source_for_a_list_read_from_nowhere(self, make_dialog, registry):
        media_list = registry.add(MediaList(items=(ListItem(uri="http://x"),)))

        assert make_dialog(media_list)._source_panel.isHidden()

    def test_the_other_cells_playing_it_told(self, make_dialog, season):
        other = SimpleNamespace(video_params=SimpleNamespace(list_id=season.id))
        stranger = SimpleNamespace(video_params=SimpleNamespace(list_id=None))

        dialog = make_dialog(season, cell_at=0, cells=(stranger, other))

        assert not dialog._shared_label.isHidden()
        assert "Cell 3 also plays this list" in dialog._shared_label.text()

    def test_nothing_told_where_no_other_does(self, make_dialog, season):
        assert make_dialog(season, cell_at=0)._shared_label.isHidden()


class TestFinding:
    def test_by_name(self, make_dialog, season):
        dialog = make_dialog(season)

        dialog._filter_edit.setText("cross")

        assert _rows(dialog) == ["Crossing"]
        assert dialog._hint.text() == "Shown: 1 of 3"

    def test_by_group(self, make_dialog, registry):
        channels = registry.add(
            MediaList(
                items=(
                    ListItem(uri="http://tv/1", title="One", group="News"),
                    ListItem(uri="http://tv/2", title="Two", group="Sport"),
                    ListItem(uri="http://tv/3", title="Three"),
                )
            )
        )
        dialog = make_dialog(channels)
        combo = dialog._group_combo

        assert [combo.itemText(i) for i in range(combo.count())] == [
            "All groups (3)",
            "News (1)",
            "Sport (1)",
            "No group (1)",
        ]

        combo.setCurrentIndex(2)
        assert _rows(dialog) == ["Two"]

        combo.setCurrentIndex(3)
        assert _rows(dialog) == ["Three"]

    def test_no_groups_no_box(self, make_dialog, season):
        assert make_dialog(season)._group_combo.isHidden()


class TestFindingOnALongList:
    def test_waits_for_typing_to_stop(self, make_dialog, registry):
        media_list = registry.add(
            MediaList(
                items=tuple(
                    ListItem(uri=f"http://tv/{n}", title=f"Channel {n}")
                    for n in range(dialog_module.FIND_AT_ONCE_ITEMS + 1)
                )
            )
        )
        dialog = make_dialog(media_list)

        dialog._filter_edit.setText("Channel 20000")

        assert dialog._model.rowCount() == len(media_list.items)
        assert _wait_until(lambda: dialog._model.rowCount() == 1)


class TestEditing:
    def test_renamed_in_a_box_over_its_title(self, make_dialog, season):
        """Framed, as a bookmark is renamed: Qt's own line has no frame."""

        dialog = make_dialog(season)
        dialog.show()
        _pick(dialog, 1)

        dialog._edit_name()
        QApplication.processEvents()

        editor = dialog._list.viewport().findChild(QLineEdit)
        row = dialog._list.visualRect(dialog._model.index(1, Column.TITLE))
        assert type(editor) is QLineEdit
        assert editor.hasFrame()
        assert editor.geometry() == row.adjusted(0, 1, 0, -1)

    def test_an_item_renamed(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        model = dialog._model

        model.setData(model.index(0, Column.TITLE), "Pilot")
        QTest.qWait(0)

        assert _titles(registry, season)[0] == "Pilot"

    def test_its_own_name_back_is_no_name(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        model = dialog._model

        model.setData(model.index(1, Column.TITLE), "02.mkv")
        QTest.qWait(0)

        assert registry.get(season.id).items[1].title is None

    def test_the_list_renamed(self, make_dialog, registry, season):
        dialog = make_dialog(season)

        dialog._name_edit.textEdited.emit("Season One")

        assert registry.get(season.id).name == "Season One"
        assert dialog.windowTitle() == "List — Season One"

    def test_items_removed(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        _pick(dialog, 0, 2)

        dialog._remove()

        assert _titles(registry, season) == ["Crossing"]
        assert dialog._hint.text() == "Removed: 2"

    def test_items_of_the_source_removed_stay_off_it(
        self, make_dialog, registry, season
    ):
        dialog = make_dialog(season)
        _pick(dialog, 0)

        dialog._remove()

        assert registry.get(season.id).removed == (_file("01.mkv"),)

    def test_the_next_one_picked_after_a_removal(self, make_dialog, season):
        dialog = make_dialog(season)
        _pick(dialog, 0)

        dialog._remove()

        assert [item.title for item in dialog._picked_items()] == ["Crossing"]

    def test_moved_to_the_top(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        _pick(dialog, 2)

        dialog._move_to_top()

        assert _titles(registry, season) == ["03.mkv", "01.mkv", "Crossing"]

    def test_moved_to_the_bottom(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        _pick(dialog, 0)

        dialog._move_to_bottom()

        assert _titles(registry, season) == ["Crossing", "03.mkv", "01.mkv"]

    def test_dragged_to_another_place(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        model = dialog._model
        data = model.mimeData([model.index(0, 0)])

        model.dropMimeData(data, Qt.MoveAction, 3, 0, model.index(-1, -1))
        QTest.qWait(0)

        assert _titles(registry, season) == ["Crossing", "03.mkv", "01.mkv"]

    def test_not_dragged_about_while_found_by_name(self, make_dialog, season):
        dialog = make_dialog(season)
        model = dialog._model
        data = model.mimeData([model.index(0, 0)])

        dialog._filter_edit.setText("0")

        assert not model.canDropMimeData(data, Qt.MoveAction, 0, 0, model.index(-1, -1))

    @pytest.mark.parametrize(
        ("how", "expected"),
        [
            ("name", ["01.mkv", "Crossing", "03.mkv"]),
            ("reverse", ["03.mkv", "Crossing", "01.mkv"]),
            ("length", ["03.mkv", "01.mkv", "Crossing"]),
        ],
    )
    def test_sorted(self, make_dialog, registry, season, how, expected):
        dialog = make_dialog(season)

        dialog._sort(how)

        assert _titles(registry, season) == expected

    def test_kept_with_ok(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        _pick(dialog, 0)
        dialog._remove()

        dialog.accept()

        assert len(registry.get(season.id).items) == 2

    def test_put_back_with_cancel(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        _pick(dialog, 0)
        dialog._remove()
        dialog._name_edit.textEdited.emit("Other")

        dialog.reject()

        assert registry.get(season.id) == season

    def test_kept_when_the_cell_closes(self, make_dialog, registry, season):
        dialog = make_dialog(season, cell_at=0)
        _pick(dialog, 1)
        dialog._remove()

        dialog.cell.closing.emit()

        assert dialog.result() == dialog.Accepted
        assert len(registry.get(season.id).items) == 2

    def test_closed_with_the_list_taken_away(self, make_dialog, registry, season):
        dialog = make_dialog(season)
        dialog.show()

        registry.remove(season.id)

        assert dialog.isHidden()

    def test_edits_elsewhere_shown(self, make_dialog, registry, season):
        dialog = make_dialog(season)

        registry.update_item(season.id, season.items[0].key, title="Renamed")

        assert _rows(dialog)[0] == "Renamed"


def _over_row(dialog, row, part):
    """A point in a row: part of the way down it, the middle across it."""

    view = dialog._list
    top = view.rowViewportPosition(row)
    return QPoint(view.viewport().width() // 2, top + int(view.rowHeight(row) * part))


def _dragged(dialog, kind, pos, data, actions=Qt.MoveAction, keys=Qt.NoModifier):
    """A drag over the list as Qt hands it on, to the rows' viewport."""

    if kind == QEvent.Drop:
        event = QDropEvent(QPointF(pos), actions, data, Qt.LeftButton, keys)
    elif kind == QEvent.DragEnter:
        event = QDragEnterEvent(pos, actions, data, Qt.LeftButton, keys)
    else:
        event = QDragMoveEvent(pos, actions, data, Qt.LeftButton, keys)

    QApplication.sendEvent(dialog._list.viewport(), event)
    return event


def _dragged_over(dialog, pos, data, **kwargs):
    _dragged(dialog, QEvent.DragEnter, pos, data, **kwargs)
    return _dragged(dialog, QEvent.DragMove, pos, data, **kwargs)


class _Drag:
    """QDrag, its exec_ dropping where it is told to: Windows' own drag
    needs a hand on the mouse."""

    view = None
    drop_at = None
    made = []

    def __init__(self, source):
        self.source = source
        _Drag.made.append(self)

    def setMimeData(self, data):
        self.data = data

    def setPixmap(self, pixmap):
        self.pixmap = pixmap

    def setHotSpot(self, hot_spot):
        self.hot_spot = hot_spot

    def exec_(self, actions, default_action):
        dialog = self.view.window()
        _dragged_over(dialog, self.drop_at, self.data)
        drop = _dragged(dialog, QEvent.Drop, self.drop_at, self.data)
        return drop.dropAction()


class TestDraggingRows:
    @pytest.fixture
    def dialog(self, make_dialog, season, mocker):
        dialog = make_dialog(season)
        dialog.show()
        QApplication.processEvents()

        _Drag.view = dialog._list
        _Drag.made = []
        mocker.patch.object(dialog_module, "QDrag", _Drag)

        return dialog

    def _drag_rows(self, dialog, *rows, to):
        _pick(dialog, *rows)
        _Drag.drop_at = to
        dialog._list.startDrag(Qt.MoveAction)
        QTest.qWait(0)

    def test_put_before_a_row_let_go_of_in_its_top_half(self, dialog, registry, season):
        self._drag_rows(dialog, 0, to=_over_row(dialog, 2, 0.3))

        assert _titles(registry, season) == ["Crossing", "01.mkv", "03.mkv"]

    def test_put_after_a_row_let_go_of_in_its_bottom_half(
        self, dialog, registry, season
    ):
        self._drag_rows(dialog, 0, to=_over_row(dialog, 2, 0.7))

        assert _titles(registry, season) == ["Crossing", "03.mkv", "01.mkv"]

    def test_several_together(self, dialog, registry, season):
        self._drag_rows(dialog, 0, 2, to=_over_row(dialog, 1, 0.2))

        assert _titles(registry, season) == ["01.mkv", "03.mkv", "Crossing"]

    def test_at_the_end_below_the_rows(self, dialog, registry, season):
        view = dialog._list
        below = QPoint(20, view.rowViewportPosition(2) + view.rowHeight(2) + 30)

        self._drag_rows(dialog, 0, to=below)

        assert _titles(registry, season) == ["Crossing", "03.mkv", "01.mkv"]

    def test_moved_not_copied(self, dialog):
        self._drag_rows(dialog, 0, to=_over_row(dialog, 2, 0.7))

        assert _Drag.made[0].data.hasFormat(KEYS_MIME)
        assert dialog._list._is_dragging_rows is False

    def test_the_line_where_it_goes_across_the_row(self, dialog):
        view = dialog._list
        data = dialog._model.mimeData([dialog._model.index(0, 0)])
        view._is_dragging_rows = True

        _dragged_over(dialog, _over_row(dialog, 1, 0.3), data)
        QApplication.processEvents()

        y = view.rowViewportPosition(1)
        assert view._drop_line_y() == y
        shot = view.viewport().grab().toImage()
        text = view.palette().color(QPalette.Text).rgb()
        assert shot.pixel(40, y) == text
        assert shot.pixel(view.viewport().width() - 6, y) == text

    def test_the_line_gone_once_the_drag_goes(self, dialog):
        view = dialog._list
        data = dialog._model.mimeData([dialog._model.index(0, 0)])
        view._is_dragging_rows = True
        _dragged_over(dialog, _over_row(dialog, 1, 0.3), data)

        QApplication.sendEvent(view.viewport(), QEvent(QEvent.DragLeave))

        assert view._drop_pos is None

    def test_another_list_s_rows_turned_away(self, dialog):
        """Keys are of a list of their own: from another window, or another
        player, they would move the wrong items."""

        data = QMimeData()
        data.setData(KEYS_MIME, b"1,2")

        moved = _dragged_over(dialog, _over_row(dialog, 1, 0.3), data)

        assert not moved.isAccepted()
        assert dialog._list._drop_pos is None

    def test_from_elsewhere_added_never_moved(self, dialog, registry, season):
        """Explorer takes a file away from its folder if it is moved."""

        data = QMimeData()
        data.setText("http://tv/1")
        actions = Qt.CopyAction | Qt.MoveAction
        at = _over_row(dialog, 1, 0.3)

        moved = _dragged_over(dialog, at, data, actions=actions, keys=Qt.ShiftModifier)
        drop = _dragged(dialog, QEvent.Drop, at, data, actions, Qt.ShiftModifier)

        assert moved.dropAction() == Qt.CopyAction
        assert drop.dropAction() == Qt.CopyAction
        assert _wait_until(lambda: len(registry.get(season.id).items) == 4)
        assert registry.get(season.id).items[1].uri == "http://tv/1"

    def test_said_on_a_card_beside_the_pointer(self, dialog):
        self._drag_rows(dialog, 1, to=_over_row(dialog, 2, 0.7))

        drag = _Drag.made[0]
        assert drag.hot_spot.x() < 0
        assert drag.hot_spot.y() < 0
        assert not drag.pixmap.isNull()

    def test_the_card_no_wider_than_it_is_let_be(self, dialog, registry, season):
        long_title = "A channel with a name as long as they come " * 4
        key = registry.get(season.id).items[0].key
        registry.update_item(season.id, key, title=long_title)
        QApplication.processEvents()
        view = dialog._list

        one = view._drag_image([dialog._model.index(0, 0)])
        three = view._drag_image([dialog._model.index(row, 0) for row in range(3)])

        assert one.width() / one.devicePixelRatio() <= DRAG_IMAGE_MAX_PX
        assert three.width() < one.width()


class TestStayingScrolled:
    """Where the list is scrolled to stays as it is edited, the cell's item
    far off at the top: the cell says its place again at every edit."""

    @pytest.fixture
    def dialog(self, make_dialog, registry):
        media_list = registry.add(
            MediaList(
                name="Long",
                items=tuple(
                    ListItem(uri=f"http://tv/{n}", title=f"Channel {n}")
                    for n in range(300)
                ),
            )
        )
        dialog = make_dialog(media_list, cell_at=0)
        dialog.show()
        QApplication.processEvents()

        # as VideoBlock does, once the list has changed
        cell = dialog.cell
        registry.changed.connect(lambda _id: cell.list_place_change.emit("1/300"))

        dialog._list.verticalScrollBar().setValue(2000)
        QApplication.processEvents()

        return dialog

    def _picked_in_view(self, dialog):
        view = dialog._list
        row = view.rowAt(view.viewport().height() // 2)
        _pick(dialog, row)
        return row

    def test_after_one_taken_off(self, dialog):
        self._picked_in_view(dialog)

        dialog._remove()
        QApplication.processEvents()

        assert dialog._list.verticalScrollBar().value() == 2000

    def test_after_one_moved(self, dialog):
        row = self._picked_in_view(dialog)
        key = dialog._model.item_at(row).key

        dialog._move((key,), row + 3)
        QApplication.processEvents()

        assert dialog._list.verticalScrollBar().value() == 2000

    def test_after_one_renamed(self, dialog):
        row = self._picked_in_view(dialog)

        dialog._model.setData(dialog._model.index(row, Column.TITLE), "Renamed")
        QApplication.processEvents()

        assert dialog._list.verticalScrollBar().value() == 2000

    def test_the_cell_followed_to_the_item_it_goes_on_to(self, dialog, registry):
        cell = dialog.cell
        cell.key = registry.get(cell.video_params.list_id).items[290].key

        cell.list_place_change.emit("291/300")

        view = dialog._list
        shown = view.visualRect(dialog._model.index(290, 0))
        assert view.viewport().rect().contains(shown.center())


class TestAdding:
    def test_at_the_end_put_on_by_hand(self, make_dialog, registry, season):
        dialog = make_dialog(season)

        dialog._add_uris(["http://tv/1"])

        assert _wait_until(lambda: len(registry.get(season.id).items) == 4)
        added = registry.get(season.id).items[-1]
        assert added.uri == "http://tv/1"
        assert added.is_added
        assert dialog._hint.text() == "Added: 1"

    def test_where_dropped(self, make_dialog, registry, season):
        dialog = make_dialog(season)

        dialog._model.dropped.emit(["http://tv/1"], 1)

        assert _wait_until(lambda: len(registry.get(season.id).items) == 4)
        assert registry.get(season.id).items[1].uri == "http://tv/1"

    def test_a_folder_as_its_files(self, make_dialog, registry, season, reading):
        reading.added["/other"] = (
            ListItem(uri=Path("/other/a.mkv")),
            ListItem(uri=Path("/other/b.mkv")),
        )
        dialog = make_dialog(season)

        dialog._add_uris(["/other"])

        assert _wait_until(lambda: len(registry.get(season.id).items) == 5)

    def test_one_taken_off_put_back_is_no_longer_kept_off(
        self, make_dialog, registry, season
    ):
        dialog = make_dialog(season)
        _pick(dialog, 0)
        dialog._remove()

        dialog._add_uris([str(_file("01.mkv"))])

        assert _wait_until(lambda: len(registry.get(season.id).items) == 3)
        assert registry.get(season.id).removed == ()

    def test_pasted(self, make_dialog, registry, season):
        QApplication.clipboard().setText("http://tv/1\nhttp://tv/2")
        dialog = make_dialog(season)

        dialog._paste()

        assert _wait_until(lambda: len(registry.get(season.id).items) == 5)

    def test_nothing_to_paste_said(self, make_dialog, season):
        dialog = make_dialog(season)

        dialog._paste()

        assert dialog._hint.text() == "Nothing to paste"

    def test_what_could_not_be_read_said(self, make_dialog, season, reading):
        reading.added["/bad"] = ()
        reading.failed = (("/bad", "no media files"),)
        dialog = make_dialog(season)

        dialog._add_uris(["/bad"])

        assert _wait_until(lambda: "Could not be read" in dialog._hint.text())


class TestReadingAgain:
    def test_new_in_and_gone_out(self, make_dialog, registry, season, reading):
        reading.fresh = (
            ListItem(uri=_file("01.mkv")),
            ListItem(uri=_file("01b.mkv")),
            ListItem(uri=_file("Extras/03.mkv")),
        )
        dialog = make_dialog(season)

        dialog._refresh()

        assert _wait_until(lambda: dialog._hint.text() == "New: 1 · Gone: 1")
        assert [item.uri.name for item in registry.get(season.id).items] == [
            "01.mkv",
            "01b.mkv",
            "03.mkv",
        ]

    def test_nothing_new(self, make_dialog, season, reading):
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)
        dialog = make_dialog(season)

        dialog._refresh()

        assert _wait_until(lambda: dialog._hint.text() == "Nothing new")

    def test_what_went_wrong_said(self, make_dialog, registry, season, reading):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)

        dialog._refresh()

        assert _wait_until(lambda: not dialog._error_box.isHidden())
        assert dialog._error_title.text() == "Folder not found"
        assert dialog._error_about.text() == (
            "It may have been moved, renamed or deleted."
        )
        assert registry.get(season.id) == season
        assert "Folder not found" not in dialog._hint.text()

    def test_tried_again(self, make_dialog, registry, season, reading):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)
        dialog._refresh()
        assert _wait_until(lambda: not dialog._error_box.isHidden())
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)

        dialog._error_again_button.click()

        assert dialog._error_box.isHidden()
        assert _wait_until(lambda: dialog._hint.text() == "Nothing new")
        assert dialog._error_box.isHidden()
        assert registry.read_error(season.id) is None

    def test_tried_again_the_way_it_failed(self, make_dialog, season, reading, mocker):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)
        mocker.patch.object(dialog, "_is_reload_confirmed", return_value=True)
        dialog._reload_from_source()
        assert _wait_until(lambda: not dialog._error_box.isHidden())
        read = mocker.patch.object(dialog, "_read_source_again")

        dialog._error_again_button.click()

        read.assert_called_once_with("reload", None)

    def test_put_away(self, make_dialog, registry, season, reading):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)
        dialog._refresh()
        assert _wait_until(lambda: not dialog._error_box.isHidden())

        dialog._error_hide_button.click()

        assert dialog._error_box.isHidden()
        assert registry.read_error(season.id) is None

    def test_said_again_when_the_window_opens_next(self, make_dialog, season, reading):
        reading.fresh = FileNotFoundError("Folder not found")
        first = make_dialog(season)
        first._refresh()
        assert _wait_until(lambda: not first._error_box.isHidden())
        first.done(0)

        dialog = make_dialog(season)

        assert not dialog._error_box.isHidden()
        assert dialog._error_title.text() == "Folder not found"

    def test_hidden_while_reading(self, make_dialog, season, reading):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)
        dialog._refresh()
        assert _wait_until(lambda: not dialog._error_box.isHidden())
        reading.gate = threading.Event()

        dialog._refresh()

        assert dialog._error_box.isHidden()
        reading.gate.set()
        assert _wait_until(lambda: not dialog._is_reading)
        assert not dialog._error_box.isHidden()

    def test_full_error_in_the_details(self, make_dialog, season, reading, mocker):
        reading.fresh = FileNotFoundError("Folder not found: <D:/Videos>")
        dialog = make_dialog(season)
        shown = []
        mocker.patch(
            "gridplayer.dialogs.media_list.ErrorDetailsDialog.exec_",
            lambda details_dialog: shown.append(details_dialog),
        )

        dialog._refresh()

        assert _wait_until(lambda: not dialog._error_box.isHidden())
        assert dialog._error_tag.tag == ("File", "Missing")

        dialog._error_details_button.click()

        (details_dialog,) = shown
        assert "Folder not found: <D:/Videos>" in details_dialog._error.raw
        assert "Folder not found: <D:/Videos>" in details_dialog.raw.toPlainText()

    def test_reloaded_with_everything_undone_once_said(
        self, make_dialog, registry, season, reading, mocker
    ):
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)
        dialog = make_dialog(season)
        mocker.patch.object(dialog, "_is_reload_confirmed", return_value=True)
        _pick(dialog, 0)
        dialog._remove()
        dialog._sort("reverse")
        dialog._add_uris(["http://tv/1"])
        assert _wait_until(lambda: len(registry.get(season.id).items) == 3)

        dialog._reload_from_source()

        assert _wait_until(lambda: dialog._hint.text() == "Reloaded: 3")
        media_list = registry.get(season.id)
        assert [item.uri for item in media_list.items] == [
            item.uri for item in season.items
        ]
        assert [item.title for item in media_list.items] == [None, None, None]
        assert media_list.removed == ()

    def test_left_as_it_is_unless_said(
        self, make_dialog, registry, season, reading, mocker
    ):
        reading.fresh = (ListItem(uri=_file("new.mkv")),)
        dialog = make_dialog(season)
        mocker.patch.object(dialog, "_is_reload_confirmed", return_value=False)

        dialog._reload_from_source()
        QTest.qWait(50)

        assert not dialog._is_reading
        assert registry.get(season.id) == season

    def test_the_cell_stays_on_its_item(
        self, make_dialog, registry, season, reading, mocker
    ):
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)
        dialog = make_dialog(season, cell_at=1)
        mocker.patch.object(dialog, "_is_reload_confirmed", return_value=True)
        dialog._model.setData(dialog._model.index(1, Column.TITLE), "Renamed")

        dialog._reload_from_source()

        assert _wait_until(lambda: dialog._hint.text() == "Reloaded: 3")
        assert dialog.cell.list_item.uri == season.items[1].uri

    def test_asked_first_cancel_the_default(self, make_dialog, season, mocker):
        dialog = make_dialog(season)
        asked = []

        def answered(box):
            asked.append((box.text(), box.defaultButton().text()))
            return 0

        mocker.patch.object(dialog_module.QCustomMessageBox, "exec_", answered)

        assert dialog._is_reload_confirmed() is False
        assert asked[0][0].startswith("Reload the list and discard your changes")
        assert asked[0][1] == "Cancel"

    def test_offered_on_the_source_panel_s_menu(self, make_dialog, season, mocker):
        dialog = make_dialog(season)
        shown = []
        mocker.patch.object(
            dialog_module.CustomMenu,
            "exec_",
            lambda menu, *_: shown.extend(a.text() for a in menu.actions()),
        )

        dialog._show_source_menu(dialog._source_panel.rect().center())

        assert "Reload and Discard Changes…" in shown

    def test_nothing_done_once_cancelled(self, make_dialog, registry, season, reading):
        reading.fresh = (ListItem(uri=_file("new.mkv")),)
        dialog = make_dialog(season)

        dialog._refresh()
        dialog.reject()
        QTest.qWait(100)

        assert registry.get(season.id) == season


class _Lookups(QObject):
    """Looks nothing up: says what a test tells it to, and keeps what it
    was asked."""

    changed = pyqtSignal(object)
    finished = pyqtSignal(object, int, int, int)
    learned = pyqtSignal(object, object)

    def __init__(self):
        super().__init__()
        self.states = {}
        self.asked = []
        self.stopped = []
        self.tried = []

    def look_up(self, list_id, items, is_missing_only):
        self.asked.append((list_id, [item.key for item in items], is_missing_only))

    def state(self, list_id):
        return self.states.get(list_id)

    def stop(self, list_id):
        self.stopped.append(list_id)
        self.states.pop(list_id, None)
        self.changed.emit(list_id)

    def try_again(self, list_id):
        self.tried.append(list_id)

    def tell(self, list_id, state):
        self.states[list_id] = state
        self.changed.emit(list_id)


@pytest.fixture
def lookups(reading):
    reading.lookups = _Lookups()
    return reading.lookups


def _menu_actions(mocker):
    """The entries of the next menu shown, by their names."""

    shown = {}
    mocker.patch.object(
        dialog_module.CustomMenu,
        "exec_",
        lambda menu, *_: shown.update(
            {action.text(): action for action in menu.actions() if action.text()}
        ),
    )
    return shown


def _menu_names(mocker):
    names = []
    mocker.patch.object(
        dialog_module.CustomMenu,
        "exec_",
        lambda menu, *_: names.extend(action.text() for action in menu.actions()),
    )
    return names


class TestGettingInfo:
    def test_get_info_for_the_rows_picked(self, make_dialog, season, lookups, mocker):
        dialog = make_dialog(season)
        keys = [season.items[0].key, season.items[2].key]
        dialog._pick_keys(keys)
        shown = _menu_actions(mocker)

        dialog._show_row_menu(QPoint())
        shown["Get Info"].trigger()

        assert lookups.asked == [(season.id, keys, False)]

    def test_after_rename(self, make_dialog, season, lookups, mocker):
        dialog = make_dialog(season)
        dialog._pick_keys([season.items[0].key])
        names = _menu_names(mocker)

        dialog._show_row_menu(QPoint())

        assert names[names.index("Rename\tF2") + 1] == "Get Info"

    def test_not_for_what_is_neither_a_file_nor_a_link(
        self, make_dialog, registry, lookups, mocker
    ):
        cameras = registry.add(MediaList(items=(ListItem(uri="rtsp://camera/1"),)))
        dialog = make_dialog(cameras)
        dialog._pick_keys([cameras.items[0].key])
        shown = _menu_actions(mocker)

        dialog._show_row_menu(QPoint())

        assert not shown["Get Info"].isEnabled()

    def test_none_where_nothing_is_looked_up(self, make_dialog, season, mocker):
        dialog = make_dialog(season)
        dialog._pick_keys([season.items[0].key])
        names = _menu_names(mocker)

        dialog._show_row_menu(QPoint())
        dialog._show_list_menu(QPoint())

        assert "Get Info" not in names
        assert "Get Missing Info" not in names

    def test_get_missing_info_for_the_whole_list(
        self, make_dialog, season, lookups, mocker
    ):
        dialog = make_dialog(season)
        names = _menu_names(mocker)
        dialog._show_list_menu(QPoint())
        assert names[-1] == "Get Missing Info"

        shown = _menu_actions(mocker)
        dialog._show_list_menu(QPoint())
        shown["Get Missing Info"].trigger()

        assert lookups.asked == [(season.id, [item.key for item in season.items], True)]


class TestHowFarItHasGot:
    def test_in_the_line_under_the_list(self, make_dialog, season, lookups):
        dialog = make_dialog(season)

        lookups.tell(season.id, LookupState(count=14, done=5, found=5, not_found=0))

        assert not dialog._lookup_line.isHidden()
        assert dialog._hint.isHidden()
        assert dialog._lookup_label.text() == "Getting info: 5 of 14"
        assert (dialog._lookup_bar.maximum(), dialog._lookup_bar.value()) == (14, 5)
        assert dialog._lookup_button.text() == "Stop"

    def test_views_and_dates_once_the_rest_is_known(self, make_dialog, season, lookups):
        dialog = make_dialog(season)

        lookups.tell(
            season.id,
            LookupState(count=3, done=1, found=3, not_found=0, is_details=True),
        )

        assert dialog._lookup_label.text() == "Getting views and dates: 1 of 3"

    def test_not_another_lists(self, make_dialog, season, lookups):
        dialog = make_dialog(season)

        lookups.tell("another", LookupState(count=1, done=0, found=0, not_found=0))

        assert dialog._lookup_line.isHidden()
        assert not dialog._hint.isHidden()

    def test_going_on_as_the_window_opens(self, make_dialog, season, lookups):
        lookups.states[season.id] = LookupState(count=2, done=1, found=1, not_found=0)

        dialog = make_dialog(season)

        assert not dialog._lookup_line.isHidden()
        assert dialog._lookup_label.text() == "Getting info: 1 of 2"

    def test_stopped(self, make_dialog, season, lookups):
        dialog = make_dialog(season)
        lookups.tell(season.id, LookupState(count=14, done=5, found=5, not_found=0))

        dialog._lookup_button.click()

        assert lookups.stopped == [season.id]
        assert dialog._lookup_line.isHidden()
        assert dialog._hint.text() == "Stopped"

    def test_turned_away_tried_again(self, make_dialog, season, lookups):
        dialog = make_dialog(season)
        lookups.tell(
            season.id,
            LookupState(count=14, done=5, found=5, not_found=0, refused="YouTube"),
        )

        assert dialog._lookup_refused.text() == (
            "YouTube is blocking requests. Stopped at 5 of 14."
        )
        assert dialog._lookup_bar.isHidden()
        assert dialog._lookup_button.text() == "Try Again"

        dialog._lookup_button.click()

        assert lookups.tried == [season.id]
        assert lookups.stopped == []

    @pytest.mark.parametrize(
        ("found", "not_found", "without_details", "said"),
        [
            (13, 1, 0, "Looked up: 13 · Not found: 1"),
            (5, 0, 0, "Looked up: 5"),
            (5, 0, 2, "Looked up: 5 · No views or dates: 2"),
            (0, 0, 0, "Nothing to look up"),
        ],
    )
    def test_done_what_was_found_said(
        self, make_dialog, season, lookups, found, not_found, without_details, said
    ):
        dialog = make_dialog(season)
        lookups.tell(season.id, LookupState(count=1, done=0, found=0, not_found=0))

        lookups.states.pop(season.id)
        lookups.finished.emit(season.id, found, not_found, without_details)

        assert dialog._lookup_line.isHidden()
        assert dialog._hint.text() == said


class TestWhatALookupLearned:
    def test_kept_with_the_window_cancelled(
        self, make_dialog, registry, season, lookups
    ):
        dialog = make_dialog(season)
        key = season.items[0].key
        registry.update_items(season.id, {key: {"duration_ms": 99}})
        lookups.learned.emit(season.id, {key: {"duration_ms": 99}})

        dialog.reject()

        assert registry.get(season.id).items[0].duration_ms == 99
        assert not dialog.is_edited

    def test_what_is_added_told(self, make_dialog, registry, season, reading):
        told = []
        registry.items_added.connect(lambda *args: told.append(args))
        dialog = make_dialog(season)

        dialog._add_uris([str(_file("new.mkv"))])

        assert _wait_until(lambda: told)
        added = registry.get(season.id).items[-1]
        assert told == [(season.id, [added.key])]


class TestPlaying:
    def test_in_the_cell(self, make_dialog, season):
        dialog = make_dialog(season, cell_at=0)
        dialog._list.setCurrentIndex(dialog._model.index(2, 0))

        dialog._play()

        assert dialog.cell.played == [2]

    def test_its_place_on_the_whole_list(self, make_dialog, season):
        dialog = make_dialog(season, cell_at=0)
        dialog._filter_edit.setText("03")
        dialog._list.setCurrentIndex(dialog._model.index(0, 0))

        dialog._play()

        assert dialog.cell.played == [2]

    def test_in_a_new_cell_without_one(self, make_dialog, season):
        opened = []
        dialog = make_dialog(season, open_in_new_cell=lambda *args: opened.append(args))
        dialog._list.setCurrentIndex(dialog._model.index(1, 0))

        dialog._play()

        assert opened == [(season.id, 1)]

    def test_the_mark_follows_the_cell(self, make_dialog, season):
        dialog = make_dialog(season, cell_at=0)
        model = dialog._model

        dialog.cell.key = season.items[2].key
        dialog.cell.list_place_change.emit("3/3")

        assert model.data(model.index(2, Column.TITLE), Qt.FontRole).bold()


class TestCopyingAndSaving:
    def test_copied_where_they_are(self, make_dialog, season):
        dialog = make_dialog(season)
        _pick(dialog, 0, 1)

        dialog._copy()

        assert QApplication.clipboard().text() == "\n".join(
            [str(_file("01.mkv")), str(_file("02.mkv"))]
        )

    def test_titles_copied(self, make_dialog, season):
        dialog = make_dialog(season)
        _pick(dialog, 0, 1)

        dialog._copy_titles()

        assert QApplication.clipboard().text() == "01.mkv\nCrossing"
        assert dialog._hint.text() == "Copied: 2"

    @pytest.mark.parametrize(
        ("uris", "expected"),
        [
            ((_file("01.mkv"), _file("02.mkv")), "Copy Path"),
            (("http://tv/1",), "Copy Link"),
            ((_file("01.mkv"), "http://tv/1"), "Copy Paths and Links"),
        ],
    )
    def test_copy_says_what_it_copies(self, uris, expected):
        items = [ListItem(uri=uri) for uri in uris]

        assert dialog_module._copy_txt(items) == expected

    def test_the_link_copied_from_where_it_was_read(self, make_dialog, channels):
        dialog = make_dialog(channels)
        button = dialog._source_copy_button

        button.click()

        assert button.isVisibleTo(dialog)
        assert button.toolTip() == "Copy Link"
        assert QApplication.clipboard().text() == "http://tv/get.php"
        assert dialog._hint.text() == "Source copied"

    def test_the_folder_copied_as_its_path(self, make_dialog, season):
        dialog = make_dialog(season)

        dialog._source_copy_button.click()

        assert dialog._source_copy_button.toolTip() == "Copy Path"
        assert QApplication.clipboard().text() == str(ROOT)

    def test_shown_in_its_folder(self, make_dialog, season, mocker):
        dialog = make_dialog(season)
        show = mocker.patch.object(dialog._revealer, "show")

        dialog._show_source_in_folder()

        show.assert_called_once_with(ROOT)

    def test_nothing_to_copy_from_a_list_read_from_nowhere(self, make_dialog, registry):
        media_list = registry.add(
            MediaList(name="Picked", items=(ListItem(uri="http://tv/1"),))
        )
        dialog = make_dialog(media_list)

        assert not dialog._source_copy_button.isVisibleTo(dialog)

    def test_exported_for_other_players(self, make_dialog, season, tmp_path, mocker):
        target = tmp_path / "season.m3u8"
        mocker.patch.object(
            dialog_module.QFileDialog,
            "getSaveFileName",
            return_value=(str(target), "M3U8 (*.m3u8)"),
        )
        dialog = make_dialog(season)

        dialog._export()

        text = target.read_text(encoding="utf-8")
        assert text.startswith("#EXTM3U\n#PLAYLIST:Season\n")
        assert "#EXTINF:60,Crossing\n" in text
        assert dialog._hint.text() == "Exported: season.m3u8"


@pytest.fixture
def channels(registry):
    return registry.add(
        MediaList(
            name="Provider",
            items=(
                ListItem(uri="http://tv/1", title="One", group="News"),
                ListItem(uri="http://tv/2", title="Two", group="Sport"),
                ListItem(uri="http://tv/3", title="Three", group="Sport"),
                ListItem(uri="http://tv/4", title="Four"),
            ),
            source=ListSource(kind=ListSourceKind.URL, location="http://tv/get.php"),
        )
    )


class TestWhileReading:
    @pytest.fixture
    def held(self, reading):
        reading.gate = threading.Event()
        reading.fresh = (ListItem(uri=_file("01.mkv")),)

        yield reading.gate

        reading.gate.set()
        if reading.gate_after is not None:
            reading.gate_after.set()

    def test_how_far_it_has_got_shown(self, make_dialog, season, reading, held):
        reading.progress = (("bytes", 12_300_000, 45_300_000),)
        reading.gate_after = threading.Event()
        dialog = make_dialog(season)

        dialog._refresh()
        held.set()

        assert _wait_until(
            lambda: "12.3 MB of 45.3 MB" in dialog._progress_label.text()
        )
        assert dialog._progress_bar.value() == 27

    def test_nothing_shown_at_first(self, make_dialog, season, held):
        dialog = make_dialog(season)

        dialog._refresh()

        assert not dialog._progress_box.isVisibleTo(dialog)
        assert dialog._source_button.text() == "Refresh"
        assert dialog._add_files_button.isEnabled()
        assert dialog._name_edit.isEnabled()

    def test_shown_once_it_takes_a_while(self, make_dialog, season, held):
        dialog = make_dialog(season)

        dialog._refresh()

        assert _wait_until(lambda: dialog._progress_label.isVisibleTo(dialog))
        assert dialog._progress_label.text() == "Reading…"

    def test_never_shown_where_it_takes_no_while(self, make_dialog, season, reading):
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)
        dialog = make_dialog(season)
        dialog._refresh()

        assert _wait_until(lambda: not dialog._is_reading)

        assert not dialog._reading_timer.isActive()
        assert not dialog._progress_box.isVisibleTo(dialog)
        assert dialog._source_button.text() == "Refresh"
        assert dialog._hint.text() == "Nothing new"

    def test_shown_until_it_is_done(self, make_dialog, season, held):
        dialog = make_dialog(season)

        dialog._refresh()
        _taking_a_while(dialog)

        assert dialog._progress_label.isVisibleTo(dialog)
        assert dialog._source_button.text() == "Stop"

        held.set()

        assert _wait_until(lambda: not dialog._progress_label.isVisibleTo(dialog))
        assert dialog._source_button.text() == "Refresh"

    def test_the_button_in_the_corner_stops_it(
        self, make_dialog, registry, season, held
    ):
        dialog = make_dialog(season)
        dialog._source_button.click()
        assert dialog._is_reading
        _taking_a_while(dialog)

        dialog._source_button.click()

        assert not dialog._is_reading
        assert dialog._hint.text() == "Stopped"

    def test_clicked_again_before_it_says_stop_it_reads_on(
        self, make_dialog, season, held
    ):
        dialog = make_dialog(season)
        dialog._source_button.click()

        dialog._source_button.click()

        assert dialog._is_reading
        assert dialog._reading_timer.isActive()

    def test_what_is_added_to_a_list_from_nowhere_said_in_a_panel_of_its_own(
        self, make_dialog, registry, reading
    ):
        reading.gate_after = None
        gate = threading.Event()
        reading.expand_gate = gate
        media_list = registry.add(MediaList(items=(ListItem(uri="http://x"),)))
        dialog = make_dialog(media_list)

        dialog._add_uris(["http://tv/list.m3u"])
        assert dialog._source_panel.isHidden()
        _taking_a_while(dialog)

        assert not dialog._source_panel.isHidden()
        assert dialog._source_title.text() == "Adding to the list"
        assert dialog._source_label.isHidden()
        assert dialog._source_button.text() == "Stop"

        gate.set()

        assert _wait_until(lambda: not dialog._is_reading)
        assert dialog._source_panel.isHidden()

    def test_the_list_left_as_it_is_meanwhile(
        self, make_dialog, registry, season, held
    ):
        dialog = make_dialog(season)
        dialog._refresh()
        _taking_a_while(dialog)

        _pick(dialog, 0)
        dialog._remove()
        dialog._sort("reverse")
        dialog._name_edit.textEdited.emit("Other")
        dialog._add_uris(["http://tv/1"])

        assert registry.get(season.id) == season
        assert not dialog._add_files_button.isEnabled()
        assert not dialog._name_edit.isEnabled()
        assert not dialog._model.flags(dialog._model.index(0, Column.TITLE)) & (
            Qt.ItemIsEditable | Qt.ItemIsDragEnabled
        )

    def test_nothing_done_to_it_before_it_is_shown_either(
        self, make_dialog, registry, season, held
    ):
        dialog = make_dialog(season)
        dialog._refresh()

        _pick(dialog, 0)
        dialog._remove()
        dialog._sort("reverse")
        dialog._name_edit.textEdited.emit("Other")

        assert registry.get(season.id) == season

    def test_played_from_and_looked_through_meanwhile(self, make_dialog, season, held):
        dialog = make_dialog(season, cell_at=0)
        dialog._refresh()
        dialog._list.setCurrentIndex(dialog._model.index(2, 0))

        dialog._play()
        dialog._filter_edit.setText("Cross")

        assert dialog.cell.played == [2]
        assert _rows(dialog) == ["Crossing"]

    def test_stopped_leaves_the_list_as_it_was(
        self, make_dialog, registry, season, reading, held
    ):
        dialog = make_dialog(season)
        dialog._refresh()

        dialog._stop_reading()
        held.set()
        QTest.qWait(100)

        assert registry.get(season.id) == season
        assert dialog._hint.text() == "Stopped"
        assert dialog._add_files_button.isEnabled()

    def test_stopping_tells_the_reading_to_stop(
        self, make_dialog, season, reading, held
    ):
        dialog = make_dialog(season)
        dialog._refresh()
        assert _wait_until(lambda: reading.told is not None)

        dialog._stop_reading()

        with pytest.raises(ReadingStopped):
            reading.told("items", 10)

    def test_closing_tells_the_reading_to_stop(
        self, make_dialog, season, reading, held
    ):
        dialog = make_dialog(season)
        dialog._refresh()
        assert _wait_until(lambda: reading.told is not None)

        dialog.accept()

        with pytest.raises(ReadingStopped):
            reading.told("items", 10)

    def test_compared_with_the_list_as_it_is_once_read(
        self, make_dialog, registry, season, reading, held
    ):
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)
        dialog = make_dialog(season)
        dialog._refresh()

        # a cell learns how long an item is meanwhile
        registry.update_item(season.id, season.items[2].key, duration_ms=31_000)
        held.set()

        assert _wait_until(lambda: dialog._hint.text() == "Nothing new")
        assert registry.get(season.id).items[2].duration_ms == 31_000


class TestTheGroupLookedAt:
    def test_opened_on_again(self, make_dialog, channels):
        first = make_dialog(channels)
        first._group_combo.setCurrentIndex(2)
        first.accept()

        again = make_dialog(channels)

        assert again._group_combo.currentText() == "Sport (2)"
        assert _rows(again) == ["Two", "Three"]

    def test_all_of_them_where_none_was_picked(self, make_dialog, channels):
        dialog = make_dialog(channels)

        assert dialog._group_combo.currentText() == "All groups (4)"
        assert len(_rows(dialog)) == 4

    def test_one_gone_since_is_all_of_them(self, make_dialog, registry, channels):
        registry.remember_group(channels.id, "Weather")

        dialog = make_dialog(channels)

        assert dialog._group_combo.currentText() == "All groups (4)"

    def test_forgotten_with_another_playlist(self, registry, channels):
        registry.remember_group(channels.id, "Sport")

        registry.load([channels])

        assert registry.remembered_group(channels.id) is None


class TestTheGroupBox:
    def test_no_wider_than_half_the_row(self, make_dialog, registry):
        long_named = registry.add(
            MediaList(
                items=(
                    ListItem(uri="http://tv/1", group="A" * 300),
                    ListItem(uri="http://tv/2", group="B"),
                )
            )
        )
        dialog = make_dialog(long_named)
        dialog.resize(600, 560)
        dialog.show()
        QApplication.processEvents()

        row = dialog._filter_edit.width() + dialog._group_combo.width()

        assert dialog._group_combo.width() <= row // 2 + 6
        assert dialog._filter_edit.width() >= row // 2 - 6


def _lines_drawn(dialog, mocker) -> dict:
    """What the rows say, each on the line of its row it is drawn on: its
    top, from the top of the row, and its height. The text itself is not
    there to look for: the offscreen platform draws none."""

    drawn = {}
    paint_line = dialog_module._paint_line

    def recorded(style, option, rect, color, painter):
        drawn[option.text] = (rect.top() - option.rect.top(), rect.height())
        paint_line(style, option, rect, color, painter)

    mocker.patch.object(dialog_module, "_paint_line", side_effect=recorded)

    dialog.show()
    dialog._list.viewport().grab()

    return drawn


class TestView:
    def test_by_their_titles_at_first(self, make_dialog, season):
        dialog = make_dialog(season)

        assert dialog._view == ListView.TITLES
        assert _rows(dialog) == ["01.mkv", "Crossing", str(Path("Extras/03.mkv"))]
        assert dialog._list.rowHeight(0) == ROW_HEIGHT

    def test_as_the_playlist_has_it(self, make_dialog, season):
        PlaylistSettings().set("playlist/list_view", ListView.LOCATIONS)

        dialog = make_dialog(season)

        assert _rows(dialog) == [str(item.uri) for item in season.items]

    def test_where_each_is_under_its_title(self, make_dialog, season):
        dialog = make_dialog(season)
        model = dialog._model

        dialog._set_view(ListView.TITLES_AND_LOCATIONS)

        index = model.index(1, Column.TITLE)
        assert model.data(index) == "Crossing"
        assert model.data(index, LOCATION_ROLE) == str(season.items[1].uri)
        assert dialog._list.rowHeight(0) == TWO_LINE_ROW_HEIGHT

    def test_back_to_rows_of_one_line(self, make_dialog, season):
        dialog = make_dialog(season)

        dialog._set_view(ListView.TITLES_AND_LOCATIONS)
        dialog._set_view(ListView.TITLES)

        assert dialog._list.rowHeight(0) == ROW_HEIGHT

    def test_the_number_and_length_on_the_title_s_line(
        self, make_dialog, season, mocker
    ):
        dialog = make_dialog(season)
        dialog._set_view(ListView.TITLES_AND_LOCATIONS)

        drawn = _lines_drawn(dialog, mocker)

        title_line = (0, ROW_HEIGHT)
        assert drawn["01.mkv"] == title_line
        assert drawn["1"] == title_line
        assert drawn["1:00"] == title_line
        assert drawn[str(season.items[0].uri)] == (SECOND_LINE_PX, ROW_HEIGHT)

    def test_renamed_on_the_title_s_line(self, make_dialog, season):
        dialog = make_dialog(season)
        dialog._set_view(ListView.TITLES_AND_LOCATIONS)
        dialog.show()
        _pick(dialog, 1)

        dialog._edit_name()
        QApplication.processEvents()

        editor = dialog._list.viewport().findChild(QLineEdit)
        row = dialog._list.visualRect(dialog._model.index(1, Column.TITLE))
        assert editor.text() == "Crossing"
        assert editor.geometry() == QRect(
            row.left(), row.top() + 1, row.width(), ROW_HEIGHT - 2
        )

    def test_renamed_by_its_title_while_where_it_is_is_shown(self, make_dialog, season):
        dialog = make_dialog(season)
        model = dialog._model

        dialog._set_view(ListView.LOCATIONS)

        index = model.index(1, Column.TITLE)
        assert model.data(index) == str(season.items[1].uri)
        assert model.data(index, Qt.EditRole) == "Crossing"

    def test_found_by_where_it_is_once_that_is_shown(self, make_dialog, channels):
        dialog = make_dialog(channels)

        dialog._filter_edit.setText("tv/3")
        assert _rows(dialog) == []

        dialog._set_view(ListView.TITLES_AND_LOCATIONS)
        assert _rows(dialog) == ["Three"]

        dialog._set_view(ListView.LOCATIONS)
        assert _rows(dialog) == ["http://tv/3"]

    def test_found_by_title_whatever_is_shown(self, make_dialog, channels):
        dialog = make_dialog(channels)
        dialog._set_view(ListView.LOCATIONS)

        dialog._filter_edit.setText("three")

        assert _rows(dialog) == ["http://tv/3"]

    @pytest.mark.parametrize(
        ("uris", "offered"),
        [
            (
                [_file("01.mkv")],
                ["Titles", "Titles and Paths", "Paths"],
            ),
            (
                ["http://tv/1"],
                ["Titles", "Titles and Links", "Links"],
            ),
            (
                [_file("01.mkv"), "http://tv/1"],
                ["Titles", "Titles, Paths and Links", "Paths and Links"],
            ),
        ],
    )
    def test_offered_named_after_what_is_on_the_list(
        self, make_dialog, registry, uris, offered
    ):
        media_list = registry.add(
            MediaList(items=tuple(ListItem(uri=uri) for uri in uris))
        )
        dialog = make_dialog(media_list)

        dialog._fill_view_menu()

        actions = dialog._view_menu.actions()
        assert [action.text() for action in actions] == offered
        assert [action.isChecked() for action in actions] == [True, False, False]

    def test_picked_in_its_menu(self, make_dialog, season):
        dialog = make_dialog(season)
        dialog._fill_view_menu()

        dialog._view_menu.actions()[2].trigger()

        assert dialog._view == ListView.LOCATIONS
        assert _rows(dialog)[0] == str(season.items[0].uri)

    def test_kept_for_the_list_while_the_playlist_is_open(
        self, make_dialog, season, channels
    ):
        first = make_dialog(season)
        first._set_view(ListView.TITLES_AND_LOCATIONS)
        first.accept()

        assert make_dialog(season)._view == ListView.TITLES_AND_LOCATIONS
        assert make_dialog(channels)._view == ListView.TITLES

    def test_kept_over_the_playlist_s(self, make_dialog, registry, season):
        PlaylistSettings().set("playlist/list_view", ListView.LOCATIONS)
        registry.remember_view(season.id, ListView.TITLES)

        assert make_dialog(season)._view == ListView.TITLES

    def test_forgotten_with_another_playlist(self, registry, season):
        registry.remember_view(season.id, ListView.LOCATIONS)

        registry.load([season])

        assert registry.remembered_view(season.id) is None


class TestOpeningAsANewList:
    def test_the_picked_played_as_a_list_of_their_own(
        self, make_dialog, registry, channels
    ):
        opened = []
        dialog = make_dialog(channels, open_in_new_cell=lambda *a: opened.append(a))
        _pick(dialog, 1, 3)

        dialog._open_as_new_list()

        ((list_id, place),) = opened
        made = registry.get(list_id)
        assert list_id != channels.id
        assert place == 0
        assert [item.title for item in made.items] == ["Two", "Four"]
        assert made.name == "Provider"
        assert made.source is None
        assert dialog._hint.text() == "Opened as a new list: 2"

    def test_named_after_their_group(self, make_dialog, registry, channels):
        opened = []
        dialog = make_dialog(channels, open_in_new_cell=lambda *a: opened.append(a))
        _pick(dialog, 1, 2)

        dialog._open_as_new_list()

        assert registry.get(opened[0][0]).name == "Sport"

    def test_items_of_their_own(self, make_dialog, registry, channels):
        opened = []
        dialog = make_dialog(channels, open_in_new_cell=lambda *a: opened.append(a))
        _pick(dialog, 1, 2)

        dialog._open_as_new_list()

        made = registry.get(opened[0][0])
        assert {item.key for item in made.items}.isdisjoint(
            item.key for item in channels.items
        )
        assert registry.get(channels.id) == channels


class TestWhetherAnythingWasDone:
    def test_nothing_at_first(self, make_dialog, season):
        assert not make_dialog(season).is_edited

    def test_renamed(self, make_dialog, season):
        dialog = make_dialog(season)

        dialog._name_edit.textEdited.emit("Other")

        assert dialog.is_edited

    def test_an_item_renamed(self, make_dialog, season):
        dialog = make_dialog(season)

        dialog._rename(season.items[0].key, "Pilot")

        assert dialog.is_edited

    def test_an_item_taken_off(self, make_dialog, season):
        dialog = make_dialog(season)
        _pick(dialog, 0)

        dialog._remove()

        assert dialog.is_edited

    def test_not_by_a_cell_learning_how_long_an_item_is(
        self, make_dialog, registry, season
    ):
        dialog = make_dialog(season)

        registry.update_item(season.id, season.items[2].key, duration_ms=31_000)

        assert not dialog.is_edited

    def test_not_by_reading_it_again_with_nothing_new(
        self, make_dialog, season, reading
    ):
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)
        dialog = make_dialog(season)

        dialog._refresh()

        assert _wait_until(lambda: dialog._hint.text() == "Nothing new")
        assert not dialog.is_edited


class TestBesideThePlayer:
    def test_closed_once_the_cell_is_put_on_another_list(self, make_dialog, season):
        dialog = make_dialog(season, cell_at=0)
        dialog.show()

        dialog.cell.video_params.list_id = None
        dialog.cell.list_place_change.emit("")

        assert dialog.isHidden()
        assert dialog.result() == dialog.Accepted

    def test_closed_with_the_playlist(self, make_dialog, registry, season):
        dialog = make_dialog(season, cell_at=0)
        dialog.show()

        registry.clear()

        assert dialog.isHidden()

    def test_cells_opened_since_told(self, make_dialog, season, registry):
        later = []
        dialog = make_dialog(season, cell_at=0, cells=later)
        assert dialog._shared_label.isHidden()

        later.append(_Cell(registry, season.id, season.items[1].key))
        dialog._show_shared()

        assert "Cell 2 also plays this list" in dialog._shared_label.text()


DAY = 86400
NOW = time.time()

PLAYLIST = ListSource(
    kind=ListSourceKind.URL, location="https://www.youtube.com/playlist?list=PL1"
)


def _picture(video_id):
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


def _video(video_id, views, days_ago, **fields):
    return ListItem(
        uri=f"https://www.youtube.com/watch?v={video_id}",
        title=f"Video {video_id}",
        duration_ms=61_000,
        details=ItemDetails(
            channel="Workshop",
            view_count=views,
            published=None if days_ago is None else int(NOW - days_ago * DAY),
            thumbnail=_picture(video_id),
        ),
        **fields,
    )


def _jpeg() -> bytes:
    from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
    from PyQt5.QtGui import QImage

    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(Qt.darkCyan)

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "JPG")

    return bytes(data)


@pytest.fixture
def videos(registry):
    return registry.add(
        MediaList(
            name="Lathe",
            items=(
                _video("a", 19_000, 3 * 365),
                _video("b", 92_000, 30),
                _video("c", None, None),
                ListItem(uri=Path("/videos/mine.mp4"), is_added=True),
            ),
            source=PLAYLIST,
        )
    )


def _view_titles(dialog):
    dialog._fill_view_menu()
    return [action.text() for action in dialog._view_menu.actions()]


def _sort_titles(dialog):
    dialog._fill_sort_menu()
    return [
        action.text()
        for action in dialog._sort_menu.actions()
        if not action.isSeparator()
    ]


class TestThumbnails:
    def test_a_list_with_pictures_opens_by_them(self, make_dialog, videos):
        dialog = make_dialog(videos)

        assert dialog._view == ListView.THUMBNAILS
        assert dialog._list.rowHeight(0) == THUMBNAIL_ROW_HEIGHT

    def test_not_where_the_playlist_says_not(self, make_dialog, videos):
        PlaylistSettings().set("playlist/list_thumbnails", False)
        PlaylistSettings().set("playlist/list_view", ListView.LOCATIONS)

        dialog = make_dialog(videos)

        assert dialog._view == ListView.LOCATIONS
        assert "Thumbnails" in _view_titles(dialog)

    def test_as_it_was_looked_at_last(self, make_dialog, registry, videos):
        registry.remember_view(videos.id, ListView.TITLES)

        assert make_dialog(videos)._view == ListView.TITLES

    def test_a_list_without_any_is_not_offered_them(self, make_dialog, season):
        dialog = make_dialog(season)

        assert dialog._view == ListView.TITLES
        assert "Thumbnails" not in _view_titles(dialog)

    def test_nor_opens_by_them_though_it_was_looked_at_so(
        self, make_dialog, registry, season
    ):
        registry.remember_view(season.id, ListView.THUMBNAILS)

        assert make_dialog(season)._view == ListView.TITLES

    def test_what_the_site_says_under_each_title(self, make_dialog, videos):
        dialog = make_dialog(videos)
        model = dialog._model

        def under(row):
            return model.data(model.index(row, Column.TITLE), DETAILS_ROLE)

        assert under(0) == "Workshop · 19K views · 3 years ago"
        assert under(1) == "Workshop · 92K views · 1 month ago"
        assert under(2) == "Workshop"
        assert under(3) is None

    def test_on_the_second_line_and_a_file_its_path(self, make_dialog, videos, mocker):
        dialog = make_dialog(videos)
        dialog.resize(900, 560)

        drawn = _lines_drawn(dialog, mocker)

        title_top, _ = drawn["Video a"]
        assert drawn["Workshop · 19K views · 3 years ago"][0] == (
            title_top + SECOND_LINE_PX
        )
        assert drawn[str(Path("/videos/mine.mp4"))][0] == title_top + SECOND_LINE_PX
        # the length on the title's line, the number left in the middle
        assert drawn["1:01"][0] == title_top

    def test_the_lines_after_the_picture(self, make_dialog, videos, mocker):
        dialog = make_dialog(videos)
        lefts = {}
        paint_line = dialog_module._paint_line

        def recorded(style, option, rect, color, painter):
            lefts[option.text] = rect.left()
            paint_line(style, option, rect, color, painter)

        mocker.patch.object(dialog_module, "_paint_line", side_effect=recorded)
        dialog.show()
        dialog._list.viewport().grab()

        title_left = dialog._list.columnViewportPosition(Column.TITLE)
        assert lefts["Video a"] >= title_left + THUMBNAIL_SIZE.width()

    def test_the_pictures_fetched_as_their_rows_show(
        self, make_dialog, reading, videos
    ):
        reading.pictures = {_picture("a"): _jpeg(), _picture("b"): _jpeg()}
        dialog = make_dialog(videos)
        dialog.resize(600, 560)
        dialog.show()

        loader = dialog._thumbnails

        def came():
            dialog._list.viewport().grab()
            return loader.picture(_picture("a")) is not None and loader.is_missing(
                _picture("c")
            )

        assert _wait_until(came)
        assert sorted(reading.pictures_asked) == [
            _picture("a"),
            _picture("b"),
            _picture("c"),
        ]

    def test_only_the_rows_shown(self, make_dialog, reading, registry):
        reading.pictures = {}
        many = registry.add(
            MediaList(
                items=tuple(_video(f"v{n}", 1, 1) for n in range(200)), source=PLAYLIST
            )
        )
        dialog = make_dialog(many)
        dialog.resize(600, 560)
        dialog.show()

        dialog._list.viewport().grab()
        _wait_until(lambda: len(reading.pictures_asked) > 0)
        QTest.qWait(50)

        assert 0 < len(reading.pictures_asked) < 20

    def test_none_fetched_where_there_is_no_fetching(self, make_dialog, videos):
        dialog = make_dialog(videos)
        dialog.show()

        dialog._list.viewport().grab()

        assert dialog._thumbnails is None

    def test_found_by_the_channel(self, make_dialog, videos):
        dialog = make_dialog(videos)

        dialog._filter_edit.setText("worksh")
        dialog._apply_filter()

        assert _rows(dialog) == ["Video a", "Video b", "Video c"]

    def test_but_not_where_only_titles_are_shown(self, make_dialog, videos):
        dialog = make_dialog(videos)
        dialog._set_view(ListView.TITLES)

        dialog._filter_edit.setText("worksh")
        dialog._apply_filter()

        assert _rows(dialog) == []

    def test_renamed_on_the_title_s_line_after_the_picture(self, make_dialog, videos):
        dialog = make_dialog(videos)
        dialog.resize(600, 560)
        dialog.show()
        _pick(dialog, 0)

        dialog._edit_name()
        QApplication.processEvents()

        editor = dialog._list.findChild(QLineEdit)
        row = dialog._list.visualRect(dialog._model.index(0, Column.TITLE))
        assert editor.geometry().left() > row.left() + THUMBNAIL_SIZE.width()
        # on the first of the two lines, in the middle of the row
        lines_top = row.top() + (THUMBNAIL_ROW_HEIGHT - TWO_LINE_ROW_HEIGHT) // 2
        assert editor.geometry().top() == lines_top + 1
        assert editor.geometry().height() == ROW_HEIGHT - 2


class TestSortedBySite:
    def test_offered_where_the_list_says_it(self, make_dialog, videos, season):
        assert _sort_titles(make_dialog(videos))[:4] == [
            "By Name",
            "By Length",
            "By Views",
            "By Date Published",
        ]
        assert "By Views" not in _sort_titles(make_dialog(season))

    def test_by_views_most_first(self, make_dialog, registry, videos):
        dialog = make_dialog(videos)

        dialog._sort("views")

        assert _titles(registry, videos) == [
            "Video b",
            "Video a",
            "Video c",
            "mine.mp4",
        ]

    def test_by_date_newest_first(self, make_dialog, registry, videos):
        dialog = make_dialog(videos)

        dialog._sort("published")

        assert _titles(registry, videos)[:2] == ["Video b", "Video a"]

    def test_source_order_for_a_list_from_somewhere(
        self, make_dialog, registry, videos
    ):
        assert "Source Order" in _sort_titles(make_dialog(videos))

        made = registry.add(MediaList(items=videos.items))
        assert "Source Order" not in _sort_titles(make_dialog(made))

    def test_source_order_reads_it_again_for_its_order(
        self, make_dialog, reading, registry, videos
    ):
        dialog = make_dialog(videos)
        dialog._sort("views")
        reading.fresh = tuple(_video(video_id, 5, 1) for video_id in ("a", "b", "c"))

        dialog._put_in_source_order()

        assert _wait_until(lambda: not dialog._is_reading)
        assert _titles(registry, videos) == [
            "Video a",
            "Video b",
            "Video c",
            "mine.mp4",
        ]
        assert dialog._hint.text() == "In the source's order"


class TestWhatASiteSays:
    @pytest.fixture(autouse=True)
    def _english(self):
        from PyQt5.QtCore import QLocale

        kept = QLocale()
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        yield
        QLocale.setDefault(kept)

    @pytest.mark.parametrize(
        ("count", "said"),
        [
            (999, "999"),
            (1000, "1K"),
            (1299, "1.2K"),
            (12_345, "12K"),
            (412_999, "412K"),
            (1_299_999, "1.2M"),
            (2_000_000_000, "2B"),
        ],
    )
    def test_a_count_cut_down_as_a_site_says_it(self, count, said):
        assert short_count_txt(count) == said

    def test_views(self):
        assert views_txt(0) == "No views"
        assert views_txt(1) == "1 view"
        assert views_txt(19_000) == "19K views"

    @pytest.mark.parametrize(
        ("seconds", "said"),
        [
            (30, "1 minute ago"),
            (5 * 60, "5 minutes ago"),
            (3600, "1 hour ago"),
            (5 * 3600, "5 hours ago"),
            (DAY, "1 day ago"),
            (6 * DAY, "6 days ago"),
            (7 * DAY, "1 week ago"),
            (29 * DAY, "4 weeks ago"),
            (30 * DAY, "1 month ago"),
            (334 * DAY, "11 months ago"),
            (365 * DAY, "1 year ago"),
            (16 * 365 * DAY, "16 years ago"),
        ],
    )
    def test_how_long_ago(self, seconds, said):
        assert published_txt(1_000_000_000, now=1_000_000_000 + seconds) == said


@pytest.fixture
def many_videos(registry):
    return registry.add(
        MediaList(
            items=tuple(_video(f"v{n}", 1, 1) for n in range(200)), source=PLAYLIST
        )
    )


def _pictures_painted(dialog, mocker) -> list:
    """Each picture drawn in a row, as it was drawn: whether it had come."""

    painted = []
    delegate = dialog._list.itemDelegate()
    paint = delegate._paint_thumbnail

    def recorded(painter, rect, index, palette):
        url = index.data(dialog_module.THUMBNAIL_ROLE)
        painted.append((url, dialog._thumbnails.picture(url) is not None))
        paint(painter, rect, index, palette)

    mocker.patch.object(delegate, "_paint_thumbnail", side_effect=recorded)

    return painted


def _in_sight(dialog) -> list:
    table = dialog._list
    first = table.rowAt(0)
    last = table.rowAt(table.viewport().height() - 1)

    return [_picture(f"v{row}") for row in range(first, last + 1)]


def _near(dialog) -> list:
    """The rows in sight, and the views of rows below and above them."""

    table = dialog._list
    first = table.rowAt(0)
    last = table.rowAt(table.viewport().height() - 1)
    ahead = (last - first + 1) * dialog_module.THUMBNAIL_AHEAD_VIEWS
    count = dialog._model.rowCount()

    rows = range(max(0, first - ahead), min(count, last + 1 + ahead))

    return [_picture(f"v{row}") for row in rows]


def _scrolled_to(dialog, row):
    dialog._list.scrollTo(
        dialog._model.index(row, Column.TITLE), QAbstractItemView.PositionAtTop
    )


@pytest.fixture
def quick_settle(mocker):
    mocker.patch.object(dialog_module, "THUMBNAIL_SETTLE_MS", 300)
    mocker.patch.object(dialog_module, "THUMBNAIL_CHECK_MS", 50)


class TestPicturesAsTheyCome:
    def test_drawn_once_come_with_nothing_else_drawing_the_list_again(
        self, make_dialog, reading, videos, mocker
    ):
        reading.pictures = {_picture("a"): _jpeg()}
        dialog = make_dialog(videos)
        dialog.resize(600, 560)
        painted = _pictures_painted(dialog, mocker)

        dialog.show()

        assert _wait_until(lambda: (_picture("a"), True) in painted)

    def test_the_rows_near_at_first_fetched_at_once_those_in_sight_first(
        self, make_dialog, reading, many_videos, mocker
    ):
        reading.pictures = {}
        dialog = make_dialog(many_videos)
        dialog.resize(600, 560)
        fetched = mocker.spy(dialog._thumbnails, "fetch")

        dialog.show()

        assert _wait_until(lambda: reading.pictures_asked, timeout=0.5)
        QTest.qWait(50)

        in_sight = _in_sight(dialog)
        asked = [call.args[0] for call in fetched.call_args_list]
        assert set(asked) == set(_near(dialog))
        assert asked[: len(in_sight)] == in_sight
        # the views of rows below, none above the first
        assert len(asked) == len(in_sight) * (1 + dialog_module.THUMBNAIL_AHEAD_VIEWS)

    def test_the_next_view_is_there_before_it_is_scrolled_to(
        self, make_dialog, reading, many_videos
    ):
        reading.pictures = {
            _picture(f"v{row}"): _jpeg() for row in range(len(many_videos.items))
        }
        dialog = make_dialog(many_videos)
        dialog.resize(600, 560)
        dialog.show()
        loader = dialog._thumbnails

        def near_came():
            return all(loader.picture(url) is not None for url in _near(dialog))

        assert _wait_until(near_came)

        page = len(_in_sight(dialog))
        _scrolled_to(dialog, page)
        QApplication.processEvents()

        assert all(loader.picture(url) is not None for url in _in_sight(dialog))

    def test_rows_scrolled_past_not_fetched(
        self, make_dialog, reading, many_videos, quick_settle
    ):
        reading.pictures = {}
        dialog = make_dialog(many_videos)
        dialog.resize(600, 560)
        dialog.show()
        _wait_until(lambda: reading.pictures_asked)
        QTest.qWait(50)
        at_first = set(reading.pictures_asked)

        dialog._list.scrollToBottom()
        QTest.qWait(100)
        went_by = set(_near(dialog))

        _scrolled_to(dialog, 100)
        QTest.qWait(100)
        stayed = set(_near(dialog))

        # not yet: near for less than a while
        assert set(reading.pictures_asked) == at_first

        assert _wait_until(lambda: stayed <= set(reading.pictures_asked))
        assert not went_by & set(reading.pictures_asked)

    def test_none_fetched_while_scrolling_on(
        self, make_dialog, reading, many_videos, quick_settle
    ):
        reading.pictures = {}
        dialog = make_dialog(many_videos)
        dialog.resize(600, 560)
        dialog.show()
        _wait_until(lambda: reading.pictures_asked)
        QTest.qWait(50)
        at_first = set(reading.pictures_asked)

        # further each time than the rows near reach, and quicker than the
        # while it takes
        for row in (50, 100, 150):
            _scrolled_to(dialog, row)
            QTest.qWait(100)

        assert set(reading.pictures_asked) == at_first

    def test_waiting_ones_of_rows_scrolled_away_from_let_go(
        self, make_dialog, reading, many_videos, quick_settle
    ):
        reading.pictures = {}
        reading.picture_gate = threading.Event()
        dialog = make_dialog(many_videos)
        dialog.resize(600, 560)
        dialog.show()

        # as many fetched as there are at once, the rest waiting their turn
        _wait_until(lambda: len(reading.pictures_asked) >= 4)
        QTest.qWait(50)
        first_near = _near(dialog)
        started = set(reading.pictures_asked)

        _scrolled_to(dialog, 150)
        QTest.qWait(500)
        reading.picture_gate.set()

        assert _wait_until(lambda: set(_near(dialog)) <= set(reading.pictures_asked))
        assert not (set(first_near) - started) & set(reading.pictures_asked)

    def test_switched_to_them_the_rows_near_at_once(
        self, make_dialog, reading, registry, many_videos
    ):
        registry.remember_view(many_videos.id, ListView.TITLES)
        reading.pictures = {}
        dialog = make_dialog(many_videos)
        dialog.resize(600, 560)
        dialog.show()
        _scrolled_to(dialog, 100)
        QApplication.processEvents()

        dialog._set_view(ListView.THUMBNAILS)

        assert _wait_until(lambda: reading.pictures_asked, timeout=0.5)
        QTest.qWait(50)
        assert set(reading.pictures_asked) == set(_near(dialog))


class TestSubfolders:
    @pytest.fixture
    def with_subfolders(self, registry):
        return registry.add(
            MediaList(
                name="Season",
                items=(
                    ListItem(uri=_file("01.mkv")),
                    ListItem(uri=_file("Extras/02.mkv")),
                ),
                source=ListSource(
                    kind=ListSourceKind.FOLDER, location=ROOT, is_recursive=True
                ),
            )
        )

    def test_offered_for_a_folder_ticked_as_it_is_read(
        self, make_dialog, season, with_subfolders, mocker
    ):
        shown = _menu_actions(mocker)

        make_dialog(season)._show_source_menu(QPoint())
        assert not shown["Include Subfolders"].isChecked()

        make_dialog(with_subfolders)._show_source_menu(QPoint())
        assert shown["Include Subfolders"].isChecked()

    @pytest.mark.parametrize(
        "source",
        [
            ListSource(kind=ListSourceKind.URL, location="http://tv/l"),
            ListSource(kind=ListSourceKind.FILE, location=ROOT / "tv.m3u"),
        ],
    )
    def test_not_for_a_list_file_or_a_link(self, make_dialog, registry, source, mocker):
        media_list = registry.add(MediaList(source=source))
        names = _menu_names(mocker)

        make_dialog(media_list)._show_source_menu(QPoint())

        assert "Copy Path" in names or "Copy Link" in names
        assert "Include Subfolders" not in names

    def test_turned_on_reads_their_files_in(
        self, make_dialog, registry, season, reading, mocker
    ):
        reading.fresh = (
            *(ListItem(uri=item.uri) for item in season.items),
            ListItem(uri=_file("Extras/04.mkv")),
        )
        dialog = make_dialog(season)
        shown = _menu_actions(mocker)
        dialog._show_source_menu(QPoint())

        shown["Include Subfolders"].trigger()

        assert _wait_until(lambda: dialog._hint.text() == "New: 1 · Gone: 0")
        assert reading.read_from[-1].is_recursive
        media_list = registry.get(season.id)
        assert media_list.source.is_recursive
        assert media_list.items[-1].uri == _file("Extras/04.mkv")
        assert dialog._source_title.text() == "Source: Folder, with subfolders"

    def test_turned_off_takes_their_files_off(
        self, make_dialog, registry, with_subfolders, reading, mocker
    ):
        reading.fresh = (ListItem(uri=_file("01.mkv")),)
        dialog = make_dialog(with_subfolders)
        shown = _menu_actions(mocker)
        dialog._show_source_menu(QPoint())

        shown["Include Subfolders"].trigger()

        assert _wait_until(lambda: dialog._hint.text() == "New: 0 · Gone: 1")
        media_list = registry.get(with_subfolders.id)
        assert not media_list.source.is_recursive
        assert [item.uri for item in media_list.items] == [_file("01.mkv")]
        assert dialog._source_title.text() == "Source: Folder"

    def test_left_as_it_was_where_the_folder_cannot_be_read(
        self, make_dialog, registry, season, reading
    ):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)

        dialog._toggle_subfolders()

        assert _wait_until(lambda: not dialog._error_box.isHidden())
        assert registry.get(season.id) == season
        assert dialog._source_title.text() == "Source: Folder"

    def test_tried_again_with_them(self, make_dialog, registry, season, reading):
        reading.fresh = FileNotFoundError("Folder not found")
        dialog = make_dialog(season)
        dialog._toggle_subfolders()
        assert _wait_until(lambda: not dialog._error_box.isHidden())
        reading.fresh = tuple(ListItem(uri=item.uri) for item in season.items)

        dialog._error_again_button.click()

        assert _wait_until(lambda: registry.get(season.id).source.is_recursive)
        assert reading.read_from[-1].is_recursive

    def test_not_while_it_is_read_again(self, make_dialog, season, reading, mocker):
        reading.gate = threading.Event()
        dialog = make_dialog(season)
        dialog._refresh()
        shown = _menu_actions(mocker)

        dialog._show_source_menu(QPoint())

        assert not shown["Include Subfolders"].isEnabled()
        reading.gate.set()
        assert _wait_until(lambda: not dialog._is_reading)
