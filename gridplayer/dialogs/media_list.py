"""The List window: what is on a list, to play from, name, put in order, add
to and take off, and to read again from where it came from.

Edits are made as they go, the cell and any other cell playing the list
following along, and Cancel puts the list back the way it was. Opened on a
cell it stays open beside the player, to go from item to item in the cell
while doing something else.
"""

import contextlib
import dataclasses
import html
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from PyQt5.QtCore import (
    QAbstractTableModel,
    QDateTime,
    QItemSelection,
    QLocale,
    QMimeData,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QDrag,
    QDragLeaveEvent,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.add_urls import QAddURLsDialog
from gridplayer.dialogs.bookmarks import (
    ROW_HEIGHT,
    STATUS_MS,
    blank_icon,
    dialog_button,
    here_icon,
    paint_empty_txt,
    with_key_txt,
)
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.unlink_list import UnlinkListDialog
from gridplayer.dialogs.update_every import UpdateEveryDialog, every_txt, in_txt
from gridplayer.models.media_list import (
    ItemDetails,
    ListItem,
    ListSource,
    MediaList,
    new_item_key,
)
from gridplayer.models.playlist import saved_list_bytes
from gridplayer.models.video_uri import URL_ALLOWED_SCHEMES
from gridplayer.params.defaults_fields import list_update_txts
from gridplayer.params.static import (
    ListSort,
    ListSourceKind,
    ListUpdate,
    ListView,
)
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.excepthook import dragging
from gridplayer.utils.file_checks import FileChecks
from gridplayer.utils.files import extract_mime_uris
from gridplayer.utils.item_info import may_be_looked_up
from gridplayer.utils.list_errors import (
    ReadError,
    ReadErrorKind,
    read_error_of,
    site_name,
)
from gridplayer.utils.list_files import m3u_text
from gridplayer.utils.list_order import (
    item_name,
    list_base,
    published_of,
    sorted_items,
    view_count_of,
)
from gridplayer.utils.list_progress import Throttled, reading_txt
from gridplayer.utils.list_refresh import (
    Refreshed,
    in_source_order,
    linked,
    refreshed,
    reloaded,
    uri_key,
    with_added,
    with_removed,
)
from gridplayer.utils.list_update import (
    INTERVALS_S,
    interval_of,
    is_short,
    next_update_at,
    update_of,
)
from gridplayer.utils.misc import is_url
from gridplayer.utils.next_file import natural_key
from gridplayer.utils.off_thread import OffThread
from gridplayer.utils.qt import count_txt, detach_modal_dialog, translate
from gridplayer.utils.screenshots import sanitize_filename
from gridplayer.utils.show_in_folder import FolderRevealer
from gridplayer.utils.thumbnails import ThumbnailLoader
from gridplayer.utils.time_txt import get_time_txt
from gridplayer.utils.url_resolve.static import PLUGIN_URLS
from gridplayer.widgets.combo_box import ElidedComboBox, cap_popup_height
from gridplayer.widgets.custom_menu import CustomMenu, checked_icon
from gridplayer.widgets.elided_label import ElidedLabel

DIALOG_SIZE = QSize(600, 560)
DIALOG_MIN_SIZE = QSize(460, 380)

HERE_ICON_PX = 12
LENGTH_COLUMN_PX = 84

# a row with where its item is under its name: the name's line where it is
# in a row of one line, and the other this much further down
SECOND_LINE_PX = 18
TWO_LINE_ROW_HEIGHT = ROW_HEIGHT + SECOND_LINE_PX

# where an item is, under its name in a row picked
PICKED_LOCATION_ALPHA = 0.72

# a row with the video's picture: the picture before its two lines, and the
# number beside it in the middle
THUMBNAIL_SIZE = QSize(80, 45)
THUMBNAIL_ROW_HEIGHT = 55
THUMBNAIL_GAP_PX = 10
THUMBNAIL_RADIUS_PX = 4

# A row's picture is fetched once the row has been near this long: in sight,
# or this many views of rows above or below them, to be there by the time
# they are scrolled to. A list scrolled through quickly fetches none of the
# pictures that went by. Which rows are near is looked at every so often
# while any wait for theirs.
THUMBNAIL_SETTLE_MS = 1000
THUMBNAIL_CHECK_MS = 250
THUMBNAIL_AHEAD_VIEWS = 2

# the room the rows' style leaves before what is in a cell
ITEM_PADDING_PX = 4

# a list longer than this is looked through once typing stops for a moment,
# rather than at every key: a channel list takes a noticeable while each time
FIND_AT_ONCE_ITEMS = 20000
FIND_PAUSE_MS = 250

# the most of the row the group box takes from the box to find with
GROUP_COMBO_SHARE = 0.5

PROGRESS_BAR_HEIGHT_PX = 8

# Reading the list again, or what is added, is shown going on only once it
# has taken this long. A folder on the disk is read again sooner than that,
# and the buttons and the panel would blink.
READING_SHOWN_AFTER_MS = 500

SOURCE_ICON_PX = 16

# how often how long ago the list was read is said again
UPDATED_REFRESH_MS = 30_000

# the room round the words of a quiet button, on each side
FITTED_PADDING_PX = 4

# what Custom… starts from, for a list read only as the playlist loads
DEFAULT_CUSTOM_UPDATE_S = 3600

# the sign of the button in the Linked tag, small for the tag to stay so
UNLINK_ICON_PX = 12

# the sign before what the list could not be read for, and the ✕ putting
# that away
READ_ERROR_ICON_PX = 16
HIDE_ERROR_ICON_PX = 12

# the HTTP answers said each in words of their own
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_THERE = frozenset((404, 410))
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERRORS = (500, 600)

# the sign on the button stopping a lookup, in the line under the list
LOOKUP_ICON_PX = 14

# items dragged about the list, by their keys
KEYS_MIME = "application/x-gridplayer-list-keys"

# what is dragged, said on a card beside the pointer
DRAG_IMAGE_MAX_PX = 240
DRAG_IMAGE_PADDING_PX = 8
DRAG_IMAGE_SHIFT_PX = 14

# the line between the rows a drop goes to
DROP_LINE_PX = 2
DROP_RING_RADIUS_PX = 3

RENAME_KEY = Qt.Key_F2
REMOVE_KEY = Qt.Key_Delete
ADD_KEY = Qt.Key_Insert

KEY_ROLE = Qt.UserRole
LOCATION_ROLE = Qt.UserRole + 1
THUMBNAIL_ROLE = Qt.UserRole + 2
DETAILS_ROLE = Qt.UserRole + 3


class Column(IntEnum):
    NUMBER = 0
    TITLE = 1
    LENGTH = 2


@dataclass
class ListReading:
    """How the window reads what is added to a list, and a list again from
    where it came from; slow, so it does both off the interface thread.

    Each is told how far it has got with a progress of its own, which it
    passes on as list_progress.Throttled is told it, and which raises
    ReadingStopped where it was asked to stop.
    """

    # the items of files, folders, list files and links, and what of them
    # could not be read, as (where, why)
    expand: Callable[[list[str], Callable | None], tuple[tuple[ListItem, ...], tuple]]
    # what is where a list was read from now; raises for what cannot be read
    read_source: Callable[[object, Callable | None], tuple[ListItem, ...]]
    # what was there the last time it was read, if that is kept; for putting
    # a list back in its source's order without reading it again
    kept_source: Callable[[object], tuple[ListItem, ...] | None] | None = None
    # the kinds of files offered to add
    name_filters: list[str] = field(default_factory=list)
    # a video's picture, by its link; raises for what cannot be had. None
    # for none to be fetched
    fetch_thumbnail: Callable[[str], bytes] | None = None
    # what is known of items, looked up from their files and the sites they
    # are on, for as long as it takes: player/managers/list_info.py's
    # ItemLookups. None for nothing to be looked up
    lookups: object | None = None


def _is_there(path: Path) -> bool:
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def _source_kind(source) -> tuple[str, str]:
    """What a list was read from, as an icon's name and a title."""

    if source.kind == ListSourceKind.URL:
        return "add-url", translate("Dialog - List", "Source: Link")

    if source.kind == ListSourceKind.FILE:
        return "add-files", translate("Dialog - List", "Source: Playlist file")

    if source.is_recursive:
        return "add-folder", translate(
            "Dialog - List", "Source: Folder, with subfolders"
        )

    return "add-folder", translate("Dialog - List", "Source: Folder")


def _length_txt(item: ListItem) -> str:
    if item.duration_ms is None:
        return ""

    return get_time_txt(item.duration_ms // 1000, strip=True)


def _item_tooltip(name: str, where: str) -> str:
    """An item's name whole, a long one being cut short in its row, and under
    it where it is; that alone where it is all the name there is."""

    lines = [] if name == where else [f"<b>{html.escape(name)}</b>"]
    lines.append(html.escape(where))

    # on a line each; a long link, with no spaces to wrap at, wraps
    # anywhere in the tip (see widgets.tooltip)
    return f"<p>{'<br>'.join(lines)}</p>"


class ListItemsModel(QAbstractTableModel):
    """The items of the list, those the filter lets through."""

    # an item named in its row: its key, and the name
    renamed = pyqtSignal(int, str)

    # items dragged to another place: their keys, and the place on the whole
    # list they go before
    moved = pyqtSignal(tuple, int)

    # files or links dropped in: what, and the place they go before
    dropped = pyqtSignal(list, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._items: tuple[ListItem, ...] = ()
        self._shown: list[int] = []
        self._rows_by_key: dict[int, int] | None = None

        # the folder the list was read from, for files under it to be named
        # from there
        self._base: Path | None = None

        self._here_key: int | None = None
        self._missing: set[str] = set()

        self._filter_txt = ""
        self._group: str | None = None

        # what each item is shown by: its name, where it is, or both
        self._view = ListView.TITLES

        # while the list is read again or added to, it stays as it is
        self._is_locked = False

        # a linked list's: in the order of its source, or the one it was
        # sorted in, not the viewer's to give; and with what its source
        # has, nothing dropped in
        self._is_linked = False

        self._here_icon = QIcon()
        self._blank_icon = blank_icon()
        self._colors = {}
        self._here_font = QFont()
        self._missing_font = QFont()

    def set_look(self, palette: QPalette, font: QFont):
        self._colors = {
            "dim": palette.color(QPalette.PlaceholderText),
        }

        self._here_icon = here_icon(palette.color(QPalette.Text))

        self._here_font = QFont(font)
        self._here_font.setBold(True)

        self._missing_font = QFont(font)
        self._missing_font.setItalic(True)

        self._refresh_all()

    def set_items(self, items: tuple[ListItem, ...], base: Path | None):
        self.beginResetModel()
        self._items = items
        self._base = base
        self._shown = self._filtered()
        self._rows_by_key = None
        self.endResetModel()

    def set_here(self, key: int | None):
        self._here_key = key
        self._refresh_all()

    def set_missing(self, key: str, is_missing: bool):
        if is_missing == (key in self._missing):
            return

        if is_missing:
            self._missing.add(key)
        else:
            self._missing.discard(key)

        self._refresh_all()

    def set_filter(self, text: str, group: str | None):
        self.beginResetModel()
        self._filter_txt = text.casefold().strip()
        self._group = group
        self._shown = self._filtered()
        self._rows_by_key = None
        self.endResetModel()

    @property
    def is_filtered(self) -> bool:
        return bool(self._filter_txt) or self._group is not None

    def set_view(self, view: ListView):
        """Found by what it is shown by as well, the next time it is
        looked through."""

        self._view = view
        self._refresh_all()

    def set_locked(self, is_locked: bool):
        """No renaming, dragging about or dropping in, while it is."""

        self._is_locked = is_locked

    def set_linked(self, is_linked: bool):
        """No dragging rows about, nor dropping in, while it is."""

        self._is_linked = is_linked

    @property
    def is_linked(self) -> bool:
        return self._is_linked

    @property
    def items(self) -> tuple[ListItem, ...]:
        return self._items

    @property
    def base(self) -> Path | None:
        return self._base

    @property
    def here_key(self) -> int | None:
        return self._here_key

    def item_at(self, row: int) -> ListItem:
        return self._items[self._shown[row]]

    def place_at(self, row: int) -> int:
        """Where the item of a row is on the whole list."""

        return self._shown[row]

    def place_before_row(self, row: int) -> int:
        """Where on the whole list something put before a row goes."""

        if row < 0 or row >= len(self._shown):
            return len(self._items)

        return self._shown[row]

    def row_of_key(self, key: int | None) -> int | None:
        if key is None:
            return None

        # found by key, of the rows shown: made once they change, a list
        # running to a few hundred thousand
        if self._rows_by_key is None:
            self._rows_by_key = {
                self._items[place].key: row for row, place in enumerate(self._shown)
            }

        return self._rows_by_key.get(key)

    def name_of(self, item: ListItem) -> str:
        return item_name(item, self._base)

    def is_missing(self, item: ListItem) -> bool:
        return isinstance(item.uri, Path) and uri_key(item.uri) in self._missing

    def _filtered(self) -> list[int]:
        if not self.is_filtered:
            return list(range(len(self._items)))

        return [place for place, item in enumerate(self._items) if self._is_shown(item)]

    def _is_shown(self, item: ListItem) -> bool:
        if self._group is not None and (item.group or "") != self._group:
            return False

        if not self._filter_txt:
            return True

        if self._filter_txt in self.name_of(item).casefold():
            return True

        # and by what is under it, where that is shown: the channel of a
        # video a site says it of, or else where it is
        if self._view == ListView.TITLES:
            return False

        if self._view == ListView.THUMBNAILS and item.details is not None:
            return self._filter_txt in (item.details.channel or "").casefold()

        return self._filter_txt in str(item.uri).casefold()

    def _refresh_all(self):
        if self.rowCount():
            self.dataChanged.emit(
                self.index(0, 0), self.index(self.rowCount() - 1, len(Column) - 1)
            )

    def rowCount(self, parent=QModelIndex()):  # noqa: B008
        if parent.isValid():
            return 0

        return len(self._shown)

    def columnCount(self, parent=QModelIndex()):  # noqa: B008
        if parent.isValid():
            return 0

        return len(Column)

    def flags(self, index):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        if self._is_locked:
            return flags if index.isValid() else Qt.NoItemFlags

        if not index.isValid():
            return Qt.ItemIsDropEnabled

        if index.column() == Column.TITLE:
            flags |= Qt.ItemIsEditable

        if not self.is_filtered and not self._is_linked:
            flags |= Qt.ItemIsDragEnabled

        return flags | Qt.ItemIsDropEnabled

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        item = self.item_at(index.row())
        column = index.column()
        is_here = item.key == self._here_key
        is_missing = self.is_missing(item)

        if role == Qt.DisplayRole:
            if column == Column.NUMBER:
                return str(self.place_at(index.row()) + 1)
            if column == Column.TITLE:
                if self._view == ListView.LOCATIONS:
                    return str(item.uri)
                return self.name_of(item)
            if is_missing:
                return translate("Dialog - List", "missing")
            return _length_txt(item)

        if role == Qt.EditRole and column == Column.TITLE:
            return self.name_of(item)

        if role == Qt.DecorationRole and column == Column.NUMBER:
            return self._here_icon if is_here else self._blank_icon

        if role == Qt.ForegroundRole:
            if is_missing or (column == Column.NUMBER and not is_here):
                return self._colors.get("dim")
            return None

        if role == Qt.FontRole:
            if is_here:
                return self._here_font
            if is_missing:
                return self._missing_font
            return None

        if role == Qt.TextAlignmentRole and column != Column.TITLE:
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if role == Qt.ToolTipRole and column == Column.TITLE:
            return _item_tooltip(self.name_of(item), str(item.uri))

        if role == KEY_ROLE:
            return item.key

        if role == LOCATION_ROLE:
            return str(item.uri)

        if role == THUMBNAIL_ROLE:
            return None if item.details is None else item.details.thumbnail

        if role == DETAILS_ROLE:
            return None if item.details is None else details_txt(item.details) or None

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or index.column() != Column.TITLE:
            return False

        self.renamed.emit(self.item_at(index.row()).key, str(value))

        return False

    # dragging about, and dropping in

    def supportedDropActions(self):
        return Qt.MoveAction | Qt.CopyAction

    def supportedDragActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [KEYS_MIME, "text/uri-list", "text/plain"]

    def mimeData(self, indexes):
        rows = sorted({index.row() for index in indexes})
        keys = ",".join(str(self.item_at(row).key) for row in rows)

        data = QMimeData()
        data.setData(KEYS_MIME, keys.encode())

        return data

    def canDropMimeData(self, data, action, row, column, parent):
        if self._is_locked or self._is_linked:
            return False

        if data.hasFormat(KEYS_MIME):
            return not self.is_filtered

        return bool(extract_mime_uris(data))

    def dropMimeData(self, data, action, row, column, parent):
        if parent.isValid():
            row = parent.row()

        place = self.place_before_row(row)

        if data.hasFormat(KEYS_MIME):
            keys = tuple(
                int(key) for key in bytes(data.data(KEYS_MIME)).decode().split(",")
            )
            self.moved.emit(keys, place)
            return True

        uris = extract_mime_uris(data)

        if uris:
            self.dropped.emit(uris, place)
            return True

        return False


class _RowDelegate(QStyledItemDelegate):
    """A row drawn whole, with no box round the one cell of it that has the
    focus; renamed in a line to type in, as a bookmark is.

    In two lines, where its item is goes under its name, and the rest of the
    row keeps to the name's line: the number, the mark of the one playing
    and the length. With the video's picture, the picture goes before the
    two lines, what the site says of the video under its name, and the
    number stays in the middle beside it.
    """

    # a row in sight with its picture still to be fetched
    picture_wanted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.view = ListView.TITLES

        # where the pictures come from; None for none to come
        self.thumbnails: ThumbnailLoader | None = None

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)

        option.state &= ~QStyle.State_HasFocus

    def paint(self, painter, option, index):
        if self.view == ListView.TITLES_AND_LOCATIONS:
            option = self._paint_ground(painter, option, index)
            self._paint_lines(painter, option, index, option.rect)
        elif self.view == ListView.THUMBNAILS and index.column() != Column.NUMBER:
            option = self._paint_ground(painter, option, index)
            lines = _thumbnail_lines(option.rect)

            if index.column() == Column.TITLE:
                picture = _thumbnail_rect(option.rect)
                self._paint_thumbnail(painter, picture, index, option.palette)

                # the lines after the picture, the style's own room before
                # them taken into account
                lines.setLeft(picture.right() + 1 + THUMBNAIL_GAP_PX - ITEM_PADDING_PX)

            self._paint_lines(painter, option, index, lines)
        else:
            super().paint(painter, option, index)

    def _paint_ground(self, painter, option, index) -> QStyleOptionViewItem:
        """The row's ground, under all of its lines; the cell as the style
        has it, for what is in it to go on."""

        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)

        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()

        ground = QStyleOptionViewItem(option)
        ground.text = ""
        ground.icon = QIcon()
        ground.features &= ~(
            QStyleOptionViewItem.HasDisplay | QStyleOptionViewItem.HasDecoration
        )
        style.drawControl(QStyle.CE_ItemViewItem, ground, painter, widget)

        return option

    def _paint_lines(self, painter, option, index, lines: QRect):
        """What is in the cell, on two lines: the first one where lines
        says, and the rest of the row keeping to it."""

        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()
        is_picked = bool(option.state & QStyle.State_Selected)

        palette = option.palette
        color = palette.color(QPalette.HighlightedText if is_picked else QPalette.Text)
        _paint_line(style, option, _first_line(lines), color, painter)

        if index.column() != Column.TITLE:
            return

        details = index.data(DETAILS_ROLE)

        under = QStyleOptionViewItem(option)
        under.icon = QIcon()
        under.features &= ~QStyleOptionViewItem.HasDecoration

        if details is not None and self.view == ListView.THUMBNAILS:
            under.text = details
        else:
            under.text = index.data(LOCATION_ROLE) or ""
            # the start of it, and the file's name or what tells a link apart
            under.textElideMode = Qt.ElideMiddle

        font = QFont(option.font)
        font.setBold(False)
        under.font = font

        if is_picked:
            color = QColor(color)
            color.setAlphaF(PICKED_LOCATION_ALPHA)
        else:
            color = palette.color(QPalette.PlaceholderText)

        _paint_line(style, under, _second_line(lines), color, painter)

    def _paint_thumbnail(self, painter, rect: QRect, index, palette: QPalette):
        url = index.data(THUMBNAIL_ROLE)
        loader = self.thumbnails
        picture = None if url is None or loader is None else loader.picture(url)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        shape = QPainterPath()
        shape.addRoundedRect(QRectF(rect), THUMBNAIL_RADIUS_PX, THUMBNAIL_RADIUS_PX)

        if picture is not None:
            painter.setClipPath(shape)
            painter.drawImage(QRectF(rect), picture)
        else:
            painter.fillPath(shape, _no_picture_color(palette))

            sign = palette.color(QPalette.PlaceholderText)

            if url is not None and loader is not None and not loader.is_missing(url):
                _paint_coming(painter, rect, sign)

                if loader.is_to_fetch(url):
                    self.picture_wanted.emit()
            else:
                _paint_no_picture(painter, rect, sign)

        painter.restore()

    def createEditor(self, parent, option, index):
        # framed, where Qt's own has none and a background of its own the
        # width of the text: a box laid over the row rather than a line in it
        return QLineEdit(parent)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect

        if self.view == ListView.TITLES_AND_LOCATIONS:
            rect = _first_line(rect)
        elif self.view == ListView.THUMBNAILS:
            rect = _first_line(_thumbnail_lines(rect))
            rect.setLeft(
                _thumbnail_rect(option.rect).right()
                + 1
                + THUMBNAIL_GAP_PX
                - ITEM_PADDING_PX
            )

        # the whole of the cell across, or the row's highlight shows in the
        # padding beside it; its own margin keeps the text where it was
        editor.setGeometry(rect.adjusted(0, 1, 0, -1))


def _first_line(rect: QRect) -> QRect:
    return QRect(rect.left(), rect.top(), rect.width(), ROW_HEIGHT)


def _second_line(rect: QRect) -> QRect:
    return QRect(rect.left(), rect.top() + SECOND_LINE_PX, rect.width(), ROW_HEIGHT)


def _thumbnail_rect(rect: QRect) -> QRect:
    """Where a row's picture goes: first in it, in the middle of its height."""

    return QRect(
        QPoint(
            rect.left() + ITEM_PADDING_PX,
            rect.top() + (rect.height() - THUMBNAIL_SIZE.height()) // 2,
        ),
        THUMBNAIL_SIZE,
    )


def _thumbnail_lines(rect: QRect) -> QRect:
    """Where the two lines of a row with a picture go: in the middle of it."""

    top = rect.top() + (rect.height() - TWO_LINE_ROW_HEIGHT) // 2

    return QRect(rect.left(), top, rect.width(), TWO_LINE_ROW_HEIGHT)


def _no_picture_color(palette: QPalette) -> QColor:
    """A box a shade off the list's own ground, the way it goes: darker on
    a light one, lighter on a dark one."""

    base = palette.color(QPalette.Base)

    return base.darker(108) if base.lightness() >= 128 else base.lighter(135)


def _paint_coming(painter, rect: QRect, color: QColor):
    """Three dots: the picture is on its way."""

    radius = rect.height() * 0.035
    step = rect.height() * 0.16
    center = QRectF(rect).center()

    painter.setPen(Qt.NoPen)
    painter.setBrush(color)

    for n in (-1, 0, 1):
        painter.drawEllipse(center + QPointF(n * step, 0), radius, radius)


def _paint_no_picture(painter, rect: QRect, color: QColor):
    """A frame with a play sign in it: a video with no picture to show."""

    side = rect.height() * 0.28
    center = QRectF(rect).center()

    frame = QRectF(0, 0, side * 1.5, side * 1.1)
    frame.moveCenter(center)

    pen = QPen(color, max(1.2, rect.height() / 40))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(frame, 2, 2)

    play = QPainterPath()
    play.moveTo(center + QPointF(-side * 0.22, -side * 0.28))
    play.lineTo(center + QPointF(side * 0.3, 0))
    play.lineTo(center + QPointF(-side * 0.22, side * 0.28))
    play.closeSubpath()

    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(play)


def _paint_line(style, option, rect, color, painter):
    """What is in a cell, laid out by the style as in a row of one line, on
    a line of a taller one: the row's ground is drawn under it already."""

    line = QStyleOptionViewItem(option)
    line.rect = rect
    line.state &= ~QStyle.State_Selected
    line.backgroundBrush = QBrush()

    palette = QPalette(option.palette)
    palette.setColor(QPalette.Text, color)
    line.palette = palette

    style.drawControl(QStyle.CE_ItemViewItem, line, painter, option.widget)


_ROW_HEIGHTS = {
    ListView.TITLES_AND_LOCATIONS: TWO_LINE_ROW_HEIGHT,
    ListView.THUMBNAILS: THUMBNAIL_ROW_HEIGHT,
}


class _TagButton(QToolButton):
    """A button in a tag, as tall as the tag has room for and as wide,
    its sign an odd number of pixels where that is and an even one where
    not: in the very middle, rather than half a pixel above it."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setIconSize(QSize(UNLINK_ICON_PX, UNLINK_ICON_PX))

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(max(size.width(), self.height()), size.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)

        height = self.height()
        icon_px = UNLINK_ICON_PX + (height - UNLINK_ICON_PX) % 2

        if self.iconSize().width() != icon_px:
            self.setIconSize(QSize(icon_px, icon_px))

        if self.width() != height:
            self.setFixedWidth(height)


class FittedButton(QToolButton):
    """Something said one of a few ways, the longest there is room for;
    nothing at all where there is room for none, rather than cut short.
    Quiet, as words beside what they are about; and where it opens a
    menu, a ▾ after it, a ground under the pointer and the words up."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._texts: tuple[str, ...] = ()
        self._is_choosable = False
        self._is_restyling = False

        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)

        self._restyle()

    def set_texts(self, *texts: str):
        self._texts = texts

        self.updateGeometry()
        self._fit()

    def set_choosable(self, is_choosable: bool):
        if is_choosable == self._is_choosable:
            return

        self._is_choosable = is_choosable

        self._restyle()
        self.updateGeometry()
        self._fit()

    @property
    def is_choosable(self) -> bool:
        return self._is_choosable

    @property
    def texts(self) -> tuple[str, ...]:
        """The ways it is said, longest first, whatever there is room for."""

        return self._texts

    def sizeHint(self):
        longest = max((self._width_of(text) for text in self._texts), default=0)

        return QSize(longest + 2 * FITTED_PADDING_PX, super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def shown_text(self) -> str:
        """What there is room to say now."""

        room = self.width() - 2 * FITTED_PADDING_PX

        return next(
            (self._said(text) for text in self._texts if self._width_of(text) <= room),
            "",
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._fit()

    def changeEvent(self, event):
        super().changeEvent(event)

        # the theme's changed; not its own style sheet's doing
        if event.type() == event.PaletteChange and not self._is_restyling:
            self._restyle()

    def _said(self, text: str) -> str:
        return f"{text} ▾" if self._is_choosable else text

    def _width_of(self, text: str) -> int:
        return self.fontMetrics().horizontalAdvance(self._said(text))

    def _fit(self):
        text = self.shown_text()

        if text != self.text():
            self.setText(text)

    def _restyle(self):
        # the theme's colours, not its own: its style sheet changes those
        palette = QApplication.palette()
        dim = palette.color(QPalette.PlaceholderText).name()
        text = palette.color(QPalette.Text).name()

        style = (
            f"QToolButton {{ color: {dim}; border: none; border-radius: 3px;"
            f" padding: 1px {FITTED_PADDING_PX}px; }}"
            " QToolButton::menu-indicator { image: none; width: 0px; }"
        )

        if self._is_choosable:
            style += (
                " QToolButton:hover, QToolButton:pressed"
                f" {{ background: palette(window); color: {text}; }}"
            )

        if style == self.styleSheet():
            return

        self._is_restyling = True
        try:
            self.setStyleSheet(style)
        finally:
            self._is_restyling = False


class ItemList(QTableView):
    """The rows of the list, with keys of their own for what their menus
    offer, the player's being its own window's.

    A table rather than a tree: a tree lays out every row before it shows
    any, which for a channel list of a few hundred thousand is a second.
    """

    play_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    remove_requested = pyqtSignal()
    add_requested = pyqtSignal()
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()

    # for a row, and for the list itself, from the space under the rows
    menu_requested = pyqtSignal(QPoint)
    list_menu_requested = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTabKeyNavigation(False)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setIconSize(QSize(HERE_ICON_PX, HERE_ICON_PX))
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(_RowDelegate(self))

        # where a drop goes is marked by a line between the rows, see
        # paintEvent: Qt's own marks one cell of the row
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)

        # where the pointer is in a drag over the list it can be dropped in
        self._drop_pos: QPoint | None = None
        # rows of its own being dragged, the only ones it moves
        self._is_dragging_rows = False

        self.setStyleSheet(
            """
            QTableView::item {
                padding-left: 4px;
                padding-right: 8px;
            }
            """
        )

        # what the list says with nothing in it: a line, and a hint under it
        self.empty_txt = ("", "")

    def header(self):
        return self.horizontalHeader()

    def show_rows_for(self, view: ListView):
        """The rows drawn for what each item is shown by, as tall as that
        takes."""

        self.itemDelegate().view = view
        self.verticalHeader().setDefaultSectionSize(_ROW_HEIGHTS.get(view, ROW_HEIGHT))
        self.viewport().update()

    def keyPressEvent(self, event):
        if self.state() == QAbstractItemView.EditingState:
            super().keyPressEvent(event)
            return

        signal = self._signal_for_key(event)

        if signal is None:
            super().keyPressEvent(event)
            return

        signal.emit()
        event.accept()

    def _signal_for_key(self, event):
        if event.matches(QKeySequence.Copy):
            return self.copy_requested

        if event.matches(QKeySequence.Paste):
            return self.paste_requested

        modifiers = int(event.modifiers() & ~Qt.KeypadModifier)

        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and not modifiers:
            return self.play_requested

        return {
            RENAME_KEY: self.rename_requested,
            REMOVE_KEY: self.remove_requested,
            ADD_KEY: self.add_requested,
        }.get(modifiers | event.key())

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
            if not self.selectionModel().isSelected(index):
                self.setCurrentIndex(index)
            self.menu_requested.emit(global_pos)
        else:
            self.list_menu_requested.emit(global_pos)

        event.accept()

    # dragging rows about, and dropping in

    def startDrag(self, supported_actions):
        """The rows picked, dragged by their keys, and beside the pointer a
        card of what they are rather than Qt's picture of them, the rows as
        wide as the list, made a part of the pointer on Windows: that came
        out as black boxes."""

        model = self.model()
        rows = [
            index
            for index in self.selectionModel().selectedRows()
            if model.flags(index) & Qt.ItemIsDragEnabled
        ]

        if not rows:
            return

        drag = QDrag(self)
        drag.setMimeData(model.mimeData(rows))
        drag.setPixmap(self._drag_image(rows))
        # beside the pointer, below it to the right
        drag.setHotSpot(QPoint(-DRAG_IMAGE_SHIFT_PX, -DRAG_IMAGE_SHIFT_PX))

        # what goes wrong as the rows are dropped said once the drag is
        # over, as for a cell's: a dialog under a drag cannot be clicked
        self._is_dragging_rows = True
        try:
            with dragging():
                drag.exec_(supported_actions, Qt.MoveAction)
        finally:
            self._is_dragging_rows = False

    def _drag_image(self, rows) -> QPixmap:
        """A card saying what is dragged: the item, or how many."""

        if len(rows) == 1:
            index = rows[0].siblingAtColumn(Column.TITLE)
            text = str(self.model().data(index))
        else:
            text = translate("Dialog - List", "{COUNT} items").format(
                COUNT=count_txt(len(rows))
            )

        metrics = QFontMetrics(self.font())
        text = metrics.elidedText(
            text, Qt.ElideRight, DRAG_IMAGE_MAX_PX - 2 * DRAG_IMAGE_PADDING_PX
        )
        size = QSize(
            metrics.horizontalAdvance(text) + 2 * DRAG_IMAGE_PADDING_PX,
            metrics.height() + DRAG_IMAGE_PADDING_PX,
        )

        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(size * ratio)
        pixmap.setDevicePixelRatio(ratio)

        palette = self.palette()
        pixmap.fill(palette.color(QPalette.Base))

        painter = QPainter(pixmap)
        painter.setPen(palette.color(QPalette.Mid))
        painter.drawRect(0, 0, size.width() - 1, size.height() - 1)
        painter.setFont(self.font())
        painter.setPen(palette.color(QPalette.Text))
        painter.drawText(QRect(QPoint(0, 0), size), Qt.AlignCenter, text)
        painter.end()

        return pixmap

    def dragEnterEvent(self, event):
        super().dragEnterEvent(event)

        self._take_drag(event)

    def dragMoveEvent(self, event):
        # scrolls the list, near its top or bottom
        super().dragMoveEvent(event)

        self._take_drag(event)

    def dragLeaveEvent(self, event):
        super().dragLeaveEvent(event)

        self._mark_drop(None)

    def dropEvent(self, event):
        # as Qt's own drop ends: no more scrolling, nor dragging over it
        self.dragLeaveEvent(QDragLeaveEvent())

        action = self._drop_action(event)

        if action == Qt.IgnoreAction:
            event.ignore()
            return

        row = self.drop_row_at(event.pos())

        if not self.model().dropMimeData(
            event.mimeData(), action, row, Column.NUMBER, QModelIndex()
        ):
            event.ignore()
            return

        event.setDropAction(action)
        event.accept()

    def drop_row_at(self, pos: QPoint) -> int:
        """The row a drop at a point goes before: the nearer edge of the row
        it is over, past the last one the end."""

        row = self.rowAt(pos.y())

        if row < 0:
            return self.model().rowCount()

        if pos.y() - self.rowViewportPosition(row) >= self.rowHeight(row) / 2:
            return row + 1

        return row

    def _take_drag(self, event):
        action = self._drop_action(event)

        if action == Qt.IgnoreAction:
            event.ignore()
            self._mark_drop(None)
            return

        event.setDropAction(action)
        event.accept()
        self._mark_drop(event.pos())

    def _drop_action(self, event):
        """Rows of its own are moved, not another list's; what comes from
        elsewhere is added, never moved: a file taken by a move would be
        gone from its folder."""

        data = event.mimeData()
        is_own = data.hasFormat(KEYS_MIME)

        if is_own and not self._is_dragging_rows:
            return Qt.IgnoreAction

        if not self.model().canDropMimeData(
            data, event.proposedAction(), -1, -1, QModelIndex()
        ):
            return Qt.IgnoreAction

        if is_own:
            return Qt.MoveAction

        for action in (Qt.CopyAction, Qt.LinkAction):
            if event.possibleActions() & action:
                return action

        return Qt.IgnoreAction

    def _mark_drop(self, pos: QPoint | None):
        if pos == self._drop_pos:
            return

        self._drop_pos = pos
        self.viewport().update()

    def _drop_line_y(self) -> int:
        """Where between the rows a drop goes, in the list as it is scrolled
        now: it scrolls under the pointer, near the top or bottom."""

        row = self.drop_row_at(self._drop_pos)
        count = self.model().rowCount()

        if row < count:
            y = self.rowViewportPosition(row)
        elif count:
            y = self.rowViewportPosition(count - 1) + self.rowHeight(count - 1)
        else:
            y = 0

        # on show at the very top and bottom
        half = DROP_LINE_PX // 2 + 1

        return max(half, min(y, self.viewport().height() - half))

    def _paint_drop_line(self, painter):
        y = self._drop_line_y()
        right = self.viewport().width() - DROP_LINE_PX

        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.palette().color(QPalette.Text), DROP_LINE_PX)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # a ring at its start, the line from it across the row
        radius = DROP_RING_RADIUS_PX
        center = QPoint(radius + DROP_LINE_PX, y)
        painter.drawEllipse(center, radius, radius)
        painter.drawLine(center.x() + radius, y, right, y)

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.model() is None:
            return

        is_empty = not self.model().rowCount()

        if not is_empty and self._drop_pos is None:
            return

        painter = QPainter(self.viewport())

        if is_empty:
            paint_empty_txt(self, painter, *self.empty_txt)

        if self._drop_pos is not None:
            self._paint_drop_line(painter)

        painter.end()


