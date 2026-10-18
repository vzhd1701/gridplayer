"""Asked how what is being added goes into the grid: what is being added, and
the ways there are to put it into cells, a card each, the first of them
picked before it is. A way that adds many cells is warned of on its card.

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
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.messagebox import TEXT_SCALE, QCustomMessageBox
from gridplayer.params.theme import set_secondary
from gridplayer.utils.qt import bold, count_txt, fit_height, translate
from gridplayer.widgets.elided_label import ElidedLabel

# how far a choice's line about it is set in, under the choice
INDENT_PX = 24

# how narrow the dialog may get, its margins left out
MIN_WIDTH_PX = 428

# how many of the things being added are named
WHAT_LISTED = 4

# the sign of what kind of thing each thing being added is
ITEM_ICON_PX = 14

# the warning sign on an option's card
WARNING_ICON_PX = 16


class AddedItem(NamedTuple):
    """A thing being added, as it is listed: its name, the icon of what
    kind of thing it is, and how much is in it."""

    name: str
    # the icon's name; empty for none
    icon: str = ""
    # as "48 items"; empty for a thing that is one
    count: str = ""


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
        what: list,
        options: list,
        parent=None,
    ):
        """what are the things being added, as AddedItem or by name alone;
        an option of None puts a line between the ones before it and after
        it. The first option is picked to start with."""

        super().__init__(parent)

        self.setWindowTitle(translate("Adding", "Add", "Header"))

        self._question_label = QLabel()
        self._question_label.setWordWrap(True)
        bold(self._question_label)
        font = self._question_label.font()
        font.setPointSizeF(font.pointSizeF() * TEXT_SCALE)
        self._question_label.setFont(font)

        # on what it says rather than on the dialog: the dialog's own would
        # let it be narrower than what is in it, in a big font
        self._question_label.setMinimumWidth(MIN_WIDTH_PX)

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
        self._root.addSpacing(2)
        self._root.addWidget(self._options_box)
        self._root.addSpacing(6)
        self._root.addWidget(buttons)

        # once in the dialog: taken into it, a button is given its font
        bold(self._add_button)

        self._is_reading = False
        self._is_stopped = False

        self.set_question(question, what, options)

    @property
    def is_reading(self) -> bool:
        return self._is_reading

    def set_question(self, question: str, what: list, options: list) -> None:
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

    def _show_what(self, what: list) -> None:
        self._what = self._replaced(self._what, _what_lines(what))
        self._what.setVisible(bool(what))

    def _show_options(self, options: list) -> None:
        for button in self._choices.buttons():
            self._choices.removeButton(button)
        self._options = {}

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for option in options:
            if option is None:
                layout.addSpacing(2)
                layout.addWidget(_separator())
                layout.addSpacing(2)
                continue

            button = QRadioButton(option.title)
            self._choices.addButton(button)
            self._options[button] = option

            layout.addWidget(_OptionCard(button, option))

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

    def showEvent(self, event):
        super().showEvent(event)
        fit_height(self)

    def _fit(self) -> None:
        if self.isVisible():
            self._root.activate()
            self.adjustSize()
            fit_height(self)


class _OptionCard(QFrame):
    """An option in a box of its own, picked by a click anywhere on it: its
    radio button, how many cells it takes, what it does and what may go
    wrong. The one picked stands out in the colours of a field."""

    def __init__(self, button: QRadioButton, option: AddOption, parent=None):
        super().__init__(parent)

        self._button = button

        self.setObjectName("addOption")
        self.setStyleSheet(
            "#addOption { border: 1px solid palette(mid); border-radius: 5px;"
            " padding: 1px }"
            '#addOption[picked="true"] { background: palette(base);'
            " border: 2px solid palette(text); padding: 0px }"
        )

        bold(button)

        title_line = QHBoxLayout()
        title_line.addWidget(button)
        title_line.addStretch(1)

        if option.note:
            note = QLabel(option.note)
            set_secondary(note)
            title_line.addWidget(note)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 8)
        layout.setSpacing(3)
        layout.addLayout(title_line)

        if option.about:
            about = QLabel(option.about)
            about.setWordWrap(True)
            set_secondary(about)
            layout.addLayout(indented(about))

        if option.warning:
            layout.addSpacing(3)
            layout.addLayout(indented(warning_box(option.warning, is_boxed=False)))

        button.toggled.connect(self._show_picked)
        self._show_picked(button.isChecked())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._button.setChecked(True)
            self._button.setFocus(Qt.MouseFocusReason)

        super().mousePressEvent(event)

    def _show_picked(self, is_picked: bool) -> None:
        self.setProperty("picked", is_picked)

        # a property is matched by the style sheet only as it is polished
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


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
            translate("Adding", "Stopped. Only what was found will be added.")
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


def _what_lines(what: list) -> QWidget:
    """The things being added, a line each in a box of the colours of a
    field: what kind of thing, its name, and how much is in it."""

    box = QFrame()
    box.setObjectName("addWhat")
    box.setStyleSheet(
        "#addWhat { background: palette(base); border: 1px solid palette(mid);"
        " border-radius: 4px }"
    )

    layout = QVBoxLayout(box)
    layout.setContentsMargins(10, 6, 10, 6)
    layout.setSpacing(3)

    for item in what[:WHAT_LISTED]:
        layout.addLayout(_what_line(_as_item(item)))

    if len(what) > WHAT_LISTED:
        more = QLabel(
            translate("Adding", "and {COUNT} more").format(
                COUNT=count_txt(len(what) - WHAT_LISTED)
            )
        )
        set_secondary(more)
        layout.addWidget(more)

    return box


def _as_item(item) -> AddedItem:
    return item if isinstance(item, AddedItem) else AddedItem(item)


def _what_line(item: AddedItem) -> QHBoxLayout:
    line = QHBoxLayout()
    line.setSpacing(8)

    if item.icon:
        icon = QLabel()
        icon.setPixmap(
            QIcon.fromTheme(item.icon).pixmap(QSize(ITEM_ICON_PX, ITEM_ICON_PX))
        )
        line.addWidget(icon)

    # the whole name in its tooltip, cut short as it may be
    line.addWidget(ElidedLabel(item.name), 1)

    if item.count:
        count = QLabel(item.count)
        set_secondary(count)
        line.addWidget(count)

    return line


def indented(widget: QWidget) -> QHBoxLayout:
    line = QHBoxLayout()
    line.setContentsMargins(INDENT_PX, 0, 0, 0)
    line.addWidget(widget, 1)
    return line


def warning_box(text: str, is_boxed: bool = True) -> QFrame:
    """What may go wrong where an option is picked: the warning sign and the
    words in bold, in a box of the colours of a field, or on what is
    under it."""

    box = QFrame()
    box.setObjectName("addWarning")
    if is_boxed:
        box.setStyleSheet(
            "#addWarning { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 4px }"
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
    layout.setContentsMargins(*((10, 7, 10, 7) if is_boxed else (0, 0, 0, 0)))
    layout.setSpacing(8)
    layout.addWidget(icon)
    layout.addWidget(label, 1)

    return box


def many_cells_txt(count: int) -> str:
    return translate("Adding", "{COUNT} cells at once can freeze the player.").format(
        COUNT=count_txt(count)
    )


class ManyCellsDialog(QCustomMessageBox):
    """A warning before adding many cells at once, where how is settled
    already: added, or not, and nothing else to pick."""

    def __init__(self, count: int, parent=None):
        super().__init__(
            QMessageBox.Warning,
            translate("Adding", "Add", "Header"),
            translate("Adding", "Add {COUNT} cells?").format(COUNT=count_txt(count)),
            parent=parent,
        )

        self.setInformativeText(many_cells_txt(count))

        self._again = QCheckBox(translate("Adding", "Don't warn again"))
        self.setCheckBox(self._again)

        self.setDefaultButton(
            self.addButton(translate("Adding", "Add"), QMessageBox.AcceptRole)
        )
        self.addButton(QMessageBox.Cancel)

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


def show_failed(failed, is_nothing_added: bool, parent=None) -> None:
    """What could not be added, and why, as (where, why): the first few of
    them listed, all of them to copy. None at all said, where nothing that
    was dropped or opened could be played."""

    icon = QMessageBox.Critical if is_nothing_added else QMessageBox.Warning
    title = translate("Adding", "Add", "Header")

    if not failed:
        QCustomMessageBox.critical(
            parent,
            title,
            translate("Adding", "Nothing to add"),
            info=translate("Adding", "None of these are videos, audio or playlists."),
        )
        return

    if len(failed) == 1:
        text = translate("Adding", "Couldn't add 1 item")
    else:
        text = translate("Adding", "Couldn't add {COUNT} items").format(
            COUNT=count_txt(len(failed))
        )

    rows = list(failed[:FAILED_LISTED])
    if len(failed) > FAILED_LISTED:
        more = translate("Adding", "and {COUNT} more").format(
            COUNT=count_txt(len(failed) - FAILED_LISTED)
        )
        rows.append((more, ""))

    box = QCustomMessageBox(icon, title, text, QMessageBox.Ok, parent)
    box.set_list(rows)
    box.set_copy_text("\n".join(f"{where}\n    {why}" for where, why in failed))
    box.exec_()
    box.deleteLater()


# how many of the things that could not be added are listed
FAILED_LISTED = 5


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
