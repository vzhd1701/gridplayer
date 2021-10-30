import logging
import platform

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.player.managers.actions import PlayerActionsManager
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.add_videos import AddVideosManager
from gridplayer.player.managers.dialogs import DialogsManager
from gridplayer.player.managers.drag_n_drop import PlayerDragNDropManager
from gridplayer.player.managers.grid import PlayerGridManager
from gridplayer.player.managers.instance_listener import InstanceListenerManager
from gridplayer.player.managers.log import LogManager
from gridplayer.player.managers.macos_fileopen import MacOSFileOpenManager
from gridplayer.player.managers.managers import ManagersManager
from gridplayer.player.managers.menu import PlayerMenuManager
from gridplayer.player.managers.mouse_hide import PlayerMouseHideManager
from gridplayer.player.managers.playlist import PlayerPlaylistManager
from gridplayer.player.managers.screensaver import ScreensaverManager
from gridplayer.player.managers.settings import PlayerSettingsManager
from gridplayer.player.managers.single_mode import PlayerSingleModeManager
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.player.mixins import PlayerVideoBlocksMixin

logger = logging.getLogger(__name__)


class Player(
    PlayerVideoBlocksMixin,
    QWidget,
):
    arguments_received = pyqtSignal(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.managers = self._init_managers()
        self.eventFilter = self.managers.global_event_filter

    def _init_managers(self):
        commands = {
            "active": self.cmd_active,
            "play_pause_all": self.cmd_play_pause_all,
            "loop_random": lambda: self.seek_random.emit(),
            "seek_shift_all": self.cmd_seek_shift_all,
            "is_active_param_set_to": self.is_active_param_set_to,
            "is_videos": lambda: self.is_videos,
        }

        managers_cls = {
            "fileopen": MacOSFileOpenManager,
            "driver": VideoDriverManager,
            "window_state": WindowStateManager,
            "grid": PlayerGridManager,
            "playlist": PlayerPlaylistManager,
            "screensaver": ScreensaverManager,
            "active_video": ActiveBlockManager,
            "mouse_hide": PlayerMouseHideManager,
            "drag_n_drop": PlayerDragNDropManager,
            "single_mode": PlayerSingleModeManager,
            "log": LogManager,
            "add_videos": AddVideosManager,
            "dialogs": DialogsManager,
            "settings": PlayerSettingsManager,
            "actions": PlayerActionsManager,
            "menu": PlayerMenuManager,
        }

        # MacOS has OpenFile events
        if platform.system() != "Darwin":
            managers_cls["instance_listener"] = InstanceListenerManager

        managers = ManagersManager(
            parent=self, commands=commands, managers=managers_cls
        )

        managers.connections = {
            "driver": [("s.video_count_change", "set_video_count")],
            "window_state": [("pause_on_minimize", "s.pause_all")],
            "grid": [
                ("minimum_size_changed", "window_state.set_minimum_size"),
                ("s.video_count_change", "grid.reload_video_grid"),
            ],
            "screensaver": [("s.playings_videos_count_change", "screensaver_check")],
            "mouse_hide": [
                ("s.video_count_change", "set_video_count"),
                ("mouse_hidden", "active_video.update_active_reset"),
                ("mouse_hidden", "s.hide_overlay"),
                ("mouse_shown", "active_video.update_active_under_mouse"),
            ],
            "drag_n_drop": [
                ("videos_swapped", "grid.reload_video_grid"),
                ("dropped_videos", "s.add_videos"),
                ("dropped_playlist", "playlist.load_playlist_file"),
            ],
            "single_mode": [
                ("mode_changed", "grid.adapt_grid"),
                ("s.video_count_change", "set_video_count"),
            ],
            "active_video": [("active_block_change", "s.set_active_block")],
            "settings": [
                ("reload", "s.reload_videos"),
                ("set_screensaver", "screensaver.screensaver_check"),
                ("set_log_level", "log.set_log_level"),
                ("set_log_level", "driver.set_log_level"),
                ("set_log_level_vlc", "driver.set_log_level_vlc"),
            ],
            "playlist": [
                ("s.arguments_received", "process_arguments"),
                ("playlist_closed", "s.close_all"),
                ("playlist_closed", "window_state.restore_to_minimum"),
                ("playlist_loaded", "window_state.activate_window"),
                ("window_state_loaded", "window_state.restore_window_state"),
                ("grid_mode_loaded", "grid.cmd_set_grid_mode"),
                ("videos_loaded", "s.add_videos"),
                ("alert", "window_state.activate_window"),
                ("error", "dialogs.error"),
            ],
            "fileopen": [("file_open", "s.add_videos")],
            "instance_listener": [("open_files", "s.add_videos")],
            "add_videos": [("videos_added", "s.add_videos")],
        }

        managers.event_filters = [
            "window_state",
            "mouse_hide",
            "drag_n_drop",
            "active_video",
            "single_mode",
            "playlist",
            "menu",
        ]

        managers.global_event_filters = ["fileopen"]

        managers.init()

        return managers

    def process_arguments(self, argv):
        self.arguments_received.emit(argv)
