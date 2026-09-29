"""The parts of YouTube videos that SponsorBlock's users have marked.

The segments are looked up once a video has resolved, on a thread of their
own, and arrive when they arrive: a video is never kept waiting on them. Not
in the resolver, which the stream proxy also runs to renew a link that has
expired, and which would then look the video up again every time; and not on
the video's resolver thread either, where a slow answer would hold up
resolving whatever that video is switched to next.

yt-dlp does the asking. It knows the API, goes out with the network settings
everyone else here does, and asks by the first characters of a hash of the
video's ID rather than by the ID itself, as SponsorBlock would have it.
"""

import logging
import math
import threading
import time
from dataclasses import dataclass, replace

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.models.sponsor_segment import SponsorSegment
from gridplayer.params.sponsorblock import (
    CATEGORY_COLORS,
    ENABLED_SETTING,
    HIGHLIGHT_CATEGORY,
    category_setting,
)
from gridplayer.params.static import SponsorBlockMode
from gridplayer.settings import Settings

_log = logging.getLogger(__name__)

# How long what a video was found to have is taken as still what it has.
# A grid of the same video, a reload, the auto-reload timer and a switch
# back to a video played a moment ago all ask again; the database changes
# more slowly than that.
LOOKUP_CACHE_SEC = 3600

# one more try before a video goes without, rather than yt-dlp's three
LOOKUP_RETRIES = 1

# Stretches to be skipped this close together are skipped as one. Users mark
# a sponsor read and the plug after it separately, and they seldom meet
# exactly; a seek on a stream costs a second or so, and there is no sense in
# landing for a moment between the two only to leave again.
SKIP_JOIN_MS = 1000

# Nothing is skipped with less than this of it left to play: on a stream the
# seek would take longer to land than the rest of it takes to play out.
SKIP_MIN_MS = 1000

# A stretch that runs to within this of where the video would stop anyway
# is taken as running to it, and ends the pass rather than being skipped.
SKIP_END_MARGIN_MS = 1000


@dataclass(frozen=True)
class SkipSpan:
    """A stretch to pass over, made of however many segments run into it."""

    start_ms: int
    end_ms: int
    # what the first of them was marked as, which is what was skipped
    category: str


def is_sponsorblock_enabled() -> bool:
    return Settings().get(ENABLED_SETTING)


def category_modes() -> dict[str, SponsorBlockMode]:
    return {
        category: Settings().get(category_setting(category))
        for category in CATEGORY_COLORS
    }


def fetch_segments(video_id: str, duration_ms: int) -> tuple[SponsorSegment, ...]:
    """Ask SponsorBlock what a YouTube video has marked, every kind of it.

    Every kind whatever the settings, so that a change to them is a change
    to what is shown rather than a reason to ask again.

    The duration is what the site says the video is: SponsorBlock keeps
    segments marked on older cuts of a video, and yt-dlp leaves out the ones
    whose video was of some other length.
    """

    # slow to import, and patches urllib3 as it does; see utils/percent_re.py
    from yt_dlp import YoutubeDL
    from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

    from gridplayer.utils.network import ytdl_network_opts
    from gridplayer.utils.percent_re import untangle_percent_re

    untangle_percent_re()

    with YoutubeDL(
        {
            "logger": _log,
            "extractor_retries": LOOKUP_RETRIES,
            **ytdl_network_opts(),
        }
    ) as ydl:
        lookup = SponsorBlockPP(ydl, categories=tuple(CATEGORY_COLORS))

        _, info = lookup.run(
            {
                "id": video_id,
                "extractor_key": "Youtube",
                "duration": duration_ms / 1000,
            }
        )

    return parse_segments(info.get("sponsorblock_chapters"))


