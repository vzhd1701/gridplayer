from PyQt5.QtCore import qInstallMessageHandler

from gridplayer.settings import Settings
from gridplayer.utils import log_config
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.version import __app_name__


def init_log():
    log_path = get_app_data_dir() / f"{__app_name__.lower()}.log"

    if Settings().get("logging/log_limit"):
        max_log_size = max(Settings().get("logging/log_limit_size"), 1) * 1024 * 1024
        max_log_backups = max(Settings().get("logging/log_limit_backups"), 1)
    else:
        max_log_size = None
        max_log_backups = None

    log_config.config_log(
        log_path=log_path,
        log_level=Settings().get("logging/log_level"),
        max_log_size=max_log_size,
        max_log_backups=max_log_backups,
    )

    log_qt = log_config.QtLogHandler()
    qInstallMessageHandler(log_qt.handle)
