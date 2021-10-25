import atexit
import os
import sys

from PyQt5.QtCore import qInstallMessageHandler

from gridplayer.settings import Settings
from gridplayer.utils import log_config
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.single_instance import Listener, is_delegated_to_primary
from gridplayer.version import __app_name__


def init_log():
    log_path = os.path.join(get_app_data_dir(), f"{__app_name__.lower()}.log")

    log_config.config_log(log_path, Settings().get("logging/log_level"))
    log_config.override_stdout()

    log_qt = log_config.QtLogHandler()
    qInstallMessageHandler(log_qt.handle)


def exit_if_delegated():
    if Settings().get("player/one_instance") and is_delegated_to_primary(sys.argv):
        sys.exit(0)


def init_instance_listener():
    instance_listener = Listener()
    instance_listener.start()

    atexit.register(instance_listener.cleanup)

    return instance_listener
