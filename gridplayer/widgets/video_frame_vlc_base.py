import ctypes
import logging
import platform
import time

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer import params_env
from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.multiprocess.instance_process import InstanceProcess
from gridplayer.multiprocess.process_manager import ProcessManager
from gridplayer.settings import Settings
from gridplayer.utils.libvlc import pre_import_embed_vlc

# Need to set env variables before importing vlc
pre_import_embed_vlc()
import vlc  # noqa: E402

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

ONE_MOMENT = 0.01
DEFAULT_FPS = 25


class VlcPlayerBase(object):
    def __init__(self, vlc_instance, **kwargs):
        super().__init__(**kwargs)

        self.instance = vlc_instance

        self.is_video_initialized = False

        self.length = None
        self.video_dimensions = None
        self.fps = None

        self._is_first_start_finished = False
        self._is_waiting_for_buffer = False
        self._is_meta_loaded = False

        self._media_player = None
        self._media = None
        self._media_options = []

        self._log = logging.getLogger(self.__class__.__name__)

    def init_player(self):
        self._media_player = self.instance.media_player_new()

        self._media_player.audio_set_mute(True)
        self._media_player.video_set_mouse_input(False)
        self._media_player.video_set_key_input(False)

        self._media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerTimeChanged, self.cb_time_changed
        )

        self._media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerBuffering, self.cb_buffering
        )

        self._media_player.event_manager().event_attach(
            vlc.EventType.MediaPlayerEncounteredError, self.cb_error
        )

    def cleanup(self):
        if self._media_player is not None:
            self.stop()

            self._media_player.release()
            self._media_player = None

    def notify_error(self):
        """Emit signal when error"""

    def notify_time_change(self, new_time):
        """Emit new video time"""

    def notify_load_video_finish(self, video_params):
        """Emit signal when video is fully loaded"""

    def loopback_load_video_player(self):
        """Emit signal to self when video is ready to be loaded into player"""

    def loopback_load_video_finish(self):
        """Emit signal to self when video is loaded into player"""

    def cb_error(self, event):
        self._log.error("MediaPlayer encountered an error!")
        self.notify_error()

    def cb_parse_changed(self, event):
        if event.u.new_status != vlc.MediaParsedStatus.done:
            status_txt = str(vlc.MediaParsedStatus(event.u.new_status))
            self._log.error(f"Media parse failed! Status changed to {status_txt}.")
            return self.notify_error()

        self._extract_meta_parse()

        self.loopback_load_video_player()

    def cb_time_changed(self, event):
        # Doesn't work anymore since python-vlc-3.0.12117
        new_time = event.u.new_time

        if not self._is_first_start_finished:
            if new_time == 0:
                return

            self._is_first_start_finished = True

            self.loopback_load_video_finish()

        if not self.is_video_initialized:
            return

        self.notify_time_change(new_time)

    def cb_buffering(self, event):
        if not self._is_waiting_for_buffer:
            return

        if int(event.u.new_cache) == 100:
            self._is_waiting_for_buffer = False

    def load_video(self, file_path):
        """Step 1. Load & parse video file"""
        self._log.info(f"Loading {file_path}")

        self._media = self.instance.media_new_path(file_path)

        if self._media is None:
            self._log.error(f"Failed to load file {file_path}!")
            return self.notify_error()

        self._media.event_manager().event_attach(
            vlc.EventType.MediaParsedChanged, self.cb_parse_changed
        )

        self._media.add_options(*self._media_options)

        self._media.parse_with_options(vlc.MediaParseFlag.local, -1)

    def load_video_player(self):
        """Step 2. Start video player with parsed file"""

        self._log.debug("Setting parsed media to player")

        self._media_player.set_media(self._media)

        self._media_player.play()

    def load_video_finish(self):
        """Step 3. Make sure video buffered and properly seekable"""

        if not self._is_meta_loaded:
            self._extract_meta_play()

        self._log.debug("Load finished")

        self._media_player.set_pause(1)
        while self._media_player.get_state() != vlc.State.Paused:
            time.sleep(ONE_MOMENT)

        self._is_waiting_for_buffer = True

        self._media_player.set_time(0)
        while self._media_player.get_time() != 0:
            time.sleep(ONE_MOMENT)

        # waiting for buffering to display paused frame
        while self._is_waiting_for_buffer:
            time.sleep(ONE_MOMENT)

        self.is_video_initialized = True

        video_params = {
            "length": self.length,
            "fps": self.fps,
            "video_dimensions": self.video_dimensions,
        }

        self.notify_load_video_finish(video_params)

    def stop(self):
        self._media_player.stop()

    def play(self):
        self._media_player.play()

    def set_pause(self, is_paused):
        self._media_player.set_pause(is_paused)

    def set_time(self, seek_ms):
        is_initial_set_time = (
            self._media_player.get_state() == vlc.State.Paused
            and self._media_player.get_time() == 0
        )

        if is_initial_set_time:
            self.set_time_ensure(seek_ms)
        else:
            self._media_player.set_time(seek_ms)

    def set_time_ensure(self, seek_ms):
        self._media_player.set_time(seek_ms + 1)

        self._is_waiting_for_buffer = True
        while self._is_waiting_for_buffer:
            time.sleep(ONE_MOMENT)
        self._media_player.set_time(seek_ms)
        self._is_waiting_for_buffer = True
        while self._is_waiting_for_buffer:
            time.sleep(ONE_MOMENT)

    def set_playback_rate(self, rate):
        self._media_player.set_rate(rate)

    def audio_set_mute(self, is_muted):
        self._media_player.audio_set_mute(is_muted)

    def audio_set_volume(self, volume):
        self._media_player.audio_set_volume(volume)

    def _get_video_track(self):
        media_tracks = self._media.tracks_get()

        if not media_tracks:
            return None

        video_tracks = (
            t.u.video.contents for t in media_tracks if t.type == vlc.TrackType.video
        )

        video_track = next(video_tracks, None)

        vital_params = (
            video_track,
            video_track.width,
            video_track.height,
        )

        if not all(vital_params):
            return None

        return video_track

    def _extract_meta_parse(self):
        video_track = self._get_video_track()

        if video_track is None:
            self._log.warning("Video track data is missing, cannot parse metadata.")
            return

        self._log.debug("Parsing metadata...")

        self.length = self._media.get_duration()
        self.video_dimensions = (video_track.width, video_track.height)

        if video_track.frame_rate_num and video_track.frame_rate_den:
            self.fps = video_track.frame_rate_num / video_track.frame_rate_den
        else:
            self.fps = DEFAULT_FPS

        self._is_meta_loaded = True

    def _extract_meta_play(self):
        self._log.debug("Extracting metadata...")

        self.length = self._media.get_duration()
        self.video_dimensions = self._media_player.video_get_size()
        self.fps = self._media_player.get_fps() or DEFAULT_FPS

        self._is_meta_loaded = True


