"""What the editors of the layout share, Edit Grid's (GridEditor) and Edit
Tiles' (TileEditor): a window over the grid, the videos dimmed under it,
each outlined with its name, and a bar of buttons along the bottom."""

import functools
from collections.abc import Callable

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.qt import translate
from gridplayer.widgets.closing_click import EatenClick
from gridplayer.widgets.grid_line_mark import EDGE_COLOR, LINE_COLOR, GridLineTag
from gridplayer.widgets.settings_controls import SegmentedChoice

# the videos dimmed under the editor, or hidden where a window cannot be
# seen through
VEIL_COLOR = QColor(0, 0, 0, 150)
OPAQUE_COLOR = QColor("#202020")

NAME_BACK_COLOR = QColor(0, 0, 0, 170)
# the others, while one is dragged
DIM_COLOR = QColor("#5a5a5a")
DIM_TEXT_COLOR = QColor("#8a8a8a")

# the bar, dark whatever the theme, as the videos' own buttons are
BAR_STYLE = (
    "#layoutEditorBar { background: rgba(30, 30, 30, 235);"
    " border: 1px solid #474747; border-radius: 18px; }"
    " QLabel { color: #e6e6e6; }"
    " QPushButton { color: #e6e6e6; background: transparent; border: none;"
    " border-radius: 14px; font-size: 15px; }"
    " QPushButton:hover { background: #3c3c3c; }"
    # brighter than the pointer over it: told apart as it is clicked
    " QPushButton:checked { background: #555555; }"
    " QPushButton:disabled { color: #6a6a6a; }"
    " QPushButton#layoutEditorDone { background: #e6e6e6; color: #111111;"
    " font-weight: bold; font-size: 12px; padding: 0 14px; }"
    " QPushButton#layoutEditorDone:hover { background: #ffffff; }"
)
# over the cell or tile a dragged one would swap with
SWAP_COLOR = QColor(255, 255, 255, 40)

BAR_HEIGHT = 36
BAR_BUTTON = 28
BAR_ICON_COLOR = QColor("#e6e6e6")
BAR_ICON_OFF_COLOR = QColor("#6a6a6a")
BAR_SEPARATOR_COLOR = "#4a4a4a"
BAR_GRIP_COLOR = QColor("#8a8a8a")
# how far an icon's filled tile keeps from a line beside it: clear of the
# menu's thin line, and of the bar's
FILL_GAP = 1.4

# a popup of the bar's box
POPUP_BACK_COLOR = QColor(30, 30, 30, 245)
POPUP_BORDER_COLOR = QColor("#474747")
POPUP_RADIUS = 10
POPUP_TITLE_COLOR = QColor("#9a9a9a")
# the keys in the list of them, and what they do
KEY_COLOR = QColor("#e6e6e6")
KEY_DOES_COLOR = QColor("#b4b4b4")

# the colours of the controls in a popup, dark whatever the theme
POPUP_PALETTE = {
    QPalette.Text: "#e6e6e6",
    QPalette.WindowText: "#e6e6e6",
    QPalette.ButtonText: "#e6e6e6",
    QPalette.Base: "#1e1e1e",
    QPalette.Window: "#1e1e1e",
    QPalette.Button: "#2a2a2a",
    QPalette.Highlight: "#4a4a4a",
    QPalette.HighlightedText: "#e6e6e6",
}

HINT_STYLE = (
    "background: rgba(0, 0, 0, 160); color: #cfcfcf;"
    " border-radius: 12px; padding: 4px 12px;"
)

# between an outline and the edge of what it outlines
INSET = 4

# how big the handles to size by are drawn
HANDLE = 10

# the button in a video's name that closes it
CLOSE_SIZE = 16
# an icon before a name, a padlock
NAME_ICON = 12

# how near an edge or a corner of a cell or a tile the pointer takes it
EDGE_REACH = 8
CORNER_REACH = 14

# the pointer over each edge and corner of a tile, to size it by
SIZE_CURSORS = {
    (-1, 0): Qt.SizeHorCursor,
    (1, 0): Qt.SizeHorCursor,
    (0, -1): Qt.SizeVerCursor,
    (0, 1): Qt.SizeVerCursor,
    (-1, -1): Qt.SizeFDiagCursor,
    (1, 1): Qt.SizeFDiagCursor,
    (1, -1): Qt.SizeBDiagCursor,
    (-1, 1): Qt.SizeBDiagCursor,
}

