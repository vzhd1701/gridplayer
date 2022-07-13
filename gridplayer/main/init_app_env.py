from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

from gridplayer.params import env
from gridplayer.version import (
    __app_id__,
    __app_name__,
    __author_name__,
    __display_name__,
    __version__,
)


def init_app_env_id():
    QApplication.setApplicationName(__app_name__)
    QApplication.setApplicationDisplayName(__display_name__)
    QApplication.setOrganizationName(__author_name__)
    QApplication.setApplicationVersion(__version__)


def init_app_env():
    if env.IS_WINDOWS:
        from PyQt5.QtWinExtras import QtWin  # noqa: WPS433

        QtWin.setCurrentProcessExplicitAppUserModelID(__app_id__)

    init_app_env_id()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
