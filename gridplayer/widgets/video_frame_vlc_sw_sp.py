from threading import Event, Lock
from uuid import uuid4

from PyQt5.QtCore import QRectF, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QBrush, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.params.static import AudioChannelMode, VideoCrop
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import calc_crop_region
from gridplayer.utils.qt import QABC, QT_ASPECT_MAP, qt_connect
from gridplayer.vlc_player.image_decoder import ImageDecoder
from gridplayer.vlc_player.instance import InstanceVLC
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC


class PlayerProcessSingleVLCSWSP(QThread, VlcPlayerBase, metaclass=QABC):
    is_preparse_required = True
    is_video_size_required = True

    playback_status_changed = pyqtSignal(bool)
    time_changed = pyqtSignal(int)
    error_signal = pyqtSignal(str)
    update_status_signal = pyqtSignal(str, int)
    snapshot_taken = pyqtSignal(str)
    video_dimensions_changed = pyqtSignal(int, int)

    load_video_done = pyqtSignal(Media)

    loop_load_video_st2_set_media = pyqtSignal()
    loop_load_video_st3_extract_media_track = pyqtSignal()
    loop_load_video_st4_loaded = pyqtSignal()

    init_frame_signal = pyqtSignal(int, int)
    process_image_signal = pyqtSignal()
    restart_load_video = pyqtSignal(MediaInput)

    _vout_reapply = pyqtSignal()

    def __init__(self, vlc_options, shared_memory, **kwargs):
        super().__init__(vlc_instance=None, **kwargs)

        self._instance = None

        self._cleanup_event = Event()
        self._instance_ready_event = Event()

        self.vlc_options = vlc_options
        self.shared_memory = shared_memory
        self.decoder = None

        self._is_decoder_initialized = False

        # Disable hardware decoding
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
        self.restart_load_video.connect(self.load_video, Qt.QueuedConnection)

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

        self.decoder = ImageDecoder(self.shared_memory, self.ready_signal)

    def ready_signal(self):
        self.process_image_signal.emit()

    @pyqtSlot()
    def cleanup(self):
        self._log.debug("cmd_cleanup called")
        super().cleanup()

        if self.decoder is not None:
            self.decoder.stop()

        self._cleanup_event.set()

    def load_video_st2_set_media(self):
        if not self._is_decoder_initialized and self.media:
            self._init_video_decoder()

        super().load_video_st2_set_media()

    def load_video_st4_loaded(self):
        if not self._is_decoder_initialized:
            # Since we need metadata to allocate video buffer, restart is required
            self._restart_playback()
            return

        self._tracks_manager.set_video_track_id(self.media_input.video.video_track_id)
        self._tracks_manager.set_audio_track_id(self.media_input.video.audio_track_id)

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

    def adjust_view(self, size, aspect, scale, crop):
        """Done by the widget"""

    def _init_video_decoder(self):
        self._is_decoder_initialized = True

        width, height = self.video_dimensions

        self.decoder.set_frame(width, height)
        # Dummy pixmap must exist before VLC can deliver the first frame.
        self.init_frame_signal.emit(width, height)
        self.decoder.attach_media_player(self._media_player)

    def _restart_playback(self):
        self._log.debug("Restarting playback...")

        self.stop()

        self.restart_load_video.emit(self.media_input)

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
    cmd_set_time = pyqtSignal(int)
    cmd_set_playback_rate = pyqtSignal(float)
    cmd_audio_set_mute = pyqtSignal(bool)
    cmd_audio_set_volume = pyqtSignal(float)
    cmd_set_video_track = pyqtSignal(int)
    cmd_set_audio_track = pyqtSignal(int)
    cmd_set_audio_channel_mode = pyqtSignal(AudioChannelMode)
    cmd_set_log_level_vlc = pyqtSignal(int)

    cmd_cleanup = pyqtSignal()

    def __init__(self, image_dest, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self._width = None
        self._height = None

        self._image_dest = image_dest
        self._pix = None

        self._shared_memory = SafeSharedMemory(f"gp-swsp-{uuid4().hex[:16]}", Lock())

        self.player = PlayerProcessSingleVLCSWSP(
            vlc_options=vlc_options,
            shared_memory=self._shared_memory,
        )

        qt_connect(
            (self.player.load_video_done, self.load_video_done),
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
            (self.cmd_set_audio_channel_mode, self.player.set_audio_channel_mode),
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

    def cleanup(self):
        # Drop the driver ref first so queued process_image slots no-op while
        # the player thread tears down the allocator-side mapping.
        shared = self._shared_memory
        self._shared_memory = None
        self.cmd_cleanup.emit()
        self.player.wait()
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

    def set_audio_channel_mode(self, mode):
        self.cmd_set_audio_channel_mode.emit(mode)

    def set_log_level_vlc(self, log_level):
        self.cmd_set_log_level_vlc.emit(log_level)

    @pyqtSlot(int, int)
    def init_frame(self, width, height):
        self._width = width
        self._height = height

        pix = QPixmap(self._width, self._height)
        pix.fill(Qt.black)
        self._image_dest.setPixmap(pix)

    @pyqtSlot()
    def process_image(self):
        if self._shared_memory is None or not self._width or not self._height:
            return

        try:
            with self._shared_memory:
                px = QImage(
                    self._shared_memory.memory.buf,
                    self._width,
                    self._height,
                    QImage.Format_RGB32,
                )
                self._pix = QPixmap.fromImage(px)
        except (AttributeError, RuntimeError):
            # Very rare race: mapping already closed by decoder.stop()
            self._log.warning("Shared memory is cleared already")
            return

        self._image_dest.setPixmap(self._pix)


class VideoFrameVLCSWSP(VideoFrameVLC):
    is_opengl = False

    def driver_setup(self, vlc_options) -> VideoDriverVLCSWSP:
        return VideoDriverVLCSWSP(
            image_dest=self._videoitem,
            vlc_options=vlc_options,
            parent=self,
        )

    def ui_video_surface(self):
        self._videoitem = QGraphicsPixmapItem()
        self._videoitem.setTransformationMode(Qt.SmoothTransformation)
        self._videoitem.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)

        self._scene = QGraphicsScene(self)
        self._scene.addItem(self._videoitem)

        video_surface = QGraphicsView(self._scene, self)
        video_surface.setBackgroundBrush(QBrush(Qt.black))
        video_surface.setWindowFlags(Qt.WindowTransparentForInput)
        video_surface.setAttribute(Qt.WA_TransparentForMouseEvents)
        video_surface.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        video_surface.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        video_surface.setFrameStyle(QFrame.NoFrame)
        video_surface.setLineWidth(0)
        video_surface.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing
            | QPainter.HighQualityAntialiasing
        )

        return video_surface

    def cleanup(self):
        if self._is_cleanup_requested:
            return True

        # need to delete these manually to avoid occasional segmentation fault
        # for some reason it won't crash if fitInView is not called (on Windows)
        # !must! come before video_driver.cleanup()
        self._scene.removeItem(self._videoitem)

        return super().cleanup()

    def take_snapshot(self) -> None:
        # no need to take snapshot, last frame stays in QGraphicsView on stop
        self.video_driver.set_pause(True)

    def adjust_view(self):
        if super().adjust_view():
            return

        aspect = QT_ASPECT_MAP[self._aspect]

        if self._crop != VideoCrop(0, 0, 0, 0):
            item_rect = self._videoitem.boundingRect()
            x, y, width, height = calc_crop_region(
                (int(item_rect.width()), int(item_rect.height())), self._crop
            )
            cropped = QRectF(item_rect.x() + x, item_rect.y() + y, width, height)

            self.video_surface.setSceneRect(cropped)
            self.video_surface.fitInView(cropped, aspect)
        else:
            self.video_surface.fitInView(self._videoitem, aspect)
        black_border_cut = 0.05
        self.video_surface.scale(
            self._scale + black_border_cut, self._scale + black_border_cut
        )

    def set_log_level_vlc(self, log_level):
        self.video_driver.set_log_level_vlc(log_level)
