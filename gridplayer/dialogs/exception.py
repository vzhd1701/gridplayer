from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QDialog

from gridplayer.dialogs.exception_ui import Ui_ExceptionDialog
from gridplayer.resources import ICONS
from gridplayer.version import __app_bugtracker_url__


class ExceptionDialog(QDialog, Ui_ExceptionDialog):
    def __init__(self, exc_txt, parent=None):
        super().__init__(parent)

        self.exc_txt = exc_txt

        self.setupUi(self)

        self.pic = QIcon(ICONS["basic/031-cancel"]).pixmap(QSize(64, 64))
        self.errorIcon.setPixmap(self.pic)

        self.exceptionBox.setText(exc_txt)

        info = self.errorLabel.text()
        info = info.replace("{APP_BUGTRACKER_URL}", __app_bugtracker_url__)
        self.errorLabel.setText(info)

        self.copyButton.clicked.connect(self.copy_text)

        for btn in self.buttonBox.buttons():
            btn.setIcon(QIcon())

    def copy_text(self):
        QApplication.clipboard().setText(self.exc_txt)
