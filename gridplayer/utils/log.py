import logging
import multiprocessing
import os
import platform
import pprint
import sys

from PyQt5 import Qt
from PyQt5.QtWidgets import QStyleFactory

from gridplayer import params_env
from gridplayer.version import __display_name__, __version__


def log_environment():
    log = logging.getLogger("MAIN")

    log.info(f"{__display_name__} v.{__version__} starting")

    if log.getEffectiveLevel() != logging.DEBUG:
        return

    pretty_environment = pprint.pformat(dict(os.environ))[1:-1]

    env_log = [
        "Environment info",
        "========",
        f"OS: {platform.platform()}",
        f"OS Ver: {platform.version()}",
        f"Python: {platform.python_version()}",
        f"Qt: {Qt.qVersion()}",
        f"MP Start method: {multiprocessing.get_start_method()}",
        f"is_pyinstaller_frozen: {params_env.IS_PYINSTALLER}",
        f"_MEIPASS: {sys._MEIPASS}"  # noqa: WPS437
        if params_env.IS_PYINSTALLER
        else "",
        f"is_flatpak: {params_env.IS_FLATPAK}",
        f"is_snap: {params_env.IS_SNAP}",
        f"is_appimage: {params_env.IS_APPIMAGE}",
        f"sys.argv: {sys.argv}",
        f"sys.executable: {sys.executable}",
        f"os.getcwd: {os.getcwd()}",
        f"QT Styles: {QStyleFactory.keys()}",
        "========",
        f"ENV\n {pretty_environment}",
        "========",
    ]

    for e in filter(None, env_log):
        log.debug(e)
