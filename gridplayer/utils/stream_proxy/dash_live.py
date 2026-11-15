"""A live DASH manifest read for the segments out now, to be served as live HLS.

mpv plays DASH with FFmpeg's reader, which can't follow a live manifest: it
reads everything listed at once, asks for segments not out yet until it gives
up (HTTP 404, or 425 Too Early from DASH-IF's own test stream), and plays what
it had, some seconds of it. FFmpeg's HLS reader follows a live playlist well.
So the proxy reads the manifest each time the player asks for the playlist
again, and writes what's out of the picture, or of the sound in one language,
as an HLS media playlist of the same segments: an init segment and media
segments, as HLS has them in fMP4.

What's served is named by what it is ("video", "audio:en"), not by a
representation's id: a stream that goes on into a new period (an ad put in, a
programme after another) is picked in it again by the same rule, the break
marked as a discontinuity, its segments numbered on.

Streamlink reads DASH too, but for its own downloader, which waits for each
segment to come out and keeps its place itself: not a list of what's out now.
"""

import itertools
import math
import re
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from isodate import Duration, ISO8601Error, parse_datetime, parse_duration

from gridplayer.utils.stream_proxy.mpd import MPD_NS
from gridplayer.utils.track_language import pick_by_language

_NS = {"mpd": MPD_NS}

# $RepresentationID$, $Number%05d$, $$ and the rest
_TEMPLATE_KEY = re.compile(r"\$(\w*)(?:%0(\d+)d)?\$")

# how far back a playlist goes, where the manifest allows more: the player
# starts a few segments from the end, and a long list is fetched every time
MAX_WINDOW_S = 60

# where a manifest says nothing of how far back it keeps them
DEFAULT_WINDOW_S = 30

# what's served: the picture, or the sound in a language ("audio:" for one
# that names none)
VIDEO = "video"
AUDIO = "audio:"

# HLS numbers its segments, and a playlist read again has to number each as it
# was. Worked out from DASH's own numbers or times they jump: where lengths vary,
# as a sound's do, from period to period, and after a while unread. So the
# numbers given last are kept, by manifest and what's served, and a reading goes
# on from them: by a segment both have, else counting on by time.
MAX_NUMBERED = 64
_numbers_lock = threading.Lock()
_numbers_given: "OrderedDict[tuple[str, str], _Numbers]" = OrderedDict()


@dataclass(frozen=True)
class Segment:
    url: str
    duration: float
    sequence: int
    # "length@offset", HLS's way, where it's a piece of a file
    byterange: str | None = None
    init_url: str | None = None
    init_byterange: str | None = None
    # the first of a period after another: its times start anew
    is_new_part: bool = False


@dataclass(frozen=True)
class Window:
    """What of the picture or the sound is out now."""

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

    @property
    def rendition(self) -> str:
        """What it's served as."""

        return VIDEO if self.kind == "video" else AUDIO + self.language


@dataclass
class _Period:
    element: ET.Element
    start: float
    end: float | None
    base: str


@dataclass(frozen=True)
class _Timed:
    """A segment of a period, its start on the stream's own time."""

    start: float
    duration: float
    url: str
    byterange: str | None
    init_url: str | None
    init_byterange: str | None
    part: int
    # its number for HLS, where nothing has been numbered yet
    hint: int


@dataclass
class _Numbers:
    by_start: dict[int, int] = field(default_factory=dict)
    last_start: int = 0
    last: int = 0


