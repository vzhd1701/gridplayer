"""One mpv instance.

Observers and event callbacks run on python-mpv's event thread, where reading
properties may wait: what the GUI needs goes to it by signal, and everything it
does comes through command(), which never waits.
"""

import collections
import logging
import threading
from ctypes import c_ulonglong
from fractions import Fraction

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.params import env
from gridplayer.params.static import VideoTransform
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
        self.has_restarted = False
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

        if self._is_start_random():
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
            options["ao"] = "pipewire,pulse,alsa"
            options["audio_fallback_to_null"] = True

        if media_input.is_audio_only:
            options["vid"] = "no"

        video = media_input.video

        if video.transform in _TURNS:
            options["video_rotate"] = _TURNS[video.transform]

        # a random start is only known with the length: see _on_preloaded
        if video.current_position and not media_input.is_live:
            options["start"] = str(video.current_position / 1000)

        return options

    def _is_start_random(self) -> bool:
        media_input = self.media_input
        video = media_input.video

        return (
            video.is_start_random
            and not video.current_position
            and not media_input.is_live
        )

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

        self.command("loadfile", self.media_input.uri)

    def close(self) -> None:
        self._is_closing = True

    def command(self, *args) -> None:
        if self._is_closing:
            return

        self.mpv.command_async(*args)

    def set_option(self, name: str, value) -> None:
        self.command("set", name, value)

    def set_pause(self, is_paused: bool) -> None:
        self.is_pause_asked = is_paused

        self.set_option("pause", "yes" if is_paused else "no")

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
        """A random start: the length is known now, and nothing is decoded yet.

        At file-loaded it's too late, the video's first frame being on its way by
        then, to be shown as loaded before the seek lands.
        """

        try:
            duration = None if self._is_closing else self.mpv.duration

            # none and it counts as live, which has no random start: see _read_media
            if duration:
                self.media_input.length = int(duration * 1000)

                self.mpv.start = str(self.media_input.initial_time / 1000)
        finally:
            self._hook_continue(hook_id)

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

        self.media_loaded.emit(media)

    def _media_from_tracks(self) -> Media:
        tracks = self.mpv.track_list or []
        duration = self.mpv.duration

        video_tracks = {}
        audio_tracks = {}
        subtitle_tracks = {}
        selected = {"video": None, "audio": None, "sub": None}
        default_audio = None
        default_subtitle = None
        external_audio = []
        external_subtitle = []

        for track in tracks:
            kind = track.get("type")
            track_id = track.get("id")

            # the picture in a song is no video, here as in VLC
            if track.get("albumart"):
                continue

            if track.get("selected"):
                selected[kind] = track_id

            if kind == "video":
                video_tracks[track_id] = _video_track(track)

            elif kind == "audio":
                audio_tracks[track_id] = _audio_track(track)

                if track.get("external"):
                    external_audio.append(track_id)
                if track.get("default") and default_audio is None:
                    default_audio = track_id

            elif kind == "sub":
                subtitle_tracks[track_id] = _subtitle_track(track)

                if track.get("external"):
                    external_subtitle.append(track_id)
                if (track.get("default") or track.get("forced")) and (
                    default_subtitle is None
                ):
                    default_subtitle = track_id

        video = self.media_input.video

        # told to leave the picture out, here as in VLC, and none will come
        if self.media_input.is_audio_only:
            video_tracks = {}

        audio_id = wanted_audio_track_id(video, audio_tracks)
        subtitle_id = wanted_subtitle_track_id(
            video, subtitle_tracks, tuple(external_subtitle)
        )

        if audio_id is None:
            audio_id = selected["audio"]

        if subtitle_id is None:
            subtitle_id = selected["sub"]

        self._select_track("aid", audio_id, selected["audio"])
        self._select_track("sid", subtitle_id, selected["sub"])

        length = (
            int(duration * 1000) if duration and not self.media_input.is_live else -1
        )

        return Media(
            length=length,
            video_tracks=video_tracks,
            audio_tracks=audio_tracks,
            cur_video_track_id=selected["video"],
            cur_audio_track_id=audio_id,
            external_audio_ids=tuple(external_audio),
            default_audio_track_id=default_audio or selected["audio"],
            subtitle_tracks=subtitle_tracks,
            cur_subtitle_track_id=subtitle_id,
            external_subtitle_ids=tuple(external_subtitle),
            default_subtitle_track_id=default_subtitle,
        )

    def _select_track(self, option: str, wanted, current) -> None:
        if wanted == current:
            return

        value = "no" if wanted in {None, DISABLED_TRACK} else str(wanted)

        self.command("set", option, value)


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
