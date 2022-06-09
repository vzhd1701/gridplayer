import platform

from PyQt5.QtCore import QMargins, QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.settings import Settings
from gridplayer.utils.qt import QABC, qt_connect
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC

if platform.system() == "Darwin":
    from PyQt5.QtWidgets import QMacCocoaViewContainer  # noqa: WPS433

from gridplayer.vlc_player.instance import InstanceVLC
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import MediaInput, MediaTrack
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver


class PlayerProcessSingleVLCHWSP(QObject, VlcPlayerBase, metaclass=QABC):
    playback_status_changed = pyqtSignal(bool)
    end_reached = pyqtSignal()
    time_changed = pyqtSignal(int)
    load_finished = pyqtSignal()
    error = pyqtSignal()
    crash = pyqtSignal(str)
    snapshot_taken = pyqtSignal(str)

    load_video_done = pyqtSignal(MediaTrack)
    load_video_display = pyqtSignal()

    loop_load_video_st2_set_parsed_media = pyqtSignal()
    loop_load_video_st3_extract_media_track = pyqtSignal()
    loop_load_video_st4_loaded = pyqtSignal()

    def __init__(self, win_id, **kwargs):
        super().__init__(**kwargs)

        self.win_id = win_id

        qt_connect(
            (
                self.loop_load_video_st2_set_parsed_media,
                self.load_video_st2_set_parsed_media,
            ),
            (
                self.loop_load_video_st3_extract_media_track,
                self.load_video_st3_extract_media_track,
            ),
            (
                self.loop_load_video_st4_loaded,
                self.load_video_st4_loaded,
            ),
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

    def notify_time_changed(self, new_time):
        self.time_changed.emit(new_time)

    def notify_playback_status_changed(self, is_paused):
        self.playback_status_changed.emit(is_paused)

    def notify_end_reached(self):
        self.end_reached.emit()

    def notify_load_video_done(self, media_track):
        self.load_video_done.emit(media_track)

    def notify_load_video_display(self):
        self.load_video_display.emit()

    def notify_snapshot_taken(self, snapshot_path):
        self.snapshot_taken.emit(snapshot_path)

    def loopback_load_video_st2_set_parsed_media(self):
        self.loop_load_video_st2_set_parsed_media.emit()

    def loopback_load_video_st3_extract_media_track(self):
        self.loop_load_video_st3_extract_media_track.emit()

    def loopback_load_video_st4_loaded(self):
        self.loop_load_video_st4_loaded.emit()


class VideoDriverVLCHWSP(VLCVideoDriver):
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
            (self.player.load_video_done, self.load_video_done),
            (self.player.load_video_display, self.load_video_display),
            (self.player.snapshot_taken, self.snapshot_taken_emit),
            (self.player.playback_status_changed, self.playback_status_changed_emit),
            (self.player.end_reached, self.end_reached_emit),
            (self.player.time_changed, self.time_changed),
            (self.player.load_finished, self.load_finished),
            (self.player.error, self.error),
            (self.player.crash, self.crash),
        )

    def cleanup(self):
        self.player.cleanup()
        self.instance.cleanup_instance()

    def load_video(self, media_input: MediaInput):
        self.player.load_video(media_input)

    def snapshot(self):
        self.player.snapshot()

    def play(self):
        self.player.play()

    def set_pause(self, is_paused):
        self.player.set_pause(is_paused)

    def set_time(self, seek_ms):
        self.player.set_time(seek_ms)

    def set_playback_rate(self, rate):
        self.player.set_playback_rate(rate)

    def audio_set_mute(self, is_muted):
        self.player.audio_set_mute(is_muted)

    def audio_set_volume(self, volume):
        self.player.audio_set_volume(volume)

    def adjust_view(self, size, aspect, scale):
        self.player.adjust_view(size, aspect, scale)

    def set_log_level_vlc(self, log_level):
        self.instance.set_log_level_vlc(log_level)


class VideoFrameVLCHWSP(VideoFrameVLC):
    is_opengl = True

    def driver_setup(self) -> VideoDriverVLCHWSP:
        return VideoDriverVLCHWSP(
            win_id=int(self.video_surface.winId()),
            parent=self,
        )

    def ui_video_surface(self):
        if platform.system() == "Darwin":
            video_surface = QMacCocoaViewContainer(0, self)
        else:
            video_surface = QWidget(self)

        video_surface.setMouseTracking(True)
        video_surface.setWindowFlags(Qt.WindowTransparentForInput)
        video_surface.setAttribute(Qt.WA_TransparentForMouseEvents)

        return video_surface

    def adjust_view(self):
        if super().adjust_view():
            return

        size = (self.size().width(), self.size().height())
        self.video_driver.adjust_view(size, self._aspect, self._scale)

        # Remove VLC crop black border
        new_size = self.size().grownBy(QMargins(2, 2, 2, 2))
        self.video_surface.resize(new_size)
        self.video_surface.move(-2, -2)

    def load_video_finish(self):
        if platform.system() == "Darwin":
            # Need an explicit resize for adjustment to work on MacOS
            size = self.size()
            size.setWidth(size.width() + 1)
            size.setHeight(size.height() + 1)
            self.resize(size)

        super().load_video_finish()

    def set_log_level_vlc(self, log_level):
        self.video_driver.set_log_level_vlc(log_level)
