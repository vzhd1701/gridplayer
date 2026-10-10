"""Asked before a linked list is kept whole in the playlist from now on: what
that means, and for a long list, what it does to the playlist's file."""

from PyQt5.QtCore import QLocale, QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from gridplayer.dialogs.add_choice import bold, warning_box
from gridplayer.utils.qt import translate

# a playlist file is a few kilobytes; a list that would make it this much
# bigger is warned of, saving and opening it taking a while from then on
BIG_LIST_BYTES = 1024 * 1024

ICON_PX = 32


class UnlinkListDialog(QDialog):
    def __init__(self, name: str, saved_bytes: int, parent=None):
        super().__init__(parent)

        self.setWindowTitle(translate("Dialog - List", "Unlink", "Header"))
        self.setMinimumWidth(420)

        icon = QLabel()
        icon.setPixmap(QIcon.fromTheme("question").pixmap(QSize(ICON_PX, ICON_PX)))
        icon.setAlignment(Qt.AlignTop)

        if name:
            question_txt = translate(
                "Dialog - List", "Unlink the list “{NAME}”?"
            ).format(NAME=name)
        else:
            question_txt = translate("Dialog - List", "Unlink the list?")

        question = QLabel(question_txt)
        question.setWordWrap(True)
        bold(question)

        about = QLabel(
            translate(
                "Dialog - List",
                "The list is saved in the playlist as it is now and no longer updates"
                " from its source.",
            )
        )
        about.setWordWrap(True)

        words = QVBoxLayout()
        words.setSpacing(6)
        words.addWidget(question)
        words.addWidget(about)

        self.is_warned = saved_bytes >= BIG_LIST_BYTES

        if self.is_warned:
            words.addSpacing(4)
            words.addWidget(warning_box(big_list_txt(saved_bytes)))

        buttons = QDialogButtonBox()
        unlink_button = buttons.addButton(
            translate("Dialog - List", "Unlink"), QDialogButtonBox.AcceptRole
        )
        cancel_button = buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        for button in buttons.buttons():
            button.setAutoDefault(False)

        # what the warning is about not done by Enter alone
        (cancel_button if self.is_warned else unlink_button).setDefault(True)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(icon)
        top.addLayout(words, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        root.addLayout(top)
        root.addWidget(buttons)

    @classmethod
    def ask(cls, name: str, saved_bytes: int, parent=None) -> bool:
        """Whether the list is unlinked, saved_bytes being about how much it
        adds to the playlist's file then."""

        dialog = cls(name, saved_bytes, parent)

        is_unlinked = dialog.exec_() == QDialog.Accepted

        dialog.deleteLater()

        return is_unlinked


def big_list_txt(saved_bytes: int) -> str:
    size = QLocale().toString(saved_bytes / (1024 * 1024), "f", 1)

    return translate(
        "Dialog - List",
        "This adds about {SIZE} MB to the playlist file, so it will open and save"
        " slower.",
    ).format(SIZE=size)
