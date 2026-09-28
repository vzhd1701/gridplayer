from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import PanTrigger
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import is_modal_open
from gridplayer.widgets.video_overlay_buttons import OverlayButton
from gridplayer.widgets.video_overlay_elements import OverlayBar

_TRIGGER_MODIFIERS = {
    PanTrigger.CTRL: Qt.ControlModifier,
    PanTrigger.SHIFT: Qt.ShiftModifier,
    PanTrigger.ALT: Qt.AltModifier,
}


class PanManager(ManagerBase):
    """Dragging a video's picture about, the picture going with the pointer.

    With the middle button by default, which nothing else uses; or the
    left one with a key held (see the pan_trigger setting). A plain left
    drag is always moving the video to another cell, and holding the key
    only counts when it is down before the button is: a key pressed once
    a video is being moved is the drop's, as ever.

    A click with no drag is still a click, for the keymap to have.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._block = None
        self._button = Qt.MiddleButton
        self._press_pos: QPoint | None = None
        self._last_pos: QPoint | None = None
        self._left_over = (0.0, 0.0)
        self._is_panning = False

    @property
    def commands(self):
        return {"is_pan_press": self.is_pan_press}

    @property
    def event_map(self):
        return {
            QEvent.MouseButtonPress: self.mouse_press,
            QEvent.MouseMove: self.mouse_move,
            QEvent.MouseButtonRelease: self.mouse_release,
        }

    def is_pan_press(self, event) -> bool:
        """Whether a press starts dragging a picture about, not anything else."""

        return self._pan_block(event) is not None

    def mouse_press(self, event):
        # seen again by every widget the press is passed up through
        if self._block is not None:
            return

        block = self._pan_block(event)

        if block is None:
            return

        self._block = block
        self._button = event.button()
        self._press_pos = QCursor.pos()
        self._last_pos = self._press_pos
        self._left_over = (0.0, 0.0)

    def mouse_move(self, event):
        if self._block is None:
            return None

        if not event.buttons() & self._button:
            # let go of somewhere the release never came from
            self._stop()
            return None

        pos = QCursor.pos()

        if not self._is_panning:
            if (pos - self._press_pos).manhattanLength() < (
                QApplication.startDragDistance()
            ):
                return None

            self._is_panning = True
            QApplication.setOverrideCursor(Qt.ClosedHandCursor)

        moved = pos - self._last_pos
        self._last_pos = pos

        if moved.isNull():
            return True

        left_x, left_y = self._left_over
        left_over = self._block.pan_by(moved.x() + left_x, moved.y() + left_y)
        self._left_over = left_over or (0.0, 0.0)

        return True

    def mouse_release(self, event):
        if self._block is None or event.button() != self._button:
            return None

        block, was_panning = self._block, self._is_panning

        self._stop()

        if not was_panning:
            # a click, not a drag
            return None

        # says where the picture ended up, as a move from the menu does
        block.set_shift(block.video_params.shift)

        return True

    def _pan_block(self, event):
        """The video a press would drag the picture of, None if it would not."""

        if is_modal_open() or not _is_trigger(event):
            return None

        block = self._ctx.commands.get_video_block_under_mouse()

        if block is None or not block.is_video_initialized or not block.video_tracks:
            return None

        return block

    def _stop(self):
        if self._is_panning:
            QApplication.restoreOverrideCursor()

        self._block = None
        self._press_pos = None
        self._last_pos = None
        self._is_panning = False


def _is_trigger(event) -> bool:
    trigger = Settings().get("player/pan_trigger")

    if trigger == PanTrigger.MIDDLE:
        return event.button() == Qt.MiddleButton

    if trigger not in _TRIGGER_MODIFIERS or event.button() != Qt.LeftButton:
        return False

    # as the drop does: the press may not say, where the window was not
    # focused when it came
    held = QApplication.queryKeyboardModifiers() | event.modifiers()

    if not held & _TRIGGER_MODIFIERS[trigger]:
        return False

    # the overlay's buttons and bars act on a left press themselves
    pressed = QApplication.widgetAt(QCursor.pos())

    return not isinstance(pressed, (OverlayButton, OverlayBar))
