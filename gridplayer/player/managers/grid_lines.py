from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import QCursor, QWindow
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.layout import Weights
from gridplayer.utils.layout.lines import GridLines, Line, Snap, SnapKind
from gridplayer.utils.qt import is_modal_open, translate
from gridplayer.widgets.grid_line_mark import GridLineMark, GridLineTag

# how near the pointer has to be to a line to take it, in pixels
LINE_REACH = 4

# how often to look whether the pointer is still on the line it was: it
# leaves for somewhere no move of it is ever seen, another application's
# window, or the button is let go of there
LINE_CHECK_MS = 150


class GridLinesManager(ManagerBase):
    """Dragging the lines between the cells, to size them by hand.

    Within LINE_REACH of a line, the pointer turns to a resize one. Pressed
    there, the left button moves it, the line shown and the cells on either
    side resized as it goes. With "Snap Lines" on, it snaps where a video
    next to it just fits its cell, where the cells on either side are the
    same size, and with Link Rows off, in line with the row before or
    after (see GridLines.snaps), a word beside it saying which, unless Alt
    is held. Esc puts it back where it was. A double click evens out all
    the lines its way: the columns, the rows, or those of its row.

    The cells and the videos' windows cover the whole grid, so the lines
    are looked for here, filtering the whole application, as PanManager
    does for a drag of the picture. A press on a line is taken at the
    window it comes to, before Qt hands it to a widget: a drag of the video
    would start from it (see DragNDropManager), and so would a click. The
    moves and the release of it are taken there too, the release of a
    press that no widget saw being nothing of any widget's.

    The line is shown while it is held, and with "Show grid lines on
    hover" while the pointer is on it. It is a window of its own, always on
    top, so it goes as soon as the pointer is seen to have left the
    player's windows, for another application's window come over them, say,
    or the application is no longer the active one.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # the line the pointer is on, and the one being moved
        self._hover: Line | None = None
        self._drag: Line | None = None

        # as the lines were when the one being moved was pressed on, where
        # the cells were then, and where the line snaps to
        self._lines: GridLines | None = None
        self._area = QRect()
        self._before: Weights | None = None
        self._targets: list[float] = []
        self._snap = Snap()

        # the buttons pressed on a line: their releases are nothing else's
        self._swallowed_buttons: set = set()

        self._is_cursor_set = False
        self._mark: GridLineMark | None = None
        self._tag: GridLineTag | None = None

        # the pointer has left the window it was on, and come to none of the
        # player's since: going from one of its windows to the next, as from
        # a cell's overlay to the next cell's, it comes to the next at once
        self._is_pointer_out = False

        self._check_timer = QTimer(self)
        self._check_timer.setInterval(LINE_CHECK_MS)
        self._check_timer.timeout.connect(self._check_pointer)

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
            QEvent.Enter: self.pointer_enter,
            QEvent.Leave: self.pointer_leave,
            QEvent.ApplicationDeactivate: self.application_deactivate,
            QEvent.MouseMove: self.mouse_move,
            QEvent.MouseButtonPress: self.mouse_press,
            QEvent.MouseButtonRelease: self.mouse_release,
            QEvent.MouseButtonDblClick: self.mouse_double_click,
            QEvent.ShortcutOverride: self.shortcut_override,
            QEvent.KeyPress: self.key_press,
        }

    def eventFilter(self, event_object, event) -> bool:
        if event.type() == QEvent.ApplicationDeactivate:
            return self.application_deactivate()

        is_key = event.type() in {QEvent.ShortcutOverride, QEvent.KeyPress}

        # the mouse at the window it comes to, the keys at the widget
        if is_key == isinstance(event_object, QWindow):
            return False

        # the List window over a video, its own
        if self._drag is None and not is_key and self.is_elsewhere(event_object):
            self._set_hover(None)
            return False

        return super().eventFilter(event_object, event)

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

    def pointer_enter(self):
        self._is_pointer_out = False

    def pointer_leave(self):
        # seen to by the check, unless it comes to another of the windows
        self._is_pointer_out = True

    def application_deactivate(self):
        if self._drag is None:
            self._set_hover(None)
        return False

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

    def mouse_press(self, event):
        if self._drag is not None:
            # another button lets go of it, put back
            if event.button() != Qt.LeftButton:
                self._swallowed_buttons.add(event.button())
                self._cancel()
            return True

        if event.button() != Qt.LeftButton:
            return None

        found = self._line_under_pointer()
        if found is None:
            return None

        line, lines, area = found
        self._start(line, lines, area)
        self._swallowed_buttons.add(event.button())
        return True

    def mouse_release(self, event):
        if self._drag is not None and event.button() == Qt.LeftButton:
            self._finish()

        if event.button() in self._swallowed_buttons:
            self._swallowed_buttons.discard(event.button())
            return True

        return None

    def mouse_double_click(self, event):
        if event.button() != Qt.LeftButton:
            return None

        # the second press of it took the line
        line, lines = self._drag, self._lines
        if line is not None:
            self._finish()
        else:
            found = self._line_under_pointer()
            if found is None:
                return None
            line, lines, _area = found

        self._ctx.commands.set_grid_weights(lines.evened(line))

        self._swallowed_buttons.add(event.button())
        return True

    def shortcut_override(self, event):
        if self._drag is None or event.key() != Qt.Key_Escape:
            return None

        # not what Esc is bound to: the key comes as a press, see key_press
        event.accept()
        return True

    def key_press(self, event):
        if self._drag is None or event.key() != Qt.Key_Escape:
            return None

        self._cancel()
        return True

    def _line_under_pointer(self) -> tuple[Line, GridLines, QRect] | None:
        """The line the pointer is on, if one can be moved now, with the
        lines and where the grid is on the screen."""

        if is_modal_open() or self._ctx.is_drag_ui:
            return None

        # the picture being dragged about, or a selection to zoom to picked
        cursor = QApplication.overrideCursor()
        if cursor is not None and not self._is_cursor_set:
            return None

        lines = self._ctx.commands.grid_lines()
        if lines is None:
            return None

        area = self._ctx.commands.grid_area()
        pos = QCursor.pos()
        if not area.contains(pos):
            return None

        # the List window over it; not the line shown there, which is no
        # window of another
        window = QApplication.topLevelAt(pos)
        if (
            window is not None
            and window is not self._mark
            and self.is_elsewhere(window)
        ):
            return None

        local = pos - area.topLeft()
        line = lines.line_at(local.x(), local.y(), LINE_REACH)
        if line is None:
            return None

        return line, lines, area

    def _hover_under_pointer(self):
        found = self._line_under_pointer()

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

        self._set_cursor(line)
        self._check_timer.start()

    def _start(self, line: Line, lines: GridLines, area: QRect):
        self._drag = line
        self._lines = lines
        self._area = area
        self._before = lines.weights()
        self._targets = lines.snaps(line)
        self._snap.let_go()

        self._set_cursor(line)
        self._show_mark(lines, area, line, lines.position(line), is_snapped=False)
        self._check_timer.start()

    def _move_to(self, global_pos: QPoint, modifiers):
        line, lines = self._drag, self._lines

        local = global_pos - self._area.topLeft()
        position = local.x() if line.is_column else local.y()

        if modifiers & Qt.AltModifier or not self.is_snapping():
            self._snap.let_go()
        else:
            position = self._snap(position, self._targets)

        weights = lines.moved(line, position)
        self._ctx.commands.set_grid_weights(weights)

        self._show_mark(
            lines,
            self._area,
            line,
            lines.position(line, weights),
            is_snapped=self._snap.target is not None,
        )
        self._show_tag(line, lines.position(line, weights), global_pos)

    def _finish(self):
        """Leave the line where it was moved to."""

        self._drag = None
        self._lines = None
        self._before = None
        self._targets = []

        self._hide_mark()
        self._hide_tag()

        # still on it, or gone
        self._hover_under_pointer()

    def _cancel(self):
        """Put the line back where it was."""

        if self._before is not None:
            self._ctx.commands.set_grid_weights(self._before)

        self._finish()

    def _check_pointer(self):
        if self._drag is not None:
            if not QApplication.mouseButtons() & Qt.LeftButton:
                self._finish()
            return

        if self._is_pointer_out:
            self._set_hover(None)
            return

        self._hover_under_pointer()

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

    def _show_tag(self, line: Line, position: int, pointer: QPoint):
        """Say what the line snapped to, beside it by the pointer."""

        target = self._snap.target
        if target is None:
            self._hide_tag()
            return

        if target.kind is SnapKind.FITS:
            text = translate("Grid Lines", "Fits")
        elif target.kind is SnapKind.ALIGNED:
            text = translate("Grid Lines", "Aligned")
        else:
            text = translate("Grid Lines", "Even")

        if self._tag is None:
            self._tag = GridLineTag(self.parent())

        area = self._area
        if line.is_column:
            at = QPoint(area.x() + position, pointer.y())
        else:
            at = QPoint(pointer.x(), area.y() + position)

        self._tag.show_text(text, line.is_column, at, area)

    def _hide_tag(self):
        if self._tag is not None and self._tag.isVisible():
            self._tag.hide()

    def _hide_mark(self):
        if self._mark is not None and self._mark.isVisible():
            self._mark.hide()

    def _set_cursor(self, line: Line | None):
        if line is None:
            if self._is_cursor_set:
                QApplication.restoreOverrideCursor()
                self._is_cursor_set = False
            return

        shape = Qt.SplitHCursor if line.is_column else Qt.SplitVCursor

        if self._is_cursor_set:
            QApplication.changeOverrideCursor(shape)
        else:
            QApplication.setOverrideCursor(shape)
            self._is_cursor_set = True
