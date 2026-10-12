import base64

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from gridplayer.params import env
from gridplayer.params.static import PLAYER_INITIAL_SIZE, PLAYER_MIN_SIZE, WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.misc import force_terminate
from gridplayer.utils.taskbar import (
    is_taskbar_hiding_available,
    set_hidden_from_taskbar,
)
from gridplayer.widgets.video_overlay import OverlayBlock

# QEvent::Quit, which PyQt5 leaves out of QEvent.Type
QUIT_EVENT = 20


class _QuitWatcher(QObject):
    """Sees the application asked to quit, as macOS asks it on Cmd+Q, before
    the windows are asked to close."""

    def __init__(self, on_quit, **kwargs):
        super().__init__(**kwargs)

        self._on_quit = on_quit

    def eventFilter(self, event_object, event):
        if event.type() == QUIT_EVENT:
            self._on_quit()

        return False


class WindowStateManager(ManagerBase):
    pause_on_minimize = pyqtSignal()
    closing = pyqtSignal()
    # minimized or in the tray, with nothing on screen to watch
    away_changed = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_maximized_pre_fullscreen = False
        self._ctx.window_state = self.window_state
        self._ctx.is_pause_minimized = Settings().get("playlist/pause_minimized")

        self.pre_minimize_unpaused = []

        self._is_away = False

        self._is_in_tray = False
        # maximized or full screen, to come back from the tray as it went
        self._tray_restore_state = Qt.WindowNoState
        # the other windows that were open, gone to the tray with the player
        self._tray_hidden_windows = []

        # asked to quit rather than to close, which the tray may take
        self._is_quitting = False

        self._quit_watcher = None

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

        app = QApplication.instance()

        # In the tray the player is hidden, and closing any other window
        # would quit with it as the last one. Closing the player quits by
        # itself, see closeEvent.
        app.setQuitOnLastWindowClosed(False)

        # logging off closes every window, which must not go to the tray
        app.commitDataRequest.connect(self._set_quitting)

        if env.IS_MACOS:
            # Cmd+Q and Quit in the Dock
            self._quit_watcher = _QuitWatcher(self._set_quitting, parent=self)
            app.installEventFilter(self._quit_watcher)

            # the Dock icon clicked, or the app opened again
            app.applicationStateChanged.connect(self._on_application_state)

    @property
    def event_map(self):
        return {
            QEvent.WindowStateChange: self.changeEvent,
            QEvent.Close: self.closeEvent,
            QEvent.Show: self.showEvent,
        }

    @property
    def commands(self):
        return {
            "minimize": self.parent().showMinimized,
            "close": self.parent().close,
            "quit": self.cmd_quit,
            "fullscreen": self.cmd_fullscreen,
            "is_fullscreen": self.parent().isFullScreen,
            "activate_window": self.activate_window,
            "toggle_window": self.toggle_window,
            "is_window_away": self.is_window_away,
            "is_pause_minimized": lambda: self._ctx.is_pause_minimized,
            "set_pause_minimized": self.set_pause_minimized,
            "toggle_pause_minimized": self.toggle_pause_minimized,
            "forget_minimize_pause": self.forget_minimize_pause,
        }

    def changeEvent(self, event):
        window = self.parent()

        if (
            window.isMinimized()
            and not self._is_in_tray
            and self._is_minimize_to_tray()
        ):
            # hidden while the minimize is still going on, Windows leaves
            # the window in two minds about its state
            old_state = event.oldState()
            QTimer.singleShot(0, lambda: self._minimize_to_tray(old_state))

        self._update_away()

    def showEvent(self, event):
        if event.spontaneous():
            return

        self.apply_taskbar(is_showing=True)

    def closeEvent(self, event):
        if not self._is_quitting and self._is_close_to_tray() and self.hide_to_tray():
            event.ignore()
            self._ctx.commands.show_tray_note()
            return True

        # Ask about unsaved changes while the window is still up, then take it
        # off screen before closing the playlist: closing it releases the video
        # players, and a hardware video output takes a moment to let go, which
        # the user would otherwise sit and watch happen pane by pane. From the
        # tray, the question brings the window back with it.
        if not self._ctx.commands.check_playlist_save():
            self._is_quitting = False
            event.ignore()
            return True

        # after the question, which can save the playlist somewhere new
        self._ctx.commands.remember_last_playlist()

        self.parent().hide()

        self._ctx.commands.force_close_playlist()

        self.closing.emit()

        force_terminate()

    def cmd_quit(self):
        self._is_quitting = True

        self.parent().close()

    def _set_quitting(self, *_):
        self._is_quitting = True

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

    def forget_minimize_pause(self):
        """Played or paused while minimized, by the media keys: the videos
        are left as they are on return, rather than played again."""

        self.pre_minimize_unpaused = []

    def toggle_pause_minimized(self):
        value = not self._ctx.is_pause_minimized
        PlaylistSettings().set("playlist/pause_minimized", value)
        self.set_pause_minimized(value)

    def restore_initial_size(self):
        if not self.parent().isMaximized() and not self.parent().isFullScreen():
            self.parent().resize(QSize(*PLAYER_INITIAL_SIZE))

    def activate_window(self):
        window = self.parent()

        if self._is_in_tray:
            self._show_from_tray()
        elif window.isMinimized():
            window.setWindowState(window.windowState() & ~Qt.WindowMinimized)

        window.raise_()
        window.activateWindow()

    def toggle_window(self):
        """The tray icon clicked: the window back, or off to the tray."""

        if self.is_window_away():
            self.activate_window()
        else:
            self.hide_to_tray()

    def is_window_away(self) -> bool:
        return self._is_in_tray or self.parent().isMinimized()

    def hide_to_tray(self, restore_state=None) -> bool:
        """Take the player off screen, to the tray icon. Whether it went.

        Not while a dialog waits for an answer: it would be left on screen
        with nothing to come back to.
        """

        if self._is_in_tray:
            return True

        if not self._ctx.is_tray_shown or QApplication.activeModalWidget():
            return False

        window = self.parent()

        if restore_state is None:
            restore_state = window.windowState()

        self._tray_restore_state = restore_state & ~Qt.WindowMinimized

        self._is_in_tray = True

        self._hide_other_windows()
        window.hide()

        self._update_away()

        if Settings().get("player/tray_stop_video"):
            self._ctx.commands.set_video_decoding_stopped(True)

        return True

    def _minimize_to_tray(self, old_state):
        if not self.parent().isMinimized() or self._is_in_tray:
            return

        self.hide_to_tray(old_state)

    def _show_from_tray(self):
        self._is_in_tray = False

        window = self.parent()

        window.setWindowState(self._tray_restore_state)
        window.show()

        self._show_other_windows()

        self._update_away()

        # the pictures back on a window that is up to show them
        if self._ctx.is_video_decoding_stopped:
            self._ctx.commands.set_video_decoding_stopped(False)

    def _hide_other_windows(self):
        player = self.parent()

        self._tray_hidden_windows = [
            w
            for w in QApplication.topLevelWidgets()
            if w is not player
            and w.isVisible()
            and w.windowType() in {Qt.Window, Qt.Dialog}
            and not isinstance(w, OverlayBlock)
        ]

        for w in self._tray_hidden_windows:
            w.hide()

    def _show_other_windows(self):
        for w in self._tray_hidden_windows:
            if not sip.isdeleted(w):
                w.show()

        self._tray_hidden_windows = []

    def _update_away(self):
        is_away = self.is_window_away()

        if is_away == self._is_away:
            return

        self._is_away = is_away

        if self._ctx.is_pause_minimized:
            if is_away:
                self.pre_minimize_unpaused = self._ctx.video_blocks.unpaused
                self.pause_on_minimize.emit()
            else:
                for v in self.pre_minimize_unpaused:
                    v.set_pause(False)
                self.pre_minimize_unpaused = []

        self.away_changed.emit(is_away)

    def _on_application_state(self, state):
        if state == Qt.ApplicationActive and self._is_in_tray:
            self.activate_window()

    def _is_minimize_to_tray(self) -> bool:
        if not Settings().get("player/tray_icon"):
            return False

        # with no button in the taskbar, a window minimized has nowhere else
        return Settings().get("player/minimize_to_tray") or self._is_taskbar_hidden()

    def _is_close_to_tray(self) -> bool:
        return Settings().get("player/tray_icon") and Settings().get(
            "player/close_to_tray"
        )

    def _is_taskbar_hidden(self) -> bool:
        return (
            Settings().get("player/tray_icon")
            and Settings().get("player/hide_taskbar")
            and is_taskbar_hiding_available()
            and self._ctx.is_tray_shown
        )

    def apply_taskbar(self, *_, is_showing=False):
        set_hidden_from_taskbar(
            self.parent(), self._is_taskbar_hidden(), is_showing=is_showing
        )

    def window_state(self):
        is_maximized = (
            self.parent().isMaximized() or self._ctx.is_maximized_pre_fullscreen
        )

        if self._is_in_tray:
            is_maximized = is_maximized or bool(
                self._tray_restore_state & Qt.WindowMaximized
            )
            is_fullscreen = bool(self._tray_restore_state & Qt.WindowFullScreen)
        else:
            is_fullscreen = self.parent().isFullScreen()

        return WindowState(
            is_maximized=is_maximized,
            is_fullscreen=is_fullscreen,
            geometry=base64.b64encode(bytes(self.parent().saveGeometry())).decode(),
        )

    @pyqtSlot(WindowState)
    def restore_window_state(self, window_state):
        geometry = base64.b64decode(window_state.geometry.encode())

        self.parent().restoreGeometry(geometry)

        # in the tray, the window comes back as the playlist has it
        if self._is_in_tray:
            if window_state.is_fullscreen and window_state.is_maximized:
                self._ctx.is_maximized_pre_fullscreen = True
                self._tray_restore_state = Qt.WindowFullScreen
            elif window_state.is_maximized and not window_state.is_fullscreen:
                self._tray_restore_state = Qt.WindowMaximized
            else:
                self._tray_restore_state = Qt.WindowNoState
            return

        if window_state.is_fullscreen:
            if window_state.is_maximized:
                self._ctx.is_maximized_pre_fullscreen = True
                self.parent().showFullScreen()

        elif window_state.is_maximized:
            self.parent().showMaximized()
