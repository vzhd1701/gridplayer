"""One mpv instance.

Observers and event callbacks run on python-mpv's event thread, where reading
properties may wait: what the GUI needs goes to it by signal, and everything it
does comes through command(), which never waits.
"""

import collections
import dataclasses
import logging
import re
import threading
import time
from collections import defaultdict
from ctypes import c_ulonglong
from fractions import Fraction
from functools import cache
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.models.audio_device import AudioDevice, resolve_device_id
from gridplayer.params import env
from gridplayer.params.static import AudioChannelMode, VideoTransform
from gridplayer.utils.media_libs import find_libvlc
from gridplayer.utils.qt import MILLISECONDS, translate
from gridplayer.vlc_player.static import (
    DISABLED_TRACK,
    AudioTrack,
    Media,
    MediaInput,
    SubtitleTrack,
    VideoTrack,
    wanted_audio_track_id,
    wanted_subtitle_track_id,
)

_log = logging.getLogger(__name__)

# What the file says to turn the picture by, in mpv's degrees clockwise
_ROTATIONS = {
    90: VideoTransform.ROTATE_90,
    180: VideoTransform.ROTATE_180,
    270: VideoTransform.ROTATE_270,
}

# What to turn the picture by for a transform, in degrees clockwise, which mpv
# adds to what the file says. The flips are painted: a filter would take away
# what hardware decoding saves. See video_frame_mpv._FLIPS.
_TURNS = {
    VideoTransform.ROTATE_90: 90,
    VideoTransform.ROTATE_180: 180,
    VideoTransform.ROTATE_270: 270,
    VideoTransform.TRANSPOSE: 90,
    VideoTransform.ANTITRANSPOSE: 90,
}

# How often the time goes to the GUI at most: mpv says every frame, VLC about
# four times a second, and what hangs off it was written for that.
TIME_REPORT_MS = 200

# vd-lavc-skipframe: the decoder leaves out frames nothing else depends on,
# about half of them, where they're there to leave out. mpv's own frame drop
# saves the decoder no work, so past what it can do the video falls apart.
_SKIP_FRAMES = {True: "nonref", False: "default"}

# What mpv said last, for when a video fails
_LOG_LINES_KEPT = 20

# The ways out mpv is to try on Linux: see _options
_LINUX_AUDIO_OUTPUTS = ("pipewire", "pulse", "alsa")

# Down to two channels by mpv's own mix first: lavfi's turns a surround track down
_FROM_STEREO = "format=channels=stereo,lavfi=[pan=stereo|{}]"

# What to put on the two channels for each channel mode that moves them about, compared
# with what VLC sends a sound server. Mono is at half of each, as there: mpv's own mix
# would clip whatever is in both. Stereo and Dolby Surround are the plain mix, Dolby being
# that on VLC too, and so is Headphones where there's no _ROOM_FILTER. All of them go out
# on two channels: a sound server is free to turn one down, as PipeWire does.
_CHANNEL_PANS = {
    AudioChannelMode.RSTEREO: "c0=c1|c1=c0",
    AudioChannelMode.LEFT: "c0=c0|c1=c0",
    AudioChannelMode.RIGHT: "c0=c1|c1=c1",
    AudioChannelMode.MONO: "c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1",
}

# Headphones on a surround track, with the file VLC does it with where VLC has one:
# the levels of VLC's own spatialaudio, measured. Where it has none, as on Linux, VLC
# plays the plain mix as well.
_ROOM_FILE = "hrtfs/dodeca_and_7channel_3DSL_HRTF.sofa"
_ROOM_FILTER = "lavfi=[sofalizer=sofa={}:gain=8.1:lfegain=3]"

# What's safe to say inside a filter, and what libmysofa can open
_ROOM_FILE_CHARS = re.compile(r"[A-Za-z0-9 ./:()_-]+")

# mpv's mix turns one channel into two down by 3 dB, where VLC has it as it is. Only
# for a track with one channel: this raises anything else that goes through the mix.
# Two it has to be, as with Mono: left to a sound server it can come out 3 dB down too.
_ONE_CHANNEL_UP = "rematrix_volume=1.41421356"

