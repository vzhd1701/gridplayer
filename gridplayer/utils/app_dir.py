import platform
import sys
from pathlib import Path

from PyQt5.QtCore import QStandardPaths

PORTABLE_APP_DIR = "portable_data"


def is_portable() -> bool:
    if platform.system() != "Windows":
        return False

    portable_data_dir = Path(sys.executable).parent / PORTABLE_APP_DIR

    return portable_data_dir.is_dir()


def get_app_data_dir() -> Path:
    if is_portable():
        return Path(sys.executable).parent / PORTABLE_APP_DIR

    app_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))

    if not app_dir.is_dir():
        app_dir.mkdir(parents=True)

    return app_dir
