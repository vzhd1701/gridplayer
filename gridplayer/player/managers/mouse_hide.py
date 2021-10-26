from PyQt5.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QInputEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.settings import Settings
from gridplayer.utils.misc import is_modal_open


class PlayerMouseHideManager(QObject):
    mouse_hidden = pyqtSignal()
    mouse_shown = pyqtSignal()

    move_events = {
        QEvent.ShortcutOverride,
        QEvent.NonClientAreaMouseMove,
        QEvent.NonClientAreaMouseButtonPress,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.is_no_videos = True

        self.mouse_timer = QTimer(self)
        self.mouse_timer.timeout.connect(self.hide_cursor)
        if Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

        QApplication.instance().focusObjectChanged.connect(self._focus_change)

    def eventFilter(self, event_object, event) -> bool:
        if isinstance(event, QInputEvent) or event.type() in self.move_events:
            self.show_cursor()

        return False

    def hide_cursor(self):
        self.mouse_timer.stop()

        if self.is_no_videos or is_modal_open():
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

    def set_video_count(self, video_count):
        self.is_no_videos = video_count == 0

    def _focus_change(self, focusWindow):
        if focusWindow and focusWindow.isModal():
            self.show_cursor()
