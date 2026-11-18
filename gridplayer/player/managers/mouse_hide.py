from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import is_modal_open


class MouseHideManager(ManagerBase):
    mouse_hidden = pyqtSignal()
    mouse_shown = pyqtSignal()

    move_events = {
        QEvent.Type.ShortcutOverride,
        QEvent.Type.NonClientAreaMouseMove,
        QEvent.Type.NonClientAreaMouseButtonPress,
        QEvent.Type.ContextMenu,
        QEvent.Type.HoverMove,
        QEvent.Type.KeyPress,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
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
        return dict.fromkeys(self.move_events, self.show_cursor)

    def hide_cursor(self):
        self.mouse_timer.stop()

        if not self._ctx.video_blocks or is_modal_open():
            return

        # resting on the List window, being read
        if self.is_elsewhere_at(QCursor.pos()):
            return

        if QApplication.overrideCursor() is None:
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)

            self.mouse_hidden.emit()

    def show_cursor(self):
        if QApplication.overrideCursor() == Qt.CursorShape.BlankCursor:
            QApplication.restoreOverrideCursor()

            self.mouse_shown.emit()

        if self.parent().isVisible() and Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))
