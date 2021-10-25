from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QInputEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.settings import Settings


class PlayerMouseHiderMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.mouse_timer = QTimer()
        self.mouse_timer.timeout.connect(self.check_mouse_state)
        if Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

    def mouseMoveEvent(self, event):
        self.mouse_reset()

        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        self.mouse_reset()

    def event(self, event) -> bool:
        if event.type() in {QEvent.ShortcutOverride, QEvent.NonClientAreaMouseMove}:
            self.mouse_reset()

        return super().event(event)

    def eventFilter(self, event_object, event) -> bool:
        """Show cursor on any mouse event for children"""

        if isinstance(event, QInputEvent):
            self.mouse_reset()

        return False

    def check_mouse_state(self):
        self.mouse_timer.stop()

        if not self.is_videos:
            return

        if self.isVisible():
            QApplication.setOverrideCursor(Qt.BlankCursor)

        self.update_active_block(None)

        self.hide_overlay.emit()

    def mouse_reset(self):
        QApplication.restoreOverrideCursor()

        if not self.is_modal_open and Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

        self.update_active_block(self.get_current_cursor_pos())
