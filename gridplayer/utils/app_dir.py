import os
import platform
import sys

from PyQt5.QtCore import QStandardPaths

PORTABLE_APP_DIR = "portable_data"


def is_portable():
    if platform.system() != "Windows":
        return False

    portable_data_dir = os.path.join(os.path.dirname(sys.executable), PORTABLE_APP_DIR)

    return os.path.isdir(portable_data_dir)


def get_app_data_dir():
    if is_portable():
        return os.path.join(os.path.dirname(sys.executable), PORTABLE_APP_DIR)

    app_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)

    if not os.path.isdir(app_dir):
        os.makedirs(app_dir)

    return app_dir
