import random
from dataclasses import dataclass

from gridplayer.models.video import Video

DISABLED_TRACK = -1
NO_TRACK = frozenset((None, DISABLED_TRACK))


@dataclass
class MediaTrack:
    codec: str
    bitrate: int
    language: str | None
    description: str | None

    @property
    def codec_info(self):
        info = [self.codec]

        if self.bitrate:
            info += [f"{self.bitrate // 1024} kbps"]

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
    video_dimensions: tuple[int, int]
    fps: float | None

    @property
    def codec_info(self):
        info = [self.codec]

        if all(self.video_dimensions):
            info += ["{}x{}".format(*self.video_dimensions)]

        if self.fps:
            info += [f"{self.fps} FPS"]

        if self.bitrate:
            info += [f"{self.bitrate // 1024} kbps"]

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
            info += [f"{self.rate // 1000} kHz"]

        if self.bitrate:
            info += [f"{self.bitrate // 1024} kbps"]

        return ", ".join(info)


@dataclass
class Media:
    length: int

    video_tracks: dict[int, VideoTrack]
    audio_tracks: dict[int, AudioTrack]

    cur_audio_track_id: int | None = None
    cur_video_track_id: int | None = None

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
class MediaInput:
    uri: str
    is_live: bool
    is_audio_only: bool
    size: tuple[int, int]
    video: Video

    length: int | None = None
    _initial_seek_ms: int | None = None

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

        return random.randint(loop_start, loop_end)


class NotPausedError(Exception):
    """Exception risen when video didn't pause at the beginning"""
