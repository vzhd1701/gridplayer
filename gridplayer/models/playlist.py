import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ValidationError

from gridplayer.models.grid_state import GridState
from gridplayer.models.video import Video
from gridplayer.params.static import SeekSyncMode, WindowState
from gridplayer.settings import Settings, default_field

logger = logging.getLogger(__name__)

VideosList = List[Video]


class Snapshot(BaseModel):
    grid_state: GridState
    videos: VideosList


class Playlist(BaseModel):
    grid_state: GridState = GridState()
    window_state: Optional[WindowState]
    videos: Optional[VideosList]
    snapshots: Optional[Dict[int, Snapshot]]
    seek_sync_mode: SeekSyncMode = default_field("playlist/seek_sync_mode")
    shuffle_on_load: bool = default_field("playlist/shuffle_on_load")
    disable_click_pause: bool = Settings().get("playlist/disable_click_pause")
    disable_wheel_seek: bool = Settings().get("playlist/disable_wheel_seek")

    @classmethod
    def read(cls, filename):
        with open(filename, "r", encoding="utf-8") as f:
            playlist_txt = f.read()

        return cls.parse(playlist_txt)

    @classmethod
    def parse(cls, playlist_txt):
        playlist_in = [pl.strip() for pl in playlist_txt.splitlines() if pl.strip()]

        if playlist_in[0] != "#GRIDPLAYER":
            raise ValueError("Playlist format is not valid")

        playlist = cls._parse_params(playlist_in)
        playlist.videos = cls._parse_videos(playlist_in)

        return playlist

    def save(self, filename: Path):
        playlist_txt = self.dumps()

        with open(filename, "w", encoding="utf-8") as f:
            f.write(playlist_txt)

    def dumps(self):
        playlist_config = []
        playlist_vids = []

        playlist_config.append("#GRIDPLAYER")

        playlist_config.append(
            "#P:{0}".format(
                self.json(exclude_none=True, exclude=_excluded_fields_playlist())
            )
        )

        for idx, video in enumerate(self.videos):
            playlist_config.append(
                "#V{0}:{1}".format(
                    idx,
                    video.json(exclude_none=True, exclude=_excluded_fields_video()),
                )
            )
            playlist_vids.append(str(video.uri))

        return "\n".join(playlist_config + playlist_vids + [""])

    @classmethod
    def _parse_params(cls, playlist_in):
        playlist_params = (
            cls.parse_raw(c[3:]) for c in playlist_in if c.startswith("#P:")
        )
        return next(playlist_params, cls())

    @classmethod
    def _parse_videos(cls, playlist_in):
        videos = []
        video_params = _parse_video_params(playlist_in)

        for idx, uri in enumerate(_parse_video_paths(playlist_in)):
            video_args = video_params.get(idx, {})

            video_args["uri"] = uri

            try:
                videos.append(Video(**video_args))
            except ValidationError as e:
                logger.error(f"Failed to add video '{uri}'")
                logger.debug(e)

        return videos


def _parse_video_params(playlist_in):
    video_param_lines = (c for c in playlist_in if c.startswith("#V"))

    video_params = {}
    for vp in video_param_lines:
        v_idx, v_params = vp[2:].split(":", maxsplit=1)

        video_params[int(v_idx)] = json.loads(v_params)

    return video_params


def _parse_video_paths(playlist_in) -> List[str]:
    return [line for line in playlist_in if line and not line.startswith("#")]


def _excluded_fields_playlist():
    excluded_fields_playlist = {"videos"}

    exclude_list = [
        ("playlist/save_window", "window_state"),
    ]

    for setting, field in exclude_list:
        if not Settings().get(setting):
            excluded_fields_playlist.add(field)

    return excluded_fields_playlist


def _excluded_fields_video():
    excluded_fields_video = {"uri"}

    exclude_list = [
        ("playlist/save_position", "current_position"),
        ("playlist/save_state", "is_paused"),
    ]

    for setting, field in exclude_list:
        if not Settings().get(setting):
            excluded_fields_video.add(field)

    return excluded_fields_video
