"""The bookmarks manager: every bookmark of a video, to go to, name, move and
take away, under the video's own bar.

Changes are made on the video as they go, as the crop is in Set Crop, so the
bar over the video and the one here show them at once; Cancel puts back the
bookmarks the video had.
"""

import html
import math
from enum import IntEnum

from PyQt5.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionFrame,
    QStylePainter,
    QToolTip,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from gridplayer.models.bookmark import Bookmark
from gridplayer.models.seek_mark import SeekMarkKind, chapter_at
from gridplayer.params.static import VideoEndAction
from gridplayer.utils.bookmarks import (
    bookmark_on,
    bookmarks_txt,
    default_bookmark_name,
    is_bookmarked,
    new_in_txt,
    parse_bookmarks_txt,
    with_bookmark,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.time_txt import (
    get_time_txt,
    ms_time_txt,
    parse_time_txt,
)
from gridplayer.widgets.bookmark_colors import (
    LIST_ICON_SHARE,
    bookmark_color_menu,
    bookmark_icon,
    color_picked_by_hand,
    text_marker_html,
)
from gridplayer.widgets.custom_menu import CustomMenu
from gridplayer.widgets.video_overlay_buttons import OverlayPlayPauseButton
from gridplayer.widgets.video_overlay_elements import (
    BOOKMARK_MARKER,
    BOOKMARK_STRIP_HEIGHT,
    BOOKMARK_TAIL,
    OverlayBookmarkMarkers,
    OverlayProgressBar,
    OverlayShortLabel,
)

# The bar is the overlay's, in a grey of the dialog's own: this much of the
# text's colour in the window's. The times step back behind the names, this
# much of the list's background in the text's colour, mixed rather than
# see-through, which fringes text in colour.
BAR_TINT = 0.13
TIME_FADE = 0.38

# The overlay's pure red and blue stand out over any video, and glare in a
# window: here, quieter ones, readable on a light grey and a dark one alike;
# and the grey over what is ahead of the mouse, this much of the way from the
# bar's to the overlay's.
BAR_PROGRESS_COLOR = "#d14747"
BAR_SELECT_COLOR = "#4775d1"
BAR_AHEAD_SHADE = 0.5

# the play button, the time and the bar, each a box of its own
PLAYER_ROW_SPACING = 6

# how far under the bar the time under the mouse is shown
HOVER_TIP_GAP = 4

# the loop's edges drawn across the list, in the green of its marks on the
# bar, darker where the list is light for the words on them to read
LOOP_EDGE_COLOR_LIGHT = "#1e9e3a"
LOOP_EDGE_COLOR_DARK = "#5ad06a"

ROW_HEIGHT = 26
HERE_ICON_PX = 12

# how long something said in place of the hint under the list stays
STATUS_MS = 4000

DIALOG_SIZE = QSize(560, 470)
DIALOG_MIN_SIZE = QSize(460, 360)

# the name a bookmark goes by without one of its own, shown in the editor
# for a name to be typed over
DEFAULT_NAME_ROLE = Qt.UserRole

# The list's keys, said in its menus; Enter goes to the current bookmark,
# and Copy and Paste are the system's.
RENAME_KEY = Qt.Key_F2
EDIT_TIME_KEY = int(Qt.SHIFT) | Qt.Key_F2
MOVE_HERE_KEY = int(Qt.CTRL) | Qt.Key_M
REMOVE_KEY = Qt.Key_Delete
ADD_KEY = Qt.Key_Insert


class Column(IntEnum):
    TIME = 0
    NAME = 1


def mixed_color(color: QColor, other: QColor, amount: float) -> QColor:
    """The colour with this much of the other in it."""

    return QColor.fromRgbF(
        *(
            channel + (other_channel - channel) * amount
            for channel, other_channel in zip(color.getRgbF()[:3], other.getRgbF()[:3])
        )
    )


def _here_icon(color: QColor) -> QIcon:
    """A small play mark: the bookmark the video is at."""

    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(20, 12), QPointF(6, 21)]))
    painter.end()

    return QIcon(pixmap)


def _blank_icon() -> QIcon:
    """The room the play mark takes, kept in every row to line the times up."""

    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)

    return QIcon(pixmap)


def _video_title(block) -> str | None:
    return block.title or None


def held_end_action_txt(end_action: VideoEndAction) -> str:
    """An end action held back while a video's bookmarks are being edited,
    as the menu calls it."""

    return {
        VideoEndAction.NEXT_FILE: translate("When Finished", "Play Next File"),
        VideoEndAction.PREVIOUS_FILE: translate("When Finished", "Play Previous File"),
        VideoEndAction.SHUFFLE_FILE: translate("When Finished", "Random In Folder"),
        VideoEndAction.CLOSE: translate("When Finished", "Close"),
    }[end_action]


def with_key_txt(item_txt: str, key) -> str:
    """A menu item's text, the key for it to the right."""

    key_txt = QKeySequence(key).toString(QKeySequence.NativeText)

    return f"{item_txt}\t{key_txt}"


def paint_empty_txt(view, painter, line_txt, hint_txt):
    """What a list says with nothing in it: a line in the middle, and a hint
    under it."""

    rect = QRectF(view.viewport().rect())

    line_font = QFont(view.font())
    line_font.setPointSizeF(line_font.pointSizeF() * 1.15)

    line_rect = rect.adjusted(24, 0, -24, 0)
    line_rect.setBottom(rect.center().y() - 2)

    painter.setFont(line_font)
    painter.setPen(view.palette().color(QPalette.Text))
    painter.drawText(line_rect, Qt.AlignHCenter | Qt.AlignBottom, line_txt)

    hint_rect = rect.adjusted(40, 0, -40, 0)
    hint_rect.setTop(rect.center().y() + 4)

    painter.setFont(view.font())
    painter.setPen(view.palette().color(QPalette.PlaceholderText))
    painter.drawText(
        hint_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, hint_txt
    )


