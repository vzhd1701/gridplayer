import logging

from PyQt5.QtWidgets import QWidget

from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.drag_n_drop import PlayerDragNDropManager
from gridplayer.player.managers.mouse_hide import PlayerMouseHideManager
from gridplayer.player.managers.screensaver import ScreensaverManager
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.player.mixins import (  # noqa: WPS235
    PlayerCommandsMixin,
    PlayerGridMixin,
    PlayerMenuMixin,
    PlayerMinorMixin,
    PlayerPlaylistMixin,
    PlayerSettingsMixin,
    PlayerSingleModeMixin,
    PlayerVideoBlocksMixin,
)
from gridplayer.utils.misc import qt_connect

logger = logging.getLogger(__name__)


class Player(  # noqa: WPS215
    PlayerMenuMixin,
    PlayerCommandsMixin,
    PlayerSettingsMixin,
    # Utilities
    PlayerSingleModeMixin,
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
        self.driver_mgr = VideoDriverManager()
        self.video_count_change.connect(self.driver_mgr.set_video_count)

        self.screensaver_mgr = ScreensaverManager()
        self.playings_videos_count_change.connect(
            self.screensaver_mgr.screensaver_check
        )

        self.active_video_mgr = ActiveBlockManager(
            video_blocks=self.video_blocks, parent=self
        )

        self.mouse_hide_mgr = PlayerMouseHideManager(parent=self)
        qt_connect(
            (self.video_count_change, self.mouse_hide_mgr.set_video_count),
            (
                self.mouse_hide_mgr.mouse_hidden,
                self.active_video_mgr.update_active_reset,
            ),
            (self.mouse_hide_mgr.mouse_hidden, self.hide_overlay),
            (
                self.mouse_hide_mgr.mouse_shown,
                self.active_video_mgr.update_active_under_mouse,
            ),
        )

        self.drag_n_drop_mgr = PlayerDragNDropManager(video_blocks=self.video_blocks)
        qt_connect(
            (
                self.active_video_mgr.active_block_change,
                self.drag_n_drop_mgr.set_active_block,
            ),
            (self.drag_n_drop_mgr.videos_swapped, self.reload_video_grid),
            (self.drag_n_drop_mgr.dropped_videos, self.add_videos),
            (self.drag_n_drop_mgr.dropped_playlist, self.load_playlist_file),
        )

        self.installEventFilter(self.mouse_hide_mgr)
        self.installEventFilter(self.drag_n_drop_mgr)
        self.installEventFilter(self.active_video_mgr)