class MediaListDialog(QDialog):
    # how far reading has got, from the thread reading: which reading it
    # is, and what it says; see list_progress.Throttled
    _reading_progress = pyqtSignal(int, str, object, object)

    def __init__(
        self,
        registry,
        list_id,
        reading: ListReading,
        block=None,
        cells: Callable[[], list] | None = None,
        open_in_new_cell: Callable | None = None,
        parent=None,
    ):
        """The window on a list of the registry. With a cell, the one it was
        opened from: its item is marked, and items are played in it. cells
        tells the cells open, first to last in the grid, to number them;
        open_in_new_cell(list_id, place) plays an item in a new one."""

        self._is_set_up = False

        super().__init__(parent)

        # to be moved off the video it plays, to see the video beside it
        detach_modal_dialog(self)

        self._registry = registry
        self._list_id = list_id
        self._reading = reading
        self._block = block
        self._cells = cells or list
        self._open_in_new_cell = open_in_new_cell

        self._original = registry.get(list_id)

        # anything done to the list here since: what is asked about before
        # the window gives way to another's
        self._is_edited = False

        # closed: what is read after that has no list to go on
        self._is_done = False

        # read off the interface thread: what is added, and the list again;
        # each reading by a number of its own, for what an earlier one finds
        # once it was stopped to be let go of, and what to set to stop it
        self._background = OffThread(self)
        self._background.done.connect(self._on_read)
        self._read_serial = 0
        self._read_stop: threading.Event | None = None

        # the reading waited for done elsewhere: a linked list read again
        # from its source as the playlist opens
        self._is_read_elsewhere = False

        # what the list could not be read from its source for, said until it
        # is read or put away; and how it was last read, and from what, for
        # Try Again: the list's own source for None
        self._read_error: ReadError | None = None
        self._last_read: tuple[str, ListSource | None] = ("refresh", None)

        # shown to be going on, once it has for a while
        self._is_reading_shown = False
        self._reading_timer = QTimer(self)
        self._reading_timer.setSingleShot(True)
        self._reading_timer.setInterval(READING_SHOWN_AFTER_MS)
        self._reading_timer.timeout.connect(self._show_reading)

        self._checks = FileChecks(_is_there, self)
        # the files asked about, by uri_key: each asked once
        self._files_asked = set()
        self._checks.checked.connect(self._on_checked)

        # the videos' pictures, fetched as their rows come to be shown
        self._thumbnails = None
        if reading.fetch_thumbnail is not None:
            self._thumbnails = ThumbnailLoader(
                reading.fetch_thumbnail, THUMBNAIL_SIZE * 2, self
            )
            self._thumbnails.loaded.connect(self._on_thumbnail)

        # the rows near with their pictures still to be fetched, since when;
        # looked at every so often while there are any. The ones near as the
        # pictures are first shown are fetched at once: nothing was scrolled
        # past to get there
        self._near_since: dict[str, float] = {}
        self._is_first_sight = True
        self._sight_timer = QTimer(self)
        self._sight_timer.setInterval(THUMBNAIL_CHECK_MS)
        self._sight_timer.timeout.connect(self._fetch_thumbnails_near)
        self._first_sight_timer = QTimer(self)
        self._first_sight_timer.setSingleShot(True)
        self._first_sight_timer.setInterval(0)
        self._first_sight_timer.timeout.connect(self._fetch_thumbnails_near)

        # what is known of the items, looked up for as long as it takes,
        # the window closed meanwhile or not
        self._lookups = reading.lookups

        self._revealer = FolderRevealer(self)

        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(FIND_PAUSE_MS)
        self._find_timer.timeout.connect(self._apply_filter)

        # how long ago it was read said again every so often
        self._updated_timer = QTimer(self)
        self._updated_timer.setInterval(UPDATED_REFRESH_MS)
        self._updated_timer.timeout.connect(self._show_updated)
        self._updated_timer.start()

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(STATUS_MS)
        self._status_timer.timeout.connect(self._show_count)

        self.setMinimumSize(DIALOG_MIN_SIZE)
        self.resize(DIALOG_SIZE)

        self._ui_setup()
        self._ui_connect()

        self._update_look()
        self._show_view(self._view_wanted())
        self._reload()
        self._show_source()

        # on the group looked at last time
        if not self._group_combo.isHidden() and self._group_combo.currentData():
            self._apply_filter()
        self._show_shared()
        self._name_edit.setText(self._media_list.name)
        self._update_title()

        here = self._here_key()
        self._pick_keys([] if here is None else [here], current_key=here)

        self._show_count()
        self._show_lookup()

        # still being read again as the playlist opened, or not read
        if self._registry.is_being_read(self._list_id):
            self._on_reading_changed(self._list_id)
        else:
            self._say_read_error()

        self._list.setFocus()

        self._is_set_up = True

    @property
    def block(self):
        """The cell the window was opened on, None for none."""

        return self._block

    @property
    def list_id(self):
        return self._list_id

    @property
    def is_edited(self) -> bool:
        """Whether anything was done to the list here since the window was
        opened; not by a cell learning how long an item is."""

        return self._is_edited

    @property
    def _media_list(self) -> MediaList:
        media_list = self._registry.get(self._list_id)

        return media_list if media_list is not None else MediaList(id=self._list_id)

    def _ui_setup(self):
        # what the box is said in it while it is empty, and over it
        name_txt = translate("Dialog - List", "Name of the list")

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(name_txt)
        self._name_edit.setToolTip(name_txt)
        self._name_edit.setAccessibleName(name_txt)

        form = QVBoxLayout()
        form.setSpacing(10)
        form.addWidget(self._name_edit)
        form.addWidget(self._source_panel_setup())

        self._shared_icon = QLabel()
        self._shared_icon.setPixmap(QIcon.fromTheme("information").pixmap(16, 16))
        self._shared_label = QLabel()
        self._shared_label.setWordWrap(True)

        shared = QHBoxLayout()
        shared.setSpacing(8)
        shared.addWidget(self._shared_icon, 0, Qt.AlignTop)
        shared.addWidget(self._shared_label, 1)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText(
            translate("Dialog - List", "Find on the list")
        )
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.addAction(QIcon.fromTheme("zoom"), QLineEdit.LeadingPosition)

        self._group_combo = ElidedComboBox()
        self._group_combo.setMinimumWidth(170)
        # how many items each group had, the last time it was filled
        self._group_counts = None

        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(self._filter_edit, 1)
        filters.addWidget(self._group_combo)
        self._filters = filters

        self._model = ListItemsModel(self)

        self._list = ItemList()
        self._list.setModel(self._model)
        self._list.itemDelegate().thumbnails = self._thumbnails
        # what is near changes as the list is scrolled, resized, found in
        self._list.itemDelegate().picture_wanted.connect(self._watch_near)
        self._list.verticalScrollBar().valueChanged.connect(self._watch_near)
        self._list.verticalScrollBar().rangeChanged.connect(self._watch_near)
        self._model.modelReset.connect(self._watch_near)
        self._model.layoutChanged.connect(self._watch_near)

        header = self._list.header()
        header.setStretchLastSection(False)
        # sized for the longest number there is rather than by every row,
        # which for a channel list is a few hundred thousand to measure
        header.setSectionResizeMode(Column.NUMBER, QHeaderView.Fixed)
        header.setSectionResizeMode(Column.TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(Column.LENGTH, QHeaderView.Fixed)
        header.resizeSection(Column.LENGTH, LENGTH_COLUMN_PX)

        # the count, or what was just done
        self._hint = QLabel()
        self._hint.setWordWrap(True)

        # how far looking up what is known of the items has got, in the
        # count's place while it goes on
        self._lookup_label = QLabel()
        self._lookup_bar = QProgressBar()
        self._lookup_bar.setTextVisible(False)
        self._lookup_bar.setFixedHeight(PROGRESS_BAR_HEIGHT_PX)
        # what a site that turned lookups away says, in the bar's place
        self._lookup_refused = ElidedLabel()
        self._lookup_button = QToolButton()
        self._lookup_button.setAutoRaise(True)
        self._lookup_button.setIconSize(QSize(LOOKUP_ICON_PX, LOOKUP_ICON_PX))
        self._lookup_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self._lookup_line = QWidget()
        lookup = QHBoxLayout(self._lookup_line)
        lookup.setContentsMargins(0, 0, 0, 0)
        lookup.setSpacing(8)
        lookup.addWidget(self._lookup_label)
        lookup.addWidget(self._lookup_bar, 1)
        lookup.addWidget(self._lookup_refused, 1)
        lookup.addWidget(self._lookup_button)
        self._lookup_line.hide()

        self._add_files_button = dialog_button(
            "add-files", translate("Dialog - List", "Add Files…")
        )
        self._add_folder_button = dialog_button(
            "add-folder", translate("Dialog - List", "Add Folder…")
        )
        self._add_links_button = dialog_button(
            "add-url", translate("Dialog - List", "Add Links…")
        )
        self._view_button = dialog_button(
            "list-view", translate("Dialog - List", "View")
        )
        self._view_menu = CustomMenu(parent=self._view_button)
        self._view_button.setMenu(self._view_menu)

        self._sort_button = dialog_button("sort", translate("Dialog - List", "Sort"))
        self._sort_menu = CustomMenu(parent=self._sort_button)
        self._sort_button.setMenu(self._sort_menu)

        self._export_button = dialog_button(
            "save-playlist",
            translate("Dialog - List", "Export…"),
            translate("Dialog - List", "Save the list as an M3U file"),
        )

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(self._add_files_button)
        tools.addWidget(self._add_folder_button)
        tools.addWidget(self._add_links_button)
        tools.addStretch(1)
        tools.addWidget(self._view_button)
        tools.addWidget(self._sort_button)

        bottom = QHBoxLayout()
        bottom.addWidget(self._export_button)
        bottom.addStretch(1)
        bottom.addWidget(self._buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)
        root.addLayout(form)
        root.addLayout(shared)
        root.addLayout(filters)
        root.addWidget(self._list, 1)
        root.addSpacing(-4)
        root.addWidget(self._hint)
        root.addWidget(self._lookup_line)
        root.addLayout(tools)
        root.addSpacing(4)
        root.addLayout(bottom)

    def _source_panel_setup(self) -> QFrame:
        """Where the list was read from, in a panel of its own: what it is
        and where, the button to read it again in its corner, and how far
        reading has got under them. The button stops it while it reads."""

        self._source_icon = QLabel()

        self._source_title = QLabel()
        font = self._source_title.font()
        font.setBold(True)
        self._source_title.setFont(font)

        # said of a linked list, in a box of its own beside what it is, with
        # the button to unlink it in the box
        self._linked_tag = self._linked_tag_setup()
        self._linked_label.setToolTip(
            translate(
                "Dialog - List",
                "Updates from its source. Only your changes are saved in the"
                " playlist. Unlink it to add items or reorder them by hand.",
            )
        )

        # when it was last read from its source, quieter still, in the room
        # the rest of the row leaves; for a linked list, how often it is
        # read again picked from it
        self._updated_button = FittedButton()
        self._update_menu = CustomMenu(parent=self._updated_button)
        self._update_menu.aboutToShow.connect(
            lambda: self._fill_update_menu(self._update_menu)
        )

        self._source_copy_button = self._corner_button()
        self._source_copy_button.setIcon(QIcon.fromTheme("copy"))

        self._source_button = self._corner_button()

        # where it came from, quieter than what it is: the role rather than a
        # colour, which the panel's style sheet would not let it be given
        self._source_label = ElidedLabel()
        self._source_label.setForegroundRole(QPalette.PlaceholderText)

        # how far reading the list again, or what is added, has got
        self._progress_label = ElidedLabel()
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(PROGRESS_BAR_HEIGHT_PX)

        self._progress_box = QWidget()
        progress = QVBoxLayout(self._progress_box)
        progress.setContentsMargins(0, 4, 0, 0)
        progress.setSpacing(4)
        progress.addWidget(self._progress_label)
        progress.addWidget(self._progress_bar)

        self._show_progress(None)

        # what it could not be read for, in the same place
        self._error_box = self._read_error_setup()

        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(self._source_icon)
        head.addWidget(self._source_title)
        head.addWidget(self._linked_tag)
        head.addStretch(1)
        head.addWidget(self._updated_button)
        head.addWidget(self._source_copy_button)
        head.addWidget(self._source_button)

        self._source_panel = QFrame()
        self._source_panel.setObjectName("sourcePanel")
        self._source_panel.setContextMenuPolicy(Qt.CustomContextMenu)
        self._source_panel.setStyleSheet(
            "#sourcePanel { border: 1px solid palette(mid); border-radius: 6px;"
            " background: palette(base); }"
        )

        panel = QVBoxLayout(self._source_panel)
        panel.setContentsMargins(12, 6, 6, 10)
        panel.setSpacing(4)
        panel.addLayout(head)
        panel.addWidget(self._source_label)
        panel.addWidget(self._progress_box)
        panel.addWidget(self._error_box)

        return self._source_panel

    def _read_error_setup(self) -> QWidget:
        """What the list could not be read for: the sign, a few words in
        bold and a quieter line under them, and Try Again and ✕ after."""

        self._error_icon = QLabel()
        self._error_icon.setAlignment(Qt.AlignTop)
        # level with the words' first line
        self._error_icon.setContentsMargins(0, 2, 0, 0)

        self._error_title = QLabel()
        font = self._error_title.font()
        font.setBold(True)
        self._error_title.setFont(font)

        self._error_about = QLabel()
        self._error_about.setWordWrap(True)
        self._error_about.setForegroundRole(QPalette.PlaceholderText)

        self._error_again_button = dialog_button(
            "reload", translate("Dialog - List", "Try Again")
        )
        self._error_again_button.clicked.connect(self._try_again)

        self._error_hide_button = self._corner_button()
        self._error_hide_button.setIcon(QIcon.fromTheme("cross"))
        self._error_hide_button.setIconSize(
            QSize(HIDE_ERROR_ICON_PX, HIDE_ERROR_ICON_PX)
        )
        self._error_hide_button.setToolTip(translate("Dialog - List", "Hide"))
        self._error_hide_button.clicked.connect(self._hide_read_error)

        words = QVBoxLayout()
        words.setSpacing(2)
        words.addWidget(self._error_title)
        words.addWidget(self._error_about)

        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._error_icon)
        layout.addLayout(words, 1)
        layout.addWidget(self._error_again_button, 0, Qt.AlignVCenter)
        layout.addWidget(self._error_hide_button, 0, Qt.AlignVCenter)

        box.hide()

        return box

    def _linked_tag_setup(self) -> QFrame:
        tag = QFrame()
        tag.setObjectName("linkedTag")
        tag.setStyleSheet(
            "#linkedTag { border: 1px solid palette(mid); border-radius: 4px; }"
            " #unlinkButton { border: none; border-radius: 3px; padding: 1px; }"
            " #unlinkButton:hover { background: palette(highlight); }"
        )

        self._linked_label = QLabel(translate("Dialog - List", "Linked"))
        self._linked_label.setForegroundRole(QPalette.PlaceholderText)

        self._unlink_button = _TagButton()
        self._unlink_button.setObjectName("unlinkButton")
        self._unlink_button.setIcon(QIcon.fromTheme("cross"))
        self._unlink_button.setToolTip(translate("Dialog - List", "Unlink"))
        self._unlink_button.setAccessibleName(translate("Dialog - List", "Unlink"))

        layout = QHBoxLayout(tag)
        layout.setContentsMargins(5, 1, 1, 1)
        layout.setSpacing(3)
        layout.addWidget(self._linked_label)
        layout.addWidget(self._unlink_button)

        return tag

    def _corner_button(self) -> QToolButton:
        # flat, the frame only under the pointer, as the panel's own
        button = QToolButton()
        button.setAutoRaise(True)
        button.setIconSize(QSize(SOURCE_ICON_PX, SOURCE_ICON_PX))
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)

        return button

    def _ui_connect(self):
        self._reading_progress.connect(self._on_reading_progress)

        # the registry's, the cell's and the lookups', let go of once the
        # dialog is done: they go on after it
        self._outside_connections = [
            (self._registry.changed, self._on_list_changed),
            (self._registry.replaced, self.accept),
            (self._registry.reading_changed, self._on_reading_changed),
            (self._registry.reading_progress, self._on_reading_elsewhere),
        ]
        if self._block is not None:
            self._outside_connections += [
                (self._block.list_place_change, self._on_place),
                (self._block.closing, self.accept),
            ]
        if self._lookups is not None:
            self._outside_connections += [
                (self._lookups.changed, self._on_lookup_changed),
                (self._lookups.finished, self._on_lookup_finished),
                (self._lookups.learned, self._on_learned),
            ]
        for signal, slot in self._outside_connections:
            signal.connect(slot)

        self._name_edit.textEdited.connect(self._rename_list)
        self._source_button.clicked.connect(self._on_source_button)
        self._source_copy_button.clicked.connect(self._copy_source)
        self._unlink_button.clicked.connect(self._unlink)
        self._source_panel.customContextMenuRequested.connect(self._show_source_menu)

        self._filter_edit.textChanged.connect(self._find)
        self._group_combo.currentIndexChanged.connect(self._apply_filter)

        # edits are made once the editor or the drag they came from is
        # done: made at once, they would take the rows from under it
        self._model.renamed.connect(self._rename, Qt.QueuedConnection)
        self._model.moved.connect(self._move, Qt.QueuedConnection)
        self._model.dropped.connect(self._add_uris, Qt.QueuedConnection)

        self._list.doubleClicked.connect(lambda _index: self._play())
        self._list.play_requested.connect(self._play)
        self._list.rename_requested.connect(self._edit_name)
        self._list.remove_requested.connect(self._remove)
        self._list.add_requested.connect(self._add_files)
        self._list.copy_requested.connect(self._copy)
        self._list.paste_requested.connect(self._paste)
        self._list.menu_requested.connect(self._show_row_menu)
        self._list.list_menu_requested.connect(self._show_list_menu)

        self._add_files_button.clicked.connect(self._add_files)
        self._add_folder_button.clicked.connect(self._add_folder)
        self._add_links_button.clicked.connect(self._add_links)
        self._view_menu.aboutToShow.connect(self._fill_view_menu)
        self._sort_menu.aboutToShow.connect(self._fill_sort_menu)
        self._export_button.clicked.connect(self._export)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        self._lookup_button.clicked.connect(self._on_lookup_button)

    def reject(self):
        # the list as it was, where it still is and was edited here; not
        # as it was before it was read again meanwhile
        if (
            self._is_edited
            and self._original is not None
            and self._registry.get(self._list_id)
        ):
            self._registry.put(self._original)

        super().reject()

    def done(self, result):
        self._is_done = True

        # a read still going is stopped: what it finds has nowhere to go
        if self._read_stop is not None:
            self._read_stop.set()

        self._checks.stop()

        if self._thumbnails is not None:
            self._thumbnails.stop()
        self._sight_timer.stop()
        self._first_sight_timer.stop()
        self._updated_timer.stop()

        # a lookup goes on, with nothing here to show it
        for signal, slot in self._outside_connections:
            with contextlib.suppress(TypeError, RuntimeError):
                signal.disconnect(slot)
        self._outside_connections = []

        super().done(result)

    def changeEvent(self, event):
        super().changeEvent(event)

        if not self._is_set_up:
            return

        if event.type() in {
            event.PaletteChange,
            event.FontChange,
            event.StyleChange,
        }:
            self._update_look()

        # cells opened and closed in the player meanwhile
        if event.type() == event.ActivationChange and self.isActiveWindow():
            self._show_shared()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._fit_group_combo()

    def _fit_group_combo(self):
        """The group box no wider than its share of the row, however long
        the groups' names: the rest is for finding by name."""

        margins = self.layout().contentsMargins()
        row = self.width() - margins.left() - margins.right()
        share = int((row - self._filters.spacing()) * GROUP_COMBO_SHARE)

        self._group_combo.setMaximumWidth(max(self._group_combo.minimumWidth(), share))

    def _update_look(self):
        self._model.set_look(self._list.palette(), self._list.font())

    # showing the list

    def _reload(self):
        media_list = self._media_list
        base = list_base(media_list)

        # gone through again only where the items changed, not the list's
        # name or how it is kept: a channel list's took a tenth of a second
        # at each key typed in its name
        if media_list.items is not self._model.items or base != self._model.base:
            picked = self._picked_keys()
            current = self._current_key()

            self._model.set_items(media_list.items, base)
            self._fill_groups(media_list)
            self._check_files(media_list)

            self._pick_keys(picked, current_key=current)

        self._model.set_linked(media_list.is_linked)
        self._list.empty_txt = _empty_txt(media_list)
        self._model.set_here(self._here_key())
        self._fit_number_column(len(media_list.items))

        self._update_buttons()

    def _view_wanted(self) -> ListView:
        """What the list was looked at by last, or else the playlist's: by
        its pictures, where it has them and the playlist says so."""

        view = self._registry.remembered_view(self._list_id)
        has_thumbnails = _has_thumbnails(self._media_list.items)

        if view == ListView.THUMBNAILS and not has_thumbnails:
            view = None

        if view is not None:
            return view

        if has_thumbnails and PlaylistSettings().get("playlist/list_thumbnails"):
            return ListView.THUMBNAILS

        return PlaylistSettings().get("playlist/list_view")

    def _show_view(self, view: ListView):
        self._view = view

        self._model.set_view(view)
        self._list.show_rows_for(view)

        if view == ListView.THUMBNAILS:
            self._is_first_sight = True

        # a path or a link alone: its start, and the file's name or what
        # tells a link apart
        self._list.setTextElideMode(
            Qt.ElideMiddle if view == ListView.LOCATIONS else Qt.ElideRight
        )

    def _set_view(self, view: ListView):
        self._show_view(view)
        self._registry.remember_view(self._list_id, view)

        # found by what it is shown by now
        if self._filter_edit.text().strip():
            self._apply_filter()

        current = self._list.currentIndex()
        if current.isValid():
            self._list.scrollTo(current)

    def _on_thumbnail(self, _url: str):
        """A picture came, or will not: its row drawn again, where it is."""

        self._list.viewport().update()

    def _watch_near(self, *_):
        """The rows near looked at every so often, while their pictures are
        to be shown."""

        if self._thumbnails is None or self._view != ListView.THUMBNAILS:
            return

        if not self._sight_timer.isActive():
            self._sight_timer.start()

        if self._is_first_sight:
            self._first_sight_timer.start()

    def _fetch_thumbnails_near(self):
        """The pictures of the rows near for long enough fetched, the ones
        in sight first; the rest waited for while they stay near, and
        forgotten once they are not."""

        loader = self._thumbnails

        if loader is None or self._is_done or self._view != ListView.THUMBNAILS:
            self._sight_timer.stop()
            return

        # not laid out yet, to tell what is in sight
        if not self._list.isVisible():
            return

        near = self._thumbnails_near()

        loader.let_go_except(near)

        now = time.monotonic()
        settle = THUMBNAIL_SETTLE_MS / 1000

        waiting = {}

        for url in near:
            if not loader.is_to_fetch(url):
                continue

            since = self._near_since.get(url, now)

            if self._is_first_sight or now - since >= settle:
                loader.fetch(url)
            else:
                waiting[url] = since

        self._is_first_sight = False
        self._near_since = waiting

        if not waiting:
            self._sight_timer.stop()

    def _thumbnails_near(self) -> list[str]:
        """The pictures of the rows near: the ones in sight, then the views
        of rows below them, then above, the nearest first."""

        count = self._model.rowCount()

        if not count:
            return []

        table = self._list
        first = table.rowAt(0)
        last = table.rowAt(table.viewport().height() - 1)

        if first < 0:
            return []

        if last < 0:
            last = count - 1

        ahead = (last - first + 1) * THUMBNAIL_AHEAD_VIEWS

        rows = [
            *range(first, last + 1),
            *range(last + 1, min(count, last + 1 + ahead)),
            *range(first - 1, max(-1, first - 1 - ahead), -1),
        ]

        urls = []
        for row in rows:
            url = self._model.data(self._model.index(row, Column.TITLE), THUMBNAIL_ROLE)

            if url is not None:
                urls.append(url)

        return urls

    def _fit_number_column(self, count: int):
        digits = self._list.fontMetrics().horizontalAdvance("8" * len(str(count)))

        # the play mark, the room around it and the number, and the row's
        # own padding either side
        width = HERE_ICON_PX + 8 + digits + 12 + 8

        self._list.header().resizeSection(Column.NUMBER, width)

    def _here_key(self) -> int | None:
        if self._block is None or self._block.video_params is None:
            return None

        if self._block.video_params.list_id != self._list_id:
            return None

        item = self._block.list_item

        return None if item is None else item.key

    def _on_place(self, _place_txt=None):
        params = self._block.video_params if self._block is not None else None

        # the cell put on another list, or on none, meanwhile
        if params is not None and params.list_id != self._list_id:
            self.accept()
            return

        here = self._here_key()
        is_gone_on = here != self._model.here_key

        self._model.set_here(here)

        # followed to the item it goes on to; not as the list is edited, its
        # place said again then, wherever the list is scrolled to
        if not is_gone_on:
            return

        row = self._model.row_of_key(here)
        if row is not None:
            self._list.scrollTo(self._model.index(row, 0))

    def _on_list_changed(self, list_id):
        if list_id != self._list_id:
            return

        if self._registry.get(self._list_id) is None:
            # taken away from under the window
            self.accept()
            return

        self._reload()
        self._show_source()
        self._show_count_unless_saying()

    def _on_checked(self, key: str, is_there: bool):
        self._model.set_missing(key, not is_there)

    def _check_files(self, media_list: MediaList):
        for item in media_list.items:
            if not isinstance(item.uri, Path):
                continue

            key = uri_key(item.uri)

            if key not in self._files_asked:
                self._files_asked.add(key)
                self._checks.check(key, item.uri)

    def _fill_groups(self, media_list: MediaList):
        counts = Counter(item.group or "" for item in media_list.items)

        # as they were: the thousands of a channel list's not put in again
        if counts == self._group_counts:
            return

        self._group_counts = counts

        groups = sorted((group for group in counts if group), key=natural_key)

        self._group_combo.setVisible(bool(groups))

        if not groups:
            return

        # the one looked at, or the one looked at last time the window was
        # open on the list
        if self._group_combo.count():
            wanted = self._group_combo.currentData()
        else:
            wanted = self._registry.remembered_group(self._list_id)

        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem(
            translate("Dialog - List", "All groups ({COUNT})").format(
                COUNT=count_txt(len(media_list.items))
            ),
            None,
        )
        for group in groups:
            self._group_combo.addItem(f"{group} ({count_txt(counts[group])})", group)
        if counts.get(""):
            self._group_combo.addItem(
                translate("Dialog - List", "No group ({COUNT})").format(
                    COUNT=count_txt(counts[""])
                ),
                "",
            )

        index = self._group_combo.findData(wanted)
        self._group_combo.setCurrentIndex(max(index, 0))
        self._group_combo.blockSignals(False)

        cap_popup_height(self._group_combo, self._group_combo.count())

    def _find(self, _text=None):
        if len(self._model.items) > FIND_AT_ONCE_ITEMS:
            self._find_timer.start()
        else:
            self._apply_filter()

    def _apply_filter(self, *_):
        picked = self._picked_keys()
        current = self._current_key()

        group = (
            None if self._group_combo.isHidden() else self._group_combo.currentData()
        )

        self._model.set_filter(self._filter_edit.text(), group)

        if not self._group_combo.isHidden():
            self._registry.remember_group(self._list_id, group)

        self._pick_keys(picked, current_key=current)
        self._update_buttons()
        self._show_count()

    def _show_source(self):
        """Where the list was read from; for one read from nowhere, the
        panel only while what is added is read, to say how far it has got."""

        source = self._media_list.source

        self._source_panel.setVisible(source is not None or self._is_reading_shown)
        self._source_label.setVisible(source is not None)

        if source is None:
            icon = "add-files"
            title = translate("Dialog - List", "Adding to the list")
        else:
            icon, title = _source_kind(source)
            self._source_label.setText(str(source.location))

        self._source_icon.setPixmap(
            QIcon.fromTheme(icon).pixmap(SOURCE_ICON_PX, SOURCE_ICON_PX)
        )
        self._source_title.setText(title)
        self._show_updated()
        self._linked_tag.setVisible(source is not None and self._media_list.is_linked)

        self._source_copy_button.setVisible(source is not None)
        if source is not None:
            self._source_copy_button.setToolTip(_copy_source_txt(source))

        self._show_source_button(source is not None)

    def _show_updated(self):
        """When the list was last read from its source, how long ago, and
        under the pointer the date and time of it and when it is read
        next; for a linked list, a button to pick how often it is read
        again."""

        media_list = self._media_list
        button = self._updated_button
        source = media_list.source
        read_at = media_list.read_at if source is not None else None

        is_choosable = source is not None and media_list.is_linked
        button.set_choosable(is_choosable)
        button.setMenu(self._update_menu if is_choosable else None)

        if read_at is None:
            # not known when it was read: still how often it is to be
            update_txt = translate("Dialog - List", "Update")
            button.set_texts(*([update_txt] if is_choosable else []))
            button.setToolTip("")
            return

        if time.time() - read_at < 60:
            text = translate("Dialog - List", "Updated just now")
            short = translate("Dialog - List", "just now")
        else:
            short = published_txt(read_at)
            text = translate("Dialog - List", "Updated {WHEN}").format(WHEN=short)

        when = QLocale().toString(
            QDateTime.fromSecsSinceEpoch(read_at), QLocale.ShortFormat
        )
        lines = [translate("Dialog - List", "Last updated: {DATE}").format(DATE=when)]

        if is_choosable:
            lines.append(self._next_update_txt(media_list))

        # how long ago alone where there is no room for more
        button.set_texts(text, short)
        button.setToolTip("\n".join(lines))

    def _next_update_txt(self, media_list: MediaList) -> str:
        playlist_update = PlaylistSettings().get("playlist/list_update")
        update = update_of(media_list, playlist_update)

        if update == ListUpdate.MANUAL:
            return translate("Dialog - List", "Updates only on Refresh")

        next_at = next_update_at(media_list, playlist_update)

        if next_at is None:
            return translate("Dialog - List", "Next update: when the playlist opens")

        return translate("Dialog - List", "Next update: {WHEN}").format(
            WHEN=in_txt(next_at - time.time())
        )

    def _fill_update_menu(self, menu):
        """How often the list is read again, as the playlist says or its
        own: the one it is checked; those more often than a site may like,
        for a list from a link, with the warning sign."""

        menu.clear()

        media_list = self._media_list
        source = media_list.source
        playlist_update = PlaylistSettings().get("playlist/list_update")
        names = list_update_txts()
        is_free = not self._is_reading

        blank = QIcon.fromTheme("empty")
        choice = checked_icon(blank, is_choice=True)
        warned = checked_icon(QIcon.fromTheme("warning"), is_choice=True)

        def add(title, interval_s, is_checked, slot):
            icon = warned if is_short(interval_s, source) else choice
            action = menu.addAction(icon, title, slot)
            action.setCheckable(True)
            action.setChecked(is_checked)
            action.setEnabled(is_free)

        add(
            translate("Dialog - List", "Playlist default ({UPDATE})").format(
                UPDATE=names[playlist_update]
            ),
            INTERVALS_S.get(playlist_update),
            media_list.update is None,
            lambda: self._set_update(None),
        )

        menu.addSeparator()

        for update in (
            ListUpdate.ON_LOAD,
            ListUpdate.FIVE_MINUTES,
            ListUpdate.FIFTEEN_MINUTES,
            ListUpdate.HOURLY,
            ListUpdate.SIX_HOURS,
            ListUpdate.DAILY,
        ):
            add(
                names[update],
                INTERVALS_S.get(update),
                media_list.update == update,
                lambda update=update: self._set_update(update),
            )

        # one of the viewer's own, said as it is, and Custom… to set another
        if media_list.update == ListUpdate.CUSTOM and media_list.update_every_s:
            add(
                every_txt(media_list.update_every_s),
                media_list.update_every_s,
                True,
                lambda: None,
            )

        menu.addAction(
            blank, translate("Dialog - List", "Custom…"), self._choose_update
        ).setEnabled(is_free)

        menu.addSeparator()

        add(
            names[ListUpdate.MANUAL],
            None,
            media_list.update == ListUpdate.MANUAL,
            lambda: self._set_update(ListUpdate.MANUAL),
        )

    def _set_update(self, update: ListUpdate | None, every_s: int | None = None):
        """How often the list is read again from now on: its own, or as
        the playlist says for None."""

        if self._is_reading:
            return

        self._apply(
            self._media_list.model_copy(
                update={"update": update, "update_every_s": every_s}
            )
        )
        self._show_updated()

    def _choose_update(self):
        """How often, as the viewer says: every so many minutes, hours or
        days."""

        media_list = self._media_list
        playlist_update = PlaylistSettings().get("playlist/list_update")

        every_s = self._ask_update_every(
            interval_of(media_list, playlist_update) or DEFAULT_CUSTOM_UPDATE_S,
            media_list.source is not None
            and media_list.source.kind == ListSourceKind.URL,
        )

        if every_s is not None:
            self._set_update(ListUpdate.CUSTOM, every_s)

    def _ask_update_every(self, every_s: int, is_from_site: bool) -> int | None:
        return UpdateEveryDialog.ask(every_s, is_from_site, parent=self)

    def _show_source_button(self, has_source: bool):
        """To read the list again; to stop reading, while it reads."""

        button = self._source_button

        if self._is_reading_shown:
            button.setIcon(QIcon.fromTheme("close"))
            button.setText(translate("Dialog - List", "Stop"))
            button.setToolTip(translate("Dialog - List", "Stop"))
            button.show()
            return

        button.setIcon(QIcon.fromTheme("reload"))
        button.setText(translate("Dialog - List", "Refresh"))
        button.setToolTip(
            translate(
                "Dialog - List",
                "Update from the source. Your changes are kept.",
            )
        )
        button.setVisible(has_source)

    def _on_source_button(self):
        if self._is_reading_shown:
            self._stop_reading()
        else:
            self._refresh()

    def _show_shared(self):
        numbers = [
            number
            for number, block in enumerate(self._cells(), 1)
            if block is not self._block
            and block.video_params is not None
            and block.video_params.list_id == self._list_id
        ]

        self._shared_icon.setVisible(bool(numbers))
        self._shared_label.setVisible(bool(numbers))

        if not numbers:
            return

        if self._block is None:
            txt = translate(
                "Dialog - List",
                "Playing in cells {NUMBERS}.",
            ).format(NUMBERS=", ".join(map(str, numbers)))
        elif len(numbers) == 1:
            txt = translate(
                "Dialog - List",
                "Cell {NUMBER} also plays this list.",
            ).format(NUMBER=numbers[0])
        else:
            txt = translate(
                "Dialog - List",
                "Cells {NUMBERS} also play this list.",
            ).format(NUMBERS=", ".join(map(str, numbers)))

        self._shared_label.setText(txt)

    def _update_title(self):
        name = self._media_list.name

        if name:
            self.setWindowTitle(
                translate("Dialog - List", "List — {NAME}").format(NAME=name)
            )
        else:
            self.setWindowTitle(translate("Dialog - List", "List"))

    def _show_count(self):
        items = self._media_list.items

        if self._model.is_filtered:
            txt = translate("Dialog - List", "Shown: {SHOWN} of {COUNT}").format(
                SHOWN=count_txt(self._model.rowCount()), COUNT=count_txt(len(items))
            )
        else:
            txt = translate("Dialog - List", "Items: {COUNT}").format(
                COUNT=count_txt(len(items))
            )

            # the whole length, once every item's is known
            if items and all(item.duration_ms is not None for item in items):
                total_ms = sum(item.duration_ms for item in items)
                txt = f"{txt} · {get_time_txt(total_ms // 1000, strip=True)}"

        self._hint.setText(txt)

    def _show_count_unless_saying(self):
        if not self._status_timer.isActive():
            self._show_count()

    def _say(self, text: str):
        self._hint.setText(text)
        self._status_timer.start()

    def _update_buttons(self):
        count = len(self._media_list.items)

        # what they do waits for reading as soon as it starts
        is_free = not self._is_reading_shown

        self._name_edit.setEnabled(is_free)
        self._sort_button.setEnabled(count > 1 and is_free)
        self._unlink_button.setEnabled(is_free)
        self._updated_button.setEnabled(is_free)

        # a linked list has what its source has, and nothing else
        is_linked = self._media_list.is_linked

        for button in (
            self._add_files_button,
            self._add_folder_button,
            self._add_links_button,
        ):
            button.setEnabled(is_free and not is_linked)
            button.setToolTip(_unlink_to_add_txt() if is_linked else "")

    # picking rows

    def _picked_rows(self) -> list[int]:
        # by the runs of rows picked, rather than by an index made for each
        # of them: tens of thousands picked take seconds that way
        rows = set()

        for picked in self._list.selectionModel().selection():
            rows.update(range(picked.top(), picked.bottom() + 1))

        return sorted(rows)

    def _picked_items(self, rows=None) -> list[ListItem]:
        rows = self._picked_rows() if rows is None else rows

        return [self._model.item_at(row) for row in rows]

    def _picked_keys(self) -> list[int]:
        return [item.key for item in self._picked_items()]

    def _current_key(self) -> int | None:
        index = self._list.currentIndex()

        if not index.isValid():
            return None

        return self._model.item_at(index.row()).key

    def _pick_keys(self, keys, current_key=None):
        selection = self._list.selectionModel()

        rows = [self._model.row_of_key(key) for key in keys]
        rows = [row for row in rows if row is not None]

        # picked at once, a run of rows at a time: each row picked on its
        # own is merged into those picked before, which for thousands of
        # rows takes seconds
        runs = []
        for row in sorted(set(rows)):
            if runs and row == runs[-1][1] + 1:
                runs[-1][1] = row
            else:
                runs.append([row, row])

        picked = QItemSelection()
        for first, last in runs:
            picked.select(self._model.index(first, 0), self._model.index(last, 0))

        selection.select(picked, selection.ClearAndSelect | selection.Rows)

        current_row = self._model.row_of_key(current_key)
        if current_row is None and rows:
            current_row = rows[-1]

        if current_row is not None:
            index = self._model.index(current_row, 0)
            selection.setCurrentIndex(index, selection.NoUpdate)
            self._list.scrollTo(index)

    # edits

    def _apply(self, media_list: MediaList, picked=None):
        """The list as it is to be now: the registry tells the cells and
        this window alike."""

        # read again with nothing new is the same list
        if media_list != self._media_list:
            self._is_edited = True

        self._registry.put(media_list)

        if picked is not None:
            self._pick_keys(picked)

        self._update_buttons()

    def _rename_list(self, name: str):
        if self._is_reading:
            return

        self._apply(self._media_list.model_copy(update={"name": name.strip()}))
        self._update_title()

    def _edit_name(self):
        index = self._list.currentIndex()

        if not index.isValid() or self._is_reading:
            return

        self._list.edit(self._model.index(index.row(), Column.TITLE))

    def _rename(self, key: int, name: str):
        media_list = self._media_list
        item = media_list.item_by_key(key)

        if item is None or self._is_reading:
            return

        name = name.strip()

        # its own name back, or none, is no name of the list's
        own_name = item_name(
            item.model_copy(update={"title": None}), list_base(media_list)
        )
        title = None if not name or name == own_name else name

        if title == item.title:
            return

        self._is_edited = True
        self._registry.rename_item(self._list_id, key, title)

    def _remove(self):
        rows = self._picked_rows()

        if not rows or self._is_reading:
            return

        picked = self._picked_items(rows)

        media_list = self._media_list
        gone = {item.key for item in picked}

        # the one after the last taken off to go on from
        next_row = rows[-1] + 1
        next_key = (
            self._model.item_at(next_row).key
            if next_row < self._model.rowCount()
            else None
        )

        kept = tuple(item for item in media_list.items if item.key not in gone)

        self._apply(
            with_removed(media_list, picked).model_copy(update={"items": kept}),
            picked=[] if next_key is None else [next_key],
        )

        self._say(
            translate("Dialog - List", "Removed: {COUNT}").format(
                COUNT=count_txt(len(picked))
            )
        )

    def _move(self, keys: tuple, place: int):
        media_list = self._media_list
        keys = set(keys)
        moving = [item for item in media_list.items if item.key in keys]

        if not moving or self._is_reading:
            return

        before = media_list.items[:place]
        after = media_list.items[place:]

        items = (
            *(item for item in before if item.key not in keys),
            *moving,
            *(item for item in after if item.key not in keys),
        )

        self._apply(
            media_list.model_copy(
                update={"items": items, "sort": None, "is_reversed": False}
            ),
            picked=[item.key for item in moving],
        )

    def _move_to_top(self):
        self._move(tuple(self._picked_keys()), 0)

    def _move_to_bottom(self):
        self._move(tuple(self._picked_keys()), len(self._media_list.items))

    def _sort(self, how: str):
        if self._is_reading:
            return

        media_list = self._media_list

        # kept, as is turning it round, for a list read again to be put in
        # the same order
        if how == "reverse":
            changes = {
                "items": media_list.items[::-1],
                "is_reversed": not media_list.is_reversed,
            }
        else:
            sort = ListSort(how)
            items = sorted_items(media_list.items, sort, list_base(media_list))

            # a linked list's Reverse is a setting of its own, kept; on a
            # list kept whole, sorting is done once and is what it says
            is_reversed = media_list.is_linked and media_list.is_reversed

            changes = {
                "items": tuple(items[::-1] if is_reversed else items),
                "sort": sort,
                "is_reversed": is_reversed,
            }

        self._apply(media_list.model_copy(update=changes), picked=self._picked_keys())

    def _fill_view_menu(self):
        menu = self._view_menu
        menu.clear()

        icon = checked_icon(QIcon.fromTheme("empty"), is_choice=True)

        for view, title in _view_txts(self._media_list.items).items():
            action = menu.addAction(icon, title, lambda view=view: self._set_view(view))
            action.setCheckable(True)
            action.setChecked(view == self._view)

    def _fill_sort_menu(self):
        menu = self._sort_menu
        menu.clear()

        media_list = self._media_list
        items = media_list.items

        entries = [
            ("name", translate("Dialog - List", "By Name")),
            ("length", translate("Dialog - List", "By Length")),
        ]

        # what it is sorted by offered, whatever its items say now
        if media_list.sort == ListSort.VIEWS or any(
            view_count_of(item) is not None for item in items
        ):
            entries.append(("views", translate("Dialog - List", "By Views")))

        if media_list.sort == ListSort.PUBLISHED or any(
            published_of(item) is not None for item in items
        ):
            entries.append(
                ("published", translate("Dialog - List", "By Date Published"))
            )

        if media_list.sort == ListSort.GROUP or any(item.group for item in items):
            entries.append(("group", translate("Dialog - List", "By Group")))

        # a blank icon for the rows with none: sized as though no row had
        # one, their names would run off the menu's edge
        blank = QIcon.fromTheme("empty")

        if media_list.is_linked:
            self._fill_kept_sort_menu(entries)
            return

        for how, title in entries:
            menu.addAction(blank, title, lambda how=how: self._sort(how))

        menu.addSeparator()

        if self._media_list.source is not None:
            menu.addAction(
                blank,
                translate("Dialog - List", "Source Order"),
                self._put_in_source_order,
            )

        menu.addAction(
            blank,
            translate("Dialog - List", "Reverse"),
            lambda: self._sort("reverse"),
        )
        menu.addAction(
            QIcon.fromTheme("loop-dir-shuffle"),
            translate("Dialog - List", "Shuffle"),
            lambda: self._sort("shuffle"),
        )

    def _fill_kept_sort_menu(self, entries):
        """A linked list's: the order it is kept in, put in again each
        time it is read, rather than one it is put in once: checked, as
        the View menu's is, its source's order among them; and turned back
        to front or not, a setting of its own."""

        menu = self._sort_menu
        media_list = self._media_list

        choice = checked_icon(QIcon.fromTheme("empty"), is_choice=True)

        def add_choice(icon, title, is_checked, slot):
            action = menu.addAction(icon, title, slot)
            action.setCheckable(True)
            action.setChecked(is_checked)

        add_choice(
            choice,
            translate("Dialog - List", "Source Order"),
            media_list.sort is None,
            self._put_in_source_order,
        )

        menu.addSeparator()

        for how, title in entries:
            add_choice(
                choice,
                title,
                media_list.sort == ListSort(how),
                lambda how=how: self._sort(how),
            )

        add_choice(
            checked_icon(QIcon.fromTheme("loop-dir-shuffle"), is_choice=True),
            translate("Dialog - List", "Shuffle"),
            media_list.sort == ListSort.SHUFFLE,
            lambda: self._sort("shuffle"),
        )

        menu.addSeparator()

        add_choice(
            checked_icon(QIcon.fromTheme("empty"), is_choice=False),
            translate("Dialog - List", "Reverse"),
            media_list.is_reversed,
            lambda: self._sort("reverse"),
        )

    # adding

    def _is_adding_refused(self) -> bool:
        """Nothing added while it is read, nor to a linked list ever: that
        is said."""

        if self._is_reading:
            return True

        if self._media_list.is_linked:
            self._say(_unlink_to_add_txt())
            return True

        return False

    def _add_files(self):
        if self._is_adding_refused():
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            translate("Dialog - List", "Add Files"),
            "",
            ";;".join(self._reading.name_filters),
        )

        if files:
            self._add_uris(files)

    def _add_folder(self):
        if self._is_adding_refused():
            return

        folder = QFileDialog.getExistingDirectory(
            self, translate("Dialog - List", "Add Folder")
        )

        if folder:
            self._add_uris([folder])

    def _add_links(self):
        if self._is_adding_refused():
            return

        urls = QAddURLsDialog.get_urls(
            parent=self,
            title=translate("Dialog - Add URLs", "Add URL(s)", "Header"),
            supported_schemas=URL_ALLOWED_SCHEMES,
            supported_urls=PLUGIN_URLS,
        )

        urls = [url for url in urls if is_url(url)]

        if urls:
            self._add_uris(urls)

    def _paste(self):
        if self._is_adding_refused():
            return

        uris = extract_mime_uris(QApplication.clipboard().mimeData())

        if not uris:
            self._say(translate("Dialog - List", "Nothing to paste"))
            return

        self._add_uris(uris)

    def _add_uris(self, uris, place=None):
        """Files, folders, list files and links put on the list, read off
        the interface thread: before that place on it, or after the rest."""

        if self._is_adding_refused():
            return

        tell = self._start_reading()
        self._background.run(
            self._reading_name("add"),
            self._expand_at,
            list(map(str, uris)),
            place,
            tell,
        )

    def _expand_at(self, uris, place, tell):
        items, failed = self._reading.expand(uris, tell)

        return items, failed, place

    def _added(self, result):
        items, failed, place = result

        media_list = self._media_list

        if items:
            media_list, added = with_added(media_list, items, place)

            self._apply(media_list, picked=[item.key for item in added])
            self._registry.tell_added(self._list_id, [item.key for item in added])

        if failed:
            self._say(
                translate("Dialog - List", "Could not be read: {WHAT}").format(
                    WHAT=", ".join(where for where, _why in failed)
                )
            )
        elif items:
            self._say(
                translate("Dialog - List", "Added: {COUNT}").format(
                    COUNT=count_txt(len(items))
                )
            )
        else:
            self._say(translate("Dialog - List", "Nothing to add"))

    # reading the list again

    def _refresh(self):
        self._read_source_again("refresh")

    def _link(self):
        """Read again from its source each time the playlist opens, from
        now on: read again now, for the playlist to keep only what was
        done to it."""

        added = sum(item.is_added for item in self._media_list.items)

        if self._is_reading or (added and not self._is_link_confirmed(added)):
            return

        self._read_source_again("link")

    def _is_unlink_confirmed(self, media_list: MediaList) -> bool:
        return UnlinkListDialog.ask(
            media_list.name, saved_list_bytes(media_list), parent=self
        )

    def _is_link_confirmed(self, added: int) -> bool:
        box = QCustomMessageBox(
            QMessageBox.Warning,
            translate("Dialog - List", "Link to Source"),
            translate("Dialog - List", "Link the list to its source?"),
            parent=self,
        )
        box.setInformativeText(
            translate(
                "Dialog - List",
                "Items you added ({COUNT}) will be removed. A linked list only has"
                " what its source has.",
            ).format(COUNT=count_txt(added))
        )

        link_button = box.addButton(
            translate("Dialog - List", "Link"), QMessageBox.DestructiveRole
        )
        box.setDefaultButton(box.addButton(QMessageBox.Cancel))

        box.exec_()

        return box.clickedButton() is link_button

    def _unlink(self):
        """Kept in the playlist whole from now on, as it is, once the
        viewer says so: told first how much bigger that makes the
        playlist's file, for a long list."""

        media_list = self._media_list

        if self._is_reading or not media_list.is_linked:
            return

        if not self._is_unlink_confirmed(media_list):
            return

        self._apply(self._media_list.model_copy(update={"is_linked": False}))
        self._show_source()
        self._say(translate("Dialog - List", "Unlinked"))

    def _put_in_source_order(self):
        """The items in the order their source has them now, after an
        order of the viewer's: read again for it, nothing added or taken
        off. A linked list in it already is left be."""

        media_list = self._media_list

        if media_list.is_linked and media_list.sort is None:
            return

        self._read_source_again("order")

    def _reload_from_source(self):
        """The list as its source has it now, everything done to it here
        undone, once the viewer says so."""

        if self._media_list.source is None or self._is_reading:
            return

        if self._is_reload_confirmed():
            self._read_source_again("reload")

    def _is_reload_confirmed(self) -> bool:
        box = QCustomMessageBox(
            QMessageBox.Warning,
            translate("Dialog - List", "Reload and Discard Changes"),
            translate(
                "Dialog - List",
                "Reload the list and discard your changes?",
            ),
            parent=self,
        )
        box.setInformativeText(
            translate(
                "Dialog - List",
                "Items you added, removed or renamed and your order are reset to"
                " match the source.",
            )
        )

        reload_button = box.addButton(
            translate("Dialog - List", "Reload"), QMessageBox.DestructiveRole
        )
        box.setDefaultButton(box.addButton(QMessageBox.Cancel))

        box.exec_()

        return box.clickedButton() is reload_button

    def _read_source_again(self, how: str, source: ListSource | None = None):
        """Refreshed, the viewer's changes kept; reloaded, undone; or put in
        the source's order. From source where given rather than the list's
        own, the list's from then on once it is read."""

        media_list = self._media_list
        read_from = media_list.source if source is None else source

        if read_from is None or self._is_reading:
            return

        self._show_read_error(None)
        self._last_read = (how, source)

        tell = self._start_reading()
        self._background.run(
            self._reading_name(how),
            self._read_again,
            read_from,
            media_list,
            tell,
            how,
        )

    def _toggle_subfolders(self):
        """A folder's list with the files of its subfolders, or without
        them: read again so, the viewer's changes kept."""

        source = self._media_list.source

        if source is None or source.kind != ListSourceKind.FOLDER:
            return

        self._read_source_again(
            "subfolders",
            source.model_copy(update={"is_recursive": not source.is_recursive}),
        )

    def _read_again(self, source, media_list, tell, how):
        """What is where the list came from, as it is now, and the list with
        it: told apart off the interface thread too, a channel list taking
        a second or so."""

        fresh = None

        # the order it had then is the order it has: a site's list of
        # thousands takes a minute to read again
        if how == "order" and self._reading.kept_source is not None:
            fresh = self._reading.kept_source(source)

        # when it was read, for the list to say; not where nothing was
        read_at = None

        if fresh is None:
            fresh = self._reading.read_source(source, tell)
            read_at = int(time.time())

        return (*self._compared(media_list, source, fresh, tell, how), read_at)

    def _compared_again(self, media_list, source, fresh, read_at, how):
        return (
            *self._compared(media_list, source, fresh, lambda *_: None, how),
            read_at,
        )

    def _compared(self, media_list, source, fresh, tell, how):
        tell("comparing", 0)

        merge = _MERGES[how]

        # read from a source other than its own, it has that one now
        read_from = (
            media_list
            if source == media_list.source
            else media_list.model_copy(update={"source": source})
        )

        return media_list, source, fresh, merge(read_from, fresh)

    def _refreshed(self, result):
        self._apply(result.media_list, picked=self._picked_keys())

        if result.added or result.gone:
            self._say(
                translate("Dialog - List", "New: {ADDED} · Gone: {GONE}").format(
                    ADDED=count_txt(result.added), GONE=count_txt(result.gone)
                )
            )
        else:
            self._say(translate("Dialog - List", "Nothing new"))

    def _reloaded(self, media_list: MediaList):
        self._apply(media_list, picked=self._picked_keys())

        self._say(
            translate("Dialog - List", "Reloaded: {COUNT}").format(
                COUNT=count_txt(len(media_list.items))
            )
        )

    @property
    def _is_reading(self) -> bool:
        return self._read_stop is not None

    def _start_reading(self) -> Throttled:
        """The list left as it is while it is read again, or added to: how
        far reading has got shown instead, once it has taken a while. What
        is to be told it."""

        self._read_serial += 1
        self._read_stop = threading.Event()

        self._model.set_locked(True)
        self._show_progress(translate("Dialog - List", "Reading…"))
        self._show_read_error_box()
        self._reading_timer.start()

        serial = self._read_serial

        return Throttled(
            lambda what, count, of=None: self._reading_progress.emit(
                serial, what, count, of
            ),
            stop=self._read_stop,
        )

    def _reading_name(self, what: str) -> str:
        return f"{what}:{self._read_serial}"

    def _show_reading(self):
        """Reading going on, the editing waiting for it: the panel says how
        far it has got, with Stop in Refresh's place."""

        self._is_reading_shown = True

        self._progress_box.show()
        self._show_source()
        self._update_buttons()

    def _finish_reading(self):
        self._reading_timer.stop()
        self._is_reading_shown = False
        self._read_stop = None

        self._model.set_locked(False)
        self._show_progress(None)
        self._show_read_error_box()
        self._show_source()
        self._update_buttons()

    def _stop_reading(self):
        if not self._is_reading:
            return

        if self._is_read_elsewhere:
            self._is_read_elsewhere = False
            self._registry.stop_reading(self._list_id)
            self._take_as_it_was()

        self._read_stop.set()

        # what it finds yet is let go of
        self._read_serial += 1

        self._finish_reading()
        self._say(translate("Dialog - List", "Stopped"))

    def _on_reading_changed(self, list_id):
        """The list read again from its source as the playlist opens:
        waited for as for a reading of the window's own, Stop stopping it;
        and what it could not be read for, once it is over."""

        if list_id != self._list_id or self._is_done:
            return

        is_read = self._registry.is_being_read(list_id)

        if is_read and not self._is_reading:
            self._is_read_elsewhere = True
            self._start_reading()
            return

        if is_read or not self._is_read_elsewhere:
            return

        self._is_read_elsewhere = False
        self._take_as_it_was()
        self._finish_reading()
        self._say_read_error()

    def _take_as_it_was(self):
        """The list read again, rather than edited here, is the one
        Cancel puts back: nothing was done to it here meanwhile."""

        if not self._is_edited:
            self._original = self._registry.get(self._list_id)

    def _say_read_error(self):
        """Why the list could not be read again the last time, as the
        playlist opened or from this window: Try Again reads it again."""

        error = self._registry.read_error(self._list_id)

        if error is not None:
            self._last_read = ("refresh", None)

        self._show_read_error(error)

    def _show_read_error(self, error: ReadError | None):
        """What the list could not be read from its source for, in the
        Source panel where reading shows, until it is read or put away."""

        self._read_error = error
        self._show_read_error_box()

    def _show_read_error_box(self):
        error = self._read_error
        is_shown = error is not None and not self._is_reading

        self._error_box.setVisible(is_shown)

        if not is_shown:
            return

        title, about = read_error_txts(error)
        icon = "network-error" if error.is_network else "error"

        self._error_icon.setPixmap(
            QIcon.fromTheme(icon).pixmap(QSize(READ_ERROR_ICON_PX, READ_ERROR_ICON_PX))
        )
        self._error_title.setText(title)
        self._error_about.setText(about)

        # the error as it was raised, for whoever wants it: wrapped, as
        # rich text is
        tooltip = f"<p>{html.escape(error.raw)}</p>"
        for label in (self._error_icon, self._error_title, self._error_about):
            label.setToolTip(tooltip)

    def _hide_read_error(self):
        self._registry.forget_read_error(self._list_id)
        self._show_read_error(None)

    def _try_again(self):
        self._read_source_again(*self._last_read)

    def _on_reading_elsewhere(self, list_id, what, count, of):
        if list_id == self._list_id and self._is_read_elsewhere:
            self._show_progress(*reading_txt(what, count, of))

    def _on_reading_progress(self, serial, what, count, of):
        if serial != self._read_serial or not self._is_reading:
            return

        if what == "comparing":
            self._show_progress(
                translate("Dialog - List", "Comparing with the list…"), 0
            )
            return

        self._show_progress(*reading_txt(what, count, of))

    def _show_progress(self, text: str | None, percent: int = 0):
        """How far reading has got: in percent where that is known, or
        under way where it is not; nothing, for no reading. Said once it has
        gone on for a while."""

        self._progress_box.setVisible(text is not None and self._is_reading_shown)

        if text is None:
            return

        self._progress_label.setText(text)

        if percent:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(percent)
        else:
            self._progress_bar.setRange(0, 0)

    def _on_read(self, name, result, error):
        what, _, serial = name.partition(":")

        if self._is_done or not self._is_reading or int(serial) != self._read_serial:
            return

        if what in _MERGES and error is None:
            media_list, source, fresh, compared, read_at = result

            # changed meanwhile, a cell learning how long an item is: told
            # apart again from the list as it is now
            if self._media_list is not media_list:
                self._background.run(
                    name,
                    self._compared_again,
                    self._media_list,
                    source,
                    fresh,
                    read_at,
                    what,
                )
                return

            result = _read_when(compared, read_at)

        self._finish_reading()

        if error is not None:
            if what in _MERGES:
                read_error = read_error_of(error, self._media_list.source)
                self._registry.remember_read_error(self._list_id, read_error)
                self._show_read_error(read_error)
            else:
                self._say(
                    translate("Dialog - List", "Could not be read: {WHAT}").format(
                        WHAT=str(error)
                    )
                )
            return

        if what in _MERGES:
            self._registry.forget_read_error(self._list_id)

        if what == "refresh":
            self._refreshed(result)
        elif what == "subfolders":
            self._refreshed(result)
            self._show_source()
        elif what == "link":
            self._apply(result.media_list, picked=self._picked_keys())
            self._show_source()
            self._say(translate("Dialog - List", "Linked"))
        elif what == "reload":
            self._reloaded(result)
        elif what == "order":
            self._apply(result, picked=self._picked_keys())
            self._say(translate("Dialog - List", "In the source's order"))
        else:
            self._added(result)

    # what is known of the items, looked up

    def _get_info(self):
        """The items picked looked up, whatever is known of them already:
        their views as they are now."""

        picked = self._picked_items()

        if picked and self._lookups is not None:
            self._lookups.look_up(self._list_id, picked, is_missing_only=False)

    def _get_missing_info(self):
        """The items with nothing known of them yet looked up."""

        if self._lookups is not None:
            self._lookups.look_up(
                self._list_id, self._media_list.items, is_missing_only=True
            )

    def _on_lookup_changed(self, list_id):
        if list_id == self._list_id:
            self._show_lookup()

    def _on_lookup_finished(
        self, list_id, found: int, not_found: int, without_details: int
    ):
        if list_id != self._list_id:
            return

        self._show_lookup()

        if not found and not not_found:
            self._say(translate("Dialog - List", "Nothing to look up"))
            return

        if not_found:
            txt = translate(
                "Dialog - List", "Looked up: {FOUND} · Not found: {MISSING}"
            ).format(FOUND=count_txt(found), MISSING=count_txt(not_found))
        else:
            txt = translate("Dialog - List", "Looked up: {COUNT}").format(
                COUNT=count_txt(found)
            )

        # the rest of them known, from YouTube's list of them
        if without_details:
            txt = "{} · {}".format(
                txt,
                translate("Dialog - List", "No views or dates: {COUNT}").format(
                    COUNT=count_txt(without_details)
                ),
            )

        self._say(txt)

    def _on_learned(self, list_id, fields_by_key: dict):
        """What was learned of items, kept should the window be cancelled:
        no edit made here, to be taken back with those."""

        original = self._original

        if list_id != self._list_id or original is None:
            return

        self._original = original.with_fields(fields_by_key)

    def _show_lookup(self):
        """How far looking up the items has got, in the line under the list
        in place of the count; what a site that turned it away says, with
        the button to try again."""

        state = None if self._lookups is None else self._lookups.state(self._list_id)

        self._lookup_line.setVisible(state is not None)
        self._hint.setVisible(state is None)

        if state is None:
            return

        button = self._lookup_button
        is_refused = state.refused is not None

        self._lookup_label.setVisible(not is_refused)
        self._lookup_bar.setVisible(not is_refused)
        self._lookup_refused.setVisible(is_refused)

        if is_refused:
            self._lookup_refused.setText(
                translate(
                    "Dialog - List",
                    "{SITE} is blocking requests. Stopped at {DONE} of {COUNT}.",
                ).format(
                    SITE=state.refused,
                    DONE=count_txt(state.done),
                    COUNT=count_txt(state.count),
                )
            )

            button.setIcon(QIcon.fromTheme("reload"))
            button.setText(translate("Dialog - List", "Try Again"))
            button.setToolTip(
                translate(
                    "Dialog - List",
                    "Try again. Sites usually allow it after a while.",
                )
            )
            return

        if state.is_details:
            text = translate(
                "Dialog - List", "Getting views and dates: {DONE} of {COUNT}"
            )
        elif state.count:
            text = translate("Dialog - List", "Getting info: {DONE} of {COUNT}")
        else:
            text = translate("Dialog - List", "Getting info…")

        self._lookup_label.setText(
            text.format(DONE=count_txt(state.done), COUNT=count_txt(state.count))
        )

        if state.count:
            self._lookup_bar.setRange(0, state.count)
            self._lookup_bar.setValue(state.done)
        else:
            self._lookup_bar.setRange(0, 0)

        button.setIcon(QIcon.fromTheme("close"))
        button.setText(translate("Dialog - List", "Stop"))
        button.setToolTip(translate("Dialog - List", "Stop and keep what was found"))

    def _on_lookup_button(self):
        state = None if self._lookups is None else self._lookups.state(self._list_id)

        if state is None:
            return

        if state.refused is not None:
            self._lookups.try_again(self._list_id)
            return

        self._lookups.stop(self._list_id)
        self._say(translate("Dialog - List", "Stopped"))

    # playing

    def _play(self):
        index = self._list.currentIndex()

        if not index.isValid():
            return

        place = self._model.place_at(index.row())

        if self._block is not None:
            self._block.play_list_item(place)
        elif self._open_in_new_cell is not None:
            self._open_in_new_cell(self._list_id, place)

    def _open_new(self):
        index = self._list.currentIndex()

        if index.isValid() and self._open_in_new_cell is not None:
            self._open_in_new_cell(self._list_id, self._model.place_at(index.row()))

        # the new cell plays the list too
        QTimer.singleShot(0, self._show_shared)

    def _open_as_new_list(self):
        """The items picked made a list of their own, played from the first
        in a new cell: some channels of a provider's thousands."""

        picked = self._picked_items()

        if not picked or self._open_in_new_cell is None:
            return

        # named after their group, if they are all of one
        groups = {item.group for item in picked}
        group = next(iter(groups)) if len(groups) == 1 else None

        media_list = self._registry.add(
            MediaList(
                name=group or self._media_list.name,
                items=tuple(
                    item.model_copy(update={"key": new_item_key()}) for item in picked
                ),
            )
        )

        self._open_in_new_cell(media_list.id, 0)

        self._say(
            translate("Dialog - List", "Opened as a new list: {COUNT}").format(
                COUNT=count_txt(len(picked))
            )
        )

    # copying, showing, saving

    def _copy(self):
        self._copy_lines([str(item.uri) for item in self._picked_items()])

    def _copy_titles(self):
        self._copy_lines([self._model.name_of(item) for item in self._picked_items()])

    def _copy_lines(self, lines: list[str]):
        if not lines:
            return

        QApplication.clipboard().setText("\n".join(lines))

        self._say(
            translate("Dialog - List", "Copied: {COUNT}").format(
                COUNT=count_txt(len(lines))
            )
        )

    def _copy_source(self):
        source = self._media_list.source

        if source is None:
            return

        QApplication.clipboard().setText(str(source.location))

        self._say(translate("Dialog - List", "Source copied"))

    def _show_source_in_folder(self):
        source = self._media_list.source

        if source is not None and source.kind != ListSourceKind.URL:
            self._revealer.show(Path(source.location))

    def _copy_all(self):
        self._copy_lines([str(item.uri) for item in self._media_list.items])

    def _show_in_folder(self):
        picked = self._picked_items()

        if len(picked) == 1 and isinstance(picked[0].uri, Path):
            self._revealer.show(picked[0].uri)

    def _export(self):
        exported, error = export_m3u(self, self._media_list)

        if error is not None:
            self._say(
                translate("Dialog - List", "Could not be exported: {WHAT}").format(
                    WHAT=error
                )
            )
        elif exported is not None:
            self._say(
                translate("Dialog - List", "Exported: {FILE}").format(
                    FILE=exported.name
                )
            )

    # menus

    def _show_row_menu(self, global_pos):
        picked = self._picked_items()

        if not picked:
            return

        menu = CustomMenu(parent=self)

        if self._block is not None:
            menu.addAction(
                QIcon.fromTheme("play"),
                with_key_txt(
                    translate("Dialog - List", "Play in This Cell"), Qt.Key_Enter
                ),
                self._play,
            ).setEnabled(len(picked) == 1)

        if self._open_in_new_cell is not None and len(picked) == 1:
            menu.addAction(
                QIcon.fromTheme("add"),
                translate("Dialog - List", "Open in a New Cell"),
                self._open_new,
            )
        elif self._open_in_new_cell is not None:
            menu.addAction(
                QIcon.fromTheme("add"),
                translate("Dialog - List", "Open in a New Cell as a New List"),
                self._open_as_new_list,
            )

        menu.addSeparator()

        is_free = not self._is_reading

        menu.addAction(
            QIcon.fromTheme("rename"),
            with_key_txt(translate("Dialog - List", "Rename"), RENAME_KEY),
            self._edit_name,
        ).setEnabled(len(picked) == 1 and is_free)

        if self._lookups is not None:
            menu.addAction(
                QIcon.fromTheme("information"),
                translate("Dialog - List", "Get Info"),
                self._get_info,
            ).setEnabled(any(may_be_looked_up(item) for item in picked))

        menu.addAction(
            QIcon.fromTheme("copy"),
            with_key_txt(_copy_txt(picked), QKeySequence.Copy),
            self._copy,
        )
        menu.addAction(
            QIcon.fromTheme("empty"),
            translate("Dialog - List", "Copy Title"),
            self._copy_titles,
        )

        if len(picked) == 1 and isinstance(picked[0].uri, Path):
            menu.addAction(
                QIcon.fromTheme("show-in-folder"),
                translate("Dialog - List", "Show in Folder"),
                self._show_in_folder,
            )

        if not self._model.is_filtered and not self._model.is_linked:
            menu.addSeparator()
            menu.addAction(
                QIcon.fromTheme("empty"),
                translate("Dialog - List", "Move to Top"),
                self._move_to_top,
            ).setEnabled(is_free)
            menu.addAction(
                QIcon.fromTheme("empty"),
                translate("Dialog - List", "Move to Bottom"),
                self._move_to_bottom,
            ).setEnabled(is_free)

        menu.addSeparator()

        menu.addAction(
            QIcon.fromTheme("close"),
            with_key_txt(translate("Dialog - List", "Remove"), REMOVE_KEY),
            self._remove,
        ).setEnabled(is_free)

        menu.exec_(global_pos)
        menu.deleteLater()

    def _show_source_menu(self, pos):
        source = self._media_list.source

        if source is None:
            return

        menu = CustomMenu(parent=self)

        menu.addAction(
            QIcon.fromTheme("copy"), _copy_source_txt(source), self._copy_source
        )

        if source.kind != ListSourceKind.URL:
            menu.addAction(
                QIcon.fromTheme("show-in-folder"),
                translate("Dialog - List", "Show in Folder"),
                self._show_source_in_folder,
            )

        if source.kind == ListSourceKind.FOLDER:
            subfolders = menu.addAction(
                checked_icon(QIcon.fromTheme("folder-tree"), is_choice=False),
                translate("Dialog - List", "Include Subfolders"),
                self._toggle_subfolders,
            )
            subfolders.setCheckable(True)
            subfolders.setChecked(source.is_recursive)
            subfolders.setEnabled(not self._is_reading)

        menu.addSeparator()

        menu.addAction(
            QIcon.fromTheme("reload"),
            translate("Dialog - List", "Refresh"),
            self._refresh,
        ).setEnabled(not self._is_reading)
        menu.addAction(
            QIcon.fromTheme("empty"),
            translate("Dialog - List", "Reload and Discard Changes…"),
            self._reload_from_source,
        ).setEnabled(not self._is_reading)

        menu.addSeparator()

        if self._media_list.is_linked:
            update_menu = CustomMenu(parent=menu)
            update_menu.setTitle(translate("Dialog - List", "Update"))
            update_menu.setIcon(QIcon.fromTheme("empty"))
            self._fill_update_menu(update_menu)
            menu.addMenu(update_menu)

            menu.addAction(
                QIcon.fromTheme("empty"),
                translate("Dialog - List", "Unlink"),
                self._unlink,
            ).setEnabled(not self._is_reading)
        else:
            menu.addAction(
                QIcon.fromTheme("empty"),
                translate("Dialog - List", "Link to Source"),
                self._link,
            ).setEnabled(not self._is_reading)

        menu.exec_(self._source_panel.mapToGlobal(pos))
        menu.deleteLater()

    def _show_list_menu(self, global_pos):
        menu = CustomMenu(parent=self)

        is_free = not self._is_reading and not self._media_list.is_linked

        menu.addAction(
            QIcon.fromTheme("add-files"),
            with_key_txt(translate("Dialog - List", "Add Files…"), ADD_KEY),
            self._add_files,
        ).setEnabled(is_free)
        menu.addAction(
            QIcon.fromTheme("add-folder"),
            translate("Dialog - List", "Add Folder…"),
            self._add_folder,
        ).setEnabled(is_free)
        menu.addAction(
            QIcon.fromTheme("add-url"),
            translate("Dialog - List", "Add Links…"),
            self._add_links,
        ).setEnabled(is_free)
        menu.addAction(
            QIcon.fromTheme("paste"),
            with_key_txt(translate("Dialog - List", "Paste"), QKeySequence.Paste),
            self._paste,
        ).setEnabled(is_free)

        menu.addSeparator()

        menu.addAction(
            QIcon.fromTheme("copy"),
            translate("Dialog - List", "Copy All"),
            self._copy_all,
        ).setEnabled(bool(self._media_list.items))

        if self._lookups is not None:
            menu.addSeparator()
            menu.addAction(
                QIcon.fromTheme("information"),
                translate("Dialog - List", "Get Missing Info"),
                self._get_missing_info,
            ).setEnabled(bool(self._media_list.items))

        menu.exec_(global_pos)
        menu.deleteLater()


