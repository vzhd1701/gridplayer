"""The dialog asking how what is being added goes into the grid."""

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
)

from gridplayer.dialogs import add_choice
from gridplayer.dialogs.add_choice import AddChoiceDialog, AddOption, ManyCellsDialog

OPTIONS = [
    AddOption("each", "A cell for each", about="One after another.", note="3 cells"),
    AddOption("one", "One cell"),
    None,
    AddOption("onto", "Add to this cell's list"),
]


def _buttons(dialog) -> list[QRadioButton]:
    return dialog.findChildren(QRadioButton)


def _texts(dialog) -> list[str]:
    """What the dialog says, as it would be seen: the question first, in
    the order it is laid out in."""

    return [
        label.text()
        for label in _laid_out(dialog.layout())
        if isinstance(label, QLabel) and label.isVisibleTo(dialog)
    ]


def _laid_out(layout):
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()

        if widget is not None:
            yield widget

            if widget.layout() is not None:
                yield from _laid_out(widget.layout())
        elif item.layout() is not None:
            yield from _laid_out(item.layout())


def _push_button(dialog, text) -> QPushButton:
    (button,) = [
        button for button in dialog.findChildren(QPushButton) if button.text() == text
    ]
    return button


def _shown(widget) -> bool:
    return not widget.isHidden()


class TestTheChoices:
    def test_each_offered_the_gap_none(self):
        dialog = AddChoiceDialog("How?", [], OPTIONS)

        assert [button.text() for button in _buttons(dialog)] == [
            "A cell for each",
            "One cell",
            "Add to this cell's list",
        ]

    def test_the_first_picked_to_start_with(self):
        dialog = AddChoiceDialog("How?", [], OPTIONS)

        assert _buttons(dialog)[0].isChecked()
        assert dialog.choice() == "each"

    def test_another_picked(self):
        dialog = AddChoiceDialog("How?", [], OPTIONS)

        _buttons(dialog)[2].setChecked(True)

        assert dialog.choice() == "onto"
        assert not _buttons(dialog)[0].isChecked()

    def test_said_what_they_do_and_take(self):
        dialog = AddChoiceDialog("How?", [], OPTIONS)

        texts = _texts(dialog)
        assert "One after another." in texts
        assert "3 cells" in texts
        # nothing said where there is nothing to say
        assert "" not in texts


class TestWarned:
    WARNED = [
        AddOption(
            "each", "A cell for each", about="One after another.", warning="Can freeze."
        ),
        AddOption("one", "One cell"),
    ]

    def _label(self, dialog, text) -> QLabel:
        (label,) = [
            label for label in dialog.findChildren(QLabel) if label.text() == text
        ]
        return label

    def test_under_what_the_option_does(self):
        dialog = AddChoiceDialog("Add 900 cells?", ["a.mp4"], self.WARNED)

        texts = [text for text in _texts(dialog) if text]
        assert texts[texts.index("One after another.") + 1] == "Can freeze."

    def test_in_a_box_with_the_warning_sign_in_bold(self):
        dialog = AddChoiceDialog("Add 900 cells?", ["a.mp4"], self.WARNED)

        label = self._label(dialog, "Can freeze.")
        (sign,) = [
            other
            for other in label.parentWidget().findChildren(QLabel)
            if other is not label
        ]
        assert isinstance(label.parentWidget(), QFrame)
        assert label.font().bold()
        # the sign itself comes from the app's icons, not loaded here
        assert sign.pixmap() is not None

    def test_not_where_there_is_nothing_to_warn_of(self):
        dialog = AddChoiceDialog("How?", ["a.mp4"], OPTIONS)

        assert "" not in _texts(dialog)


class TestWhatIsBeingAdded:
    def test_named_under_the_question(self):
        dialog = AddChoiceDialog("How?", ["a.mp4", "Shows — 2 items"], OPTIONS)

        texts = _texts(dialog)
        assert texts[:3] == ["How?", "a.mp4", "Shows — 2 items"]

    def test_so_many_the_rest_counted(self):
        names = [f"{n}.mp4" for n in range(add_choice.WHAT_LISTED + 3)]

        dialog = AddChoiceDialog("How?", names, OPTIONS)

        texts = _texts(dialog)
        assert texts[1 : add_choice.WHAT_LISTED + 1] == names[: add_choice.WHAT_LISTED]
        assert texts[add_choice.WHAT_LISTED + 1] == "and 3 more"
        assert f"{add_choice.WHAT_LISTED}.mp4" not in texts


class TestAsked:
    def test_the_pick(self, mocker):
        mocker.patch.object(AddChoiceDialog, "exec_", return_value=QDialog.Accepted)

        assert AddChoiceDialog.ask("How?", [], OPTIONS) == "each"

    def test_none_the_viewer_thinking_better_of_it(self, mocker):
        mocker.patch.object(AddChoiceDialog, "exec_", return_value=QDialog.Rejected)

        assert AddChoiceDialog.ask("How?", [], OPTIONS) is None


