from PyQt5.QtCore import pyqtSlot

from gridplayer.dialogs.about import AboutDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.misc import tr


class DialogsManager(ManagerBase):
    @property
    def commands(self):
        return {"about": lambda: AboutDialog(self.parent()).exec_()}

    @pyqtSlot(str)
    def error(self, message):
        QCustomMessageBox.critical(self.parent(), tr("Error"), message)
