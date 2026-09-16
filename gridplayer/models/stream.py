import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional


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
        quality_lines = re.search(r"^(\d+)", quality)
        if not quality_lines:
            return self.best

        quality_lines = int(quality_lines.group(1))
        for quality_code, stream_url in reversed(self.video_streams.items()):
            stream_lines = re.search(r"^(\d+)", quality_code)
            if not stream_lines:
                continue

            stream_lines = int(stream_lines.group(1))

            if stream_lines <= quality_lines:
                return quality_code, stream_url

        return self.best
