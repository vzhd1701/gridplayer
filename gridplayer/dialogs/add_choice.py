"""Asked how what is being added goes into the grid: what is being added, and
the ways there are to put it into cells, the first of them picked before it
is. A way that adds many cells is warned of under it.

What has to be read first -- a folder, a list file, a link to a list -- may
take a while: the dialog comes up as it is read, saying how far it has got,
with Stop to go on with what is found by then, and asks once it is read."""

from typing import Any, NamedTuple

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPalette
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.utils.qt import count_txt, translate
from gridplayer.widgets.elided_label import ElidedLabel

# how far a choice's line about it is set in, under the choice
INDENT_PX = 24

# how many of the things being added are named
WHAT_LISTED = 4

# the warning sign under an option, and in the warning of its own
WARNING_ICON_PX = 16
WARNING_DIALOG_ICON_PX = 32


class AddOption(NamedTuple):
    # what is handed back for it, picked
    data: Any
    title: str
    # a line under it, of what it does
    about: str = ""
    # at the end of its line: how many cells it takes
    note: str = ""
    # a line under it, of what may go wrong where it is picked
    warning: str = ""


class AddChoiceDialog(QDialog):
    # Stop pressed as what is being added is read: for the reading to end
    # with what it has found by then
    stop_asked = pyqtSignal()

    def __init__(
        self,
        question: str,
        what: list[str],
        options: list,
        parent=None,
    ):
        """what are the things being added, by name; an option of None
        puts a line between the ones before it and after it. The first
        option is picked to start with."""

        super().__init__(parent)

        self.setWindowTitle(translate("Adding", "Add", "Header"))

        self._question_label = QLabel()
        self._question_label.setWordWrap(True)
        bold(self._question_label)

        self._what = QWidget()

        self._reading = _ReadingLine()
        self._reading.stop_button.clicked.connect(self._stop)

        self._choices = QButtonGroup(self)
        self._options: dict[QRadioButton, AddOption] = {}
        self._options_box = QWidget()

        buttons = QDialogButtonBox()
        self._add_button = buttons.addButton(
            translate("Adding", "Add"), QDialogButtonBox.AcceptRole
        )
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Enter adds once there is something to add, and never does
        # anything else: not Cancel or Stop, by having been tabbed to
        for button in (*buttons.buttons(), self._reading.stop_button):
            button.setAutoDefault(False)
        self._add_button.setDefault(True)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 16, 16, 16)
        self._root.setSpacing(10)
        self._root.addWidget(self._question_label)
        self._root.addWidget(self._what)
        self._root.addWidget(self._reading)
        self._root.addSpacing(4)
        self._root.addWidget(self._options_box)
        self._root.addSpacing(6)
        self._root.addWidget(buttons)

        self.setMinimumWidth(460)

        self._is_reading = False
        self._is_stopped = False

        self.set_question(question, what, options)

    @property
    def is_reading(self) -> bool:
        return self._is_reading

    def set_question(self, question: str, what: list[str], options: list) -> None:
        """What is asked, of what, and the ways to answer it, as when made:
        asked once what is being added is read. Stopped before it was all
        read, it says so."""

        self._is_reading = False

        self._question_label.setText(question)
        self._show_what(what)
        self._show_options(options)

        self._reading.setVisible(self._is_stopped)
        self._reading.show_stopped()

        self._add_button.setVisible(True)
        self._add_button.setEnabled(bool(self._options))
        self._add_button.setFocus()

        self._fit()

    def start_reading(self, is_asked: bool) -> None:
        """What is being added read first: how far it has got said, with
        Stop. Add is there to be pressed once it is read, where something is
        to be asked then; otherwise there is nothing to add it with."""

        self._is_reading = True

        self._show_options([])

        self._reading.show_reading()
        self._reading.show()

        self._add_button.setVisible(is_asked)
        self._add_button.setEnabled(False)

        self._fit()

    def tell_reading(self, text: str, percent: int = 0) -> None:
        """How far reading has got: in percent where that is known, or under
        way where it is not."""

        if self._is_reading and not self._is_stopped:
            self._reading.tell(text, percent)

    def choice(self) -> Any:
        button = self._choices.checkedButton()

        return None if button is None else self._options[button].data

    @classmethod
    def ask(cls, question, what, options, parent=None) -> Any:
        """The data of the option picked; None for none, the viewer thinking
        better of it."""

        dialog = cls(question, what, options, parent=parent)

        is_picked = dialog.exec_() == QDialog.Accepted
        choice = dialog.choice()

        dialog.deleteLater()

        return choice if is_picked else None

    @classmethod
    def reading(cls, question, what, is_asked, parent=None) -> "AddChoiceDialog":
        """A dialog saying how far what is being added is read, as it is;
        set_question asks about it once it is."""

        dialog = cls(question, what, [], parent=parent)
        dialog.start_reading(is_asked)

        return dialog

    def _stop(self):
        self._is_stopped = True
        self._reading.show_stopping()
        self.stop_asked.emit()

    def _show_what(self, what: list[str]) -> None:
        self._what = self._replaced(self._what, _what_lines(what))
        self._what.setVisible(bool(what))

    def _show_options(self, options: list) -> None:
        for button in self._choices.buttons():
            self._choices.removeButton(button)
        self._options = {}

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        for option in options:
            if option is None:
                layout.addWidget(_separator())
                continue

            button = QRadioButton(option.title)
            self._choices.addButton(button)
            self._options[button] = option

            layout.addLayout(_option_lines(button, option))

        self._options_box = self._replaced(self._options_box, box)
        self._options_box.setVisible(bool(options))

        first = next(iter(self._options), None)
        if first is not None:
            first.setChecked(True)

    def _replaced(self, old: QWidget, new: QWidget) -> QWidget:
        self._root.replaceWidget(old, new)

        # out of the dialog at once, not once it is deleted
        old.setParent(None)
        old.deleteLater()

        return new

    def _fit(self) -> None:
        if self.isVisible():
            self._root.activate()
            self.adjustSize()