def _empty_txt(media_list: MediaList) -> tuple[str, str]:
    """What the list says with nothing on it, and how to put something on
    it."""

    nothing = translate("Dialog - List", "Nothing on the list")

    if media_list.is_linked:
        return nothing, translate("Dialog - List", "Press Refresh to load it.")

    return nothing, translate(
        "Dialog - List", "Add files, a folder or links, or drop them here."
    )


def _unlink_to_add_txt() -> str:
    return translate("Dialog - List", "Unlink the list to add to it")


def _read_when(result, read_at: int | None):
    """The list read again, saying when; as it was, where nothing was read
    for it: put in its source's order from what was kept."""

    if read_at is None:
        return result

    if isinstance(result, Refreshed):
        return dataclasses.replace(
            result,
            media_list=result.media_list.model_copy(update={"read_at": read_at}),
        )

    return result.model_copy(update={"read_at": read_at})


def _copy_source_txt(source: ListSource) -> str:
    if source.kind == ListSourceKind.URL:
        return translate("Dialog - List", "Copy Link")

    return translate("Dialog - List", "Copy Path")


def _view_txts(items) -> dict[ListView, str]:
    """The views offered, named after what the list has: files, links, or
    both; and its videos' pictures, where it has them."""

    views = _location_view_txts(items)

    if _has_thumbnails(items):
        views[ListView.THUMBNAILS] = translate("Dialog - List", "Thumbnails")

    return views


