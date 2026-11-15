"""A live DASH manifest read for the segments out now, to be served as live HLS.

mpv plays DASH with FFmpeg's reader, which can't follow a live manifest: it
reads everything listed at once, asks for segments not out yet until it gives
up (HTTP 404, or 425 Too Early from DASH-IF's own test stream), and plays what
it had, some seconds of it. FFmpeg's HLS reader follows a live playlist well.
So the proxy reads the manifest each time the player asks for the playlist
again, picks a representation, and writes what of it is out as an HLS media
playlist of the same segments: an init segment and numbered media segments,
as HLS has them in fMP4.

What's here is the reading: templates with a duration or a timeline, numbered
or timed, segment lists, base URLs at every level. Neither multi-period
splicing nor anything protected: a stream with DRM plays nowhere here.
"""

import math
import re
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from gridplayer.utils.stream_proxy.mpd import MPD_NS
from gridplayer.utils.track_language import pick_by_language

_NS = {"mpd": MPD_NS}

# "PT1H2M3.5S", "P1DT2H", "PT0S", "P0Y0M0DT0H1M0S"
_DURATION = re.compile(
    r"P(?:(?P<years>\d+(?:\.\d+)?)Y)?(?:(?P<months>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<weeks>\d+(?:\.\d+)?)W)?(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?"
)

# $RepresentationID$, $Number%05d$, $$ and the rest
_TEMPLATE_KEY = re.compile(r"\$(\w*)(?:%0(\d+)d)?\$")

# how far back a playlist goes, where the manifest allows more: the player
# starts a few segments from the end, and a long list is fetched every time
MAX_WINDOW_S = 60

# where a manifest says nothing of how far back it keeps them
DEFAULT_WINDOW_S = 30

# listed however short the window: an empty live playlist is never played
MIN_SEGMENTS = 3

# Where a timeline names its segments by time and not by number, the numbers HLS
# needs are made here. Worked out from the time alone they drift where lengths
# vary, as a sound's do, and a playlist read again would number a segment anew:
# so the numbers given last are kept, by manifest and representation, and the
# next reading goes on from them.
_numbers_lock = threading.Lock()
_numbers_given: OrderedDict[tuple[str, str], dict[int, int]] = OrderedDict()
MAX_NUMBERED = 64

# "12:00:00.5", "12:00:00.123456789": as Python 3.10 reads it, six places or none
_FRACTION = re.compile(r"\.(\d+)")


@dataclass(frozen=True)
class Segment:
    url: str
    duration: float
    # the HLS media sequence number: the same segment keeps it from one
    # reading of the manifest to the next
    sequence: int


@dataclass(frozen=True)
class Window:
    """What of a representation is out now."""

    init_url: str | None
    segments: tuple[Segment, ...]
    # the manifest says the stream is over, nothing more will come
    is_over: bool


@dataclass(frozen=True)
class Representation:
    id: str
    kind: str  # "video", "audio" or another content type
    bandwidth: int
    height: int
    language: str
    is_main: bool


