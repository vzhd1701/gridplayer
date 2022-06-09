import random
from dataclasses import dataclass
from typing import Optional, Tuple

from gridplayer.models.video import Video


@dataclass
class MediaTrack(object):
    is_audio_only: bool
    length: int
    video_dimensions: Tuple[int, int]
    fps: int

    @property
    def is_live(self):
        return self.length == -1


@dataclass
class MediaInput(object):
    uri: str
    is_live: bool
    size: Tuple[int, int]
    video: Video

    length: Optional[int] = None
    _initial_seek_ms: Optional[int] = None

    @property
    def initial_time(self) -> int:
        if self._initial_seek_ms is None:
            is_video_start = self.video.current_position == 0

            if not self.is_live and is_video_start and self.video.is_start_random:
                self._initial_seek_ms = self._get_random_position()
            else:
                self._initial_seek_ms = self.video.current_position

        return self._initial_seek_ms

    @initial_time.setter
    def initial_time(self, initial_seek_ms: int):
        self._initial_seek_ms = initial_seek_ms

    def _get_random_position(self) -> int:
        if self.length is None:
            raise ValueError("Length is not set")

        loop_start = self.video.loop_start or 0
        loop_end = self.video.loop_end or self.length

        return random.randint(loop_start, loop_end)  # noqa: S311


class NotPausedError(Exception):
    """Exception risen when video didn't pause at the beginning"""
