import logging
import multiprocessing
import os
import platform
import pprint
import sys

from PyQt5 import Qt
from PyQt5.QtWidgets import QStyleFactory

from gridplayer import params_env


def log_environment():
    from gridplayer.settings import settings

    log = logging.getLogger("MAIN")

    if log.getEffectiveLevel() != logging.DEBUG:
        return

    log.debug(f"Environment info")
    log.debug(f"========")
    log.debug(f"OS: {platform.platform()}")
    log.debug(f"OS Ver: {platform.version()}")
    log.debug(f"Python: {platform.python_version()}")
    log.debug(f"Qt: {Qt.qVersion()}")
    log.debug(f"MP Start method: {multiprocessing.get_start_method()}")
    log.debug(f"is_pyinstaller_frozen: {params_env.IS_PYINSTALLER}")
    if params_env.IS_PYINSTALLER:
        log.debug(f"_MEIPASS: {sys._MEIPASS}")
    log.debug(f"is_flatpak: {params_env.IS_FLATPAK}")
    log.debug(f"is_snap: {params_env.IS_SNAP}")
    log.debug(f"is_appimage: {params_env.IS_APPIMAGE}")
    log.debug(f"sys.argv: {sys.argv}")
    log.debug(f"sys.executable: {sys.executable}")
    log.debug(f"os.getcwd: {os.getcwd()}")
    log.debug(f"QT Styles: {QStyleFactory.keys()}")
    log.debug(f"Settings path: {settings.settings.fileName()}")
    log.debug(f"========")
    log.debug("ENV\n {0}".format(pprint.pformat(dict(os.environ))[1:-1]))
    log.debug(f"========")
