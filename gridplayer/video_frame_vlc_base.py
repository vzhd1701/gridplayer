import ctypes
import logging
import platform
import time

from gridplayer import params_env
from gridplayer.params_vlc import pre_import_embed_vlc
from gridplayer.settings import settings

pre_import_embed_vlc()
import vlc
from PyQt5 import QtCore
from PyQt5.QtCore import QObject

from gridplayer.utils.multiprocessing import (
    CommandLoopThreaded,
    InstanceProcess,
    ProcessManager,
)

# Prepare `vsnprintf` function
if platform.system() == "Windows":
    # Note: must use same version of libc as libvlc
    vsnprintf = ctypes.cdll.msvcrt.vsnprintf
else:
    libc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("c"))
    vsnprintf = libc.vsnprintf

vsnprintf.restype = ctypes.c_int
vsnprintf.argtypes = (
    ctypes.c_char_p,
    ctypes.c_size_t,
    ctypes.c_char_p,
    ctypes.c_void_p,
)


class VlcPlayerBase:
    def __init__(self, vlc_instance):
        self.instance = vlc_instance

        self.is_video_initialized = False
        self.is_first_start_finished = False
        self.is_waiting_for_buffer = False

        self.media_player = None
        self.media = None
        self.media_options = []

        self.video_dimensions = None
        self.length = None
        self.fps = None

        self.log = logging.getLogger(self.__class__.__name__)

    def init_player(self):
        self.media_player = self.instance.media_player_new()

        self.media_player.audio_set_mute(True)
        self.media_player.video_set_mouse_input(False)
        self.media_player.video_set_key_input(False)

        self.media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerTimeChanged, self.cb_time_changed
        )

        self.media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerBuffering, self.cb_buffering
        )

        self.media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerEncounteredError, self.cb_error
        )

    def cleanup(self):
        self.media_player.stop()

        while self.media_player.get_state() != vlc.State.Stopped:
            time.sleep(0.01)

        self.media_player.release()

    def notify_error(self):
        pass

    def notify_time_change(self, new_time):
        pass

    def notify_load_video_finish(self, video_params):
        pass

    def loopback_load_video_player(self):
        pass

    def loopback_load_video_finish(self):
        pass

    def cb_error(self, event):
        self.log.error("MediaPlayer encountered an error!")
        self.notify_error()

    def cb_parse_changed(self, event):
        if event.u.new_status != vlc.MediaParsedStatus.done:
            status_txt = str(vlc.MediaParsedStatus(event.u.new_status))
            self.log.error(f"Media parse failed! Status changed to {status_txt}.")
            return self.notify_error()

        video_track = self._get_video_track()

        if video_track is None:
            self.log.error("Video track is missing!")
            return self.notify_error()

        self.video_dimensions = (video_track.width, video_track.height)
        self.length = self.media.get_duration()
        self.fps = video_track.frame_rate_num / video_track.frame_rate_den

        self.log.debug("Video parsed")
        self.log.debug("========")
        self.log.debug(
            f"Dimensions: {self.video_dimensions[0]}x{self.video_dimensions[1]}"
        )
        self.log.debug(f"Length: {self.length}")
        self.log.debug(f"FPS: {self.fps}")
        self.log.debug("========")

        self.loopback_load_video_player()

    def _get_video_track(self):
        video_tracks = (
            t.u.video.contents
            for t in self.media.tracks_get()
            if t.type == vlc.TrackType.video
        )

        video_track = next(video_tracks, None)

        if (
            video_track is None
            or video_track.frame_rate_num == 0
            or video_track.frame_rate_den == 0
            or video_track.width == 0
            or video_track.height == 0
            or self.media.get_duration() == 0
        ):
            return None

        return video_track

    def cb_time_changed(self, event):
        # Doesn't work anymore since python-vlc-3.0.12117
        new_time = event.u.new_time

        # new_time = self.media_player.get_time()

        if not self.is_first_start_finished:
            if new_time == 0:
                return

            self.is_first_start_finished = True

            self.loopback_load_video_finish()

        if not self.is_video_initialized:
            return

        self.notify_time_change(new_time)

    def cb_buffering(self, event):
        if not self.is_waiting_for_buffer:
            return

        if event.u.new_cache == 100.0:
            self.is_waiting_for_buffer = False

    def load_video(self, file_path):
        """Step 1. Load & parse video file"""

        self.log.info(f"Loading {file_path}")

        self.media = self.instance.media_new_path(file_path)

        if self.media is None:
            self.log.error(f"Failed to load file {file_path}!")
            return self.notify_error()

        self.media.event_manager().event_attach(
            vlc.EventType.MediaParsedChanged, self.cb_parse_changed
        )

        # Disable hardware decoding
        self.media.add_options(*self.media_options)

        self.media.parse_with_options(vlc.MediaParseFlag.local, -1)

    def load_video_player(self):
        """Step 2. Start video player with parsed file"""

        self.log.debug("Setting parsed media to player")

        self.media_player.set_media(self.media)

        self.media_player.play()

    def load_video_finish(self):
        """Step 3. Make sure video buffered and properly seekable"""

        self.log.debug("Load finished")

        self.media_player.set_pause(1)
        while self.media_player.get_state() != vlc.State.Paused:
            time.sleep(0.01)

        self.is_waiting_for_buffer = True

        self.media_player.set_time(0)
        while self.media_player.get_time() != 0:
            time.sleep(0.01)

        # waiting for buffering to display paused frame
        while self.is_waiting_for_buffer:
            time.sleep(0.01)

        self.is_video_initialized = True

        video_params = {
            "length": self.length,
            "fps": self.fps,
            "video_dimensions": self.video_dimensions,
        }

        self.notify_load_video_finish(video_params)

    def play(self):
        self.media_player.play()

    def set_pause(self, is_paused):
        self.media_player.set_pause(is_paused)

    def set_time(self, seek_ms):
        is_initial_set_time = (
            self.media_player.get_state() == vlc.State.Paused
            and self.media_player.get_time() == 0
        )

        if is_initial_set_time:
            self.set_time_ensure(seek_ms)
        else:
            self.media_player.set_time(seek_ms)

    def set_time_ensure(self, seek_ms):
        self.media_player.set_time(seek_ms + 1)

        self.is_waiting_for_buffer = True
        while self.is_waiting_for_buffer:
            time.sleep(0.01)
        self.media_player.set_time(seek_ms)
        self.is_waiting_for_buffer = True
        while self.is_waiting_for_buffer:
            time.sleep(0.01)

    def set_playback_rate(self, rate):
        self.media_player.set_rate(rate)

    def audio_set_mute(self, is_muted):
        self.media_player.audio_set_mute(is_muted)

    def audio_set_volume(self, volume):
        self.media_player.audio_set_volume(volume)


