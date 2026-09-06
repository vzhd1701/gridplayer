import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_extra_types.color import Color

from gridplayer.models.grid_state import GridState
from gridplayer.models.video import Video
from gridplayer.models.video_uri import parse_uri
from gridplayer.params.defaults_fields import GRID_STATE_ATTR
from gridplayer.params.static import (
    AudioChannelMode,
    DropAction,
    DropModifier,
    SeekSyncMode,
    UnsavedChangesMode,
    VideoAspect,
    VideoCrop,
    VideoRepeat,
    VideoTransform,
    WindowState,
)
from gridplayer.settings import Settings

logger = logging.getLogger(__name__)

VideosList = list[Video]


class Snapshot(BaseModel):
    grid_state: GridState
    videos: VideosList


class PlaylistVideoDefaults(BaseModel):
    aspect: VideoAspect | None = None
    transform: VideoTransform | None = None
    repeat: VideoRepeat | None = None
    audio_mode: AudioChannelMode | None = None
    random_loop: bool | None = None
    muted: bool | None = None
    paused: bool | None = None
    rate: float | None = None
    scale: float | None = None
    volume: float | None = None
    color: Color | None = None
    crop: VideoCrop | None = None
    stream_quality: str | None = None
    auto_reload_timer: int | None = None


class Playlist(BaseModel):
    grid_state: GridState = Field(default_factory=GridState)
    window_state: WindowState | None = None
    videos: VideosList | None = None
    snapshots: dict[int, Snapshot] | None = None
    seek_sync_mode: SeekSyncMode | None = None
    shuffle_on_load: bool | None = None
    disable_mouse_click_events: bool | None = None
    disable_mouse_wheel_events: bool | None = None
    disable_overlay: bool | None = None
    pause_background_videos: bool | None = None
    pause_minimized: bool | None = None
    show_overlay_border: bool | None = None
    overlay_hide_on_timeout: bool | None = None
    overlay_timeout: int | None = None
    unsaved_changes: UnsavedChangesMode | None = None
    save_window: bool | None = None
    save_position: bool | None = None
    save_state: bool | None = None
    drop_action_internal: DropAction | None = None
    drop_action_external: DropAction | None = None
    drop_modifier: DropModifier | None = None
    video_defaults: PlaylistVideoDefaults = Field(default_factory=PlaylistVideoDefaults)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_mouse_flags(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        if "disable_click_pause" in data and "disable_mouse_click_events" not in data:
            data["disable_mouse_click_events"] = data.pop("disable_click_pause")
        else:
            data.pop("disable_click_pause", None)

        if "disable_wheel_seek" in data and "disable_mouse_wheel_events" not in data:
            data["disable_mouse_wheel_events"] = data.pop("disable_wheel_seek")
        else:
            data.pop("disable_wheel_seek", None)

        return data

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_track_changes(cls, data: Any) -> Any:
        """Legacy bool "warn about unsaved changes" flag → close mode enum."""
        if not isinstance(data, dict):
            return data

        if "track_changes" not in data:
            return data

        legacy_flag = data.pop("track_changes")

        if "unsaved_changes" not in data:
            if legacy_flag is False:
                data["unsaved_changes"] = UnsavedChangesMode.DISCARD
            elif legacy_flag is True:
                data["unsaved_changes"] = UnsavedChangesMode.ASK

        return data

    @classmethod
    def read(cls, filename):
        with Path(filename).open("r", encoding="utf-8") as f:
            playlist_txt = f.read()

        return cls.parse(playlist_txt)

    @classmethod
    def parse(cls, playlist_txt):
        playlist_in = [pl.strip() for pl in playlist_txt.splitlines() if pl.strip()]

        if not playlist_in or playlist_in[0] != "#GRIDPLAYER":
            raise ValueError("Playlist format is not valid")

        playlist = cls._parse_params(playlist_in)
        playlist.videos = cls._parse_videos(playlist_in)

        return playlist

    def save(self, filename: Path):
        playlist_txt = self.dumps()

        with Path(filename).open("w", encoding="utf-8") as f:
            f.write(playlist_txt)

    def dumps(self):
        playlist_config = ["#GRIDPLAYER", "#P:" + _dump_json(_params_data(self))]

        for idx, video in enumerate(self.videos or []):
            playlist_config.append(f"#V{idx}:{_dump_json(_video_data(video, self))}")

        playlist_vids = [str(video.uri) for video in self.videos or []]

        return "\n".join([*playlist_config, *playlist_vids, ""])

    @classmethod
    def _parse_params(cls, playlist_in):
        playlist_params = (
            cls.model_validate_json(c[3:]) for c in playlist_in if c.startswith("#P:")
        )
        return next(playlist_params, cls())

    @classmethod
    def _parse_videos(cls, playlist_in):
        videos = []
        video_params = _parse_video_params(playlist_in)

        for idx, uri in enumerate(_parse_video_paths(playlist_in)):
            video_args = video_params.get(idx, {})

            video_args["uri"] = parse_uri(uri)

            try:
                videos.append(Video(**video_args))
            except ValidationError as e:
                logger.error(f"Failed to add video '{uri}'")  # noqa: TRY400
                logger.debug(e)

        return videos


def _parse_video_params(playlist_in):
    video_param_lines = (c for c in playlist_in if c.startswith("#V"))

    video_params = {}
    for vp in video_param_lines:
        v_idx, v_params = vp[2:].split(":", maxsplit=1)

        video_params[int(v_idx)] = json.loads(v_params)

    return video_params


def _parse_video_paths(playlist_in) -> list[str]:
    return [line for line in playlist_in if line and not line.startswith("#")]


def _effective_flag(playlist: Playlist, attr: str, settings_key: str) -> bool:
    value = getattr(playlist, attr)
    if value is None:
        return Settings().get(settings_key)
    return value


def _dump_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _params_data(playlist: Playlist) -> dict:
    data = playlist.model_dump(mode="json", exclude_none=True)

    data.pop("videos", None)  # videos are saved as URI lines
    if not _effective_flag(playlist, "save_window", "playlist/save_window"):
        data.pop("window_state", None)
    if not data.get("snapshots"):
        data.pop("snapshots", None)
    if not data.get("video_defaults"):
        data.pop("video_defaults", None)

    grid = _grid_state_data(playlist)
    if grid is None:
        data.pop("grid_state", None)
    else:
        data["grid_state"] = grid

    return data


def _grid_state_data(playlist: Playlist) -> dict | None:
    state = playlist.grid_state
    data = state.model_dump(mode="json", exclude_none=True)

    # Inherited keys are omitted: the next load takes them from global settings.
    for attr in GRID_STATE_ATTR.values():
        if attr not in state.model_fields_set:
            data.pop(attr, None)
    if not state.cells:
        data.pop("cells", None)
    if not state.video_order:
        data.pop("video_order", None)

    return data or None


def _video_data(video: Video, playlist: Playlist) -> dict:
    data = video.model_dump(mode="json", exclude_none=True)

    data.pop("uri", None)  # the URI is the bare line itself
    if not _effective_flag(playlist, "save_position", "playlist/save_position"):
        data.pop("current_position", None)
    if not _effective_flag(playlist, "save_state", "playlist/save_state"):
        data.pop("is_paused", None)

    return data
