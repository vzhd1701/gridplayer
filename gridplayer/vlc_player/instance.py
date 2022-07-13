import ctypes
import logging
import platform
import shlex
import warnings
from pathlib import Path
from typing import Iterator

import certifi

from gridplayer.multiprocess.instance_process import InstanceProcess
from gridplayer.multiprocess.process_manager import ProcessManager
from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.vlc_player.libvlc import vlc

# Prepare `vsnprintf` function
if env.IS_WINDOWS:
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

VLC_USER_AGENT_NAME = "Mozilla"
VLC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/99.0.7113.93 Safari/537.36"
)


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

    def init_player_shared_data(self, player_id):
        ...

    def release_player_shared_data(self, player_id):
        ...

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

    @property
    def init_options(self):
        options = [
            # this option is good for making video loop forever,
            # but glitchy files will retry 65535 times before giving up
            # --input-repeat=65535
            # these two only work with playlists
            # --repeat
            # --loop
            "--play-and-pause",
            "--quiet",
            "--no-disable-screensaver",
            "--no-sub-autodetect-file",
            "--no-lua",
            "--no-osd",
            "--no-snapshot-preview",
            "--no-spu",
            "--no-interact",
            "--no-stats",
            "--no-keyboard-events",
            "--no-mouse-events",
            # "--http-reconnect",
            *self.vlc_options,
            *_iter_settings_options(),
        ]

        self._logger.debug(f"VLC init options: {options}")

        if _is_plugin_cache_exists():
            self._logger.debug("Using plugin cache")
            options.append("--no-plugins-scan")
        # https://forum.videolan.org/viewtopic.php?t=147229

        if env.IS_WINDOWS:
            options.append("--aout=directsound")

            # Root CAs are outdated on Windows 7
            if platform.release() == "7":
                cert_dir = str(Path(certifi.where()).parent)

                self._logger.debug(f"Using certifi root CA dir: {cert_dir}")

                options.append("--no-gnutls-system-trust")
                options.append(f"--gnutls-dir-trust={cert_dir}")

        if env.IS_APPIMAGE:
            options.append("--aout=pulse")

        return options

    # process
    def init_instance(self):
        self._logger = logging.getLogger("VLC")

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        self.vlc_instance = vlc.Instance(self.init_options)

        if self.vlc_instance is None:
            raise RuntimeError("VLC failed to initialize")

        self.vlc_instance.set_user_agent(VLC_USER_AGENT_NAME, VLC_USER_AGENT)

        self.init_logger()

    # process
    def cleanup_instance(self):
        self.vlc_instance.release()

    # process
    def init_logger(self):
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
        log_txt = self._logger_buf.raw[:str_len].decode(errors="ignore")

        log_head = f"{m_file.decode(errors='ignore')}:{m_line}"
        log_msg = f"{m_name.decode(errors='ignore')}: {log_txt}"

        return log_head, log_msg


class ProcessManagerVLC(ProcessManager):
    def set_log_level_vlc(self, log_level):
        for a in self.active_instances:
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


def _is_plugin_cache_exists() -> bool:
    if vlc.plugin_path is None:
        return False

    plugin_cache_path = Path(vlc.plugin_path) / "plugins.dat"

    return plugin_cache_path.is_file()


def _iter_settings_options() -> Iterator[str]:  # noqa: WPS231
    options = shlex.split(Settings().sync_get("misc/vlc_options"))

    for opt_idx, opt in enumerate(options):
        if not opt.startswith("-"):
            continue

        if opt_idx + 1 < len(options):
            next_opt = options[opt_idx + 1]
        else:
            next_opt = None

        # --option=value
        if "=" in opt:
            yield opt

        # --option value
        elif next_opt and not next_opt.startswith("-"):
            yield f"{opt}={next_opt}"

        # --flag
        else:
            yield opt
