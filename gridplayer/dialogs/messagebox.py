"""A question, warning, error or notice: the icon beside it, what it says in
bold, what it means under it in plain text, and buttons that say what they
do. Asked as QMessageBox is, so it takes its place wherever one was."""

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from gridplayer.params.theme import set_html_with_links
from gridplayer.utils.qt import translate

ICON_PX = 32

# the text grows a little above the rest, as a title would
TEXT_SCALE = 1.12

# how wide the words are let go before they wrap
TEXT_MIN_WIDTH_PX = 360
TEXT_MAX_WIDTH_PX = 520

_ICONS = {
    QMessageBox.Critical: "error",
    QMessageBox.Information: "information",
    QMessageBox.Question: "question",
    QMessageBox.Warning: "warning",
}

# the roles of buttons that answer yes
_YES_ROLES = (QMessageBox.AcceptRole, QMessageBox.YesRole)


class QCustomMessageBox(QDialog):
    def __init__(
        self,
        icon,
        title,
        text,
        buttons=QMessageBox.NoButton,
        parent=None,
        f=Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint,
    ):
        super().__init__(parent, f)

        self.setWindowTitle(title)

        self._clicked: QAbstractButton | None = None
        self._default: QAbstractButton | None = None
        self._copied = ""

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignTop)
        if icon in _ICONS:
            self._icon.setPixmap(
                QIcon.fromTheme(_ICONS[icon]).pixmap(QSize(ICON_PX, ICON_PX))
            )
        self._icon.setVisible(icon in _ICONS)

        self._text = _words_label()
        font = self._text.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * TEXT_SCALE)
        self._text.setFont(font)
        self.setText(text)

        self._info = _words_label()
        self._info.hide()

        self._list = QFrame()
        self._list.setObjectName("messageList")
        self._list.setStyleSheet(
            "#messageList { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 4px }"
        )
        self._list.hide()

        self._words = QVBoxLayout()
        self._words.setSpacing(6)
        self._words.addWidget(self._text)
        self._words.addWidget(self._info)
        self._words.addWidget(self._list)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self._icon)
        top.addLayout(self._words, 1)

        self._button_box = QDialogButtonBox()
        self._button_box.clicked.connect(self._answered)

        self._bottom = QHBoxLayout()
        self._bottom.setSpacing(6)
        self._bottom.addStretch(1)
        self._bottom.addWidget(self._button_box)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(16)
        root.addLayout(top)
        root.addLayout(self._bottom)
        root.setSizeConstraint(QVBoxLayout.SetFixedSize)

        for button in _standard_buttons(buttons):
            self.addButton(button)

    # ---- as QMessageBox has it ----

    def text(self) -> str:
        return self._text.text()

    def setText(self, text: str) -> None:
        _set_words(self._text, text)

    def informativeText(self) -> str:
        return self._info.text() if not self._info.isHidden() else ""

    def setInformativeText(self, text: str) -> None:
        _set_words(self._info, text)
        self._info.setVisible(bool(text))

    def setCheckBox(self, box: QCheckBox) -> None:
        """A box to tick on the left of the buttons, such as "Don't ask
        again"."""

        self._bottom.insertWidget(0, box)

    def addButton(self, button, role=None) -> QPushButton:
        """A standard button by its value, or one named, in the role
        given."""

        if isinstance(button, str):
            added = self._button_box.addButton(
                button, QDialogButtonBox.ButtonRole(int(role))
            )
        else:
            added = self._button_box.addButton(
                QDialogButtonBox.StandardButton(int(button))
            )

        # Enter only ever presses the default, never what was tabbed to
        added.setAutoDefault(False)

        return added

    def button(self, which) -> QPushButton | None:
        return self._button_box.button(QDialogButtonBox.StandardButton(int(which)))

    def buttons(self) -> list[QAbstractButton]:
        return self._button_box.buttons()

    def buttonRole(self, button) -> int:
        return self._button_box.buttonRole(button)

    def standardButton(self, button) -> int:
        return int(self._button_box.standardButton(button))

    def defaultButton(self) -> QPushButton | None:
        if self._default is not None:
            return self._default

        return next(
            (b for b in self.buttons() if self.buttonRole(b) in _YES_ROLES),
            next(iter(self.buttons()), None),
        )

    def setDefaultButton(self, button) -> None:
        if not isinstance(button, QAbstractButton):
            button = self.button(button)

        self._default = button
        button.setDefault(True)

    def clickedButton(self) -> QAbstractButton | None:
        return self._clicked

    def exec_(self) -> int:
        self._show_default()
        return super().exec_()

    def open(self) -> None:
        self._show_default()
        super().open()

    # ---- of its own ----

    def set_list(self, rows) -> None:
        """Things it is about, each by name with what became of it under
        it: (name, why), why empty for none. A row of a name alone, as
        "and 3 more", is said as it is."""

        layout = QVBoxLayout(self._list)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(5)

        for name, why in rows:
            row = QVBoxLayout()
            row.setSpacing(1)
            row.addWidget(_list_label(name))

            if why:
                why_label = _list_label(why)
                why_label.setContentsMargins(16, 0, 0, 0)
                row.addWidget(why_label)

            layout.addLayout(row)

        self._list.setVisible(bool(rows))

    def set_copy_text(self, text: str) -> None:
        """A Copy button, on the left, putting text on the clipboard; the
        box stays up."""

        self._copied = text

        copy_button = QPushButton(translate("Dialog", "Copy"))
        copy_button.setAutoDefault(False)
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(self._copied)
        )

        self._bottom.insertWidget(0, copy_button)

    def reject(self) -> None:
        """Escape, or the window closed: the answer of Cancel, or of the one
        button that says no; nothing where no button does."""

        escape = self._escape_button()

        if escape is None:
            return

        self._clicked = escape
        super().reject()

    def _answered(self, button):
        self._clicked = button

        if self.buttonRole(button) in _YES_ROLES:
            self.accept()
        else:
            super().reject()

    def _escape_button(self) -> QAbstractButton | None:
        cancel = self.button(QMessageBox.Cancel)
        if cancel is not None:
            return cancel

        buttons = self.buttons()

        for role in (QMessageBox.RejectRole, QMessageBox.NoRole):
            in_role = [b for b in buttons if self.buttonRole(b) == role]
            if len(in_role) == 1:
                return in_role[0]

        return buttons[0] if len(buttons) == 1 else None

    def _show_default(self):
        default = self.defaultButton()

        if default is None:
            return

        default.setDefault(True)
        default.setFocus()

        font = default.font()
        font.setBold(True)
        default.setFont(font)

    @classmethod
    def critical(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Ok,
        defaultButton=QMessageBox.NoButton,
        info="",
    ):
        return cls._asked(QMessageBox.Critical, parent, title, text, buttons, info)

    @classmethod
    def information(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Ok,
        defaultButton=QMessageBox.NoButton,
        info="",
    ):
        return cls._asked(QMessageBox.Information, parent, title, text, buttons, info)

    @classmethod
    def question(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Yes | QMessageBox.No,
        defaultButton=QMessageBox.NoButton,
        info="",
    ):
        return cls._asked(QMessageBox.Question, parent, title, text, buttons, info)

    @classmethod
    def cancellable_question(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        defaultButton=QMessageBox.NoButton,
        info="",
    ):
        return cls._asked(QMessageBox.Question, parent, title, text, buttons, info)

    @classmethod
    def warning(
        cls,
        parent,
        title,
        text,
        buttons=QMessageBox.Ok,
        defaultButton=QMessageBox.NoButton,
        info="",
    ):
        return cls._asked(QMessageBox.Warning, parent, title, text, buttons, info)

    @classmethod
    def confirm(
        cls,
        parent,
        title,
        text,
        action: str,
        info: str = "",
        is_destructive: bool = False,
        icon=QMessageBox.Question,
    ) -> bool:
        """Whether the button named for what is asked was pressed, rather
        than Cancel. Where it loses something, Cancel is the default."""

        box = cls(icon, title, text, parent=parent)
        box.setInformativeText(info)

        role = QMessageBox.DestructiveRole if is_destructive else QMessageBox.AcceptRole
        action_button = box.addButton(action, role)
        cancel_button = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(cancel_button if is_destructive else action_button)

        box.exec_()

        is_confirmed = box.clickedButton() is action_button

        box.deleteLater()

        return is_confirmed

    @classmethod
    def _asked(cls, icon, parent, title, text, buttons, info) -> int:
        """The standard button the answer was given with."""

        box = cls(icon, title, text, buttons, parent)
        box.setInformativeText(info)
        box.exec_()

        clicked = box.clickedButton()
        answer = (
            QMessageBox.NoButton if clicked is None else box.standardButton(clicked)
        )

        box.deleteLater()

        return answer


def _standard_buttons(buttons) -> list[int]:
    """The standard buttons of a set of their flags, one by one."""

    buttons = int(buttons)
    each = []

    bit = int(QMessageBox.FirstButton)
    while bit <= int(QMessageBox.LastButton):
        if buttons & bit:
            each.append(QMessageBox.StandardButton(bit))
        bit <<= 1

    return each


def _words_label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setMinimumWidth(TEXT_MIN_WIDTH_PX)
    label.setMaximumWidth(TEXT_MAX_WIDTH_PX)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    label.setOpenExternalLinks(True)
    return label


def _set_words(label: QLabel, text: str) -> None:
    # links come out the theme's colour only where they are said to
    if "<a " in text:
        set_html_with_links(label, text)
    else:
        label.setText(text)


def _list_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setMaximumWidth(TEXT_MAX_WIDTH_PX - 24)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label