# what mpv calls whichever way out the machine is using
_SYSTEM_DEVICE = "auto"

# How long the list of those lasts: long enough for a whole grid opening to share one
_AUDIO_DEVICES_KEPT_S = 5

# Told by what the filter says as it starts, for the whole run: what stops it stops it
# for every video, the file or a libmpv made without the filter
_ROOM_FILTER_BROKE = threading.Event()
_ROOM_FILTER_FAILURES = re.compile(r"Parsed_sofalizer|filter 'sofalizer'")


@cache
def _room_file() -> str | None:
    """VLC's file for Headphones, spelled for a filter. None to play the plain mix."""

    libvlc = find_libvlc()

    if libvlc is None:
        return None

    path = (Path(libvlc).parent / _ROOM_FILE).resolve()

    if not path.is_file() or not _ROOM_FILE_CHARS.fullmatch(path.as_posix()):
        return None

    return path.as_posix().replace(":", "\\\\:")


def audio_chain(mode: AudioChannelMode, track_channels: int) -> dict:
    """The options that make a channel mode out of a track with this many channels."""

    audio_filter = ""

    if mode in _CHANNEL_PANS:
        audio_filter = _FROM_STEREO.format(_CHANNEL_PANS[mode])

    elif mode == AudioChannelMode.HEADPHONES and track_channels > 2:
        room_file = None if _ROOM_FILTER_BROKE.is_set() else _room_file()

        if room_file is not None:
            audio_filter = _ROOM_FILTER.format(room_file)

    is_one_channel = track_channels == 1
    is_left_to_mpv = mode == AudioChannelMode.UNSET and not is_one_channel

    return {
        "audio-swresample-o": _ONE_CHANNEL_UP if is_one_channel else "",
        "af": audio_filter,
        "audio-channels": "auto-safe" if is_left_to_mpv else "stereo",
    }


