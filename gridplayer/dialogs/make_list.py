"""Asked before a cell that plays one video is made to play a list: a cell on
a list goes along the list rather than through the folder, so it is made
one on purpose, never by opening the List window by the way."""

from enum import Enum, auto
from pathlib import Path
from typing import NamedTuple

from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from gridplayer.dialogs.add_choice import bold, indented
from gridplayer.dialogs.messagebox import TEXT_SCALE
from gridplayer.utils.qt import fit_height, translate
from gridplayer.widgets.elided_label import ElidedLabel


class MakeFrom(Enum):
    VIDEO = auto()
    FOLDER = auto()


class MakeListChoice(NamedTuple):
    make_from: MakeFrom
    # for a list of the folder, its subfolders' files as well
    is_recursive: bool = False


class MakeListDialog(QDialog):
    def __init__(self, folder: Path | None, is_recursive: bool, parent=None):
        """folder is the one the video is in, None for a link, which has
        none to make a list of; is_recursive is how the box for its
        subfolders starts."""

        super().__init__(parent)

        self.setWindowTitle(translate("Dialog - Make list", "Make a List", "Header"))

        question = QLabel(
            translate("Dialog - Make list", "Make this cell play a list?")
        )
        bold(question)
        font = question.font()
        font.setPointSizeF(font.pointSizeF() * TEXT_SCALE)
        question.setFont(font)

        about = QLabel(
            translate(
                "Dialog - Make list",
                "Next and Previous will go through the list instead of the"
                " folder. You can edit the list.",
            )
        )
        about.setWordWrap(True)

        self._video_choice = QRadioButton(
            translate("Dialog - Make list", "Just this video")
        )
        self._folder_choice = QRadioButton(
            translate("Dialog - Make list", "Everything in its folder")
        )
        self._recursive_box = QCheckBox(
            translate("Dialog - Make list", "Include subfolders")
        )
        self._recursive_box.setChecked(is_recursive)

        # the folder in a box of the colours of a field, as a path is
        folder_label = ElidedLabel("" if folder is None else str(folder))
        folder_label.setObjectName("makeListFolder")
        folder_label.setStyleSheet(
            "#makeListFolder { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 4px;"
            " padding: 3px 7px }"
        )

        self._choices = QButtonGroup(self)
        self._choices.addButton(self._video_choice)
        self._choices.addButton(self._folder_choice)

        buttons = QDialogButtonBox()
        self._make_button = buttons.addButton(
            translate("Dialog - Make list", "Make List"), QDialogButtonBox.AcceptRole
        )
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        for button in buttons.buttons():
            button.setAutoDefault(False)
        self._make_button.setDefault(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        root.addWidget(question)
        root.addWidget(about)

        # a link has no folder: the one choice there is needs no asking
        if folder is not None:
            root.addSpacing(4)
            root.addWidget(self._video_choice)
            root.addWidget(self._folder_choice)
            root.addLayout(indented(folder_label))
            root.addLayout(indented(self._recursive_box))

            # the folder, as dropping it would make
            self._folder_choice.setChecked(True)
        else:
            self._video_choice.setChecked(True)

        root.addSpacing(6)
        root.addWidget(buttons)

        # once in the dialog: taken into it, a button is given its font
        bold(self._make_button)

        self._folder_choice.toggled.connect(self._recursive_box.setEnabled)
        self._recursive_box.setEnabled(self._folder_choice.isChecked())

        self.setMinimumWidth(420)

        self._make_button.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        fit_height(self)

    def choice(self) -> MakeListChoice:
        if self._folder_choice.isChecked():
            return MakeListChoice(MakeFrom.FOLDER, self._recursive_box.isChecked())

        return MakeListChoice(MakeFrom.VIDEO)

    @classmethod
    def ask(cls, folder, is_recursive, parent=None) -> MakeListChoice | None:
        dialog = cls(folder, is_recursive, parent=parent)

        is_made = dialog.exec_() == QDialog.Accepted
        choice = dialog.choice()

        dialog.deleteLater()

        return choice if is_made else None
