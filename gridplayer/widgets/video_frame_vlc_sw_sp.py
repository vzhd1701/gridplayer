from threading import Event

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot

from gridplayer.params.static import AudioChannelMode
from gridplayer.settings import Settings
from gridplayer.utils.qt import MILLISECONDS, QABC, qt_connect
from gridplayer.vlc_player.image_decoder import ImageDecoder
from gridplayer.vlc_player.instance import InstanceVLC
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.rgb_buffer import InProcessRgbBuffer
from gridplayer.vlc_player.static import Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface


class PlayerProcessSingleVLCSWSP(QThread, VlcPlayerBase, metaclass=QABC):
    playback_status_changed = pyqtSignal(bool)
    time_changed = pyqtSignal(MILLISECONDS)
    error_signal = pyqtSignal(str)
    update_status_signal = pyqtSignal(str, int)
    snapshot_taken = pyqtSignal(str)
    video_dimensions_changed = pyqtSignal(int, int)

    load_video_done = pyqtSignal(Media)
    tracks_changed = pyqtSignal(Media)

    loop_load_video_st2_set_media = pyqtSignal()
    loop_load_video_st3_extract_media_track = pyqtSignal()
    loop_load_video_st4_loaded = pyqtSignal()

    init_frame_signal = pyqtSignal(int, int, int)
    process_image_signal = pyqtSignal()

    _vout_reapply = pyqtSignal()

    def __init__(self, vlc_options, shared_memory, **kwargs):
        super().__init__(vlc_instance=None, **kwargs)

        self._instance = None

        self._cleanup_event = Event()
        self._instance_ready_event = Event()

        self.vlc_options = vlc_options
        self.shared_memory = shared_memory
        self.decoder = None

        # Disable hardware decoding. This has to stay a media option: libvlc
        # ignores avcodec-hw passed as an instance option, where the hw decoder
        # lookup silently falls back to "any" and decodes on the GPU anyway.
        self._media_options.append("avcodec-hw=none")

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
            (
                self._vout_reapply,
                self._on_vout_reapply,
            ),
        )

    @pyqtSlot()
    def _on_vout_reapply(self):
        self._apply_media_input_view()

    def _schedule_view_reapply(self):
        # Emitted from libvlc's event thread; this player object's affinity is the
        # main thread, so Qt delivers via QueuedConnection onto the main event
        # loop — off the libvlc callback thread. Avoids re-entering libvlc.
        self._vout_reapply.emit()

    def run(self):
        options = [*self.vlc_options, "--vout=vdummy"]
        self._instance = InstanceVLC(0, options)

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

        self.decoder = ImageDecoder(
            self.shared_memory,
            frame_ready_cb=self.ready_signal,
            size_ready_cb=self.size_ready,
        )
        self.decoder.attach_media_player(self._media_player)

    def ready_signal(self):
        self.process_image_signal.emit()

    def size_ready(self, width, height, buffer_size):
        self.init_frame_signal.emit(width, height, buffer_size)

    @pyqtSlot()
    def cleanup(self):
        self._log.debug("cmd_cleanup called")
        super().cleanup()

        if self.decoder is not None:
            self.decoder.stop()

        self._cleanup_event.set()

    def load_video_st4_loaded(self):
        self._tracks_manager.set_video_track_id(self.media_input.video.video_track_id)
        self._tracks_manager.set_audio_track_id(self._wanted_audio_track_id())

        super().load_video_st4_loaded()

    def play(self):
        if self.decoder is not None:
            self.decoder.is_paused = False

        super().play()

    def stop(self):
        if self.decoder is not None:
            self.decoder.is_paused = True

        super().stop()

    def set_pause(self, is_paused):
        if self.decoder is not None:
            self.decoder.is_paused = is_paused

        super().set_pause(is_paused)

    def _sync_decoder_pause(self, is_paused):
        """Keep the decoder's paused flag on the real playback state.

        play()/stop()/set_pause() only cover explicit commands. Initial load
        and the live-stream unpause failsafe move the player without going
        through them, which used to leave the decoder paused for the whole
        session — every frame then had to survive the paused dedup check.
        """
        if self.decoder is not None:
            self.decoder.is_paused = is_paused

    def adjust_view(self, size, aspect, scale, crop):
        """Done by the widget"""

    def notify_update_status(self, status, percent=0):
        self.update_status_signal.emit(status, percent)

    def notify_error(self, error):
        self.error_signal.emit(error)

    def notify_time_changed(self, new_time):
        self.time_changed.emit(new_time)

    def notify_playback_status_changed(self, is_paused):
        self._sync_decoder_pause(is_paused)

        self.playback_status_changed.emit(is_paused)

    def notify_load_video_done(self, media_track):
        self.load_video_done.emit(media_track)

    def notify_tracks_changed(self, media_track):
        self.tracks_changed.emit(media_track)

    def notify_snapshot_taken(self, snapshot_path):
        self.snapshot_taken.emit(snapshot_path)

    def notify_video_dimensions(self, width, height):
        self.video_dimensions_changed.emit(width, height)

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


