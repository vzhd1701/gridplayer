"""Finding the way around a video by its chapters.

A jump lands on a stop: where a chapter starts, or where the stretch being
played starts. That stretch is the whole video, or the loop where one is set,
and a chapter that starts outside of it has nowhere to be jumped to.
"""

from bisect import bisect_right

from gridplayer.models.chapter import Chapter

# VLC reports the time a hair short of where a seek landed -- 10ms before a
# chapter's start, measured on mkv, mp4 and m4a alike -- so a video sitting
# on the start of a chapter reads as still being in the one before. Anything
# this close to where a chapter starts counts as being in it.
CHAPTER_TOLERANCE_MS = 250

# Going back from further into a chapter than this starts the same chapter
# over, as VLC does. Only near its start does it go to the one before.
CHAPTER_RESTART_MS = 3000

# How far the length of what plays may be from the length the site gives
# before the site's chapters are taken to be for some other cut of it: the
# larger of the two. A site rounds to the second and a stream can run a
# little over; adverts spliced into the stream, or a preview in place of the
# video, put it out by far more.
SITE_LENGTH_SLACK_MS = 5000
SITE_LENGTH_SLACK_RATIO = 0.02


def clean_chapters(chapters, length: int) -> tuple[Chapter, ...]:
    """The chapters worth offering, in order and each only once.

    Files get this wrong in every way there is: out of order, twice over,
    past the end, or one chapter covering the whole video, which is no
    chapter at all. One that starts a moment in starts at the beginning.
    """

    cleaned: dict[int, Chapter] = {}

    for chapter in sorted(chapters, key=lambda c: c.start_ms):
        start_ms = chapter.start_ms

        if start_ms < 0 or (length > 0 and start_ms >= length):
            continue

        if start_ms < CHAPTER_TOLERANCE_MS:
            start_ms = 0

        if start_ms in cleaned:
            continue

        cleaned[start_ms] = Chapter(start_ms=start_ms, name=_clean_name(chapter.name))

    if not any(start_ms > 0 for start_ms in cleaned):
        return ()

    return tuple(cleaned.values())


def _clean_name(name: str | None) -> str | None:
    # mkv names come with a space in front of them
    if name is None:
        return None

    return name.strip() or None


def is_site_length_playing(length: int, site_length_ms: int) -> bool:
    """Whether what plays is as long as the site says, near enough.

    Either one unknown leaves nothing to go against, which counts as yes.
    """

    if length <= 0 or site_length_ms <= 0:
        return True

    slack_ms = max(SITE_LENGTH_SLACK_MS, site_length_ms * SITE_LENGTH_SLACK_RATIO)

    return abs(length - site_length_ms) <= slack_ms


def chapter_index_at(chapters, time_ms: int) -> int | None:
    """Which chapter the video is in, None before the first one starts."""

    starts = [chapter.start_ms for chapter in chapters]

    index = bisect_right(starts, time_ms + CHAPTER_TOLERANCE_MS) - 1

    return index if index >= 0 else None


def chapter_span(chapters, index: int, length: int) -> tuple[int, int]:
    """Where a chapter starts and where the next one takes over."""

    start_ms = chapters[index].start_ms

    if index + 1 < len(chapters):
        return start_ms, chapters[index + 1].start_ms

    return start_ms, length


def span_at(chapters, time_ms: int, length: int) -> tuple[int, int]:
    """The stretch between chapter starts that the video is in.

    Before the first chapter that is the stretch leading up to it, which
    is no chapter of the file's but is still somewhere to be.
    """

    index = chapter_index_at(chapters, time_ms)

    if index is None:
        return 0, chapters[0].start_ms if chapters else length

    return chapter_span(chapters, index, length)


def is_span_reachable(span: tuple[int, int], start_ms: int, end_ms: int) -> bool:
    """Whether any of this stretch is inside the one being played."""

    return span[0] < end_ms and span[1] > start_ms


def chapter_stops(chapters, start_ms: int, end_ms: int) -> list[int]:
    """Where a jump can land, between start_ms and end_ms."""

    inside = {c.start_ms for c in chapters if start_ms < c.start_ms < end_ms}

    return sorted({start_ms, *inside})


def next_stop(chapters, time_ms: int, start_ms: int, end_ms: int) -> int | None:
    """Where the next chapter starts, None where the last one is playing."""

    for stop in chapter_stops(chapters, start_ms, end_ms):
        if stop > time_ms + CHAPTER_TOLERANCE_MS:
            return stop

    return None


def previous_stop(chapters, time_ms: int, start_ms: int, end_ms: int) -> int:
    """Where going back a chapter lands: this one's start, or the one before."""

    stops = chapter_stops(chapters, start_ms, end_ms)

    index = max(bisect_right(stops, time_ms + CHAPTER_TOLERANCE_MS) - 1, 0)

    if time_ms - stops[index] > CHAPTER_RESTART_MS:
        return stops[index]

    return stops[max(index - 1, 0)]
