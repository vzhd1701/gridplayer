from PyQt5.QtCore import pyqtSlot

from gridplayer.dialogs.about import AboutDialog
from gridplayer.dialogs.add_choice import show_failed
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import translate


class DialogsManager(ManagerBase):
    @property
    def commands(self):
        return {
            "about": self.about,
            "warning": self.warning,
        }

    def about(self):
        dialog = AboutDialog(self.parent())
        dialog.exec_()
        dialog.deleteLater()

    @pyqtSlot(str)
    def error(self, message):
        QCustomMessageBox.critical(self.parent(), translate("Dialog", "Error"), message)

    @pyqtSlot(str)
    def warning(self, message):
        QCustomMessageBox.warning(
            self.parent(), translate("Dialog", "Warning"), message
        )

    @pyqtSlot(object, bool)
    def failed(self, failed, is_nothing_added):
        show_failed(failed, is_nothing_added, self.parent())
