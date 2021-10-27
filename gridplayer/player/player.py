import logging

from PyQt5.QtWidgets import QWidget

from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.drag_n_drop import PlayerDragNDropManager
from gridplayer.player.managers.managers import ManagersManager
from gridplayer.player.managers.mouse_hide import PlayerMouseHideManager
from gridplayer.player.managers.screensaver import ScreensaverManager
from gridplayer.player.managers.single_mode import PlayerSingleModeManager
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.player.mixins import (
    PlayerCommandsMixin,
    PlayerGridMixin,
    PlayerMenuMixin,
    PlayerMinorMixin,
    PlayerPlaylistMixin,
    PlayerSettingsMixin,
    PlayerVideoBlocksMixin,
)

logger = logging.getLogger(__name__)


class Player(  # noqa: WPS215
    PlayerMenuMixin,
    PlayerCommandsMixin,
    PlayerSettingsMixin,
    # Base
    PlayerPlaylistMixin,
    PlayerGridMixin,
    PlayerVideoBlocksMixin,
    PlayerMinorMixin,
    QWidget,
):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.is_maximized_pre_fullscreen = False

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._init_managers()

        self.reload_video_grid()

    def _init_managers(self):
        self.managers = ManagersManager(
            parent=self,
            driver=VideoDriverManager(),
            screensaver=ScreensaverManager(),
            active_video=ActiveBlockManager(
                video_blocks=self.video_blocks, parent=self
            ),
            mouse_hide=PlayerMouseHideManager(parent=self),
            drag_n_drop=PlayerDragNDropManager(
                video_blocks=self.video_blocks, parent=self
            ),
            single_mode=PlayerSingleModeManager(
                video_blocks=self.video_blocks, parent=self
            ),
        )

        self.managers.connections = {
            "driver": [("s.video_count_change", "set_video_count")],
            "screensaver": [("s.playings_videos_count_change", "screensaver_check")],
            "mouse_hide": [
                ("s.video_count_change", "set_video_count"),
                ("mouse_hidden", "active_video.update_active_reset"),
                ("mouse_hidden", "s.hide_overlay"),
                ("mouse_shown", "active_video.update_active_under_mouse"),
            ],
            "drag_n_drop": [
                ("active_video.active_block_change", "set_active_block"),
                ("videos_swapped", "s.reload_video_grid"),
                ("dropped_videos", "s.add_videos"),
                ("dropped_playlist", "s.load_playlist_file"),
            ],
            "single_mode": [
                ("active_video.active_block_change", "set_active_block"),
                ("mode_changed", "s.adapt_grid"),
                ("s.video_count_change", "set_video_count"),
            ],
        }

        self.managers.event_filters = [
            "mouse_hide",
            "drag_n_drop",
            "active_video",
            "single_mode",
        ]