class BookmarksModel(QAbstractTableModel):
    """The video's bookmarks, a row each: where it is, and what it is called.

    Read from the video, and edited by the dialog on the video: an edit
    typed in a row is handed on, to be made once its editor is gone.
    """

    renamed = pyqtSignal(int, str)
    retimed = pyqtSignal(int, str)

    def __init__(self, block, parent=None):
        super().__init__(parent)

        self._block = block
        self._here = None

        # the video's length, as the dialog knows it: kept while the video
        # has no player, for the times to read as they did
        self.length = 0

        self._here_icon = QIcon()
        self._blank_icon = _blank_icon()
        self._colors = {}
        self._unnamed_font = QFont()

        # a bookmark's marker in its colour, by the colour
        self._marker_icons = {}
        self._marker_rim = QColor()

    def set_look(self, palette: QPalette, font: QFont):
        text = palette.color(QPalette.Text)

        self._colors = {
            "time": mixed_color(text, palette.color(QPalette.Base), TIME_FADE),
            "unnamed": palette.color(QPalette.PlaceholderText),
            "out_of_reach": palette.color(QPalette.Disabled, QPalette.Text),
        }

        self._here_icon = _here_icon(text)

        self._marker_icons = {}
        self._marker_rim = text

        self._unnamed_font = QFont(font)
        self._unnamed_font.setItalic(True)

        if self.rowCount():
            self.dataChanged.emit(
                self.index(0, 0), self.index(self.rowCount() - 1, len(Column) - 1)
            )

    def reload(self):
        self.beginResetModel()
        self._here = self._block.bookmark_here
        self.endResetModel()

    def set_here(self, here: int | None):
        """Move the play mark to the bookmark the video is at now."""

        if here == self._here:
            return

        rows = [row for row in (self._here, here) if row is not None]

        self._here = here

        for row in rows:
            if row < self.rowCount():
                index = self.index(row, Column.TIME)
                self.dataChanged.emit(index, index, [Qt.DecorationRole])

    def rowCount(self, parent=QModelIndex()):  # noqa: B008
        if parent.isValid():
            return 0

        return len(self._block.bookmarks)

    def columnCount(self, parent=QModelIndex()):  # noqa: B008
        if parent.isValid():
            return 0

        return len(Column)

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def data(self, index, role=Qt.DisplayRole):
        bookmarks = self._block.bookmarks

        if not index.isValid() or index.row() >= len(bookmarks):
            return None

        row = index.row()
        bookmark = bookmarks[row]
        is_time = index.column() == Column.TIME

        if role in {Qt.DisplayRole, Qt.EditRole} and is_time:
            return ms_time_txt(bookmark.time_ms, self.length)

        if role == Qt.DisplayRole:
            return bookmark.name or default_bookmark_name(row)

        if role == Qt.EditRole:
            return bookmark.name or ""

        if role == DEFAULT_NAME_ROLE:
            return default_bookmark_name(row)

        if role == Qt.DecorationRole and is_time:
            return self._here_icon if row == self._here else self._blank_icon

        if role == Qt.DecorationRole:
            return self._marker_icon(bookmark.color)

        if role == Qt.ForegroundRole:
            return self._foreground(row, bookmark, is_time)

        if role == Qt.FontRole and not is_time and not bookmark.name:
            return self._unnamed_font

        if role == Qt.ToolTipRole:
            return self._out_of_reach_txt(row, bookmark)

        return None

    def _marker_icon(self, color: str | None) -> QIcon:
        """Its marker in its colour, as the bar above draws it."""

        if color not in self._marker_icons:
            self._marker_icons[color] = bookmark_icon(
                [color], self._marker_rim, LIST_ICON_SHARE
            )

        return self._marker_icons[color]

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False

        if index.column() == Column.NAME:
            self.renamed.emit(index.row(), value)
        else:
            self.retimed.emit(index.row(), value)

        return True

    def _foreground(self, row, bookmark, is_time):
        block = self._block

        # with nothing playing none is in reach, nor out of it: the list
        # reads as it did, but for the play mark
        if block.is_video_initialized and not block.is_reachable(bookmark):
            return self._colors.get("out_of_reach")

        if is_time:
            return self._colors.get("time")

        if not bookmark.name:
            return self._colors.get("unnamed")

        return None

    def _out_of_reach_txt(self, row, bookmark) -> str | None:
        if not self._block.is_video_initialized:
            return None

        if self._block.is_reachable(bookmark):
            return None

        if bookmark.time_ms >= self.length:
            return translate("Dialog - Bookmarks", "Past the end of the video")

        return translate("Dialog - Bookmarks", "Outside the loop")


