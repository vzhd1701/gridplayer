from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from gridplayer.version import __app_bugtracker_url__


class ExceptionDialog(QDialog):
    def __init__(self, exc_txt, **kwargs):
        super().__init__(**kwargs)

        self.exc_txt = exc_txt

        self.setWindowTitle(self.tr("Unhandled Exception"))

        icon_size = 64

        self.pic = QIcon.fromTheme("close").pixmap(QSize(icon_size, icon_size))
        self.error_icon = QLabel(self)
        self.error_icon.setPixmap(self.pic)

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
        self.error_label = QLabel(exception_info, self)
        self.error_label.setTextFormat(Qt.RichText)
        self.error_label.setOpenExternalLinks(True)

        self.exception_box = QTextBrowser(self)
        self.exception_box.setMinimumSize(QSize(500, 200))
        self.exception_box.setMaximumHeight(200)
        self.exception_box.setText(exc_txt)

        self.copy_button = QPushButton(self.tr("Copy to Clipboard"), self)
        self.copy_button.setMinimumWidth(150)
        self.copy_button.clicked.connect(self.copy_text)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        self.buttons.rejected.connect(self.reject)

        self._ui_setup()

    def _ui_setup(self):
        error_row = QHBoxLayout()
        error_row.addWidget(self.error_icon)
        error_row.addWidget(self.error_label, 1)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.copy_button)
        buttons_row.addWidget(self.buttons)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        layout.addLayout(error_row)
        layout.addWidget(self.exception_box)
        layout.addLayout(buttons_row)

    def copy_text(self):
        QApplication.clipboard().setText(self.exc_txt)
