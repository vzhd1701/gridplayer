from multiprocessing import Semaphore

from PyQt5.QtCore import QMargins, Qt
from PyQt5.QtWidgets import QWidget

from gridplayer.params import env
from gridplayer.vlc_player.instance import InstanceProcessVLC
from gridplayer.vlc_player.player_base_threaded import VlcPlayerThreaded
from gridplayer.vlc_player.static import MediaTrack
from gridplayer.vlc_player.video_driver_base_threaded import VLCVideoDriverThreaded
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLCProcess


class InstanceProcessVLCHW(InstanceProcessVLC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.init_semaphore = Semaphore()

    def new_player(self, player_id, init_data, pipe):
        init_data["init_semaphore"] = self.init_semaphore

        player = PlayerProcessSingleVLCHW(
            player_id=player_id,
            release_callback=self.release_player,
            init_data=init_data,
            vlc_instance=self.vlc_instance,
            crash_func=self.crash,
            pipe=pipe,
        )
        self._players[player_id] = player


class PlayerProcessSingleVLCHW(VlcPlayerThreaded):
    def __init__(
        self,
        player_id,
        release_callback,
        init_data,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.id = player_id
        self.release_callback = release_callback

        self.win_id = init_data["win_id"]
        self.init_semaphore = init_data["init_semaphore"]

        self.start()

    def init_player(self):
        # video loading is not thread safe on linux
        if env.IS_LINUX:
            self.init_semaphore.acquire()
            self._log.debug("Semaphore acquired")

        super().init_player()

        if env.IS_LINUX:
            self._media_player.set_xwindow(self.win_id)
        elif env.IS_WINDOWS:
            self._media_player.set_hwnd(self.win_id)
        elif env.IS_MACOS:
            self._media_player.set_nsobject(self.win_id)

    def notify_load_video_done(self, media_track: MediaTrack):
        if env.IS_LINUX:
            self.init_semaphore.release()
            self._log.debug("Semaphore released")

        super().notify_load_video_done(media_track)

    def cleanup(self):
        if env.IS_LINUX:
            self.init_semaphore.release()

        super().cleanup()

        self.release_callback(self.id)

    def cleanup_final(self):
        self.cmd_loop_terminate()


class VideoDriverVLCHW(VLCVideoDriverThreaded):
    def __init__(self, win_id, process_manager, **kwargs):
        super().__init__(**kwargs)

        process_manager.init_player({"win_id": win_id}, self.cmd_child_pipe())

    def adjust_view(self, size, aspect, scale):
        self.cmd_send("adjust_view", size, aspect, scale)


class VideoFrameVLCHW(VideoFrameVLCProcess):
    is_opengl = True

    def driver_setup(self):
        return VideoDriverVLCHW(
            win_id=int(self.video_surface.winId()),
            process_manager=self.process_manager,
            parent=self,
        )

    def ui_video_surface(self):
        if env.IS_MACOS:
            # Drawing using window id from another process is not possible on MacOS
            # https://stackoverflow.com/questions/583202/mac-os-x-can-one-process-render-to-another-processs-window
            raise NotImplementedError()

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
