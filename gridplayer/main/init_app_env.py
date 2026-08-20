import os

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
    if env.IS_LINUX:
        # Hardware video is drawn by VLC into an X11 window, not by Qt OpenGL.
        # If the xcb plugin loads libGL here, forked decoder processes inherit
        # a broken GLdispatch and abort on the second Hardware process:
        #   DispatchCurrentUnref: Assertion `dispatch->currentThreads >= 0'
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")

    if env.IS_WINDOWS:
        from PyQt5.QtWinExtras import QtWin

        QtWin.setCurrentProcessExplicitAppUserModelID(__app_id__)

    init_app_env_id()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