class LiveManifest:
    def __init__(self, text: str, url: str, now: datetime):
        """`url` where it was served from, `now` the server's time."""

        self._root = ET.fromstring(text)
        self._now = now
        self._url_key = urlsplit(url)._replace(query="", fragment="").geturl()

        self.is_over = self._root.get("type", "static") != "dynamic"

        base = _base_of(self._root, url)

        self._period, self._period_start = self._current_period()
        self._base = _base_of(self._period, base) if self._period is not None else base

    @property
    def representations(self) -> list[Representation]:
        found = []

        for adaptation_set, representation in self._representations():
            found.append(
                Representation(
                    id=representation.get("id", ""),
                    kind=_kind_of(adaptation_set, representation),
                    bandwidth=_int(representation.get("bandwidth")),
                    height=_int(
                        representation.get("height") or adaptation_set.get("height")
                    ),
                    language=adaptation_set.get("lang", ""),
                    is_main=_is_main(adaptation_set),
                )
            )

        return found

    def pick(
        self, kind: str, max_height: int = 0, languages: tuple[str, ...] = ()
    ) -> Representation | None:
        """The video at most so tall, the best of it; the sound in the first of
        these languages there is, else the main one, the best of it."""

        of_kind = [r for r in self.representations if r.kind == kind]

        if not of_kind:
            return None

        if kind == "video":
            fitting = [
                r
                for r in of_kind
                if not max_height or not r.height or r.height <= max_height
            ]

            if not fitting:
                return min(of_kind, key=lambda r: (r.height, r.bandwidth))

            return max(fitting, key=lambda r: (r.height, r.bandwidth))

        spoken = pick_by_language(
            languages, [(r.language, r.language) for r in of_kind]
        )

        if spoken is not None:
            of_kind = [r for r in of_kind if r.language == spoken]

        return max(of_kind, key=lambda r: (r.is_main, r.bandwidth))

    def window(self, representation_id: str) -> Window:
        for adaptation_set, representation in self._representations():
            if representation.get("id", "") == representation_id:
                return self._window_of(adaptation_set, representation)

        raise LookupError(f"No representation {representation_id!r} in the manifest")

    # ---

    def _current_period(self):
        """The last period started by now: the one a live stream is in."""

        periods = self._root.findall("mpd:Period", _NS)

        if not periods:
            return None, 0.0

        current, current_start = periods[0], _seconds(periods[0].get("start"))
        elapsed = self._elapsed_s()

        for period in periods[1:]:
            start = _seconds(period.get("start"))
            if elapsed is None or start <= elapsed:
                current, current_start = period, start

        return current, current_start

    def _elapsed_s(self) -> float | None:
        """Since the stream became available, by the server's clock."""

        start = self._root.get("availabilityStartTime")

        if start is None:
            return None

        return (self._now - _datetime(start)).total_seconds()

    def _representations(self):
        if self._period is None:
            return

        for adaptation_set in self._period.findall("mpd:AdaptationSet", _NS):
            for representation in adaptation_set.findall("mpd:Representation", _NS):
                yield adaptation_set, representation

    def _window_of(self, adaptation_set, representation) -> Window:
        base = _base_of(representation, _base_of(adaptation_set, self._base))

        segment_list = _nearest(
            "SegmentList", representation, adaptation_set, self._period
        )
        if segment_list is not None:
            return self._list_window(segment_list, base)

        template = _Template(representation, adaptation_set, self._period)
        if not template.media:
            raise LookupError("Neither a segment template nor a list")

        if template.timeline is not None:
            segments = self._timeline_segments(
                template, base, representation.get("id", "")
            )
        else:
            segments = self._numbered_segments(template, base)

        init_url = (
            urljoin(base, template.fill(template.initialization))
            if template.initialization
            else None
        )

        return Window(init_url=init_url, segments=tuple(segments), is_over=self.is_over)

    def _period_now_s(self) -> float:
        """How far into the period the stream is now; a finished one, its end."""

        elapsed = self._elapsed_s()

        if elapsed is None or self.is_over:
            duration = _seconds(self._root.get("mediaPresentationDuration"))
            return max(duration - self._period_start, 0.0)

        return elapsed - self._period_start

    def _window_s(self) -> float:
        depth = self._root.get("timeShiftBufferDepth")
        window = _seconds(depth) if depth else DEFAULT_WINDOW_S

        return min(window, MAX_WINDOW_S)

    def _numbered_segments(self, template: "_Template", base: str):
        if not template.duration:
            raise LookupError("A template with neither a duration nor a timeline")

        length_s = template.duration / template.timescale
        now_s = self._period_now_s() + template.availability_offset

        # out once it has ended
        last = math.floor(now_s / length_s) - 1
        if self.is_over:
            last = math.ceil(self._period_now_s() / length_s) - 1

        count = max(math.floor(self._window_s() / length_s), MIN_SEGMENTS)
        first = max(0, last - count + 1)

        for index in range(first, last + 1):
            number = template.start_number + index
            time = template.presentation_offset + index * template.duration

            yield Segment(
                url=urljoin(base, template.fill(template.media, number, time)),
                duration=length_s,
                sequence=number,
            )

    def _timeline_segments(self, template: "_Template", base: str, representation: str):
        scale = template.timescale
        window = self._window_s() * scale

        now_t = (
            template.presentation_offset
            + (self._period_now_s() + template.availability_offset) * scale
        )

        out = [
            (index, time, duration)
            for index, time, duration in self._timeline(template, now_t, now_t - window)
            if self.is_over or time + duration <= now_t
        ]

        kept = _last(out, window)

        if not kept:
            return

        if "$Number" in template.media:
            sequences = [template.start_number + index for index, _, _ in kept]
        else:
            sequences = self._numbers_by_time(representation, template, kept)

        for (index, time, duration), sequence in zip(kept, sequences, strict=True):
            number = template.start_number + index

            yield Segment(
                url=urljoin(base, template.fill(template.media, number, time)),
                duration=duration / scale,
                sequence=sequence,
            )

    def _numbers_by_time(self, representation: str, template: "_Template", kept):
        """Going on from the numbers given these segments last time; the first
        time, by the time of the first, in its usual length."""

        key = (self._url_key, representation)
        times = [time for _, time, _ in kept]

        with _numbers_lock:
            given = _numbers_given.get(key, {})

            first = next(
                (
                    given[time] - place
                    for place, time in enumerate(times)
                    if time in given
                ),
                None,
            )

            if first is None:
                usual = Counter(duration for _, _, duration in kept).most_common(1)
                first = round((times[0] - template.presentation_offset) / usual[0][0])

            _numbers_given[key] = {
                time: first + place for place, time in enumerate(times)
            }
            _numbers_given.move_to_end(key)

            while len(_numbers_given) > MAX_NUMBERED:
                _numbers_given.popitem(last=False)

        return [first + place for place in range(len(times))]

    def _timeline(self, template: "_Template", now_t: float, from_t: float):
        """(index, time, duration) of the segments the timeline lists, in its
        timescale, from a little before from_t: those long over, as a timeline
        repeated from hours ago has, are counted past, not gone through."""

        entries = template.timeline.findall("mpd:S", _NS)
        time = template.presentation_offset
        index = 0

        for position, entry in enumerate(entries):
            if entry.get("t") is not None:
                time = int(entry.get("t"))

            duration = int(entry.get("d"))
            repeat = int(entry.get("r", "0"))

            if duration <= 0:
                raise LookupError("A timeline segment with no length")

            if repeat < 0:
                # up to the next one, or to now
                if position + 1 < len(entries) and entries[position + 1].get("t"):
                    until = int(entries[position + 1].get("t"))
                else:
                    until = now_t
                repeat = max(math.ceil((until - time) / duration) - 1, 0)

            passed = math.floor((from_t - time) / duration) - MIN_SEGMENTS
            passed = min(max(passed, 0), repeat + 1)

            index += passed
            time += passed * duration

            for _ in range(repeat + 1 - passed):
                yield index, time, duration
                index += 1
                time += duration

    def _list_window(self, segment_list, base: str) -> Window:
        timescale = _int(segment_list.get("timescale")) or 1
        duration = _int(segment_list.get("duration")) / timescale
        start_number = _int(segment_list.get("startNumber"), 1)

        initialization = segment_list.find("mpd:Initialization", _NS)
        init_url = (
            urljoin(base, initialization.get("sourceURL"))
            if initialization is not None and initialization.get("sourceURL")
            else None
        )

        urls = [
            urljoin(base, segment.get("media", ""))
            for segment in segment_list.findall("mpd:SegmentURL", _NS)
        ]

        kept = (
            max(MIN_SEGMENTS, math.floor(self._window_s() / duration))
            if duration
            else len(urls)
        )
        first = max(0, len(urls) - kept)

        return Window(
            init_url=init_url,
            segments=tuple(
                Segment(url=url, duration=duration, sequence=start_number + index)
                for index, url in enumerate(urls)
                if index >= first
            ),
            is_over=self.is_over,
        )