class _AudioDevices:
    """The ways out of the machine, read by an mpv that does nothing else.

    One that has read the list stays connected to the sound server for as long as it
    lives. That's a client more for each video, and PulseAudio takes 64: at 32 cells the
    rest fell silent, and nothing else on the machine could connect either.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._read_at = None
        self._devices: tuple[AudioDevice, ...] = ()

    def read(self, mpv_module) -> tuple[AudioDevice, ...]:
        with self._lock:
            now = time.monotonic()

            if self._read_at is None or now - self._read_at > _AUDIO_DEVICES_KEPT_S:
                self._devices = self._read_from_mpv(mpv_module)
                self._read_at = now

            return self._devices

    @staticmethod
    def _read_from_mpv(mpv_module) -> tuple[AudioDevice, ...]:
        try:
            reader = mpv_module.MPV(
                vo="null", ao="null", load_scripts=False, ytdl=False
            )
        # what a libmpv that won't take what it's asked can raise
        except Exception:
            _log.exception("Could not read the audio devices")
            return ()

        try:
            return devices_of_first_output(
                reader.audio_device_list or [],
                _LINUX_AUDIO_OUTPUTS if env.IS_LINUX else None,
            )
        finally:
            reader.terminate()


_AUDIO_DEVICES = _AudioDevices()


def calc_fit_size(
    size: tuple[int, int], box: tuple[int, int] | None
) -> tuple[int, int]:
    """A picture this size fitted into a box, no bigger than it is."""

    width, height = size

    if box is None or not all(box):
        return width, height

    scale = min(1.0, box[0] / width, box[1] / height)

    return max(round(width * scale), 2), max(round(height * scale), 2)


class MpvPlayer(QObject):
    media_loaded = pyqtSignal(Media)
    playback_restarted = pyqtSignal()
    time_changed = pyqtSignal(MILLISECONDS)
    paused_changed = pyqtSignal(bool)
    video_size_changed = pyqtSignal(int, int, object)
    failed = pyqtSignal(str, tuple)
    tracks_changed = pyqtSignal(Media)

    render_context_ready = pyqtSignal()
    terminated = pyqtSignal(object)

    def __init__(
        self,
        mpv_module,
        media_input: MediaInput,
        hwdec,
        wake_renderer,
        skip_frames: bool = False,
    ):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)

        self._mpv_module = mpv_module
        self.media_input = media_input
        self._hwdec = hwdec
        self._skip_frames = skip_frames
        self._wake_renderer = wake_renderer

        # GUI thread. python-mpv sends async commands through a handle that
        # shutdown destroys: one sent after terminate() is a use-after-free in
        # libmpv, not an error. See command().
        self._is_closing = False

        # the picture's size as mpv draws it, turned as the file says
        self._dims: tuple[int, int] | None = None
        # the box a frame fits into until the view says better, and then that
        self._box: tuple[int, int] | None = None
        self._render_size: tuple[int, int] | None = None
        # the size wanted over all of those for now, see hold_render_size
        self._held_size: tuple[int, int] | None = None

        self.is_paused = media_input.video.is_paused
        # what it was last told, which it says it is only a moment later
        self.is_pause_asked = media_input.video.is_paused
        self._last_time_sent = None

        self._is_media_read = False
        self._media: Media | None = None
        self._audio_devices: tuple[AudioDevice, ...] = ()
        self.has_restarted = False
        self._channel_mode = media_input.video.audio_channel_mode
        # of the track being heard, 0 for none or not saying
        self._heard_channels = 0
        self._audio_chain = audio_chain(AudioChannelMode.UNSET, 0)
        self._log_lines = collections.deque(maxlen=_LOG_LINES_KEPT)

        self.mpv = mpv_module.MPV(
            log_handler=self._on_log,
            loglevel="warn",
            **self._options(),
        )

        self.mpv.register_event_callback(self._on_event)
        self.mpv.observe_property("video-params", self._on_video_params)
        self.mpv.observe_property("time-pos", self._on_time)
        self.mpv.observe_property("pause", self._on_pause)
        self.mpv.observe_property("hwdec-current", self._on_hwdec)

        if env.MPV_VERSION is None:
            self.mpv.observe_property("mpv-version", self._on_version)

        self._hook_add("on_preloaded")

    def _options(self) -> dict:
        media_input = self.media_input

        options = {
            "vo": "libmpv",
            # d3d11va has no OpenGL interop on desktop GL: asking for it gives
            # silent CPU decoding. "auto" lands on nvdec on NVIDIA.
            "hwdec": self._hwdec,
            # The default of 6 costs 130 MB VRAM per 1080p 10-bit video. If the
            # pool does run out mpv falls back to a -copy mode by itself:
            # hwdec-current says so, see _on_hwdec. Anything holding more
            # frames, deinterlacing first of all, needs this tested again.
            "hwdec_extra_frames": 0,
            # Software decoding only. The default is a thread per core, and
            # each holds frames: 110 MB more RAM per 1080p video, 290 at 4K,
            # for no fewer dropped frames in anything measured.
            "vd_lavc_threads": 4,
            "vd_lavc_skipframe": _SKIP_FRAMES[self._skip_frames],
            # see VideoRenderer._render
            "video_timing_offset": 0,
            # The picture fills the frame, the surface places it
            "keepaspect": False,
            "profile": "fast",
            "loop_file": "inf",
            "keep_open": "always",
            "mute": True,
            "osd_level": 0,
            "demuxer_max_bytes": "32MiB",
            "demuxer_max_back_bytes": "16MiB",
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            # links are the app's to resolve, and files beside a video are
            # only offered once asked for
            "ytdl": False,
            "audio_file_auto": "no",
            "sub_auto": "no",
            "cover_art_auto": "no",
            "load_scripts": False,
            "pause": media_input.video.is_paused,
        }

        if env.IS_LINUX:
            # On a machine with no sound to be had, mpv otherwise tries every
            # output it knows: JACK and SDL don't take being started by several
            # videos at once, which hangs or crashes. Without a sound device
            # the video just plays on.
            options["ao"] = ",".join(_LINUX_AUDIO_OUTPUTS)
            options["audio_fallback_to_null"] = True

        if media_input.is_audio_only:
            options["vid"] = "no"

        video = media_input.video

        # as it starts, rather than starting the sound over once it has. The channel
        # mode goes by the track: see _pick_tracks
        options["audio_delay"] = video.audio_delay_ms / 1000

        if video.transform in _TURNS:
            options["video_rotate"] = _TURNS[video.transform]

        # a random start is only known with the length: see _pick_random_start
        if video.current_position and not media_input.is_live:
            options["start"] = str(video.current_position / 1000)

        return options

    def _hook_add(self, name: str) -> None:
        # python-mpv doesn't have these. Hooks are the client's that added them,
        # and its events are on this handle.
        self._mpv_module.backend.mpv_hook_add(
            self.mpv._event_handle, c_ulonglong(0), name.encode(), 0
        )

    def _hook_continue(self, hook_id: int) -> None:
        self._mpv_module.backend.mpv_hook_continue(
            self.mpv._event_handle, c_ulonglong(hook_id)
        )

    # Render thread --------------------------------------------------------

    def render_size(self) -> tuple[int, int] | None:
        """The size of the next frame, None while the picture's isn't known."""

        if self._dims is None:
            return None

        return (
            self._held_size or self._render_size or calc_fit_size(self._dims, self._box)
        )

    def on_render_context_ready(self) -> None:
        # not from here: this thread never waits on the core
        self.render_context_ready.emit()

    def on_render_context_gone(self) -> None:
        """The last of the render side, so mpv can go. It can take a moment."""

        self._is_closing = True

        threading.Thread(
            target=self._terminate, name="mpv terminate", daemon=True
        ).start()

    def _terminate(self) -> None:
        self.mpv.terminate()

        self._log.debug("mpv terminated")

        self.terminated.emit(self)

    # GUI thread -----------------------------------------------------------

    def start(self, box: tuple[int, int]) -> None:
        self._box = box

        audio_file = self.media_input.selected_audio_slave

        if audio_file is not None:
            self.command("change-list", "audio-files", "append", audio_file)

        self.command("loadfile", self.media_input.uri)

    def close(self) -> None:
        self._is_closing = True

    def command(self, *args, **kwargs) -> None:
        if self._is_closing:
            return

        self.mpv.command_async(*args, **kwargs)

    def set_option(self, name: str, value) -> None:
        self.command("set", name, value)

    def set_pause(self, is_paused: bool) -> None:
        self.is_pause_asked = is_paused

        self.set_option("pause", "yes" if is_paused else "no")

    def select_track(self, option: str, track_id: int) -> None:
        if option == "aid":
            self._heard_channels = _track_channels(self._media.audio_tracks, track_id)

            self._apply_audio_chain()

        self.set_option(option, _track_option(track_id))

    def add_audio_file(self, uri: str) -> None:
        # selected once it's known how many channels it has: see _on_audio_file_added
        self.command("audio-add", uri, "auto", callback=self._on_audio_file_added)

    def set_audio_device(self, device: AudioDevice | None) -> None:
        if device is None:
            self.set_option("audio-device", _SYSTEM_DEVICE)
            return

        device_id = self._audio_device_id(device)

        if device_id is not None:
            self.set_option("audio-device", device_id)

    def set_channel_mode(self, mode: AudioChannelMode) -> None:
        self._channel_mode = mode

        self._apply_audio_chain()

    def _apply_audio_chain(self) -> None:
        for option, value in self._audio_chain_changes():
            self.set_option(option, value)

    def _audio_chain_changes(self) -> list[tuple[str, str]]:
        """Only what changed: it's asked on every load, and telling mpv starts the
        sound over."""

        chain = audio_chain(self._channel_mode, self._heard_channels)
        changes = [
            (option, value)
            for option, value in chain.items()
            if value != self._audio_chain[option]
        ]

        self._audio_chain = chain

        return changes

    def set_skip_frames(self, is_skipping: bool) -> None:
        self.set_option("vd-lavc-skipframe", _SKIP_FRAMES[is_skipping])

    def set_render_size(self, size: tuple[int, int]) -> None:
        if size != self._render_size:
            self._render_size = size
            self._wake_renderer()

    def hold_render_size(self, size: tuple[int, int] | None) -> None:
        """Render at this size whatever the view says, until told None."""

        self._held_size = size
        self._wake_renderer()

    # Event thread ---------------------------------------------------------

    def _on_log(self, level: str, component: str, message: str) -> None:
        line = f"{component}: {message.strip()}"

        if level in {"fatal", "error"}:
            self._log_lines.append(line)
            self._log.warning(line)

            # one that won't start leaves no sound at all
            if _ROOM_FILTER_FAILURES.search(message):
                _ROOM_FILTER_BROKE.set()
                self._apply_audio_chain()
        else:
            # hwdec=auto tries everything the machine might have, out loud
            self._log.debug(line)

    def _on_event(self, event) -> None:
        event_id = event.event_id.value
        ids = self._mpv_module.MpvEventID

        # mpv waits on this one, closing or not
        if event_id == ids.HOOK:
            self._on_preloaded(event.data.id)
            return

        if self._is_closing:
            return

        if event_id == ids.FILE_LOADED:
            self._read_media()
        elif event_id == ids.PLAYBACK_RESTART:
            self.has_restarted = True
            self._wake_renderer()
            self.playback_restarted.emit()
        elif event_id == ids.END_FILE:
            self._on_end_file(event.data)

    def _on_preloaded(self, hook_id: int) -> None:
        """The tracks and the length are known now, and nothing has started.

        At file-loaded it's too late. The video's first frame is on its way by then,
        to be shown as loaded before a random start lands, and being told a device
        while the sound starts up leaves mpv never saying it's playing.
        """

        try:
            if not self._is_closing:
                self._pick_random_start()
                self._pick_tracks()
                self._pick_audio_device()
        except self._mpv_module.ShutdownError:
            pass
        finally:
            self._hook_continue(hook_id)

    def _pick_random_start(self) -> None:
        media_input = self.media_input
        video = media_input.video

        if not video.is_start_random or video.current_position or media_input.is_live:
            return

        duration = self.mpv.duration

        # none and it counts as live, which has no random start: see _read_media
        if duration:
            media_input.length = int(duration * 1000)

            self.mpv.start = str(media_input.initial_time / 1000)

    def _pick_tracks(self) -> None:
        """Only what's asked for: left alone, mpv takes the track the file marks."""

        tracks = self._read_tracks()
        video_id = self._wanted_video_track_id(tracks)
        audio_id = self._wanted_audio_track_id(tracks)

        # with no picture either, mpv would have nothing to play and end the file
        if audio_id == DISABLED_TRACK and (
            video_id == DISABLED_TRACK
            or not tracks.video_tracks
            or self.media_input.is_audio_only
        ):
            audio_id = None

        picks = {"vid": video_id, "aid": audio_id}

        # no subtitles in it is the ordinary case, with nothing to switch off
        if tracks.subtitle_tracks:
            picks["sid"] = wanted_subtitle_track_id(
                self.media_input.video,
                tracks.subtitle_tracks,
                tracks.external_subtitle_ids,
            )

        heard_id = tracks.default_audio_track_id if audio_id is None else audio_id

        self._heard_channels = _track_channels(tracks.audio_tracks, heard_id)

        options = self._audio_chain_changes() + [
            (option, _track_option(track_id))
            for option, track_id in picks.items()
            if track_id is not None
        ]

        for option, value in options:
            self.mpv.command("set", option, value)

    def _pick_audio_device(self) -> None:
        self._audio_devices = _AUDIO_DEVICES.read(self._mpv_module)

        wanted = self.media_input.video.audio_device
        device_id = None if wanted is None else self._audio_device_id(wanted)

        if device_id is not None:
            self.mpv.audio_device = device_id

    def _on_end_file(self, data) -> None:
        if data.reason != self._mpv_module.MpvEventEndFile.ERROR:
            return

        self._log.error(f"mpv ended the file with error {data.error}")

        self.failed.emit(
            translate("Video Error", "Player error"), tuple(self._log_lines)
        )

    def _on_video_params(self, _name, params) -> None:
        if not params or not params.get("dw") or not params.get("dh"):
            return

        # dw and dh leave the rotation out
        width, height = params["dw"], params["dh"]
        if params.get("rotate", 0) % 180 == 90:
            width, height = height, width

        self._dims = (width, height)

        self._wake_renderer()

        self.video_size_changed.emit(
            params.get("w", 0), params.get("h", 0), _params_sar(params)
        )

    def _on_time(self, _name, seconds) -> None:
        if seconds is None or not self._is_media_read:
            return

        # A frame's start can be up to half a millisecond off its true one, in
        # whichever direction, and the time has to be in the frame: the frame
        # is worked out from it, see VideoBlock.step_frame.
        new_time = round(seconds * 1000) + 1

        last_time = self._last_time_sent

        if (
            last_time is not None
            and 0 <= new_time - last_time < TIME_REPORT_MS
            # paused, a frame step has only the one report to make
            and not self.is_paused
        ):
            return

        self._last_time_sent = new_time

        self.time_changed.emit(new_time)

    def _on_pause(self, _name, is_paused) -> None:
        if is_paused is None:
            return

        self.is_paused = bool(is_paused)

        self.paused_changed.emit(self.is_paused)

    def _on_hwdec(self, _name, value) -> None:
        if value is not None:
            self._log.info(f"Decoding with: {value}")

    def _on_version(self, _name, value) -> None:
        if value:
            env.MPV_VERSION = value.removeprefix("mpv ")

    def _read_media(self) -> None:
        try:
            media = self._media_from_tracks()
        except self._mpv_module.ShutdownError:
            return

        # no length to go by, here as in VLC: a random start has none to pick from
        if media.length == -1:
            self.media_input.is_live = True

        self.media_input.length = media.length

        self._is_media_read = True
        self._media = media

        self.media_loaded.emit(media)

    def _on_audio_file_added(self, error, _result) -> None:
        if self._is_closing or self._media is None:
            return

        # the video plays on as it was, and nothing else has changed
        if error is not None:
            self._log.warning(f"Failed to add the audio file: {error}")
            return

        try:
            tracks = self._read_tracks()
        except self._mpv_module.ShutdownError:
            return

        wanted = self._wanted_audio_track_id(tracks)

        self._media = dataclasses.replace(
            self._media,
            audio_tracks=tracks.audio_tracks,
            cur_audio_track_id=tracks.cur_audio_track_id if wanted is None else wanted,
            external_audio_ids=tracks.external_audio_ids,
        )

        if wanted is not None:
            self.select_track("aid", wanted)

        self.tracks_changed.emit(self._media)

    def _read_tracks(self) -> Media:
        """All of what mpv lists. The length and the devices aren't read here."""

        tracks = {kind: {} for kind in _TRACK_READERS}
        selected = {}
        external = defaultdict(list)
        # the first of those it's told to open on and the first of the others
        own_audio = {}
        default_subtitle = None

        for track in self.mpv.track_list or []:
            kind = track.get("type")
            track_id = track.get("id")

            # the picture in a song is no video, here as in VLC
            if kind not in tracks or track.get("albumart"):
                continue

            tracks[kind][track_id] = _TRACK_READERS[kind](track)

            if track.get("selected"):
                selected[kind] = track_id

            if track.get("external"):
                external[kind].append(track_id)
            elif kind == "audio":
                own_audio.setdefault(bool(track.get("default")), track_id)

            if kind == "sub" and default_subtitle is None:
                if track.get("default") or track.get("forced"):
                    default_subtitle = track_id

        def current(kind):
            return _cur_track_id(selected.get(kind), tracks[kind])

        return Media(
            length=-1,
            video_tracks=tracks["video"],
            audio_tracks=tracks["audio"],
            cur_video_track_id=current("video"),
            cur_audio_track_id=current("audio"),
            external_audio_ids=tuple(external["audio"]),
            default_audio_track_id=own_audio.get(True, own_audio.get(False)),
            subtitle_tracks=tracks["sub"],
            cur_subtitle_track_id=current("sub"),
            external_subtitle_ids=tuple(external["sub"]),
            default_subtitle_track_id=default_subtitle,
        )

    def _media_from_tracks(self) -> Media:
        media = self._read_tracks()
        duration = self.mpv.duration

        if duration and not self.media_input.is_live:
            media.length = int(duration * 1000)

        media.audio_devices = self._audio_devices

        # told to leave the picture out, here as in VLC, and none will come
        if self.media_input.is_audio_only:
            media.video_tracks = {}
            media.cur_video_track_id = None

        return media

    def _wanted_video_track_id(self, tracks: Media) -> int | None:
        # it's off from the start, see _options
        if self.media_input.is_audio_only:
            return None

        wanted = self.media_input.video.video_track_id

        if wanted == DISABLED_TRACK:
            # with no sound either, nothing would be left to play
            return DISABLED_TRACK if tracks.audio_tracks else None

        # an id from another driver, or a file changed since
        return wanted if wanted in tracks.video_tracks else None

    def _wanted_audio_track_id(self, tracks: Media) -> int | None:
        return wanted_audio_track_id(
            self.media_input.video, tracks.audio_tracks, tracks.external_audio_ids
        )

    def _audio_device_id(self, device: AudioDevice) -> str | None:
        device_id = resolve_device_id(device, self._audio_devices)

        if device_id is None:
            self._log.warning(
                f"Audio device {device.name or device.id} is not here,"
                " leaving the sound where the machine puts it"
            )

        return device_id


