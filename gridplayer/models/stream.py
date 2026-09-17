import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

from gridplayer.utils.track_language import parse_preferences, pick_by_language


class HashableDict(dict):
    def __hash__(self):
        return hash(frozenset(self.items()))


@dataclass(frozen=True)
class StreamSessionOpts:
    service: str
    session_headers: HashableDict | None


# what the proxy answers with a playlist instead of the media itself, which
# VLC opens with its "adaptive" demuxer
ADAPTIVE_PROTOCOLS = frozenset({"hls", "hls_proxy", "dash", "http_hls"})

# a standing instruction to fit the stream to the pane rather than a rung of
# the quality ladder, so it is not resolved away the way "best" is
STREAM_QUALITY_AUTO = "auto"


@dataclass(frozen=True)
class StreamOrigin:
    """Where a stream came from, so that it can be resolved again.

    Services hand out signed URLs that stop working after a while, and there
    is nothing in such a URL to repair once it has: the page it was resolved
    from has to be resolved anew to get another one.
    """

    url: str
    quality: str
    audio_track: str | None = None


@dataclass(frozen=True)
class StreamFragment:
    """A single segment of a fragmented stream (DASH segment, byte range, ...)."""

    url: str
    duration: float = 0.0
    byterange: str | None = None


@dataclass(frozen=True)
class Stream:
    url: str
    protocol: str
    is_audio_only: bool = False
    video_codec: str | None = None
    # what the source calls the language of this stream's audio, in whatever
    # spelling it uses; see gridplayer.utils.track_language
    language: str | None = None
    # the language the video was made in, as opposed to dubbed into, which
    # is the one to fall back on when the viewer asked for none of them
    is_original_language: bool = False
    session: StreamSessionOpts | None = None
    audio_tracks: Optional["Streams"] = None
    fragments: tuple[StreamFragment, ...] | None = None
    init_fragment: StreamFragment | None = None
    duration: float = 0.0
    origin: StreamOrigin | None = None

    @property
    def is_adaptive(self) -> bool:
        """VLC opens this with its adaptive demuxer rather than a plain one.

        That demuxer restarts the video decoder on every seek, where a plain
        one just seeks. A manifest handed over untouched is demuxed adaptively
        too, but only a live one ever is, and a live stream cannot be seeked.
        """

        return bool(self.audio_tracks) or self.protocol in ADAPTIVE_PROTOCOLS

    @property
    def is_complex(self) -> bool:
        """Stream carries data that does not fit into a proxy URL query."""

        return bool(self.audio_tracks or self.fragments or self.duration)

    @property
    def is_refreshable(self) -> bool:
        """Stream knows where it came from, so its URLs can be renewed."""

        return self.origin is not None


