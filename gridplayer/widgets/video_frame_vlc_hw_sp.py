from threading import Event

from PyQt5.QtCore import QMargins, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget

from gridplayer.params import env
from gridplayer.params.static import AudioChannelMode, VideoAspect, VideoCrop
from gridplayer.settings import Settings
from gridplayer.utils.qt import QABC, qt_connect
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC

if env.IS_MACOS:
    from PyQt5.QtWidgets import QMacCocoaViewContainer

from gridplayer.vlc_player.instance import InstanceVLC
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver


class PlayerProcessSingleVLCHWSP(QThread, VlcPlayerBase, metaclass=QABC):
    playback_status_changed = pyqtSignal(bool)
    time_changed = pyqtSignal(int)
    error_signal = pyqtSignal(str)
    update_status_signal = pyqtSignal(str, int)
    snapshot_taken = pyqtSignal(str)

    load_video_done = pyqtSignal(Media)

    loop_load_video_st2_set_media = pyqtSignal()
    loop_load_video_st3_extract_media_track = pyqtSignal()
    loop_load_video_st4_loaded = pyqtSignal()

    def __init__(self, win_id, vlc_options, **kwargs):
        super().__init__(vlc_instance=None, **kwargs)

        self._instance = None

        self._cleanup_event = Event()
        self._instance_ready_event = Event()

        self.win_id = win_id
        self.vlc_options = vlc_options

        qt_connect(
            (
                self.loop_load_video_st2_set_media,
                self.load_video_st2_set_media,
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

    def run(self):
        self._instance = InstanceVLC(0, self.vlc_options)

        self._instance.set_log_level_vlc(Settings().get("logging/log_level_vlc"))
        self._instance.init_instance()

        self.instance = self._instance.vlc_instance

        self.init_player()

        self._log.debug("Player initialized")

        self._instance_ready_event.set()

        self._cleanup_event.wait()

        self._log.debug("VLC instance terminating")

        self._instance.cleanup_instance()

        self._log.debug("Terminating player thread")

    def init_player(self):
        super().init_player()

        if env.IS_LINUX:
            self._media_player.set_xwindow(self.win_id)
        elif env.IS_WINDOWS:
            self._media_player.set_hwnd(self.win_id)
        elif env.IS_MACOS:
            self._media_player.set_nsobject(self.win_id)

    @pyqtSlot()
    def cleanup(self):
        self._log.debug("cmd_cleanup called")
        super().cleanup()

        self._cleanup_event.set()

    def notify_update_status(self, status, percent=0):
        self.update_status_signal.emit(status, percent)

    def notify_error(self, error):
        self.error_signal.emit(error)

    def notify_time_changed(self, new_time):
        self.time_changed.emit(new_time)

    def notify_playback_status_changed(self, is_paused):
        self.playback_status_changed.emit(is_paused)

    def notify_load_video_done(self, media_track):
        self.load_video_done.emit(media_track)

    def notify_snapshot_taken(self, snapshot_path):
        self.snapshot_taken.emit(snapshot_path)

    def loopback_load_video_st2_set_media(self):
        self.loop_load_video_st2_set_media.emit()

    def loopback_load_video_st3_extract_media_track(self):
        self.loop_load_video_st3_extract_media_track.emit()

    def loopback_load_video_st4_loaded(self):
        self.loop_load_video_st4_loaded.emit()

    def set_log_level_vlc(self, log_level):
        self._instance.set_log_level_vlc(log_level)

    def wait_for_init(self):
        self._instance_ready_event.wait()


class VideoDriverVLCHWSP(VLCVideoDriver):
    cmd_load_video = pyqtSignal(MediaInput)
    cmd_snapshot = pyqtSignal()
    cmd_play = pyqtSignal()
    cmd_set_pause = pyqtSignal(bool)
    cmd_set_time = pyqtSignal(int)
    cmd_set_playback_rate = pyqtSignal(float)
    cmd_audio_set_mute = pyqtSignal(bool)
    cmd_audio_set_volume = pyqtSignal(float)
    cmd_set_video_track = pyqtSignal(int)
    cmd_set_audio_track = pyqtSignal(int)
    cmd_set_audio_channel_mode = pyqtSignal(AudioChannelMode)
    cmd_adjust_view = pyqtSignal(tuple, VideoAspect, float, VideoCrop)
    cmd_set_log_level_vlc = pyqtSignal(int)

    cmd_init_player = pyqtSignal()
    cmd_cleanup = pyqtSignal()

    def __init__(self, win_id, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self.player = PlayerProcessSingleVLCHWSP(win_id=win_id, vlc_options=vlc_options)

        qt_connect(
            (self.player.load_video_done, self.load_video_done),
            (self.player.snapshot_taken, self.snapshot_taken_emit),
            (self.player.playback_status_changed, self.playback_status_changed_emit),
            (self.player.time_changed, self.time_changed),
            (self.player.error_signal, self.error),
            (self.player.update_status_signal, self.update_status),
            (self.cmd_load_video, self.player.load_video),
            (self.cmd_snapshot, self.player.snapshot),
            (self.cmd_play, self.player.play),
            (self.cmd_set_pause, self.player.set_pause),
            (self.cmd_set_time, self.player.set_time),
            (self.cmd_set_playback_rate, self.player.set_playback_rate),
            (self.cmd_audio_set_mute, self.player.audio_set_mute),
            (self.cmd_audio_set_volume, self.player.audio_set_volume),
            (self.cmd_set_video_track, self.player.set_video_track),
            (self.cmd_set_audio_track, self.player.set_audio_track),
            (self.cmd_set_audio_channel_mode, self.player.set_audio_channel_mode),
            (self.cmd_adjust_view, self.player.adjust_view),
            (self.cmd_set_log_level_vlc, self.player.set_log_level_vlc),
            (self.cmd_cleanup, self.player.cleanup),
        )

        self.player.start()
        self.player.wait_for_init()

    def cleanup(self):
        self.cmd_cleanup.emit()
        self.player.wait()

    def load_video(self, media_input: MediaInput):
        self.cmd_load_video.emit(media_input)

    def snapshot(self):
        self.cmd_snapshot.emit()

    def play(self):
        self.cmd_play.emit()

    def set_pause(self, is_paused):
        self.cmd_set_pause.emit(is_paused)

    def set_time(self, seek_ms):
        self.cmd_set_time.emit(seek_ms)

    def set_playback_rate(self, rate):
        self.cmd_set_playback_rate.emit(rate)

    def audio_set_mute(self, is_muted):
        self.cmd_audio_set_mute.emit(is_muted)

    def audio_set_volume(self, volume):
        self.cmd_audio_set_volume.emit(volume)

    def set_video_track(self, track_id):
        self.cmd_set_video_track.emit(track_id)

    def set_audio_track(self, track_id):
        self.cmd_set_audio_track.emit(track_id)

    def set_audio_channel_mode(self, mode):
        self.cmd_set_audio_channel_mode.emit(mode)

    def adjust_view(self, size, aspect, scale, crop):
        self.cmd_adjust_view.emit(size, aspect, scale, crop)

    def set_log_level_vlc(self, log_level):
        self.cmd_set_log_level_vlc.emit(log_level)


class VideoFrameVLCHWSP(VideoFrameVLC):
    is_opengl = True

    def driver_setup(self, vlc_options) -> VideoDriverVLCHWSP:
        return VideoDriverVLCHWSP(
            win_id=int(self.video_surface.winId()),
            vlc_options=vlc_options,
            parent=self,
        )

    def ui_video_surface(self):
        if env.IS_MACOS:
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
        self.video_driver.adjust_view(size, self._aspect, self._scale, self._crop)

        # Remove VLC crop black border
        new_size = self.size().grownBy(QMargins(2, 2, 2, 2))
        self.video_surface.resize(new_size)
        self.video_surface.move(-2, -2)

    def load_video_finish(self, media_track: Media):
        if env.IS_MACOS:
            # Need an explicit resize for adjustment to work on MacOS
            size = self.size()
            size.setWidth(size.width() + 1)
            size.setHeight(size.height() + 1)
            self.resize(size)

        super().load_video_finish(media_track)

    def set_log_level_vlc(self, log_level):
        self.video_driver.set_log_level_vlc(log_level)