class _Template:
    """A segment template, its attributes looked up from the representation
    out: one set on the adaptation set or the period holds for those under it."""

    def __init__(self, *levels):
        self._representation_id = levels[0].get("id", "")
        self._bandwidth = levels[0].get("bandwidth", "")

        templates = [
            level.find("mpd:SegmentTemplate", _NS)
            for level in levels
            if level is not None
        ]
        self._templates = [t for t in templates if t is not None]

        self.media = self._get("media")
        self.initialization = self._get("initialization")
        self.timescale = _int(self._get("timescale")) or 1
        self.duration = _int(self._get("duration"))
        self.start_number = _int(self._get("startNumber"), 1)
        self.presentation_offset = _int(self._get("presentationTimeOffset"))
        # "INF" says a segment can be asked for while it's being made: taken
        # here once it's whole, as any other
        offset = float(self._get("availabilityTimeOffset") or 0)
        self.availability_offset = offset if math.isfinite(offset) else 0.0

        self.timeline = next(
            (
                found
                for found in (
                    t.find("mpd:SegmentTimeline", _NS) for t in self._templates
                )
                if found is not None
            ),
            None,
        )

    def _get(self, name: str) -> str | None:
        return next(
            (t.get(name) for t in self._templates if t.get(name) is not None), None
        )

    def fill(self, text: str, number: int = 0, time: int = 0) -> str:
        values = {
            "RepresentationID": self._representation_id,
            "Number": number,
            "Bandwidth": self._bandwidth,
            "Time": time,
        }

        def value(match):
            name, width = match[1], match[2]

            if not name:
                return "$"

            if name not in values:
                return match[0]

            if width:
                return f"{int(values[name]):0{int(width)}d}"

            return str(values[name])

        return _TEMPLATE_KEY.sub(value, text)


