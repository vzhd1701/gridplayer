from bisect import bisect_right
from typing import NamedTuple

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.layout.boxes import line_edges
from gridplayer.utils.layout.lines import LINE_REACH, GridLines, Line, LineDrag
from gridplayer.utils.qt import translate
from gridplayer.widgets.grid_line_mark import (
    EDGE_COLOR,
    LINE_COLOR,
    GridLineTag,
)

# the videos dimmed under the cells, or hidden where a window cannot be
# seen through
VEIL_COLOR = QColor(0, 0, 0, 150)
OPAQUE_COLOR = QColor("#202020")

NAME_BACK_COLOR = QColor(0, 0, 0, 170)
# a free cell, a lighter patch
EMPTY_COLOR = QColor(255, 255, 255, 18)
# the other cells, while one is dragged
DIM_COLOR = QColor("#5a5a5a")
DIM_TEXT_COLOR = QColor("#8a8a8a")

# the bar, dark whatever the theme, as the videos' own buttons are
BAR_STYLE = (
    "#gridEditorBar { background: rgba(30, 30, 30, 235);"
    " border: 1px solid #474747; border-radius: 18px; }"
    " QLabel { color: #e6e6e6; }"
    " QPushButton { color: #e6e6e6; background: transparent; border: none;"
    " border-radius: 14px; font-size: 15px; }"
    " QPushButton:hover { background: #3c3c3c; }"
    " QPushButton:disabled { color: #6a6a6a; }"
    " QPushButton#gridEditorDone { background: #e6e6e6; color: #111111;"
    " font-weight: bold; font-size: 12px; padding: 0 14px; }"
    " QPushButton#gridEditorDone:hover { background: #ffffff; }"
)
BAR_HEIGHT = 36
BAR_BUTTON = 28
BAR_ICON_COLOR = QColor("#e6e6e6")
BAR_ICON_OFF_COLOR = QColor("#6a6a6a")
BAR_SEPARATOR_COLOR = "#4a4a4a"
BAR_GRIP_COLOR = QColor("#8a8a8a")

HINT_STYLE = (
    "background: rgba(0, 0, 0, 160); color: #cfcfcf;"
    " border-radius: 12px; padding: 4px 12px;"
)

# between a cell's outline and its edge in the grid
INSET = 4

# how near an edge or a corner of a cell the pointer takes it, and how big
# its handles are drawn
EDGE_REACH = 8
CORNER_REACH = 14
HANDLE = 10

# the grip of the line between two cells, taken before their edges
GRIP_LENGTH = 26
GRIP_WIDTH = 6

# the button in a video's name that closes it
CLOSE_SIZE = 16

# a minus sign, wider than a hyphen, to go with the plus
MINUS = "\u2212"

DONE_KEYS = frozenset({Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter})


class EditCell(NamedTuple):
    video_id: str
    name: str
    row: int
    col: int
    rowspan: int
    colspan: int

    @property
    def place(self) -> tuple[int, int, int, int]:
        return self.row, self.col, self.rowspan, self.colspan


class _Drag(NamedTuple):
    cell: EditCell
    # the sides it moves ("left", "top", "right", "bottom"), none to move
    # the whole cell, and where it was taken, in cells from its corner
    sides: frozenset
    grab: tuple[int, int]