def _location_view_txts(items) -> dict[ListView, str]:
    are_files = set()
    for item in items:
        are_files.add(isinstance(item.uri, Path))
        if len(are_files) > 1:
            break

    if are_files == {True}:
        return {
            ListView.TITLES: translate("Dialog - List", "Titles"),
            ListView.TITLES_AND_LOCATIONS: translate(
                "Dialog - List", "Titles and Paths"
            ),
            ListView.LOCATIONS: translate("Dialog - List", "Paths"),
        }

    if are_files == {False}:
        return {
            ListView.TITLES: translate("Dialog - List", "Titles"),
            ListView.TITLES_AND_LOCATIONS: translate(
                "Dialog - List", "Titles and Links"
            ),
            ListView.LOCATIONS: translate("Dialog - List", "Links"),
        }

    return {
        ListView.TITLES: translate("Dialog - List", "Titles"),
        ListView.TITLES_AND_LOCATIONS: translate(
            "Dialog - List", "Titles, Paths and Links"
        ),
        ListView.LOCATIONS: translate("Dialog - List", "Paths and Links"),
    }


def _has_thumbnails(items) -> bool:
    return any(item.details is not None and item.details.thumbnail for item in items)


def details_txt(details: ItemDetails, now: float | None = None) -> str:
    """What a site says of a video, the way it says it: its channel, its
    views and how long ago it was put up, "Channel · 1.2K views · 3 years
    ago"; as much of it as it said."""

    parts = []

    if details.channel:
        parts.append(details.channel)

    if details.view_count is not None:
        parts.append(views_txt(details.view_count))

    if details.published is not None:
        parts.append(published_txt(details.published, now))

    return " · ".join(parts)


