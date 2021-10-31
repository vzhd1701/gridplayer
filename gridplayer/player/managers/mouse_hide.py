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

        for event in self.move_events:
            self._event_map[event] = self.show_cursor

        QApplication.instance().focusObjectChanged.connect(self._focus_change)

    def hide_cursor(self):
        self.mouse_timer.stop()

        if not self._context["video_blocks"] or is_modal_open():
            return

        if QApplication.overrideCursor() != Qt.BlankCursor:
            QApplication.setOverrideCursor(Qt.BlankCursor)

            self.mouse_hidden.emit()

    def show_cursor(self):
        if QApplication.overrideCursor() == Qt.BlankCursor:
            QApplication.restoreOverrideCursor()

            self.mouse_shown.emit()

        if Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

    def _focus_change(self, focusWindow):
        try:
            is_modal = focusWindow.isModal()
        except AttributeError:
            return

        if is_modal:
            self.show_cursor()