class _EditDelegate(QStyledItemDelegate):
    """A line to type in, over the name or the time; the name's shows what
    the bookmark goes by without one."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)

        if index.column() == Column.NAME:
            editor.setPlaceholderText(index.data(DEFAULT_NAME_ROLE))

        return editor

    def updateEditorGeometry(self, editor, option, index):
        # the whole of the cell across, or the row's highlight shows in the
        # padding beside it; its own margin keeps the text where it was
        editor.setGeometry(option.rect.adjusted(0, 1, 0, -1))


class BookmarkList(QTreeView):
    """The rows of bookmarks, the loop's edges drawn across them.

    It has keys of its own for what its menus offer, and Space plays or
    pauses, the player's own keys being out of reach while the dialog is up.
    """

    jump_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    edit_time_requested = pyqtSignal()
    move_here_requested = pyqtSignal()
    remove_requested = pyqtSignal()
    add_requested = pyqtSignal()
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    play_pause_requested = pyqtSignal()

    # for a row, and for the list itself, from the space under the rows
    menu_requested = pyqtSignal(QPoint)
    list_menu_requested = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setHeaderHidden(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.SelectedClicked)
        self.setIconSize(QSize(HERE_ICON_PX, HERE_ICON_PX))
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(_EditDelegate(self))

        self.setStyleSheet(
            f"""
            QTreeView::item {{
                height: {ROW_HEIGHT}px;
                padding-left: 4px;
                padding-right: 8px;
            }}
            """
        )

        # what the list says with nothing in it: a line, and a hint under it
        self.empty_txt = ("", "")

        # lines across the list: (the row each is drawn above, what it says,
        # its colour), a row past the last for one under them all
        self.edges = ()

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
        # (the view's own copies the current cell's text)
        if event.matches(QKeySequence.Copy):
            return self.copy_requested

        if event.matches(QKeySequence.Paste):
            return self.paste_requested

        modifiers = int(event.modifiers() & ~Qt.KeypadModifier)

        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and not modifiers:
            return self.jump_requested

        return {
            RENAME_KEY: self.rename_requested,
            EDIT_TIME_KEY: self.edit_time_requested,
            MOVE_HERE_KEY: self.move_here_requested,
            REMOVE_KEY: self.remove_requested,
            ADD_KEY: self.add_requested,
            Qt.Key_Space: self.play_pause_requested,
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
            self.menu_requested.emit(global_pos)
        else:
            self.list_menu_requested.emit(global_pos)

        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.model() is None:
            return

        painter = QPainter(self.viewport())

        if self.model().rowCount():
            self._paint_edges(painter)
        else:
            self._paint_empty(painter)

        painter.end()

    def _paint_empty(self, painter):
        paint_empty_txt(self, painter, *self.empty_txt)

    def _paint_edges(self, painter):
        rows = self.model().rowCount()
        width = self.viewport().width()

        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 0.85)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        for row, edge_txt, color in self.edges:
            if row < rows:
                y = self.visualRect(self.model().index(row, 0)).top()
            else:
                y = self.visualRect(self.model().index(rows - 1, 0)).bottom() + 1

            tag_width = metrics.horizontalAdvance(edge_txt) + 12
            # one above the first row hangs below the line, out of the way of
            # the list's edge
            tag_top = max(y - metrics.height() / 2, 0)
            tag = QRectF(width - tag_width - 6, tag_top, tag_width, metrics.height())

            painter.fillRect(QRectF(0, y - 0.5, width, 1), color)
            painter.fillRect(tag, self.palette().color(QPalette.Base))
            painter.setPen(color)
            painter.drawText(tag, Qt.AlignCenter, edge_txt)


class _Markers(OverlayBookmarkMarkers):
    """The markers above the bar as they are over the video, but for those
    of the bookmarks picked out in the list, drawn grown. With no hover
    label here to take the one under the mouse for its pointer, it stays."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._picked = frozenset()

    def set_picked(self, times):
        self._picked = frozenset(times)
        self.update()

    def _paint_markers(self, painter):
        painter.setRenderHint(QPainter.Antialiasing, True)

        picked = []

        for x, marks in self.markers:
            if self._picked.intersection(mark.time_ms for mark in marks):
                picked.append((x, marks))
            else:
                self._draw_marker(painter, x, BOOKMARK_MARKER, marks)

        for x, marks in picked:
            self._draw_marker(painter, x, BOOKMARK_TAIL, marks)


class HoverTip(QLabel):
    """A tooltip that keeps up with the mouse along the bar.

    Qt's own stays where it was shown until its text changes, so along the
    bar it hops from place to place; this one moves with every move of the
    mouse, at a height of its own, and stays up while the mouse is there.
    It looks as Qt's do.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip)

        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.setForegroundRole(QPalette.ToolTipText)
        self.setBackgroundRole(QPalette.ToolTipBase)
        self.setPalette(QToolTip.palette())
        self.setFont(QToolTip.font())

        style = self.style()
        self.setMargin(
            1 + style.pixelMetric(QStyle.PM_ToolTipLabelFrameWidth, None, self)
        )
        self.setFrameStyle(QFrame.NoFrame)
        self.setWindowOpacity(
            style.styleHint(QStyle.SH_ToolTipLabel_Opacity, None, self) / 255
        )

    def show_at(self, text, x, top, bottom):
        """Show the text centred on x, under bottom, or over top where the
        screen ends below it; all on the screen's own coordinates."""

        if text != self.text():
            self.setText(text)
            self.adjustSize()

        screen = QApplication.screenAt(QPoint(x, bottom))
        if screen is None:
            screen = QApplication.primaryScreen()
        area = screen.availableGeometry()

        left = x - self.width() // 2
        left = max(area.left(), min(left, area.right() + 1 - self.width()))

        y = bottom + HOVER_TIP_GAP
        if y + self.height() > area.bottom() + 1:
            y = top - HOVER_TIP_GAP - self.height()

        self.move(left, y)
        self.show()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(QStyle.PE_PanelTipLabel, option)
        painter.end()

        super().paintEvent(event)


class _Bar(OverlayProgressBar):
    """The overlay's bar, in quieter colours."""

    @property
    def color_progress(self):
        return QColor(BAR_PROGRESS_COLOR)

    @property
    def color_select(self):
        return QColor(BAR_SELECT_COLOR)

    @property
    def color_ahead(self):
        return mixed_color(self.color, self.color_contrast_mid, BAR_AHEAD_SHADE)


