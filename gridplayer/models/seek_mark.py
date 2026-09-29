"""Places on the seek bar worth marking, whoever put them there.

The bar draws and names them without knowing where they came from: the
chapters, the file's own or the site's, and the parts of a YouTube video
that SponsorBlock's users have marked, each in a look of its own.
"""

from bisect import bisect_right
from dataclasses import dataclass
from enum import Enum, auto


class SeekMarkKind(Enum):
    # the start of a chapter, which runs until the next one starts
    CHAPTER = auto()
    # a stretch with an end of its own, drawn in a colour of its own
    SEGMENT = auto()
    # a single place picked out as the one worth seeing
    HIGHLIGHT = auto()


@dataclass(frozen=True)
class SeekMark:
    time_ms: int
    label: str
    kind: SeekMarkKind = SeekMarkKind.CHAPTER
    # where a segment ends; None for a mark that is a place
    end_ms: int | None = None
    # what it is drawn in, None for the bar's own colours
    color: str | None = None


def chapter_at(marks, time_ms: int, length: int) -> tuple[SeekMark, int, int] | None:
    """The chapter a time falls in, with where it starts and ends.

    None before the first chapter starts, which is no chapter's.
    """

    chapters = [mark for mark in marks if mark.kind == SeekMarkKind.CHAPTER]

    starts = [mark.time_ms for mark in chapters]

    index = bisect_right(starts, time_ms) - 1

    if index < 0:
        return None

    end_ms = starts[index + 1] if index + 1 < len(starts) else length

    return chapters[index], starts[index], end_ms


def segments_at(marks, time_ms: int, near_ms: int = 0) -> list[SeekMark]:
    """The segments a time falls in, and the highlights within near_ms of it.

    First to start first. A highlight has no length for a time to fall in,
    so it is found by being near enough.
    """

    found = []

    for mark in marks:
        if mark.kind == SeekMarkKind.SEGMENT:
            if mark.time_ms <= time_ms < mark.end_ms:
                found.append(mark)

        elif mark.kind == SeekMarkKind.HIGHLIGHT:
            if abs(mark.time_ms - time_ms) <= near_ms:
                found.append(mark)

    return sorted(found, key=lambda mark: mark.time_ms)