class _ReadingLine(QWidget):
    """How far what is being added is read: what is being done, a bar and
    Stop; or that it was stopped."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._label = ElidedLabel()

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setMaximumHeight(8)

        self.stop_button = QPushButton(translate("Adding", "Stop"))
        self.stop_button.setToolTip(
            translate("Adding", "Stop and add what was found so far")
        )

        bar_line = QHBoxLayout()
        bar_line.setSpacing(8)
        bar_line.addWidget(self._bar, 1)
        bar_line.addWidget(self.stop_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._label)
        layout.addLayout(bar_line)

    def show_reading(self):
        self.tell(translate("Adding", "Reading…"))
        self._bar.show()
        self.stop_button.show()
        self.stop_button.setEnabled(True)

    def show_stopping(self):
        self._label.setText(translate("Adding", "Stopping…"))
        self.stop_button.setEnabled(False)

    def show_stopped(self):
        self._label.setText(
            translate("Adding", "Stopped. Only what was found so far will be added.")
        )
        self._bar.hide()
        self.stop_button.hide()

    def tell(self, text: str, percent: int = 0):
        self._label.setText(text)

        if percent:
            self._bar.setRange(0, 100)
            self._bar.setValue(percent)
        else:
            self._bar.setRange(0, 0)


def _what_lines(what: list[str]) -> QWidget:
    lines = []

    for name in what[:WHAT_LISTED]:
        # the whole name in its tooltip, cut short as it may be
        line = ElidedLabel()
        line.setText(name)
        lines.append(line)

    if len(what) > WHAT_LISTED:
        lines.append(
            QLabel(
                translate("Adding", "and {COUNT} more").format(
                    COUNT=count_txt(len(what) - WHAT_LISTED)
                )
            )
        )

    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    for line in lines:
        dimmed(line)
        layout.addWidget(line)

    return box


def _option_lines(button: QRadioButton, option: AddOption) -> QVBoxLayout:
    title_line = QHBoxLayout()
    title_line.addWidget(button)
    title_line.addStretch(1)

    if option.note:
        note = QLabel(option.note)
        dimmed(note)
        title_line.addWidget(note)

    layout = QVBoxLayout()
    layout.setSpacing(4)
    layout.addLayout(title_line)

    if option.about:
        about = QLabel(option.about)
        about.setWordWrap(True)
        dimmed(about)
        layout.addLayout(indented(about))

    if option.warning:
        layout.addLayout(indented(warning_box(option.warning)))

    return layout


def indented(widget: QWidget) -> QHBoxLayout:
    line = QHBoxLayout()
    line.setContentsMargins(INDENT_PX, 0, 0, 0)
    line.addWidget(widget, 1)
    return line


def warning_box(text: str) -> QFrame:
    """What may go wrong where an option is picked: the warning sign and the
    words in bold, in a box of the colours of a field."""

    box = QFrame()
    box.setObjectName("addWarning")
    box.setStyleSheet(
        "#addWarning { background: palette(base); border: 1px solid palette(mid);"
        " border-radius: 4px }"
    )

    icon = QLabel()
    icon.setPixmap(
        QIcon.fromTheme("warning").pixmap(QSize(WARNING_ICON_PX, WARNING_ICON_PX))
    )
    icon.setAlignment(Qt.AlignTop)

    label = QLabel(text)
    label.setWordWrap(True)
    bold(label)

    layout = QHBoxLayout(box)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(8)
    layout.addWidget(icon)
    layout.addWidget(label, 1)

    return box


def many_cells_txt(count: int) -> str:
    return translate("Adding", "{COUNT} cells at once can freeze the player.").format(
        COUNT=count_txt(count)
    )


class ManyCellsDialog(QDialog):
    """A warning before adding many cells at once, where how is settled
    already: added, or not, and nothing else to pick."""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)

        self.setWindowTitle(translate("Adding", "Add", "Header"))
        self.setMinimumWidth(420)

        icon = QLabel()
        icon.setPixmap(
            QIcon.fromTheme("warning").pixmap(
                QSize(WARNING_DIALOG_ICON_PX, WARNING_DIALOG_ICON_PX)
            )
        )
        icon.setAlignment(Qt.AlignTop)

        question = QLabel(
            translate("Adding", "Add {COUNT} cells?").format(COUNT=count_txt(count))
        )
        bold(question)

        warning = QLabel(many_cells_txt(count))
        warning.setWordWrap(True)

        self._again = QCheckBox(translate("Adding", "Don't warn again"))

        buttons = QDialogButtonBox()
        add_button = buttons.addButton(
            translate("Adding", "Add"), QDialogButtonBox.AcceptRole
        )
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        for button in buttons.buttons():
            button.setAutoDefault(False)
        add_button.setDefault(True)

        words = QVBoxLayout()
        words.setSpacing(6)
        words.addWidget(question)
        words.addWidget(warning)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(icon)
        top.addLayout(words, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(self._again)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        root.addLayout(top)
        root.addLayout(bottom)

    @property
    def is_warned_again(self) -> bool:
        return not self._again.isChecked()

    @classmethod
    def ask(cls, count: int, parent=None) -> tuple[bool, bool]:
        """Whether the cells are added, and whether to be warned again."""

        dialog = cls(count, parent)

        is_added = dialog.exec_() == QDialog.Accepted
        is_warned_again = dialog.is_warned_again

        dialog.deleteLater()

        return is_added, is_warned_again


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)

    # the theme's gray between the window and its text: Sunken draws a
    # light edge that stands out on a dark window
    palette = line.palette()
    palette.setColor(QPalette.WindowText, palette.color(QPalette.Mid))
    line.setPalette(palette)

    return line


def bold(label: QLabel) -> None:
    font = label.font()
    font.setBold(True)
    label.setFont(font)


def dimmed(label: QLabel) -> None:
    palette = label.palette()
    palette.setColor(QPalette.WindowText, palette.color(QPalette.PlaceholderText))
    label.setPalette(palette)
