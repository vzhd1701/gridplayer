from functools import partial

from PyQt5.QtCore import QTimer

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.exceptions import PlayerException
from gridplayer.mpv_player.subtitles import current_subtitle_style
from gridplayer.params import env
from gridplayer.params.static import VideoDriver
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.media_libs import MediaLib, lib_of_driver, lib_problem_text
from gridplayer.utils.qt import translate
from gridplayer.utils.video_driver import load_session_driver
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy


class VideoDriverManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.video_driver = self.video_driver

        self._process_manager = None
        self._mpv_render_service = None

        # the libraries it has been said about, which is once a run
        self._told_about = set()

    def video_driver(self):
        video_driver = Settings().get("player/video_driver")

        if video_driver == VideoDriver.VLC_HW and env.IS_MACOS:
            video_driver = VideoDriver.VLC_HW_SP
            Settings().set("player/video_driver", video_driver)

        picked_lib = lib_of_driver(video_driver)

        video_driver = load_session_driver(video_driver)

        if video_driver is None:
            self._tell_library_problem(picked_lib, None)
            return VideoFrameDummy

        if lib_of_driver(video_driver) != picked_lib:
            self._tell_library_problem(picked_lib, lib_of_driver(video_driver))

        if video_driver == VideoDriver.DUMMY:
            return VideoFrameDummy

        if lib_of_driver(video_driver) == MediaLib.MPV:
            return self._mpv_video_frame(video_driver)

        return self._vlc_video_frame(video_driver)

    def _tell_library_problem(self, picked_lib, stand_in_lib):
        if picked_lib in self._told_about:
            return

        self._told_about.add(picked_lib)

        text = lib_problem_text(picked_lib)

        if stand_in_lib == MediaLib.VLC:
            info = translate("SettingsDialog", "Playing with VLC for now.")
        elif stand_in_lib == MediaLib.MPV:
            info = translate("SettingsDialog", "Playing with MPV for now.")
        else:
            info = translate("SettingsDialog", "Videos can't play without VLC or MPV.")

        # a video is being made as this is asked, not the time to wait for an answer
        QTimer.singleShot(
            0,
            lambda: QCustomMessageBox.warning(
                self.parent(), "GridPlayer", text, info=info
            ),
        )

    def _vlc_video_frame(self, video_driver):
        # imported here, python-vlc loads libVLC as it is imported
        if video_driver == VideoDriver.VLC_SW_SP:
            from gridplayer.widgets.video_frame_vlc_sw_sp import VideoFrameVLCSWSP

            return VideoFrameVLCSWSP

        if video_driver == VideoDriver.VLC_HW_SP:
            from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP

            return VideoFrameVLCHWSP

        from gridplayer.vlc_player.instance import ProcessManagerVLC
        from gridplayer.widgets.video_frame_vlc_hw import (
            InstanceProcessVLCHW,
            VideoFrameVLCHW,
        )
        from gridplayer.widgets.video_frame_vlc_sw import (
            InstanceProcessVLCSW,
            VideoFrameVLCSW,
        )

        frame, process_instance = {
            VideoDriver.VLC_SW: (VideoFrameVLCSW, InstanceProcessVLCSW),
            VideoDriver.VLC_HW: (VideoFrameVLCHW, InstanceProcessVLCHW),
        }[video_driver]

        if self._process_manager is None:
            self._process_manager = ProcessManagerVLC(process_instance)
            self._process_manager.crash.connect(self.crash)

        return partial(frame, process_manager=self._process_manager)

    def _mpv_video_frame(self, video_driver):
        # likewise libmpv, only when something is going to play with it
        from gridplayer.mpv_player.renderer import MpvRenderService
        from gridplayer.widgets.video_frame_mpv import VideoFrameMpv

        if self._mpv_render_service is None:
            self._mpv_render_service = MpvRenderService(parent=self)

        return partial(
            VideoFrameMpv,
            render_service=self._mpv_render_service,
            hwdec="no" if video_driver == VideoDriver.MPV_SW else "auto",
        )

    def cleanup(self):
        if self._process_manager:
            self._process_manager.cleanup()
            self._process_manager = None

        if self._mpv_render_service:
            self._mpv_render_service.cleanup()

    def set_log_level_vlc(self, log_level):
        if self._process_manager:
            self._process_manager.set_log_level_vlc(log_level)
        elif Settings().get("player/video_driver") in {
            VideoDriver.VLC_HW_SP,
            VideoDriver.VLC_SW_SP,
        }:
            for vb in self._ctx.video_blocks:
                driver = vb.video_driver
                if driver is not None and hasattr(driver, "set_log_level_vlc"):
                    driver.set_log_level_vlc(log_level)

    def set_mpv_skip_frames(self, is_skipping):
        if self._mpv_render_service:
            self._mpv_render_service.set_skip_frames(is_skipping)

    def apply_subtitle_style(self):
        if self._mpv_render_service:
            self._mpv_render_service.set_subtitle_style(current_subtitle_style())

    def set_log_level(self, log_level):
        if self._process_manager:
            self._process_manager.set_log_level(log_level)

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)
