import platform
from multiprocessing import Semaphore

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QStackedLayout

from gridplayer.params_static import VideoAspect
from gridplayer.video_frame_vlc_base import (
    InstanceProcessVLC,
    VlcPlayerThreaded,
    VLCVideoDriverThreaded,
)


class InstanceProcessVLCHW(InstanceProcessVLC):
    def __init__(
        self,
        players_per_instance,
        pm_callback_pipe,
        pm_log_queue,
        log_level,
        log_level_vlc,
    ):
        super().__init__(
            players_per_instance,
            pm_callback_pipe,
            pm_log_queue,
            log_level,
            log_level_vlc,
        )

        self.init_semaphore = Semaphore()

    def new_player(self, player_id, init_data, pipe):
        player = PlayerProcessSingleVLCHW(
            player_id,
            self._vlc_instance,
            self.release_player,
            init_data,
            self.init_semaphore,
            self.crash,
            pipe,
        )
        self._players[player.id] = player


class PlayerProcessSingleVLCHW(VlcPlayerThreaded):
    def __init__(
        self,
        player_id,
        vlc_instance,
        release_callback,
        init_data,
        init_semaphore,
        crash_func,
        pipe,
    ):
        VlcPlayerThreaded.__init__(self, vlc_instance, crash_func, pipe)

        self.id = player_id
        self.release_callback = release_callback

        self.win_id = init_data["win_id"]
        self.init_semaphore = init_semaphore

        self.start()

    def init_player(self):
        if platform.system() == "Linux":
            self.init_semaphore.acquire()

        super().init_player()

        if platform.system() == "Linux":  # for Linux using the X Server
            self.media_player.set_xwindow(self.win_id)
        elif platform.system() == "Windows":  # for Windows
            self.media_player.set_hwnd(self.win_id)
        elif platform.system() == "Darwin":  # for MacOS
            self.media_player.set_nsobject(self.win_id)

    def load_video_finish(self):
        self.init_semaphore.release()

        super().load_video_finish()

    def cleanup(self):
        self.init_semaphore.release()

        super().cleanup()

        self.release_callback(self.id)

    def cleanup_final(self):
        self.cmd_loop_terminate()

    def adjust_view(self, size, aspect, scale):
        if not self.is_video_initialized:
            return

        scr_x, scr_y = size
        vid_x, vid_y = self.video_dimensions

        scaling = {
            VideoAspect.STRETCH: {"aspect": (scr_x, scr_y), "crop": (scr_x, scr_y)},
            VideoAspect.FIT: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
            VideoAspect.NONE: {"aspect": (vid_x, vid_y), "crop": (vid_x, vid_y)},
        }

        if scale > 1:
            if aspect == VideoAspect.FIT:
                resize_scale = max(scr_x / vid_x, scr_y / vid_y) * scale
            else:
                resize_scale = min(scr_x / vid_x, scr_y / vid_y) * scale

        else:
            resize_scale = 0

        self.media_player.video_set_aspect_ratio(
            "{0}:{1}".format(*scaling[aspect]["aspect"])
        )
        self.media_player.video_set_crop_geometry(
            "{0}:{1}".format(*scaling[aspect]["crop"])
        )
        self.media_player.video_set_scale(resize_scale)


class VideoDriverVLCHW(VLCVideoDriverThreaded):
    def __init__(self, win_id, process_manager, parent=None):
        VLCVideoDriverThreaded.__init__(self, parent=parent)

        process_manager.init_player({"win_id": win_id}, self.cmd_child_pipe())

    def adjust_view(self, size, aspect, scale):
        self.cmd_send("adjust_view", size, aspect, scale)


class VideoFrameVLCHW(QtWidgets.QWidget):
    time_changed = QtCore.pyqtSignal(int)
    video_ready = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal()
    crash = QtCore.pyqtSignal(str)

    def __init__(self, process_manager, parent=None):
        super().__init__(parent)

        self._aspect = VideoAspect.FIT
        self._scale = 1

        self.is_video_initialized = False

        # Basic UI

        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setMouseTracking(True)

        QStackedLayout(self)
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0, 0, 0, 0)

        # Video setup

        if platform.system() == "Darwin":  # for MacOS
            self.video_surface = QtWidgets.QMacCocoaViewContainer(0, self)
            self.palette = self.video_surface.palette()
            self.palette.setColor(QtGui.QPalette.Window, QtGui.QColor(0, 0, 0))
            self.video_surface.setPalette(self.palette)
            self.video_surface.setAutoFillBackground(True)
        else:
            self.video_surface = QtWidgets.QWidget(self)

        self.video_surface.setWindowFlags(Qt.WindowTransparentForInput)
        self.video_surface.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.layout().addWidget(self.video_surface)

        self.video_driver = VideoDriverVLCHW(
            int(self.video_surface.winId()), process_manager, self
        )
        self.video_driver.time_changed.connect(self.time_change_emit)
        self.video_driver.load_finished.connect(self.load_video_finish)
        self.video_driver.error.connect(self.error_state)
        self.video_driver.crash.connect(self.crash_driver)

    def crash_driver(self, exception_txt):
        self.crash.emit(exception_txt)

    def error_state(self):
        self.cleanup()

        self.error.emit()

    def cleanup(self):
        self.video_driver.cleanup()
        # self.video_surface.deleteLater()

    def adjust_view(self):
        size = (self.size().width(), self.size().height())
        self.video_driver.adjust_view(size, self._aspect, self._scale)

    def resizeEvent(self, event):
        # Remove VLC crop black border
        new_size = QSize(self.size().width() + 4, self.size().height() + 4)
        self.video_surface.resize(new_size)
        self.video_surface.move(-2, -2)

        self.adjust_view()

    def time_change_emit(self, new_time):
        self.time_changed.emit(new_time)

    def load_video(self, file_path):
        self.video_driver.load_video(file_path)

    def load_video_finish(self):
        self.is_video_initialized = True

        self.video_ready.emit()

    def play(self):
        self.video_driver.play()

    def set_pause(self, is_paused):
        self.video_driver.set_pause(is_paused)

    def set_time(self, seek_ms):
        self.video_driver.set_time(seek_ms)

    def set_playback_rate(self, rate):
        self.video_driver.set_playback_rate(rate)

    def get_ms_per_frame(self):
        return self.video_driver.get_ms_per_frame()

    def audio_set_mute(self, is_muted):
        self.video_driver.audio_set_mute(is_muted)

    def audio_set_volume(self, volume):
        self.video_driver.audio_set_volume(volume)

    def set_aspect_ratio(self, aspect: VideoAspect):
        self._aspect = aspect

        self.adjust_view()

    def set_scale(self, scale):
        self._scale = scale

        self.adjust_view()

    @property
    def length(self):
        return self.video_driver.length
