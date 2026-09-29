"""Places on the seek bar worth marking, whoever put them there.

The bar draws and names them without knowing where they came from: the
chapters today, the file's own or the site's, and whatever else is marked
on the timeline later on, each in a look of its own.
"""

from bisect import bisect_right
from dataclasses import dataclass
from enum import Enum, auto


class SeekMarkKind(Enum):
    # the start of a chapter, which runs until the next one starts
    CHAPTER = auto()


@dataclass(frozen=True)
class SeekMark:
    time_ms: int
    label: str
    kind: SeekMarkKind = SeekMarkKind.CHAPTER


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
