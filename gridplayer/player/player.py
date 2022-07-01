from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.params import env
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
from gridplayer.player.managers.snapshots import SnapshotsManager
from gridplayer.player.managers.stream_proxy import StreamProxyManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.player.managers.window_state import WindowStateManager


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
            "snapshots": SnapshotsManager,
            "screensaver": ScreensaverManager,
            "active_block": ActiveBlockManager,
            "mouse_hide": MouseHideManager,
            "drag_n_drop": DragNDropManager,
            "single_mode": SingleModeManager,
            "log": LogManager,
            "stream_proxy": StreamProxyManager,
            "add_videos": AddVideosManager,
            "dialogs": DialogsManager,
            "settings": SettingsManager,
            "actions": ActionsManager,
            "menu": MenuManager,
        }

        self.connections = {
            "window_state": [
                ("pause_on_minimize", "video_blocks.pause_all"),
            ],
            "grid": [
                ("minimum_size_changed", "window_state.set_minimum_size"),
                ("video_blocks.video_count_changed", "reload_video_grid"),
                ("video_blocks.video_order_changed", "reload_video_grid"),
            ],
            "screensaver": [
                ("video_blocks.playings_videos_count_changed", "screensaver_check")
            ],
            "mouse_hide": [
                ("video_blocks.video_count_changed", "show_cursor"),
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
            "video_blocks": [
                ("reload_all_closed", "video_driver.cleanup"),
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
                ("window_state_loaded", "window_state.restore_window_state"),
                ("grid_state_loaded", "grid.set_grid_state"),
                ("snapshots_loaded", "snapshots.set_snapshots"),
                ("seek_sync_mode_loaded", "video_blocks.set_seek_sync_mode"),
                ("shuffle_on_load_loaded", "video_blocks.set_shuffle_on_load"),
                ("disable_click_pause_loaded", "video_blocks.set_disable_click_pause"),
                ("disable_wheel_seek_loaded", "video_blocks.set_disable_wheel_seek"),
                ("videos_loaded", "video_blocks.add_videos"),
                ("alert", "window_state.activate_window"),
                ("error", "dialogs.error"),
            ],
            "snapshots": [
                ("grid_state_loaded", "grid.set_grid_state"),
                ("video_blocks.video_count_changed", "clear_snapshots"),
                ("warning", "dialogs.warning"),
            ],
            "add_videos": [
                ("videos_added", "video_blocks.add_videos"),
                ("videos_added", "window_state.activate_window"),
                ("error", "dialogs.error"),
            ],
        }

        if env.IS_MACOS:
            self.managers["macos_fileopen"] = MacOSFileOpenManager
            self.connections["macos_fileopen"] = [
                ("file_opened", "playlist.process_arguments")
            ]
            self.global_event_filters.append("macos_fileopen")
        else:
            self.managers["instance_listener"] = InstanceListenerManager
            self.connections["instance_listener"] = [
                ("files_opened", "playlist.process_arguments"),
                ("window_state.closing", "cleanup"),
            ]

        self.global_event_filters.append("mouse_hide")

        self.event_filters = [
            "window_state",
            "drag_n_drop",
            "active_block",
            "single_mode",
            "menu",
        ]

        self.init()

    def process_arguments(self, argv):
        self.arguments_received.emit(argv)
