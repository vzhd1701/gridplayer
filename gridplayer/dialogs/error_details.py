"""Everything known of why a video would not play, or a list could not be
read: what it is, where it broke and its code, and the error itself as it
was raised, to copy into a bug report."""

from dataclasses import dataclass

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from gridplayer.dialogs.bookmarks import dialog_button
from gridplayer.utils.qt import translate
from gridplayer.widgets.error_tag import ErrorTag

ICON_PX = 32


@dataclass(frozen=True)
class ErrorDetails:
    title: str
    about: str = ""
    where: str = ""
    code: str = ""
    # what is known of it, a row each: (label, value)
    rows: tuple[tuple[str, str], ...] = ()
    raw: str = ""
    icon: str = "error"

    def as_text(self) -> str:
        """All of it, for the clipboard."""

        lines = [self.title]

        if self.about:
            lines.append(self.about)

        if self.where or self.code:
            lines.append(" · ".join(part for part in (self.where, self.code) if part))

        lines.append("")
        lines.extend(f"{label}: {value}" for label, value in self.rows)

        if self.raw:
            lines.extend(("", self.raw))

        return "\n".join(lines)


class ErrorDetailsDialog(QDialog):
    try_again = pyqtSignal()

    def __init__(self, details: ErrorDetails, parent=None):
        super().__init__(parent)

        self._details = details

        self.setWindowTitle(translate("Error Details", "Error Details"))
        self.setMinimumWidth(560)

        icon = QLabel()
        icon.setPixmap(QIcon.fromTheme(details.icon).pixmap(QSize(ICON_PX, ICON_PX)))
        icon.setAlignment(Qt.AlignTop)

        title = QLabel(details.title)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        title.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # its own from the start: shown with no parent, it is a window
        self.tag = ErrorTag(parent=self)
        self.tag.set_tag(details.where, details.code)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(title)
        title_row.addWidget(self.tag, 0, Qt.AlignVCenter)
        title_row.addStretch(1)

        words = QVBoxLayout()
        words.setSpacing(4)
        words.addLayout(title_row)

        if details.about:
            about = QLabel(details.about)
            about.setWordWrap(True)
            about.setForegroundRole(QPalette.PlaceholderText)
            words.addWidget(about)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(icon)
        header.addLayout(words, 1)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignLeft)

        for label, value in details.rows:
            name = QLabel(label)
            name.setForegroundRole(QPalette.PlaceholderText)

            shown = QLabel(value)
            shown.setTextInteractionFlags(Qt.TextSelectableByMouse)
            shown.setWordWrap(True)

            form.addRow(name, shown)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addLayout(form)

        if details.raw:
            raw_title = QLabel(translate("Error Details", "Technical details"))

            self.raw = QPlainTextEdit(details.raw)
            self.raw.setReadOnly(True)
            self.raw.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.raw.setMinimumHeight(140)

            layout.addWidget(raw_title)
            layout.addWidget(self.raw, 1)

        self.copy_button = dialog_button(None, translate("Error Details", "Copy"))
        self.copy_button.clicked.connect(self.copy)

        self.again_button = dialog_button(None, translate("Error Details", "Try Again"))
        self.again_button.clicked.connect(self._try_again)

        close_button = QPushButton(translate("Error Details", "Close"))
        close_button.setDefault(True)
        close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        buttons.addWidget(self.again_button)
        buttons.addWidget(close_button)

        layout.addLayout(buttons)

    def copy(self):
        QApplication.clipboard().setText(self._details.as_text())

    def _try_again(self):
        self.try_again.emit()
        self.accept()
