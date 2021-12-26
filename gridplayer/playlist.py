import logging
import os
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from gridplayer.params import GridState
from gridplayer.params_static import WindowState
from gridplayer.settings import Settings, default_field
from gridplayer.video import Video

logger = logging.getLogger(__name__)


class Playlist(BaseModel):
    grid_state: GridState = GridState()
    window_state: Optional[WindowState]
    videos: Optional[List[Video]]
    is_seek_synced: bool = default_field("playlist/seek_synced")

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
            playlist_vids.append(str(video.file_path))

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

        for idx, path in enumerate(_parse_video_paths(playlist_in)):
            video = video_params.get(idx, Video())
            video.file_path = path

            if not video.title:
                video.title = video.file_path.name

            videos.append(video)

        return videos


def _parse_video_params(playlist_in):
    video_param_lines = (c for c in playlist_in if c.startswith("#V"))

    video_params = {}
    for vp in video_param_lines:
        v_idx, v_params = vp[2:].split(":", maxsplit=1)

        video_params[int(v_idx)] = Video.parse_raw(v_params)

    return video_params


def _parse_video_paths(playlist_in):
    video_paths = []

    video_lines = (line for line in playlist_in if line and not line.startswith("#"))

    for video_path in video_lines:
        video_path = Path(video_path)

        if not (video_path.is_file() and os.access(video_path, os.R_OK)):
            logger.warning(f"{video_path} file is not accessible!")
            continue

        video_paths.append(video_path)

    return video_paths


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
    excluded_fields_video = {"file_path"}

    exclude_list = [
        ("playlist/save_position", "current_position"),
        ("playlist/save_state", "is_paused"),
    ]

    for setting, field in exclude_list:
        if not Settings().get(setting):
            excluded_fields_video.add(field)

    return excluded_fields_video