def _bar_icon(kind: str, ratio: float) -> QIcon:
    """The bar's small line icons, drawn on a 16 px square: the rows, the
    columns, undo, redo and reopen; dim where the button is off."""

    path = _bar_icon_path(kind)

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
        pen = QPen(color, 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

        icon.addPixmap(pixmap, mode)
    return icon


def _bar_icon_path(kind: str) -> QPainterPath:
    path = QPainterPath()
    if kind in {"rows", "cols"}:
        path.addRoundedRect(QRectF(2, 2.5, 12, 11), 1.5, 1.5)
        for at in (6.2, 9.8) if kind == "rows" else (6, 10):
            if kind == "rows":
                path.moveTo(2, at)
                path.lineTo(14, at)
            else:
                path.moveTo(at, 2.5)
                path.lineTo(at, 13.5)
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
    return path


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
    the edges of the cells under it cannot be taken."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setCursor(Qt.SizeAllCursor)

        self._grab: QPoint | None = None
        # where it was put by hand, from the editor's bottom middle
        self.offset: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
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


class GridEditor(QWidget):
    """The cells of a Fixed Grid, to resize and move by hand: drawn over the
    grid, each an outline with its video's name.

    Dragged by an edge or a corner, a cell takes more cells or fewer, a
    whole cell at a time; dragged by the middle, it moves. While it is
    dragged the other cells are greyed, and the place it goes outlined in
    white with its name, dashed with "No room" where the videos in the way
    have nowhere to go. The gap between two cells is the line between them,
    dragged to move it as it is outside the editor. The video under the
    pointer has a button in its name to close it.

    A bar has the rows and columns of the grid, to add and take away, Undo,
    Redo and Done. Esc and Enter are done too, Esc first putting back a
    drag. A hint at the top says what to do, until the first drag.

    A window of its own, as a tip is, over the grid: nothing painted in the
    player's own window shows over a hardware video, which is a native
    window.
    """

    place_requested = pyqtSignal(str, int, int, int, int)
    size_requested = pyqtSignal(int, int)
    close_requested = pyqtSignal(str)
    # a line taken, moved to the weights, and let go of
    line_started = pyqtSignal()
    weights_changed = pyqtSignal(object)
    line_finished = pyqtSignal()
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    reopen_requested = pyqtSignal()
    done = pyqtSignal()
    # a key it has no use for, for the player's actions: Undo and Redo,
    # where the player's own shortcuts are not taken in its window
    key_pressed = pyqtSignal(object)

    def __init__(
        self,
        can_place,
        can_resize,
        lines,
        is_snapping,
        can_undo,
        can_redo,
        can_reopen,
        parent=None,
    ):
        super().__init__(
            parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )

        self._can_place = can_place
        self._can_resize = can_resize
        self._get_lines = lines
        self._is_snapping = is_snapping
        self._can_undo = can_undo
        self._can_redo = can_redo
        self._can_reopen = can_reopen

        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._rows = 1
        self._cols = 1
        self._col_weights = ()
        self._row_weights = ()
        self._cells: list[EditCell] = []
        # where the lines between the cells are in the window, and for what
        self._edges_found: tuple = ((), ())
        self._edges_for: tuple | None = None

        self._hover: EditCell | None = None
        self._drag: _Drag | None = None
        self._target: tuple[int, int, int, int] | None = None
        self._is_target_ok = True

        # the lines between the cells, as laid out now, once looked for
        self._lines: GridLines | None = None
        self._is_lines_found = False
        self._hover_line: Line | None = None
        # how far along the line the pointer is, for its grip
        self._line_across = 0
        self._line_drag: LineDrag | None = None
        # what a line being moved snapped to, said by the pointer
        self._tag: GridLineTag | None = None

        # the video whose close button was pressed
        self._close_pressed: str | None = None

        self._bar = self._make_bar()
        self._hint = self._make_hint()

    # --- the bar ---

    def _make_bar(self) -> QFrame:
        bar = _Bar(self)
        bar.setObjectName("gridEditorBar")
        bar.setStyleSheet(BAR_STYLE)
        bar.setFixedHeight(BAR_HEIGHT)

        ratio = self.devicePixelRatioF()

        def button(text, slot, tip=None, icon=None):
            button = _BarButton(text, bar)
            button.setCursor(Qt.ArrowCursor)
            button.setFixedSize(BAR_BUTTON, BAR_BUTTON)
            button.setFocusPolicy(Qt.NoFocus)
            if icon is not None:
                button.setIcon(_bar_icon(icon, ratio))
            if tip is not None:
                button.setToolTip(tip)
            button.clicked.connect(slot)
            return button

        def stepper(text, rows, cols, tip):
            return button(
                text,
                lambda: self.size_requested.emit(self._rows + rows, self._cols + cols),
                tip,
            )

        def label(icon, tip):
            label = QLabel(bar)
            label.setPixmap(_bar_icon(icon, ratio).pixmap(QSize(16, 16)))
            label.setToolTip(tip)
            return label

        def separator():
            line = QFrame(bar)
            line.setFixedSize(1, 18)
            line.setStyleSheet(f"background: {BAR_SEPARATOR_COLOR};")
            return line

        rows_tip = translate("Edit Grid", "Rows")
        cols_tip = translate("Edit Grid", "Columns")

        self._fewer_rows = stepper(MINUS, -1, 0, rows_tip)
        self._rows_label = QLabel(bar)
        self._more_rows = stepper("+", 1, 0, rows_tip)
        self._fewer_cols = stepper(MINUS, 0, -1, cols_tip)
        self._cols_label = QLabel(bar)
        self._more_cols = stepper("+", 0, 1, cols_tip)

        self._undo = button(
            "", self.undo_requested, translate("Edit Grid", "Undo"), "undo"
        )
        self._redo = button(
            "", self.redo_requested, translate("Edit Grid", "Redo"), "redo"
        )
        # a video closed from the editor is not undone, but opened again
        self._reopen = button(
            "",
            self.reopen_requested,
            translate("Edit Grid", "Reopen Last Closed"),
            "reopen",
        )

        done = QPushButton(translate("Edit Grid", "Done"), bar)
        done.setObjectName("gridEditorDone")
        done.setCursor(Qt.ArrowCursor)
        done.setFixedHeight(BAR_BUTTON)
        done.setFocusPolicy(Qt.NoFocus)
        done.clicked.connect(self.done)

        for count in (self._rows_label, self._cols_label):
            count.setAlignment(Qt.AlignCenter)
            count.setMinimumWidth(14)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 3, 4, 3)
        layout.setSpacing(2)
        layout.addWidget(_Grip(bar))
        layout.addSpacing(2)
        # None for a line between the groups
        for widget in (
            label("rows", rows_tip),
            self._fewer_rows,
            self._rows_label,
            self._more_rows,
            None,
            label("cols", cols_tip),
            self._fewer_cols,
            self._cols_label,
            self._more_cols,
            None,
            self._undo,
            self._redo,
            self._reopen,
        ):
            if widget is None:
                layout.addSpacing(4)
                layout.addWidget(separator())
                layout.addSpacing(4)
            else:
                layout.addWidget(widget)
        layout.addSpacing(4)
        layout.addWidget(done)

        return bar

    def _make_hint(self) -> QLabel:
        hint = QLabel(
            translate("Edit Grid", "Drag edges to resize, videos to move."), self
        )
        hint.setStyleSheet(HINT_STYLE)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        hint.adjustSize()
        return hint

    def _update_bar(self) -> None:
        self._rows_label.setText(str(self._rows))
        self._cols_label.setText(str(self._cols))

        rows, cols = self._rows, self._cols
        self._fewer_rows.setEnabled(self._can_resize(rows - 1, cols))
        self._more_rows.setEnabled(self._can_resize(rows + 1, cols))
        self._fewer_cols.setEnabled(self._can_resize(rows, cols - 1))
        self._more_cols.setEnabled(self._can_resize(rows, cols + 1))
        self.update_undo()

        self._bar.adjustSize()
        self.place_bar()
        self._place_hint()

    def update_undo(self) -> None:
        """Undo, Redo and Reopen on or off, as there is anything to undo,
        redo or open again."""

        self._undo.setEnabled(self._can_undo())
        self._redo.setEnabled(self._can_redo())
        self._reopen.setEnabled(self._can_reopen())

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

    def _place_hint(self) -> None:
        size = self._hint.sizeHint()
        self._hint.setGeometry(
            QRect(QPoint((self.width() - size.width()) // 2, 10), size)
        )
        if self._hint.isVisibleTo(self) and size.width() + 20 > self.width():
            self._hint.hide()

    def _hint_done(self) -> None:
        # once a cell or a line is taken, it is known
        self._hint.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._forget_lines()
        self._update_bar()

    # --- the grid ---

    def set_grid(self, rows, cols, col_weights, row_weights, cells) -> None:
        """The grid as it is now: rows x cols, its lines as the weights
        have them (see Weights), and its videos' cells."""

        self._rows = rows
        self._cols = cols
        if self._line_drag is None:
            self._col_weights = tuple(col_weights)
            self._row_weights = tuple(row_weights)
        self._cells = list(cells)
        self._forget_lines()

        ids = {cell.video_id for cell in self._cells}
        if self._drag is not None and self._drag.cell.video_id not in ids:
            self.cancel_drag()

        self._hover_at(self.mapFromGlobal(QCursor.pos()))
        self._update_bar()
        self.update()

    def cells(self) -> list[EditCell]:
        return list(self._cells)

    def is_dragging(self) -> bool:
        return self._drag is not None or self._line_drag is not None

    def cancel_drag(self) -> None:
        if self._line_drag is not None:
            self.weights_changed.emit(self._line_drag.before)
            self._finish_line()
            return

        self._drag = None
        self._target = None
        self.unsetCursor()
        self.update()

    def _edges(self):
        found_for = (
            self.size(),
            self._cols,
            self._rows,
            self._col_weights,
            self._row_weights,
        )
        if found_for != self._edges_for:
            width, height = self.width(), self.height()
            self._edges_for = found_for
            self._edges_found = (
                [round(e * width) for e in line_edges(self._cols, self._col_weights)],
                [round(e * height) for e in line_edges(self._rows, self._row_weights)],
            )
        return self._edges_found

    def rect_of(self, row, col, rowspan, colspan) -> QRect:
        """Where cells are in the window: those from (row, col), rowspan x
        colspan of them."""

        cols, rows = self._edges()
        return QRect(
            QPoint(cols[col], rows[row]),
            QPoint(cols[col + colspan] - 1, rows[row + rowspan] - 1),
        )

    def _cell_rect(self, cell: EditCell) -> QRect:
        return self.rect_of(*cell.place)

    def _position_at(self, point: QPoint) -> tuple[int, int]:
        # the grid's cell the point is in, the nearest where it is outside
        cols, rows = self._edges()
        col = min(max(bisect_right(cols, point.x()) - 1, 0), self._cols - 1)
        row = min(max(bisect_right(rows, point.y()) - 1, 0), self._rows - 1)
        return row, col

    def _nearest_line(self, edges, position) -> int:
        return min(range(len(edges)), key=lambda index: abs(edges[index] - position))

    def _cell_at(self, point: QPoint) -> EditCell | None:
        return next(
            (cell for cell in self._cells if self._cell_rect(cell).contains(point)),
            None,
        )

    def _sides_at(self, cell: EditCell, point: QPoint) -> frozenset:
        """The sides of the cell the point takes: one near its edge, two
        near its corner, none in its middle, to move it."""

        rect = self._cell_rect(cell).adjusted(INSET, INSET, -INSET, -INSET)

        def near(reach):
            sides = set()
            if abs(point.x() - rect.left()) <= reach:
                sides.add("left")
            elif abs(point.x() - rect.right()) <= reach:
                sides.add("right")
            if abs(point.y() - rect.top()) <= reach:
                sides.add("top")
            elif abs(point.y() - rect.bottom()) <= reach:
                sides.add("bottom")
            return sides

        corner = near(CORNER_REACH)
        if len(corner) == 2:
            return frozenset(corner)
        return frozenset(near(EDGE_REACH))

    def _target_for(self, point: QPoint) -> tuple[int, int, int, int]:
        """Where the cell being dragged goes, for the pointer there: a whole
        cell at a time."""

        cell, sides = self._drag.cell, self._drag.sides

        if not sides:
            row, col = self._position_at(point)
            row = min(max(row - self._drag.grab[0], 0), self._rows - cell.rowspan)
            col = min(max(col - self._drag.grab[1], 0), self._cols - cell.colspan)
            return row, col, cell.rowspan, cell.colspan

        cols, rows = self._edges()
        top, left = cell.row, cell.col
        bottom, right = top + cell.rowspan, left + cell.colspan

        if "left" in sides:
            left = min(self._nearest_line(cols, point.x()), right - 1)
        if "right" in sides:
            right = max(self._nearest_line(cols, point.x()), left + 1)
        if "top" in sides:
            top = min(self._nearest_line(rows, point.y()), bottom - 1)
        if "bottom" in sides:
            bottom = max(self._nearest_line(rows, point.y()), top + 1)

        return top, left, bottom - top, right - left

    # --- the lines between the cells ---

    def _forget_lines(self) -> None:
        self._lines = None
        self._is_lines_found = False

    def _grid_lines(self) -> GridLines | None:
        if not self._is_lines_found:
            self._lines = self._get_lines()
            self._is_lines_found = True
        return self._lines

    def _line_at(self, point: QPoint) -> Line | None:
        lines = self._grid_lines()
        if lines is None:
            return None
        return lines.line_at(point.x(), point.y(), LINE_REACH)

    def _start_line(self, line: Line) -> None:
        self._line_drag = LineDrag(line, self._grid_lines())
        self._hint_done()
        self.line_started.emit()

    def _move_line(self, point: QPoint, modifiers) -> None:
        drag = self._line_drag
        line = drag.line

        position = point.x() if line.is_column else point.y()
        is_snapping = not modifiers & Qt.AltModifier and self._is_snapping()

        weights = drag.moved(position, is_snapping)
        self._col_weights = tuple(weights.cols)
        self._row_weights = tuple(weights.rows)
        self.weights_changed.emit(weights)
        self._line_across = point.y() if line.is_column else point.x()

        if self._tag is None:
            self._tag = GridLineTag(self)
        self._tag.show_snap(
            drag.target,
            line.is_column,
            drag.position(weights),
            self.mapToGlobal(point),
            QRect(self.mapToGlobal(QPoint(0, 0)), self.size()),
        )
        self.update()

    def _hide_tag(self) -> None:
        if self._tag is not None and self._tag.isVisible():
            self._tag.hide()

    def _finish_line(self) -> None:
        self._line_drag = None
        self._hide_tag()
        self._forget_lines()
        self.line_finished.emit()
        self._hover_at(self.mapFromGlobal(QCursor.pos()))
        self.update()

    # --- the mouse and the keys ---

    def _hover_at(self, point: QPoint) -> None:
        """What the pointer is on, with no button held: the close button
        of a video's name, a line, or a cell's edge or middle."""

        shown = self._hover, self._hover_line, self._line_across

        closing = self._close_at(point)
        line = None
        if closing is None and self.rect().contains(point):
            line = self._line_at(point)
        if closing is not None:
            self._hover = closing
            self._hover_line = None
            self.setCursor(Qt.PointingHandCursor)
        elif line is not None:
            self._hover_line = line
            self._line_across = point.y() if line.is_column else point.x()
            self._hover = None
            self.setCursor(Qt.SplitHCursor if line.is_column else Qt.SplitVCursor)
        else:
            self._hover_line = None
            self._hover = self._cell_at(point)
            sides = None
            if self._hover is not None:
                sides = self._sides_at(self._hover, point)
            self._set_cursor(sides)

        if (self._hover, self._hover_line, self._line_across) != shown:
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        pos = event.pos()

        closing = self._close_at(pos)
        if closing is not None:
            self._close_pressed = closing.video_id
            return

        line = self._line_at(pos)
        if line is not None:
            self._start_line(line)
            return

        cell = self._cell_at(pos)
        if cell is None:
            return

        row, col = self._position_at(pos)
        self._drag = _Drag(
            cell, self._sides_at(cell, pos), (row - cell.row, col - cell.col)
        )
        self._target = cell.place
        self._is_target_ok = True
        self._hint_done()
        self._set_cursor(self._drag.sides, is_dragging=True)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._line_drag is not None:
            self._move_line(event.pos(), event.modifiers())
            return

        if self._drag is None:
            if self._close_pressed is None:
                self._hover_at(event.pos())
            return

        target = self._target_for(event.pos())
        if target != self._target:
            self._target = target
            cell = self._drag.cell
            self._is_target_ok = target == cell.place or self._can_place(
                cell.video_id, *target
            )
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        if self._close_pressed is not None:
            video_id, self._close_pressed = self._close_pressed, None
            closing = self._close_at(event.pos())
            if closing is not None and closing.video_id == video_id:
                self.close_requested.emit(video_id)
            return

        if self._line_drag is not None:
            self._finish_line()
            return

        if self._drag is None:
            return

        cell, target, is_ok = self._drag.cell, self._target, self._is_target_ok
        self.cancel_drag()
        self._hover_at(event.pos())

        if is_ok and target != cell.place:
            self.place_requested.emit(cell.video_id, *target)

    def leaveEvent(self, event) -> None:
        if not self.is_dragging():
            self._hover = None
            self._hover_line = None
            self.update()

    def event(self, event) -> bool:
        # Esc and Enter its own, not the player's (Esc minimizes it)
        if event.type() == QEvent.ShortcutOverride and event.key() in DONE_KEYS:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self.is_dragging():
            self.cancel_drag()
        elif event.key() in DONE_KEYS:
            self.done.emit()
        else:
            self.key_pressed.emit(event)

    def _set_cursor(self, sides, is_dragging=False) -> None:
        if sides is None:
            self.unsetCursor()
        elif not sides:
            self.setCursor(Qt.ClosedHandCursor if is_dragging else Qt.OpenHandCursor)
        elif sides in ({"left", "top"}, {"right", "bottom"}):
            self.setCursor(Qt.SizeFDiagCursor)
        elif sides in ({"right", "top"}, {"left", "bottom"}):
            self.setCursor(Qt.SizeBDiagCursor)
        elif sides & {"left", "right"}:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.SizeVerCursor)

    # --- drawing ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_translucent:
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), VEIL_COLOR)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        else:
            painter.fillRect(self.rect(), OPAQUE_COLOR)

        covered = set()
        for cell in self._cells:
            covered.update(
                (row, col)
                for row in range(cell.row, cell.row + cell.rowspan)
                for col in range(cell.col, cell.col + cell.colspan)
            )

        painter.setPen(Qt.NoPen)
        painter.setBrush(EMPTY_COLOR)
        for row in range(self._rows):
            for col in range(self._cols):
                if (row, col) not in covered:
                    inner = QRectF(self.rect_of(row, col, 1, 1))
                    inner.adjust(INSET, INSET, -INSET, -INSET)
                    painter.drawRoundedRect(inner, 4, 4)

        # the one dragged, and the others greyed, while one is
        dragged = self._drag.cell if self._drag else None
        for cell in self._cells:
            rect = self._cell_rect(cell)
            if dragged is not None:
                self._outline(painter, rect, QPen(DIM_COLOR, 1))
                if cell != dragged:
                    self._name(painter, rect, cell.name, color=DIM_TEXT_COLOR)
                continue

            self._outline(painter, rect, QPen(LINE_COLOR, 2))
            has_close = cell == self._hover and self._line_drag is None
            self._name(painter, rect, cell.name, has_close=has_close)

        if self._drag is not None:
            self._draw_target(painter)
        elif self._line_drag is not None:
            self._draw_line(painter, self._line_drag.line, self._line_drag.lines)
        elif self._hover_line is not None:
            self._draw_line(painter, self._hover_line, self._grid_lines())
        elif self._hover is not None:
            self._handles(painter, self._cell_rect(self._hover))

    def _outline(self, painter, rect: QRect, pen: QPen) -> None:
        inner = QRectF(rect).adjusted(INSET, INSET, -INSET, -INSET)
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
        if found is None:
            return
        name, box, close = found

        painter.setPen(Qt.NoPen)
        painter.setBrush(back)
        painter.drawRoundedRect(box, 4, 4)

        text = QRectF(box)
        if close is not None:
            text.setRight(close.left())
        painter.setPen(color)
        painter.drawText(text, Qt.AlignCenter, name)

        if close is None:
            return

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
        self, rect: QRect, name: str, *, has_close: bool = False
    ) -> tuple[str, QRectF, QRectF | None] | None:
        """The name as it fits in the rect, where its box is, and where the
        button to close the video is in it; None where it does not fit."""

        metrics = self.fontMetrics()
        room = rect.width() - 4 * INSET - 16
        if has_close:
            room -= CLOSE_SIZE + 4
        name = metrics.elidedText(name, Qt.ElideMiddle, room)
        if not name:
            return None

        box = QRectF(metrics.boundingRect(name)).adjusted(-8, -3, 8, 3)
        if has_close:
            box.setRight(box.right() + CLOSE_SIZE + 2)
            box.setTop(min(box.top(), box.center().y() - CLOSE_SIZE / 2 - 3))
            box.setBottom(max(box.bottom(), box.center().y() + CLOSE_SIZE / 2 + 3))
        box.moveCenter(QRectF(rect).center())

        if not has_close:
            return name, box, None

        close = QRectF(0, 0, CLOSE_SIZE, CLOSE_SIZE)
        close.moveCenter(QPointF(box.right() - 3 - CLOSE_SIZE / 2, box.center().y()))
        return name, box, close

    def close_rect_of(self, cell: EditCell) -> QRectF | None:
        """Where the button to close the video is, in its name."""

        found = self._name_box(self._cell_rect(cell), cell.name, has_close=True)
        return None if found is None else found[2]

    def _close_at(self, point: QPoint) -> EditCell | None:
        """The video whose close button the point is on."""

        cell = self._cell_at(point)
        if cell is None:
            return None
        close = self.close_rect_of(cell)
        if close is None or not close.contains(QPointF(point)):
            return None
        return cell

    def _handles(self, painter, rect: QRect) -> None:
        inner = rect.adjusted(INSET, INSET, -INSET, -INSET)
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
                handle.moveCenter(QPoint(x, y))
                painter.drawRect(handle)

    def _draw_target(self, painter) -> None:
        rect = self.rect_of(*self._target)
        style = Qt.SolidLine if self._is_target_ok else Qt.DashLine
        self._outline(painter, rect, QPen(LINE_COLOR, 3, style))

        name = self._drag.cell.name
        if not self._is_target_ok:
            name = translate("Edit Grid", "No room")
        self._name(painter, rect, name, color=EDGE_COLOR, back=LINE_COLOR)

    def _draw_line(self, painter, line: Line, lines: GridLines | None) -> None:
        """The line between the cells, lit, with a grip where the pointer is
        along it."""

        if lines is None:
            return

        cols, rows = self._edges()
        edges = cols if line.is_column else rows
        at = edges[line.index + 1]
        start, end = lines.span(line)

        if line.is_column:
            ends = (QPointF(at, start), QPointF(at, end))
        else:
            ends = (QPointF(start, at), QPointF(end, at))

        for color, width in ((EDGE_COLOR, 4), (LINE_COLOR, 2)):
            painter.setPen(QPen(color, width))
            painter.drawLine(*ends)

        across = min(
            max(self._line_across, start + GRIP_LENGTH / 2), end - GRIP_LENGTH / 2
        )
        grip = (
            QRectF(0, 0, GRIP_WIDTH, GRIP_LENGTH)
            if line.is_column
            else QRectF(0, 0, GRIP_LENGTH, GRIP_WIDTH)
        )
        grip.moveCenter(QPointF(at, across) if line.is_column else QPointF(across, at))
        painter.setPen(QPen(EDGE_COLOR, 1))
        painter.setBrush(LINE_COLOR)
        painter.drawRoundedRect(grip, GRIP_WIDTH / 2, GRIP_WIDTH / 2)
