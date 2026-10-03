"""Every bookmark the playlist keeps, by the file it is in: to see what is
there, to open a file and have its bookmarks back, and to clear away those
nothing can reach any more -- of files gone, and of cells closed.

Removals are made as they go, as they are in the bookmarks manager, and
Cancel puts back what was removed.
"""

import contextlib
from concurrent.futures import ThreadPoolExecutor
from enum import Enum, IntEnum, auto
from pathlib import Path

from pydantic import ValidationError
from PyQt5.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
)

from gridplayer.dialogs.bookmarks import (
    LOOP_EDGE_COLOR_DARK,
    LOOP_EDGE_COLOR_LIGHT,
    ROW_HEIGHT,
    STATUS_MS,
    TIME_FADE,
    mixed_color,
    paint_empty_txt,
    with_key_txt,
)
from gridplayer.models.video import Video
from gridplayer.utils.bookmarks import (
    bookmarks_txt,
    default_bookmark_name,
    file_key,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.time_txt import ms_time_txt
from gridplayer.widgets.bookmark_colors import LIST_ICON_SHARE, bookmark_icon
from gridplayer.widgets.custom_menu import CustomMenu

# what nothing can reach any more, in the orange of a warning, darker where
# the list is light for the words to read
WARNING_COLOR_LIGHT = "#b45309"
WARNING_COLOR_DARK = "#f0a43a"

DIALOG_SIZE = QSize(660, 560)
DIALOG_MIN_SIZE = QSize(520, 380)

MIN_LENGTH_MS = 60_000

STATUS_COLUMN_PX = 170
ICON_PX = 16
SWATCH_PX = 12

# a bookmark's marker between its time and its name, as the manager has it
MARKER_PX = 12
MARKER_GAP_PX = 6

# telling whether a file is still there can take a while on a network drive
# that is gone, so it is asked off to the side, a few at a time
FILE_CHECKS_AT_ONCE = 4

# every row carries its file's entry; a bookmark's row the bookmark, as it
# is shown, and its time
ENTRY_ROLE = Qt.UserRole
BOOKMARK_ROLE = Qt.UserRole + 1
TIME_ROLE = Qt.UserRole + 2


class Column(IntEnum):
    FILE = 0
    CELL = 1
    COUNT = 2
    STATUS = 3


class Status(Enum):
    OPEN = auto()
    PLAYING = auto()
    NOT_PLAYING = auto()
    NOT_OPEN = auto()
    STREAM = auto()
    MISSING = auto()
    NO_FOLDER = auto()
    CLOSED_CELL = auto()


# those nothing can reach any more
UNREACHABLE = frozenset({Status.MISSING, Status.NO_FOLDER, Status.CLOSED_CELL})

# those a file opened again brings back
OPENABLE = frozenset({Status.NOT_OPEN, Status.STREAM, Status.CLOSED_CELL})


class Found(Enum):
    """What looking for a file found."""

    FILE = auto()
    # its folder, but not the file
    NO_FILE = auto()
    # not even its folder: gone, or on a drive not connected
    NO_FOLDER = auto()


def _entry_key(entry):
    return file_key(entry.uri), entry.cell


def _file_txt(uri) -> str:
    if isinstance(uri, Path):
        return uri.name

    return uri.split("://", 1)[-1]


def _swatch(color: str, rim: QColor) -> QIcon:
    """A cell's colour, rimmed: white, the colour a cell has unless it is
    given one, is no colour at all on a light list."""

    pixmap = QPixmap(SWATCH_PX, SWATCH_PX)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(rim)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(1.5, 1.5, SWATCH_PX - 3, SWATCH_PX - 3), 3, 3)
    painter.end()

    return QIcon(pixmap)


def _look_for(path: Path) -> Found:
    try:
        if path.exists():
            return Found.FILE

        if path.parent.exists():
            return Found.NO_FILE
    except (OSError, ValueError):
        pass

    # nothing to tell a folder gone from one out of reach for now
    return Found.NO_FOLDER


