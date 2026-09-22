import json
import logging
from pathlib import Path
from typing import Any, NoReturn

from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_extra_types.color import Color

from gridplayer.models.audio_selection import AudioExternal
from gridplayer.models.grid_state import GridState
from gridplayer.models.subtitle_selection import SubtitleExternal
from gridplayer.models.video import Video, migrate_end_action
from gridplayer.models.video_uri import parse_uri, relativize_uri
from gridplayer.params.defaults_fields import GRID_STATE_ATTR
from gridplayer.params.static import (
    AudioChannelMode,
    AudioTrackMode,
    DropAction,
    DropModifier,
    NetworkRetryMode,
    SeekSyncMode,
    SubtitleTrackMode,
    UnsavedChangesMode,
    VideoAspect,
    VideoCrop,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
    WindowState,
)
from gridplayer.settings import Settings

logger = logging.getLogger(__name__)

FORMAT_ID = "gridplayer-playlist"
FORMAT_VERSION = 1

VideosList = list[Video]


class UnsupportedPlaylistVersion(ValueError):
    def __init__(self, version: int) -> None:
        self.version = version
        super().__init__(f"Playlist format version {version} is not supported")


def _invalid_playlist() -> NoReturn:
    raise ValueError("Playlist format is not valid")


class Snapshot(BaseModel):
    grid_state: GridState
    videos: VideosList


