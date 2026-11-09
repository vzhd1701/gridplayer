"""A video played by libmpv, driven over the same commands as a VLC player.

Everything libmpv tells us arrives on its event thread, and is either passed
straight on (the time, the pause) or sent to this player's own command thread
to be dealt with there, so that only one thread ever drives the player.
"""

import dataclasses
import logging
import tempfile
from collections import deque
from fractions import Fraction
from pathlib import Path
from threading import Timer
from time import monotonic

from gridplayer.models.audio_device import AudioDevice, resolve_device_id
from gridplayer.models.audio_selection import AudioExternal, track_of_file
from gridplayer.models.chapter import Chapter
from gridplayer.models.subtitle_selection import SubtitleExternal
from gridplayer.models.subtitle_selection import track_of_file as subtitle_track_of_file
from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.params import env
from gridplayer.params.static import (
    AudioChannelMode,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoTransform,
    ViewParams,
)
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import (
    calc_ratio_crop,
    calc_shown_pixel_aspect,
    calc_view_placement,
)
from gridplayer.utils.network import vlc_user_agent
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

# mpv reports the time every frame; the player has no use for more than this
TIME_REPORT_INTERVAL_S = 0.05

KEPT_ERROR_LINES = 20

NO_CROP = "0x0+0+0"

TRACK_NONE = "no"

# the rotation the file asks for, in degrees clockwise, as the player's own
ORIENTATIONS = {
    90: VideoTransform.ROTATE_90,
    180: VideoTransform.ROTATE_180,
    270: VideoTransform.ROTATE_270,
}

TRANSFORM_ROTATIONS = {
    VideoTransform.ROTATE_90: 90,
    VideoTransform.ROTATE_180: 180,
    VideoTransform.ROTATE_270: 270,
}

TRANSFORM_FILTERS = {
    VideoTransform.HFLIP: "hflip",
    VideoTransform.VFLIP: "vflip",
    VideoTransform.TRANSPOSE: "lavfi=[transpose=0]",
    VideoTransform.ANTITRANSPOSE: "lavfi=[transpose=3]",
}

# Surround and headphone downmixes have no equivalent here yet.
CHANNEL_MODE_FILTERS = {
    AudioChannelMode.RSTEREO: "lavfi=[pan=stereo|c0=c1|c1=c0]",
    AudioChannelMode.LEFT: "lavfi=[pan=stereo|c0=c0|c1=c0]",
    AudioChannelMode.RIGHT: "lavfi=[pan=stereo|c0=c1|c1=c1]",
    AudioChannelMode.MONO: "lavfi=[pan=mono|c0=0.5*c0+0.5*c1]",
}


def translate(context, text):
    """A dummy to make strings discoverable via pylupdate."""
    return text


def only_initialized_player(func):
    def wrapper(self, *args, **kwargs):
        if self._mpv is not None:
            return func(self, *args, **kwargs)

    return wrapper


def track_sar(par) -> tuple[int, int] | None:
    if not par:
        return None

    aspect = Fraction(par).limit_denominator(10000)

    return aspect.numerator, aspect.denominator


