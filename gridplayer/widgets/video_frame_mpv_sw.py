"""Videos mpv draws in software, painted by Qt from memory shared with it."""

from multiprocessing import Array, Lock, Value

from PyQt5.QtCore import QTimer, pyqtSignal

from gridplayer.mpv_player.instance import InstanceProcessMPV
from gridplayer.mpv_player.player import TRANSFORM_FILTERS, MpvPlayerThreaded
from gridplayer.mpv_player.rgb_buffer import FrameReader, holding
from gridplayer.mpv_player.software import MpvSoftwareRenderer
from gridplayer.mpv_player.video_driver_base_threaded import PlayerDriverThreaded
from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.params.static import (
    PLAYER_ID_LENGTH,
    HardwareDecoding,
    VideoTransform,
)
from gridplayer.utils.qt import qt_connect
from gridplayer.utils.screenshots import ScreenshotView
from gridplayer.widgets.video_frame_base import VideoFrameProcess
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface

# Every player shares this one, so that they share processes too.
NO_OPTIONS = []

SOFTWARE_TRANSFORM_FILTERS = {
    VideoTransform.ROTATE_90: "lavfi=[transpose=1]",
    VideoTransform.ROTATE_180: "lavfi=[hflip,vflip]",
    VideoTransform.ROTATE_270: "lavfi=[transpose=2]",
    **TRANSFORM_FILTERS,
}


class InstanceProcessMPVSW(InstanceProcessMPV):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._memory_locks = [
            {
                "lock": Lock(),
                "is_busy": Value("i", 0),
                "player_id": Array("c", PLAYER_ID_LENGTH * 2),
            }
            for _ in range(self.players_per_instance)
        ]

    def init_player_shared_data(self, player_id):
        player_lock = next(ml for ml in self._memory_locks if ml["is_busy"].value == 0)

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

        self._players[player_id] = PlayerProcessSingleMPVSW(
            player_id=player_id,
            release_callback=self.release_player,
            init_data=init_data,
            crash_func=self.crash,
            pipe=pipe,
        )


class PlayerProcessSingleMPVSW(MpvPlayerThreaded):
    is_quality_managed = False

    def __init__(self, player_id, release_callback, init_data, **kwargs):
        super().__init__(**kwargs)

        self.id = player_id
        self.release_callback = release_callback

        self.shared_memory = init_data["shared_memory"]
        self.renderer = None

        self.start()

    def _mpv_options(self):
        # keepaspect off: the frame is the whole picture, which the widget
        # puts in shape as it paints it
        #
        # video_rotate off: the software renderer ignores rotation, so all of
        # it is done with filters instead, see _rotation_filters
        #
        # hwdec: this driver's Auto is the CPU, its reason for being there
        is_copied = self._hardware_decoding is HardwareDecoding.COPY

        return {
            "vo": "libmpv",
            "hwdec": "auto-copy-safe" if is_copied else "no",
            "keepaspect": False,
            "video_rotate": "no",
        }

    def init_player(self):
        super().init_player()

        self.renderer = MpvSoftwareRenderer(
            self._mpv,
            self.shared_memory,
            frame_ready_cb=self.ready_signal,
            size_ready_cb=self.size_ready,
            crash_cb=self.crash_func,
        )
        self.renderer.start()

        self._mpv.observe_property("video-dec-params", self._on_decoder_params)

    def _on_decoder_params(self, _name, value):
        if value:
            self.renderer.set_picture(value.get("w"), value.get("h"))

    def _apply_transform(self, transform):
        """Held until the file is open: it can ask for a turn of its own."""

        self._transform = transform

    def on_file_loaded(self):
        super().on_file_loaded()

        track = self._shown_video_track()

        self.renderer.set_turned(track is not None and track.is_turned)

        self._set("vf", self._rotation_filters(track))

    def _rotation_filters(self, track) -> str:
        """What the file asks for, then what the viewer picked on top of it."""

        orientation = track.orientation if track is not None else None

        filters = (
            SOFTWARE_TRANSFORM_FILTERS.get(orientation),
            SOFTWARE_TRANSFORM_FILTERS.get(self._transform),
        )

        return ",".join(item for item in filters if item)

    def ready_signal(self):
        self.cmd_send("process_image")

    def size_ready(self, width, height, buffer_size):
        self.cmd_send("init_frame", width, height, buffer_size)

    def _apply_view(self):
        """Done by the widget."""

    def cleanup(self):
        if self.renderer is not None:
            self.renderer.stop()

        try:
            super().cleanup()

            with holding(self.shared_memory.lock) as is_locked:
                if not is_locked:
                    self._log.warning("Frame lock was not given back")

                self.shared_memory.close()
        finally:
            self.release_callback(self.id)

    def cleanup_final(self):
        self.cmd_loop_terminate()


