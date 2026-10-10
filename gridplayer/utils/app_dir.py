import os
import sys
from pathlib import Path

from PyQt5.QtCore import QStandardPaths

from gridplayer.params import env

PORTABLE_APP_DIR = "portable_data"

# the cache in the data folder, where that is the one used
CACHE_DIR_NAME = "cache"

ENV_USER_DATA_DIR = "GP_USER_DATA_DIR"


def is_portable() -> bool:
    if not (env.IS_WINDOWS and env.IS_PYINSTALLER):
        return False

    portable_data_dir = Path(sys.executable).parent / PORTABLE_APP_DIR

    return portable_data_dir.is_dir()


def get_user_data_dir_override() -> Path | None:
    value = os.environ.get(ENV_USER_DATA_DIR, "").strip()

    if not value:
        return None

    app_dir = Path(value).expanduser()

    if not app_dir.is_absolute():
        app_dir = Path.cwd() / app_dir

    return app_dir


def get_app_data_dir() -> Path:
    user_data_dir = get_user_data_dir_override()

    if user_data_dir is not None:
        user_data_dir.mkdir(parents=True, exist_ok=True)

        return user_data_dir

    if is_portable():
        return Path(sys.executable).parent / PORTABLE_APP_DIR

    app_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))

    if not app_dir.is_dir():
        app_dir.mkdir(parents=True)

    return app_dir


def get_app_cache_dir() -> Path:
    """Where what is kept to save downloading it again goes: the system's
    folder for caches, which backups and roaming profiles leave out, or in
    the data folder when that was moved or the app is portable, so that
    nothing is written anywhere else."""

    if get_user_data_dir_override() is not None or is_portable():
        return get_app_data_dir() / CACHE_DIR_NAME

    cache_dir = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)

    if not cache_dir:
        return get_app_data_dir() / CACHE_DIR_NAME

    return Path(cache_dir)