class VideoDriverVLCSWSP(VLCVideoDriver):
    cmd_load_video = pyqtSignal(MediaInput)
    cmd_snapshot = pyqtSignal()
    cmd_play = pyqtSignal()
    cmd_set_pause = pyqtSignal(bool)
    cmd_set_time = pyqtSignal(MILLISECONDS)
    cmd_set_playback_rate = pyqtSignal(float)
    cmd_audio_set_mute = pyqtSignal(bool)
    cmd_audio_set_volume = pyqtSignal(float)
    cmd_set_video_track = pyqtSignal(int)
    cmd_set_audio_track = pyqtSignal(int)
    cmd_add_audio_slave = pyqtSignal(str)
    cmd_set_audio_channel_mode = pyqtSignal(AudioChannelMode)
    cmd_set_audio_delay = pyqtSignal(int)
    cmd_set_log_level_vlc = pyqtSignal(int)

    cmd_cleanup = pyqtSignal()

    def __init__(self, image_dest, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self._width = None
        self._height = None

        self._image_dest = image_dest
        self._frame_buf = None
        self._show_scheduled = False

        self._shared_memory = InProcessRgbBuffer()
        self._shared_memory_closing = None

        self.player = PlayerProcessSingleVLCSWSP(
            vlc_options=vlc_options,
            shared_memory=self._shared_memory,
        )

        qt_connect(
            (self.player.load_video_done, self.load_video_done),
            (self.player.tracks_changed, self.tracks_changed_emit),
            (self.player.snapshot_taken, self.snapshot_taken_emit),
            (self.player.video_dimensions_changed, self.set_video_dimensions),
            (self.player.playback_status_changed, self.playback_status_changed_emit),
            (self.player.time_changed, self.time_changed),
            (self.player.error_signal, self.error),
            (self.player.update_status_signal, self.update_status),
            (self.player.init_frame_signal, self.init_frame),
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
            (self.cmd_add_audio_slave, self.player.add_audio_slave),
            (self.cmd_set_audio_channel_mode, self.player.set_audio_channel_mode),
            (self.cmd_set_audio_delay, self.player.set_audio_delay),
            (self.cmd_set_log_level_vlc, self.player.set_log_level_vlc),
            (self.cmd_cleanup, self.player.cleanup),
        )
        # Unlock callback runs on a libvlc native thread. AutoConnection can
        # look like DirectConnection from ctypes and deadlock on the frame lock.
        self.player.process_image_signal.connect(
            self.process_image, Qt.QueuedConnection
        )

        self.player.start()
        self.player.wait_for_init()

    def cleanup_start(self):
        self._show_scheduled = False
        self._frame_buf = None
        # Drop the driver ref first so queued process_image slots no-op while
        # the player thread tears down the allocator-side mapping.
        self._shared_memory_closing = self._shared_memory
        self._shared_memory = None
        self.cmd_cleanup.emit()

    def cleanup_wait(self):
        self.player.wait()

        shared = self._shared_memory_closing
        self._shared_memory_closing = None
        if shared is not None:
            shared.close()

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

    def add_audio_slave(self, uri):
        self.cmd_add_audio_slave.emit(uri)

    def set_audio_channel_mode(self, mode):
        self.cmd_set_audio_channel_mode.emit(mode)

    def set_audio_delay(self, delay_ms):
        self.cmd_set_audio_delay.emit(delay_ms)

    def set_log_level_vlc(self, log_level):
        self.cmd_set_log_level_vlc.emit(log_level)

    @pyqtSlot(int, int, int)
    def init_frame(self, width, height, buffer_size):
        if self._shared_memory is not None:
            with self._shared_memory:
                self._shared_memory.attach(buffer_size)

        self._width = width
        self._height = height

        self._image_dest.present_black(self._width, self._height)

    @pyqtSlot()
    def process_image(self):
        if self._shared_memory is None or not self._width or not self._height:
            return

        try:
            with self._shared_memory:
                self._frame_buf = bytes(self._shared_memory.memory.buf)
        except (AttributeError, RuntimeError):
            self._log.warning("Shared memory is cleared already")
            return

        self._schedule_show()

    def _schedule_show(self):
        if self._show_scheduled:
            return
        self._show_scheduled = True
        QTimer.singleShot(0, self._show_frame)

    def _show_frame(self):
        self._show_scheduled = False
        if (
            self._frame_buf is None
            or not self._width
            or not self._height
            or self._shared_memory is None
        ):
            return
        self._image_dest.present_rgb32(self._frame_buf, self._width, self._height)


class VideoFrameVLCSWSP(VideoFrameVLC):
    is_opengl = False

    def driver_setup(self, vlc_options) -> VideoDriverVLCSWSP:
        return VideoDriverVLCSWSP(
            image_dest=self.video_surface,
            vlc_options=vlc_options,
            parent=self,
        )

    def ui_video_surface(self):
        return SoftwareVideoSurface(self)

    def take_snapshot(self) -> None:
        # last frame stays painted on the surface
        self.video_driver.set_pause(True)

    def adjust_view(self):
        if super().adjust_view():
            return

        self.video_surface.set_view(self._aspect, self._scale, self._crop)

    def set_log_level_vlc(self, log_level):
        self.video_driver.set_log_level_vlc(log_level)
