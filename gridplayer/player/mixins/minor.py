from PyQt5.QtCore import QEvent

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.settings import Settings
from gridplayer.utils import log_config


class PlayerMinorMixin(object):
    def get_current_cursor_pos(self):
        return self.mapFromGlobal(self.cursor().pos())

    def error(self, message):
        QCustomMessageBox.critical(self, "Error", message)

    @staticmethod
    def set_log_level(log_level):
        log_config.set_root_level(log_level)
