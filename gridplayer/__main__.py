import logging.config
import os
import platform
import sys
import traceback
from multiprocessing import active_children, freeze_support

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QStyleFactory

from gridplayer.utils import log_config
from gridplayer.dialogs.exception import ExceptionDialog
from gridplayer.utils.log_config import QtLogHandler
from gridplayer.resources import ICONS, init_resources
from gridplayer.utils.log import log_environment
from gridplayer.version import (
    __app_id__,
    __app_name__,
    __display_name__,
    __author_name__,
    __version__,
)

try:
    # Include in try/except block if you're also targeting Mac/Linux
    from PyQt5.QtWinExtras import QtWin, QWinThumbnailToolBar

    QtWin.setCurrentProcessExplicitAppUserModelID(__app_id__)
except ImportError:
    pass


def excepthook(exc_type, exc_value, exc_tb):
    # Log into file
    exception_txt = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    logger = logging.getLogger("UNHANDLED")
    logger.critical(exception_txt)

    # Terminate if Qt is not up
    if QApplication.instance() is None:
        os._exit(1)

    for w in QApplication.topLevelWidgets():
        w.hide()
    QApplication.restoreOverrideCursor()

    exc_dialog = ExceptionDialog(exception_txt)
    exc_dialog.exec_()

    for p in active_children():
        p.kill()

    os._exit(0)


class MainApp(QApplication):
    open_files = pyqtSignal(list)

    def __init__(self, argv):
        super().__init__(argv)

        self._is_empty = True

    def notify(self, obj, event):
        try:
            return QApplication.notify(self, obj, event)
        except Exception:
            excepthook(*sys.exc_info())

    def event(self, event):
        if platform.system() == "Darwin":
            self._handle_macos_fileopen(event)

        return super().event(event)

    def _handle_macos_fileopen(self, event):
        # MacOS support
        if event.type() != QEvent.FileOpen or not event.file():
            return

        from gridplayer.settings import settings
        from gridplayer.utils.macos import is_the_only_instance

        settings.sync()

        is_only_empty = is_the_only_instance() and self._is_empty

        if settings.get("player/one_instance") or is_only_empty:
            self.open_files.emit([event.file()])
        else:
            os.system(
                f"open -n /Applications/{__app_name__}.app --args '{event.file()}'"
            )

    def video_count_change(self, count):
        self._is_empty = count == 0


def init_log():
    from gridplayer.settings import get_app_data_dir, settings

    log_path = os.path.join(get_app_data_dir(), "gridplayer.log")

    log_config.config_log(log_path, settings.get("logging/log_level"))
    log_config.override_stdout()

    log_qt = QtLogHandler()
    QtCore.qInstallMessageHandler(log_qt.handle)


def init_app():
    app = MainApp(sys.argv)

    if platform.system() == "Linux":
        app.setStyle(QStyleFactory.create("Fusion"))

    init_resources()

    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    if platform.system() == "Darwin":
        app.setWindowIcon(ICONS["main/sys/macos"])
    elif platform.system() == "Windows":
        app.setWindowIcon(ICONS["main/sys/windows"])
    else:
        if app.desktop().devicePixelRatio() == 1:
            app.setWindowIcon(ICONS["main/png/48x48"])
        else:
            app.setWindowIcon(ICONS["main/svg/normal"])

    font_size = app.font().pointSize() if platform.system() == "Darwin" else 9
    app.setFont(QFont("Hack", font_size, QFont.Normal))

    return app


def main():
    freeze_support()

    sys.excepthook = excepthook

    QApplication.setApplicationName(__app_name__)
    QApplication.setApplicationDisplayName(__display_name__)
    QApplication.setOrganizationName(__author_name__)
    QApplication.setApplicationVersion(__version__)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    init_log()

    from gridplayer.settings import settings

    # MacOS has OpenFile events
    if platform.system() != "Darwin":
        from gridplayer.utils.single_instance import (
            Listener,
            delegate_if_not_primary,
        )

        if settings.get("player/one_instance") and delegate_if_not_primary(sys.argv):
            sys.exit(0)

    log = logging.getLogger("MAIN")

    log.info(f"{__display_name__} v.{__version__} starting")

    log_environment()

    log.info("Initializing app")
    app = init_app()

    from gridplayer.params_vlc import init_vlc

    log.info("Initializing VLC")

    try:
        init_vlc()
    except FileNotFoundError:
        from gridplayer.dialogs.messagebox import QCustomMessageBox

        QCustomMessageBox.critical(None, "Error", "VLC player is not installed!")
        sys.exit(1)

    from gridplayer.player import Player

    player = Player()
    player.show()

    # MacOS has OpenFile events
    if platform.system() != "Darwin":
        import atexit

        instance_listener = Listener()
        instance_listener.start()
        atexit.register(instance_listener.cleanup)

        instance_listener.open_files.connect(player.process_arguments)

    app.open_files.connect(player.process_arguments)
    player.video_count_change.connect(app.video_count_change)

    if sys.argv[1:]:
        player.process_arguments(sys.argv[1:])

    ret = app.exec_()

    sys.exit(ret)


if __name__ == "__main__":
    main()
