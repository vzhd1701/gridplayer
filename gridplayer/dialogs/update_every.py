"""How often a linked list is read again, set by the viewer: every so many
minutes, hours or days."""

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from gridplayer.dialogs.add_choice import warning_box
from gridplayer.utils.list_update import SHORT_UPDATE_S
from gridplayer.utils.qt import translate

MINUTE_S = 60
HOUR_S = 60 * MINUTE_S
DAY_S = 24 * HOUR_S

MOST = 999


class UpdateEveryDialog(QDialog):
    def __init__(self, every_s: int, is_from_site: bool, parent=None):
        """every_s: how often it is read now, in seconds; is_from_site: it
        is read from a link, a site being asked each time."""

        super().__init__(parent)

        self.setWindowTitle(translate("Lists", "Update", "Header"))
        self.setMinimumWidth(380)

        self._is_from_site = is_from_site

        self._count = QSpinBox()
        self._count.setRange(1, MOST)

        self._unit = QComboBox()
        self._unit.addItem(translate("Lists", "minutes"), MINUTE_S)
        self._unit.addItem(translate("Lists", "hours"), HOUR_S)
        self._unit.addItem(translate("Lists", "days"), DAY_S)

        # in the largest unit it comes to a whole number of
        unit = next((unit for unit in (DAY_S, HOUR_S) if every_s % unit == 0), MINUTE_S)
        self._unit.setCurrentIndex(self._unit.findData(unit))
        self._count.setValue(max(1, min(MOST, every_s // unit)))

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(translate("Lists", "Every")))
        row.addWidget(self._count)
        row.addWidget(self._unit)
        row.addStretch(1)

        self._warning = warning_box(
            translate(
                "Lists",
                "Sites may block updates this frequent. Each update downloads the"
                " whole list.",
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(row)
        layout.addWidget(self._warning)
        layout.addWidget(buttons)

        self._count.valueChanged.connect(self._show_warning)
        self._unit.currentIndexChanged.connect(self._show_warning)
        self._show_warning()

    @property
    def every_s(self) -> int:
        return self._count.value() * self._unit.currentData()

    @property
    def is_warned(self) -> bool:
        return not self._warning.isHidden()

    def _show_warning(self, *_):
        self._warning.setHidden(
            not self._is_from_site or self.every_s >= SHORT_UPDATE_S
        )
        self.adjustSize()

    @classmethod
    def ask(cls, every_s: int, is_from_site: bool, parent=None) -> int | None:
        """How often it is to be read, in seconds; None for as it was."""

        dialog = cls(every_s, is_from_site, parent)

        is_set = dialog.exec_() == QDialog.Accepted
        every_s = dialog.every_s

        dialog.deleteLater()

        return every_s if is_set else None


def every_txt(every_s: int) -> str:
    """How often, as the menu says it: "Every 40 minutes"."""

    if every_s % DAY_S == 0:
        count = every_s // DAY_S
        if count == 1:
            return translate("Lists", "Every day")
        return translate("Lists", "Every {COUNT} days").format(COUNT=count)

    if every_s % HOUR_S == 0:
        count = every_s // HOUR_S
        if count == 1:
            return translate("Lists", "Every hour")
        return translate("Lists", "Every {COUNT} hours").format(COUNT=count)

    count = max(1, every_s // MINUTE_S)
    if count == 1:
        return translate("Lists", "Every minute")
    return translate("Lists", "Every {COUNT} minutes").format(COUNT=count)


def in_txt(seconds: float) -> str:
    """How long until something, "in 55 minutes"; "soon" for any moment."""

    seconds = int(seconds)

    if seconds < MINUTE_S:
        return translate("Lists", "soon")

    if seconds < HOUR_S:
        count = seconds // MINUTE_S
        if count == 1:
            return translate("Lists", "in 1 minute")
        return translate("Lists", "in {COUNT} minutes").format(COUNT=count)

    if seconds < DAY_S:
        count = seconds // HOUR_S
        if count == 1:
            return translate("Lists", "in 1 hour")
        return translate("Lists", "in {COUNT} hours").format(COUNT=count)

    count = seconds // DAY_S
    if count == 1:
        return translate("Lists", "in 1 day")
    return translate("Lists", "in {COUNT} days").format(COUNT=count)
