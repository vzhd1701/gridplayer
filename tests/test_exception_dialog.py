import pytest
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox

from gridplayer.dialogs.exception import ExceptionDialog
from gridplayer.version import __app_bugtracker_url__

TRACEBACK = "Traceback (most recent call last):\n  ...\nValueError: boom"


@pytest.fixture
def dialog():
    dialog = ExceptionDialog(TRACEBACK)

    yield dialog

    dialog.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_it_shows_the_traceback(dialog):
    assert dialog.windowTitle() == "Unhandled Exception"
    assert dialog.exception_box.toPlainText() == TRACEBACK


def test_it_points_to_the_bug_tracker(dialog):
    assert __app_bugtracker_url__ in dialog.error_label.text()


def test_copy_puts_the_traceback_on_the_clipboard(dialog):
    QApplication.clipboard().clear()

    dialog.copy_button.click()

    assert QApplication.clipboard().text() == TRACEBACK


def test_close_rejects(dialog):
    dialog.show()

    dialog.buttons.button(QDialogButtonBox.Close).click()

    assert dialog.result() == QDialog.Rejected
    assert not dialog.isVisible()
