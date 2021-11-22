import logging
import platform

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import ManagersManager
from gridplayer.player.managers.actions import ActionsManager
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.add_videos import AddVideosManager
from gridplayer.player.managers.dialogs import DialogsManager
from gridplayer.player.managers.drag_n_drop import DragNDropManager
from gridplayer.player.managers.grid import GridManager
from gridplayer.player.managers.instance_listener import InstanceListenerManager
from gridplayer.player.managers.log import LogManager
from gridplayer.player.managers.macos_fileopen import MacOSFileOpenManager
from gridplayer.player.managers.menu import MenuManager
from gridplayer.player.managers.mouse_hide import MouseHideManager
from gridplayer.player.managers.playlist import PlaylistManager
from gridplayer.player.managers.screensaver import ScreensaverManager
from gridplayer.player.managers.settings import SettingsManager
from gridplayer.player.managers.single_mode import SingleModeManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.player.managers.window_state import WindowStateManager

logger = logging.getLogger(__name__)


class Player(QWidget, ManagersManager):
    arguments_received = pyqtSignal(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.managers = {
            "video_driver": VideoDriverManager,
            "window_state": WindowStateManager,
            "video_blocks": VideoBlocksManager,
            "grid": GridManager,
            "playlist": PlaylistManager,
            "screensaver": ScreensaverManager,
            "active_block": ActiveBlockManager,
            "mouse_hide": MouseHideManager,
            "drag_n_drop": DragNDropManager,
            "single_mode": SingleModeManager,
            "log": LogManager,
            "add_videos": AddVideosManager,
            "dialogs": DialogsManager,
            "settings": SettingsManager,
            "actions": ActionsManager,
            "menu": MenuManager,
        }

        self.connections = {
            "video_driver": [("video_blocks.video_count_changed", "set_video_count")],
            "window_state": [("pause_on_minimize", "video_blocks.pause_all")],
            "grid": [
                ("minimum_size_changed", "window_state.set_minimum_size"),
                ("video_blocks.video_count_changed", "reload_video_grid"),
            ],
            "screensaver": [
                ("video_blocks.playings_videos_count_changed", "screensaver_check")
            ],
            "mouse_hide": [
                ("video_blocks.video_count_changed", "show_cursor"),
                ("mouse_hidden", "active_block.update_active_reset"),
                ("mouse_hidden", "video_blocks.hide_overlay"),
                ("mouse_shown", "active_block.update_active_under_mouse"),
            ],
            "active_block": [
                ("video_blocks.video_count_changed", "update_active_under_mouse")
            ],
            "drag_n_drop": [
                ("videos_swapped", "grid.reload_video_grid"),
                ("videos_dropped", "video_blocks.add_videos"),
                ("videos_dropped", "window_state.activate_window"),
                ("playlist_dropped", "playlist.load_playlist_file"),
            ],
            "single_mode": [
                ("mode_changed", "grid.adapt_grid"),
                ("video_blocks.video_count_changed", "set_video_count"),
            ],
            "settings": [
                ("reload", "video_blocks.reload_videos"),
                ("set_screensaver", "screensaver.screensaver_check"),
                ("set_log_level", "log.set_log_level"),
                ("set_log_level", "video_driver.set_log_level"),
                ("set_log_level_vlc", "video_driver.set_log_level_vlc"),
            ],
            "playlist": [
                ("s.arguments_received", "process_arguments"),
                ("playlist_closed", "video_blocks.close_all"),
                ("playlist_closed", "window_state.restore_to_minimum"),
                ("playlist_loaded", "window_state.activate_window"),
                ("window_state_loaded", "window_state.restore_window_state"),
                ("grid_state_loaded", "grid.set_grid_state"),
                ("is_seek_synced_loaded", "video_blocks.set_seek_synced"),
                ("videos_loaded", "video_blocks.add_videos"),
                ("alert", "window_state.activate_window"),
                ("error", "dialogs.error"),
            ],
            "add_videos": [
                ("videos_added", "video_blocks.add_videos"),
                ("videos_added", "window_state.activate_window"),
            ],
        }

        if platform.system() == "Darwin":
            self.managers["macos_fileopen"] = MacOSFileOpenManager
            self.connections["macos_fileopen"] = [
                ("file_opened", "playlist.process_arguments")
            ]
            self.global_event_filters.append("macos_fileopen")
        else:
            self.managers["instance_listener"] = InstanceListenerManager
            self.connections["instance_listener"] = [
                ("files_opened", "playlist.process_arguments")
            ]

        self.global_event_filters.append("mouse_hide")

        self.event_filters = [
            "window_state",
            "drag_n_drop",
            "active_block",
            "single_mode",
            "playlist",
            "menu",
        ]

        self.init()

    def process_arguments(self, argv):
        self.arguments_received.emit(argv)