class PlaylistVideoDefaults(BaseModel):
    aspect: VideoAspect | None = None
    transform: VideoTransform | None = None
    end_action: VideoEndAction | None = None
    audio_mode: AudioChannelMode | None = None
    audio_track_mode: AudioTrackMode | None = None
    audio_languages: str | None = None
    external_audio_autodiscover: bool | None = None
    subtitle_track_mode: SubtitleTrackMode | None = None
    subtitle_languages: str | None = None
    subtitle_encoding: str | None = None
    external_subtitle_autodiscover: bool | None = None
    random_loop: bool | None = None
    muted: bool | None = None
    initial_state: VideoInitialState | None = None
    rate: float | None = None
    scale: float | None = None
    volume: float | None = None
    color: Color | None = None
    crop: VideoCrop | None = None
    stream_quality: str | None = None
    quality_adapt_delay: int | None = None
    network_retry_mode: NetworkRetryMode | None = None
    network_retry_times: int | None = None
    auto_reload_timer: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_paused_default(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        paused = data.pop("paused", None)
        if paused is not None and "initial_state" not in data:
            data["initial_state"] = (
                VideoInitialState.PAUSED if paused else VideoInitialState.PLAYING
            )
        if "end_action" not in data and "repeat" in data:
            data["end_action"] = data.pop("repeat")
        else:
            data.pop("repeat", None)
        if "end_action" in data:
            data["end_action"] = migrate_end_action(data["end_action"])
        return data


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
    save_paths_relative: bool | None = None
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
    def read(cls, filename: Path | str) -> "Playlist":
        playlist_txt = Path(filename).read_text(encoding="utf-8-sig")
        return cls.parse(playlist_txt, base_dir=_playlist_base_dir(filename))

    @classmethod
    def parse(cls, playlist_txt: str, base_dir: Path | None = None) -> "Playlist":
        text = playlist_txt.lstrip("\ufeff")
        stripped = text.lstrip()
        if stripped.startswith("{"):
            return cls._parse_json(stripped, base_dir)
        return cls._parse_legacy(text, base_dir)

    def save(self, filename: Path) -> None:
        Path(filename).write_text(
            self.dumps(base_dir=_playlist_base_dir(filename)), encoding="utf-8"
        )

    def dumps(self, base_dir: Path | None = None) -> str:
        relative = base_dir is not None and self._effective_flag(
            "save_paths_relative", "playlist/save_paths_relative"
        )
        params = self._params_data(base_dir, relative)
        snapshots = params.pop("snapshots", None)

        videos = []
        for video in self.videos or []:
            data = self._video_data(video)
            data["uri"] = _dump_uri(video.uri, relative, base_dir)
            _dump_external_files(
                data, "external_audio", video.external_audio, relative, base_dir
            )
            _dump_file_selection(data, "audio_selection", relative, base_dir)
            _dump_external_files(
                data,
                "external_subtitles",
                video.external_subtitles,
                relative,
                base_dir,
            )
            _dump_file_selection(data, "subtitle_selection", relative, base_dir)
            videos.append(data)

        doc: dict[str, Any] = {
            "format": FORMAT_ID,
            "version": FORMAT_VERSION,
        }
        if params:
            doc["settings"] = params
        if videos:
            doc["videos"] = videos
        if snapshots:
            doc["snapshots"] = snapshots

        return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def _parse_json(cls, playlist_txt: str, base_dir: Path | None) -> "Playlist":
        try:
            doc = json.loads(playlist_txt)
        except json.JSONDecodeError as e:
            raise ValueError("Playlist format is not valid") from e

        if not isinstance(doc, dict) or doc.get("format") != FORMAT_ID:
            _invalid_playlist()

        # Omitted version is JSON v1, not "whatever FORMAT_VERSION is now".
        version = doc.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            _invalid_playlist()
        if version > FORMAT_VERSION:
            raise UnsupportedPlaylistVersion(version)

        settings = doc.get("settings")
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            _invalid_playlist()

        payload = dict(settings)
        payload.pop("videos", None)
        payload.pop("snapshots", None)
        payload["videos"] = cls._parse_json_videos(doc.get("videos"), base_dir)
        if "snapshots" in doc:
            payload["snapshots"] = doc["snapshots"]

        playlist = cls.model_validate(payload)
        _resolve_snapshot_uris(playlist.snapshots, base_dir)
        return playlist

    @classmethod
    def _parse_json_videos(cls, videos_in: Any, base_dir: Path | None) -> list[Video]:
        if videos_in is None:
            return []
        if not isinstance(videos_in, list):
            _invalid_playlist()

        videos = []
        for video_args in videos_in:
            if not isinstance(video_args, dict):
                logger.error("Failed to add video: entry is not an object")
                continue

            uri = video_args.get("uri")
            try:
                video_args = dict(video_args)
                if uri is not None:
                    video_args["uri"] = parse_uri(uri, base_dir)
                _resolve_external_files(video_args, "external_audio", base_dir)
                _resolve_file_selection(video_args, "audio_selection", base_dir)
                _resolve_external_files(video_args, "external_subtitles", base_dir)
                _resolve_file_selection(video_args, "subtitle_selection", base_dir)
                videos.append(Video(**video_args))
            except (TypeError, ValidationError, ValueError) as e:
                logger.error(f"Failed to add video '{uri}'")  # noqa: TRY400
                logger.debug(e)

        return videos

    @classmethod
    def _parse_legacy(cls, playlist_txt: str, base_dir: Path | None) -> "Playlist":
        playlist_in = [pl.strip() for pl in playlist_txt.splitlines() if pl.strip()]

        if not playlist_in or playlist_in[0] != "#GRIDPLAYER":
            raise ValueError("Playlist format is not valid")

        playlist = cls._parse_params(playlist_in)
        playlist.videos = cls._parse_videos(playlist_in, base_dir)
        _resolve_snapshot_uris(playlist.snapshots, base_dir)

        return playlist

    @classmethod
    def _parse_params(cls, playlist_in: list[str]) -> "Playlist":
        playlist_params = (
            cls.model_validate_json(c[3:]) for c in playlist_in if c.startswith("#P:")
        )
        return next(playlist_params, cls())

    @classmethod
    def _parse_videos(
        cls, playlist_in: list[str], base_dir: Path | None = None
    ) -> list[Video]:
        videos = []
        video_params = _parse_video_params(playlist_in)

        for idx, uri in enumerate(_parse_video_paths(playlist_in)):
            video_args = video_params.get(idx, {})

            video_args["uri"] = parse_uri(uri, base_dir)
            _resolve_external_files(video_args, "external_audio", base_dir)
            _resolve_file_selection(video_args, "audio_selection", base_dir)
            _resolve_external_files(video_args, "external_subtitles", base_dir)
            _resolve_file_selection(video_args, "subtitle_selection", base_dir)

            try:
                videos.append(Video(**video_args))
            except ValidationError as e:
                logger.error(f"Failed to add video '{uri}'")  # noqa: TRY400
                logger.debug(e)

        return videos

    def _effective_flag(self, attr: str, settings_key: str) -> bool:
        value = getattr(self, attr)
        if value is None:
            return Settings().get(settings_key)
        return value

    def _params_data(
        self, base_dir: Path | None = None, relative: bool = False
    ) -> dict:
        data = self.model_dump(mode="json", exclude_none=True)

        data.pop("videos", None)  # videos are a top-level array
        if not self._effective_flag("save_window", "playlist/save_window"):
            data.pop("window_state", None)
        if not data.get("snapshots"):
            data.pop("snapshots", None)
        if not data.get("video_defaults"):
            data.pop("video_defaults", None)

        if data.get("snapshots"):
            _relativize_snapshot_uris(data["snapshots"], relative, base_dir)

        grid = self._grid_state_data()
        if grid is None:
            data.pop("grid_state", None)
        else:
            data["grid_state"] = grid

        return data

    def _grid_state_data(self) -> dict | None:
        state = self.grid_state
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

    def _video_data(self, video: Video) -> dict:
        data = video.model_dump(mode="json", exclude_none=True)

        if not self._effective_flag("save_position", "playlist/save_position"):
            data.pop("current_position", None)
        if not self._effective_flag("save_state", "playlist/save_state"):
            data.pop("playback_state", None)

        return data


def _parse_video_params(playlist_in: list[str]) -> dict[int, Any]:
    video_param_lines = (c for c in playlist_in if c.startswith("#V"))

    video_params = {}
    for vp in video_param_lines:
        v_idx, v_params = vp[2:].split(":", maxsplit=1)

        video_params[int(v_idx)] = json.loads(v_params)

    return video_params


def _parse_video_paths(playlist_in: list[str]) -> list[str]:
    return [line for line in playlist_in if line and not line.startswith("#")]


def _playlist_base_dir(filename: Path | str) -> Path:
    return Path(filename).absolute().parent


def _dump_external_files(
    video_data: dict, key: str, files, relative: bool, base_dir: Path | None
) -> None:
    """Write files kept beside a video the way the video itself is written.

    They sit next to it, so a playlist that travels with the videos has to
    carry them the same way or they would be looked for where they are not.
    The same for the audio files and for the subtitle ones, which differ
    only in the key they are written under.
    """

    if not files:
        video_data.pop(key, None)
        return

    video_data[key] = [_dump_uri(file_path, relative, base_dir) for file_path in files]


def _dump_file_selection(
    video_data: dict, key: str, relative: bool, base_dir: Path | None
) -> None:
    """Write a chosen file the same way the list it came from is written."""

    selection = video_data.get(key)

    if not isinstance(selection, dict) or selection.get("kind") != "external":
        return

    selection["file"] = _dump_uri(selection["file"], relative, base_dir)


def _resolve_file_selection(video_args: dict, key: str, base_dir: Path | None) -> None:
    selection = video_args.get(key)

    if not isinstance(selection, dict) or selection.get("kind") != "external":
        return

    selection["file"] = parse_uri(str(selection["file"]), base_dir)


def _resolve_external_files(video_args: dict, key: str, base_dir: Path | None) -> None:
    files = video_args.get(key)

    if not files:
        return

    video_args[key] = [parse_uri(str(file_path), base_dir) for file_path in files]


def _dump_uri(uri: Path | str, relative: bool, base_dir: Path | None) -> str:
    if isinstance(uri, str) and "://" in uri:
        return uri
    if relative and base_dir is not None and Path(uri).is_absolute():
        return relativize_uri(uri, base_dir)
    return str(uri)


def _resolve_snapshot_uris(
    snapshots: dict[int, Snapshot] | None, base_dir: Path | None
) -> None:
    # JSON file URIs stay str; parse_uri so they match video Path URIs.
    if not snapshots:
        return

    for snapshot in snapshots.values():
        for video in snapshot.videos:
            if isinstance(video.uri, str):
                video.uri = parse_uri(video.uri, base_dir)

            if video.external_audio:
                video.external_audio = [
                    Path(parse_uri(str(file_path), base_dir))
                    for file_path in video.external_audio
                ]

            if video.external_subtitles:
                video.external_subtitles = [
                    Path(parse_uri(str(file_path), base_dir))
                    for file_path in video.external_subtitles
                ]

            selection = video.audio_selection

            if isinstance(selection, AudioExternal):
                video.audio_selection = selection.model_copy(
                    update={"file": Path(parse_uri(str(selection.file), base_dir))}
                )

            subtitles = video.subtitle_selection

            if isinstance(subtitles, SubtitleExternal):
                video.subtitle_selection = subtitles.model_copy(
                    update={"file": Path(parse_uri(str(subtitles.file), base_dir))}
                )


def _relativize_snapshot_uris(
    snapshots: dict[Any, Any], relative: bool, base_dir: Path | None
) -> None:
    for snapshot in snapshots.values():
        for video in snapshot.get("videos") or []:
            uri = video.get("uri")
            if uri is not None:
                video["uri"] = _dump_uri(uri, relative, base_dir)

            _dump_external_files(
                video,
                "external_audio",
                video.get("external_audio") or [],
                relative,
                base_dir,
            )
            _dump_file_selection(video, "audio_selection", relative, base_dir)
            _dump_external_files(
                video,
                "external_subtitles",
                video.get("external_subtitles") or [],
                relative,
                base_dir,
            )
            _dump_file_selection(video, "subtitle_selection", relative, base_dir)
