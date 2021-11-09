import platform

from PyQt5.QtCore import QMargins, QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QStackedLayout, QWidget

from gridplayer.settings import Settings
from gridplayer.utils.misc import qt_connect

if platform.system() == "Darwin":
    from PyQt5.QtWidgets import QMacCocoaViewContainer  # noqa: WPS433

from gridplayer.params_static import VideoAspect
from gridplayer.widgets.video_frame_vlc_base import InstanceVLC, VlcPlayerBase


class PlayerProcessSingleVLCHWSP(QObject, VlcPlayerBase):
    time_changed = pyqtSignal(int)
    load_finished = pyqtSignal()
    error = pyqtSignal()
    crash = pyqtSignal(str)

    self_load_video_finish = pyqtSignal(dict)
    loop_load_video_player = pyqtSignal()
    loop_load_video_finish = pyqtSignal()

    def __init__(self, win_id, **kwargs):
        super().__init__(**kwargs)

        self.win_id = win_id

        qt_connect(
            (self.loop_load_video_player, self.load_video_player),
            (self.loop_load_video_finish, self.load_video_finish),
        )

    def init_player(self):
        super().init_player()

        if platform.system() == "Linux":  # for Linux using the X Server
            self._media_player.set_xwindow(self.win_id)
        elif platform.system() == "Windows":  # for Windows
            self._media_player.set_hwnd(self.win_id)
        elif platform.system() == "Darwin":  # for MacOS
            self._media_player.set_nsobject(self.win_id)

    def notify_error(self):
        self.error.emit()

    def notify_time_change(self, new_time):
        self.time_changed.emit(new_time)

    def notify_load_video_finish(self, video_params):
        self.self_load_video_finish.emit(video_params)

    def loopback_load_video_player(self):
        self.loop_load_video_player.emit()

    def loopback_load_video_finish(self):
        self.loop_load_video_finish.emit()

    def adjust_view(self, size, aspect, scale):
        if not self.is_video_initialized:
            return

        crop_aspect, crop_geometry = self._calc_crop(size, aspect)

        resize_scale = self._calc_resize_scale(size, aspect, scale)

        self._media_player.video_set_aspect_ratio("{0}:{1}".format(*crop_aspect))
        self._media_player.video_set_crop_geometry("{0}:{1}".format(*crop_geometry))
        self._media_player.video_set_scale(resize_scale)

    def _calc_resize_scale(self, size, aspect, scale):
        scr_x, scr_y = size
        vid_x, vid_y = self.video_dimensions

        if scale > 1:
            if aspect == VideoAspect.FIT:
                resize_scale = max(scr_x / vid_x, scr_y / vid_y) * scale
            else:
                resize_scale = min(scr_x / vid_x, scr_y / vid_y) * scale

        else:
            resize_scale = 0

        return resize_scale

    def _calc_crop(self, size, aspect):
        scr_x, scr_y = size
        vid_x, vid_y = self.video_dimensions

        scaling = {
            VideoAspect.STRETCH: {"aspect": (scr_x, scr_y), "crop": (scr_x, scr_y)},
            VideoAspect.FIT: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
            VideoAspect.NONE: {"aspect": (vid_x, vid_y), "crop": (vid_x, vid_y)},
        }

        return scaling[aspect]["aspect"], scaling[aspect]["crop"]