class Streams:
    def __init__(self, streams: dict[str, Stream] | None = None):
        if streams:
            self.streams = HashableDict(streams)
        else:
            self.streams = HashableDict()

    def __hash__(self):
        return hash(self.streams)

    def __getitem__(self, key):
        return self.streams[key]

    def __setitem__(self, key, value):
        self.streams[key] = value

    def __len__(self):
        return len(self.streams)

    def __iter__(self):
        return iter(self.streams)

    def __contains__(self, key):
        return key in self.streams

    def __reversed__(self):
        return reversed(self.streams)

    def items(self) -> Iterable[tuple[str, Stream]]:
        return self.streams.items()

    @property
    def video_streams(self) -> dict[str, Stream]:
        return {k: v for k, v in self.streams.items() if not v.is_audio_only}

    @property
    def audio_only_streams(self) -> dict[str, Stream]:
        return {k: v for k, v in self.streams.items() if v.is_audio_only}

    @property
    def best_audio_only(self) -> tuple[str, Stream] | None:
        if not self.audio_only_streams:
            return None

        return list(self.audio_only_streams.items())[-1]

    @property
    def worst_audio_only(self) -> tuple[str, Stream] | None:
        if not self.audio_only_streams:
            return None

        return next(iter(self.audio_only_streams.items()))

    @property
    def best(self) -> tuple[str, Stream]:
        if self.video_streams:
            return list(self.video_streams.items())[-1]

        return self.best_audio_only

    @property
    def worst(self) -> tuple[str, Stream]:
        if self.video_streams:
            return next(iter(self.video_streams.items()))

        return self.worst_audio_only

    @property
    def languages(self) -> tuple[str, ...]:
        """The distinct languages these streams are offered in.

        A rung that names no language is not a language of its own: plenty
        of ladders tag nothing at all, and that makes them monolingual
        rather than a ladder in the unnamed language.
        """

        languages = (
            stream.language for stream in self.streams.values() if stream.language
        )

        return tuple(dict.fromkeys(languages))

    @property
    def is_multilingual(self) -> bool:
        """There is a language here worth choosing between."""

        return len(self.languages) > 1

    @property
    def original_language(self) -> str | None:
        """The language the video was made in, where the source says."""

        return next(
            (
                stream.language
                for stream in self.streams.values()
                if stream.is_original_language and stream.language
            ),
            None,
        )

    def language_for(self, preferences: str) -> str | None:
        """Which of these languages to play, given the ones asked for.

        Nothing to choose between is not a choice, so a ladder offered in
        a single language answers with none at all.
        """

        if not self.is_multilingual:
            return None

        languages = self.languages

        preferred = pick_by_language(
            parse_preferences(preferences),
            [(language, language) for language in languages],
        )

        # falling back on the language the video was made in, rather than
        # on whichever dub the site happened to list first
        return preferred or self.original_language or languages[0]

    def for_language(self, language: str | None) -> "Streams":
        """The rungs carrying one language, out of a ladder that mixes several.

        Sites that dub a video hand back the whole ladder once per language,
        so picking a size means picking a language too unless the ones
        nobody asked for are set aside first.
        """

        if not language:
            return self

        matching = {
            name: stream
            for name, stream in self.streams.items()
            if stream.language == language or _is_language_neutral(stream)
        }

        # a language that answers for nothing here is no reason to offer
        # an empty ladder
        return Streams(matching) if matching else self

    def fit_to_height(self, height: int) -> tuple[str, Stream]:
        """Pick the cheapest rung that still fills a box this tall.

        Anything below the box would be upscaled into a blurrier picture than
        the pane can show, so the smallest one that is not is the best deal.
        """

        for quality, stream in self.video_streams.items():
            stream_height = _quality_height(quality)

            if stream_height is not None and stream_height >= height:
                return quality, stream

        return self.best

    def by_quality(self, quality: str) -> tuple[str, Stream]:
        standard_quality_map = {
            "best": self.best,
            "worst": self.worst,
            "best_audio_only": self.best_audio_only,
            "worst_audio_only": self.worst_audio_only,
        }

        if standard_quality_map.get(quality):
            return standard_quality_map[quality]

        if self.streams.get(quality):
            return quality, self.streams[quality]

        return self._guess_quality(quality)

    def _guess_quality(self, quality: str) -> tuple[str, Stream]:
        quality_lines = _quality_height(quality)
        if quality_lines is None:
            return self.best

        for quality_code, stream_url in reversed(self.video_streams.items()):
            stream_lines = _quality_height(quality_code)
            if stream_lines is None:
                continue

            if stream_lines <= quality_lines:
                return quality_code, stream_url

        return self.best


def _is_language_neutral(stream: Stream) -> bool:
    """A rung that belongs to no language and stands in the way of none.

    A silent rung takes its language from whichever audio track is paired
    with it, so every language has the same claim on it. A rung that
    carries its own untagged sound is a different matter: it is in some
    language nobody can name, so it only gets in the way of the ones
    that can be.
    """

    return stream.language is None and bool(stream.audio_tracks)


def _quality_height(quality: str) -> int | None:
    """How tall a stream a quality code promises, where it says so at all.

    Codes are whatever the service called the format, so "1080p60 [vp9]" is
    as good as it gets and "Unknown 2" has nothing to go on.
    """

    height = re.match(r"^(\d+)", quality)

    return int(height.group(1)) if height else None
