import platform
import subprocess
import sys

from PyQt5.QtCore import QDir, QDirIterator, QEvent, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QFontDatabase, QIcon
from PyQt5.QtWidgets import QApplication, QStyleFactory

from gridplayer.settings import Settings
from gridplayer.utils.darkmode import is_dark_mode
from gridplayer.utils.single_instance import is_the_only_instance
from gridplayer.version import (
    __app_id__,
    __app_name__,
    __author_name__,
    __display_name__,
    __version__,
)


class MainApp(QApplication):
    open_files = pyqtSignal(list)

    def __init__(self, argv):
        super().__init__(argv)

        self._is_empty = True

    def event(self, event):
        if platform.system() == "Darwin":
            self._handle_macos_fileopen(event)

        if event.type() == QEvent.PaletteChange:
            _switch_icon_theme()

        return super().event(event)

    def video_count_change(self, count):
        self._is_empty = count == 0

    def _handle_macos_fileopen(self, event):
        # MacOS support
        if event.type() != QEvent.FileOpen or not event.file():
            return

        Settings().sync()

        is_only_empty = is_the_only_instance() and self._is_empty

        if Settings().get("player/one_instance") or is_only_empty:
            self.open_files.emit([event.file()])
        else:
            subprocess.run(  # noqa: S603, S607
                [
                    "open",
                    "-n",
                    f"/Applications/{__app_name__}.app",
                    "--args",
                    event.file(),
                ]
            )


def setup_app_env():
    if platform.system() == "Windows":
        from PyQt5.QtWinExtras import QtWin  # noqa: WPS433

        QtWin.setCurrentProcessExplicitAppUserModelID(__app_id__)

    QApplication.setApplicationName(__app_name__)
    QApplication.setApplicationDisplayName(__display_name__)
    QApplication.setOrganizationName(__author_name__)
    QApplication.setApplicationVersion(__version__)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)


def init_app():
    app = MainApp(sys.argv)

    _init_resources()

    if platform.system() == "Linux":
        app.setStyle(QStyleFactory.create("Fusion"))

    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    _switch_icon_theme()

    _init_icon(app)

    font_size = app.font().pointSize() if platform.system() == "Darwin" else 9
    app.setFont(QFont("Hack", font_size, QFont.Normal))

    return app


def _init_icon(app):
    if platform.system() == "Darwin":
        app.setWindowIcon(QIcon(":/icons/main_ico_mac.icns"))
    elif platform.system() == "Windows":
        app.setWindowIcon(QIcon(":/icons/main_ico_win.ico"))
    else:
        if app.desktop().devicePixelRatio() == 1:
            app.setWindowIcon(QIcon(":/icons/main_ico_48.png"))
        else:
            app.setWindowIcon(QIcon(":/icons/main_ico_svg.svg"))


def _switch_icon_theme():
    if is_dark_mode():
        QIcon.setThemeName("dark")
    else:
        QIcon.setThemeName("light")


def _init_resources():
    # noinspection PyUnresolvedReferences
    from gridplayer import resources_bin  # noqa:F401,WPS433

    fonts = QDirIterator(":/fonts", ("*.ttf",), QDir.Files)

    while fonts.hasNext():
        font = fonts.next()
        QFontDatabase.addApplicationFont(font)
