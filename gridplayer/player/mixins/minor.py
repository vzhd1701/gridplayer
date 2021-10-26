from PyQt5.QtCore import QEvent

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.settings import Settings


class PlayerMinorMixin(object):
    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            pause_when_minimized = self.isMinimized() and Settings().get(
                "player/pause_minimized"
            )
            if pause_when_minimized:
                self.pause_all()

    def get_current_cursor_pos(self):
        return self.mapFromGlobal(self.cursor().pos())

    def error(self, message):
        QCustomMessageBox.critical(self, "Error", message)
