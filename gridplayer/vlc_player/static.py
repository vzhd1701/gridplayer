import random
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from gridplayer.models.video import Video

DISABLED_TRACK = -1
NO_TRACK = frozenset((None, DISABLED_TRACK))


@dataclass
class MediaTrack(object):
    codec: str
    bitrate: int
    language: Optional[str]
    description: Optional[str]

    @property
    def codec_info(self):
        info = [self.codec]

        if self.bitrate:
            info += ["{0} kbps".format(self.bitrate // 1024)]

        return ", ".join(info)

    @property
    def info(self):
        info = [self.codec_info]

        if self.language and self.description:
            info += [f"{self.language} ({self.description})"]
        else:
            if self.language:
                info += [f"{self.language}"]

            if self.description:
                info += [f"{self.description}"]

        return ", ".join(info)


@dataclass
class VideoTrack(MediaTrack):
    video_dimensions: Tuple[int, int]
    fps: Optional[float]

    @property
    def codec_info(self):
        info = [self.codec]

        if all(self.video_dimensions):
            info += ["{0}x{1}".format(*self.video_dimensions)]

        if self.fps:
            info += [f"{self.fps} FPS"]

        if self.bitrate:
            info += ["{0} kbps".format(self.bitrate // 1024)]

        return ", ".join(info)


@dataclass
class AudioTrack(MediaTrack):
    channels: int
    rate: int

    @property
    def codec_info(self):
        info = [self.codec]

        if self.channels:
            info += [f"{self.channels} ch"]

        if self.rate:
            info += ["{0} kHz".format(self.rate // 1000)]

        if self.bitrate:
            info += ["{0} kbps".format(self.bitrate // 1024)]

        return ", ".join(info)


@dataclass
class Media(object):
    length: int

    video_tracks: Dict[int, VideoTrack]
    audio_tracks: Dict[int, AudioTrack]

    cur_audio_track_id: Optional[int] = None
    cur_video_track_id: Optional[int] = None

    @property
    def is_live(self) -> bool:
        return self.length == -1

    @property
    def is_audio_only(self) -> bool:
        return not self.video_tracks or self.cur_video_track_id == DISABLED_TRACK

    @property
    def cur_video_track(self):
        if self.cur_video_track_id in NO_TRACK:
            return None
        return self.video_tracks[self.cur_video_track_id]

    @property
    def cur_audio_track(self):
        if self.cur_audio_track_id in NO_TRACK:
            return None
        return self.audio_tracks[self.cur_audio_track_id]


@dataclass
class MediaInput(object):
    uri: str
    is_live: bool
    is_audio_only: bool
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
