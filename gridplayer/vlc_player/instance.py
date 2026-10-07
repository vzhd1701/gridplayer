import ctypes
import logging
import platform
import shlex
import warnings
from collections.abc import Iterator
from pathlib import Path

import certifi

from gridplayer.multiprocess.instance_process import InstanceProcess
from gridplayer.multiprocess.process_manager import ProcessManager
from gridplayer.params import env
from gridplayer.params.subtitle_style import (
    SUBTITLE_STYLE_SETTINGS,
    subtitle_style_options,
)
from gridplayer.settings import Settings
from gridplayer.utils.network import vlc_user_agent
from gridplayer.utils.win32_com import keep_mta_alive
from gridplayer.vlc_player.libvlc import vlc
from gridplayer.vlc_player.vlc_errors import (
    http_refusal,
    is_http_answer,
    is_keeping_vlc_errors,
    is_said_of_vlc_itself,
    keep_vlc_error,
    note_vlc_object,
)

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

# The VLC object a log line was said as. vlc.py's binding of it takes the
# object's id in, where the C function hands its type name, its header and
# its id back.
_log_get_object = ctypes.CFUNCTYPE(
    None,
    vlc.Log_ptr,
    ctypes.POINTER(ctypes.c_char_p),
    ctypes.POINTER(ctypes.c_char_p),
    ctypes.POINTER(ctypes.c_size_t),
)(("libvlc_log_get_object", vlc.dll))


def _vlc_object_of(ctx) -> int:
    """Which VLC object said it, as a number of its own; 0 for none."""

    vlc_object = ctypes.c_size_t()
    _log_get_object(ctx, None, None, ctypes.byref(vlc_object))

    return vlc_object.value


def _vlc_object_type_of(ctx) -> bytes:
    """What kind of VLC object said it: b"demux", b"stream", ..."""

    name = ctypes.c_char_p()
    _log_get_object(ctx, ctypes.byref(name), None, None)

    return name.value or b""


VLC_USER_AGENT_NAME = "Mozilla"


class InstanceProcessVLC(InstanceProcess):
    def __init__(self, vlc_log_level, **kwargs):
        super().__init__(**kwargs)

        self._vlc = InstanceVLC(vlc_log_level, kwargs["options"])

    @property
    def vlc_instance(self):
        return self._vlc.vlc_instance

    def init_instance(self):
        self._vlc.init_instance()

    def cleanup_instance(self):
        self._vlc.cleanup_instance()

    def init_player_shared_data(self, player_id): ...

    def release_player_shared_data(self, player_id): ...

    # outside
    def request_set_log_level_vlc(self, log_level):
        self.cmd_send_self("set_log_level_vlc", log_level)

    # process
    def set_log_level_vlc(self, log_level):
        self._vlc.set_log_level_vlc(log_level)


