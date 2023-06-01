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
    is_audio_only: bool = False
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
    def video_streams(self) -> Dict[str, Stream]:
        return {k: v for k, v in self.streams.items() if not v.is_audio_only}

    @property
    def audio_only_streams(self) -> Dict[str, Stream]:
        return {k: v for k, v in self.streams.items() if v.is_audio_only}

    @property
    def best_audio_only(self) -> Optional[Tuple[str, Stream]]:
        if not self.audio_only_streams:
            return None

        return list(self.audio_only_streams.items())[-1]

    @property
    def worst_audio_only(self) -> Optional[Tuple[str, Stream]]:
        if not self.audio_only_streams:
            return None

        return list(self.audio_only_streams.items())[0]

    @property
    def best(self) -> Tuple[str, Stream]:
        if self.video_streams:
            return list(self.video_streams.items())[-1]

        return self.best_audio_only

    @property
    def worst(self) -> Tuple[str, Stream]:
        if self.video_streams:
            return list(self.video_streams.items())[0]

        return self.worst_audio_only

    def by_quality(self, quality: str) -> Tuple[str, Stream]:
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

    def _guess_quality(self, quality: str) -> Tuple[str, Stream]:
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
