import base64

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal, pyqtSlot

from gridplayer.params import env
from gridplayer.params.static import PLAYER_INITIAL_SIZE, PLAYER_MIN_SIZE, WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.misc import force_terminate


class WindowStateManager(ManagerBase):
    pause_on_minimize = pyqtSignal()
    closing = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_maximized_pre_fullscreen = False
        self._ctx.window_state = self.window_state
        self._ctx.is_pause_minimized = Settings().get("playlist/pause_minimized")

        self.pre_minimize_unpaused = []

    def init(self):
        self.parent().setMinimumSize(QSize(*PLAYER_MIN_SIZE))
        self.parent().resize(QSize(*PLAYER_INITIAL_SIZE))

        # Linux has window manager for this, the flag doesn't work there anyway
        if not env.IS_LINUX and Settings().get("player/stay_on_top"):
            self.parent().setWindowFlag(Qt.WindowStaysOnTopHint)

        self._ctx.is_maximized_pre_fullscreen = all(
            (
                Settings().get("player/start_fullscreen"),
                Settings().get("player/start_maximized"),
            )
        )

    @property
    def event_map(self):
        return {
            QEvent.WindowStateChange: self.changeEvent,
            QEvent.Close: self.closeEvent,
        }

    @property
    def commands(self):
        return {
            "minimize": self.parent().showMinimized,
            "close": self.parent().close,
            "fullscreen": self.cmd_fullscreen,
            "is_fullscreen": self.parent().isFullScreen,
            "activate_window": self.activate_window,
            "is_pause_minimized": lambda: self._ctx.is_pause_minimized,
            "set_pause_minimized": self.set_pause_minimized,
            "toggle_pause_minimized": self.toggle_pause_minimized,
        }

    def changeEvent(self, event):
        if not self._ctx.is_pause_minimized:
            return

        # Minimize
        if self.parent().isMinimized():
            self.pre_minimize_unpaused = self._ctx.video_blocks.unpaused
            self.pause_on_minimize.emit()
        # Restore
        elif event.oldState() & Qt.WindowMinimized:
            for v in self.pre_minimize_unpaused:
                v.set_pause(False)
            self.pre_minimize_unpaused = []

    def closeEvent(self, event):
        # Ask about unsaved changes while the window is still up, then take it
        # off screen before closing the playlist: closing it releases the video
        # players, and a hardware video output takes a moment to let go, which
        # the user would otherwise sit and watch happen pane by pane.
        if not self._ctx.commands.check_playlist_save():
            event.ignore()
            return True

        self.parent().hide()

        self._ctx.commands.force_close_playlist()

        self.closing.emit()

        force_terminate()

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

    def set_pause_minimized(self, is_pause):
        self._ctx.is_pause_minimized = is_pause

    def toggle_pause_minimized(self):
        value = not self._ctx.is_pause_minimized
        PlaylistSettings().set("playlist/pause_minimized", value)
        self.set_pause_minimized(value)

    def restore_initial_size(self):
        if not self.parent().isMaximized() and not self.parent().isFullScreen():
            self.parent().resize(QSize(*PLAYER_INITIAL_SIZE))

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
