from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QCursor

from gridplayer.player.managers.layout_drag import LayoutDragManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.layout.lines import LINE_REACH, Line, LineDrag, MovableLines
from gridplayer.utils.qt import is_modal_open
from gridplayer.widgets.grid_line_mark import GridLineMark, GridLineTag


class GridLinesManager(LayoutDragManager):
    """Dragging the lines between the cells, to size them by hand.

    Within LINE_REACH of a line, the pointer turns to a resize one. Pressed
    there, the left button moves it, the line shown and the cells on either
    side resized as it goes. With "Snap Lines" on, it snaps where a video
    next to it just fits its cell, where the cells on either side are the
    same size, and with Link Rows off, in line with the row before or
    after (see GridLines.snaps), a word beside it saying which, unless Alt
    is held. Esc puts it back where it was. A double click evens out all
    the lines its way: the columns, the rows, or those of its row.

    The line is shown while it is held, and with "Show grid lines on
    hover" while the pointer is on it. It is a window of its own, always on
    top, so it goes as soon as the pointer is seen to have left the
    player's windows, for another application's window come over them, say,
    or the application is no longer the active one.
    """

    # Snap Lines turned on or off
    snapping_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # the line the pointer is on, and the one being moved
        self._hover: Line | None = None
        self._drag: LineDrag | None = None
        self._is_drag_single = False
        # where the cells were when it was pressed on
        self._area = QRect()

        self._mark: GridLineMark | None = None
        self._tag: GridLineTag | None = None

        # the pointer has left the window it was on, and come to none of the
        # player's since: going from one of its windows to the next, as from
        # a cell's overlay to the next cell's, it comes to the next at once
        self._is_pointer_out = False

    @property
    def commands(self):
        return {
            "is_show_grid_lines": self.is_show_on_hover,
            "toggle_show_grid_lines": self.toggle_show_on_hover,
            "is_grid_line_snap": self.is_snapping,
            "toggle_grid_line_snap": self.toggle_snapping,
        }

    @property
    def event_map(self):
        return {
            **super().event_map,
            QEvent.Enter: self.pointer_enter,
            QEvent.Leave: self.pointer_leave,
        }

    def is_show_on_hover(self) -> bool:
        return PlaylistSettings().get("playlist/show_grid_lines")

    def toggle_show_on_hover(self):
        PlaylistSettings().set("playlist/show_grid_lines", not self.is_show_on_hover())

        if self._drag is None:
            self._hide_mark()
            self._hover_under_pointer()

    def is_snapping(self) -> bool:
        return PlaylistSettings().get("playlist/grid_line_snap")

    def toggle_snapping(self):
        PlaylistSettings().set("playlist/grid_line_snap", not self.is_snapping())
        self.snapping_changed.emit()

    def pointer_enter(self):
        self._is_pointer_out = False

    def pointer_leave(self):
        # seen to by the check, unless it comes to another of the windows
        self._is_pointer_out = True

    def mouse_move(self, event):
        self._is_pointer_out = False

        if self._drag is None:
            if event.buttons() == Qt.NoButton:
                self._hover_under_pointer()
            return None

        if not event.buttons() & Qt.LeftButton:
            # let go of somewhere the release never came from
            self._finish()
            return None

        self._move_to(QCursor.pos(), event.modifiers())
        return True

    def mouse_double_click(self, event):
        if event.button() != Qt.LeftButton:
            return None

        # the second press of it took the line
        if self._drag is not None:
            line, lines = self._drag.line, self._drag.lines
            self._finish()
        else:
            found = self._line_under_pointer()
            if found is None:
                return None
            line, lines, _area = found

        self._ctx.commands.begin_grid_change()
        self._ctx.commands.set_grid_weights(lines.evened(line))
        self._ctx.commands.end_grid_change()

        self._swallowed_buttons.add(event.button())
        return True

    def _press(self, event):
        if event.button() != Qt.LeftButton:
            return None

        found = self._line_under_pointer()
        if found is None:
            return None

        line, lines, area = found
        self._start(line, lines, area)
        self._swallowed_buttons.add(event.button())
        return True

    def _leave(self):
        self._set_hover(None)

    def _line_under_pointer(self) -> tuple[Line, MovableLines, QRect] | None:
        """The line the pointer is on, if one can be moved now, with the
        lines and where the grid is on the screen."""

        if is_modal_open() or self._ctx.is_drag_ui or self._is_pointer_taken():
            return None

        lines = self._ctx.commands.movable_lines()
        if lines is None:
            return None

        area = self._ctx.commands.grid_area()
        pos = QCursor.pos()
        if not area.contains(pos):
            return None

        # the List window over it
        if self.is_elsewhere_at(pos):
            return None

        local = pos - area.topLeft()
        line = lines.line_at(local.x(), local.y(), LINE_REACH)
        if line is None:
            return None

        return line, lines, area

    def _hover_under_pointer(self):
        found = None if self._is_pointer_out else self._line_under_pointer()

        if found is None:
            self._set_hover(None)
            return

        line, lines, area = found
        self._set_hover(line)

        if self.is_show_on_hover():
            position = lines.position(line)
            self._show_mark(lines, area, line, position, is_snapped=False)

    def _set_hover(self, line: Line | None):
        self._hover = line

        if line is None:
            if self._drag is None:
                self._hide_mark()
                self._set_cursor(None)
                self._check_timer.stop()
            return

        self._set_cursor(_cursor_of(line))
        self._check_timer.start()

    def _start(self, line: Line, lines: MovableLines, area: QRect):
        self._drag = LineDrag(line, lines)
        self._area = area
        # the strip's edge, or the grid's lines
        self._is_drag_single = self._ctx.is_single_mode
        self._begin_drag()

        self._set_cursor(_cursor_of(line))
        self._show_mark(lines, area, line, lines.position(line), is_snapped=False)

    def _move_to(self, global_pos: QPoint, modifiers):
        if self._is_drag_gone():
            self._finish()
            return

        drag = self._drag
        line = drag.line

        local = global_pos - self._area.topLeft()
        position = local.x() if line.is_column else local.y()
        is_snapping = not modifiers & Qt.AltModifier and self.is_snapping()

        weights = drag.moved(position, is_snapping)
        self._ctx.commands.set_grid_weights(weights)

        position = drag.position(weights)
        is_snapped = drag.target is not None
        self._show_mark(drag.lines, self._area, line, position, is_snapped)

        if self._tag is None:
            self._tag = GridLineTag(self.parent())
        self._tag.show_snap(
            drag.target, line.is_column, position, global_pos, self._area
        )

    def _finish(self):
        self._end_drag()
        self._drag = None

        self._hide_mark()
        self._hide_tag()

        # still on it, or gone
        self._hover_under_pointer()

    def _cancel(self):
        if self._drag is not None and not self._is_drag_gone():
            self._ctx.commands.set_grid_weights(self._drag.before)

        self._finish()

    def _is_drag_gone(self) -> bool:
        # Single Mode come or gone while the line was held: its weights
        # are not for the lines there are now
        return self._is_drag_single != self._ctx.is_single_mode

    def _show_mark(self, lines, area, line, position, is_snapped):
        if self._mark is None:
            self._mark = GridLineMark(self.parent())

        start, end = lines.span(line)
        if line.is_column:
            origin, across = area.x(), area.y()
        else:
            origin, across = area.y(), area.x()

        self._mark.show_line(
            line.is_column,
            origin + position,
            across + start,
            across + end,
            is_snapped,
        )

    def _hide_tag(self):
        if self._tag is not None and self._tag.isVisible():
            self._tag.hide()

    def _hide_mark(self):
        if self._mark is not None and self._mark.isVisible():
            self._mark.hide()


def _cursor_of(line: Line) -> Qt.CursorShape:
    return Qt.SplitHCursor if line.is_column else Qt.SplitVCursor
