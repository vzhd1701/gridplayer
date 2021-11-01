from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.misc import is_modal_open


class MouseHideManager(ManagerBase):
    mouse_hidden = pyqtSignal()
    mouse_shown = pyqtSignal()

    move_events = {
        QEvent.ShortcutOverride,
        QEvent.NonClientAreaMouseMove,
        QEvent.NonClientAreaMouseButtonPress,
        QEvent.ContextMenu,
        QEvent.HoverMove,
        QEvent.KeyPress,
        QEvent.MouseMove,
        QEvent.Wheel,
        QEvent.MouseButtonPress,
        QEvent.MouseButtonRelease,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.mouse_timer = QTimer(self)
        self.mouse_timer.timeout.connect(self.hide_cursor)
        if Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

        QApplication.instance().focusObjectChanged.connect(self.show_cursor)

    @property
    def event_map(self):
        return {e: self.show_cursor for e in self.move_events}

    def hide_cursor(self):
        self.mouse_timer.stop()

        if not self._ctx.video_blocks or is_modal_open():
            return

        if QApplication.overrideCursor() is None:
            QApplication.setOverrideCursor(Qt.BlankCursor)

            self.mouse_hidden.emit()

    def show_cursor(self):
        if QApplication.overrideCursor() == Qt.BlankCursor:
            QApplication.restoreOverrideCursor()

            self.mouse_shown.emit()

        if self.parent().isVisible() and Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))
