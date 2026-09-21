import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from pydantic import UUID4, BaseModel, Field, ValidationError, model_validator
from pydantic_extra_types.color import Color

from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioPreferred,
    AudioSelection,
)
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleDisabled,
    SubtitlePreferred,
    SubtitleSelection,
)
from gridplayer.models.video_uri import VideoURI, parse_uri
from gridplayer.params.static import (
    MAX_AUDIO_DELAY_MS,
    MAX_RATE,
    MAX_SCALE,
    MAX_SUBTITLE_DELAY_MS,
    MIN_AUDIO_DELAY_MS,
    MIN_RATE,
    MIN_SCALE,
    MIN_SUBTITLE_DELAY_MS,
    AudioChannelMode,
    AudioTrackMode,
    NetworkRetryMode,
    SubtitleTrackMode,
    VideoAspect,
    VideoCrop,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.playlist_settings import PlaylistSettings, session_field

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


# What each mode a video can be set to default to comes out as. Only three
# of the six choices are here: the rest name a track, a language or a file,
# and none of those mean anything until there is a video to name them in.
_DEFAULT_AUDIO_SELECTION = {
    AudioTrackMode.DEFAULT: AudioDefault,
    AudioTrackMode.PREFERRED: AudioPreferred,
    AudioTrackMode.DISABLED: AudioDisabled,
}


def default_audio_selection() -> AudioSelection:
    """The sound a video starts on, as the defaults have it.

    A playlist carries video defaults of its own and can name a mode that
    was never one -- EXPLICIT is a per-video answer -- which is no reason
    to refuse to open it.
    """

    mode = PlaylistSettings().get("video_defaults/audio_track_mode")

    return _DEFAULT_AUDIO_SELECTION.get(mode, AudioDefault)()


# The same three of the six for subtitles. The others name a track, a
# language or a file, none of which mean anything until there is a video.
_DEFAULT_SUBTITLE_SELECTION = {
    SubtitleTrackMode.DISABLED: SubtitleDisabled,
    SubtitleTrackMode.PREFERRED: SubtitlePreferred,
    SubtitleTrackMode.DEFAULT: SubtitleDefault,
}


def default_subtitle_selection() -> SubtitleSelection:
    """The subtitles a video starts on, as the defaults have it."""

    mode = PlaylistSettings().get("video_defaults/subtitle_track_mode")

    return _DEFAULT_SUBTITLE_SELECTION.get(mode, SubtitleDisabled)()


def _audio_selection_from_legacy(data: dict) -> dict | None:
    """Read a pick that was spread over the three keys it used to take.

    The words are the ones those playlists were written with, "explicit"
    among them, which said a track had been picked by hand and left the
    other two keys to say which. Nothing recorded which of the tracks was
    an external file's, so a pick of one comes back as the id it had: the
    same track where the files are still the same, and the preference
    where they are not.
    """

    mode = data.get("audio_track_mode")
    mode = getattr(mode, "value", mode)

    if mode is None:
        return None

    if mode == "disabled":
        return {"kind": "disabled"}

    if mode == "explicit":
        language = data.get("audio_language")

        if language:
            return {"kind": "language", "tag": language}

        track_id = data.get("audio_track_id")

        if track_id is not None and track_id != -1:
            return {"kind": "track", "id": track_id}

    return {"kind": "preferred"}


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
    network_retry_mode: NetworkRetryMode = session_field(
        "video_defaults/network_retry_mode"
    )
    network_retry_times: int = session_field("video_defaults/network_retry_times")
    auto_reload_timer_min: int = session_field("video_defaults/auto_reload_timer")

    # Tracks
    video_track_id: int | None = None

    # what this video's sound was chosen to be, whichever of the five ways
    # it was chosen; see models/audio_selection.py
    audio_selection: AudioSelection = Field(default_factory=default_audio_selection)

    audio_channel_mode: AudioChannelMode = session_field("video_defaults/audio_mode")

    # how far the sound runs behind the picture, positive for later. An
    # audio file cut from another release of the same film is the reason
    # this exists, so it belongs to the video rather than to any preference
    audio_delay_ms: Annotated[
        int, Field(ge=MIN_AUDIO_DELAY_MS, le=MAX_AUDIO_DELAY_MS)
    ] = 0

    # the languages to go by where nothing was picked by hand, which is a
    # standing preference rather than a choice of track
    audio_languages: str = session_field("video_defaults/audio_languages")

    # External audio
    # files picked to play alongside this video, in the order they were
    # picked, which is the order their tracks come back in
    external_audio: list[Path] = Field(default_factory=list)
    is_external_audio_autodiscover: bool = session_field(
        "video_defaults/external_audio_autodiscover"
    )

    # Subtitles
    # what this video's subtitles were chosen to be, whichever of the six
    # ways they were chosen; see models/subtitle_selection.py
    subtitle_selection: SubtitleSelection = Field(
        default_factory=default_subtitle_selection
    )

    # how far the subtitles run behind the picture, positive for later. A
    # file cut for another release of the same video is why this exists, so
    # it belongs to the video rather than to any preference
    subtitle_delay_ms: Annotated[
        int, Field(ge=MIN_SUBTITLE_DELAY_MS, le=MAX_SUBTITLE_DELAY_MS)
    ] = 0

    # the languages to go by where nothing was picked by hand
    subtitle_languages: str = session_field("video_defaults/subtitle_languages")

    # subtitle files picked for this video, in the order they were picked,
    # which is the order their tracks come back in
    external_subtitles: list[Path] = Field(default_factory=list)
    is_external_subtitle_autodiscover: bool = session_field(
        "video_defaults/external_subtitle_autodiscover"
    )

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

        if "audio_selection" not in data:
            legacy_audio = _audio_selection_from_legacy(data)

            if legacy_audio is not None:
                data["audio_selection"] = legacy_audio

        for legacy_audio_key in (
            "audio_track_mode",
            "audio_track_id",
            "audio_language",
        ):
            data.pop(legacy_audio_key, None)

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
