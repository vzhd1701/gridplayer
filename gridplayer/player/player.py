import logging

from PyQt5.QtWidgets import QWidget

from gridplayer.player.managers.actions import PlayerActionsManager
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.drag_n_drop import PlayerDragNDropManager
from gridplayer.player.managers.managers import ManagersManager
from gridplayer.player.managers.menu import PlayerMenuManager
from gridplayer.player.managers.mouse_hide import PlayerMouseHideManager
from gridplayer.player.managers.screensaver import ScreensaverManager
from gridplayer.player.managers.settings import PlayerSettingsManager
from gridplayer.player.managers.single_mode import PlayerSingleModeManager
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.player.mixins import (
    PlayerCommandsMixin,
    PlayerGridMixin,
    PlayerMinorMixin,
    PlayerPlaylistMixin,
    PlayerVideoBlocksMixin,
)

logger = logging.getLogger(__name__)


class Player(  # noqa: WPS215
    PlayerCommandsMixin,
    # Base
    PlayerPlaylistMixin,
    PlayerGridMixin,
    PlayerVideoBlocksMixin,
    PlayerMinorMixin,
    QWidget,
):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._init_managers()

        self.reload_video_grid()

    def _init_managers(self):
        commands = {
            "active": self.cmd_active,
            "add_videos": self.cmd_add_videos,
            "set_grid_mode": self.cmd_set_grid_mode,
            "play_pause_all": self.cmd_play_pause_all,
            "loop_random": lambda: self.seek_random.emit(),
            "open_playlist": self.cmd_open_playlist,
            "close_playlist": self.cmd_close_playlist,
            "save_playlist": self.cmd_save_playlist,
            "seek_shift_all": self.cmd_seek_shift_all,
            "about": self.cmd_about,
            "is_active_param_set_to": self.is_active_param_set_to,
            "is_grid_mode_set_to": lambda m: self.playlist.grid_mode == m,
            "is_videos": lambda: self.is_videos,
        }

        self.managers = ManagersManager(
            parent=self,
            commands=commands,
            driver=VideoDriverManager,
            window_state=WindowStateManager,
            screensaver=ScreensaverManager,
            active_video=ActiveBlockManager,
            mouse_hide=PlayerMouseHideManager,
            drag_n_drop=PlayerDragNDropManager,
            single_mode=PlayerSingleModeManager,
            settings=PlayerSettingsManager,
            actions=PlayerActionsManager,
            menu=PlayerMenuManager,
        )

        self.managers.connections = {
            "driver": [("s.video_count_change", "set_video_count")],
            "window_state": [("pause_on_minimize", "s.pause_all")],
            "screensaver": [("s.playings_videos_count_change", "screensaver_check")],
            "mouse_hide": [
                ("s.video_count_change", "set_video_count"),
                ("mouse_hidden", "active_video.update_active_reset"),
                ("mouse_hidden", "s.hide_overlay"),
                ("mouse_shown", "active_video.update_active_under_mouse"),
            ],
            "drag_n_drop": [
                ("videos_swapped", "s.reload_video_grid"),
                ("dropped_videos", "s.add_videos"),
                ("dropped_playlist", "s.load_playlist_file"),
            ],
            "single_mode": [
                ("mode_changed", "s.adapt_grid"),
                ("s.video_count_change", "set_video_count"),
            ],
            "active_video": [("active_block_change", "s.set_active_block")],
            "settings": [
                ("reload", "s.reload_playlist"),
                ("set_screensaver", "screensaver.screensaver_check"),
                ("set_log_level", "s.set_log_level"),
                ("set_log_level", "driver.set_log_level"),
                ("set_log_level_vlc", "driver.set_log_level_vlc"),
            ],
        }

        self.managers.event_filters = [
            "window_state",
            "mouse_hide",
            "drag_n_drop",
            "active_video",
            "single_mode",
            "menu",
        ]
