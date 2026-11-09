from functools import partial

from gridplayer.exceptions import PlayerException
from gridplayer.mpv_player.instance import ProcessManagerMPV
from gridplayer.params import env
from gridplayer.params.static import VideoDriver
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.video_driver import session_video_driver
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_frame_mpv_hw import InstanceProcessMPVHW, VideoFrameMPVHW
from gridplayer.widgets.video_frame_mpv_sw import InstanceProcessMPVSW, VideoFrameMPVSW


class VideoDriverManager(ManagerBase):
    _video_drivers = {
        VideoDriver.DUMMY: VideoFrameDummy,
        VideoDriver.MPV_HW: VideoFrameMPVHW,
        VideoDriver.MPV_SW: VideoFrameMPVSW,
    }

    _process_instances = {
        VideoDriver.MPV_HW: InstanceProcessMPVHW,
        VideoDriver.MPV_SW: InstanceProcessMPVSW,
    }

    _multiprocess_drivers = {
        VideoDriver.MPV_SW,
        VideoDriver.MPV_HW,
    }

    _process_managers = {
        VideoDriver.MPV_HW: ProcessManagerMPV,
        VideoDriver.MPV_SW: ProcessManagerMPV,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.video_driver = self.video_driver

        self._process_manager = None

    def video_driver(self):
        video_driver = Settings().get("player/video_driver")

        # mpv can't draw into a window of another process there
        if video_driver == VideoDriver.MPV_HW and env.IS_MACOS:
            video_driver = VideoDriver.MPV_SW
            Settings().set("player/video_driver", video_driver)

        video_driver = session_video_driver(video_driver)

        is_multiprocess = video_driver in self._multiprocess_drivers

        if is_multiprocess:
            if self._process_manager is None:
                self._process_manager = self._process_managers[video_driver](
                    self._process_instances[video_driver]
                )
                self._process_manager.crash.connect(self.crash)

            return partial(
                self._video_drivers[video_driver],
                process_manager=self._process_manager,
            )

        return self._video_drivers[video_driver]

    def cleanup(self):
        if self._process_manager:
            self._process_manager.cleanup()
            self._process_manager = None

    def set_log_level(self, log_level):
        if self._process_manager:
            self._process_manager.set_log_level(log_level)

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)