class VlcPlayerThreaded(CommandLoopThreaded, VlcPlayerBase):
    def __init__(self, vlc_instance, crash_func, pipe):
        CommandLoopThreaded.__init__(self, crash_func=crash_func, pipe=pipe)
        VlcPlayerBase.__init__(self, vlc_instance)

    def start(self):
        self.cmd_loop_start_thread(self.init_player)

    def notify_error(self):
        self.cmd_send("error_state")

    def notify_time_change(self, new_time):
        self.cmd_send("time_change_emit", new_time)

    def notify_load_video_finish(self, video_params):
        self.cmd_send("load_video_finish", video_params)

    def loopback_load_video_player(self):
        self.cmd_send_self("load_video_player")

    def loopback_load_video_finish(self):
        self.cmd_send_self("load_video_finish")


class VLCVideoDriverThreaded(CommandLoopThreaded, QObject):
    time_changed = QtCore.pyqtSignal(int)
    load_finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal()
    crash = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent=parent)
        CommandLoopThreaded.__init__(self, crash_func=self.crash_thread)

        self.length = 0
        self.fps = None

        self.cmd_loop_start_thread()

    def crash_thread(self, traceback_txt):
        self.crash.emit(traceback_txt)

    def cleanup(self):
        self.cmd_send("cleanup")
        self.cmd_loop_terminate()

    def time_change_emit(self, new_time):
        self.time_changed.emit(new_time)

    def load_video(self, file_path):
        self.cmd_send("load_video", file_path)

    def load_video_finish(self, video_params):
        self.length = video_params["length"]
        self.fps = video_params["fps"]

        self.load_finished.emit()

    def play(self):
        self.cmd_send("play")

    def set_pause(self, is_paused):
        self.cmd_send("set_pause", is_paused)

    def set_time(self, seek_ms):
        self.cmd_send("set_time", seek_ms)

    def set_playback_rate(self, rate):
        self.cmd_send("set_playback_rate", rate)

    def get_ms_per_frame(self):
        return int(1000 // self.fps)

    def audio_set_mute(self, is_muted):
        self.cmd_send("audio_set_mute", is_muted)

    def audio_set_volume(self, volume):
        self.cmd_send("audio_set_volume", volume)

    def error_state(self):
        self.error.emit()


class InstanceProcessVLC(InstanceProcess):
    log_level_map = {
        vlc.LogLevel.DEBUG: logging.DEBUG,
        vlc.LogLevel.ERROR: logging.ERROR,
        vlc.LogLevel.NOTICE: logging.INFO,
        vlc.LogLevel.WARNING: logging.WARNING,
    }

    def __init__(
        self,
        players_per_instance,
        pm_callback_pipe,
        pm_log_queue,
        log_level,
        vlc_log_level,
    ):
        super().__init__(
            players_per_instance, pm_callback_pipe, pm_log_queue, log_level
        )

        self._vlc_instance = None
        self._vlc_options = []
        self._vlc_log_level = vlc_log_level

        self._logger = None
        self._logger_cb = None
        self._logger_buf = None
        self._logger_buf_len = 1024

    # process
    def init_instance(self):
        options = [
            "--input-repeat=65535",
            "--quiet",
            "--no-disable-screensaver",
            "--no-sub-autodetect-file",
            *self._vlc_options,
        ]

        # https://forum.videolan.org/viewtopic.php?t=147229
        if platform.system() == "Windows":
            options.append("--aout=directsound")

        if params_env.IS_APPIMAGE:
            options.append("--aout=pulse")

        self._vlc_instance = vlc.Instance(options)

        if self._vlc_instance is None:
            raise RuntimeError("VLC failed to initialize")

        self.init_logger()

    # process
    def cleanup_instance(self):
        self._vlc_instance.release()

    # process
    def init_logger(self):
        self._logger = logging.getLogger("VLC")
        self._logger_cb = self.get_libvlc_log_callback()
        self._logger_buf = ctypes.create_string_buffer(self._logger_buf_len)

        self._vlc_instance.log_set(self._logger_cb, None)

    # process
    def get_libvlc_log_callback(self):
        @vlc.CallbackDecorators.LogCb
        def _cb(data, level, ctx, fmt, args):
            log_level = self.log_level_map[vlc.LogLevel(level)]

            if log_level < self._vlc_log_level:
                return

            m_name, m_file, m_line = vlc.libvlc_log_get_context(ctx)

            # Format given fmt/args pair
            str_len = vsnprintf(self._logger_buf, self._logger_buf_len, fmt, args)
            log_txt = self._logger_buf.raw[:str_len].decode()

            log_msg = f"{m_name.decode()}: {log_txt}"

            if self._logger.level == logging.DEBUG:
                log_head = f"{m_file.decode()}:{m_line}"
                self._logger.log(log_level, log_head)

            self._logger.log(log_level, log_msg)

        return _cb

    # outside
    def request_set_log_level_vlc(self, log_level):
        self.cmd_send_self("set_log_level_vlc", log_level)

    # process
    def set_log_level_vlc(self, log_level):
        self._vlc_log_level = log_level


class ProcessManagerVLC(ProcessManager):
    def set_log_level_vlc(self, log_level):
        active_instances = (i for i in self.instances.values() if not i.is_dead.value)

        for a in active_instances:
            a.request_set_log_level_vlc(log_level)

    def create_instance(self):
        log_level = settings.get("logging/log_level")
        log_level_vlc = settings.get("logging/log_level_vlc")

        return self.instance_class(
            self.limit, self._self_pipe, self.log_queue, log_level, log_level_vlc
        )
