"""Videos mpv draws straight into a window of ours, each process holding several."""

from threading import Event

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from gridplayer.mpv_player.instance import InstanceProcessMPV
from gridplayer.mpv_player.player import MpvPlayerThreaded
from gridplayer.mpv_player.video_driver_base_threaded import PlayerDriverThreaded
from gridplayer.settings import Settings
from gridplayer.utils.gpu_adapters import gpu_adapters, resolve_gpu_adapter
from gridplayer.widgets.video_frame_base import (
    NATIVE_VIEW_RESIZE_INTERVAL_MS,
    VideoFrameProcess,
)

# Keep the window alive until mpv has stopped drawing into it.
PLAYER_RELEASE_TIMEOUT_S = 5

# Every player shares this one, so that they share processes too.
NO_OPTIONS = []


class InstanceProcessMPVHW(InstanceProcessMPV):
    def new_player(self, player_id, init_data, pipe):
        self._players[player_id] = PlayerProcessSingleMPVHW(
            player_id=player_id,
            release_callback=self.release_player,
            init_data=init_data,
            crash_func=self.crash,
            pipe=pipe,
        )


class PlayerProcessSingleMPVHW(MpvPlayerThreaded):
    def __init__(self, player_id, release_callback, init_data, **kwargs):
        super().__init__(**kwargs)

        self.id = player_id
        self.release_callback = release_callback
        self.win_id = init_data["win_id"]
        self.pixel_ratio = init_data.get("pixel_ratio", 1)

        self.start()

    def _mpv_options(self):
        options = {"wid": str(self.win_id)}

        adapter = resolve_gpu_adapter(
            Settings().sync_get("player/gpu_adapter"), gpu_adapters()
        )

        if adapter is not None:
            options["d3d11_adapter"] = adapter

        return options

    def _pane_pixels(self):
        return super()._pane_pixels() * self.pixel_ratio**2

    def cleanup(self):
        try:
            super().cleanup()
        finally:
            try:
                self.cmd_send("player_released")
            except Exception:
                self._log.warning(
                    "Failed to notify parent that player was released",
                    exc_info=True,
                )
            self.release_callback(self.id)

    def cleanup_final(self):
        self.cmd_loop_terminate()


class VideoDriverMPVHW(PlayerDriverThreaded):
    def __init__(self, win_id, process_manager, pixel_ratio=1, **kwargs):
        super().__init__(**kwargs)

        self._released = Event()

        self.player = process_manager.init_player(
            {"win_id": win_id, "pixel_ratio": pixel_ratio},
            self.cmd_child_pipe(),
            NO_OPTIONS,
            on_crash=self.process_crashed,
        )

    def player_released(self):
        self._released.set()

    def player_gone(self):
        self._released.set()

    def cleanup_wait(self):
        if not self._released.wait(timeout=PLAYER_RELEASE_TIMEOUT_S):
            self._log.warning("Timed out waiting for mpv to release the video window")

        super().cleanup_wait()

        self.player.cleanup()

    def adjust_view(self, size, view):
        self.cmd_send("adjust_view", size, view)


class VideoFrameMPVHW(VideoFrameProcess):
    resize_view_interval_ms = NATIVE_VIEW_RESIZE_INTERVAL_MS
    is_native_surface = True

    def driver_setup(self):
        return VideoDriverMPVHW(
            win_id=int(self.video_surface.winId()),
            pixel_ratio=self.devicePixelRatioF(),
            process_manager=self.process_manager,
            parent=self,
        )

    def ui_video_surface(self):
        video_surface = QWidget(self.video_clip)
        video_surface.setMouseTracking(True)
        video_surface.setWindowFlags(Qt.WindowTransparentForInput)
        video_surface.setAttribute(Qt.WA_TransparentForMouseEvents)

        return video_surface

    def adjust_view(self):
        if super().adjust_view():
            return

        self._place_native_surface()

        size = (self.size().width(), self.size().height())
        self.video_driver.adjust_view(size, self._view)