class MpvPlayerThreaded(CommandLoopThreaded):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._mpv = None
        self._is_released = False

        self.media_input: MediaInput | None = None
        self.media: Media | None = None

        self.is_video_initialized = False
        self._is_paused = False
        self._is_file_open = False
        self._is_playback_reported = False

        self._timer_load = None
        self._last_time_report = 0.0

        self._size = (0, 0)
        self._view: ViewParams | None = None
        self._last_crop = None
        self._last_keepaspect = None

        self._error_lines = deque(maxlen=KEPT_ERROR_LINES)

    # --- what a concrete driver has to say

    def _mpv_options(self) -> dict:
        raise NotImplementedError

    # --- setup and teardown

    def start(self):
        self.cmd_loop_start_thread(self.init_player)

    def init_player(self):
        import mpv

        self._mpv = mpv.MPV(
            log_handler=self._on_log,
            loglevel="warn",
            config=False,
            load_scripts=False,
            ytdl=False,
            osc=False,
            osd_level=0,
            idle="yes",
            hwdec="auto-safe",
            hr_seek="yes",
            mute=True,
            pause=True,
            audio_file_auto="no",
            sub_auto="no",
            cursor_autohide="no",
            input_cursor="no",
            input_cursor_passthrough="yes",
            **self._mpv_options(),
        )

        self._mpv.register_event_callback(self._on_mpv_event)

        self._mpv.observe_property("time-pos", self._on_time_pos)
        self._mpv.observe_property("pause", self._on_pause)
        self._mpv.observe_property("track-list", self._on_track_list)
        self._mpv.observe_property("chapter-list", self._on_chapter_list)
        self._mpv.observe_property("video-params", self._on_video_params)

    def cmd_process_command(self, command_args, command_name):
        if self._is_released:
            return

        super().cmd_process_command(command_args, command_name)

    def cleanup(self):
        self.is_video_initialized = False
        self._is_released = True

        self._cancel_load_timer()

        if self._mpv is not None:
            player = self._mpv
            self._mpv = None

            player.terminate()

            self._log.debug("Player released")

    def error(self, message):
        self._log.error(message)

        self._cancel_load_timer()

        self.cmd_send("error_state", message, tuple(self._error_lines))

    # --- what mpv tells us, on its event thread

    def _on_log(self, level, prefix, text):
        line = f"{prefix}: {text.strip()}"

        if level in {"fatal", "error"}:
            self._error_lines.append(line)
            self._log.warning(line)
        else:
            self._log.debug(line)

    def _send_from_event(self, command_name, *args):
        if not self._is_released:
            self.cmd_send_self(command_name, *args)

    def _on_mpv_event(self, event):
        import mpv

        event_id = event.event_id.value

        if event_id == mpv.MpvEventID.FILE_LOADED:
            self._send_from_event("on_file_loaded")

        elif event_id == mpv.MpvEventID.PLAYBACK_RESTART:
            self._send_from_event("on_playback_restart")

        elif event_id == mpv.MpvEventID.END_FILE:
            self._send_from_event("on_end_file", event.data.reason)

    def _on_time_pos(self, _name, value):
        if value is None or not self.is_video_initialized:
            return

        now = monotonic()

        if now - self._last_time_report < TIME_REPORT_INTERVAL_S:
            return

        self._last_time_report = now

        self.cmd_send("time_changed_emit", int(value * 1000))

    def _on_pause(self, _name, value):
        if value is None:
            return

        self._send_from_event("on_pause_changed", bool(value))

    def _on_track_list(self, _name, value):
        if value is not None:
            self._send_from_event("on_tracks_listed")

    def _on_chapter_list(self, _name, value):
        if value is not None:
            self._send_from_event("on_chapters_listed")

    def _on_video_params(self, _name, value):
        if value:
            self._send_from_event("on_video_params", value.get("w"), value.get("h"))

    # --- the same, on the command thread

    def on_file_loaded(self):
        self._is_file_open = True

        self._attach_external_files()

        self.media = self._read_media()

        if self.media.length == -1 and not self.media_input.is_live:
            self._log.debug("Media length is not known, probably live stream")
            self.media_input.is_live = True
            self._set("loop-file", "no")

        self.media_input.length = self.media.length

        self._apply_wanted_tracks()
        self._apply_wanted_audio_device()

        self._view = self.media_input.view
        self._size = self.media_input.size
        self._apply_view()

        if self._is_seek_after_load:
            self._seek_ms(self.media_input.initial_time)

    def on_playback_restart(self):
        if self.media is None:
            return

        if not self.is_video_initialized:
            self._finish_load()

        if not self._is_playback_reported:
            self._is_playback_reported = True
            self.cmd_send("playback_started_emit")

    def _finish_load(self):
        self._log.debug("Load finished")

        self._cancel_load_timer()

        self.media = self._read_media()

        self.is_video_initialized = True

        self.cmd_send("load_video_done", self.media)
        self.cmd_send("playback_status_changed_emit", self._is_paused)
        self.cmd_send("time_changed_emit", self.media_input.initial_time)

    def on_end_file(self, reason):
        import mpv

        was_open = self._is_file_open
        self._is_file_open = False

        if reason == mpv.MpvEventEndFile.ERROR:
            self.error(
                translate("Video Error", "Player error")
                if self.is_video_initialized
                else translate("Video Error", "Failed to load media")
            )

        elif reason == mpv.MpvEventEndFile.EOF and was_open:
            if self.media_input is not None and self.media_input.is_live:
                self.error(translate("Video Error", "Live stream ended"))
            elif not self.is_video_initialized:
                self.error(
                    translate("Video Error", "Video stopped before initialization")
                )

    def on_load_timeout(self):
        if not self.is_video_initialized:
            self.error(translate("Video Error", "Buffering timeout"))

    def on_pause_changed(self, is_paused):
        if is_paused == self._is_paused:
            return

        self._is_paused = is_paused

        if self.is_video_initialized:
            self.cmd_send("playback_status_changed_emit", is_paused)

    def on_tracks_listed(self):
        if not self.is_video_initialized or self.media is None or self._mpv is None:
            return

        media = self._read_media()

        is_same_list = (
            set(media.video_tracks) == set(self.media.video_tracks)
            and set(media.audio_tracks) == set(self.media.audio_tracks)
            and set(media.subtitle_tracks) == set(self.media.subtitle_tracks)
        )

        if is_same_list:
            return

        self.media = media

        self.cmd_send("tracks_changed_emit", self.media)

    def on_chapters_listed(self):
        if not self.is_video_initialized or self.media is None or self._mpv is None:
            return

        chapters = self._read_chapters()

        if chapters == self.media.chapters:
            return

        self.media = dataclasses.replace(self.media, chapters=chapters)

        self.cmd_send("chapters_changed_emit", chapters)

    def on_video_params(self, width, height):
        """The picture's size, which a stream only says once it is decoded."""

        track = self._shown_video_track()

        if track is None or all(track.video_dimensions) or not (width and height):
            return

        track.video_dimensions = (width, height)

        self._apply_view()

        if self.is_video_initialized:
            self.cmd_send("set_video_dimensions", width, height, track.sar)

    # --- loading

    @property
    def _is_seek_after_load(self) -> bool:
        """A random start needs the length, only known once the file is open."""

        video = self.media_input.video

        return (
            not self.media_input.is_live
            and video.is_start_random
            and video.current_position == 0
        )

    @only_initialized_player
    def load_video(self, media_input: MediaInput):
        self.media_input = media_input
        self.media = None
        self.is_video_initialized = False
        self._is_file_open = False
        self._is_playback_reported = False
        self._last_crop = None
        self._last_keepaspect = None
        self._error_lines.clear()

        self._log.info(f"Loading {media_input.uri}")

        self.cmd_send(
            "update_status_emit", translate("Video Status", "Preparing video output"), 0
        )

        self._is_paused = media_input.video.is_paused

        self._set("pause", self._is_paused)
        self._set("loop-file", "no" if media_input.is_live else "inf")
        self._set("vid", TRACK_NONE if media_input.is_audio_only else "auto")
        self._set("sub-codepage", media_input.video.subtitle_encoding or "auto")

        self._apply_http_options(media_input.http_headers)
        self._apply_transform(media_input.video.transform)
        self._apply_deinterlace(media_input.video.deinterlace)

        if media_input.is_live or self._is_seek_after_load:
            self._set("start", "none")
        else:
            self._set("start", f"{media_input.initial_time / 1000:.3f}")

        self._cancel_load_timer()
        self._timer_load = Timer(
            Settings().sync_get("player/video_init_timeout"),
            self.cmd_send_self,
            args=("on_load_timeout",),
        )
        self._timer_load.daemon = True
        self._timer_load.start()

        self._mpv.loadfile(media_input.uri)

    def _cancel_load_timer(self):
        if self._timer_load is not None:
            self._timer_load.cancel()
            self._timer_load = None

    def _apply_http_options(self, headers: dict[str, str]):
        lowered = {name.lower(): value for name, value in headers.items()}

        self._set("user-agent", lowered.get("user-agent") or vlc_user_agent())
        self._set("referrer", lowered.get("referer", ""))

    def _apply_transform(self, transform: VideoTransform | None):
        self._set("video-rotate", TRANSFORM_ROTATIONS.get(transform, 0))
        self._set("vf", TRANSFORM_FILTERS.get(transform, ""))

    def _attach_external_files(self):
        if self.media_input.selected_audio_slave:
            self._add_file(self._mpv.audio_add, self.media_input.selected_audio_slave)

        for uri in self.media_input.selected_subtitle_slaves:
            self._add_file(self._mpv.sub_add, uri)

    def _add_file(self, add_func, uri) -> bool:
        try:
            add_func(uri, "auto")
        except Exception:
            self._log.warning(f"Failed to add {uri}", exc_info=True)
            return False

        return True

    # --- reading what mpv has

    def _read_media(self) -> Media:
        tracks = self._get("track-list") or []

        video_tracks, audio_tracks, subtitle_tracks = {}, {}, {}
        current = {"video": None, "audio": None, "sub": None}
        external = {"audio": [], "sub": []}

        for track in tracks:
            kind, track_id = track["type"], track["id"]

            if kind == "video":
                video_tracks[track_id] = self._video_track(track)
            elif kind == "audio":
                audio_tracks[track_id] = self._audio_track(track)
            elif kind == "sub":
                subtitle_tracks[track_id] = self._subtitle_track(track)
            else:
                continue

            if track.get("selected"):
                current[kind] = track_id

            if track.get("external") and kind in external:
                external[kind].append(track_id)

        duration = self._get("duration")

        return Media(
            length=int(duration * 1000) if duration else -1,
            video_tracks=video_tracks,
            audio_tracks=audio_tracks,
            cur_video_track_id=current["video"],
            cur_audio_track_id=current["audio"],
            external_audio_ids=tuple(external["audio"]),
            default_audio_track_id=current["audio"],
            subtitle_tracks=subtitle_tracks,
            cur_subtitle_track_id=current["sub"],
            external_subtitle_ids=tuple(external["sub"]),
            default_subtitle_track_id=current["sub"],
            audio_devices=self._read_audio_devices(),
            chapters=self._read_chapters(),
        )

    @staticmethod
    def _video_track(track: dict) -> VideoTrack:
        return VideoTrack(
            codec=track.get("codec") or "",
            bitrate=int(track.get("demux-bitrate") or 0),
            language=track.get("lang"),
            description=track.get("title"),
            video_dimensions=(track.get("demux-w") or 0, track.get("demux-h") or 0),
            fps=track.get("demux-fps"),
            orientation=ORIENTATIONS.get(
                track.get("demux-rotation") or 0, VideoTransform.NONE
            ),
            sar=track_sar(track.get("demux-par")),
        )

    @staticmethod
    def _audio_track(track: dict) -> AudioTrack:
        return AudioTrack(
            codec=track.get("codec") or "",
            bitrate=int(track.get("demux-bitrate") or 0),
            language=track.get("lang"),
            description=track.get("title"),
            channels=track.get("demux-channel-count") or 0,
            rate=track.get("demux-samplerate") or 0,
        )

    @staticmethod
    def _subtitle_track(track: dict) -> SubtitleTrack:
        return SubtitleTrack(
            codec=track.get("codec") or "",
            bitrate=0,
            language=track.get("lang"),
            description=track.get("title") or track.get("external-filename"),
        )

    def _read_chapters(self) -> tuple[Chapter, ...]:
        chapters = self._get("chapter-list") or []

        return tuple(
            Chapter(start_ms=int(chapter["time"] * 1000), name=chapter.get("title"))
            for chapter in chapters
        )

    def _read_audio_devices(self) -> tuple[AudioDevice, ...]:
        devices = self._get("audio-device-list") or []

        return tuple(
            AudioDevice(id=device["name"], name=device.get("description"))
            for device in devices
            if device["name"] != "auto"
        )

    def _get(self, name):
        try:
            # as attributes: mpv["..."] reaches options only, not properties
            return getattr(self._mpv, name.replace("-", "_"))
        except Exception:
            self._log.debug(f"Failed to read {name}", exc_info=True)
            return None

    def _set(self, name, value) -> bool:
        try:
            setattr(self._mpv, name.replace("-", "_"), value)
        except Exception:
            self._log.warning(f"Failed to set {name}={value!r}", exc_info=True)
            return False

        return True

    def _shown_video_track(self) -> VideoTrack | None:
        if self.media is None:
            return None

        return self.media.video_tracks.get(self.media.cur_video_track_id)

    # --- what the settings ask for

    def _apply_wanted_tracks(self):
        video = self.media_input.video
        media = self.media

        audio_id = wanted_audio_track_id(video, media.audio_tracks)

        if isinstance(video.audio_selection, AudioExternal):
            picked = track_of_file(video.audio_selection, media.external_audio_ids)
            audio_id = audio_id if picked is None else picked

        subtitle_id = wanted_subtitle_track_id(
            video, media.subtitle_tracks, media.external_subtitle_ids
        )

        if isinstance(video.subtitle_selection, SubtitleExternal):
            picked = subtitle_track_of_file(
                video.subtitle_selection, media.external_subtitle_ids
            )
            subtitle_id = subtitle_id if picked is None else picked

        self._select_track("aid", audio_id)

        if media.subtitle_tracks:
            self._select_track("sid", subtitle_id)

    def _select_track(self, prop: str, track_id: int | None):
        if track_id is None:
            return

        self._set(prop, TRACK_NONE if track_id == DISABLED_TRACK else track_id)

    def _apply_wanted_audio_device(self):
        wanted = self.media_input.video.audio_device

        if wanted is None:
            return

        device_id = resolve_device_id(wanted, self.media.audio_devices)

        if device_id is None:
            self._log.warning(f"Audio device {wanted.name or wanted.id} is not here")
            return

        self._set("audio-device", device_id)

    def _apply_deinterlace(self, deinterlace: VideoDeinterlace):
        # mpv picks the deinterlacer that suits the decoder itself, so the
        # modes VLC offers have nothing to map to.
        value = {VideoDeinterlace.ON: "yes", VideoDeinterlace.OFF: "no"}.get(
            deinterlace, "auto"
        )

        self._set("deinterlace", value)

    # --- commands

    def _grab_frame(self) -> Path | None:
        tmp_root = env.FLATPAK_RUNTIME_DIR if env.IS_FLATPAK else None

        file_path = Path(tempfile.mkdtemp(dir=tmp_root)) / "snapshot.png"

        try:
            self._mpv.screenshot_to_file(str(file_path))
        except Exception:
            self._log.warning("Failed to grab frame", exc_info=True)

        if not file_path.is_file():
            file_path.parent.rmdir()
            return None

        return file_path

    @only_initialized_player
    def snapshot(self):
        file_path = self._grab_frame()

        self.cmd_send("snapshot_taken_emit", str(file_path) if file_path else "")

    def screenshot(self):
        file_path = self._grab_frame() if self._mpv is not None else None

        self.cmd_send("screenshot_taken_emit", str(file_path) if file_path else "")

    @only_initialized_player
    def play(self):
        self.set_pause(False)

    @only_initialized_player
    def set_pause(self, is_paused):
        self._log.debug(f"Set pause {is_paused}")

        if is_paused == self._is_paused:
            # nothing will change, and the widget is waiting to hear back
            self.cmd_send("playback_status_changed_emit", is_paused)
            return

        self._set("pause", is_paused)

    @only_initialized_player
    def set_time(self, seek_ms):
        if self.media_input is None or self.media_input.is_live or self.media is None:
            return

        self._seek_ms(seek_ms)

    def _seek_ms(self, seek_ms):
        seek_ms = max(seek_ms, 0)

        if self.media.length > 0:
            seek_ms = min(seek_ms, self.media.length - 1)

        self._mpv.command_async(
            "seek", seek_ms / 1000, "absolute+exact", callback=_ignore_seek_result
        )

    @only_initialized_player
    def set_playback_rate(self, rate):
        if self.media_input is None or not self.media_input.is_live:
            self._set("speed", rate)

    @only_initialized_player
    def audio_set_mute(self, is_muted):
        self._set("mute", bool(is_muted))

    @only_initialized_player
    def audio_set_volume(self, volume_percent: float):
        self._set("volume", volume_percent * 100)

    @only_initialized_player
    def set_audio_track(self, track_id):
        self._select_track("aid", track_id)

    @only_initialized_player
    def set_video_track(self, track_id):
        self._select_track("vid", track_id)

    @only_initialized_player
    def set_subtitle_track(self, track_id):
        self._select_track("sid", track_id)

    @only_initialized_player
    def set_audio_device(self, device: AudioDevice | None):
        self.media_input.video.audio_device = device

        if device is None:
            self._set("audio-device", "auto")
        elif self.media is not None:
            self._apply_wanted_audio_device()

    @only_initialized_player
    def add_audio_slave(self, uri: str):
        if self._add_file(self._mpv.audio_add, uri):
            self.media_input.selected_audio_slave = uri

    @only_initialized_player
    def add_subtitle_slave(self, uri: str):
        if uri in self.media_input.selected_subtitle_slaves:
            return

        if self._add_file(self._mpv.sub_add, uri):
            self.media_input.selected_subtitle_slaves = (
                *self.media_input.selected_subtitle_slaves,
                uri,
            )

    @only_initialized_player
    def set_audio_channel_mode(self, mode: AudioChannelMode):
        self._set("af", CHANNEL_MODE_FILTERS.get(mode, ""))

    @only_initialized_player
    def set_deinterlace(
        self, deinterlace: VideoDeinterlace, mode: VideoDeinterlaceMode
    ):
        self.media_input.video.deinterlace = deinterlace
        self.media_input.video.deinterlace_mode = mode

        self._apply_deinterlace(deinterlace)

    @only_initialized_player
    def set_audio_delay(self, delay_ms: int):
        self._set("audio-delay", delay_ms / 1000)

    @only_initialized_player
    def set_subtitle_delay(self, delay_ms: int):
        self._set("sub-delay", delay_ms / 1000)

    # --- the view

    @only_initialized_player
    def adjust_view(self, size, view: ViewParams):
        self._size = size
        self._view = view

        if self.media_input is not None:
            self.media_input.size = size

        self._apply_view()

    def _apply_view(self):
        """Cut the frame down to what is on show.

        The widget has already put the surface exactly over where that goes,
        so mpv only has to stretch it to fill the surface.
        """

        track = self._shown_video_track()

        if track is None or self._view is None:
            return

        crop, keep_aspect = self._view_crop(track)

        if crop != self._last_crop:
            self._last_crop = crop
            self._set("video-crop", crop)

        if keep_aspect != self._last_keepaspect:
            self._last_keepaspect = keep_aspect
            self._set("keepaspect", keep_aspect)

    def _view_crop(self, track: VideoTrack) -> tuple[str, bool]:
        # one the file turns or flips is drawn whole, see calc_whole_placement
        if track.is_reoriented:
            return NO_CROP, False

        frame_size = track.video_dimensions

        if not all(frame_size):
            return NO_CROP, True

        view = self._view
        transform = self.media_input.video.transform

        pixel_aspect = calc_shown_pixel_aspect(
            frame_size, transform, view.aspect_ratio, track.stored_pixel_aspect
        )

        if view.crop_ratio:
            view = view._replace(
                crop=calc_ratio_crop(
                    frame_size, transform, view.crop_ratio, pixel_aspect
                )
            )

        placement = calc_view_placement(
            frame_size, self._size, view, transform, pixel_aspect=pixel_aspect
        )

        if placement is None:
            return NO_CROP, True

        x, y, width, height = placement.source

        left, top = max(round(x), 0), max(round(y), 0)
        crop_w = max(min(round(x + width), frame_size[0]) - left, 1)
        crop_h = max(min(round(y + height), frame_size[1]) - top, 1)

        if (crop_w, crop_h) == frame_size:
            return NO_CROP, False

        return f"{crop_w}x{crop_h}+{left}+{top}", False


def _ignore_seek_result(_error, _result):
    """A seek that failed left the video where it was, which is all it can do."""
