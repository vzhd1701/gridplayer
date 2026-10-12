from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from gridplayer.params import env
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.version import __app_name__
from gridplayer.widgets.custom_menu import CustomMenu

NOTE_DURATION_MS = 5000


class TrayManager(ManagerBase):
    """The icon in the tray, the menu bar on macOS, to show the window from.

    Clicked, it shows the window or hides it; its menu does the same, and
    quits. On macOS, and in GNOME's tray, a click opens the menu instead.
    """

    # the icon put up or taken down, or its settings changed
    changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._icon = None
        self._menu = None
        self._show_action = None
        self._quit_action = None

        self._ctx.is_tray_shown = self.is_shown

    @property
    def commands(self):
        return {"show_tray_note": self.show_note}

    def init(self):
        self.apply_settings()

    def apply_settings(self, *_):
        is_wanted = Settings().get("player/tray_icon")

        if is_wanted and self._icon is None:
            self._create()
        elif not is_wanted and self._icon is not None:
            self.cleanup()

        self.changed.emit()

    def is_shown(self) -> bool:
        """Whether the icon is there to bring the window back with."""

        return (
            self._icon is not None
            and self._icon.isVisible()
            and QSystemTrayIcon.isSystemTrayAvailable()
        )

    def cleanup(self):
        """Take the icon down. Windows leaves one behind otherwise, until
        the pointer goes over it: the player ends with os._exit."""

        if self._icon is None:
            return

        self._icon.hide()
        self._icon.deleteLater()
        self._icon = None

        self._menu.deleteLater()
        self._menu = None

    def show_note(self):
        """Say once that the player is still running, as it goes to the tray
        on close for the first time."""

        if Settings().get("player/tray_note_shown"):
            return

        if self._icon is None or not QSystemTrayIcon.supportsMessages():
            return

        if env.IS_MACOS:
            text = translate(
                "Tray", "GridPlayer is still running. Click its icon to quit."
            )
        else:
            text = translate(
                "Tray", "GridPlayer is still running. Right-click its icon to quit."
            )

        self._icon.showMessage(
            __app_name__, text, QSystemTrayIcon.Information, NOTE_DURATION_MS
        )

        Settings().set("player/tray_note_shown", True)

    def _create(self):
        self._menu = CustomMenu()

        self._show_action = self._menu.addAction(
            translate("Actions", "Show"), self._toggle_window
        )

        # what a click on the icon does, as Windows marks it
        font = QFont(self._show_action.font())
        font.setBold(True)
        self._show_action.setFont(font)

        self._menu.addSeparator()

        # No icons: GNOME and macOS draw the menu themselves, and look an icon
        # up by its name in the system's theme, which has none of ours
        self._quit_action = self._menu.addAction(
            translate("Actions", "Quit"), self._quit
        )

        self._menu.aboutToShow.connect(self._update_menu)

        self._icon = QSystemTrayIcon(_tray_icon(), self)
        self._icon.setToolTip(__app_name__)
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)
        self._icon.messageClicked.connect(self._ctx.commands.activate_window)
        self._icon.show()

    def _update_menu(self):
        is_away = self._ctx.commands.is_window_away()
        is_modal = QApplication.activeModalWidget() is not None

        if is_away:
            self._show_action.setText(translate("Actions", "Show"))
        else:
            self._show_action.setText(translate("Actions", "Hide"))

        # a dialog waiting for an answer goes nowhere: shown, it comes along
        self._show_action.setEnabled(is_away or not is_modal)
        self._quit_action.setEnabled(not is_modal)

    def _on_activated(self, reason):
        # macOS opens the menu on a click, which has Show in it
        if env.IS_MACOS:
            return

        if reason == QSystemTrayIcon.Trigger:
            self._toggle_window()

    def _toggle_window(self):
        self._ctx.commands.toggle_window()

    def _quit(self):
        if QApplication.activeModalWidget() is not None:
            return

        self._ctx.commands.quit()


def _tray_icon() -> QIcon:
    # the menu bar has its icons in one colour, the one it picks itself
    if env.IS_MACOS:
        icon = QIcon(str(env.RESOURCES_DIR / "icons" / "main_ico_symbolic.svg"))
        icon.setIsMask(True)
        return icon

    return QApplication.windowIcon()