class _FileChecks(QObject):
    """Whether files are still there, told one by one as each is known."""

    checked = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pool = ThreadPoolExecutor(max_workers=FILE_CHECKS_AT_ONCE)

    def check(self, key: str, path: Path):
        future = self._pool.submit(_look_for, path)
        future.add_done_callback(lambda done: self._tell(key, done))

    def stop(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _tell(self, key, done):
        if done.cancelled():
            return

        # (the dialog may be gone by the time a slow one is known)
        with contextlib.suppress(RuntimeError):
            self.checked.emit(key, done.result())


class _BookmarkRowDelegate(QStyledItemDelegate):
    """A bookmark under its file, as the manager lists it: the time stepped
    back, then its marker in its colour, then the name, or the number it goes
    by without one."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.time_color = QColor()

        # a bookmark's marker in its colour, by the colour
        self._marker_icons = {}

    def _marker_icon(self, color, rim) -> QIcon:
        key = (color, rim.rgba())

        if key not in self._marker_icons:
            self._marker_icons[key] = bookmark_icon([color], rim, LIST_ICON_SHARE)

        return self._marker_icons[key]

    def paint(self, painter, option, index):
        bookmark = index.data(BOOKMARK_ROLE)

        if bookmark is None:
            super().paint(painter, option, index)
            return

        self.initStyleOption(option, index)
        option.text = ""

        style = option.widget.style()
        style.drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget)

        palette = option.palette
        is_selected = bool(option.state & QStyle.State_Selected)
        selected_color = palette.color(QPalette.HighlightedText)

        time_txt, name, is_named, color = bookmark

        rect = option.rect.adjusted(4, 0, -8, 0)
        time_rect = QRect(rect)
        time_rect.setWidth(option.fontMetrics.horizontalAdvance(time_txt) + 16)

        marker_rect = QRect(
            time_rect.right(),
            rect.top() + (rect.height() - MARKER_PX) // 2,
            MARKER_PX,
            MARKER_PX,
        )

        name_rect = QRect(rect)
        name_rect.setLeft(marker_rect.right() + MARKER_GAP_PX)

        painter.save()

        painter.setPen(selected_color if is_selected else self.time_color)
        painter.drawText(time_rect, Qt.AlignVCenter, time_txt)

        self._marker_icon(color, palette.color(QPalette.Text)).paint(
            painter, marker_rect
        )

        font = QFont(option.font)
        font.setItalic(not is_named)
        painter.setFont(font)

        if is_selected:
            painter.setPen(selected_color)
        elif is_named:
            painter.setPen(palette.color(QPalette.Text))
        else:
            painter.setPen(palette.color(QPalette.PlaceholderText))

        painter.drawText(
            name_rect,
            Qt.AlignVCenter,
            option.fontMetrics.elidedText(name, Qt.ElideRight, name_rect.width()),
        )

        painter.restore()


class EntryList(QTreeView):
    """The files, a row each, each opening on its bookmarks."""

    copy_requested = pyqtSignal()
    remove_requested = pyqtSignal()

    # for the picked rows, and for the list itself, from the space under them
    menu_requested = pyqtSignal(QPoint)
    list_menu_requested = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setIconSize(QSize(ICON_PX, ICON_PX))
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.setStyleSheet(
            f"""
            QTreeView::item {{
                height: {ROW_HEIGHT}px;
                padding-left: 4px;
                padding-right: 8px;
            }}
            """
        )

        self.empty_txt = ("", "")

    def keyPressEvent(self, event):
        # (the view's own copies the current cell's text)
        if event.matches(QKeySequence.Copy):
            self.copy_requested.emit()
            event.accept()
            return

        if event.key() == Qt.Key_Delete:
            self.remove_requested.emit()
            event.accept()
            return

        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        # from the keyboard, for the current row, under it
        if event.reason() == QContextMenuEvent.Keyboard:
            index = self.currentIndex()
            pos = self.visualRect(index).bottomLeft() if index.isValid() else QPoint()
        else:
            index = self.indexAt(event.pos())
            pos = event.pos()

        global_pos = self.viewport().mapToGlobal(pos)

        if index.isValid():
            self.menu_requested.emit(global_pos)
        else:
            self.list_menu_requested.emit(global_pos)

        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.model() is None or self.model().rowCount():
            return

        painter = QPainter(self.viewport())
        paint_empty_txt(self, painter, *self.empty_txt)
        painter.end()


class PlaylistBookmarksDialog(QDialog):
    def __init__(self, registry, cells, open_files, parent=None):
        """The registry's bookmarks; the cells open, first to last in the
        grid, as a function to ask; and how to open files in new cells, which
        says which of them it did."""

        self._is_set_up = False

        super().__init__(parent)

        self._registry = registry
        self._cells = cells
        self._open_files = open_files

        # what was there before a removal, by file and cell, for Cancel
        self._originals = {}

        # what was found of each file not open, by its key, once known
        self._found: dict[str, Found] = {}
        self._checks = _FileChecks(self)
        self._checks.checked.connect(self._on_checked)

        self._statuses = {}
        self._cell_numbers = {}
        self._entries = {}

        self.setWindowTitle(
            translate("Dialog - Playlist bookmarks", "Bookmarks in Playlist")
        )
        self.setMinimumSize(DIALOG_MIN_SIZE)
        self.resize(DIALOG_SIZE)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(STATUS_MS)
        self._status_timer.timeout.connect(self._show_hint)

        # several changes at once are shown once
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(0)
        self._reload_timer.timeout.connect(self._reload)

        self._ui_setup()
        self._ui_connect()

        self._update_look()
        self._reload()

        self._list.setFocus()

        self._is_set_up = True

    def _ui_setup(self):
        self._mode_icon = QLabel()
        self._mode_icon.setAlignment(Qt.AlignTop)

        self._mode = QLabel()
        self._mode.setWordWrap(True)

        mode = QHBoxLayout()
        mode.setSpacing(8)
        mode.addWidget(self._mode_icon)
        mode.addWidget(self._mode, 1)

        self._model = QStandardItemModel(self)

        self._list = EntryList()
        self._list.setModel(self._model)
        self._delegate = _BookmarkRowDelegate(self._list)
        self._list.setItemDelegate(self._delegate)
        self._list.empty_txt = (
            translate("Dialog - Playlist bookmarks", "No bookmarks in this playlist"),
            translate(
                "Dialog - Playlist bookmarks",
                "Bookmarks added to the videos are kept here, by the file they are in.",
            ),
        )

        # the counts, or what was just done, wrapped onto a line more if long
        self._hint = QLabel()
        self._hint.setWordWrap(True)

        self._open_button = self._button(
            "add-files",
            translate("Dialog - Playlist bookmarks", "Open"),
            translate(
                "Dialog - Playlist bookmarks",
                "Open the file in a new cell, with its bookmarks",
            ),
        )
        self._copy_button = self._button(
            "copy",
            translate("Dialog - Playlist bookmarks", "Copy"),
            translate(
                "Dialog - Playlist bookmarks",
                "Copy the selected bookmarks as timestamps, one to a line,"
                " like 1:23 Intro; those of several files under each file's name",
            ),
        )
        self._remove_button = self._button(
            "bookmark-remove", translate("Dialog - Playlist bookmarks", "Remove")
        )
        self._unreachable_button = self._button(
            "bookmark-remove-all",
            translate("Dialog - Playlist bookmarks", "Remove Unreachable"),
            translate(
                "Dialog - Playlist bookmarks",
                "Remove the bookmarks of files that are gone, and of cells"
                " that are closed",
            ),
        )

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(self._open_button)
        tools.addWidget(self._copy_button)
        tools.addStretch(1)
        tools.addWidget(self._remove_button)

        bottom = QHBoxLayout()
        bottom.addWidget(self._unreachable_button)
        bottom.addStretch(1)
        bottom.addWidget(self._buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)
        root.addLayout(mode)
        root.addWidget(self._list, 1)
        root.addSpacing(-4)
        root.addWidget(self._hint)
        root.addLayout(tools)
        root.addSpacing(4)
        root.addLayout(bottom)

    def _button(self, icon, text, tooltip=None) -> QPushButton:
        button = QPushButton(QIcon.fromTheme(icon), text)
        button.setIconSize(QSize(ICON_PX, ICON_PX))
        button.setAutoDefault(False)

        if tooltip:
            button.setToolTip(tooltip)

        return button

    def _ui_connect(self):
        self._registry.changed.connect(self._reload_timer.start)
        self._registry.replaced.connect(self._forget_originals)

        self._list.selectionModel().selectionChanged.connect(self._update_buttons)
        self._list.copy_requested.connect(self._copy)
        self._list.remove_requested.connect(self._remove)
        self._list.menu_requested.connect(self._show_row_menu)
        self._list.list_menu_requested.connect(self._show_list_menu)

        self._open_button.clicked.connect(self._open)
        self._copy_button.clicked.connect(lambda _=False: self._copy())
        self._remove_button.clicked.connect(self._remove)
        self._unreachable_button.clicked.connect(self._remove_unreachable)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

    def reject(self):
        if self._originals:
            self._registry.put_entries(self._originals.values())

        super().reject()

    def done(self, result):
        self._registry.changed.disconnect(self._reload_timer.start)
        self._registry.replaced.disconnect(self._forget_originals)
        self._reload_timer.stop()
        self._checks.stop()

        super().done(result)

    def _forget_originals(self):
        # Another playlist opened, or this one closed, while the dialog was
        # open: what was removed was of one that is gone, and Cancel would
        # put it into this one.
        self._originals = {}

    def changeEvent(self, event):
        super().changeEvent(event)

        if self._is_set_up and event.type() in {
            QEvent.PaletteChange,
            QEvent.FontChange,
        }:
            self._update_look()
            self._reload()

    def _update_look(self):
        palette = self.palette()
        is_dark = palette.color(QPalette.Base).lightness() < 128

        self._colors = {
            "reachable": QColor(
                LOOP_EDGE_COLOR_DARK if is_dark else LOOP_EDGE_COLOR_LIGHT
            ),
            "unreachable": QColor(
                WARNING_COLOR_DARK if is_dark else WARNING_COLOR_LIGHT
            ),
            "idle": palette.color(QPalette.PlaceholderText),
            "gone": palette.color(QPalette.Disabled, QPalette.Text),
            "count": mixed_color(
                palette.color(QPalette.Text), palette.color(QPalette.Base), TIME_FADE
            ),
        }

        self._delegate.time_color = self._colors["count"]

        self._show_mode()
        self._show_counts()

    # What is shown

    def _show_mode(self):
        if self._registry.is_shared:
            icon = "information"
            mode_txt = translate(
                "Dialog - Playlist bookmarks",
                "Bookmarks are shared by every cell playing the same file, and"
                " kept when a cell is closed.",
            )
        else:
            icon = "warning"
            mode_txt = translate(
                "Dialog - Playlist bookmarks",
                "Each cell keeps its own bookmarks. Those of a closed cell are"
                " removed when the playlist is saved.",
            )

        self._mode_icon.setPixmap(QIcon.fromTheme(icon).pixmap(18, 18))
        self._mode.setText(mode_txt)

    def _show_hint(self):
        """Back to the counts, from what was said."""

        self._status_timer.stop()

        self._show_counts()

    def _show_counts(self):
        # not over what is being said
        if self._status_timer.isActive():
            return

        entries = list(self._entries.values())
        count = sum(len(entry.bookmarks) for entry in entries)

        if self._registry.is_shared:
            parts = [
                translate("Dialog - Playlist bookmarks", "Bookmarks: {COUNT}").format(
                    COUNT=count
                ),
                translate("Dialog - Playlist bookmarks", "Files: {COUNT}").format(
                    COUNT=len(entries)
                ),
            ]
        else:
            cells = {entry.cell for entry in entries if entry.cell is not None}
            parts = [
                translate("Dialog - Playlist bookmarks", "Bookmarks: {COUNT}").format(
                    COUNT=count
                ),
                translate("Dialog - Playlist bookmarks", "Cells: {COUNT}").format(
                    COUNT=len(cells)
                ),
            ]

        self._hint.setText(" · ".join(parts) if entries else "")
        self._hint.setForegroundRole(QPalette.PlaceholderText)

    def _say(self, text):
        self._hint.setText(text)
        self._hint.setForegroundRole(QPalette.WindowText)

        self._status_timer.start()

    def _reload(self):
        """Show the registry again, keeping what was open and picked."""

        self._reload_timer.stop()

        expanded = self._expanded_keys()
        picked = self._picked_keys()
        current = self._current_key()

        blocks = [block for block in self._cells() if block.video_params is not None]

        self._entries = {_entry_key(entry): entry for entry in self._registry.entries()}
        self._statuses = {
            key: self._status(entry, blocks) for key, entry in self._entries.items()
        }

        self._model.clear()
        self._model.setHorizontalHeaderLabels(
            [
                translate("Dialog - Playlist bookmarks", "File"),
                translate("Dialog - Playlist bookmarks", "Cell"),
                translate("Dialog - Playlist bookmarks", "Bookmarks"),
                translate("Dialog - Playlist bookmarks", "Status"),
            ]
        )

        cells_by_id = {block.video_params.id: block for block in blocks}

        # a cell by where it is in the grid, first to last, for two playing
        # one file to be told apart; and its own listed in that order, those
        # of cells closed after them
        self._cell_numbers = {
            block.video_params.id: number for number, block in enumerate(blocks, 1)
        }
        in_grid_order = sorted(
            self._entries.items(),
            key=lambda item: self._cell_numbers.get(item[1].cell, len(blocks) + 1),
        )

        for key, entry in in_grid_order:
            self._model.appendRow(self._entry_row(key, entry, cells_by_id))

        for row in range(self._model.rowCount()):
            parent = self._model.index(row, 0)
            for child in range(self._model.rowCount(parent)):
                self._list.setFirstColumnSpanned(child, parent, True)

        self._fit_columns()
        self._restore_view(expanded, picked, current)

        self._show_mode()
        self._show_counts()
        self._update_buttons()

        self._check_files()

    def _entry_row(self, key, entry, cells_by_id):
        status = self._statuses[key]

        file_item = QStandardItem(
            QIcon.fromTheme("add-url" if isinstance(entry.uri, str) else "video"),
            _file_txt(entry.uri),
        )
        file_item.setToolTip(str(entry.uri))
        file_item.setData(key, ENTRY_ROLE)

        if status in UNREACHABLE:
            file_item.setForeground(self._colors["gone"])

        count_item = QStandardItem(str(len(entry.bookmarks)))
        count_item.setTextAlignment(Qt.AlignCenter)
        count_item.setForeground(self._colors["count"])

        row = [
            file_item,
            self._cell_item(entry, cells_by_id),
            count_item,
            self._status_item(entry, status, cells_by_id),
        ]

        # the length of a file not open is not known: its times are laid out
        # as the manager lays out those of a video as long as its last one,
        # and at least a minute, minutes and all
        length = max(MIN_LENGTH_MS, *(bookmark.time_ms for bookmark in entry.bookmarks))

        for index, bookmark in enumerate(entry.bookmarks):
            bookmark_item = QStandardItem()
            bookmark_item.setData(
                (
                    ms_time_txt(bookmark.time_ms, length),
                    bookmark.name or default_bookmark_name(index),
                    bookmark.name is not None,
                    bookmark.color,
                ),
                BOOKMARK_ROLE,
            )
            bookmark_item.setData(key, ENTRY_ROLE)
            bookmark_item.setData(bookmark.time_ms, TIME_ROLE)
            file_item.appendRow(
                [bookmark_item, *(QStandardItem() for _ in range(len(Column) - 1))]
            )

        for item in row[1:]:
            item.setData(key, ENTRY_ROLE)

        return row

    def _cell_item(self, entry, cells_by_id):
        if entry.cell is None:
            item = QStandardItem("—")
            item.setForeground(self._colors["idle"])
            return item

        block = cells_by_id.get(entry.cell)

        if block is not None:
            look = (
                translate("Dialog - Playlist bookmarks", "{NUMBER} · {TITLE}").format(
                    NUMBER=self._cell_numbers[entry.cell],
                    TITLE=block.title or block.video_params.uri_name,
                ),
                block.video_params.color.as_hex(),
            )
        else:
            look = self._registry.cell_look(entry.cell)

        if look is None:
            item = QStandardItem("—")
            item.setForeground(self._colors["idle"])
            return item

        title, color = look

        return QStandardItem(_swatch(color, self._colors["count"]), title)

    def _status_item(self, entry, status, cells_by_id):
        playing = sum(
            1
            for block in cells_by_id.values()
            if file_key(block.video_params.uri) == file_key(entry.uri)
        )

        texts = {
            Status.OPEN: (
                translate("Dialog - Playlist bookmarks", "Open")
                if playing < 2
                else translate(
                    "Dialog - Playlist bookmarks", "Open in {COUNT} cells"
                ).format(COUNT=playing)
            ),
            Status.PLAYING: translate("Dialog - Playlist bookmarks", "Playing"),
            Status.NOT_PLAYING: translate("Dialog - Playlist bookmarks", "Not playing"),
            Status.NOT_OPEN: translate("Dialog - Playlist bookmarks", "Not open"),
            Status.STREAM: translate("Dialog - Playlist bookmarks", "Stream, not open"),
            Status.MISSING: translate("Dialog - Playlist bookmarks", "File missing"),
            Status.NO_FOLDER: translate(
                "Dialog - Playlist bookmarks", "Folder not found"
            ),
            Status.CLOSED_CELL: translate("Dialog - Playlist bookmarks", "Closed cell"),
        }

        item = QStandardItem(texts[status])
        item.setToolTip(self._status_tooltip(entry, status))

        if status in {Status.OPEN, Status.PLAYING}:
            item.setForeground(self._colors["reachable"])
        elif status in UNREACHABLE:
            item.setForeground(self._colors["unreachable"])
            item.setIcon(QIcon.fromTheme("warning"))
        else:
            item.setForeground(self._colors["idle"])

        return item

    def _status_tooltip(self, entry, status) -> str | None:
        if (
            status == Status.NOT_OPEN
            and entry.cell is None
            and not (self._registry.is_shared)
        ):
            return translate(
                "Dialog - Playlist bookmarks",
                "They go to the next cell that opens the file",
            )

        tooltips = {
            Status.NOT_OPEN: translate(
                "Dialog - Playlist bookmarks", "Back when the file is opened again"
            ),
            Status.STREAM: translate(
                "Dialog - Playlist bookmarks", "Back when the stream is opened again"
            ),
            Status.NOT_PLAYING: translate(
                "Dialog - Playlist bookmarks",
                "The cell plays another file now, and has them back when it"
                " plays this one again",
            ),
            Status.MISSING: translate(
                "Dialog - Playlist bookmarks", "The file is not there any more"
            ),
            Status.NO_FOLDER: translate(
                "Dialog - Playlist bookmarks",
                "Its folder is not there either: a drive not connected, or a"
                " folder moved or renamed",
            ),
            Status.CLOSED_CELL: translate(
                "Dialog - Playlist bookmarks",
                "Removed when the playlist is saved; Open gives them to a new cell",
            ),
        }

        return tooltips.get(status)

    def _status(self, entry, blocks) -> Status:
        key = file_key(entry.uri)

        if entry.cell is not None:
            block = next(
                (block for block in blocks if block.video_params.id == entry.cell),
                None,
            )

            if block is None:
                return Status.CLOSED_CELL

            if file_key(block.video_params.uri) == key:
                return Status.PLAYING

        elif self._registry.is_shared and any(
            file_key(block.video_params.uri) == key for block in blocks
        ):
            return Status.OPEN

        if isinstance(entry.uri, str):
            return Status.NOT_PLAYING if entry.cell is not None else Status.STREAM

        found = self._found.get(key)

        if found == Found.NO_FILE:
            return Status.MISSING

        if found == Found.NO_FOLDER:
            return Status.NO_FOLDER

        return Status.NOT_PLAYING if entry.cell is not None else Status.NOT_OPEN

    def _fit_columns(self):
        header = self._list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(Column.FILE, QHeaderView.Stretch)
        header.setSectionResizeMode(Column.CELL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Column.COUNT, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Column.STATUS, QHeaderView.Fixed)
        header.resizeSection(Column.STATUS, STATUS_COLUMN_PX)

        self._list.setColumnHidden(Column.CELL, self._registry.is_shared)

    def _check_files(self):
        """Ask whether the files not open are there, those not asked yet."""

        for key, entry in self._entries.items():
            path_key = key[0]

            if not isinstance(entry.uri, Path) or path_key in self._found:
                continue

            if self._statuses[key] in {Status.OPEN, Status.PLAYING}:
                continue

            # asked once: told, or still on its way
            self._found[path_key] = Found.FILE
            self._checks.check(path_key, entry.uri)

    def _on_checked(self, path_key, found):
        if self._found.get(path_key) == found:
            return

        self._found[path_key] = found

        self._reload_timer.start()

    # What is picked

    def _expanded_keys(self):
        return {
            self._model.index(row, 0).data(ENTRY_ROLE)
            for row in range(self._model.rowCount())
            if self._list.isExpanded(self._model.index(row, 0))
        }

    def _picked_keys(self):
        """The picked rows, by file and cell, and by the bookmark's time for
        a bookmark's row."""

        picked = set()

        for index in self._list.selectionModel().selectedRows():
            key = index.data(ENTRY_ROLE)

            if index.parent().isValid():
                picked.add((key, index.data(TIME_ROLE)))
            else:
                picked.add((key, None))

        return picked

    def _current_key(self):
        index = self._list.currentIndex()

        if not index.isValid():
            return None

        index = index.sibling(index.row(), 0)

        if index.parent().isValid():
            return index.data(ENTRY_ROLE), index.data(TIME_ROLE)

        return index.data(ENTRY_ROLE), None

    def _restore_view(self, expanded, picked, current):
        selection = self._list.selectionModel()

        for row in range(self._model.rowCount()):
            file_index = self._model.index(row, 0)
            key = file_index.data(ENTRY_ROLE)

            if key in expanded:
                self._list.expand(file_index)

            indexes = [(file_index, (key, None))]
            indexes.extend(
                (
                    self._model.index(child, 0, file_index),
                    (key, self._model.index(child, 0, file_index).data(TIME_ROLE)),
                )
                for child in range(self._model.rowCount(file_index))
            )

            for index, index_key in indexes:
                if index_key == current:
                    selection.setCurrentIndex(index, selection.NoUpdate)
                if index_key in picked:
                    selection.select(index, selection.Select | selection.Rows)

        if not self._list.currentIndex().isValid() and self._model.rowCount():
            selection.setCurrentIndex(self._model.index(0, 0), selection.NoUpdate)

    def _picked_entries(self) -> dict:
        """The picked bookmarks, by the entry they are in: None for the
        whole of it, picked by its file's row."""

        picked: dict = {}

        for key, time_ms in self._picked_keys():
            if key not in self._entries:
                continue

            if time_ms is None:
                picked[key] = None
            elif picked.get(key, set()) is not None:
                picked.setdefault(key, set()).add(time_ms)

        return picked

    def _update_buttons(self, *_):
        picked = self._picked_entries()

        self._open_button.setEnabled(self._is_openable(picked))
        self._copy_button.setEnabled(bool(picked))
        self._remove_button.setEnabled(bool(picked))
        self._unreachable_button.setEnabled(
            any(status in UNREACHABLE for status in self._statuses.values())
        )

    def _is_openable(self, picked) -> bool:
        return any(
            self._statuses.get(key) in OPENABLE
            for key, times in picked.items()
            if times is None
        )

    # What the viewer does

    def _remove(self):
        picked = self._picked_entries()

        if not picked:
            return

        gone = []
        changed = []

        for key, times in picked.items():
            entry = self._entries[key]
            self._originals.setdefault(key, entry)

            if times is None:
                gone.append(entry)
                continue

            changed.append(
                entry.model_copy(
                    update={
                        "bookmarks": [
                            bookmark
                            for bookmark in entry.bookmarks
                            if bookmark.time_ms not in times
                        ]
                    }
                )
            )

        self._list.selectionModel().clearSelection()

        if gone:
            self._registry.remove_entries(gone)
        if changed:
            self._registry.put_entries(changed)

        self._reload()

    def _remove_unreachable(self):
        unreachable = [
            entry
            for key, entry in self._entries.items()
            if self._statuses[key] in UNREACHABLE
        ]

        for entry in unreachable:
            self._originals.setdefault(_entry_key(entry), entry)

        self._registry.remove_entries(unreachable)

        self._reload()

        self._say(
            translate("Dialog - Playlist bookmarks", "Files removed: {COUNT}").format(
                COUNT=len(unreachable)
            )
        )

    def _open(self):
        videos = []
        # the closed cells' entries, by the video opened for each
        closed = {}

        for key, times in self._picked_entries().items():
            if times is not None or self._statuses.get(key) not in OPENABLE:
                continue

            entry = self._entries[key]

            try:
                video = Video(uri=entry.uri)
            except ValidationError:
                continue

            if self._statuses[key] == Status.CLOSED_CELL:
                closed[video.id] = (key, entry)

            videos.append(video)

        opened = self._open_files(videos) if videos else []

        # a closed cell's go to the new one, and are its own from there; those
        # of one a full grid turned away stay where they were
        for video in opened:
            if video.id not in closed:
                continue

            key, entry = closed[video.id]

            self._originals.pop(key, None)
            self._registry.remove_entries([entry])
            self._registry.put_entries([entry.model_copy(update={"cell": video.id})])

        self._reload()

    def _copy(self, is_precise=False):
        """Copy the picked bookmarks."""

        self._copy_entries(self._picked_entries(), is_precise)

    def _copy_all(self, is_precise=False):
        self._copy_entries(dict.fromkeys(self._entries), is_precise)

    def _copy_entries(self, picked, is_precise):
        """Copy these bookmarks, by entry (None for all of one's), as
        timestamps: those of one file as they are, to paste into its
        manager; those of several each under the name of its file, in the
        order they are listed."""

        sections = []
        count = 0

        for row in range(self._model.rowCount()):
            key = self._model.index(row, 0).data(ENTRY_ROLE)

            if key not in picked:
                continue

            times = picked[key]
            entry = self._entries[key]
            bookmarks = [
                bookmark
                for bookmark in entry.bookmarks
                if times is None or bookmark.time_ms in times
            ]

            if not bookmarks:
                continue

            # laid out alike for all of a file's, picked or not
            length = max(bookmark.time_ms for bookmark in entry.bookmarks)

            sections.append(
                (
                    self._entry_title(row, entry),
                    bookmarks_txt(bookmarks, length, is_precise),
                )
            )
            count += len(bookmarks)

        if not sections:
            return

        if len(sections) == 1:
            text = sections[0][1]
        else:
            text = "\n\n".join(
                f"{title}\n{timestamps}" for title, timestamps in sections
            )

        QApplication.clipboard().setText(text)

        self._say(
            translate("Dialog - Bookmarks", "Bookmarks copied: {COUNT}").format(
                COUNT=count
            )
        )

    def _entry_title(self, row, entry) -> str:
        """The file's name, or the stream's address, over its bookmarks
        copied with others; and its cell, where they are kept by cell."""

        title = entry.uri.name if isinstance(entry.uri, Path) else entry.uri

        if self._list.isColumnHidden(Column.CELL) or entry.cell is None:
            return title

        cell_txt = self._model.index(row, Column.CELL).data()

        if not cell_txt or cell_txt == "—":
            return title

        return translate("Dialog - Playlist bookmarks", "{FILE} ({CELL})").format(
            FILE=title, CELL=cell_txt
        )

    def _show_row_menu(self, global_pos):
        picked = self._picked_entries()

        if not picked:
            return

        menu = CustomMenu(parent=self)

        open_files = menu.addAction(
            QIcon.fromTheme("add-files"),
            translate("Dialog - Playlist bookmarks", "Open"),
        )
        open_files.setEnabled(self._is_openable(picked))
        open_files.triggered.connect(lambda _=False: self._open())

        menu.addSeparator()

        copy = menu.addAction(
            QIcon.fromTheme("copy"),
            with_key_txt(
                translate("Dialog - Playlist bookmarks", "Copy"), QKeySequence.Copy
            ),
        )
        copy.triggered.connect(lambda _=False: self._copy())

        copy_precise = menu.addAction(
            QIcon.fromTheme("empty"),
            translate("Dialog - Bookmarks", "Copy with Milliseconds"),
        )
        copy_precise.triggered.connect(lambda _=False: self._copy(is_precise=True))

        menu.addSeparator()

        remove = menu.addAction(
            QIcon.fromTheme("bookmark-remove"),
            with_key_txt(
                translate("Dialog - Playlist bookmarks", "Remove"), Qt.Key_Delete
            ),
        )
        remove.triggered.connect(lambda _=False: self._remove())

        menu.exec_(global_pos)
        menu.deleteLater()

    def _show_list_menu(self, global_pos):
        """What can be done with the list as a whole, from under its rows."""

        has_any = bool(self._entries)

        menu = CustomMenu(parent=self)

        copy_all = menu.addAction(
            QIcon.fromTheme("copy"), translate("Dialog - Bookmarks", "Copy All")
        )
        copy_all.setEnabled(has_any)
        copy_all.triggered.connect(lambda _=False: self._copy_all())

        copy_all_precise = menu.addAction(
            QIcon.fromTheme("empty"),
            translate("Dialog - Bookmarks", "Copy All with Milliseconds"),
        )
        copy_all_precise.setEnabled(has_any)
        copy_all_precise.triggered.connect(
            lambda _=False: self._copy_all(is_precise=True)
        )

        menu.addSeparator()

        remove_unreachable = menu.addAction(
            QIcon.fromTheme("bookmark-remove-all"),
            translate("Dialog - Playlist bookmarks", "Remove Unreachable"),
        )
        remove_unreachable.setEnabled(self._unreachable_button.isEnabled())
        remove_unreachable.triggered.connect(lambda _=False: self._remove_unreachable())

        menu.exec_(global_pos)
        menu.deleteLater()
