from functools import partial

from gridplayer.exceptions import PlayerException
from gridplayer.params_static import VideoDriver
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_frame_vlc_base import ProcessManagerVLC
from gridplayer.widgets.video_frame_vlc_hw import InstanceProcessVLCHW, VideoFrameVLCHW
from gridplayer.widgets.video_frame_vlc_sw import InstanceProcessVLCSW, VideoFrameVLCSW


class VideoDriverManager(ManagerBase):
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.video_driver = self.video_driver

        self._process_manager = None

    def video_driver(self):
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