class TestUpWhileItIsRead:
    def _reading(self, is_asked=True):
        return AddChoiceDialog.reading("How?", ["Big Folder"], is_asked)

    def _bar(self, dialog) -> QProgressBar:
        return dialog.findChild(QProgressBar)

    def test_says_it_is_read_with_nothing_to_pick_yet(self):
        dialog = self._reading()

        assert _texts(dialog) == ["How?", "Big Folder", "Reading…"]
        assert _buttons(dialog) == []
        assert dialog.is_reading

    def test_add_there_but_not_to_be_pressed(self):
        dialog = self._reading()

        add = _push_button(dialog, "Add")
        assert _shown(add)
        assert not add.isEnabled()

    def test_add_not_there_where_nothing_is_to_be_asked(self):
        dialog = self._reading(is_asked=False)

        assert not _shown(_push_button(dialog, "Add"))

    def test_how_far_it_has_got(self):
        dialog = self._reading()

        dialog.tell_reading("Reading the list… 2,000 items", 40)

        assert "Reading the list… 2,000 items" in _texts(dialog)
        assert self._bar(dialog).value() == 40

    def test_under_way_where_how_far_is_not_known(self):
        dialog = self._reading()

        dialog.tell_reading("Scanning folder… 12 files")

        assert self._bar(dialog).maximum() == 0

    def test_asked_once_it_is_read(self):
        dialog = self._reading()

        dialog.set_question("How?", ["Big Folder — 3 items"], OPTIONS)

        assert _texts(dialog)[:2] == ["How?", "Big Folder — 3 items"]
        assert not _shown(self._bar(dialog))
        assert "Reading…" not in _texts(dialog)
        assert _push_button(dialog, "Add").isEnabled()
        assert dialog.choice() == "each"
        assert not dialog.is_reading

    def test_stop_asks_for_it_to_end(self):
        dialog = self._reading()
        asked = []
        dialog.stop_asked.connect(lambda: asked.append(True))

        _push_button(dialog, "Stop").click()

        assert asked == [True]
        assert "Stopping…" in _texts(dialog)
        assert not _push_button(dialog, "Stop").isEnabled()

    def test_nothing_more_told_once_stopped(self):
        dialog = self._reading()
        _push_button(dialog, "Stop").click()

        dialog.tell_reading("Reading the list… 4,000 items", 80)

        assert "Stopping…" in _texts(dialog)

    def test_asked_once_stopped_says_so(self):
        dialog = self._reading()
        _push_button(dialog, "Stop").click()

        dialog.set_question("How?", ["Big Folder — 1 items"], OPTIONS)

        assert "Stopped. Only what was found so far will be added." in _texts(dialog)
        assert not _shown(_push_button(dialog, "Stop"))

    def test_enter_only_ever_adds(self):
        dialog = self._reading()

        assert _push_button(dialog, "Add").isDefault()
        assert not _push_button(dialog, "Stop").autoDefault()
        assert not _push_button(dialog, "Cancel").autoDefault()


class TestManyCellsWarning:
    def test_says_how_many_and_what_it_can_do(self):
        dialog = ManyCellsDialog(1500)

        assert [
            label.text() for label in dialog.findChildren(QLabel) if label.text()
        ] == [
            "Add 1,500 cells?",
            "1,500 cells at once can freeze the player.",
        ]

    def test_the_warning_sign_by_it(self):
        dialog = ManyCellsDialog(30)

        (sign,) = [label for label in dialog.findChildren(QLabel) if not label.text()]
        assert sign.pixmap() is not None

    def test_add_or_cancel_and_nothing_else(self):
        dialog = ManyCellsDialog(30)

        assert sorted(button.text() for button in dialog.findChildren(QPushButton)) == [
            "Add",
            "Cancel",
        ]
        assert _push_button(dialog, "Add").isDefault()
        assert _buttons(dialog) == []

    def test_warned_again_unless_ticked(self):
        dialog = ManyCellsDialog(30)
        assert dialog.is_warned_again

        dialog.findChild(QCheckBox).setChecked(True)

        assert not dialog.is_warned_again

    def test_asked_whether_added_and_whether_again(self, mocker):
        mocker.patch.object(ManyCellsDialog, "exec_", return_value=QDialog.Accepted)

        assert ManyCellsDialog.ask(30) == (True, True)

    def test_cancelled_nothing_added(self, mocker):
        mocker.patch.object(ManyCellsDialog, "exec_", return_value=QDialog.Rejected)

        assert ManyCellsDialog.ask(30)[0] is False