DONE_KEYS = frozenset({Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter})
MODIFIER_KEYS = frozenset(
    {Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_AltGr, Qt.Key_Meta}
)


def bar_icon(kind: str, ratio: float) -> QIcon:
    """An icon of the bar's (see icon_paths), dim where the button is
    off."""

    icon = QIcon()
    for mode, color in (
        (QIcon.Normal, BAR_ICON_COLOR),
        (QIcon.Disabled, BAR_ICON_OFF_COLOR),
    ):
        pixmap = QPixmap(QSize(16, 16) * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_icon(painter, kind, QRectF(0, 0, 16, 16), color)
        painter.end()

        icon.addPixmap(pixmap, mode)
    return icon


def paint_icon(painter: QPainter, kind: str, rect: QRectF, color: QColor) -> None:
    """One of the editors' small line icons (see icon_paths), drawn to fill
    the rect."""

    lines, fill = icon_paths(kind)
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 16, rect.height() / 16)
    if fill is not None:
        painter.fillPath(fill, color)
    pen = QPen(color, 1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(lines)
    painter.restore()


def _sparkle(x: float, y: float, size: float) -> QPainterPath:
    """A four-pointed star, its points `size` from its middle at x, y."""

    waist = size * 0.4
    near, far = waist * 0.3, waist
    path = QPainterPath()
    path.moveTo(x, y - size)
    path.cubicTo(x + near, y - far, x + far, y - near, x + size, y)
    path.cubicTo(x + far, y + near, x + near, y + far, x, y + size)
    path.cubicTo(x - near, y + far, x - far, y + near, x - size, y)
    path.cubicTo(x - far, y - near, x - near, y - far, x, y - size)
    path.closeSubpath()
    return path


# the same each time, and only drawn by those taking them
@functools.cache
def icon_paths(kind: str) -> tuple[QPainterPath, QPainterPath | None]:
    """An icon's lines, and what of it is filled, if anything: the rows, the
    columns, the lines fitted to the videos or reset, undo, redo, reopen; the
    tiles arranged, how much that may crop, fitted to the window, kept
    as the window is resized, one over another, snapping; a lock, a tile put
    in front, or behind.

    The menu's icons for the tiles and snapping (resources/icons/custom) are
    these drawings, with the menu's lighter line."""

    path = QPainterPath()
    fill = None
    if kind in {"rows", "cols"}:
        path.addRoundedRect(QRectF(2, 2.5, 12, 11), 1.5, 1.5)
        for at in (6.2, 9.8) if kind == "rows" else (6, 10):
            if kind == "rows":
                path.moveTo(2, at)
                path.lineTo(14, at)
            else:
                path.moveTo(at, 2.5)
                path.lineTo(at, 13.5)
    elif kind == "fit_lines":
        # cells of two widths, as their videos need, as the menu has it
        path.addRoundedRect(QRectF(2, 2.5, 4, 11), 1, 1)
        path.addRoundedRect(QRectF(8, 2.5, 6, 11), 1, 1)
    elif kind == "reset_lines":
        # cells of one width, the line between them brought back to the
        # middle
        path.addRoundedRect(QRectF(2, 2, 5.2, 7.5), 1, 1)
        path.addRoundedRect(QRectF(8.8, 2, 5.2, 7.5), 1, 1)
        for tip, start, back in ((6.8, 2, 5), (9.2, 14, 11)):
            path.moveTo(start, 12.5)
            path.lineTo(tip, 12.5)
            path.moveTo(back, 10.8)
            path.lineTo(tip, 12.5)
            path.lineTo(back, 14.2)
    elif kind == "reopen":
        # an empty cell, its corners alone, with a plus: filled again, as the
        # menu has it
        for x, y, dx, dy in (
            (2, 2, 1, 1),
            (14, 2, -1, 1),
            (2, 14, 1, -1),
            (14, 14, -1, -1),
        ):
            path.moveTo(x + 3 * dx, y)
            path.lineTo(x, y)
            path.lineTo(x, y + 3 * dy)
        path.moveTo(8, 5)
        path.lineTo(8, 11)
        path.moveTo(5, 8)
        path.lineTo(11, 8)
    elif kind == "arrange":
        # tiles of a few sizes, lined up, filled in, and a sparkle: done for
        # you
        tiles = QPainterPath()
        for rect in ((2, 2.5, 5.5, 5), (2, 9.5, 3.5, 4), (7.5, 9.5, 6.5, 4)):
            tiles.addRect(QRectF(*rect))
        # its middle on a pixel's middle in the menu and on the bar, so its
        # thin points come out even
        fill = _sparkle(11.6, 5.2, 2.95)
        fill.addPath(tiles)
    elif kind == "crop":
        # two corners crossing, where a picture is cut, as the menu's crop
        path.moveTo(4.5, 2)
        path.lineTo(4.5, 11.5)
        path.lineTo(14, 11.5)
        path.moveTo(2, 4.5)
        path.lineTo(11.5, 4.5)
        path.lineTo(11.5, 14)
    elif kind == "fit":
        # the window, the tiles stretched out to its sides
        path.addRoundedRect(QRectF(2, 2.5, 12, 11), 1.5, 1.5)
        path.moveTo(5, 8)
        path.lineTo(11, 8)
        for tip, back in ((5, 7), (11, 9)):
            path.moveTo(back, 6)
            path.lineTo(tip, 8)
            path.lineTo(back, 10)
    elif kind == "window_resize":
        # the window, a grip in its corner: what is done as it is resized
        path.addRoundedRect(QRectF(2, 2.5, 12, 11), 1.5, 1.5)
        path.moveTo(7.5, 11.5)
        path.lineTo(12, 7)
        path.moveTo(10, 11.5)
        path.lineTo(12, 9.5)
    elif kind == "overlap":
        # one tile over another, the hidden corner of the one behind left out
        path.moveTo(6, 9)
        path.lineTo(2, 9)
        path.lineTo(2, 2)
        path.lineTo(10, 2)
        path.lineTo(10, 6)
        path.addRect(QRectF(6, 6, 8, 8))
    elif kind == "snap":
        # a magnet, one closed outline, its poles marked off
        path.moveTo(2.5, 2.5)
        path.lineTo(6, 2.5)
        path.lineTo(6, 8.5)
        path.arcTo(QRectF(6, 6.5, 4, 4), 180, 180)
        path.lineTo(10, 2.5)
        path.lineTo(13.5, 2.5)
        path.lineTo(13.5, 8.5)
        path.arcTo(QRectF(2.5, 3, 11, 11), 0, -180)
        path.closeSubpath()
        path.moveTo(2.5, 5.5)
        path.lineTo(6, 5.5)
        path.moveTo(10, 5.5)
        path.lineTo(13.5, 5.5)
    elif kind == "help":
        path.addEllipse(QRectF(2, 2, 12, 12))
        path.moveTo(6.2, 6.4)
        path.arcTo(QRectF(6.2, 4.4, 3.6, 3.6), 180, -220)
        path.lineTo(8, 9.2)
        path.moveTo(8, 11.4)
        path.lineTo(8, 11.5)
    elif kind == "lock":
        path.addRoundedRect(QRectF(3.5, 7.5, 9, 6.5), 1, 1)
        path.moveTo(5.5, 7.5)
        path.lineTo(5.5, 5.5)
        path.arcTo(QRectF(5.5, 2.5, 5, 5), 180, -180)
        path.lineTo(10.5, 7.5)
    elif kind == "front":
        # the tile filled in front, the one behind stopped short of it
        path.moveTo(6 - FILL_GAP, 10)
        path.lineTo(2, 10)
        path.lineTo(2, 2)
        path.lineTo(10, 2)
        path.lineTo(10, 6 - FILL_GAP)
        fill = QPainterPath()
        fill.addRect(QRectF(6, 6, 8, 8))
    elif kind == "back":
        # what shows of the tile filled behind, kept as clear of the one in
        # front as the front's line is of its fill
        path.addRect(QRectF(6, 6, 8, 8))
        fill = QPainterPath()
        fill.addPolygon(
            QPolygonF(
                QPointF(*p)
                for p in (
                    (2, 2),
                    (10, 2),
                    (10, 6 - FILL_GAP),
                    (6 - FILL_GAP, 6 - FILL_GAP),
                    (6 - FILL_GAP, 10),
                    (2, 10),
                )
            )
        )
        fill.closeSubpath()
    else:
        path.moveTo(5.5, 3.5)
        path.lineTo(2.5, 6.5)
        path.lineTo(5.5, 9.5)
        path.moveTo(2.5, 6.5)
        path.lineTo(9.5, 6.5)
        path.arcTo(QRectF(6, 6.5, 7, 7), 90, -180)
        path.lineTo(7, 13.5)
        if kind == "redo":
            path = QTransform(-1, 0, 0, 1, 16, 0).map(path)
    return path, fill


class _BarButton(QPushButton):
    """A button of the bar; off, it lets the mouse through to the bar, to
    drag it by."""

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.EnabledChange:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, not self.isEnabled())
        super().changeEvent(event)


