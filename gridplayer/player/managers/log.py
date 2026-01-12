from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils import log_config


class LogManager(ManagerBase):
    @staticmethod
    def set_log_level(log_level):
        log_config.set_root_level(log_level)
