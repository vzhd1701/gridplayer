from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLayout, QSpinBox, QVBoxLayout


class QCustomSpinboxInput(QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.spinbox = QSpinBox(self)
        self.spinbox.setRange(0, 1000)
        self.spinbox.setSpecialValueText(self.tr("Auto"))

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        for btn in self.buttons.buttons():
            btn.setIcon(QIcon())

        main_layout = QVBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        main_layout.addWidget(self.spinbox)
        main_layout.addWidget(self.buttons)

    @classmethod
    def get_int(  # noqa: WPS211
        cls,
        parent,
        title,
        special_text=None,
        initial_value=0,
        _min=-2147483647,
        _max=2147483647,
        step=1,
    ):
        dialog = cls(parent=parent)
        dialog.setWindowTitle(title)
        dialog.spinbox.setRange(_min, _max)
        dialog.spinbox.setValue(initial_value)
        dialog.spinbox.setSingleStep(step)

        if special_text:
            dialog.spinbox.setSpecialValueText(special_text)

        if dialog.exec():
            return dialog.spinbox.value()

        return initial_value
