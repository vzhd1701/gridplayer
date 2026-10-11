"""The box asking a question, or telling of a warning, an error or a notice:
asked as QMessageBox is, laid out as the app's own."""

from PyQt5.QtWidgets import QApplication, QCheckBox, QLabel, QMessageBox, QPushButton

from gridplayer.dialogs import add_choice
from gridplayer.dialogs.messagebox import QCustomMessageBox


def _button(box, text) -> QPushButton:
    (button,) = [b for b in box.findChildren(QPushButton) if b.text() == text]
    return button


def _texts(box) -> list[str]:
    return [
        label.text()
        for label in box.findChildren(QLabel)
        if label.text() and label.isVisibleTo(box)
    ]


def _answered_with(mocker, text):
    """exec_ answering with the button named."""

    def _exec(box):
        _button(box, text).click()
        return box.result()

    mocker.patch.object(QCustomMessageBox, "exec_", _exec)


class TestWhatItSays:
    def test_the_question_then_what_it_means(self):
        box = QCustomMessageBox(QMessageBox.Question, "Playlist", "Save changes?")
        box.setInformativeText("Your changes will be lost.")

        assert _texts(box) == ["Save changes?", "Your changes will be lost."]
        assert box.windowTitle() == "Playlist"

    def test_the_question_in_bold(self):
        box = QCustomMessageBox(QMessageBox.Question, "Playlist", "Save changes?")

        (question,) = [
            b for b in box.findChildren(QLabel) if b.text() == "Save changes?"
        ]
        assert question.font().bold()

    def test_nothing_more_where_nothing_more_is_said(self):
        box = QCustomMessageBox(QMessageBox.Warning, "Add", "Add 30 cells?")

        assert _texts(box) == ["Add 30 cells?"]

    def test_a_list_of_what_it_is_about(self):
        box = QCustomMessageBox(QMessageBox.Critical, "Add", "Couldn't add 2 items")

        box.set_list([("a.mts", "Not a video"), ("and 1 more", "")])

        assert _texts(box) == [
            "Couldn't add 2 items",
            "a.mts",
            "Not a video",
            "and 1 more",
        ]

    def test_copy_puts_it_all_on_the_clipboard_and_stays_up(self):
        box = QCustomMessageBox(
            QMessageBox.Critical, "Add", "Couldn't add", QMessageBox.Ok
        )
        box.set_copy_text("a.mts\n    Not a video")

        _button(box, "Copy").click()

        assert QApplication.clipboard().text() == "a.mts\n    Not a video"
        assert box.clickedButton() is None


class TestAnswered:
    def test_with_the_standard_button_pressed(self, mocker):
        _answered_with(mocker, "Cancel")

        answer = QCustomMessageBox.cancellable_question(None, "Playlist", "Save?")

        assert answer == QMessageBox.Cancel

    def test_buttons_named_for_what_they_do(self, mocker):
        _answered_with(mocker, "Save")

        answer = QCustomMessageBox.cancellable_question(
            None,
            "Playlist",
            "Save?",
            buttons=QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )

        assert answer == QMessageBox.Save

    def test_confirmed_by_the_button_named(self, mocker):
        _answered_with(mocker, "Reload")

        assert QCustomMessageBox.confirm(None, "List", "Reload?", "Reload")

    def test_not_confirmed_by_cancel(self, mocker):
        _answered_with(mocker, "Cancel")

        assert not QCustomMessageBox.confirm(None, "List", "Reload?", "Reload")


class TestDefault:
    def test_the_button_that_says_yes(self):
        box = QCustomMessageBox(
            QMessageBox.Question, "", "Save?", QMessageBox.Yes | QMessageBox.No
        )

        assert box.defaultButton() is box.button(QMessageBox.Yes)

    def test_the_one_set(self):
        box = QCustomMessageBox(QMessageBox.Warning, "", "Reload?")
        box.addButton("Reload", QMessageBox.DestructiveRole)
        cancel = box.addButton(QMessageBox.Cancel)

        box.setDefaultButton(cancel)

        assert box.defaultButton() is cancel
        assert cancel.isDefault()

    def test_in_bold_once_shown(self):
        box = QCustomMessageBox(QMessageBox.Information, "", "Done", QMessageBox.Ok)

        box.open()
        box.close()

        assert box.button(QMessageBox.Ok).font().bold()

    def test_enter_never_presses_what_was_tabbed_to(self):
        box = QCustomMessageBox(
            QMessageBox.Question, "", "Save?", QMessageBox.Yes | QMessageBox.No
        )

        assert not any(button.autoDefault() for button in box.buttons())


class TestEscape:
    def test_cancel(self):
        box = QCustomMessageBox(
            QMessageBox.Question,
            "",
            "Save?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )

        box.reject()

        assert box.clickedButton() is box.button(QMessageBox.Cancel)

    def test_the_one_button_that_says_no(self):
        box = QCustomMessageBox(
            QMessageBox.Question, "", "Save?", QMessageBox.Yes | QMessageBox.No
        )

        box.reject()

        assert box.clickedButton() is box.button(QMessageBox.No)

    def test_ok_alone(self):
        box = QCustomMessageBox(QMessageBox.Information, "", "Done", QMessageBox.Ok)

        box.reject()

        assert box.clickedButton() is box.button(QMessageBox.Ok)


class TestCheckBox:
    def test_on_the_left_of_the_buttons(self):
        box = QCustomMessageBox(QMessageBox.Warning, "", "Add 30 cells?")
        again = QCheckBox("Don't warn again")

        box.setCheckBox(again)

        assert again.parent() is box


class TestCouldNotBeAdded:
    def test_listed_with_why(self, mocker):
        shown = []
        mocker.patch.object(
            QCustomMessageBox, "exec_", lambda box: shown.append(_texts(box))
        )

        add_choice.show_failed((("a.mts", "Not a video"),), is_nothing_added=True)

        assert shown == [["Couldn't add 1 item", "a.mts", "Not a video"]]

    def test_so_many_the_rest_counted(self, mocker):
        shown = []
        mocker.patch.object(
            QCustomMessageBox, "exec_", lambda box: shown.append(_texts(box))
        )
        failed = tuple((f"{n}.mts", "Not a video") for n in range(7))

        add_choice.show_failed(failed, is_nothing_added=False)

        (texts,) = shown
        assert texts[0] == "Couldn't add 7 items"
        assert texts[-1] == "and 2 more"
        assert "5.mts" not in texts

    def test_nothing_at_all_to_add(self, mocker):
        shown = []
        mocker.patch.object(
            QCustomMessageBox, "exec_", lambda box: shown.append(_texts(box))
        )

        add_choice.show_failed((), is_nothing_added=True)

        assert shown == [
            ["Nothing to add", "None of these are videos, audio or playlists."]
        ]
