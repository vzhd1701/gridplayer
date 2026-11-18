from PyQt6 import sip
from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QCursor, QWindow
from PyQt6.QtWidgets import QApplication

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.keymap import KEY_MODIFIERS, modifiers_after

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
    puts it back (see _cancel). Alt or Shift pressed or let go of counts
    at once, not at the next move of the pointer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag = None

        # the buttons pressed on what is dragged: their releases are nothing
        # else's
        self._swallowed_buttons: set = set()
        self._is_cursor_set = False

        # the last Alt or Shift that counted (see key_release)
        self._key_seen: tuple | None = None

        self._check_timer = QTimer(self)
        self._check_timer.setInterval(CHECK_MS)
        self._check_timer.timeout.connect(self._check_pointer)

    @property
    def event_map(self):
        return {
            QEvent.Type.ApplicationDeactivate: self.app_deactivate,
            QEvent.Type.MouseMove: self.mouse_move,
            QEvent.Type.MouseButtonPress: self.mouse_press,
            QEvent.Type.MouseButtonRelease: self.mouse_release,
            QEvent.Type.MouseButtonDblClick: self.mouse_double_click,
            QEvent.Type.ShortcutOverride: self.shortcut_override,
            QEvent.Type.KeyPress: self.key_press,
            QEvent.Type.KeyRelease: self.key_release,
        }

    def eventFilter(self, event_object, event) -> bool:
        if event.type() == QEvent.Type.ApplicationDeactivate:
            # the application's, at no window
            return super().eventFilter(event_object, event)

        is_key = event.type() in {
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
        }

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
            if event.button() != Qt.MouseButton.LeftButton:
                self._swallowed_buttons.add(event.button())
                self._cancel()
            return True

        # a release seen nowhere, the drag ended away from the application
        self._swallowed_buttons.discard(event.button())
        return self._press(event)

    def mouse_release(self, event):
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._finish()

        if event.button() in self._swallowed_buttons:
            self._swallowed_buttons.discard(event.button())
            return True

        return None

    def shortcut_override(self, event):
        if self._drag is None or event.key() != Qt.Key.Key_Escape:
            return None

        # not what Esc is bound to: the key comes as a press, see key_press
        event.accept()
        return True

    def key_press(self, event):
        if self._drag is None:
            return None

        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return True

        return self.key_release(event)

    def key_release(self, event):
        # held where it is, it snaps or stops snapping there
        if self._drag is None or event.key() not in KEY_MODIFIERS:
            return None
        if event.isAutoRepeat():
            return None

        # not taken, the same key comes again at each widget up from the
        # one it is for: it counts once
        seen = (sip.unwrapinstance(event), event.type(), event.timestamp())
        if seen == self._key_seen:
            return None
        self._key_seen = seen

        self._move_to(QCursor.pos(), modifiers_after(event))
        return None

    # --- for each kind ---

    def _press(self, event):
        """A press with nothing dragged: what to start dragging, if any."""

        raise NotImplementedError

    def _leave(self):
        """The pointer gone from the player's windows, nothing dragged."""

        raise NotImplementedError

    def _hover_under_pointer(self):
        raise NotImplementedError

    def _move_to(self, global_pos, modifiers):
        """Dragged to there, these keys held."""

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
            if not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
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
