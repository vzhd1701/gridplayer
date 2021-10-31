import base64

from PyQt5.QtCore import QEvent, Qt, pyqtSignal, pyqtSlot

from gridplayer.params_static import WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings


class WindowStateManager(ManagerBase):
    pause_on_minimize = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_maximized_pre_fullscreen = False
        self._ctx.window_state = self.window_state

    @property
    def event_map(self):
        return {QEvent.WindowStateChange: self.changeEvent}

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
            if self._ctx.is_maximized_pre_fullscreen:
                self.parent().showMaximized()
            else:
                self.parent().showNormal()

            self._ctx.is_maximized_pre_fullscreen = False
        else:
            self._ctx.is_maximized_pre_fullscreen = (
                self.parent().windowState() == Qt.WindowMaximized
            )

            self.parent().showFullScreen()

    def set_minimum_size(self, size):
        self.parent().setMinimumSize(size)

    def restore_to_minimum(self):
        if not self.parent().isMaximized() and not self.parent().isFullScreen():
            self.parent().resize(self.parent().minimumSize())

    def activate_window(self):
        self.parent().raise_()
        self.parent().activateWindow()

    def window_state(self):
        is_maximized = (
            self.parent().isMaximized() or self._ctx.is_maximized_pre_fullscreen
        )

        return WindowState(
            is_maximized=is_maximized,
            is_fullscreen=self.parent().isFullScreen(),
            geometry=base64.b64encode(bytes(self.parent().saveGeometry())).decode(),
        )

    @pyqtSlot(WindowState)
    def restore_window_state(self, window_state):
        geometry = base64.b64decode(window_state.geometry.encode())

        self.parent().restoreGeometry(geometry)

        if window_state.is_fullscreen:
            if window_state.is_maximized:
                self._ctx.is_maximized_pre_fullscreen = True
                self.parent().showFullScreen()

        elif window_state.is_maximized:
            self.parent().showMaximized()
