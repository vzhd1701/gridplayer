from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QWindow
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers.base import ManagerBase

# how often to look whether the pointer is still where it was: it leaves
# for somewhere no move of it is ever seen, another application's window,
# or the button is let go of there
CHECK_MS = 150


class LayoutDragManager(ManagerBase):
    """Dragging part of the layout by hand with the left button: a line
    between cells (GridLinesManager), or a tile (FreeTilesManager).

    The cells and the videos' windows cover the whole grid, so what is
    dragged is looked for here, filtering the whole application. A press
    taken is taken at the window it comes to, before Qt hands it to a
    widget: a drag of the video would start from it (see
    DragNDropManager), and so would a click. The moves and the release of
    it are taken there too, the release of a press that no widget saw
    being nothing of any widget's; the keys at the widget they are for.

    While it is dragged, it is one change to undo, no video's overlay is
    shown, and the mouse is the player window's, whatever window under it
    the press went to (see _begin_drag). Another button pressed, or Esc,
    puts it back (see _cancel).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag = None

        # the buttons pressed on what is dragged: their releases are nothing
        # else's
        self._swallowed_buttons: set = set()
        self._is_cursor_set = False

        self._check_timer = QTimer(self)
        self._check_timer.setInterval(CHECK_MS)
        self._check_timer.timeout.connect(self._check_pointer)

    @property
    def event_map(self):
        return {
            QEvent.ApplicationDeactivate: self.app_deactivate,
            QEvent.MouseMove: self.mouse_move,
            QEvent.MouseButtonPress: self.mouse_press,
            QEvent.MouseButtonRelease: self.mouse_release,
            QEvent.MouseButtonDblClick: self.mouse_double_click,
            QEvent.ShortcutOverride: self.shortcut_override,
            QEvent.KeyPress: self.key_press,
        }

    def eventFilter(self, event_object, event) -> bool:
        if event.type() == QEvent.ApplicationDeactivate:
            # the application's, at no window
            return super().eventFilter(event_object, event)

        is_key = event.type() in {QEvent.ShortcutOverride, QEvent.KeyPress}

        # the mouse at the window it comes to, the keys at the widget
        if is_key == isinstance(event_object, QWindow):
            return False

        # the List window over a video, its own
        if self._drag is None and not is_key and self.is_elsewhere(event_object):
            self._leave()
            return False

        return super().eventFilter(event_object, event)

    def app_deactivate(self):
        if self._drag is not None:
            # left where it is, as if let go of: the lines and words shown
            # over every window would stay there until it came back
            self._finish()
        self._leave()

    def mouse_press(self, event):
        if self._drag is not None:
            # another button lets go of it, put back
            if event.button() != Qt.LeftButton:
                self._swallowed_buttons.add(event.button())
                self._cancel()
            return True

        # a release seen nowhere, the drag ended away from the application
        self._swallowed_buttons.discard(event.button())
        return self._press(event)

    def mouse_release(self, event):
        if self._drag is not None and event.button() == Qt.LeftButton:
            self._finish()

        if event.button() in self._swallowed_buttons:
            self._swallowed_buttons.discard(event.button())
            return True

        return None

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

    # --- for each kind ---

    def _press(self, event):
        """A press with nothing dragged: what to start dragging, if any."""

        raise NotImplementedError

    def _leave(self):
        """The pointer gone from the player's windows, nothing dragged."""

        raise NotImplementedError

    def _hover_under_pointer(self):
        raise NotImplementedError

    def _finish(self):
        """Leave it where it was moved to."""

        raise NotImplementedError

    def _cancel(self):
        """Put it back where it was."""

        raise NotImplementedError

    # --- inside ---

    def _is_pointer_taken(self) -> bool:
        """Whether the pointer is another's now: the picture being dragged
        about, or a selection to zoom to picked."""

        return QApplication.overrideCursor() is not None and not self._is_cursor_set

    def _begin_drag(self):
        commands = self._ctx.commands
        commands.begin_grid_change()
        # the press the drag's, not a video's
        commands.forget_drag_press()
        # nothing to draw anew under the pointer, nor to hover on the way
        commands.set_layout_drag(True)
        # every move the player's own, the overlay pressed on hidden and
        # other windows coming and going under the pointer
        self._grab_mouse(True)
        self._check_timer.start()

    def _end_drag(self):
        commands = self._ctx.commands
        commands.end_grid_change()
        self._grab_mouse(False)
        commands.set_layout_drag(False)
        # the overlay of the video under the pointer
        commands.update_active_under_mouse()

    def _grab_mouse(self, is_grabbed: bool):
        window = self.parent().windowHandle()
        if window is not None:
            window.setMouseGrabEnabled(is_grabbed)

    def _check_pointer(self):
        if self._drag is not None:
            if not QApplication.mouseButtons() & Qt.LeftButton:
                # let go of somewhere the release never came from
                self._finish()
            return

        self._hover_under_pointer()

    def _set_cursor(self, shape: Qt.CursorShape | None):
        if shape is None:
            if self._is_cursor_set:
                QApplication.restoreOverrideCursor()
                self._is_cursor_set = False
            return

        if self._is_cursor_set:
            QApplication.changeOverrideCursor(shape)
        else:
            QApplication.setOverrideCursor(shape)
            self._is_cursor_set = True
