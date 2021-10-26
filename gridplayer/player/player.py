import logging
from functools import partial

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QInputEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.exceptions import PlayerException
from gridplayer.params_static import VideoDriver
from gridplayer.player.mixins import (  # noqa: WPS235
    PlayerCommandsMixin,
    PlayerDragNDropMixin,
    PlayerGridMixin,
    PlayerMenuMixin,
    PlayerMinorMixin,
    PlayerPlaylistMixin,
    PlayerSettingsMixin,
    PlayerSingleModeMixin,
    PlayerVideoBlocksMixin,
)
from gridplayer.settings import Settings
from gridplayer.utils.keepawake import KeepAwake
from gridplayer.utils.misc import is_modal_open, qt_connect
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_frame_vlc_base import ProcessManagerVLC
from gridplayer.widgets.video_frame_vlc_hw import InstanceProcessVLCHW, VideoFrameVLCHW
from gridplayer.widgets.video_frame_vlc_sw import InstanceProcessVLCSW, VideoFrameVLCSW

logger = logging.getLogger(__name__)


class VideoDriverManager(object):
    _video_drivers = {
        VideoDriver.DUMMY: VideoFrameDummy,
        VideoDriver.VLC_SW: VideoFrameVLCSW,
        VideoDriver.VLC_HW: VideoFrameVLCHW,
    }

    _process_instances = {
        VideoDriver.VLC_SW: InstanceProcessVLCSW,
        VideoDriver.VLC_HW: InstanceProcessVLCHW,
    }

    _multiprocess_drivers = {
        VideoDriver.VLC_SW,
        VideoDriver.VLC_HW,
    }

    def __init__(self):
        self._process_manager = None

    @property
    def driver(self):
        video_driver_cfg = Settings().get("player/video_driver")
        is_multiprocess = video_driver_cfg in self._multiprocess_drivers

        if is_multiprocess:
            if self._process_manager is None:
                self._process_manager = ProcessManagerVLC(
                    self._process_instances[video_driver_cfg]
                )
                self._process_manager.crash.connect(self.crash)

            return partial(
                self._video_drivers[video_driver_cfg],
                process_manager=self._process_manager,
            )

        return self._video_drivers[video_driver_cfg]

    def cleanup(self):
        if self._process_manager:
            self._process_manager.cleanup()
            self._process_manager = None

    def set_log_level_vlc(self, log_level):
        if self._process_manager:
            self._process_manager.set_log_level_vlc(log_level)

    def set_log_level(self, log_level):
        if self._process_manager:
            self._process_manager.set_log_level(log_level)

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)

    def set_video_count(self, video_count):
        if video_count == 0:
            self.cleanup()


class ScreensaverManager(object):
    def __init__(self):
        self.keepawake = KeepAwake()

    def screensaver_check(self, playing_videos_count):
        if not Settings().get("player/inhibit_screensaver"):
            self.keepawake.screensaver_on()
            return

        is_something_playing = playing_videos_count > 0

        if is_something_playing:
            self.keepawake.screensaver_off()
        else:
            self.keepawake.screensaver_on()


class PlayerMouseHideManager(QObject):
    mouse_hidden = pyqtSignal()
    mouse_shown = pyqtSignal()

    move_events = {
        QEvent.ShortcutOverride,
        QEvent.NonClientAreaMouseMove,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.is_no_videos = True

        self.mouse_timer = QTimer()
        self.mouse_timer.timeout.connect(self.hide_cursor)
        if Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

    def eventFilter(self, event_object, event) -> bool:
        if isinstance(event, QInputEvent) or event.type() in self.move_events:
            self.show_cursor()

        return False

    def hide_cursor(self):
        self.mouse_timer.stop()

        if self.is_no_videos or is_modal_open():
            return

        if QApplication.overrideCursor() != Qt.BlankCursor:
            QApplication.setOverrideCursor(Qt.BlankCursor)

            self.mouse_hidden.emit()

    def show_cursor(self):
        if QApplication.overrideCursor() == Qt.BlankCursor:
            QApplication.restoreOverrideCursor()

            self.mouse_shown.emit()

        if Settings().get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * Settings().get("misc/mouse_hide_timeout"))

    def set_video_count(self, video_count):
        self.is_no_videos = video_count == 0


class Player(  # noqa: WPS215
    PlayerMenuMixin,
    PlayerCommandsMixin,
    PlayerSettingsMixin,
    # Utilities
    PlayerDragNDropMixin,
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

        self.is_modal_open = False
        self.is_maximized_pre_fullscreen = False

        self.setMouseTracking(True)

        self.driver_mgr = VideoDriverManager()
        self.video_count_change.connect(self.driver_mgr.set_video_count)

        self.screensaver_mgr = ScreensaverManager()
        self.playings_videos_count_change.connect(
            self.screensaver_mgr.screensaver_check
        )

        self.mouse_hide_mgr = PlayerMouseHideManager()
        self.installEventFilter(self.mouse_hide_mgr)
        qt_connect(
            (self.video_count_change, self.mouse_hide_mgr.set_video_count),
            (self.mouse_hide_mgr.mouse_hidden, self.update_active_reset),
            (self.mouse_hide_mgr.mouse_hidden, lambda: self.hide_overlay.emit()),
            (self.mouse_hide_mgr.mouse_shown, self.update_active_under_mouse),
        )

        self.reload_video_grid()
