from pathlib import Path
from typing import Iterable, List, Optional
from uuid import uuid4

from pydantic import UUID4, BaseModel, Field, ValidationError, confloat  # noqa: WPS450
from pydantic.color import Color

from gridplayer.models.video_uri import AbsoluteFilePath, VideoURI, VideoURL
from gridplayer.params.static import (
    AudioChannelMode,
    VideoAspect,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.settings import default_field

MIN_SCALE = 1.0
MAX_SCALE = 3.0
MIN_RATE = 0.2
MAX_RATE = 12


class Video(BaseModel):
    id: UUID4 = Field(default_factory=uuid4)
    uri: VideoURI

    # Presentation
    title: Optional[str]
    color: Color = Color("white")

    # Seekable video
    current_position: int = 0
    loop_start: Optional[int]
    loop_end: Optional[int]

    repeat_mode: VideoRepeat = default_field("video_defaults/repeat")
    is_start_random: bool = default_field("video_defaults/random_loop")
    rate: confloat(ge=MIN_RATE, le=MAX_RATE) = 1.0

    # Generic
    aspect_mode: VideoAspect = default_field("video_defaults/aspect")
    is_muted: bool = default_field("video_defaults/muted")
    is_paused: bool = default_field("video_defaults/paused")
    scale: confloat(ge=MIN_SCALE, le=MAX_SCALE) = 1.0
    volume: float = 1.0
    transform: VideoTransform = default_field("video_defaults/transform")

    # Streamable
    stream_quality: str = default_field("video_defaults/stream_quality")
    auto_reload_timer_min: int = default_field("video_defaults/auto_reload_timer")

    # Tracks
    audio_track_id: Optional[int]
    video_track_id: Optional[int]

    audio_channel_mode: AudioChannelMode = default_field("video_defaults/audio_mode")

    @property
    def uri_name(self) -> str:
        if isinstance(self.uri, VideoURL):
            return str(self.uri)

        return self.uri.name

    @property
    def is_local_file(self):
        return isinstance(self.uri, AbsoluteFilePath)

    @property
    def is_http_url(self):
        return isinstance(self.uri, VideoURL) and self.uri.scheme in {"http", "https"}


class VideoBlockMime(BaseModel):
    id: str
    video: Video


def filter_video_uris(uris: Iterable[str]) -> List[Video]:
    valid_urls = []

    for uri in uris:
        try:
            video = Video(uri=uri)
        except ValidationError:
            try:
                video = _convert_relative_path(uri)
            except ValidationError:
                continue

        valid_urls.append(video)

    return valid_urls


def _convert_relative_path(uri: str) -> Video:
    uri_relative = Path.cwd() / uri

    return Video(uri=uri_relative)
