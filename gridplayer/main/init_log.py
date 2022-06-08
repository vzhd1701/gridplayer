from PyQt5.QtCore import qInstallMessageHandler

from gridplayer.settings import Settings
from gridplayer.utils import log_config
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.version import __app_name__


def init_log():
    log_path = get_app_data_dir() / f"{__app_name__.lower()}.log"

    log_config.config_log(log_path, Settings().get("logging/log_level"))
    log_config.override_stdout()

    log_qt = log_config.QtLogHandler()
    qInstallMessageHandler(log_qt.handle)