def _last(timed: list, span: float) -> list:
    """The last of these, (index, time, duration), as long together as span,
    and never fewer than MIN_SEGMENTS of them."""

    kept, total = [], 0

    for item in reversed(timed):
        if total >= span and len(kept) >= MIN_SEGMENTS:
            break

        kept.append(item)
        total += item[2]

    kept.reverse()

    return kept


def _nearest(tag: str, *levels):
    for level in levels:
        if level is None:
            continue
        found = level.find(f"mpd:{tag}", _NS)
        if found is not None:
            return found
    return None


def _base_of(element, base: str) -> str:
    """Where what's under this element is, by its first BaseURL."""

    found = element.find("mpd:BaseURL", _NS)

    if found is None or not (found.text or "").strip():
        return base

    return urljoin(base, found.text.strip())


def _kind_of(adaptation_set, representation) -> str:
    content = adaptation_set.get("contentType")

    if content:
        return content

    mime = representation.get("mimeType") or adaptation_set.get("mimeType") or ""

    return mime.partition("/")[0] or "video"


def _is_main(adaptation_set) -> bool:
    return any(
        role.get("value") == "main" for role in adaptation_set.findall("mpd:Role", _NS)
    )


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _seconds(text: str | None) -> float:
    if not text:
        return 0.0

    found = _DURATION.fullmatch(text.strip())

    if found is None:
        return 0.0

    parts = {name: float(value or 0) for name, value in found.groupdict().items()}

    return (
        parts["years"] * 365 * 86400
        + parts["months"] * 30 * 86400
        + parts["weeks"] * 7 * 86400
        + parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def _datetime(text: str) -> datetime:
    text = text.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    text = _FRACTION.sub(lambda found: "." + found[1][:6].ljust(6, "0"), text, count=1)

    moment = datetime.fromisoformat(text)

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment
