import contextlib

from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QCursor, QWindow
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import ZoomSelectTrigger
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import is_modal_open
from gridplayer.widgets.video_overlay import OverlayBlock

_TRIGGER_MODIFIERS = {
    ZoomSelectTrigger.CTRL: Qt.ControlModifier,
    ZoomSelectTrigger.SHIFT: Qt.ShiftModifier,
    ZoomSelectTrigger.ALT: Qt.AltModifier,
}


class ZoomSelectManager(ManagerBase):
    """Zooming in on a part of a video's picture, selected with the mouse.

    A drag over the picture with the left button and a key held, or with
    the middle one (see the zoom_select_trigger setting, off by default);
    or the next left drag after Zoom to Selection is picked, whatever is
    held. Let go of, the part dragged over is fitted into the cell, in its
    middle (see VideoBlock.zoom_to_selection).

    The press is taken here, and the moves after it, before a drag would
    move the video to another cell or the picture about. A click with no
    drag is still a click, for the keymap to have, unless Zoom to Selection
    was picked for it. Esc and the right button let go of a selection, and
    of one picked for.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._block = None
        self._button = Qt.LeftButton
        self._press_pos: QPoint | None = None
        self._is_selecting = False

        # picked from the menu: the next left drag over a video selects
        self._is_armed = False
        self._is_cursor_set = False
        # the video saying how to, the one the pointer was last over
        self._hinted = None

        # the releases, and the menu, of buttons a selection was let go of
        # with or while they were held, which are nothing else's either
        self._swallowed_buttons: set = set()
        self._is_context_menu_swallowed = False

    @property
    def commands(self):
        return {"arm_zoom_selection": self.arm}

    @property
    def event_map(self):
        return {
            QEvent.MouseButtonPress: self.mouse_press,
            QEvent.MouseMove: self.widget_move,
            QEvent.MouseButtonRelease: self.mouse_release,
            QEvent.ShortcutOverride: self.shortcut_override,
            QEvent.KeyPress: self.key_press,
            QEvent.ContextMenu: self.context_menu,
        }

    def eventFilter(self, event_object, event) -> bool:
        if isinstance(event_object, QWindow):
            return self._window_event(event)

        return super().eventFilter(event_object, event)

    def _window_event(self, event) -> bool:
        """A mouse event as it comes to a window, before Qt picks a widget.

        The moves while a button pressed for a selection is held are taken
        here, the selection's: a drag of the video would take them, from the
        press it has seen here before the widget's (see DragNDropManager).

        The release is seen to here, the widget pressed on may be gone from
        under it by then (the overlay's chrome, hidden for the selecting),
        and Qt hands it to none. It goes on all the same: taken here, Qt
        would never let go of that widget (see PanManager), and where it
        does reach one, it is nothing of that one's (see mouse_release).
        """

        if event.type() == QEvent.MouseButtonRelease:
            self.window_release(event)
            return False

        if event.type() != QEvent.MouseMove:
            return False

        if self._block is not None:
            return self.mouse_move(event) is True

        if self._is_armed:
            self._hint_under_pointer()

        # one let go of while it was held
        return self._is_swallowed_held(event)

    def widget_move(self, event):
        """A move as it comes to a widget, after the window has had it.

        Those of a selection were taken at the window (see _window_event).
        What comes here meanwhile is Qt's own: a move with no button held,
        made up to say the pointer has left a widget hidden from under it,
        such as the overlay's chrome as the selecting starts. Taken for a
        release, it would end the selection there and then.
        """

        if self._block is not None or self._is_swallowed_held(event):
            return True

        return None

    def arm(self):
        """Have the next left drag over a video select a part to zoom to.

        Picked again before that, it is not to after all.
        """

        if self._is_armed:
            self._stop()
            return

        if self._block is not None:
            return

        self._is_armed = True
        self._set_cursor()

        self._hint(self._ctx.active_block)

    def mouse_press(self, event, event_object):
        self._is_context_menu_swallowed = False

        # pressed again, or not held now, a button was let go of before,
        # wherever its release went
        self._swallowed_buttons = {
            button
            for button in self._swallowed_buttons
            if button != event.button() and event.buttons() & button
        }

        if self._block is not None:
            # seen again on the way up to the cell, see OverlayBlockChild
            if event.button() == self._button:
                return True

            # another button let go of it, the right one with no menu
            self._cancel(event.button())
            return True

        if self._is_armed:
            return self._armed_press(event, event_object)

        block = self._trigger_block(event, event_object)

        if block is None:
            return None

        self._start(block, event.button())

        return True

    def mouse_move(self, event):
        if self._block is None:
            return None

        if not event.buttons() & self._button:
            # let go of somewhere the release never came from
            self._stop()
            return None

        if not self._is_selecting:
            moved = QCursor.pos() - self._press_pos

            # still a click, if it is let go of here
            if moved.manhattanLength() < QApplication.startDragDistance():
                return True

            self._is_selecting = True
            self._set_cursor()

        self._block.show_zoom_selection(self._selection())

        # the outline says it all now
        self._unhint()

        return True

    def window_release(self, event):
        """Zoom to the selection let go of; see _window_event."""

        if self._block is None or event.button() != self._button:
            return

        block = self._block
        was_selecting, was_armed = self._is_selecting, self._is_armed
        selection = self._selection() if was_selecting else QRect()

        self._stop()

        # not a click on the video either, unless it is one with a key held
        # that was never dragged, for the keymap to have
        if was_selecting or was_armed:
            self._swallowed_buttons.add(event.button())

        if not selection.isEmpty():
            block.zoom_to_selection(selection)

    def mouse_release(self, event):
        """A release as it comes to a widget, after the window had it."""

        if event.button() in self._swallowed_buttons:
            self._swallowed_buttons.discard(event.button())
            return True

        return None

    def shortcut_override(self, event):
        if not self._is_busy() or event.key() != Qt.Key_Escape:
            return None

        # not what Esc is bound to: the key comes as a press, see key_press
        event.accept()
        return True

    def key_press(self, event):
        if not self._is_busy() or event.key() != Qt.Key_Escape:
            return None

        self._cancel()
        return True

    def context_menu(self, event):
        if self._is_context_menu_swallowed:
            self._is_context_menu_swallowed = False
            return True

        # from the keyboard: it lets go of the selection all the same
        if self._is_busy():
            self._cancel()
            return True

        return None

    def _armed_press(self, event, event_object):
        if is_modal_open() or not self._is_players(event_object):
            # gone on to something else
            self._stop()
            return None

        if event.button() != Qt.LeftButton:
            self._cancel(event.button())
            return True

        block = self._selectable_block(event_object)

        if block is None:
            # somewhere with no picture to zoom: not after all, and not a
            # click on whatever it was either
            self._cancel(event.button())
            return True

        self._start(block, event.button())

        return True

    def _trigger_block(self, event, event_object):
        """The video a press selects a part of, None if it does not."""

        if is_modal_open() or not _is_trigger(event):
            return None

        block = self._selectable_block(event_object)

        if block is None:
            return None

        # the overlay's buttons, bars and markers act on a press themselves
        if block.overlay.is_control_at(QCursor.pos()):
            return None

        return block

    def _selectable_block(self, pressed):
        """The video pressed on where it has a picture on show to zoom."""

        block = self._ctx.commands.get_video_block_under_mouse()

        if block is None or not _is_part_of(pressed, block):
            return None

        if block.zoom_selection_area() is None:
            return None

        return block

    def _is_players(self, widget) -> bool:
        """Whether a widget is in the player's window, or a video's overlay
        of its own, rather than a window that is over the player."""

        window = widget.window()

        return window is self.parent() or isinstance(window, OverlayBlock)

    def _start(self, block, button):
        self._block = block
        self._button = button
        self._press_pos = QCursor.pos()

        block.destroyed.connect(self._forget_block)

    def _selection(self) -> QRect:
        """The part of the picture dragged over, in the cell's pixels."""

        area = self._block.zoom_selection_area()

        if area is None:
            return QRect()

        start = self._block.mapFromGlobal(self._press_pos)
        end = self._block.mapFromGlobal(QCursor.pos())

        spanned = QRect(
            QPoint(min(start.x(), end.x()), min(start.y(), end.y())),
            QSize(abs(end.x() - start.x()), abs(end.y() - start.y())),
        )

        return spanned.intersected(area)

    def _is_swallowed_held(self, event) -> bool:
        return any(event.buttons() & button for button in self._swallowed_buttons)

    def _is_busy(self) -> bool:
        return self._is_armed or self._block is not None

    def _cancel(self, *buttons):
        """Let go of the selection, or of the one picked for.

        The buttons it is let go of with are nothing else's, nor is the one
        it was being made with: let go of later, it would be a click.
        """

        if self._block is not None:
            self._swallowed_buttons.add(self._button)

        self._swallowed_buttons.update(buttons)

        if Qt.RightButton in buttons:
            self._is_context_menu_swallowed = True

        self._stop()

    def _forget_block(self):
        # gone, and its overlay with it
        self._block = None
        self._stop()

    def _hint(self, block):
        """Say how to select on this video, if it has a picture to, and on
        no other: the one the selection is likeliest to be made over."""

        if block is None or block is self._hinted:
            return

        if block.zoom_selection_area() is None:
            return

        self._unhint()

        self._hinted = block
        block.destroyed.connect(self._forget_hinted)
        block.show_zoom_hint(True)

    def _hint_under_pointer(self):
        # off the videos, the one it was last over goes on saying it
        self._hint(self._ctx.commands.get_video_block_under_mouse())

    def _unhint(self):
        hinted, self._hinted = self._hinted, None

        if hinted is None:
            return

        with contextlib.suppress(TypeError, RuntimeError):
            hinted.destroyed.disconnect(self._forget_hinted)

        hinted.show_zoom_hint(False)

    def _forget_hinted(self):
        # gone, and its overlay with it
        self._hinted = None

    def _stop(self):
        self._unhint()

        block = self._block

        if block is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                block.destroyed.disconnect(self._forget_block)

            if self._is_selecting:
                block.show_zoom_selection(None)

        if self._is_cursor_set:
            QApplication.restoreOverrideCursor()

        self._block = None
        self._press_pos = None
        self._is_selecting = False
        self._is_armed = False
        self._is_cursor_set = False

    def _set_cursor(self):
        if not self._is_cursor_set:
            QApplication.setOverrideCursor(Qt.CrossCursor)
            self._is_cursor_set = True


def _is_part_of(widget, block) -> bool:
    """Whether a widget is the video's, or its overlay's, rather than one
    of a window over it, such as a dialog that belongs to it."""

    while widget is not None:
        if widget is block or widget is block.overlay:
            return True

        if widget.isWindow():
            return False

        widget = widget.parentWidget()

    return False


def _is_trigger(event) -> bool:
    settings = Settings()
    trigger = settings.get("player/zoom_select_trigger")

    if trigger == ZoomSelectTrigger.NONE:
        return False

    # moving the picture about has it, which the settings do not let be
    if trigger.value == settings.get("player/pan_trigger").value:
        return False

    if trigger == ZoomSelectTrigger.MIDDLE:
        return event.button() == Qt.MiddleButton

    if event.button() != Qt.LeftButton:
        return False

    # as the drop does: the press may not say, where the window was not
    # focused when it came
    held = QApplication.queryKeyboardModifiers() | event.modifiers()

    return bool(held & _TRIGGER_MODIFIERS[trigger])