def parse_segments(raw_segments) -> tuple[SponsorSegment, ...]:
    """The segments yt-dlp found, as far as they make any sense."""

    segments = []

    for raw in raw_segments or ():
        category = raw.get("category")

        if category not in CATEGORY_COLORS:
            continue

        start_ms = _to_ms(raw.get("start_time"))
        end_ms = _to_ms(raw.get("end_time"))

        # a database is no reason for a video not to play
        if start_ms is None or end_ms is None or start_ms < 0:
            continue

        # yt-dlp stretches a highlight out to a second, to mark it in a file
        if category == HIGHLIGHT_CATEGORY:
            end_ms = start_ms
        elif end_ms <= start_ms:
            continue

        segments.append(SponsorSegment(start_ms, end_ms, category))

    return tuple(sorted(segments, key=lambda s: (s.start_ms, s.end_ms)))


def _to_ms(seconds) -> int | None:
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
        return None

    return round(seconds * 1000)


def skip_spans(segments, modes) -> tuple[SkipSpan, ...]:
    """The stretches to pass over, those that run into each other made one.

    A sponsor read that runs into a plug for the channel is one seek, from
    the start of the one to the end of the other.
    """

    spans: list[SkipSpan] = []

    for segment in sorted(segments, key=lambda s: s.start_ms):
        if modes.get(segment.category) is not SponsorBlockMode.SKIP:
            continue

        if segment.end_ms <= segment.start_ms:
            continue

        if spans and segment.start_ms <= spans[-1].end_ms + SKIP_JOIN_MS:
            if segment.end_ms > spans[-1].end_ms:
                spans[-1] = replace(spans[-1], end_ms=segment.end_ms)
            continue

        spans.append(SkipSpan(segment.start_ms, segment.end_ms, segment.category))

    return tuple(spans)


def skip_span_at(spans, time_ms: int) -> SkipSpan | None:
    """The stretch to pass over that a time is in, None where it is in none."""

    for span in spans:
        if span.start_ms <= time_ms < span.end_ms:
            return span

    return None


class SponsorBlockFetcher(QObject):
    """Looks videos up on SponsorBlock, off the interface thread.

    One lookup per video at a time, however many cells are playing it, and
    each one answered from what was found last for a while after. A lookup
    runs on a daemon thread: one still waiting on a slow server when the app
    closes is left to be dropped with the rest of the process, rather than
    keeping it open until the server answers.
    """

    # the video's ID and its segments; () where there are none, or where
    # SponsorBlock could not be asked
    fetched = pyqtSignal(str, tuple)

    # from the lookup's thread back to this one; None where it failed
    _looked_up = pyqtSignal(str, object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._found: dict[str, tuple[float, tuple[SponsorSegment, ...]]] = {}
        self._in_flight: set[str] = set()

        self._looked_up.connect(self._on_looked_up)

    def fetch(self, video_id: str, duration_ms: int):
        """The segments at once where they are known, None where they are on
        their way through fetched."""

        found = self._found.get(video_id)

        if found is not None:
            found_at, segments = found

            if time.monotonic() - found_at < LOOKUP_CACHE_SEC:
                return segments

        if video_id not in self._in_flight:
            self._in_flight.add(video_id)

            threading.Thread(
                target=self._look_up,
                args=(video_id, duration_ms),
                name="sponsorblock",
                daemon=True,
            ).start()

        return None

    def _look_up(self, video_id: str, duration_ms: int) -> None:
        try:
            segments = fetch_segments(video_id, duration_ms)
        except Exception as e:
            _log.warning(f"SponsorBlock lookup of {video_id} failed: {e}")
            segments = None

        self._looked_up.emit(video_id, segments)

    def _on_looked_up(self, video_id: str, segments) -> None:
        self._in_flight.discard(video_id)

        # a failure is not remembered, the next play of it asks again
        if segments is None:
            segments = ()
        else:
            self._found[video_id] = (time.monotonic(), segments)

        _log.debug(f"SponsorBlock has {len(segments)} segment(s) for {video_id}")

        self.fetched.emit(video_id, segments)


_fetcher: SponsorBlockFetcher | None = None


def sponsorblock_fetcher() -> SponsorBlockFetcher:
    """The one every video asks through, made on first use."""

    global _fetcher

    if _fetcher is None:
        _fetcher = SponsorBlockFetcher()

    return _fetcher