class _Grip(QWidget):
    """Dots at the bar's end: it is dragged by."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(10, 18)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(BAR_GRIP_COLOR)
        for x in (3, 7):
            for y in (4, 9, 14):
                painter.drawEllipse(QPointF(x, y), 1.2, 1.2)


class _Bar(QFrame):
    """The editor's bar, moved out of the way by dragging it: where it is,
    what is under it cannot be taken."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setCursor(Qt.SizeAllCursor)

        self._grab: QPoint | None = None
        # where it was put by hand, from the editor's bottom middle
        self.offset: QPoint | None = None

    def enterEvent(self, event) -> None:
        # nothing under it is pointed at: the editor's own pointer, a hand
        # over a tile say, would show while a button of it is pressed
        self.parentWidget().leave_for_bar()
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:
        # not the switch's, which passes a press on on its own item
        is_switch = isinstance(self.childAt(event.pos()), SegmentedChoice)
        if event.button() == Qt.LeftButton and not is_switch:
            self._grab = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._grab is None:
            return
        editor = self.parentWidget()
        home = QPoint(editor.width() // 2, editor.height())
        self.offset = self.mapToParent(event.pos()) - self._grab - home
        editor.place_bar()

    def mouseReleaseEvent(self, event) -> None:
        self._grab = None


class LayoutEditor(QWidget):
    """A window of its own, as a tip is, over the grid: nothing painted in
    the player's own window shows over a hardware video, which is a native
    window. The videos are dimmed under it, or hidden where the window
    cannot be seen through.

    Its bar ends with Undo, Redo, Reopen Last Closed and Done; Esc and Enter
    are done too, Esc first putting back a drag (see is_dragging). A hint
    at the top says what to do, until the first drag.
    """

    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    reopen_requested = pyqtSignal()
    done = pyqtSignal()
    # the other kind of editor asked for by the switch on the bar: the
    # tiles' (True), or the cells'
    kind_requested = pyqtSignal(bool)
    # a key it has no use for, for the player's actions: Undo and Redo,
    # where the player's own shortcuts are not taken in its window
    key_pressed = pyqtSignal(object)

    # which it is, of the two: the editor of Free Tiles, or of a Fixed Grid
    is_tiles = False

    def __init__(self, can_undo, can_redo, can_reopen, parent=None):
        super().__init__(
            parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )

        self._can_undo = can_undo
        self._can_redo = can_redo
        self._can_reopen = can_reopen

        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._bar = _Bar(self)
        self._bar.setObjectName("layoutEditorBar")
        self._bar.setStyleSheet(BAR_STYLE)
        self._bar.setFixedHeight(BAR_HEIGHT)

        # the buttons for the player's actions, by what they do (their icons
        # too), and what they are called; a video closed from the editor is
        # not undone, but opened again
        self._actions = {
            "undo": translate("Edit Grid", "Undo"),
            "redo": translate("Edit Grid", "Redo"),
            "reopen": translate("Edit Grid", "Reopen Last Closed"),
        }
        self._action_buttons = {
            name: self._bar_button(
                functools.partial(self._request_action, name), tip, name
            )
            for name, tip in self._actions.items()
        }

        self._kind = self._make_kind_switch()

        self._help = self._bar_button(
            self._show_help, translate("Edit Grid", "Keys"), "help"
        )
        self._help.setCheckable(True)
        # the keys of the player's actions on the bar's buttons, by what
        # they do: "undo", "redo", "reopen"
        self._action_keys: dict[str, str] = {}

        self._popup: EditorPopup | None = None
        self._popup_refresh: Callable[[], None] | None = None
        # a word by the pointer, saying what is done there
        self._tag: GridLineTag | None = None

        self._hint = QLabel(self)
        self._hint.setStyleSheet(HINT_STYLE)
        self._hint.setAttribute(Qt.WA_TransparentForMouseEvents)

    # --- the bar ---

    def _bar_button(self, slot, tip=None, icon=None, text="") -> QPushButton:
        button = _BarButton(text, self._bar)
        button.setCursor(Qt.ArrowCursor)
        button.setFixedSize(BAR_BUTTON, BAR_BUTTON)
        button.setFocusPolicy(Qt.NoFocus)
        if icon is not None:
            button.setIcon(bar_icon(icon, self.devicePixelRatioF()))
        if tip is not None:
            button.setToolTip(tip)
        button.clicked.connect(slot)
        return button

    def _bar_label(self, icon, tip) -> QLabel:
        label = QLabel(self._bar)
        label.setPixmap(bar_icon(icon, self.devicePixelRatioF()).pixmap(QSize(16, 16)))
        label.setToolTip(tip)
        return label

    def _lay_out_bar(self, widgets) -> None:
        """The bar: its grip, the widgets, None for a line between groups of
        them, then Undo, Redo, Reopen and Done."""

        done = QPushButton(translate("Edit Grid", "Done"), self._bar)
        done.setObjectName("layoutEditorDone")
        done.setCursor(Qt.ArrowCursor)
        done.setFixedHeight(BAR_BUTTON)
        done.setFocusPolicy(Qt.NoFocus)
        done.clicked.connect(self.done)

        layout = QHBoxLayout(self._bar)
        layout.setContentsMargins(8, 3, 4, 3)
        layout.setSpacing(2)
        layout.addWidget(_Grip(self._bar))
        layout.addSpacing(2)
        for widget in (
            self._kind,
            None,
            *widgets,
            None,
            *self._action_buttons.values(),
        ):
            if widget is None:
                layout.addSpacing(4)
                line = QFrame(self._bar)
                line.setFixedSize(1, 18)
                line.setStyleSheet(f"background: {BAR_SEPARATOR_COLOR};")
                layout.addWidget(line)
                layout.addSpacing(4)
            else:
                layout.addWidget(widget)
        layout.addWidget(self._help)
        layout.addSpacing(4)
        layout.addWidget(done)

    def _make_kind_switch(self) -> SegmentedChoice:
        """Grid or Tiles: a Fixed Grid's cells edited, or Free Tiles' tiles,
        the layout made the other kind for the other."""

        switch = SegmentedChoice(self._bar)
        switch.addItem(translate("Edit Grid", "Grid"), False)
        switch.addItem(translate("Edit Grid", "Tiles"), True)
        switch.setCurrentIndex(switch.findData(self.is_tiles))
        switch.setCursor(Qt.ArrowCursor)
        # the editor's keys stay the editor's: Tab and the arrows
        switch.setFocusPolicy(Qt.NoFocus)
        switch.setToolTip(translate("Edit Grid", "Edit as a grid, or as tiles"))
        switch.setPalette(popup_palette(switch))
        switch.currentIndexChanged.connect(
            lambda _: self.kind_requested.emit(switch.currentData())
        )
        return switch

    def continue_from(self, other: "LayoutEditor") -> None:
        """Shown for the other kind of editor, switched from: its bar where
        the other's was dragged to (see _Bar), no hint."""

        self._bar.offset = other._bar.offset
        self.place_bar()
        self._hint_done()

    def set_action_keys(self, keys: dict[str, str]) -> None:
        """The keys of the player's actions the bar's buttons do too, as
        they are shown: "undo", "redo" and "reopen"."""

        self._action_keys = dict(keys)
        for name, tip in self._actions.items():
            key = self._action_keys.get(name)
            self._action_buttons[name].setToolTip(f"{tip} ({key})" if key else tip)

    def _update_bar(self) -> None:
        self.update_undo()
        self._bar.adjustSize()
        self.place_bar()
        self._place_hint()

    def update_undo(self) -> None:
        """Undo, Redo and Reopen on or off, as there is anything to undo,
        redo or open again."""

        buttons = self._action_buttons
        buttons["undo"].setEnabled(self._can_undo())
        buttons["redo"].setEnabled(self._can_redo())
        buttons["reopen"].setEnabled(self._can_reopen())

    def place_bar(self) -> None:
        # along the bottom, in the middle, or where it was dragged to
        size = self._bar.sizeHint()
        place = QRect(
            QPoint(
                (self.width() - size.width()) // 2, self.height() - size.height() - 10
            ),
            size,
        )
        if self._bar.offset is not None:
            home = QPoint(self.width() // 2, self.height())
            place.moveTopLeft(home + self._bar.offset)

        # kept inside
        place.moveLeft(min(max(place.left(), 0), self.width() - size.width()))
        place.moveTop(min(max(place.top(), 0), self.height() - size.height()))
        self._bar.setGeometry(place)

    def _set_hint(self, text: str) -> None:
        self._hint.setText(text)
        self._hint.adjustSize()

    def _place_hint(self) -> None:
        size = self._hint.sizeHint()
        self._hint.setGeometry(
            QRect(QPoint((self.width() - size.width()) // 2, 10), size)
        )
        if self._hint.isVisibleTo(self) and size.width() + 20 > self.width():
            self._hint.hide()

    def _hint_done(self) -> None:
        # once something is taken, it is known
        self._hint.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_bar()

    def _is_on_bar(self, point: QPoint) -> bool:
        return self._bar.isVisible() and self._bar.geometry().contains(point)

    def leave_for_bar(self) -> None:
        """The pointer gone onto the bar: off whatever it was on."""

        if not self.is_dragging():
            self.unsetCursor()
            self.leaveEvent(QEvent(QEvent.Leave))

    # --- the popups ---

    def _show_popup(
        self, button: QPushButton, title: str, parts, width=0, refresh=None
    ) -> None:
        """Parts, widgets or layouts, under a title in a popup above the
        bar's button, which stays pressed while it is up; refresh shows the
        settings in it as they are now (see update_settings)."""

        popup = EditorPopup(title, parts, width, self)
        popup.closed.connect(lambda: button.setChecked(False))
        popup.closed.connect(self._popup_closed)
        button.setChecked(True)
        self._popup = popup
        self._popup_refresh = refresh
        popup.show_above(button)

    def _popup_closed(self) -> None:
        self._popup = None
        self._popup_refresh = None

    def _show_help(self) -> None:
        """The keys and the mouse in the editor, and what they do."""

        rows = self._help_rows()
        keys = self._action_keys
        for name, does in self._actions.items():
            if keys.get(name):
                rows.append((keys[name], does))
        rows.append(
            (
                keys_text(Qt.Key_Enter, Qt.Key_Escape),
                translate("Edit Grid", "Done"),
            )
        )

        table = QGridLayout()
        table.setContentsMargins(0, 0, 0, 0)
        table.setHorizontalSpacing(16)
        table.setVerticalSpacing(4)
        for row, (key, does) in enumerate(rows):
            for column, (text, color) in enumerate(
                ((key, KEY_COLOR), (does, KEY_DOES_COLOR))
            ):
                label = QLabel(text)
                label.setProperty("color", color)
                table.addWidget(label, row, column)

        self._show_popup(self._help, translate("Edit Grid", "Keys"), [table])

    def _help_rows(self) -> list[tuple[str, str]]:
        """What the mouse and the editor's own keys do: (how, what)."""

        raise NotImplementedError

    # --- the word by the pointer ---

    def _pointer_tag(self) -> GridLineTag:
        if self._tag is None:
            self._tag = GridLineTag(self)
        return self._tag

    def _show_tag(self, text: str, point: QPoint) -> None:
        """A word by the pointer at point; none for no text."""

        if not text:
            self._hide_tag()
            return
        self._pointer_tag().show_text(
            text, True, self.mapToGlobal(point), self._on_screen()
        )

    def _hide_tag(self) -> None:
        if self._tag is not None and self._tag.isVisible():
            self._tag.hide()

    def _on_screen(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())

    # --- the keys ---

    def is_dragging(self) -> bool:
        raise NotImplementedError

    def cancel_drag(self) -> None:
        raise NotImplementedError

    def _is_own_key(self, event) -> bool:
        """Whether a key is the editor's, not the player's: Esc and Enter
        (Esc minimizes it)."""

        return event.key() in DONE_KEYS

    def event(self, event) -> bool:
        if event.type() == QEvent.ShortcutOverride and self._is_own_key(event):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self.is_dragging():
            self.cancel_drag()
        elif event.key() in DONE_KEYS:
            self.done.emit()
        else:
            self.pass_key(event)

    def pass_key(self, event) -> None:
        """A key for the player's actions, from the editor or a popup of
        its bar."""

        # Shift, say, held for the next arrow: no key of the player's yet
        if event.key() not in MODIFIER_KEYS:
            self._end_change()
        self.key_pressed.emit(event)

    def update_settings(self) -> None:
        """What the bar sets, as it is now: turned by its key, say."""

        if self._popup_refresh is not None:
            self._popup_refresh()

    def _request_action(self, name: str, *_) -> None:
        """Undo, Redo or Reopen, from the bar's buttons."""

        self._end_change()
        getattr(self, f"{name}_requested").emit()

    def _end_change(self) -> None:
        """A change made over time, keys pressed one after another, done:
        the player's actions do nothing to the grid while one is going on
        (see GridManager.begin_grid_change)."""

    def finish(self) -> None:
        """Whatever is being changed, done: the editor is going."""

        self._end_change()
        if self._popup is not None:
            self._popup.dismiss()

    # --- drawing ---

    def _paint_veil(self, painter) -> None:
        if self._is_translucent:
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), VEIL_COLOR)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        else:
            painter.fillRect(self.rect(), OPAQUE_COLOR)

    def _outline(self, painter, rect: QRect, pen: QPen, inset: float = INSET) -> None:
        inner = QRectF(rect).adjusted(inset, inset, -inset, -inset)
        painter.setBrush(Qt.NoBrush)

        # a dark edge either side of the line, to show over any picture:
        # whole, under a dashed one, whose dashes would not meet its own
        edge = QPen(pen)
        edge.setColor(EDGE_COLOR)
        edge.setStyle(Qt.SolidLine)
        edge.setWidthF(pen.widthF() + 2)
        painter.setPen(edge)
        painter.drawRoundedRect(inner, 4, 4)

        painter.setPen(pen)
        painter.drawRoundedRect(inner, 4, 4)

    def _name(
        self,
        painter,
        rect: QRect,
        name: str,
        *,
        color: QColor = LINE_COLOR,
        back: QColor = NAME_BACK_COLOR,
        has_close: bool = False,
    ) -> None:
        """A name in a box in the middle of the rect; with a button to close
        the video at its end."""

        found = self._name_box(rect, name, has_close=has_close)
        if found is not None:
            self._draw_name(painter, *found, color=color, back=back)

    def _draw_name(
        self,
        painter,
        name: str,
        box: QRectF,
        close: QRectF | None,
        *,
        color: QColor = LINE_COLOR,
        back: QColor = NAME_BACK_COLOR,
        icon: str | None = None,
    ) -> None:
        """A name in its box (see _name_box), an icon before it, if any."""

        painter.setPen(Qt.NoPen)
        painter.setBrush(back)
        painter.drawRoundedRect(box, 4, 4)

        text = box.adjusted(8, 0, -8, 0)
        if icon is not None:
            place = QRectF(0, 0, NAME_ICON, NAME_ICON)
            place.moveCenter(QPointF(text.left() + NAME_ICON / 2, text.center().y()))
            paint_icon(painter, icon, place, color)
            text.setLeft(place.right() + 4)
        if close is not None:
            text.setRight(text.right() - CLOSE_SIZE - 2)
        painter.setPen(color)
        painter.drawText(text, Qt.AlignCenter, name)

        if close is not None:
            self._close_button(painter, close)

    def _close_button(self, painter, close: QRectF) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(LINE_COLOR)
        painter.drawEllipse(close)

        cross = close.adjusted(5, 5, -5, -5)
        pen = QPen(EDGE_COLOR, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(cross.topLeft(), cross.bottomRight())
        painter.drawLine(cross.topRight(), cross.bottomLeft())

    def _name_box(
        self,
        rect: QRect | QRectF,
        name: str,
        *,
        has_close: bool = False,
        has_icon: bool = False,
    ) -> tuple[str, QRectF, QRectF | None] | None:
        """The name as it fits in the rect, where its box is, and where the
        button to close the video is in it; None where it does not fit. Room
        is left before it for an icon (has_icon)."""

        rect = QRectF(rect)
        lead = NAME_ICON + 4 if has_icon else 0
        metrics = self.fontMetrics()
        room = int(rect.width()) - 4 * INSET - 16 - lead
        if has_close:
            room -= CLOSE_SIZE + 4
        name = metrics.elidedText(name, Qt.ElideMiddle, room)
        if not name:
            return None

        box = QRectF(metrics.boundingRect(name)).adjusted(-8 - lead, -3, 8, 3)
        if has_close:
            box.setRight(box.right() + CLOSE_SIZE + 2)
            box.setTop(min(box.top(), box.center().y() - CLOSE_SIZE / 2 - 3))
            box.setBottom(max(box.bottom(), box.center().y() + CLOSE_SIZE / 2 + 3))
        box.moveCenter(rect.center())

        if not has_close:
            return name, box, None

        close = QRectF(0, 0, CLOSE_SIZE, CLOSE_SIZE)
        close.moveCenter(QPointF(box.right() - 3 - CLOSE_SIZE / 2, box.center().y()))
        return name, box, close

    def _handles(self, painter, rect: QRect, inset: float = INSET) -> None:
        inner = QRectF(rect).adjusted(inset, inset, -inset, -inset)
        center = inner.center()
        xs = (inner.left(), center.x(), inner.right())
        ys = (inner.top(), center.y(), inner.bottom())

        painter.setPen(QPen(EDGE_COLOR, 1))
        painter.setBrush(LINE_COLOR)
        for x in xs:
            for y in ys:
                if (x, y) == (center.x(), center.y()):
                    continue
                handle = QRectF(0, 0, HANDLE, HANDLE)
                handle.moveCenter(QPointF(x, y))
                painter.drawRect(handle)


class EditorPopup(QFrame):
    """A setting or two of the bar's, or the keys, in a small window above
    its button, gone with a click elsewhere: on its button too, which so
    closes it."""

    closed = pyqtSignal()

    def __init__(self, title: str, parts, width: int, parent):
        super().__init__(
            parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoMouseReplay)
        self.setAttribute(Qt.WA_DeleteOnClose)
        # its own, not the editor's under it, which it has while it is up
        self.setCursor(Qt.ArrowCursor)
        self._width = width
        # closed by a key, or by the editor going (see dismiss)
        self._is_dismissed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        label = QLabel(title, self)
        label.setProperty("color", POPUP_TITLE_COLOR)
        layout.addWidget(label)
        for part in parts:
            if isinstance(part, QLayout):
                layout.addLayout(part)
            else:
                layout.addWidget(part)

        # each its own: the application's style sheet keeps a parent's
        # palette from its children
        palette = popup_palette(self)
        for widget in (self, *self.findChildren(QWidget)):
            own = QPalette(palette)
            color = widget.property("color")
            if color is not None:
                own.setColor(QPalette.WindowText, color)
            widget.setPalette(own)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(POPUP_BORDER_COLOR)
        painter.setBrush(POPUP_BACK_COLOR)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = POPUP_RADIUS if self._is_translucent else 0
        painter.drawRoundedRect(box, radius, radius)

    def show_above(self, button: QPushButton) -> None:
        self.adjustSize()
        width = max(self.width(), self._width)
        if self.layout().hasHeightForWidth():
            self.resize(width, self.layout().heightForWidth(width))
        else:
            self.resize(width, self.height())

        size = self.size()
        top = button.mapToGlobal(QPoint(button.width() // 2, 0))
        place = QRect(
            QPoint(top.x() - size.width() // 2, top.y() - size.height() - 6), size
        )

        screen = QApplication.screenAt(top)
        if screen is not None:
            room = screen.availableGeometry()
            place.moveLeft(
                min(max(place.left(), room.left()), room.right() - size.width())
            )
            if place.top() < room.top():
                # below the button, with no room above it
                place.moveTop(top.y() + button.height() + 6)
        self.move(place.topLeft())
        self.show()

    def dismiss(self) -> None:
        """Closed, not by a click."""

        self._is_dismissed = True
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismiss()
        else:
            # the player's, as in the editor: the keys are the popup's
            # while it is up
            self.parentWidget().pass_key(event)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # closed by a click outside it: that click does nothing else
        if not self._is_dismissed:
            EatenClick()
        self.closed.emit()


def popup_palette(widget: QWidget) -> QPalette:
    """A widget's palette, dark whatever the theme, for the controls on the
    bar and in its popups."""

    palette = widget.palette()
    for role, color in POPUP_PALETTE.items():
        palette.setColor(role, QColor(color))
    return palette


def modifier_name(modifier) -> str:
    """A modifier key as the system names it: "Shift", or "⇧" on macOS."""

    text = QKeySequence(int(modifier) | Qt.Key_A).toString(QKeySequence.NativeText)
    return text[:-1].rstrip("+")


def keys_text(*keys) -> str:
    """Keys as the system names them, one or another."""

    return ", ".join(
        QKeySequence(key).toString(QKeySequence.NativeText) for key in keys
    )
