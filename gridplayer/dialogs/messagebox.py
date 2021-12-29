from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox


class QCustomMessageBox(QMessageBox):
    def __init__(
        self,
        icon,
        title,
        text,
        buttons=QMessageBox.NoButton,
        parent=None,
        f=Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint,
    ):
        super().__init__(icon, title, text, buttons, parent, f)

        for btn in self.buttons():
            btn.setIcon(QIcon())

        icons = {
            QMessageBox.Information: QIcon.fromTheme("information"),
            QMessageBox.Question: QIcon.fromTheme("question"),
            QMessageBox.Critical: QIcon.fromTheme("close"),
        }

        icon_size = 64

        self.setIconPixmap(icons[icon].pixmap(icon_size, icon_size))

    @classmethod
    def critical(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Ok,
        defaultButton=QMessageBox.NoButton,
    ):
        return cls(QMessageBox.Critical, title, text, buttons, parent).exec_()

    @classmethod
    def information(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Ok,
        defaultButton=QMessageBox.NoButton,
    ):
        return cls(QMessageBox.Information, title, text, buttons, parent).exec_()

    @classmethod
    def question(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Yes | QMessageBox.No,
        defaultButton=QMessageBox.NoButton,
    ):
        return cls(QMessageBox.Question, title, text, buttons, parent).exec_()

    @classmethod
    def warning(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Ok,
        defaultButton=QMessageBox.NoButton,
    ):
        return cls(QMessageBox.Warning, title, text, buttons, parent).exec_()
