from bisect import bisect_right
from typing import NamedTuple

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QPainter, QPen
from PyQt5.QtWidgets import QLabel

from gridplayer.utils.layout.boxes import line_edges
from gridplayer.utils.layout.lines import LINE_REACH, GridLines, Line, LineDrag
from gridplayer.utils.qt import translate
from gridplayer.widgets.grid_line_mark import EDGE_COLOR, LINE_COLOR
from gridplayer.widgets.layout_editor import (
    CORNER_REACH,
    DIM_COLOR,
    DIM_TEXT_COLOR,
    EDGE_REACH,
    INSET,
    SWAP_COLOR,
    LayoutEditor,
    keys_text,
    modifier_name,
)

# a free cell, a lighter patch
EMPTY_COLOR = QColor(255, 255, 255, 18)

# the grip of the line between two cells, taken before their edges
GRIP_LENGTH = 26
GRIP_WIDTH = 6

# a minus sign, wider than a hyphen, to go with the plus
MINUS = "\u2212"


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


class GridEditor(LayoutEditor):
    """The cells of a Fixed Grid, to resize and move by hand: drawn over the
    grid, each an outline with its video's name.

    Dragged by an edge or a corner, a cell takes more cells or fewer, a
    whole cell at a time; dragged by the middle, it moves. While it is
    dragged the other cells are greyed, and the place it goes outlined in
    white with its name, dashed with "No room" where the videos in the way
    have nowhere to go. The gap between two cells is the line between them,
    dragged to move it as it is outside the editor. The video under the
    pointer has a button in its name to close it.

    Dragged onto another of its size, the two swap: that one lit, its name
    where it goes, a word by the pointer saying so.

    A bar has the rows and columns of the grid, to add and take away, Fit
    Lines to Videos, Reset Lines and Snap Lines, before Undo, Redo and Done
    (see LayoutEditor).
    """

    place_requested = pyqtSignal(str, int, int, int, int)
    size_requested = pyqtSignal(int, int)
    close_requested = pyqtSignal(str)
    # Snap Lines turned on or off, Fit Lines to Videos, Reset Lines, from
    # the bar
    snapping_toggled = pyqtSignal()
    fit_lines_requested = pyqtSignal()
    reset_lines_requested = pyqtSignal()
    # a line taken, moved to the weights, and let go of
    line_started = pyqtSignal()
    weights_changed = pyqtSignal(object)
    line_finished = pyqtSignal()

    def __init__(
        self,
        can_place,
        can_resize,
        lines,
        is_snapping,
        can_fit_lines,
        can_reset_lines,
        can_undo,
        can_redo,
        can_reopen,
        parent=None,
    ):
        super().__init__(can_undo, can_redo, can_reopen, parent)

        self._can_place = can_place
        self._can_resize = can_resize
        self._get_lines = lines
        self._is_snapping = is_snapping
        self._can_fit_lines = can_fit_lines
        self._can_reset_lines = can_reset_lines

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
        # the cell the one dragged would swap with, there
        self._swap_with: EditCell | None = None

        # the lines between the cells, as laid out now, once looked for
        self._lines: GridLines | None = None
        self._is_lines_found = False
        self._hover_line: Line | None = None
        # how far along the line the pointer is, for its grip
        self._line_across = 0
        self._line_drag: LineDrag | None = None

        # the video whose close button was pressed
        self._close_pressed: str | None = None

        self._make_bar()
        self._set_hint(translate("Edit Grid", "Drag edges to resize, videos to move."))

    # --- the bar ---

    def _make_bar(self) -> None:
        def stepper(text, rows, cols, tip):
            return self._bar_button(
                lambda: self.size_requested.emit(self._rows + rows, self._cols + cols),
                tip,
                text=text,
            )

        rows_tip = translate("Edit Grid", "Rows")
        cols_tip = translate("Edit Grid", "Columns")

        self._fewer_rows = stepper(MINUS, -1, 0, rows_tip)
        self._rows_label = QLabel(self._bar)
        self._more_rows = stepper("+", 1, 0, rows_tip)
        self._fewer_cols = stepper(MINUS, 0, -1, cols_tip)
        self._cols_label = QLabel(self._bar)
        self._more_cols = stepper("+", 0, 1, cols_tip)

        for count in (self._rows_label, self._cols_label):
            count.setAlignment(Qt.AlignCenter)
            count.setMinimumWidth(14)

        self._fit_lines = self._bar_button(
            self.fit_lines_requested,
            translate("Actions", "Fit Lines to Videos"),
            "fit_lines",
        )
        self._reset_lines = self._bar_button(
            self.reset_lines_requested,
            translate("Actions", "Reset Lines"),
            "reset_lines",
        )
        # pressed in while it is on
        self._snap = self._bar_button(
            self.snapping_toggled, translate("Snap Lines", "Snap Lines"), "snap"
        )
        self._snap.setCheckable(True)

        # None for a line between the groups
        self._lay_out_bar(
            (
                self._bar_label("rows", rows_tip),
                self._fewer_rows,
                self._rows_label,
                self._more_rows,
                None,
                self._bar_label("cols", cols_tip),
                self._fewer_cols,
                self._cols_label,
                self._more_cols,
                None,
                self._fit_lines,
                self._reset_lines,
                self._snap,
            )
        )

    def _help_rows(self) -> list[tuple[str, str]]:
        return [
            (
                translate("Edit Grid", "Drag a video"),
                translate("Edit Grid", "Move it, or swap"),
            ),
            (
                translate("Edit Grid", "Drag an edge"),
                translate("Edit Grid", "Resize it"),
            ),
            (
                translate("Edit Grid", "Drag a line"),
                translate("Edit Grid", "Move the line"),
            ),
            (
                translate("Edit Grid", "{} + drag a line").format(
                    modifier_name(Qt.AltModifier)
                ),
                translate("Edit Grid", "No snapping"),
            ),
            (
                translate("Edit Grid", "{} while dragging").format(
                    keys_text(Qt.Key_Escape)
                ),
                translate("Edit Grid", "Put it back"),
            ),
        ]

    def _update_bar(self) -> None:
        self._rows_label.setText(str(self._rows))
        self._cols_label.setText(str(self._cols))

        rows, cols = self._rows, self._cols
        self._fewer_rows.setEnabled(self._can_resize(rows - 1, cols))
        self._more_rows.setEnabled(self._can_resize(rows + 1, cols))
        self._fewer_cols.setEnabled(self._can_resize(rows, cols - 1))
        self._more_cols.setEnabled(self._can_resize(rows, cols + 1))
        self._fit_lines.setEnabled(self._can_fit_lines())
        self._reset_lines.setEnabled(self._can_reset_lines())
        self.update_settings()
        super()._update_bar()

    def update_settings(self) -> None:
        # the magnet pressed in while Snap Lines is on
        self._snap.setChecked(self._is_snapping())
        super().update_settings()

    def resizeEvent(self, event) -> None:
        self._forget_lines()
        super().resizeEvent(event)

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

    def finish(self) -> None:
        # a line let go of where it is, one change to undo; a cell's drag
        # put back
        if self._line_drag is not None:
            self._finish_line()
        elif self._drag is not None:
            self.cancel_drag()
        super().finish()

    def cancel_drag(self) -> None:
        if self._line_drag is not None:
            self.weights_changed.emit(self._line_drag.before)
            self._finish_line()
            return

        self._drag = None
        self._target = None
        self._swap_with = None
        self._hide_tag()
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

        # what it snapped to, said by the pointer
        self._pointer_tag().show_snap(
            drag.target,
            line.is_column,
            drag.position(weights),
            self.mapToGlobal(point),
            self._on_screen(),
        )
        self.update()

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

        if self._is_on_bar(point):
            # nothing under the bar
            point = QPoint(-1, -1)

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
            self._swap_with = self._swapped_by(target)
            self.update()
        is_swap = self._swap_with is not None
        self._show_tag(translate("Edit Grid", "Swap") if is_swap else "", event.pos())

    def _swapped_by(self, target) -> EditCell | None:
        """The cell the one dragged swaps with, moved there: one of its size
        just there."""

        dragged = self._drag.cell
        if self._drag.sides or not self._is_target_ok:
            return None
        return next(
            (
                cell
                for cell in self._cells
                if cell.place == target and cell.video_id != dragged.video_id
            ),
            None,
        )

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
        self._paint_veil(painter)

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
        swapped = self._swap_with
        for cell in self._cells:
            rect = self._cell_rect(cell)
            if swapped is not None and cell == swapped:
                # lit, its name where the one dragged is: the dragged one's
                # name is drawn in it, with the target
                painter.fillRect(rect, SWAP_COLOR)
                self._outline(painter, rect, QPen(LINE_COLOR, 3))
                continue
            if swapped is not None and cell == dragged:
                self._outline(painter, rect, QPen(LINE_COLOR, 3))
                self._name(painter, rect, swapped.name)
                continue
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
