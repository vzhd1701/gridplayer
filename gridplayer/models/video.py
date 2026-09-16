import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from pydantic import UUID4, BaseModel, Field, ValidationError, model_validator
from pydantic_extra_types.color import Color

from gridplayer.models.video_uri import VideoURI, parse_uri
from gridplayer.params.static import (
    MAX_RATE,
    MAX_SCALE,
    MIN_RATE,
    MIN_SCALE,
    AudioChannelMode,
    VideoAspect,
    VideoCrop,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.playlist_settings import session_field

_LEGACY_END_ACTION = {
    "none": VideoEndAction.STOP,
    "single_file": VideoEndAction.LOOP_FILE,
    "dir": VideoEndAction.NEXT_FILE,
    "dir_shuffle": VideoEndAction.SHUFFLE_FILE,
}


def migrate_end_action(value):
    if isinstance(value, str):
        return _LEGACY_END_ACTION.get(value, value)
    return value


def _playback_state_from_legacy(data: dict):
    if data.get("is_stopped"):
        return VideoInitialState.STOPPED
    if "is_paused" in data:
        if data["is_paused"]:
            return VideoInitialState.PAUSED
        return VideoInitialState.PLAYING
    return None


class Video(BaseModel):
    id: UUID4 = Field(default_factory=uuid4)
    uri: VideoURI

    # Presentation
    title: str | None = None
    color: Color = session_field("video_defaults/color", validate=True)

    # Seekable video
    current_position: int = 0
    loop_start: int | None = None
    loop_end: int | None = None

    end_action: VideoEndAction = session_field("video_defaults/end_action")
    is_start_random: bool = session_field("video_defaults/random_loop")
    rate: Annotated[float, Field(ge=MIN_RATE, le=MAX_RATE)] = session_field(
        "video_defaults/rate"
    )

    # Generic
    aspect_mode: VideoAspect = session_field("video_defaults/aspect")
    is_muted: bool = session_field("video_defaults/muted")
    playback_state: VideoInitialState = session_field("video_defaults/initial_state")
    scale: Annotated[float, Field(ge=MIN_SCALE, le=MAX_SCALE)] = session_field(
        "video_defaults/scale"
    )
    crop: VideoCrop = session_field("video_defaults/crop")
    volume: float = session_field("video_defaults/volume")
    transform: VideoTransform = session_field("video_defaults/transform")

    # Streamable
    stream_quality: str = session_field("video_defaults/stream_quality")
    quality_adapt_delay_sec: int = session_field("video_defaults/quality_adapt_delay")
    auto_reload_timer_min: int = session_field("video_defaults/auto_reload_timer")

    # Tracks
    audio_track_id: int | None = None
    video_track_id: int | None = None

    audio_channel_mode: AudioChannelMode = session_field("video_defaults/audio_mode")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "playback_state" not in data:
            legacy_state = _playback_state_from_legacy(data)
            if legacy_state is not None:
                data["playback_state"] = legacy_state
        data.pop("is_paused", None)
        data.pop("is_stopped", None)
        if "end_action" not in data and "repeat_mode" in data:
            data["end_action"] = data.pop("repeat_mode")
        else:
            data.pop("repeat_mode", None)
        if "end_action" in data:
            data["end_action"] = migrate_end_action(data["end_action"])
        return data

    @property
    def is_paused(self) -> bool:
        return self.playback_state != VideoInitialState.PLAYING

    @property
    def is_stopped(self) -> bool:
        return self.playback_state == VideoInitialState.STOPPED

    @property
    def uri_name(self) -> str:
        if isinstance(self.uri, Path):
            return self.uri.name

        return str(self.uri)

    @property
    def is_local_file(self):
        return isinstance(self.uri, Path) and self.uri.is_absolute()

    @property
    def is_http_url(self):
        return isinstance(self.uri, str) and self.uri.startswith(("http", "https"))


class VideoBlockMime(BaseModel):
    id: str
    video: Video


def filter_video_uris(uris: Iterable[str]) -> list[Video]:
    valid_urls = []

    for uri in uris:
        try:
            video = Video(uri=parse_uri(uri))
        except ValidationError as e:
            logging.getLogger("filter_video_uris").error(str(e))  # noqa: TRY400
            continue

        valid_urls.append(video)

    return valid_urls
