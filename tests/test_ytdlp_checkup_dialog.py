"""The window the checkup is watched in.

The run is on a thread of its own so the list can fill in while it goes,
which is the whole point of the dialog and also the only part of it that
can go wrong quietly: a result arriving after the window has gone, or a
run nobody can call off.
"""

import threading
import time

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.dialogs.ytdlp_checkup import YtDlpCheckupDialog, _linked
from gridplayer.utils.ytdlp_checkup import Check, CheckResult, CheckStatus

WAIT_SEC = 5
POLL_SEC = 0.01

# long enough for something that should not happen to have happened
SETTLE_SEC = 0.5


class FakeCheckup:
    """A checkup of steps the test decides the timing of."""

    def __init__(self, *checks):
        self.checks = checks


@pytest.fixture
def parent():
    """A parent held for the length of the test.

    Dropped, Qt takes the dialog down with it, and every look at it
    afterwards raises about a deleted C++ object.
    """

    widget = QWidget()

    yield widget

    widget.deleteLater()


def _passing(title, summary="fine", hint=""):
    return Check(title, lambda: CheckResult(CheckStatus.PASSED, summary, hint))


def _blocking(title, released: threading.Event):
    def _run():
        released.wait(WAIT_SEC)

        return CheckResult(CheckStatus.PASSED, "let go")

    return Check(title, _run)


def _exploding(title):
    def _run():
        raise RuntimeError("no idea")

    return Check(title, _run)


def _wait_until(is_done, seconds=WAIT_SEC):
    """Spin the loop until the run gets where the test is waiting for."""

    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        QApplication.processEvents()

        if is_done():
            return True

        time.sleep(POLL_SEC)

    return False


def _finished(dialog):
    return lambda: all(row is not None for row in dialog._results)


def test_every_step_is_listed_before_any_of_them_has_run(parent):
    """The list says what is coming, not only what has happened."""

    checkup = FakeCheckup(_passing("One"), _passing("Two"))

    dialog = YtDlpCheckupDialog(parent, checkup)

    assert [row.title.text() for row in dialog.rows] == ["One", "Two"]


def test_a_run_fills_the_list_in(parent):
    checkup = FakeCheckup(_passing("One", "all well"), _passing("Two"))

    dialog = YtDlpCheckupDialog(parent, checkup)

    assert _wait_until(_finished(dialog))
    assert dialog.rows[0].summary.text() == "all well"
    assert dialog.progress.value() == dialog.progress.maximum()


def test_a_hint_only_shows_where_there_is_one(parent):
    checkup = FakeCheckup(_passing("One", hint="do this"), _passing("Two"))

    dialog = YtDlpCheckupDialog(parent, checkup)
    parent.show()

    assert _wait_until(_finished(dialog))
    assert dialog.rows[0].hint.isVisibleTo(dialog)
    assert not dialog.rows[1].hint.isVisibleTo(dialog)


def test_a_step_that_goes_wrong_is_a_result_like_any_other(parent):
    """One check falling over must not take the rest of the run with it."""

    checkup = FakeCheckup(_exploding("One"), _passing("Two"))

    dialog = YtDlpCheckupDialog(parent, checkup)

    assert _wait_until(_finished(dialog))
    assert dialog._results[0].status is CheckStatus.FAILED
    assert "no idea" in dialog._results[0].summary
    assert dialog._results[1].status is CheckStatus.PASSED


def test_stopping_leaves_what_was_learned_on_screen(parent):
    released = threading.Event()
    checkup = FakeCheckup(_passing("One", "all well"), _blocking("Two", released))

    dialog = YtDlpCheckupDialog(parent, checkup)

    assert _wait_until(lambda: dialog._results[0] is not None)

    dialog.abort()

    assert dialog.rows[0].summary.text() == "all well"
    assert dialog.rows[1].summary.text() == "Not run"
    assert not dialog.abort_button.isVisibleTo(dialog)

    released.set()


def test_a_step_still_running_cannot_reach_a_closed_dialog(parent):
    """The thread outlives the window by as long as its request takes.

    Closing has to let go of the run rather than wait for it, so what
    the run says next has to land nowhere.
    """

    released = threading.Event()
    checkup = FakeCheckup(_blocking("One", released), _passing("Two"))

    dialog = YtDlpCheckupDialog(parent, checkup)

    dialog.reject()

    assert dialog._runner.is_cancelled

    released.set()

    assert _wait_until(_finished(dialog), seconds=SETTLE_SEC) is False
    assert dialog._results == [None, None]


def test_the_report_covers_the_steps_that_never_ran(parent):
    released = threading.Event()
    checkup = FakeCheckup(_passing("One", "all well"), _blocking("Two", released))

    dialog = YtDlpCheckupDialog(parent, checkup)

    assert _wait_until(lambda: dialog._results[0] is not None)

    dialog.abort()
    dialog.copy_report()

    report = QApplication.clipboard().text()

    assert "[ ok ] One: all well" in report
    assert "[ -- ] Two: Not run" in report

    released.set()


class TestHintMarkup:
    """A hint is shown as rich text, and not all of it is ours to trust."""

    def test_a_page_worth_reading_is_made_clickable(self):
        marked_up = _linked("See https://example.com/wiki#cookies")

        assert '<a href="https://example.com/wiki#cookies">' in marked_up

    def test_a_warning_yt_dlp_wrote_cannot_smuggle_markup_in(self):
        marked_up = _linked("<b>skipped</b> formats & such")

        assert "<b>" not in marked_up
        assert "&amp; such" in marked_up

    def test_warnings_stay_on_lines_of_their_own(self):
        assert _linked("one\ntwo") == "one<br>two"