class VideoDriverMPVSW(PlayerDriverThreaded):
    set_dummy_frame_sig = pyqtSignal()
    image_ready_sig = pyqtSignal()

    def __init__(self, image_dest, process_manager, **kwargs):
        super().__init__(**kwargs)

        self._width = None
        self._height = None

        self._image_dest = image_dest
        self._shared_memory = None
        self._frame_reader = FrameReader()
        self._show_scheduled = False

        qt_connect(
            (self.set_dummy_frame_sig, self.set_dummy_frame),
            (self.image_ready_sig, self.image_ready),
        )

        self.player = process_manager.init_player(
            {}, self.cmd_child_pipe(), NO_OPTIONS, on_crash=self.process_crashed
        )

    def init_frame(self, width, height, buffer_size):
        self._shared_memory = self.player.get_player_shared_data()

        # a bigger frame means a new segment, which the player process has
        # already allocated by the time it tells us about it
        try:
            with holding(self._shared_memory.lock) as is_locked:
                if is_locked:
                    self._shared_memory.attach(buffer_size)
        except RuntimeError as err:
            self._log.warning(f"Frame buffer is not there: {err}")

        self._width = width
        self._height = height

        self.set_dummy_frame_sig.emit()

    def set_dummy_frame(self):
        self._image_dest.present_black(self._width, self._height)

    def process_image(self):
        if self._shared_memory is None or not self._width or not self._height:
            return

        self.image_ready_sig.emit()

    def image_ready(self):
        if self._show_scheduled:
            return

        self._show_scheduled = True
        QTimer.singleShot(0, self._show_frame)

    def _show_frame(self):
        self._show_scheduled = False

        # the pipe thread can move these on while we copy
        shared_memory, width, height = self._shared_memory, self._width, self._height
        if shared_memory is None or not width or not height:
            return

        try:
            frame = self._frame_reader.read(shared_memory, width, height)
        except (AttributeError, RuntimeError):
            self._log.warning("Shared memory is cleared already")
            return

        if frame is not None:
            self._image_dest.present_rgb32(frame, width, height)

    def cleanup_start(self):
        self._show_scheduled = False
        self._frame_reader.clear()

        if self._shared_memory is not None:
            with holding(self._shared_memory.lock) as is_locked:
                if not is_locked:
                    self._log.warning("Frame lock was not given back")

                self._shared_memory.close()
                self._shared_memory = None

        super().cleanup_start()

    def cleanup_wait(self):
        super().cleanup_wait()

        self.player.cleanup()


class VideoFrameMPVSW(VideoFrameProcess):
    def driver_setup(self) -> VideoDriverMPVSW:
        return VideoDriverMPVSW(
            image_dest=self.video_surface,
            process_manager=self.process_manager,
            parent=self,
        )

    def ui_video_surface(self):
        return SoftwareVideoSurface(self)

    def take_snapshot(self) -> None:
        # last frame stays painted on the surface
        self.video_driver.set_pause(True)

    def shown_frame_image(self):
        return self.video_surface.frame_image()

    def screenshot_view(self):
        return ScreenshotView(
            self._pane_size(),
            self._view,
            self._transform,
            self.video_surface.picture_size(),
            self._orientation(),
            self._pixel_aspect(),
        )

    def adjust_view(self):
        if super().adjust_view():
            return

        self.video_surface.set_view(
            self._view, self._transform, self._frame_size(), self._pixel_aspect()
        )

    def _view_frame_size(self):
        return self.video_surface.picture_size()