class VideoDriverVLCHWSP(QObject):
    time_changed = pyqtSignal(int)
    load_finished = pyqtSignal()
    error = pyqtSignal()
    crash = pyqtSignal(str)

    def __init__(self, win_id, **kwargs):
        super().__init__(**kwargs)

        self.instance = InstanceVLC(0)

        self.instance.set_log_level_vlc(Settings().get("logging/log_level_vlc"))
        self.instance.init_instance()

        self.player = PlayerProcessSingleVLCHWSP(
            win_id=win_id,
            vlc_instance=self.instance.vlc_instance,
        )

        self.player.init_player()

        qt_connect(
            (self.player.self_load_video_finish, self.load_video_finish),
            (self.player.time_changed, self.time_changed),
            (self.player.load_finished, self.load_finished),
            (self.player.error, self.error),
            (self.player.crash, self.crash),
        )

        self.length = 0
        self.fps = None

    def cleanup(self):
        self.player.cleanup()
        self.instance.cleanup_instance()

    def time_change_emit(self, new_time):
        self.time_changed.emit(new_time)

    def load_video(self, file_path):
        self.player.load_video(file_path)

    def load_video_finish(self, video_params):
        self.length = video_params["length"]
        self.fps = video_params["fps"]

        self.load_finished.emit()

    def play(self):
        self.player.play()

    def set_pause(self, is_paused):
        self.player.set_pause(is_paused)

    def set_time(self, seek_ms):
        self.player.set_time(seek_ms)

    def set_playback_rate(self, rate):
        self.player.set_playback_rate(rate)

    def get_ms_per_frame(self):
        return int(1000 // self.fps)

    def audio_set_mute(self, is_muted):
        self.player.audio_set_mute(is_muted)

    def audio_set_volume(self, volume):
        self.player.audio_set_volume(volume)

    def error_state(self):
        self.error.emit()

    def adjust_view(self, size, aspect, scale):
        self.player.adjust_view(size, aspect, scale)

    def set_log_level_vlc(self, log_level):
        self.instance.set_log_level_vlc(log_level)


class VideoFrameVLCHWSP(QWidget):
    time_changed = pyqtSignal(int)
    video_ready = pyqtSignal()
    error = pyqtSignal()
    crash = pyqtSignal(str)

    is_opengl = True

    def __init__(self, parent=None):
        super().__init__(parent)

        self._aspect = VideoAspect.FIT
        self._scale = 1

        self.is_video_initialized = False

        self.ui_setup()

        self.ui_video_widget()

        self.layout().addWidget(self.video_surface)

        self.video_driver = VideoDriverVLCHWSP(
            win_id=int(self.video_surface.winId()),
            parent=self,
        )
        qt_connect(
            (self.video_driver.time_changed, self.time_change_emit),
            (self.video_driver.load_finished, self.load_video_finish),
            (self.video_driver.error, self.error_state),
            (self.video_driver.crash, self.crash_driver),
        )

    def ui_setup(self):
        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.setMouseTracking(True)

        QStackedLayout(self)
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0, 0, 0, 0)

    def ui_video_widget(self):
        if platform.system() == "Darwin":  # for MacOS
            self.video_surface = QMacCocoaViewContainer(0, self)
        else:
            self.video_surface = QWidget(self)

        self.video_surface.setMouseTracking(True)
        self.video_surface.setWindowFlags(Qt.WindowTransparentForInput)
        self.video_surface.setAttribute(Qt.WA_TransparentForMouseEvents)

    def crash_driver(self, exception_txt):
        self.crash.emit(exception_txt)

    def error_state(self):
        self.cleanup()

        self.error.emit()

    def cleanup(self):
        self.video_driver.cleanup()

    def adjust_view(self):
        size = (self.size().width(), self.size().height())
        self.video_driver.adjust_view(size, self._aspect, self._scale)

    def resizeEvent(self, event):
        # Remove VLC crop black border
        new_size = self.size().grownBy(QMargins(2, 2, 2, 2))

        self.video_surface.resize(new_size)
        self.video_surface.move(-2, -2)

        self.adjust_view()

    def time_change_emit(self, new_time):
        self.time_changed.emit(new_time)

    def load_video(self, file_path):
        self.video_driver.load_video(file_path)

    def load_video_finish(self):
        self.is_video_initialized = True

        if platform.system() == "Darwin":
            # Need an explicit resize for adjustment to work on MacOS
            size = self.size()
            size.setWidth(size.width() + 1)
            size.setHeight(size.height() + 1)
            self.resize(size)

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

    def set_scale(self, scale):  # noqa: WPS615
        self._scale = scale

        self.adjust_view()

    @property
    def length(self):
        return self.video_driver.length
