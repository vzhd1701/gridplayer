from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from gridplayer.params.subtitle_encodings import DEFAULT_ENCODING, SUBTITLE_ENCODINGS
from gridplayer.utils.qt import translate
from gridplayer.widgets.combo_box import cap_popup_height


def subtitle_encoding_choices() -> dict:
    """Every set a subtitle file can be read as, leaving it alone first."""

    return {
        DEFAULT_ENCODING: translate("Subtitle Encoding", "Default"),
        **SUBTITLE_ENCODINGS,
    }


class SetSubtitleEncodingDialog(QDialog):
    """What a video's subtitle files are read as, where they are not UTF-8.

    Forty-odd character sets is a list to scroll rather than a column to
    walk, so it is a box here rather than a submenu of its own. Nothing is
    applied while it is open either: the set is settled when the input
    opens, so every change reopens the video, and that is worth doing once
    on the way out rather than on every step through the list.
    """

    def __init__(self, encoding=DEFAULT_ENCODING, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            translate(
                "Dialog - Set subtitle encoding", "Set subtitle encoding", "Header"
            )
        )
        self.setModal(True)

        choices = subtitle_encoding_choices()

        self.combo = QComboBox(self)
        for value, name in choices.items():
            self.combo.addItem(name, value)
        cap_popup_height(self.combo, len(choices))
        self.combo.setCurrentIndex(max(self.combo.findData(encoding), 0))

        # a fallback rather than an override, and worth saying so here:
        # a pick that appears to do nothing was a file VLC already read as
        # UTF-8, which is a different problem than the wrong character set
        hint = QLabel(
            translate(
                "Dialog - Set subtitle encoding",
                "Only used when the file is not UTF-8",
            ),
            self,
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(self.combo)
        root.addWidget(hint)
        root.addWidget(buttons)

        self.setFixedSize(self.sizeHint())

    @classmethod
    def get_encoding(cls, encoding=DEFAULT_ENCODING, parent=None) -> str | None:
        """The set that was picked, or None where the dialog was dismissed."""

        dialog = cls(encoding=encoding, parent=parent)

        return dialog.combo.currentData() if dialog.exec_() else None
