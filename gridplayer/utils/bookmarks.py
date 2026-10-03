"""Finding the way around a video by the places the viewer marked in it.

A jump only goes to a bookmark inside the stretch being played: the whole
video, or the loop where one is set, as it is for chapters.
"""

import functools
import os
import re
from bisect import insort
from pathlib import Path

from gridplayer.models.bookmark import Bookmark
from gridplayer.utils.chapters import CHAPTER_TOLERANCE_MS
from gridplayer.utils.qt import translate
from gridplayer.utils.time_txt import parse_time_txt, timestamp_txt

# Two bookmarks this close are the same place, so a second press of the key
# a moment after the first marks nothing new.
BOOKMARK_SAME_MS = 500

# How near the video has to be to a bookmark to be at it: the one renaming
# and removing act on, and the one ticked in the menu. VLC's time moves in
# whole seconds on some streams, so anything nearer is no telling apart.
BOOKMARK_AT_MS = 1000

# Less than this past a bookmark the video is still at it, as far as moving
# on from it goes: going back goes to the one before it, so that a second
# press moves on rather than landing on the same one again.
BOOKMARK_BACK_MS = 1000

# VLC reports the time a hair short of where a seek landed, so a video just
# sent to a bookmark reads as a little before it, and a jump onwards from
# there has to count it as passed.
BOOKMARK_AHEAD_MS = CHAPTER_TOLERANCE_MS


# A time in a line of text, as lists of chapters and timestamps write one:
# 3:27 or 1:02:03, or to a fraction of a second, 3:27.400. Plain numbers are
# no times, or every line with a number in it would be one.
_TIMESTAMP = re.compile(
    r"(?<![\d:.])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\.(\d+))?(?![\d:])"
)

# what sets a timestamp apart from the name beside it
_TIMESTAMP_BRACKETS_BEFORE = "[("
_TIMESTAMP_BRACKETS_AFTER = ")]"
# (en and em dashes, bullets and middle dots among them)
_NAME_SEPARATORS = " \t-\u2013\u2014:|\u2022\xb7*"

# A YouTube video, however its link is written: watch?v=, youtu.be/,
# shorts/, embed/ or live/, with whatever else after the id.
_YOUTUBE_ID = re.compile(
    r"^(?:https?://)?(?:[\w-]+\.)?"
    r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|embed/|live/)|youtu\.be/)"
    r"([\w-]{11})(?![\w-])"
)


# asked for every time a cell reads its bookmarks, of only a few files
@functools.lru_cache(maxsize=256)
def file_key(uri: Path | str) -> str:
    """What tells one file's bookmarks from another's.

    A path as Windows reads it, whatever the case of its letters, and a
    YouTube video by its id, not by the link it came in by: the same video
    from a share link and from the address bar is one video.
    """

    if isinstance(uri, Path):
        return os.path.normcase(os.path.normpath(uri))

    match = _YOUTUBE_ID.match(uri)

    if match is not None:
        return f"youtube:{match.group(1)}"

    return uri


def in_order(bookmarks) -> list[Bookmark]:
    """First to last, and only one to a place: the first of those at one."""

    by_time = {bookmark.time_ms: bookmark for bookmark in reversed(list(bookmarks))}

    return sorted(by_time.values(), key=lambda bookmark: bookmark.time_ms)


def merged(lists) -> list[Bookmark]:
    """Several lists of one file's bookmarks made one.

    Every place any of them marks, once: where two are at the same place,
    the first list's is kept, with the first name and the first colour there
    are among them, so that a name or a colour given in one is not lost to
    one left without in another.
    """

    result: list[Bookmark] = []

    for bookmarks in lists:
        for bookmark in bookmarks:
            same = next(
                (
                    i
                    for i, kept in enumerate(result)
                    if abs(kept.time_ms - bookmark.time_ms) < BOOKMARK_SAME_MS
                ),
                None,
            )

            if same is None:
                result = with_bookmark(result, bookmark)
                continue

            kept = result[same]

            missing = {
                field: getattr(bookmark, field)
                for field in ("name", "color")
                if getattr(kept, field) is None and getattr(bookmark, field) is not None
            }

            if missing:
                result[same] = kept.model_copy(update=missing)

    return result


def bookmarks_txt(bookmarks, length_ms: int, is_precise: bool = False) -> str:
    """The bookmarks as timestamps, one to a line, the way lists of
    chapters are written: where it is, then its name if it has one.

    One without a name goes as its time alone, to come back without one. The
    time goes in whole seconds, which is how sites that link timestamps
    read them, see is_timestamp_bookmarked for coming back from that; or
    precisely, to the millisecond, to come back exactly where it was.
    """

    lines = []

    for bookmark in bookmarks:
        time_txt = timestamp_txt(bookmark.time_ms, length_ms, is_precise)

        lines.append(f"{time_txt} {bookmark.name}" if bookmark.name else time_txt)

    return "\n".join(lines)


def parse_bookmarks_txt(text: str) -> list[Bookmark]:
    """The bookmarks in timestamps, one to a line, as lists of chapters
    are written or bookmarks_txt writes them; lines without one are passed
    over.

    The name is the rest of the line, on either side of the time, without
    what sets the two apart: "0:00 - Intro", "[1:02:03] Outro" and "Credits
    9:41" all name theirs.
    """

    return [bookmark for bookmark, _is_whole_second in _timestamps(text)]


