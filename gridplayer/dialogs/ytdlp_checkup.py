"""The checkup as it is watched: a list that fills in as it goes.

The steps go out to the network and one of them can sit there for the
better part of a minute, so the run is put on a thread of its own and the
list says which step it is on. Anything that looks stuck can be called
off, and what was learned before that stays on screen.

The thread is a plain daemon rather than a QThread: a check already inside
a socket read cannot be interrupted, and a QThread that has to be waited
for would hold the window shut for as long as that read takes. This one is
simply let go of, and the dialog stops listening.
"""

import html
import logging
import re
import threading

from PyQt5 import QtWidgets
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPalette
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox

from gridplayer.params.theme import set_html_with_links
from gridplayer.utils.qt import qt_connect, translate
from gridplayer.utils.ytdlp_checkup import (
    TRANSLATION_CONTEXT,
    CheckResult,
    CheckStatus,
    report_text,
)

STATUS_ICONS = {
    CheckStatus.PASSED: "checkmark",
    CheckStatus.WARNING: "warning",
    CheckStatus.FAILED: "error",
    CheckStatus.SKIPPED: "information",
}

PENDING_ICON = "empty"

# big enough to tell a tick from a cross at a glance, which is the one
# thing somebody reads this list for
ICON_SIZE = 24

# what the icon column costs, leaving the text of every row lined up
# whether or not the row has an icon yet
ICON_GUTTER = 12

LIST_PADDING = 12
ROW_SPACING = 14

# how often the clock on a run in progress is redrawn
TICK_MS = 500

SECONDS_IN_MINUTE = 60

DIALOG_SIZE = (620, 560)

# a hint is as likely as not to end in the page that explains the rest of
# it, and a URL nobody can click is a URL nobody reads
URL_PATTERN = re.compile(r"https?://\S+")


def _t(text: str) -> str:
    return translate(TRANSLATION_CONTEXT, text)


class CheckRunner(QObject):
    """Runs the checks one after another, off the interface thread.

    Cancelling sets a flag the loop looks at between checks: the one in
    flight is left to finish into nothing, since there is no safe way to
    stop it and every check is bounded by its own timeout anyway.
    """

    check_started = pyqtSignal(int)
    check_finished = pyqtSignal(int, object)
    run_finished = pyqtSignal(bool)

    def __init__(self, checks):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)

        self._checks = checks
        self._cancelled = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def start(self) -> None:
        threading.Thread(target=self._run, name="ytdlp-checkup", daemon=True).start()

    def cancel(self) -> None:
        self._cancelled.set()

    def _run(self) -> None:
        for index, check in enumerate(self._checks):
            if self.is_cancelled:
                break

            self.check_started.emit(index)

            check_result = self._run_check(check)

            if self.is_cancelled:
                break

            self.check_finished.emit(index, check_result)

        self.run_finished.emit(self.is_cancelled)

    def _run_check(self, check):
        try:
            return check.run()
        except Exception as e:
            self._log.exception(f"Checkup step failed: {check.title}")

            return _crashed(e)