class InstanceVLC:
    log_level_map = {
        vlc.LogLevel.DEBUG: logging.DEBUG,
        vlc.LogLevel.ERROR: logging.ERROR,
        vlc.LogLevel.NOTICE: logging.INFO,
        vlc.LogLevel.WARNING: logging.WARNING,
    }

    def __init__(self, vlc_log_level, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self.vlc_instance = None
        self.vlc_options = vlc_options.copy()

        self._vlc_log_level = vlc_log_level

        self._logger = None
        self._logger_cb = None
        self._logger_buf_len = 1024

    @property
    def init_options(self):
        options = [
            "--quiet",
            "--no-disable-screensaver",
            # subtitle files beside a video are found by us rather than by
            # VLC, so that a video opens with the one that was picked for it
            # and nothing else; see gridplayer.utils.external_subtitles
            "--no-sub-autodetect-file",
            "--no-lua",
            "--no-osd",
            "--no-snapshot-preview",
            # NOTE: "--no-spu" must not go here. It is settled when the input
            # opens and cannot be undone afterwards: libvlc_video_set_spu then
            # returns success and libvlc_video_get_spu reports the track, while
            # nothing is ever decoded or drawn. Subtitles are switched off per
            # video instead, by asking for no track at all; see TracksManager.
            "--no-interact",
            # NOTE: no "--no-stats" either. How many pictures VLC has put on
            # screen is the only sign that a stream it froze on its first
            # one has started playing; see VlcPlayerBase._check_playback_started
            "--no-keyboard-events",
            "--no-mouse-events",
            *self.vlc_options,
            *_audio_output_options(),
            # before the options typed by hand, which are last so that
            # they still win over anything a page here has set
            *_subtitle_style_options(),
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

        # before any video output can open a window
        keep_mta_alive()

        self.vlc_instance = vlc.Instance(self.init_options)

        if self.vlc_instance is None:
            raise RuntimeError("VLC failed to initialize")

        self.vlc_instance.set_user_agent(VLC_USER_AGENT_NAME, vlc_user_agent())

        self.init_logger()

    # process
    def cleanup_instance(self):
        self.vlc_instance.release()

    # process
    def init_logger(self):
        self._logger_cb = self.libvlc_log_callback()

        self.vlc_instance.log_set(self._logger_cb, None)

    # process
    def libvlc_log_callback(self):
        @vlc.CallbackDecorators.LogCb
        def _cb(ptr_data, level, ctx, fmt, args):
            log_level = self.log_level_map[vlc.LogLevel(level)]

            # whatever is said, by whom: what a video's object says on a
            # thread of no video, fetching its segments, is the video's
            vlc_object = _vlc_object_of(ctx)
            note_vlc_object(vlc_object)

            # kept whatever is logged, for a video that fails to tell
            is_kept = (
                log_level >= logging.ERROR
                and not is_said_of_vlc_itself(fmt)
                and is_keeping_vlc_errors()
            )

            # what a server answered the segments of a stream being fetched,
            # said nowhere else; the HTTP access says it as an error itself
            is_answer = (
                log_level == logging.DEBUG
                and is_http_answer(fmt)
                and _vlc_object_type_of(ctx) == b"demux"
            )

            is_logged = log_level >= self._vlc_log_level

            if not (is_kept or is_answer or is_logged):
                return

            # formatted once: the arguments are used up by it on some systems
            log_head, log_msg = self._format_log_msg(args, ctx, fmt)

            if is_kept:
                keep_vlc_error(log_msg, vlc_object)

            if is_answer:
                refusal = http_refusal(log_msg)

                if refusal is not None and is_keeping_vlc_errors():
                    keep_vlc_error(refusal, vlc_object)

            if not is_logged:
                return

            if self._logger.level == logging.DEBUG:
                self._logger.log(log_level, log_head)

            self._logger.log(log_level, log_msg)

        return _cb

    # process
    def set_log_level_vlc(self, log_level):
        self._vlc_log_level = log_level

    def _format_log_msg(self, args, ctx, fmt):
        m_name, m_file, m_line = vlc.libvlc_log_get_context(ctx)

        # Format given fmt/args pair, in a buffer of its own: VLC logs from
        # several threads at once
        buffer = ctypes.create_string_buffer(self._logger_buf_len)
        str_len = vsnprintf(buffer, self._logger_buf_len, fmt, args)
        log_txt = buffer.raw[: min(str_len, self._logger_buf_len - 1)].decode(
            errors="ignore"
        )

        log_head = f"{m_file.decode(errors='ignore')}:{m_line}"
        log_msg = f"{m_name.decode(errors='ignore')}: {log_txt}"

        return log_head, log_msg


class ProcessManagerVLC(ProcessManager):
    def set_log_level_vlc(self, log_level):
        for a in self.active_instances:
            a.request_set_log_level_vlc(log_level)

    def create_instance(self, options):
        log_level_vlc = Settings().get("logging/log_level_vlc")

        instance = self._instance_class(
            players_per_instance=self._limit,
            pm_callback_pipe=self._self_pipe,
            options=options,
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


def _subtitle_style_options() -> list[str]:
    """What subtitles are to look like in the process about to start.

    Read here rather than passed in because this runs in that process,
    where the settings are read off the disk like every other one.
    """

    style = {key: Settings().sync_get(key) for key in SUBTITLE_STYLE_SETTINGS}

    return subtitle_style_options(style)


def _audio_output_options() -> list[str]:
    """Audio output to ask VLC for, ahead of any typed by hand."""

    if env.IS_LINUX:
        return ["--aout=pulse,any"]

    return []


def _iter_settings_options() -> Iterator[str]:
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