def new_in_txt(bookmarks, text: str, length_ms: int) -> list[Bookmark]:
    """Those of the bookmarks in timestamps that are not there already, nor
    past the end, first to last; the first of any at one place.

    A timestamp in whole seconds is there already where a bookmark is
    anywhere in its second (is_timestamp_bookmarked); one to a fraction of a
    second, where one is as near as for any bookmark.
    """

    kept = list(bookmarks)
    new = []

    for bookmark, is_whole_second in _timestamps(text):
        time_ms = bookmark.time_ms

        if time_ms >= length_ms:
            continue

        if is_whole_second:
            is_there = is_timestamp_bookmarked(kept, time_ms)
        else:
            is_there = is_bookmarked(kept, time_ms)

        if is_there:
            continue

        kept = with_bookmark(kept, bookmark)
        new = with_bookmark(new, bookmark)

    return new


def _timestamps(text: str):
    """The bookmarks in timestamps, each with whether its time was in whole
    seconds."""

    for line in text.splitlines():
        match = _TIMESTAMP.search(line)

        if match is None:
            continue

        time_ms = parse_time_txt(match.group(0))

        if time_ms is None:
            continue

        before = line[: match.start()].rstrip().rstrip(_TIMESTAMP_BRACKETS_BEFORE)
        after = line[match.end() :].lstrip().lstrip(_TIMESTAMP_BRACKETS_AFTER)

        name = " ".join(part for part in (before, after) if part.strip())
        name = name.strip(_NAME_SEPARATORS)

        is_whole_second = match.group(4) is None

        yield Bookmark(time_ms=time_ms, name=name or None), is_whole_second


def default_bookmark_name(index: int) -> str:
    """What a bookmark goes by without a name of its own: its number among
    its file's, from 1."""

    return translate("Actions", "Bookmark {NUMBER}").format(NUMBER=index + 1)


def with_bookmark(bookmarks, bookmark: Bookmark) -> list[Bookmark]:
    """The bookmarks with one more, in its place among them."""

    added = list(bookmarks)

    insort(added, bookmark, key=lambda b: b.time_ms)

    return added


def is_bookmarked(bookmarks, time_ms: int) -> bool:
    """Whether there is a bookmark here already, near enough."""

    return any(abs(b.time_ms - time_ms) < BOOKMARK_SAME_MS for b in bookmarks)


def is_timestamp_bookmarked(bookmarks, time_ms: int) -> bool:
    """Whether there is a bookmark at a timestamp already.

    A timestamp is in whole seconds, what came after them dropped, so it
    stands for all of its second: a bookmark anywhere in it is the one it was
    written for, copied out and pasted back.
    """

    return is_bookmarked(bookmarks, time_ms) or any(
        time_ms <= b.time_ms < time_ms + 1000 for b in bookmarks
    )


def bookmark_at(bookmarks, time_ms: int) -> int | None:
    """Which bookmark the video is at, the nearest, None where it is at none."""

    near = [
        (abs(b.time_ms - time_ms), index)
        for index, b in enumerate(bookmarks)
        if abs(b.time_ms - time_ms) <= BOOKMARK_AT_MS
    ]

    return min(near)[1] if near else None


def is_in_stretch(time_ms: int, start_ms: int, end_ms: int) -> bool:
    """Whether a bookmark lies inside the stretch being played.

    One right on its end is outside: a jump there only comes back round.
    """

    return start_ms <= time_ms < end_ms


def _passing(bookmarks, reachable, time_ms: int) -> int | None:
    """The bookmark the video is at, or has only just gone past, the nearest.

    Next and Previous go on from that one to the ones either side of it,
    however near those are: marked a moment apart, each is still somewhere
    to go.
    """

    near = [
        (abs(bookmarks[index].time_ms - time_ms), index)
        for index in reachable
        if time_ms - BOOKMARK_BACK_MS
        < bookmarks[index].time_ms
        <= time_ms + BOOKMARK_AHEAD_MS
    ]

    return min(near)[1] if near else None


def bookmark_on(bookmarks, time_ms: int) -> int | None:
    """Which of these bookmarks the video is on: at, or has only just gone
    past, the nearest, as Next and Previous see it; None for none of them."""

    return _passing(bookmarks, range(len(bookmarks)), time_ms)


def next_bookmark_round(bookmarks, time_ms: int) -> int | None:
    """Which of a marker's bookmarks a click on it goes to: the one after
    the one the video is on, round to the first after the last; the first
    where it is on none of them. None where there are none."""

    if not bookmarks:
        return None

    on = bookmark_on(bookmarks, time_ms)

    if on is None:
        return 0

    return (on + 1) % len(bookmarks)


def _reachable(bookmarks, start_ms: int, end_ms: int) -> list[int]:
    return [
        index
        for index, b in enumerate(bookmarks)
        if is_in_stretch(b.time_ms, start_ms, end_ms)
    ]


def next_bookmark_index(
    bookmarks, time_ms: int, start_ms: int, end_ms: int
) -> int | None:
    """Which bookmark is next ahead, None where there are no more."""

    reachable = _reachable(bookmarks, start_ms, end_ms)

    here = _passing(bookmarks, reachable, time_ms)

    if here is None:
        ahead = [i for i in reachable if bookmarks[i].time_ms > time_ms]
    else:
        ahead = [i for i in reachable if i > here]

    return ahead[0] if ahead else None


def previous_bookmark_index(
    bookmarks, time_ms: int, start_ms: int, end_ms: int
) -> int | None:
    """Which bookmark is behind, None where there are none before."""

    reachable = _reachable(bookmarks, start_ms, end_ms)

    here = _passing(bookmarks, reachable, time_ms)

    if here is None:
        behind = [i for i in reachable if bookmarks[i].time_ms < time_ms]
    else:
        behind = [i for i in reachable if i < here]

    return behind[-1] if behind else None
