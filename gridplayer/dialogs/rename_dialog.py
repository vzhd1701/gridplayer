from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from gridplayer.utils.qt import translate
from gridplayer.widgets.color_palette import QColorPalette


class QVideoRenameDialog(QtWidgets.QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.original_title = ""

        self.title = QtWidgets.QLineEdit(self)

        self.title_reset_button = QtWidgets.QPushButton(
            translate("Dialog - Rename video", "Reset"), self
        )
        self.title_reset_button.clicked.connect(self.reset_title)

        self.palette = QColorPalette(parent=self)

        self.buttons = self.init_buttons()

        self.ui_setup()

    def init_buttons(self):
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        return buttons

    def ui_setup(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        input_line = QtWidgets.QHBoxLayout()
        input_line.addWidget(self.title)
        input_line.addWidget(self.title_reset_button)

        main_layout.addLayout(input_line)
        main_layout.addWidget(self.palette)
        main_layout.addWidget(self.buttons)

    def reset_title(self):
        self.title.setText(self.original_title)

    @classmethod
    def get_edits(
        cls,
        parent,
        title: str,
        orig_title: str,
        cur_title: str,
        cur_color: tuple[int, int, int],
    ):
        dialog = cls(parent=parent)
        dialog.setWindowTitle(title)

        dialog.original_title = orig_title
        dialog.title.setText(cur_title)
        dialog.palette.color = cur_color

        if dialog.exec():
            new_title = dialog.title.text().strip() or cur_title
            new_color = dialog.palette.color.name(QColor.HexRgb)
            return new_title, new_color

        return None