class LiveManifest:
    def __init__(self, text: str, url: str, now: datetime):
        """`url` where it was served from, `now` the server's time."""

        self._root = ET.fromstring(text)

        if self._root.tag != f"{{{MPD_NS}}}MPD":
            raise ValueError("Not a DASH manifest")

        self._now = _aware(now)
        self._url_key = urlsplit(url)._replace(query="", fragment="").geturl()

        self.is_over = self._root.get("type", "static") != "dynamic"

        start = self._root.get("availabilityStartTime")
        self._start = _datetime(start) if start else None

        self._periods = self._read_periods(_base_of(self._root, url))

    # what's on offer ---

    def representations(self) -> list[Representation]:
        """Of the period the stream is in now."""

        period = self._current_period()

        if period is None:
            return []

        return [_representation(*found) for found in _sets_of(period)]

    def pick(
        self, kind: str, max_height: int = 0, languages: tuple[str, ...] = ()
    ) -> Representation | None:
        """The video at most so tall, the best of it; the sound in the first of
        these languages there is, else the main one, the best of it."""

        return _pick(self.representations(), kind, max_height, languages)

    def sounds(self) -> list[Representation]:
        """The best sound in each language, the main one first."""

        best = {}

        for sound in self.representations():
            if sound.kind != "audio":
                continue

            known = best.get(sound.language)
            if known is None or _rank(sound) > _rank(known):
                best[sound.language] = sound

        return sorted(best.values(), key=lambda sound: not sound.is_main)

    # what's out ---

    def window(self, rendition: str, max_height: int = 0) -> Window:
        """What's out of the picture, or of the sound in a language, as far
        back as the manifest keeps it."""

        now = self._now_s()
        window = self._window_s()

        timed: list[_Timed] = []

        for part, period in enumerate(self._periods):
            if period.start > now or (
                period.end is not None and period.end < now - window
            ):
                continue

            found = self._find(period, rendition, max_height)

            if found is not None:
                timed += self._segments_of(period, part, *found, now, now - window)

        kept = _last(timed, window)

        if not kept:
            return Window(segments=(), is_over=self.is_over)

        first = self._first_number(rendition, kept)

        return Window(
            segments=tuple(
                Segment(
                    url=item.url,
                    duration=item.duration,
                    sequence=first + place,
                    byterange=item.byterange,
                    init_url=item.init_url,
                    init_byterange=item.init_byterange,
                    is_new_part=place > 0 and item.part != kept[place - 1].part,
                )
                for place, item in enumerate(kept)
            ),
            is_over=self.is_over,
        )

    # ---

    def _read_periods(self, base: str) -> list[_Period]:
        periods = []
        follows = 0.0

        for element in self._root.findall("mpd:Period", _NS):
            start = element.get("start")
            start = _seconds(start) if start is not None else follows

            duration = element.get("duration")
            end = start + _seconds(duration) if duration else None

            periods.append(_Period(element, start, end, _base_of(element, base)))

            follows = end if end is not None else start

        # one ends where the next starts
        for period, next_period in itertools.pairwise(periods):
            if period.end is None or period.end > next_period.start:
                period.end = next_period.start

        return periods

    def _now_s(self) -> float:
        """Where the stream is now, from its start; a finished one, its end."""

        if not self.is_over and self._start is not None:
            return (self._now - self._start).total_seconds()

        total = _seconds(self._root.get("mediaPresentationDuration"))

        if not total and self._periods:
            last = self._periods[-1]
            total = last.end if last.end is not None else last.start

        return total

    def _current_period(self) -> _Period | None:
        """The last one started by now."""

        now = self._now_s()

        started = [period for period in self._periods if period.start <= now]

        return (started or self._periods or [None])[-1]

    def _window_s(self) -> float:
        depth = self._root.get("timeShiftBufferDepth")
        window = _seconds(depth) if depth else DEFAULT_WINDOW_S

        return min(window, MAX_WINDOW_S)

    def _find(self, period: _Period, rendition: str, max_height: int):
        """The adaptation set and representation of a period served as this."""

        found = list(_sets_of(period))
        offered = [_representation(*pair) for pair in found]

        if rendition == VIDEO:
            picked = _pick(offered, "video", max_height)
        else:
            language = rendition.removeprefix(AUDIO)
            picked = _pick(offered, "audio", languages=(language,) if language else ())

        if picked is None:
            return None

        return found[offered.index(picked)]

    def _segments_of(self, period, part, adaptation_set, representation, now, since):
        base = _base_of(representation, _base_of(adaptation_set, period.base))
        levels = (representation, adaptation_set, period.element)

        # the lowest level that says how wins, as DASH has it
        for level in levels:
            segment_list = level.find("mpd:SegmentList", _NS)
            if segment_list is not None:
                return self._list_segments(period, part, segment_list, base, now)

            if level.find("mpd:SegmentTemplate", _NS) is not None:
                break

        template = _Template(*levels)

        if not template.media:
            raise LookupError("Neither a segment template nor a list")

        if template.timeline is not None:
            return self._timeline_segments(period, part, template, base, now, since)

        return self._numbered_segments(period, part, template, base, now, since)

    def _numbered_segments(self, period, part, template, base, now, since):
        if not template.duration:
            raise LookupError("A template with neither a duration nor a timeline")

        length = template.duration / template.timescale
        ends = period.end if period.end is not None else math.inf

        # out once it has ended, the last of a period once the period has
        if self.is_over or now >= ends:
            last = math.ceil((min(now, ends) - period.start) / length) - 1
        else:
            out_at = now - period.start + template.availability_offset
            last = math.floor(out_at / length) - 1

        first = max(0, math.floor((since - period.start) / length) - 1)

        init_url = template.init_url(base)
        segments = []

        for index in range(first, last + 1):
            number = template.start_number + index
            time = template.presentation_offset + index * template.duration

            segments.append(
                _Timed(
                    start=period.start + index * length,
                    duration=length,
                    url=urljoin(base, template.fill(template.media, number, time)),
                    byterange=None,
                    init_url=init_url,
                    init_byterange=None,
                    part=part,
                    hint=number,
                )
            )

        return segments

    def _timeline_segments(self, period, part, template, base, now, since):
        scale = template.timescale
        offset = template.presentation_offset
        ends = period.end if period.end is not None else math.inf

        def on_stream(time):
            return period.start + (time - offset) / scale

        out_by = min(now + template.availability_offset, ends)
        now_t = offset + (out_by - period.start) * scale
        since_t = offset + (since - period.start) * scale

        is_numbered = "$Number" in template.media
        init_url = template.init_url(base)
        segments = []

        for index, time, duration in _timeline(template, now_t, since_t):
            if not self.is_over and time + duration > now_t:
                continue

            if on_stream(time) >= ends:
                break

            number = template.start_number + index

            segments.append(
                _Timed(
                    start=on_stream(time),
                    duration=duration / scale,
                    url=urljoin(base, template.fill(template.media, number, time)),
                    byterange=None,
                    init_url=init_url,
                    init_byterange=None,
                    part=part,
                    hint=number if is_numbered else -1,
                )
            )

        return segments

    def _list_segments(self, period, part, segment_list, base, now):
        timescale = _int(segment_list.get("timescale")) or 1
        length = _int(segment_list.get("duration")) / timescale
        start_number = _int(segment_list.get("startNumber"), 1)

        initialization = segment_list.find("mpd:Initialization", _NS)
        init_url = init_range = None
        if initialization is not None and initialization.get("sourceURL"):
            init_url = urljoin(base, initialization.get("sourceURL"))
            init_range = _byterange(initialization.get("range"))

        segments = []

        for index, entry in enumerate(segment_list.findall("mpd:SegmentURL", _NS)):
            start = period.start + index * length

            if length and not self.is_over and start + length > now:
                break

            segments.append(
                _Timed(
                    start=start,
                    duration=length,
                    url=urljoin(base, entry.get("media", "")),
                    byterange=_byterange(entry.get("mediaRange")),
                    init_url=init_url,
                    init_byterange=init_range,
                    part=part,
                    hint=start_number + index,
                )
            )

        return segments

    def _first_number(self, rendition: str, kept: list[_Timed]) -> int:
        """The HLS number of the first of these: see _numbers_given."""

        key = (self._url_key, rendition)
        starts = [round(item.start * 1000) for item in kept]

        with _numbers_lock:
            known = _numbers_given.get(key)
            first = None

            if known is not None:
                first = next(
                    (
                        known.by_start[start] - place
                        for place, start in enumerate(starts)
                        if start in known.by_start
                    ),
                    None,
                )

                if first is None and starts[0] > known.last_start:
                    usual = _usual_length_ms(kept)
                    first = known.last + max(
                        1, round((starts[0] - known.last_start) / usual)
                    )

            if first is None:
                first = kept[0].hint

            if first < 0:
                first = round(starts[0] / _usual_length_ms(kept))

            _numbers_given[key] = _Numbers(
                by_start={start: first + place for place, start in enumerate(starts)},
                last_start=starts[-1],
                last=first + len(starts) - 1,
            )
            _numbers_given.move_to_end(key)

            while len(_numbers_given) > MAX_NUMBERED:
                _numbers_given.popitem(last=False)

        return first


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

    def init_url(self, base: str) -> str | None:
        if not self.initialization:
            return None

        return urljoin(base, self.fill(self.initialization))

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


