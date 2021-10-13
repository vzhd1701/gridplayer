import logging
import os

from gridplayer.params import PlaylistParams, VideoParams
from gridplayer.settings import settings

logger = logging.getLogger(__name__)


def parse_playlist(playlist_txt):
    playlist_in = [l.strip() for l in playlist_txt.splitlines() if l.strip()]

    playlist = {
        "params": None,
        "videos": [],
    }

    params_vids = {}

    if playlist_in[0] == "#GRIDPLAYER":
        config_lines = (line for line in playlist_in if line.startswith("#"))

        for config in config_lines:
            if config.startswith("#P:"):
                playlist["params"] = PlaylistParams.parse_raw(config[3:])
            if config.startswith("#V"):
                video_idx, video_params = config[2:].split(":", maxsplit=1)
                params_vids[int(video_idx)] = VideoParams.parse_raw(video_params)

    video_lines = (line for line in playlist_in if not line.startswith("#") and line)

    for video_idx, video_path in enumerate(video_lines):
        video_path = os.path.normpath(video_path)

        if not (os.path.isfile(video_path) and os.access(video_path, os.R_OK)):
            logger.warning(f"{video_path} file is not accessible!")
            continue

        video_params = params_vids.get(video_idx)

        playlist["videos"].append({"path": video_path, "params": video_params})

    return playlist


def dumps_playlist(playlist):
    playlist_config = []
    playlist_vids = []

    excluded_fields_playlist = set()
    excluded_fields_video = set()

    if not settings.get("playlist/save_window"):
        excluded_fields_playlist.add("window_state")

    if not settings.get("playlist/save_position"):
        excluded_fields_video.add("current_position")

    if not settings.get("playlist/save_state"):
        excluded_fields_video.add("is_paused")

    playlist_config.append("#GRIDPLAYER")

    if playlist["params"]:
        playlist_config.append(
            "#P:{0}".format(
                playlist["params"].json(
                    exclude_none=True, exclude=excluded_fields_playlist
                )
            )
        )

    for idx, vid in enumerate(playlist["videos"]):
        if vid["params"]:
            playlist_config.append(
                "#V{0}:{1}".format(
                    idx,
                    vid["params"].json(
                        exclude_none=True, exclude=excluded_fields_video
                    ),
                )
            )
        playlist_vids.append(vid["path"])

    return "\n".join(playlist_config + playlist_vids + [""])


def read_playlist(filename):
    with open(filename, "r", encoding="utf-8") as f:
        playlist = f.read()

    return parse_playlist(playlist)


def save_playlist(filename, playlist):
    playlist_txt = dumps_playlist(playlist)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(playlist_txt)
