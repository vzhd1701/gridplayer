from multiprocessing import Array, Lock, Value

from PyQt5.QtCore import QTimer, pyqtSignal

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.params.static import PLAYER_ID_LENGTH
from gridplayer.utils.qt import qt_connect
from gridplayer.vlc_player.image_decoder import ImageDecoder
from gridplayer.vlc_player.instance import InstanceProcessVLC
from gridplayer.vlc_player.player_base_threaded import VlcPlayerThreaded
from gridplayer.vlc_player.video_driver_base_threaded import VLCVideoDriverThreaded
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLCProcess
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface


class InstanceProcessVLCSW(InstanceProcessVLC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # shared data multiprocess
        self._memory_locks = [
            {
                "lock": Lock(),
                "is_busy": Value("i", 0),
                "player_id": Array("c", PLAYER_ID_LENGTH * 2),
            }
            for _ in range(self.players_per_instance)
        ]

        self._vlc.vlc_options.append("--vout=vdummy")

    def init_player_shared_data(self, player_id):
        available_locks = (ml for ml in self._memory_locks if ml["is_busy"].value == 0)

        player_lock = next(available_locks)

        player_lock["is_busy"].value = 1
        player_lock["player_id"].value = player_id.encode()

        self._players_shared_data[player_id] = self.get_player_shared_memory(player_id)

    def release_player_shared_data(self, player_id):
        player_lock = self.get_player_lock(player_id)

        player_lock["player_id"].value = b""
        player_lock["is_busy"].value = 0

    def get_player_lock(self, player_id):
        return next(
            ml
            for ml in self._memory_locks
            if ml["player_id"].value == player_id.encode()
        )

    def get_player_shared_memory(self, player_id):
        player_lock = self.get_player_lock(player_id)
        return SafeSharedMemory(player_id, player_lock["lock"])

    def new_player(self, player_id, init_data, pipe):
        init_data["shared_memory"] = self.get_player_shared_memory(player_id)

        player = PlayerProcessSingleVLCSW(
            player_id=player_id,
            release_callback=self.release_player,
            init_data=init_data,
            vlc_instance=self.vlc_instance,
            crash_func=self.crash,
            pipe=pipe,
        )
        self._players[player_id] = player


class PlayerProcessSingleVLCSW(VlcPlayerThreaded):
    def __init__(self, player_id, release_callback, init_data, **kwargs):
        super().__init__(**kwargs)

        self.id = player_id
        self.release_callback = release_callback

        self.shared_memory = init_data["shared_memory"]
        self.decoder = None

        # Disable hardware decoding. This has to stay a media option: libvlc
        # ignores avcodec-hw passed as an instance option, where the hw decoder
        # lookup silently falls back to "any" and decodes on the GPU anyway.
        self._media_options.append("avcodec-hw=none")

        self.start()

    def init_player(self):
        super().init_player()

        self.decoder = ImageDecoder(
            self.shared_memory,
            frame_ready_cb=self.ready_signal,
            size_ready_cb=self.size_ready,
        )
        self.decoder.attach_media_player(self._media_player)

    def ready_signal(self):
        self.cmd_send("process_image")

    def size_ready(self, width, height):
        self.cmd_send("init_frame", width, height)

    def cleanup(self):
        super().cleanup()

        self.decoder.stop()

        self.release_callback(self.id)

    def cleanup_final(self):
        self.cmd_loop_terminate()

    def load_video_st4_loaded(self):
        self._tracks_manager.set_video_track_id(self.media_input.video.video_track_id)
        self._tracks_manager.set_audio_track_id(self.media_input.video.audio_track_id)

        super().load_video_st4_loaded()

    def play(self):
        self.decoder.is_paused = False

        super().play()

    def stop(self):
        if self.decoder is not None:
            self.decoder.is_paused = True

        super().stop()

    def set_pause(self, is_paused):
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

    def notify_playback_status_changed(self, is_paused):
        self._sync_decoder_pause(is_paused)

        super().notify_playback_status_changed(is_paused)


class VideoDriverVLCSW(VLCVideoDriverThreaded):
    set_dummy_frame_sig = pyqtSignal()
    image_ready_sig = pyqtSignal()

    def __init__(self, image_dest, process_manager, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self._width = None
        self._height = None

        self._image_dest = image_dest
        self._shared_memory = None
        self._frame_buf = None
        self._show_scheduled = False

        qt_connect(
            (self.set_dummy_frame_sig, self.set_dummy_frame),
            (self.image_ready_sig, self.image_ready),
        )

        self.player = process_manager.init_player(
            {}, self.cmd_child_pipe(), vlc_options
        )

    def init_frame(self, width, height):
        self._shared_memory = self.player.get_player_shared_data()

        self._width = width
        self._height = height

        self.set_dummy_frame_sig.emit()

    def set_dummy_frame(self):
        self._image_dest.present_black(self._width, self._height)

    def process_image(self):
        if self._shared_memory is None or not self._width or not self._height:
            return

        try:
            with self._shared_memory:
                self._frame_buf = bytes(self._shared_memory.memory.buf)
        except (AttributeError, RuntimeError):
            self._log.warning("Shared memory is cleared already")
            return

        self.image_ready_sig.emit()

    def image_ready(self):
        self._schedule_show()

    def _schedule_show(self):
        if self._show_scheduled:
            return
        self._show_scheduled = True
        QTimer.singleShot(0, self._show_frame)

    def _show_frame(self):
        self._show_scheduled = False
        if self._frame_buf is None or not self._width or not self._height:
            return
        self._image_dest.present_rgb32(self._frame_buf, self._width, self._height)

    def cleanup(self):
        self._show_scheduled = False
        self._frame_buf = None
        if self._shared_memory is not None:
            with self._shared_memory:
                self._shared_memory.close()
                self._shared_memory = None

        super().cleanup()

        self.player.cleanup()


class VideoFrameVLCSW(VideoFrameVLCProcess):
    is_opengl = False

    def driver_setup(self, vlc_options) -> VideoDriverVLCSW:
        return VideoDriverVLCSW(
            image_dest=self.video_surface,
            process_manager=self.process_manager,
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
