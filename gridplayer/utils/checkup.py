"""What a checkup is, apart from whatever any one of them checks.

A checkup walks the steps of something that failed as a single opaque
message and says which step gave way. There are two of them now -- one
for a YouTube link, one for the network settings -- and they share a
dialog, so what a step is and how a run reads have to live somewhere
neither of them owns.

A checkup is a title, a line saying what it is about, and an ordered run
of checks. The order is part of it: a step leaves behind what the next
one needs, so one whose ground was never laid says so rather than
failing.
"""

import dataclasses
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum

from gridplayer.utils.qt import translate

TRANSLATION_CONTEXT = "Checkup"


class CheckStatus(Enum):
    """How one check came out.

    A checkup is a diagnosis rather than a verdict, so most of what it
    finds is a warning: something that explains a failure when one
    happens, and is worth knowing about when nothing has failed yet.
    """

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclasses.dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    summary: str
    # what to do about it, where there is something to do
    hint: str = ""


@dataclasses.dataclass(frozen=True)
class Check:
    title: str
    run: Callable[[], CheckResult]


class Checkup(ABC):
    """The three things the dialog needs of anything it is asked to run."""

    @property
    @abstractmethod
    def title(self) -> str:
        """What this checkup is called, in the window and on the report."""

    @property
    @abstractmethod
    def intro(self) -> str:
        """The line above the list, saying what is about to be tried."""

    @property
    @abstractmethod
    def checks(self) -> tuple[Check, ...]:
        """The steps, in the order they build up."""


def report_text(title: str, rows) -> str:
    """The whole run as plain text, for pasting where it can be read.

    Rows are (title, result), with a result of None for a check that
    never ran, so an abandoned run reports as much as it got through.
    """

    ran_at = datetime.now(tz=timezone.utc).astimezone()

    lines = [f"{title} - {ran_at.strftime('%Y-%m-%d %H:%M')}", ""]

    for check_title, check_result in rows:
        lines.append(
            f"{_status_tag(check_result)} {check_title}: {_summary_of(check_result)}"
        )

        if check_result is not None and check_result.hint:
            # rstripped so a hint with a gap in it does not leave a line
            # of trailing spaces where the gap is
            lines.extend(
                f"    {line}".rstrip() for line in check_result.hint.splitlines()
            )

    return "\n".join(lines)


def _t(text: str) -> str:
    return translate(TRANSLATION_CONTEXT, text)


def _status_tag(check_result) -> str:
    if check_result is None:
        return "[ -- ]"

    tags = {
        CheckStatus.PASSED: "[ ok ]",
        CheckStatus.WARNING: "[warn]",
        CheckStatus.FAILED: "[fail]",
        CheckStatus.SKIPPED: "[skip]",
    }

    return tags[check_result.status]


def _summary_of(check_result) -> str:
    return check_result.summary if check_result is not None else _t("Not run")
