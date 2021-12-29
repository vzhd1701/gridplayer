from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QDialog

from gridplayer.dialogs.exception_dialog_ui import Ui_ExceptionDialog
from gridplayer.version import __app_bugtracker_url__


class ExceptionDialog(QDialog, Ui_ExceptionDialog):
    def __init__(self, exc_txt, **kwargs):
        super().__init__(**kwargs)

        self.exc_txt = exc_txt

        self.setupUi(self)

        icon_size = 64

        self.pic = QIcon.fromTheme("close").pixmap(QSize(icon_size, icon_size))
        self.errorIcon.setPixmap(self.pic)

        self.exceptionBox.setText(exc_txt)

        exception_info = [
            self.tr("<p><b>Program terminated due to unhandled exception!</b></p>"),
            self.tr(
                "<p>Please consider sending a bug report to the"
                ' <a href="{APP_BUGTRACKER_URL}">bug tracker</a>.</p>'
            ),
        ]
        exception_info = "".join(exception_info).replace(
            "{APP_BUGTRACKER_URL}", __app_bugtracker_url__
        )
        self.errorLabel.setText(exception_info)

        self.copyButton.clicked.connect(self.copy_text)

        for btn in self.buttonBox.buttons():
            btn.setIcon(QIcon())

    def copy_text(self):
        QApplication.clipboard().setText(self.exc_txt)
