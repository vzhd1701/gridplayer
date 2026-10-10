"""How far reading a list has got, told from the thread reading it to the
interface, and how it is asked to stop."""

import time

from PyQt5.QtCore import QLocale

from gridplayer.utils.qt import count_txt, translate

# how often at most the interface is told how far reading has got
PROGRESS_INTERVAL_S = 0.25


class ReadingStopped(Exception):
    """Raised by a list's progress being told, where the reading of it was
    asked to stop: out of the download, or the reading of the text."""


class ReadingEnough(Exception):
    """Raised by a list's progress being told, where the reading of it was
    asked to end with what it has read by then: what can be is kept by the
    reader that is told it, a folder's files found so far or a list's items,
    and anything else is let go."""


class Throttled:
    """Passes on how far reading has got, a few times a second at most: a
    list read item by item would flood the interface with it.

    Told what is done, how many, and of what: the bytes downloaded and how
    many there are to come where that is known, the items read and how far
    through the list in percent, or the files found in a folder so far; see
    reading_txt.
    """

    def __init__(self, tell, stop=None, enough=None):
        self._tell = tell
        self._last = None
        self._last_what = None

        # set, for the reading to stop the next time it says how far it is
        self._stop = stop
        # set, for it to end then with what it has read so far
        self._enough = enough

    def __call__(self, what: str, count: int, of: int | None = None):
        if self._stop is not None and self._stop.is_set():
            raise ReadingStopped

        if self._enough is not None and self._enough.is_set():
            raise ReadingEnough

        now = time.monotonic()

        # what comes next told at once: reading after downloading
        is_next = what != self._last_what

        if not is_next and now - self._last < PROGRESS_INTERVAL_S:
            return

        self._last = now
        self._last_what = what
        self._tell(what, count, of)


def reading_txt(what: str, count: int, of: int | None = None) -> tuple[str, int]:
    """What to say of how far reading a list has got, and how far that is
    in percent, 0 for not known: the bytes downloaded of how many there
    are, the items read and how far through the list, or the files found
    scanning a folder."""

    if what == "bytes":
        size = _size_txt(count)

        if not of:
            text = translate("Lists", "Downloading the list… {SIZE}").format(SIZE=size)
            return text, 0

        text = translate("Lists", "Downloading the list… {SIZE} of {TOTAL}").format(
            SIZE=size, TOTAL=_size_txt(of)
        )
        return text, min(count * 100 // of, 100)

    if what == "files":
        text = translate("Lists", "Scanning folder… {COUNT} files")
        return text.format(COUNT=count_txt(count)), 0

    text = translate("Lists", "Reading the list… {COUNT} items").format(
        COUNT=count_txt(count)
    )

    return text, of or 0


def _size_txt(size: int) -> str:
    return QLocale().formattedDataSize(size, 1, QLocale.DataSizeSIFormat)