def devices_of_first_output(listed, outputs=None) -> tuple[AudioDevice, ...]:
    """The ways out of the machine of the first output that has any, in the order
    these are tried. mpv lists every output it has, and which it will use is only
    known once the sound has started: too late to have the list with the media.

    An entry that names no device is left out, standing for whichever way out the
    machine is using, as with VLC.
    """

    by_output = {}

    for device in listed:
        output, _, name = device["name"].partition("/")

        if name:
            by_output.setdefault(output, []).append(
                AudioDevice(id=device["name"], name=device.get("description") or "")
            )

    if outputs is None:
        outputs = by_output

    return next(
        (tuple(by_output[output]) for output in outputs if output in by_output), ()
    )


def _track_option(track_id: int) -> str:
    return "no" if track_id == DISABLED_TRACK else str(track_id)


def _track_channels(tracks: dict, track_id: int | None) -> int:
    track = tracks.get(track_id)

    return track.channels if track is not None else 0


def _cur_track_id(selected: int | None, tracks: dict) -> int | None:
    """None where there's nothing of the kind, as opposed to it being switched off."""

    if selected is None and tracks:
        return DISABLED_TRACK

    return selected


def _params_sar(params: dict) -> tuple[int, int] | None:
    """How wide the pixels are for their height, as a fraction of the sizes."""

    stored_w, stored_h = params.get("w"), params.get("h")
    shown_w, shown_h = params.get("dw"), params.get("dh")

    if not (stored_w and stored_h and shown_w and shown_h):
        return None

    sar = Fraction(shown_w * stored_h, shown_h * stored_w)

    return sar.numerator, sar.denominator