class PlayerRow(QWidget):
    """The video as its overlay shows it at the foot of its cell: play and
    pause, the time, the bar and the bookmarks' markers above it, the same
    widgets in a grey of the dialog's, set apart, the bar in quieter
    colours."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.play_pause = OverlayPlayPauseButton(parent=self)
        self.time_label = OverlayShortLabel(parent=self)
        self.bar = _Bar(parent=self)
        self.markers = _Markers(bar=self.bar, parent=self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, BOOKMARK_STRIP_HEIGHT, 0, 0)
        layout.setSpacing(PLAYER_ROW_SPACING)
        layout.addWidget(self.play_pause)
        layout.addWidget(self.time_label)
        layout.addWidget(self.bar, 1)

    def set_color(self, color: QColor):
        for widget in (self.play_pause, self.time_label, self.bar, self.markers):
            widget.color = color

    def set_position(self, position_ms: int, length_ms: int):
        position_ms = max(position_ms, 0)

        position_txt = ms_time_txt(position_ms, length_ms)
        length_txt = get_time_txt(length_ms // 1000, length_ms // 1000)

        self.time_label.text = f"{position_txt} / {length_txt}"
        self.time_label.update_visuals()

        self.bar.length = length_ms
        self.bar.position = position_ms / length_ms if length_ms > 0 else 0
        self.markers.set_length(length_ms)

    def set_marks(self, marks):
        self.bar.marks = marks
        self.markers.set_marks(marks)


class BookmarksDialog(QDialog):
    def __init__(self, block, selected=(), parent=None):
        self._is_set_up = False

        super().__init__(parent)

        self._block = block
        self._original = block.bookmarks

        # The video's length as it last played, for while it has no player:
        # stopped, reconnecting, or loaded again. The bookmarks are still
        # there to name, move and take away then.
        self._length = block.video_driver.length

        # what the list shows, to tell a change of the video's from none
        self._shown = None

        # closed, by the viewer or with the video: an edit still on its way
        # from the list then has nothing to be made on
        self._is_done = False

        # the video held at its start, said under the list until it plays
        self._is_held = False

        title = _video_title(block)
        if title:
            self.setWindowTitle(
                translate("Dialog - Bookmarks", "Bookmarks — {VIDEO}").format(
                    VIDEO=title
                )
            )
        else:
            self.setWindowTitle(translate("Dialog - Bookmarks", "Bookmarks"))

        self.setMinimumSize(DIALOG_MIN_SIZE)
        self.resize(DIALOG_SIZE)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(STATUS_MS)
        self._status_timer.timeout.connect(self._show_hint)

        self._ui_setup()
        self._ui_connect()

        self._update_look()
        self._show_position(block.time_to_bookmark, self._length)
        self._player.set_marks(self._bar_marks())
        self._show_loop()
        self._reload()
        self._pick_rows(sorted(selected))
        self._update_paste()
        self._show_hint()

        self._list.setFocus()

        self._is_set_up = True

    def _ui_setup(self):
        self._player = PlayerRow()
        self._hover_tip = HoverTip(self)

        # the bookmarks of the marker the tip is over, none over the bar
        self._tip_marks = ()

        self._model = BookmarksModel(self._block, self)

        self._list = BookmarkList()
        self._list.setModel(self._model)
        self._list.empty_txt = (
            translate("Dialog - Bookmarks", "No bookmarks yet"),
            translate(
                "Dialog - Bookmarks",
                "Add marks where the video is now. Paste adds bookmarks from"
                " copied timestamps, one to a line, like 1:23 Intro.",
            ),
        )

        header = self._list.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(Column.TIME, QHeaderView.Fixed)

        # the count, or what was just done, wrapped onto a line more if long
        self._hint = QLabel()
        self._hint.setWordWrap(True)

        self._add_button = self._button(
            "bookmark-add",
            translate("Dialog - Bookmarks", "Add"),
            translate("Dialog - Bookmarks", "Add a bookmark where the video is now"),
        )
        self._remove_button = self._button(
            "bookmark-remove", translate("Dialog - Bookmarks", "Remove")
        )
        self._copy_button = self._button(
            "copy",
            translate("Dialog - Bookmarks", "Copy All"),
            translate(
                "Dialog - Bookmarks",
                "Copy all the bookmarks as timestamps, one to a line, like 1:23 Intro",
            ),
        )
        self._paste_button = self._button(
            "paste",
            translate("Dialog - Bookmarks", "Paste"),
            translate(
                "Dialog - Bookmarks",
                "Add bookmarks from copied timestamps, one to a line, like 1:23 Intro",
            ),
        )
        self._remove_all_button = self._button(
            "bookmark-remove-all", translate("Dialog - Bookmarks", "Remove All")
        )

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(self._add_button)
        tools.addWidget(self._remove_button)
        tools.addStretch(1)
        tools.addWidget(self._copy_button)
        tools.addWidget(self._paste_button)

        bottom = QHBoxLayout()
        bottom.addWidget(self._remove_all_button)
        bottom.addStretch(1)
        bottom.addWidget(self._buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)
        root.addWidget(self._player)
        root.addWidget(self._list, 1)
        root.addSpacing(-4)
        root.addWidget(self._hint)
        root.addLayout(tools)
        root.addSpacing(4)
        root.addLayout(bottom)

    def _button(self, icon, text, tooltip=None) -> QPushButton:
        button = QPushButton(QIcon.fromTheme(icon), text)
        button.setIconSize(QSize(16, 16))
        button.setAutoDefault(False)

        if tooltip:
            button.setToolTip(tooltip)

        return button

    def _ui_connect(self):
        block = self._block

        # the video's, let go of once the dialog is done
        self._block_connections = [
            (block.time_change, self._show_position),
            (block.is_paused_change, self._show_paused),
            (block.is_stopped_change, self._show_stopped),
            (block.seek_marks_change, self._on_marks_change),
            (block.loop_start_change, self._show_loop),
            (block.loop_end_change, self._show_loop),
        ]
        for signal, slot in self._block_connections:
            signal.connect(slot)

        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self._update_paste)
        self._block_connections.append((clipboard.dataChanged, self._update_paste))

        player = self._player
        player.play_pause.clicked.connect(self._play_pause)
        player.bar.position_changed.connect(
            lambda position: block.manual_seek("seek_percent", position)
        )
        player.bar.mouse_over.connect(self._show_bar_tooltip)
        player.bar.mouse_left.connect(self._hide_hover_tip)
        player.markers.marker_over.connect(self._show_marker_tooltip)
        player.markers.marker_left.connect(self._hide_hover_tip)
        player.markers.marker_clicked.connect(self._on_marker_clicked)
        player.markers.marker_menu_requested.connect(self._on_marker_menu)

        # edits are made once the editor they came from is closed: made at
        # once, they would take the rows from under it
        self._model.renamed.connect(self._rename, Qt.QueuedConnection)
        self._model.retimed.connect(self._retime, Qt.QueuedConnection)

        self._list.selectionModel().selectionChanged.connect(self._on_pick)
        self._list.selectionModel().currentChanged.connect(self._on_pick)
        self._list.doubleClicked.connect(self._on_double_click)
        self._list.jump_requested.connect(self._jump)
        self._list.rename_requested.connect(self._edit_name)
        self._list.edit_time_requested.connect(self._edit_time)
        self._list.move_here_requested.connect(self._move_here)
        self._list.remove_requested.connect(self._remove)
        self._list.add_requested.connect(self._add)
        self._list.copy_requested.connect(self._copy)
        self._list.paste_requested.connect(self._paste)
        self._list.play_pause_requested.connect(self._play_pause)
        self._list.menu_requested.connect(self._show_row_menu)
        self._list.list_menu_requested.connect(self._show_list_menu)

        self._add_button.clicked.connect(self._add)
        self._remove_button.clicked.connect(self._remove)
        self._copy_button.clicked.connect(lambda _=False: self._copy_all())
        self._paste_button.clicked.connect(self._paste)
        self._remove_all_button.clicked.connect(self._remove_all)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

    def reject(self):
        if self._block.bookmarks != self._original:
            self._block.set_bookmarks(self._original)

        super().reject()

    def done(self, result):
        self._is_done = True

        for signal, slot in self._block_connections:
            signal.disconnect(slot)

        self._block_connections = []

        self._hide_hover_tip()

        super().done(result)

    def changeEvent(self, event):
        super().changeEvent(event)

        # (one may come while the dialog is still being put together)
        if self._is_set_up and event.type() in {
            QEvent.PaletteChange,
            QEvent.FontChange,
        }:
            self._update_look()

    # The video

    @property
    def _video_length(self) -> int:
        if self._block.is_video_initialized:
            return self._block.video_driver.length

        return self._length

    def _show_position(self, position_ms, length_ms):
        if length_ms > 0:
            self._length = length_ms

        # Where Add would put a bookmark, to the millisecond: a seek on its
        # way counts as there, as VLC reports a time a hair short of where
        # one landed, and a jump to a bookmark would read as short of it.
        if self._block.is_video_initialized:
            position_ms = self._block.time_to_bookmark

        self._player.set_position(position_ms, self._length)
        self._model.set_here(self._block.bookmark_here)

        self._update_buttons()

        # over a marker standing for several, the one the video is on, after
        # a click on it, say
        if self._tip_marks and self._hover_tip.isVisible():
            self._show_hover_tip(self._marker_tip_txt())

    def _show_paused(self, is_paused):
        self._player.play_pause.is_off = not is_paused

        # held at the start, and played on from there
        if not is_paused and self._is_held:
            self._show_hint()

    def _show_stopped(self, is_stopped):
        # back at the start, where it plays from again
        if is_stopped:
            self._show_position(0, self._length)

    def _show_loop(self, _position=None):
        block = self._block

        # with no player the loop's end is nowhere to be read, and the marks
        # stay where they were: a stop clears them first
        if block.is_video_initialized and self._video_length > 0:
            self._player.bar.loop_start = block.loop_start / self._video_length
            self._player.bar.loop_end = block.loop_end / self._video_length

        self._refresh()

    def _on_marks_change(self, _marks):
        self._player.set_marks(self._bar_marks())

        self._refresh()

    def _bar_marks(self):
        """What the bar marks: what the bar over the video does, or while the
        video has no player, its bookmarks still, where they were."""

        block = self._block

        if block.is_video_initialized:
            return block.seek_marks

        return block.bookmark_marks(self._length)

    def _play_pause(self):
        # Stopped, it is played from the start. Loading, or reconnecting,
        # there is nothing to play or pause yet, and a start now would race
        # the one on its way.
        if self._block.is_playable:
            self._block.play_pause()

    def _update_look(self):
        palette = self.palette()

        self._player.set_color(
            mixed_color(
                palette.color(QPalette.Window),
                palette.color(QPalette.WindowText),
                BAR_TINT,
            )
        )
        self._show_paused(self._block.video_params.is_paused)

        self._model.set_look(palette, self._list.font())

        self._fit_time_column()
        self._update_edges()
        self._show_count()

    # The list

    def _refresh(self):
        """Show the video's bookmarks again, if they read otherwise now: new
        ones, or ones come into reach or gone out of it."""

        if self._shown != self._shown_now():
            self._reload()

    def _shown_now(self):
        block = self._block
        bookmarks = block.bookmarks

        return (
            bookmarks,
            block.is_video_initialized,
            tuple(block.is_reachable(bookmark) for bookmark in bookmarks),
            self._video_length,
            block.loop_start,
            block.loop_end,
        )

    def _reload(self):
        picked_times = self._picked_times()
        current_time = self._current_time()

        self._model.length = self._video_length
        self._model.reload()
        self._shown = self._shown_now()

        self._fit_time_column()
        self._update_edges()
        self._show_count()

        times = [bookmark.time_ms for bookmark in self._block.bookmarks]
        self._pick_rows(
            [times.index(time) for time in picked_times if time in times],
            times.index(current_time) if current_time in times else None,
        )

    def _fit_time_column(self):
        length = self._video_length
        widest = self._list.fontMetrics().horizontalAdvance(ms_time_txt(length, length))

        # the play mark and the room either side of it and the time
        self._list.header().resizeSection(Column.TIME, HERE_ICON_PX + widest + 32)

    def _update_edges(self):
        self._list.edges = self._edges()
        self._list.viewport().update()

    def _edges(self):
        """Where the loop starts and ends among the bookmarks, and the video
        ends, each above the first row past it."""

        block = self._block

        if not block.is_video_initialized:
            return ()

        length = self._video_length
        bookmarks = block.bookmarks

        on_bar = sum(1 for bookmark in bookmarks if bookmark.time_ms < length)
        reachable = [
            i
            for i, bookmark in enumerate(bookmarks[:on_bar])
            if block.is_reachable(bookmark)
        ]

        loop_color = QColor(
            LOOP_EDGE_COLOR_DARK
            if self.palette().color(QPalette.Base).lightness() < 128
            else LOOP_EDGE_COLOR_LIGHT
        )
        end_color = self.palette().color(QPalette.Disabled, QPalette.Text)

        def time_txt(time_ms):
            return get_time_txt(time_ms // 1000, length // 1000)

        edges = []

        is_loop_set = block.loop_start > 0 or block.loop_end < length

        if is_loop_set and on_bar:
            if not reachable:
                # the loop sits between two of them
                row = sum(
                    1
                    for bookmark in bookmarks[:on_bar]
                    if bookmark.time_ms < block.loop_start
                )
                loop_txt = translate("Dialog - Bookmarks", "loop {START}-{END}").format(
                    START=time_txt(block.loop_start), END=time_txt(block.loop_end)
                )
                edges.append((row, loop_txt, loop_color))
            else:
                if reachable[0] > 0:
                    start_txt = translate(
                        "Dialog - Bookmarks", "loop start {TIME}"
                    ).format(TIME=time_txt(block.loop_start))
                    edges.append((reachable[0], start_txt, loop_color))

                if reachable[-1] < on_bar - 1:
                    end_txt = translate("Dialog - Bookmarks", "loop end {TIME}").format(
                        TIME=time_txt(block.loop_end)
                    )
                    edges.append((reachable[-1] + 1, end_txt, loop_color))

        if on_bar < len(bookmarks):
            video_end_txt = translate("Dialog - Bookmarks", "end {TIME}").format(
                TIME=time_txt(length)
            )
            edges.append((on_bar, video_end_txt, end_color))

        return tuple(_joined_edges(edges))

    def _picked_rows(self) -> list[int]:
        return sorted(
            index.row() for index in self._list.selectionModel().selectedRows()
        )

    def _picked_times(self) -> list[int]:
        bookmarks = self._block.bookmarks

        return [
            bookmarks[row].time_ms
            for row in self._picked_rows()
            if row < len(bookmarks)
        ]

    def _current_row(self) -> int | None:
        index = self._list.currentIndex()

        if not index.isValid() or index.row() >= len(self._block.bookmarks):
            return None

        return index.row()

    def _current_time(self) -> int | None:
        row = self._current_row()

        return None if row is None else self._block.bookmarks[row].time_ms

    def _pick_rows(self, rows, current=None):
        """Pick these rows out, the current one the given one or the first."""

        selection = self._list.selectionModel()
        selection.clearSelection()

        rows = [row for row in rows if 0 <= row < self._model.rowCount()]

        if not rows:
            self._on_pick()
            return

        if current not in rows:
            current = rows[0]

        selection.setCurrentIndex(
            self._model.index(current, Column.NAME), selection.NoUpdate
        )

        for row in rows:
            selection.select(
                self._model.index(row, Column.TIME),
                selection.Select | selection.Rows,
            )

        self._list.scrollTo(self._model.index(current, Column.TIME))

        self._on_pick()

    def _pick_times(self, times, current_time=None):
        bookmark_times = [bookmark.time_ms for bookmark in self._block.bookmarks]

        rows = [bookmark_times.index(t) for t in times if t in bookmark_times]
        current = (
            bookmark_times.index(current_time)
            if current_time in bookmark_times
            else None
        )

        self._pick_rows(rows, current)

    def _on_pick(self, *_):
        self._player.markers.set_picked(self._picked_times())

        self._update_buttons()

    def _update_buttons(self):
        has_any = bool(self._block.bookmarks)
        is_playing = self._block.is_video_initialized

        self._player.play_pause.setEnabled(self._block.is_playable)
        self._add_button.setEnabled(is_playing)
        self._remove_button.setEnabled(bool(self._picked_rows()))
        self._copy_button.setEnabled(has_any)
        self._remove_all_button.setEnabled(has_any)

    def _update_paste(self):
        self._paste_button.setEnabled(bool(self._pasted()))

    def _pasted(self) -> list[Bookmark]:
        return parse_bookmarks_txt(QApplication.clipboard().text())

    # What is said under the list

    def _show_hint(self):
        """Back to the count, from what was said."""

        self._status_timer.stop()
        self._is_held = False

        self._show_count()

    def _show_count(self):
        # not over what is being said
        if self._status_timer.isActive() or self._is_held:
            return

        count = len(self._block.bookmarks)

        self._hint.setText(
            translate("Dialog - Bookmarks", "Bookmarks: {COUNT}").format(COUNT=count)
            if count
            else ""
        )
        self._hint.setForegroundRole(QPalette.PlaceholderText)

    def _say(self, text, is_lasting=False):
        self._hint.setText(text)
        self._hint.setForegroundRole(QPalette.WindowText)

        self._is_held = is_lasting

        if is_lasting:
            self._status_timer.stop()
        else:
            self._status_timer.start()

    def hold_end(self, end_action):
        """Say the video is held at its start in place of its end action;
        said until it plays again, being easily missed.

        The end action is not made up for once the dialog is closed: the
        video stays where it is, and ends as it is set to the next time.
        """

        self._say(
            translate(
                "Dialog - Bookmarks",
                "Paused at the start instead of “{ACTION}” while this is open.",
            ).format(ACTION=held_end_action_txt(end_action)),
            is_lasting=True,
        )

    # Tooltips over the bar

    def _show_bar_tooltip(self, _top_edge, position, _bar_width):
        # no times to go to with nothing playing
        if not self._block.is_video_initialized:
            return

        length = self._video_length
        time_ms = int(position * length)

        lines = [ms_time_txt(time_ms, length)]

        chapter = chapter_at(self._block.seek_marks, time_ms, length)
        if chapter is not None:
            lines.append(chapter[0].label)

        self._tip_marks = ()
        self._show_hover_tip("\n".join(lines))

    def _show_marker_tooltip(self, _top_edge, marks, _bar_width):
        self._tip_marks = tuple(
            mark for mark in marks if mark.kind == SeekMarkKind.BOOKMARK
        )

        self._show_hover_tip(self._marker_tip_txt())

    def _marker_tip_txt(self) -> str:
        """The bookmarks of the marker under the mouse, a line each; of
        several, the one the video is on in bold, a click going to the one
        after it. Each with its marker in its colour between its time and its
        name, as in the list and over the video; of a striped marker, that
        tells the stripes apart."""

        length = self._video_length
        marks = self._tip_marks

        on = None
        if len(marks) > 1 and self._block.is_video_initialized:
            on = bookmark_on(marks, self._block.time_to_bookmark)

        lines = []

        for mark in marks:
            time_txt = html.escape(ms_time_txt(mark.time_ms, length))
            name_txt = html.escape(mark.label)

            lines.append(f"{time_txt} {self._tip_marker_html(mark.color)}{name_txt}")

        if on is not None:
            lines[on] = f"<b>{lines[on]}</b>"

        return '<div style="white-space: pre">{}</div>'.format("<br>".join(lines))

    def _tip_marker_html(self, color: str | None) -> str:
        tip = self._hover_tip

        return text_marker_html(
            color,
            tip.palette().color(QPalette.ToolTipText),
            math.ceil(tip.devicePixelRatioF()),
        )

    def _hide_hover_tip(self):
        self._tip_marks = ()
        self._hover_tip.hide()

    def _show_hover_tip(self, text):
        """Under the bar, where the mouse is along it."""

        bar = self._player.bar
        top = bar.mapToGlobal(QPoint(0, 0)).y() - BOOKMARK_STRIP_HEIGHT
        bottom = bar.mapToGlobal(QPoint(0, bar.height())).y()

        self._hover_tip.show_at(text, QCursor.pos().x(), top, bottom)

    # What the viewer does

    def _on_marker_clicked(self, times):
        # each of those it stands for in turn, as over the video
        row = self._block.marker_bookmark_to_go(times)

        if row is None:
            self._pick_times(times[:1])
            return

        self._pick_rows([row])
        self._jump()

    def _on_marker_menu(self, global_pos, times):
        self._pick_times(times)
        self._show_row_menu(global_pos)

    def _on_double_click(self, index):
        if index.isValid():
            self._jump()

    def _jump(self):
        row = self._current_row()

        if self._is_done or row is None or not self._block.is_bookmark_reachable(row):
            return

        self._block.manual_seek("seek_bookmark", row)

    def _edit_name(self):
        self._edit(Column.NAME)

    def _edit_time(self):
        self._edit(Column.TIME)

    def _edit(self, column):
        row = self._current_row()

        if row is not None:
            self._list.edit(self._model.index(row, column))

    def _add(self):
        block = self._block

        if not block.is_video_initialized:
            return

        time_ms = block.time_to_bookmark

        if is_bookmarked(block.bookmarks, time_ms):
            self._pick_times([self._nearest_time(time_ms)])
            self._say(translate("Bookmarks", "Already bookmarked"))
            return

        self._apply(
            with_bookmark(block.bookmarks, Bookmark(time_ms=time_ms)), [time_ms]
        )

        # named straight away, or left to go by its number with Enter or Esc
        self._edit_name()

    def _remove(self):
        rows = self._picked_rows()

        if not rows:
            return

        remaining = [
            bookmark
            for row, bookmark in enumerate(self._block.bookmarks)
            if row not in rows
        ]

        self._apply(remaining, [])

        # the one after those, where they were
        if remaining:
            self._pick_rows([min(rows[0], len(remaining) - 1)])

    def _remove_all(self):
        self._apply([], [])

    def _rename(self, row, name):
        bookmarks = self._block.bookmarks

        if row >= len(bookmarks):
            return

        bookmark = bookmarks[row]
        name = name.strip() or None

        if name == bookmark.name:
            return

        renamed = list(bookmarks)
        renamed[row] = bookmark.model_copy(update={"name": name})

        self._apply(renamed, [bookmark.time_ms])

    def _retime(self, row, time_txt):
        bookmarks = self._block.bookmarks

        if row >= len(bookmarks):
            return

        # left as it was shown, it stays where it is
        shown_txt = self._model.index(row, Column.TIME).data(Qt.EditRole)
        if time_txt.strip() == shown_txt:
            return

        time_ms = parse_time_txt(time_txt)

        if time_ms is None:
            self._say(
                translate("Dialog - Bookmarks", "Not a time: {TEXT}").format(
                    TEXT=time_txt.strip()
                )
            )
            return

        self._move(row, time_ms)

    def _move_here(self):
        row = self._current_row()

        if row is None or not self._block.is_video_initialized:
            return

        self._move(row, self._block.time_to_bookmark)

    def _move(self, row, time_ms):
        bookmarks = self._block.bookmarks
        bookmark = bookmarks[row]

        if time_ms == bookmark.time_ms:
            return

        if time_ms >= self._video_length:
            self._say(translate("Dialog - Bookmarks", "Past the end of the video"))
            return

        others = [b for i, b in enumerate(bookmarks) if i != row]

        if is_bookmarked(others, time_ms):
            self._say(
                translate("Dialog - Bookmarks", "Another bookmark is there already")
            )
            return

        moved = bookmark.model_copy(update={"time_ms": time_ms})

        self._apply(with_bookmark(others, moved), [time_ms])

    def _color(self, color: str | None):
        """Colour the picked bookmarks, None giving them back the bookmarks'
        own."""

        bookmarks = self._block.bookmarks
        picked = [row for row in self._picked_rows() if row < len(bookmarks)]

        colored = [
            bookmark.model_copy(update={"color": color}) if row in picked else bookmark
            for row, bookmark in enumerate(bookmarks)
        ]

        if colored == list(bookmarks):
            return

        self._apply(
            colored,
            [bookmarks[row].time_ms for row in picked],
            self._current_time(),
        )

    def _pick_color(self):
        """Colour the picked bookmarks in one picked by hand, starting from
        the current one's."""

        row = self._current_row()

        if row is None:
            return

        color = color_picked_by_hand(self, self._block.bookmarks[row].color)

        if color is not None and not self._is_done:
            self._color(color)

    def _copy(self, is_precise=False):
        """Copy the picked bookmarks."""

        bookmarks = self._block.bookmarks
        picked = self._picked_rows()

        self._copy_bookmarks(
            [bookmarks[row] for row in picked if row < len(bookmarks)], is_precise
        )

    def _copy_all(self, is_precise=False):
        self._copy_bookmarks(self._block.bookmarks, is_precise)

    def _copy_bookmarks(self, bookmarks, is_precise):
        if not bookmarks:
            return

        QApplication.clipboard().setText(
            bookmarks_txt(bookmarks, self._video_length, is_precise)
        )

        self._say(
            translate("Dialog - Bookmarks", "Bookmarks copied: {COUNT}").format(
                COUNT=len(bookmarks)
            )
        )

    def _paste(self):
        pasted = self._pasted()

        # (the button is grayed out then, but not the key)
        if not pasted:
            self._say(translate("Dialog - Bookmarks", "No timestamps to paste"))
            return

        new = new_in_txt(
            self._block.bookmarks,
            QApplication.clipboard().text(),
            self._video_length,
        )

        if not new:
            self._say(translate("Dialog - Bookmarks", "Nothing new to add"))
            return

        bookmarks = list(self._block.bookmarks)
        for bookmark in new:
            bookmarks = with_bookmark(bookmarks, bookmark)

        self._apply(bookmarks, [bookmark.time_ms for bookmark in new])

        self._say(
            translate("Dialog - Bookmarks", "Bookmarks added: {COUNT}").format(
                COUNT=len(new)
            )
        )

    def _apply(self, bookmarks, picked_times, current_time=None):
        """Give the video these bookmarks, and pick out those at these times,
        the one at current_time the current one, or the first."""

        if self._is_done:
            return

        self._block.set_bookmarks(bookmarks)

        # the video's bar marks them for this one while it plays; with
        # nothing playing it marks none, and this one goes on its own
        self._player.set_marks(self._bar_marks())

        self._reload()
        self._pick_times(picked_times, current_time)

    def _nearest_time(self, time_ms) -> int:
        return min(
            (bookmark.time_ms for bookmark in self._block.bookmarks),
            key=lambda bookmark_ms: abs(bookmark_ms - time_ms),
        )

    def _show_row_menu(self, global_pos):
        row = self._current_row()

        if row is None:
            return

        is_playing = self._block.is_video_initialized

        menu = CustomMenu(parent=self)

        jump = menu.addAction(
            QIcon.fromTheme("jump-to"),
            with_key_txt(translate("Actions", "Jump to Bookmark"), Qt.Key_Enter),
        )
        jump.setEnabled(self._block.is_bookmark_reachable(row))
        jump.triggered.connect(lambda _=False: self._jump())

        menu.addSeparator()

        rename = menu.addAction(
            QIcon.fromTheme("bookmark-rename"),
            with_key_txt(translate("Dialog - Bookmarks", "Rename"), RENAME_KEY),
        )
        rename.triggered.connect(lambda _=False: self._edit_name())

        edit_time = menu.addAction(
            QIcon.fromTheme("delay"),
            with_key_txt(translate("Dialog - Bookmarks", "Edit Time"), EDIT_TIME_KEY),
        )
        edit_time.triggered.connect(lambda _=False: self._edit_time())

        move_here = menu.addAction(
            QIcon.fromTheme("empty"),
            with_key_txt(
                translate("Dialog - Bookmarks", "Move to Current Position"),
                MOVE_HERE_KEY,
            ),
        )
        move_here.setEnabled(is_playing)
        move_here.triggered.connect(lambda _=False: self._move_here())

        bookmarks = self._block.bookmarks

        menu.addMenu(
            bookmark_color_menu(
                menu,
                [bookmarks[row].color for row in self._picked_rows()],
                slot_for=lambda color: lambda _=False: self._color(color),
                custom_slot=lambda _=False: self._pick_color(),
            )
        )

        menu.addSeparator()

        copy = menu.addAction(
            QIcon.fromTheme("copy"),
            with_key_txt(translate("Dialog - Bookmarks", "Copy"), QKeySequence.Copy),
        )
        copy.setEnabled(bool(self._picked_rows()))
        copy.triggered.connect(lambda _=False: self._copy())

        copy_precise = menu.addAction(
            QIcon.fromTheme("empty"),
            translate("Dialog - Bookmarks", "Copy with Milliseconds"),
        )
        copy_precise.setEnabled(copy.isEnabled())
        copy_precise.triggered.connect(lambda _=False: self._copy(is_precise=True))

        menu.addSeparator()

        remove = menu.addAction(
            QIcon.fromTheme("bookmark-remove"),
            with_key_txt(translate("Dialog - Bookmarks", "Remove"), REMOVE_KEY),
        )
        remove.triggered.connect(lambda _=False: self._remove())

        menu.exec_(global_pos)
        menu.deleteLater()

    def _show_list_menu(self, global_pos):
        """What can be done with the list as a whole, from under its rows."""

        has_any = bool(self._block.bookmarks)

        menu = CustomMenu(parent=self)

        add = menu.addAction(
            QIcon.fromTheme("bookmark-add"),
            with_key_txt(translate("Dialog - Bookmarks", "Add"), ADD_KEY),
        )
        add.setEnabled(self._block.is_video_initialized)
        add.triggered.connect(lambda _=False: self._add())

        menu.addSeparator()

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

        paste = menu.addAction(
            QIcon.fromTheme("paste"),
            with_key_txt(translate("Dialog - Bookmarks", "Paste"), QKeySequence.Paste),
        )
        paste.setEnabled(bool(self._pasted()))
        paste.triggered.connect(lambda _=False: self._paste())

        menu.addSeparator()

        remove_all = menu.addAction(
            QIcon.fromTheme("bookmark-remove-all"),
            translate("Dialog - Bookmarks", "Remove All"),
        )
        remove_all.setEnabled(has_any)
        remove_all.triggered.connect(lambda _=False: self._remove_all())

        menu.exec_(global_pos)
        menu.deleteLater()


def _joined_edges(edges):
    """One line to a row: two falling on the same one say both on it."""

    joined = {}

    for row, edge_txt, color in edges:
        if row in joined:
            first_txt, first_color = joined[row]
            joined[row] = (f"{first_txt} · {edge_txt}", first_color)
        else:
            joined[row] = (edge_txt, color)

    return [(row, edge_txt, color) for row, (edge_txt, color) in sorted(joined.items())]