def _timeline(template: _Template, now_t: float, since_t: float):
    """(index, time, duration) of the segments the timeline lists, in its
    timescale, from a little before since_t: those long over, as a timeline
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

        passed = math.floor((since_t - time) / duration) - 1
        passed = min(max(passed, 0), repeat + 1)

        index += passed
        time += passed * duration

        for _ in range(repeat + 1 - passed):
            yield index, time, duration
            index += 1
            time += duration


def _sets_of(period: _Period):
    for adaptation_set in period.element.findall("mpd:AdaptationSet", _NS):
        for representation in adaptation_set.findall("mpd:Representation", _NS):
            yield adaptation_set, representation


def _representation(adaptation_set, representation) -> Representation:
    return Representation(
        id=representation.get("id", ""),
        kind=_kind_of(adaptation_set, representation),
        bandwidth=_int(representation.get("bandwidth")),
        height=_int(representation.get("height") or adaptation_set.get("height")),
        language=adaptation_set.get("lang", ""),
        is_main=_is_main(adaptation_set),
    )


def _pick(
    offered: list[Representation],
    kind: str,
    max_height: int = 0,
    languages: tuple[str, ...] = (),
) -> Representation | None:
    of_kind = [r for r in offered if r.kind == kind]

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

    spoken = pick_by_language(languages, [(r.language, r.language) for r in of_kind])

    if spoken is not None:
        of_kind = [r for r in of_kind if r.language == spoken]

    return max(of_kind, key=_rank)


def _rank(sound: Representation) -> tuple[bool, int]:
    return sound.is_main, sound.bandwidth


def _last(timed: list[_Timed], span: float) -> list[_Timed]:
    """The last of these, as long together as span, and never none of them;
    no more than span, so as to leave out what the server may have let go of."""

    kept, total = [], 0.0

    for item in reversed(timed):
        if kept and total + item.duration > span + 1e-6:
            break

        kept.append(item)
        total += item.duration

    kept.reverse()

    return kept


def _usual_length_ms(kept: list[_Timed]) -> int:
    usual = Counter(round(item.duration * 1000) for item in kept).most_common(1)

    return max(usual[0][0], 1)


def _byterange(text: str | None) -> str | None:
    """DASH's "first-last" as HLS's "length@first"."""

    if not text:
        return None

    first, _, last = text.partition("-")

    return f"{int(last) - int(first) + 1}@{int(first)}"


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

    try:
        duration = parse_duration(text.strip())
    except (ISO8601Error, ValueError):
        return 0.0

    # with years or months, counted from a date
    if isinstance(duration, Duration):
        duration = duration.totimedelta(start=datetime(2000, 1, 1, tzinfo=timezone.utc))

    return duration.total_seconds()


def _datetime(text: str) -> datetime:
    return _aware(parse_datetime(text.strip()))


def _aware(moment: datetime) -> datetime:
    """A time that says no zone is taken as UTC, which is what DASH and HTTP
    mean by one."""

    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)

    return moment