class VlcPlayerThreaded(CommandLoopThreaded, VlcPlayerBase):
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
    time_changed = pyqtSignal(int)
    load_finished = pyqtSignal()
    error = pyqtSignal()
    crash = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.crash_func = self.crash_thread

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
    def __init__(self, vlc_log_level, **kwargs):
        super().__init__(**kwargs)

        self._vlc = InstanceVLC(vlc_log_level)

    @property
    def vlc_instance(self):
        return self._vlc.vlc_instance

    def init_instance(self):
        self._vlc.init_instance()

    def cleanup_instance(self):
        self._vlc.cleanup_instance()

    # outside
    def request_set_log_level_vlc(self, log_level):
        self.cmd_send_self("set_log_level_vlc", log_level)

    # process
    def set_log_level_vlc(self, log_level):
        self._vlc.set_log_level_vlc(log_level)


class InstanceVLC(object):
    log_level_map = {
        vlc.LogLevel.DEBUG: logging.DEBUG,
        vlc.LogLevel.ERROR: logging.ERROR,
        vlc.LogLevel.NOTICE: logging.INFO,
        vlc.LogLevel.WARNING: logging.WARNING,
    }

    def __init__(self, vlc_log_level, **kwargs):
        super().__init__(**kwargs)

        self.vlc_instance = None
        self.vlc_options = []

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
            *self.vlc_options,
        ]

        # https://forum.videolan.org/viewtopic.php?t=147229
        if platform.system() == "Windows":
            options.append("--aout=directsound")

        if params_env.IS_APPIMAGE:
            options.append("--aout=pulse")

        self.vlc_instance = vlc.Instance(options)

        if self.vlc_instance is None:
            raise RuntimeError("VLC failed to initialize")

        self.init_logger()

    # process
    def cleanup_instance(self):
        self.vlc_instance.release()

    # process
    def init_logger(self):
        self._logger = logging.getLogger("VLC")
        self._logger_cb = self.libvlc_log_callback()
        self._logger_buf = ctypes.create_string_buffer(self._logger_buf_len)

        self.vlc_instance.log_set(self._logger_cb, None)

    # process
    def libvlc_log_callback(self):
        @vlc.CallbackDecorators.LogCb
        def _cb(ptr_data, level, ctx, fmt, args):  # noqa: WPS430
            log_level = self.log_level_map[vlc.LogLevel(level)]

            if log_level < self._vlc_log_level:
                return

            log_head, log_msg = self._format_log_msg(args, ctx, fmt)

            if self._logger.level == logging.DEBUG:
                self._logger.log(log_level, log_head)

            self._logger.log(log_level, log_msg)

        return _cb

    # process
    def set_log_level_vlc(self, log_level):
        self._vlc_log_level = log_level

    def _format_log_msg(self, args, ctx, fmt):  # noqa: WPS210
        m_name, m_file, m_line = vlc.libvlc_log_get_context(ctx)

        # Format given fmt/args pair
        str_len = vsnprintf(self._logger_buf, self._logger_buf_len, fmt, args)
        log_txt = self._logger_buf.raw[:str_len].decode()

        log_head = f"{m_file.decode()}:{m_line}"
        log_msg = f"{m_name.decode()}: {log_txt}"

        return log_head, log_msg


class ProcessManagerVLC(ProcessManager):
    def set_log_level_vlc(self, log_level):
        active_instances = (i for i in self.instances.values() if not i.is_dead.value)

        for a in active_instances:
            a.request_set_log_level_vlc(log_level)

    def create_instance(self):
        log_level_vlc = Settings().get("logging/log_level_vlc")

        instance = self._instance_class(
            players_per_instance=self._limit,
            pm_callback_pipe=self._self_pipe,
            vlc_log_level=log_level_vlc,
        )

        if self._log_queue:
            log_level = Settings().get("logging/log_level")
            instance.setup_log_queue(self._log_queue, log_level)

        return instance