def views_txt(count: int) -> str:
    if count == 0:
        return translate("Dialog - List", "No views")

    if count == 1:
        return translate("Dialog - List", "1 view")

    return translate("Dialog - List", "{COUNT} views").format(
        COUNT=short_count_txt(count)
    )


def short_count_txt(count: int) -> str:
    """A count the way a site says it: 999, 1.2K, 12K, 1.2M, cut down to
    the figures shown rather than rounded up."""

    units = (
        (1_000_000_000, translate("Dialog - List", "{COUNT}B", "billions")),
        (1_000_000, translate("Dialog - List", "{COUNT}M", "millions")),
        (1_000, translate("Dialog - List", "{COUNT}K", "thousands")),
    )

    locale = QLocale()

    for unit, unit_txt in units:
        if count < unit:
            continue

        tenths = count * 10 // unit

        if tenths >= 100 or tenths % 10 == 0:
            number = locale.toString(tenths // 10)
        else:
            number = locale.toString(tenths / 10, "f", 1)

        return unit_txt.format(COUNT=number)

    return locale.toString(count)


def published_txt(published: int, now: float | None = None) -> str:
    """How long ago something was put up, the way a site says it: "3 years
    ago", "2 weeks ago"."""

    if now is None:
        now = time.time()

    minutes = max(0, int(now - published)) // 60
    hours = minutes // 60
    days = hours // 24

    if days >= 365:
        count = days // 365
        if count == 1:
            return translate("Dialog - List", "1 year ago")
        return translate("Dialog - List", "{COUNT} years ago").format(COUNT=count)

    if days >= 30:
        count = days // 30
        if count == 1:
            return translate("Dialog - List", "1 month ago")
        return translate("Dialog - List", "{COUNT} months ago").format(COUNT=count)

    if days >= 7:
        count = days // 7
        if count == 1:
            return translate("Dialog - List", "1 week ago")
        return translate("Dialog - List", "{COUNT} weeks ago").format(COUNT=count)

    if days >= 1:
        if days == 1:
            return translate("Dialog - List", "1 day ago")
        return translate("Dialog - List", "{COUNT} days ago").format(COUNT=days)

    if hours >= 1:
        if hours == 1:
            return translate("Dialog - List", "1 hour ago")
        return translate("Dialog - List", "{COUNT} hours ago").format(COUNT=hours)

    if minutes <= 1:
        return translate("Dialog - List", "1 minute ago")

    return translate("Dialog - List", "{COUNT} minutes ago").format(COUNT=minutes)


def read_error_txts(error: ReadError) -> tuple[str, str]:
    """What the list could not be read from its source for: a few words,
    and a line on what that means or what to do."""

    kind = error.kind
    host = error.host

    if kind is ReadErrorKind.HTTP:
        return _http_error_txts(error.status)

    if kind is ReadErrorKind.PROXY:
        return (
            translate("Dialog - List", "Proxy error"),
            translate(
                "Dialog - List", "Couldn't connect through the proxy set in Settings."
            ),
        )

    if kind is ReadErrorKind.CERTIFICATE:
        return (
            translate("Dialog - List", "Secure connection failed"),
            translate("Dialog - List", "The site's certificate isn't trusted."),
        )

    if kind is ReadErrorKind.SECURE:
        return (
            translate("Dialog - List", "Secure connection failed"),
            translate(
                "Dialog - List", "Couldn't make a secure connection to {HOST}."
            ).format(HOST=host),
        )

    if kind is ReadErrorKind.DNS:
        return (
            translate("Dialog - List", "Server not found"),
            translate(
                "Dialog - List",
                "Couldn't find {HOST}. Check the link and your internet connection.",
            ).format(HOST=host),
        )

    if kind is ReadErrorKind.TIMEOUT:
        return (
            translate("Dialog - List", "Timed out"),
            translate("Dialog - List", "{HOST} took too long to answer.").format(
                HOST=host
            ),
        )

    if kind is ReadErrorKind.REFUSED:
        return (
            translate("Dialog - List", "Connection refused"),
            translate("Dialog - List", "{HOST} isn't accepting connections.").format(
                HOST=host
            ),
        )

    if kind is ReadErrorKind.LOST:
        return (
            translate("Dialog - List", "Connection lost"),
            translate("Dialog - List", "The connection to {HOST} was cut off.").format(
                HOST=host
            ),
        )

    if kind is ReadErrorKind.CONNECTION:
        return (
            translate("Dialog - List", "Couldn't connect"),
            translate(
                "Dialog - List",
                "Couldn't reach {HOST}. Check your internet connection.",
            ).format(HOST=host),
        )

    if kind is ReadErrorKind.BLOCKED:
        return (
            translate("Dialog - List", "{SITE} is blocking requests").format(
                SITE=site_name(host)
            ),
            translate(
                "Dialog - List", "Try again later, or set up cookies in Settings."
            ),
        )

    if kind is ReadErrorKind.GONE:
        return (
            translate("Dialog - List", "Not found"),
            translate("Dialog - List", "It may be private or deleted."),
        )

    if kind is ReadErrorKind.NOT_A_LIST:
        if error.source_kind == ListSourceKind.FILE:
            about = translate("Dialog - List", "The file isn't a playlist.")
        else:
            about = translate("Dialog - List", "The link didn't return a playlist.")

        return translate("Dialog - List", "Not a playlist"), about

    if kind is ReadErrorKind.TOO_LARGE:
        return (
            translate("Dialog - List", "Playlist too big"),
            translate(
                "Dialog - List",
                "It's over the M3U size limit ({SIZE} MB). You can raise it in"
                " Settings.",
            ).format(SIZE=error.limit_mb),
        )

    if kind is ReadErrorKind.EMPTY:
        return (
            translate("Dialog - List", "Empty playlist"),
            translate("Dialog - List", "The source has nothing to play right now."),
        )

    if kind is ReadErrorKind.MISSING:
        if error.source_kind == ListSourceKind.FOLDER:
            title = translate("Dialog - List", "Folder not found")
        else:
            title = translate("Dialog - List", "File not found")

        return title, translate(
            "Dialog - List", "It may have been moved, renamed or deleted."
        )

    if kind is ReadErrorKind.NO_ACCESS:
        return (
            translate("Dialog - List", "Access denied"),
            translate("Dialog - List", "You don't have permission to open it."),
        )

    if error.source_kind == ListSourceKind.URL:
        title = translate("Dialog - List", "Couldn't download the list")
    else:
        title = translate("Dialog - List", "Couldn't read the list")

    return title, error.raw_said


def _http_error_txts(status: int) -> tuple[str, str]:
    if status == HTTP_UNAUTHORIZED:
        return (
            translate("Dialog - List", "Login needed (HTTP {CODE})").format(
                CODE=status
            ),
            translate("Dialog - List", "The server wants a username and password."),
        )

    if status == HTTP_FORBIDDEN:
        return (
            translate("Dialog - List", "Access denied (HTTP {CODE})").format(
                CODE=status
            ),
            translate(
                "Dialog - List", "The server refused. The link may have expired."
            ),
        )

    if status in HTTP_NOT_THERE:
        return (
            translate("Dialog - List", "Not found (HTTP {CODE})").format(CODE=status),
            translate("Dialog - List", "The server has nothing at this link."),
        )

    if status == HTTP_TOO_MANY_REQUESTS:
        return (
            translate("Dialog - List", "Too many requests (HTTP {CODE})").format(
                CODE=status
            ),
            translate(
                "Dialog - List",
                "The server is limiting requests. Try again later.",
            ),
        )

    if HTTP_SERVER_ERRORS[0] <= status < HTTP_SERVER_ERRORS[1]:
        return (
            translate("Dialog - List", "Server error (HTTP {CODE})").format(
                CODE=status
            ),
            translate(
                "Dialog - List",
                "The problem is on the server's side. Try again later.",
            ),
        )

    return (
        translate("Dialog - List", "Request refused (HTTP {CODE})").format(CODE=status),
        translate("Dialog - List", "The server didn't accept the request."),
    )


# how the list is told apart from what its source has now, by how it is
# read again
_MERGES = {
    "refresh": refreshed,
    "subfolders": refreshed,
    "reload": reloaded,
    "order": in_source_order,
    "link": linked,
}


def _copy_txt(items) -> str:
    """What Copy copies: files' paths, links, or both."""

    are_files = {isinstance(item.uri, Path) for item in items}

    if are_files == {True}:
        return translate("Dialog - List", "Copy Path")

    if are_files == {False}:
        return translate("Dialog - List", "Copy Link")

    return translate("Dialog - List", "Copy Paths and Links")


def export_m3u(parent, media_list: MediaList) -> tuple[Path | None, str | None]:
    """The list written to an M3U file the viewer picks, for other players:
    where to, or None for nowhere; and why not, where it could not be."""

    name = media_list.name or translate("Dialog - List", "List")

    file_path, chosen_filter = QFileDialog.getSaveFileName(
        parent,
        translate("Dialog - List", "Export List"),
        str(Path.home() / f"{_file_name(name)}.m3u8"),
        "M3U8 (*.m3u8);;M3U (*.m3u)",
    )

    if not file_path:
        return None, None

    path = Path(file_path)

    if path.suffix.lower() not in {".m3u8", ".m3u"}:
        path = path.with_suffix(".m3u" if "(*.m3u)" in chosen_filter else ".m3u8")

    text = m3u_text(media_list.name, media_list.items, base_dir=path.parent)

    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        return None, str(e)

    return path, None


def _file_name(name: str) -> str:
    """A name fit to be a file's: a list called nothing is a list."""

    return sanitize_filename(name) if name.strip(" .") else "list"