def _track_sar(track: dict) -> tuple[int, int] | None:
    par = track.get("demux-par")

    if not par:
        return None

    sar = Fraction(par).limit_denominator(1000)

    return sar.numerator, sar.denominator


def _video_track(track: dict) -> VideoTrack:
    return VideoTrack(
        video_dimensions=(track.get("demux-w") or 0, track.get("demux-h") or 0),
        fps=track.get("demux-fps"),
        orientation=_ROTATIONS.get(track.get("demux-rotation"), VideoTransform.NONE),
        sar=_track_sar(track),
        bitrate=track.get("demux-bitrate") or 0,
        language=track.get("lang"),
        description=track.get("title"),
        codec=track.get("codec") or "",
    )


def _audio_track(track: dict) -> AudioTrack:
    return AudioTrack(
        channels=track.get("demux-channel-count") or 0,
        rate=track.get("demux-samplerate") or 0,
        bitrate=track.get("demux-bitrate") or 0,
        language=track.get("lang"),
        description=track.get("title"),
        codec=track.get("codec") or "",
    )


def _subtitle_track(track: dict) -> SubtitleTrack:
    return SubtitleTrack(
        bitrate=0,
        language=track.get("lang"),
        description=track.get("title"),
        codec=track.get("codec") or "",
    )


_TRACK_READERS = {
    "video": _video_track,
    "audio": _audio_track,
    "sub": _subtitle_track,
}