class CheckRow(QtWidgets.QWidget):
    """One step, with room for what it found and what to do about it."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)

        self.icon = self._ui_icon()
        self.title = self._ui_title(title)
        self.summary = _wrapping_label(_t("Waiting"))
        self.hint = self._ui_hint()

        lines = QtWidgets.QVBoxLayout()
        lines.setContentsMargins(0, 0, 0, 0)
        lines.setSpacing(2)
        lines.addWidget(self.title)
        lines.addWidget(self.summary)
        lines.addWidget(self.hint)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ICON_GUTTER)
        layout.addWidget(self.icon, alignment=Qt.AlignTop)
        layout.addLayout(lines, stretch=1)

        self.set_pending()

    def set_pending(self) -> None:
        self._set_icon(PENDING_ICON)
        self.summary.setText(_t("Waiting"))
        self.hint.setVisible(False)
        self.setEnabled(False)

    def set_running(self) -> None:
        self._set_icon(PENDING_ICON)
        self.summary.setText(_t("Running..."))
        self.setEnabled(True)

    def set_result(self, check_result) -> None:
        self.setEnabled(True)

        self._set_icon(STATUS_ICONS[check_result.status])
        self.summary.setText(check_result.summary)

        set_html_with_links(self.hint, _linked(check_result.hint))
        self.hint.setVisible(bool(check_result.hint))

    def set_not_run(self) -> None:
        self._set_icon(PENDING_ICON)
        self.summary.setText(_t("Not run"))
        self.hint.setVisible(False)
        self.setEnabled(False)

    def _set_icon(self, name: str) -> None:
        self.icon.setPixmap(QIcon.fromTheme(name).pixmap(ICON_SIZE, ICON_SIZE))

    def _ui_icon(self):
        icon = QtWidgets.QLabel(parent=self)
        icon.setFixedSize(ICON_SIZE, ICON_SIZE)

        return icon

    def _ui_title(self, title: str):
        label = QtWidgets.QLabel(title, parent=self)

        font = label.font()
        font.setBold(True)
        label.setFont(font)

        return label

    def _ui_hint(self):
        hint = _wrapping_label("")

        font = hint.font()
        font.setItalic(True)
        hint.setFont(font)

        hint.setTextFormat(Qt.RichText)
        hint.setOpenExternalLinks(True)
        hint.setTextInteractionFlags(Qt.TextBrowserInteraction)

        return hint


class YtDlpCheckupDialog(QDialog):
    """A checkup, run as soon as it is shown."""

    def __init__(self, parent, checkup):
        super().__init__(parent)

        self._checks = checkup.checks
        self._results = [None] * len(self._checks)

        self._runner = CheckRunner(self._checks)
        self._elapsed = QTimer(self)
        self._seconds = 0
        self._is_stopped = False

        self.setWindowTitle(_t("yt-dlp checkup"))
        self.resize(*DIALOG_SIZE)

        self.rows = [CheckRow(check.title, parent=self) for check in self._checks]
        self.progress = self._ui_progress()
        self.status = QtWidgets.QLabel(parent=self)
        self.buttons = self._ui_buttons()

        self._ui_layout()
        self._ui_connect()

        self._start()

    def done(self, result):
        """Every way out of the dialog comes through here.

        A run still in flight is let go of rather than waited on: the
        window shuts now, and the thread finishes into nothing.
        """

        self._stop()

        super().done(result)

    def copy_report(self) -> None:
        rows = zip((check.title for check in self._checks), self._results)

        QApplication.clipboard().setText(report_text(list(rows)))

    def abort(self) -> None:
        self._runner.cancel()

        self._finish(is_cancelled=True)

    def check_started(self, index: int) -> None:
        self.rows[index].set_running()

        self.status.setText(
            _t("Step {STEP} of {STEPS}: {TITLE}").format(
                STEP=index + 1, STEPS=len(self._checks), TITLE=self._checks[index].title
            )
        )

    def check_finished(self, index: int, check_result) -> None:
        self._results[index] = check_result

        self.rows[index].set_result(check_result)

        self.progress.setValue(index + 1)

    def run_finished(self, is_cancelled: bool) -> None:
        self._finish(is_cancelled=is_cancelled)

    def tick(self) -> None:
        self._seconds += TICK_MS / 1000

        self.progress.setFormat(_elapsed_text(int(self._seconds)))

    def _start(self) -> None:
        self._elapsed.start(TICK_MS)

        self._runner.start()

    def _stop(self) -> None:
        """Stop caring what the run says next.

        Disconnecting matters more than cancelling: the thread outlives
        this window by however long its last request takes, and a signal
        arriving after the widgets are gone is a crash.
        """

        if self._is_stopped:
            return

        self._is_stopped = True

        self._elapsed.stop()
        self._runner.cancel()

        self._runner.disconnect()

    def _finish(self, is_cancelled: bool) -> None:
        self._elapsed.stop()

        for row, check_result in zip(self.rows, self._results):
            if check_result is None:
                row.set_not_run()

        self.progress.setValue(self.progress.maximum())
        self.progress.setFormat(_elapsed_text(int(self._seconds)))

        self.status.setText(
            _t("Stopped") if is_cancelled else _summary_line(self._results)
        )

        self.abort_button.setVisible(False)
        self.close_button.setVisible(True)
        self.close_button.setFocus()

    def _ui_progress(self):
        progress = QtWidgets.QProgressBar(parent=self)
        progress.setRange(0, len(self._checks))
        progress.setValue(0)
        progress.setFormat(_elapsed_text(0))

        return progress

    def _ui_buttons(self):
        buttons = QDialogButtonBox(parent=self)

        self.copy_button = buttons.addButton(
            _t("Copy report"), QDialogButtonBox.ActionRole
        )
        self.abort_button = buttons.addButton(
            _t("Stop"), QDialogButtonBox.DestructiveRole
        )
        self.close_button = buttons.addButton(QDialogButtonBox.Close)

        self.close_button.setVisible(False)

        return buttons

    def _ui_checks(self):
        """The list, in a panel of its own.

        Loose on the dialog the rows read as stray labels. Sunk into a
        panel the colour of a text field, the way the cookie table next
        door is, they read as the one thing the window is about.
        """

        checks = QtWidgets.QWidget()

        checks_layout = QtWidgets.QVBoxLayout(checks)
        checks_layout.setContentsMargins(*[LIST_PADDING] * 4)
        checks_layout.setSpacing(ROW_SPACING)

        for row in self.rows:
            checks_layout.addWidget(row)

        checks_layout.addStretch()

        scroll = QtWidgets.QScrollArea(parent=self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.StyledPanel)
        scroll.setBackgroundRole(QPalette.Base)
        scroll.setWidget(checks)

        checks.setBackgroundRole(QPalette.Base)
        checks.setAutoFillBackground(True)

        return scroll

    def _ui_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            _wrapping_label(
                _t(
                    "Playing a YouTube link, step by step, with the cookies"
                    " on the settings page as they stand now."
                )
            )
        )
        layout.addWidget(self._ui_checks())
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.buttons)

    def _ui_connect(self) -> None:
        qt_connect(
            (self._runner.check_started, self.check_started),
            (self._runner.check_finished, self.check_finished),
            (self._runner.run_finished, self.run_finished),
            (self._elapsed.timeout, self.tick),
            (self.copy_button.clicked, self.copy_report),
            (self.abort_button.clicked, self.abort),
            (self.close_button.clicked, self.accept),
        )


def _wrapping_label(text: str):
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)

    return label


def _linked(hint: str) -> str:
    """A hint as rich text, with whatever is a URL in it made clickable.

    Escaped first and marked up after, since a hint can be a warning
    yt-dlp wrote and there is no telling what is in one of those.
    """

    marked_up = URL_PATTERN.sub(
        lambda found: f'<a href="{found.group()}">{found.group()}</a>',
        html.escape(hint),
    )

    return "<br>".join(marked_up.splitlines())


def _elapsed_text(seconds: int) -> str:
    """How far along and how long it has taken, as the bar spells it.

    The clock is the point: a step that has been going for a minute is
    the only sign the dialog can give that it is worth calling off.
    """

    minutes, seconds = divmod(seconds, SECONDS_IN_MINUTE)

    return f"%v/%m - {minutes}:{seconds:02}"


def _summary_line(results) -> str:
    """How the run came out, in the one line under the list."""

    counted = [check_result for check_result in results if check_result is not None]

    failed = sum(r.status is CheckStatus.FAILED for r in counted)
    warned = sum(r.status is CheckStatus.WARNING for r in counted)

    if failed and warned:
        return _t("{FAILED} failed, {WARNED} to look at").format(
            FAILED=failed, WARNED=warned
        )

    if failed:
        return _t("{FAILED} failed").format(FAILED=failed)

    if warned:
        return _t("Nothing failed, {WARNED} to look at").format(WARNED=warned)

    return _t("All good")


def _crashed(error: Exception) -> CheckResult:
    """A check that went wrong in a way it had no answer for."""

    return CheckResult(CheckStatus.FAILED, f"{type(error).__name__}: {error}")
