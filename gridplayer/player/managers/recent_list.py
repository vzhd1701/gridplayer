from pathlib import Path

from PyQt5.QtCore import pyqtSignal

from gridplayer.models.recent_list import RecentListPlaylists, RecentListVideos
from gridplayer.models.video import Video
from gridplayer.models.video_uri import VideoURI
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate


class RecentListManager(ManagerBase):
    videos_added = pyqtSignal(list)
    playlist_opened = pyqtSignal(Path)

    @property
    def commands(self):
        return {
            "add_video": self.cmd_add_video,
            "clear_recent_videos": self.cmd_clear_recent_videos,
            "is_any_recent_videos": self.is_any_recent_videos,
            "menu_generator_recent_videos": self.menu_generator_recent_videos,
            "open_recent_playlist": self.cmd_open_recent_playlist,
            "clear_recent_playlists": self.cmd_clear_recent_playlists,
            "is_any_recent_playlists": self.is_any_recent_playlists,
            "menu_generator_recent_playlists": self.menu_generator_recent_playlists,
            "is_recent_list_enabled": self.is_recent_list_enabled,
        }

    def is_recent_list_enabled(self):
        return Settings().get("player/recent_list_enabled")

    def set_recent_list_state(self, is_enabled: bool) -> None:
        if not is_enabled:
            self.cmd_clear_recent_videos()
            self.cmd_clear_recent_playlists()

    def menu_generator_recent_videos(self):
        recent_videos: RecentListVideos = Settings().get("recent_list_videos")

        if not recent_videos:
            return []

        if len(recent_videos) > Settings().get("player/recent_list_max_size"):
            recent_videos.truncate(Settings().get("player/recent_list_max_size"))
            Settings().set("recent_list_videos", recent_videos)

        menu = [
            {"title": elide_uri(uri), "func": ("add_video", uri)}
            for uri in recent_videos
        ]

        menu += ["---"]
        menu += [
            {
                "title": translate("Actions", "Clear List"),
                "func": "clear_recent_videos",
            }
        ]

        return menu

    def cmd_add_video(self, uri) -> None:
        videos = [Video(uri=uri)]

        self.add_recent_videos(videos)
        self.videos_added.emit(videos)

    def cmd_clear_recent_videos(self) -> None:
        Settings().reset("recent_list_videos")

    def is_any_recent_videos(self) -> bool:
        return bool(Settings().get("recent_list_videos"))

    def add_recent_videos(self, videos: list[Video]) -> None:
        if not self.is_recent_list_enabled():
            return

        recent_videos: RecentListVideos = Settings().get("recent_list_videos")

        recent_videos.add([v.uri for v in videos])
        recent_videos.truncate(Settings().get("player/recent_list_max_size"))

        Settings().set("recent_list_videos", recent_videos)

    def menu_generator_recent_playlists(self):
        recent_playlists: RecentListPlaylists = Settings().get("recent_list_playlists")

        if not recent_playlists:
            return []

        if len(recent_playlists) > Settings().get("player/recent_list_max_size"):
            recent_playlists.truncate(Settings().get("player/recent_list_max_size"))
            Settings().set("recent_list_playlists", recent_playlists)

        menu = [
            {"title": elide_uri(path), "func": ("open_recent_playlist", path)}
            for path in recent_playlists
        ]

        menu += ["---"]
        menu += [
            {
                "title": translate("Actions", "Clear List"),
                "func": "clear_recent_playlists",
            }
        ]

        return menu

    def cmd_open_recent_playlist(self, path) -> None:
        self.playlist_opened.emit(path)

    def cmd_clear_recent_playlists(self) -> None:
        Settings().reset("recent_list_playlists")

    def is_any_recent_playlists(self) -> bool:
        return bool(Settings().get("recent_list_playlists"))

    def add_recent_playlist(self, path: Path) -> None:
        if not self.is_recent_list_enabled():
            return

        recent_playlists = Settings().get("recent_list_playlists")

        recent_playlists.add([path])
        recent_playlists.truncate(Settings().get("player/recent_list_max_size"))

        Settings().set("recent_list_playlists", recent_playlists)


def elide_uri(uri: VideoURI, max_length: int = 100) -> str:
    if len(str(uri)) <= max_length:
        return str(uri)

    if isinstance(uri, Path) and len(uri.name) <= max_length:
        return uri.name

    if isinstance(uri, Path):
        return elide_str(uri.name, max_length)

    return elide_str(str(uri), max_length)


def elide_str(s: str, max_length: int) -> str:
    if len(s) <= max_length:
        return s

    half_length = max_length // 2

    return s[:half_length] + "..." + s[-half_length:]
