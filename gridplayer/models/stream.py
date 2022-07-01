import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple


class HashableDict(dict):  # noqa: WPS600
    def __hash__(self):
        return hash(frozenset(self.items()))


@dataclass(frozen=True)
class StreamSessionOpts(object):
    service: str
    session_headers: Optional[HashableDict]


@dataclass(frozen=True)
class Stream(object):
    url: str
    protocol: str
    session: Optional[StreamSessionOpts] = None
    audio_tracks: Optional["Streams"] = None


class Streams(object):
    def __init__(self, streams: Optional[Dict[str, Stream]] = None):
        if streams:
            self.streams = HashableDict(streams)
        else:
            self.streams = HashableDict()

    def __hash__(self):
        return hash(self.streams)

    def __getitem__(self, key):
        return self.streams[key]

    def __setitem__(self, key, value):  # noqa: WPS110
        self.streams[key] = value

    def __len__(self):
        return len(self.streams)

    def __iter__(self):
        return iter(self.streams)

    def __reversed__(self):
        return reversed(self.streams)

    def items(self) -> Iterable[Tuple[str, Stream]]:  # noqa: WPS110
        return self.streams.items()

    @property
    def best(self) -> Tuple[str, Stream]:
        return list(self.streams.items())[-1]

    @property
    def worst(self) -> Tuple[str, Stream]:
        return list(self.streams.items())[0]

    def by_quality(self, quality: str) -> Tuple[str, Stream]:
        if quality == "best":
            return self.best

        if quality == "worst":
            return self.worst

        if self.streams.get(quality):
            return quality, self.streams[quality]

        return self._guess_quality(quality)

    def _guess_quality(self, quality: str) -> Tuple[str, Stream]:
        quality_lines = re.search(r"^(\d+)", quality)
        if not quality_lines:
            return self.best

        quality_lines = int(quality_lines.group(1))
        for quality_code, stream_url in reversed(self.streams.items()):
            stream_lines = re.search(r"^(\d+)", quality_code)
            if not stream_lines:
                continue

            stream_lines = int(stream_lines.group(1))

            if stream_lines <= quality_lines:
                return quality_code, stream_url

        return self.best
