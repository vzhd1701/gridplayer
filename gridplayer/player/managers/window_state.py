from PyQt5.QtCore import QEvent, Qt, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings


class WindowStateManager(ManagerBase):
    pause_on_minimize = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._context["is_maximized_pre_fullscreen"] = False

        self._event_map = {QEvent.WindowStateChange: self.changeEvent}

    @property
    def commands(self):
        return {
            "minimize": self.parent().showMinimized,
            "close": self.parent().close,
            "fullscreen": self.cmd_fullscreen,
            "is_fullscreen": self.parent().isFullScreen,
        }

    def changeEvent(self, event):
        pause_when_minimized = self.parent().isMinimized() and Settings().get(
            "player/pause_minimized"
        )
        if pause_when_minimized:
            self.pause_on_minimize.emit()

    def cmd_fullscreen(self):
        if self.parent().isFullScreen():
            if self._context["is_maximized_pre_fullscreen"]:
                self.parent().showMaximized()
            else:
                self.parent().showNormal()

            self._context["is_maximized_pre_fullscreen"] = False
        else:
            self._context["is_maximized_pre_fullscreen"] = (
                self.parent().windowState() == Qt.WindowMaximized
            )

            self.parent().showFullScreen()
