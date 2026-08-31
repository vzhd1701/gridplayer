from PyQt5.QtCore import Qt, QTime
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLayout,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
)

from gridplayer.utils.qt import translate


class QCustomSpinboxInput(QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.spinbox = QSpinBox(self)
        self.spinbox.setRange(0, 1000)

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
    def get_int(
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


class QFixedGridSizeDialog(QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setWindowTitle(
            translate("Dialog - Set grid size", "Set grid size", "Header")
        )

        self.rows = QSpinBox(self)
        self.rows.setRange(1, 100)
        self.cols = QSpinBox(self)
        self.cols.setRange(1, 100)
        self.preallocate = QCheckBox(
            translate("Grid Size", "Show all cells even when empty"), self
        )

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        for btn in self.buttons.buttons():
            btn.setIcon(QIcon())

        form = QFormLayout()
        form.addRow(self.tr("Rows"), self.rows)
        form.addRow(self.tr("Columns"), self.cols)
        form.addRow(self.preallocate)

        main_layout = QVBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        main_layout.addLayout(form)
        main_layout.addWidget(self.buttons)

    @classmethod
    def get_size(
        cls,
        parent,
        rows: int,
        cols: int,
        preallocate: bool,
        include_preallocate: bool,
    ) -> tuple[int, int, bool] | None:
        dialog = cls(parent=parent)
        dialog.rows.setValue(max(1, rows))
        dialog.cols.setValue(max(1, cols))
        dialog.preallocate.setChecked(preallocate)
        if not include_preallocate:
            dialog.preallocate.hide()

        if dialog.exec():
            return (
                dialog.rows.value(),
                dialog.cols.value(),
                dialog.preallocate.isChecked(),
            )

        return None


class QCustomSpinboxTimeInput(QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.timebox = QTimeEdit(self)
        self.timebox.setDisplayFormat("hh:mm:ss")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        for btn in self.buttons.buttons():
            btn.setIcon(QIcon())

        main_layout = QVBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        main_layout.addWidget(self.timebox)
        main_layout.addWidget(self.buttons)

    @classmethod
    def get_time_ms_int(cls, parent, title) -> int | None:
        dialog = cls(parent=parent)
        dialog.setWindowTitle(title)

        if dialog.exec():
            return abs(dialog.timebox.time().msecsTo(QTime(0, 0, 0)))

        return None
