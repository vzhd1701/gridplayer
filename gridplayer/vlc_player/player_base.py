import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from time import time
from typing import Optional

from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import calc_crop, calc_resize_scale
from gridplayer.utils.misc import is_url
from gridplayer.vlc_player.libvlc import vlc
from gridplayer.vlc_player.player_event_manager import EventManager
from gridplayer.vlc_player.player_event_waiter import (
    EventWaiter,
    async_timer,
    async_wait,
)
from gridplayer.vlc_player.static import MediaInput, MediaTrack, NotPausedError

DEFAULT_FPS = 25
SNAPSHOT_TIMEOUT = 15

MEDIA_EXTRACT_RETRY_TIME = 0.1


def translate(context, text):
    """
    This is just a dummy to make strings discoverable via pylupdate,
    actual translation takes place in Qt app
    """
    return text


def only_initialized_player(func):
    def wrapper(*args, **kwargs):
        self = args[0]  # noqa: WPS117
        if self._media_player is not None:
            return func(*args, **kwargs)

    return wrapper


class VlcPlayerBase(ABC):
    is_preparse_required = False
    is_video_size_required = False

    def __init__(self, vlc_instance, **kwargs):
        super().__init__(**kwargs)

        self.instance = vlc_instance

        self.is_video_initialized = False

        self._is_paused = False

        self._timeout_init_start = None
        self._timeout_init = None

        self._timer_unpause_failsafe = None
        self._timer_extract_media_track = None

        self.media_input: Optional[MediaInput] = None
        self.media_track: Optional[MediaTrack] = None

        self._media_player = None
        self._media = None
        self._media_options = []

        self._event_manager = EventManager()
        self._event_waiter = EventWaiter()

        self.init_event_manager()

        self._log = logging.getLogger(self.__class__.__name__)

    @property
    def init_time_left(self) -> int:
        if not all([self._timeout_init, self._timeout_init_start]):
            return 0

        return max(int(self._timeout_init - (time() - self._timeout_init_start)), 0)

    def init_player(self):
        self._media_player = self.instance.media_player_new()

        self._media_player.audio_set_mute(True)
        self._media_player.video_set_mouse_input(False)
        self._media_player.video_set_key_input(False)

        self._event_manager.attach_to_media_player(self._media_player)

    def init_event_manager(self):
        self._event_waiter.subscribe(self._event_manager)

        callbacks = {
            "playing": self.cb_playing,
            "paused": self.cb_paused,
            "stopped": self.cb_stopped,
            "end_reached": self.cb_end_reached,
            "encountered_error": self.cb_error,
            "time_changed": self.cb_time_changed,
            "media_parsed_changed": self.cb_parse_changed,
            "buffering": self.cb_buffering,
        }

        for event_name, callback in callbacks.items():
            self._event_manager.subscribe(event_name, callback)

    def cb_buffering(self, event):
        buffered_percent = int(event.u.new_cache)
        self.notify_update_status(
            translate("Video Status", "Buffering"), buffered_percent
        )

    def cb_playing(self, event):
        self._log.debug("Media playing")

        if not self.is_video_initialized:
            return

        # some formats have unreliable time_change (rtp)
        # this creates a failsafe to avoid video being paused while playing
        if self.media_track.is_live:
            self._timer_unpause_failsafe = async_timer(5, self.unpause)
            self._event_waiter.async_wait_for(
                event="buffering",
                on_completed=self._timer_unpause_failsafe.start,
                on_timeout=lambda: self.error(
                    translate("Video Error", "Buffering timeout")
                ),
                timeout=self._timeout_init,
            )

    def cb_paused(self, event):
        self._log.debug("Media paused")

        if not self.is_video_initialized:
            if self.media_input.is_live or self._get_duration() in {0, -1}:
                # live video paused = something went wrong
                # video with 0 duration = file is bad
                self.error(
                    translate("Video Error", "Video stopped before initialization")
                )
            return

        if self.media_input.is_live:
            self.error(translate("Video Error", "Live stream ended"))
            return

        if self._media_player.get_time() > self.media_track.length - 1000:
            self._log.debug("Video ended, time to loop")
            self.notify_end_reached()
            return

        self._is_paused = True
        self.notify_playback_status_changed(True)

    def cb_stopped(self, event):
        self._log.debug("Media stopped")

        if not self.is_video_initialized:
            return

        if not self.media_input.is_live:
            # only live videos can stop
            self.error(translate("Video Error", "Video stopped unexpectedly"))
            return

        self._is_paused = True
        self.notify_playback_status_changed(True)

    def cb_end_reached(self, event):
        self._log.debug("Media end reached")

        if not self.is_video_initialized:
            self.error(translate("Video Error", "Video stopped before initialization"))
            return

    def cb_error(self, event):
        self.error(translate("Video Error", "Player error"))

    def cb_parse_changed(self, event):
        self._log.debug("Media parse changed")

        if event.u.new_status == vlc.MediaParsedStatus.skipped:
            self._log.debug("Media parsing skipped")

        elif event.u.new_status == vlc.MediaParsedStatus.done:
            self._init_media_track()

        elif event.u.new_status == vlc.MediaParsedStatus.timeout:
            return self.error(translate("Video Error", "Media parse timeout"))

        else:
            return self.error(translate("Video Error", "Media parse failed"))

        self.loopback_load_video_st2_set_media()

    def cb_time_changed(self, event):
        # Doesn't work anymore since python-vlc-3.0.12117
        new_time = int(event.u.new_time)

        if new_time == 0:
            return

        if not self.is_video_initialized:
            if self.media_input.is_live:
                self.media_input.initial_time = new_time
            return

        if self._is_paused:
            self.unpause()

        self.notify_time_changed(new_time)

    def unpause(self):
        if not self._is_paused:
            return

        if self._timer_unpause_failsafe is not None:
            self._timer_unpause_failsafe.cancel()
            self._timer_unpause_failsafe = None

        self._is_paused = False
        self.notify_playback_status_changed(False)

    def cleanup(self):
        self.is_video_initialized = False

        if self._timer_extract_media_track is not None:
            self._timer_extract_media_track.cancel()

        if self._timer_unpause_failsafe is not None:
            self._timer_unpause_failsafe.cancel()

        self._event_waiter.abort()

        if self._media_player is not None:
            self._log.debug("Releasing player")

            media_player = self._media_player
            self._media_player = None

            media_player.release()

            self._log.debug("Player released")

    def error(self, message):
        self._log.error(message)
        self.notify_error(message)

    @abstractmethod
    def notify_update_status(self, status, percent=0):
        ...

    @abstractmethod
    def notify_error(self, error):
        ...

    @abstractmethod
    def notify_time_changed(self, new_time):
        ...

    @abstractmethod
    def notify_playback_status_changed(self, new_status):
        ...

    @abstractmethod
    def notify_end_reached(self):
        ...

    @abstractmethod
    def notify_load_video_done(self, media_track: MediaTrack):
        ...

    @abstractmethod
    def notify_snapshot_taken(self, snapshot_path):
        ...

    @abstractmethod
    def loopback_load_video_st2_set_media(self):
        ...

    @abstractmethod
    def loopback_load_video_st3_extract_media_track(self):
        ...

    @abstractmethod
    def loopback_load_video_st4_loaded(self):
        ...

    def load_video(self, media_input: MediaInput):
        """Step 1. Load & parse video file"""

        self._timeout_init = Settings().sync_get("player/video_init_timeout")
        self._timeout_init_start = time()

        self.media_input = media_input

        self._log.info("Loading {0}".format(self.media_input.uri))

        if is_url(self.media_input.uri):
            self._log.debug("Loading URL")
            parse_flag = vlc.MediaParseFlag.network
            parse_timeout = 60 * 1000
            self._media = self.instance.media_new(self.media_input.uri)
        else:
            self._log.debug("Loading local file")
            parse_flag = vlc.MediaParseFlag.local
            parse_timeout = -1
            self._media = self.instance.media_new_path(self.media_input.uri)

        if self._media is None:
            return self.error(translate("Video Error", "Failed to load media"))

        self._event_manager.attach_to_media(self._media)

        if not self.media_input.is_live and self.media_input.video.is_paused:
            self._media_options.append(":start-paused")

        self._media.add_options(*self._media_options)

        if self.is_preparse_required:
            self._media.parse_with_options(parse_flag, parse_timeout)

            self.notify_update_status(translate("Video Status", "Parsing media"))
        else:
            self.loopback_load_video_st2_set_media()

    def load_video_st2_set_media(self):
        """Step 2. Start video player with parsed file"""

        self._log.debug("Setting parsed media to player and waiting for buffering")

        self._media_player.set_media(self._media)

        self._event_waiter.async_wait_for(
            event="buffering",
            on_completed=self.loopback_load_video_st3_extract_media_track,
            on_timeout=lambda: self.error(
                translate("Video Error", "Buffering timeout")
            ),
            timeout=self.init_time_left,
        )

        self._media_player.play()

    def load_video_st3_extract_media_track(self):
        """Step 3. Extract media track"""

        self.notify_update_status(translate("Video Status", "Preparing video output"))

        self._log.debug("Extracting media track")

        self._init_media_track()

        if not self.media_track:
            # video not loaded yet, happens with live streams
            # waiting for decoder to catch first frame
            # usually time begins to tick after that

            # this can take a while
            if self.init_time_left == 0:
                self.error(translate("Video Error", "Timed out to extract media track"))
                return

            self._log.debug("No media track yet, waiting...")

            # could async_wait_for "time_changed", but some formats are unreliable (rtp)
            self._timer_extract_media_track = async_wait(
                MEDIA_EXTRACT_RETRY_TIME,
                self.loopback_load_video_st3_extract_media_track,
            )

            return

        self.loopback_load_video_st4_loaded()

    def load_video_st4_loaded(self):
        """Step 4. Setting initial video params"""

        self._log.debug("Load finished")

        if not self._try_set_initial_state():
            return

        self.is_video_initialized = True

        self.notify_load_video_done(self.media_track)

        self.notify_playback_status_changed(self._is_paused)
        self.notify_time_changed(self.media_input.initial_time)

    @only_initialized_player
    def snapshot(self):
        tmp_root = env.FLATPAK_RUNTIME_DIR if env.IS_FLATPAK else None

        file_path = Path(tempfile.mkdtemp(dir=tmp_root)) / "snapshot.png"

        self._log.debug(f"Taking snapshot to {file_path}")

        try:
            with self._event_waiter.waiting_for("snapshot_taken", SNAPSHOT_TIMEOUT):
                res = self._media_player.video_take_snapshot(0, str(file_path), 0, 0)
        except TimeoutError:
            self._log.error("Timed out to take snapshot")
            res = -1

        if res != 0:
            self._log.error("Failed to take snapshot")
            file_path.unlink(missing_ok=True)
            file_path.parent.rmdir()
            self.notify_snapshot_taken("")
            return

        self.notify_snapshot_taken(str(file_path))

    @only_initialized_player
    def stop(self):
        self._media_player.stop()

    @only_initialized_player
    def play(self):
        self._media_player.play()

    @only_initialized_player
    def set_pause(self, is_paused):
        self._log.debug(f"Set pause {is_paused}")

        if self.media_input.is_live:
            if is_paused:
                self.stop()
            else:
                self.play()
            return

        self._media_player.set_pause(is_paused)

    @only_initialized_player
    def set_time(self, seek_ms):
        if self.media_input.is_live:
            return

        if seek_ms > self.media_track.length - 1000:
            return

        self._media_player.set_time(seek_ms)

    @only_initialized_player
    def set_playback_rate(self, rate):
        if self.media_input.is_live:
            return

        self._media_player.set_rate(rate)

    @only_initialized_player
    def audio_set_mute(self, is_muted):
        self._media_player.audio_set_mute(is_muted)

    @only_initialized_player
    def audio_set_volume(self, volume_percent: float):
        volume = int(volume_percent * 100)

        self._media_player.audio_set_volume(volume)

    @property
    def video_dimensions(self):
        if self._media_player is None:
            if self.media_track:
                return self.media_track.video_dimensions
            return 0, 0

        return self._media_player.video_get_size()

    @only_initialized_player
    def adjust_view(self, size, aspect, scale):
        if self.media_track is None:
            # video not loaded yet, video frame resized on init
            if self.media_input:
                self.media_input.size = size
            return

        crop_aspect, crop_geometry = calc_crop(self.video_dimensions, size, aspect)

        resize_scale = calc_resize_scale(self.video_dimensions, size, aspect, scale)

        self._media_player.video_set_aspect_ratio("{0}:{1}".format(*crop_aspect))
        self._media_player.video_set_crop_geometry("{0}:{1}".format(*crop_geometry))
        self._media_player.video_set_scale(resize_scale)

    def _try_set_initial_state(self):
        try:
            self._set_initial_state()
        except TimeoutError:
            self.error(translate("Video Error", "Timed out setting initial state"))
            return False
        except NotPausedError:
            self.error(translate("Video Error", "Video failed to initialize paused"))
            return False

        return True

    def _set_initial_state(self):
        self._log.debug("Ensuring initial state")

        self._set_pause_initial(self.media_input.video.is_paused)

        self._adjust_view_initial()

        self._set_time_initial(self.media_input.initial_time)

    def _adjust_view_initial(self):
        if self.media_track.is_audio_only:
            return

        # wait for video output init
        # otherwise adjust_view won't work
        # if video is paused it happens on seek
        if not self.media_input.video.is_paused:
            self._event_waiter.wait_for("vout", self.init_time_left)

        self.adjust_view(
            size=self.media_input.size,
            aspect=self.media_input.video.aspect_mode,
            scale=self.media_input.video.scale,
        )

    def _set_pause_initial(self, is_paused):
        if not self.media_input.is_live and is_paused:
            if self._media_player.get_state() != vlc.State.Paused:
                raise NotPausedError

        if self.media_input.is_live and is_paused:
            self.snapshot()
            with self._event_waiter.waiting_for("stopped", self.init_time_left):
                self.stop()

        self._is_paused = is_paused

    def _set_time_initial(self, seek_ms):
        if self.media_input.is_live:
            return

        if self._is_paused or seek_ms > 0:
            with self._event_waiter.waiting_for("buffering", self.init_time_left):
                self._media_player.set_time(seek_ms)

            if not self.media_track.is_audio_only:
                self._event_waiter.wait_for("vout", self.init_time_left)

    def _get_media_track(self):
        media_tracks = self._media.tracks_get()

        if not media_tracks:
            self._log.debug("No media tracks found")
            return None

        video_tracks = (
            t.u.video.contents for t in media_tracks if t.type == vlc.TrackType.video
        )

        video_track = next(video_tracks, None)

        if video_track is None:
            self._log.debug("No video track found, audio only")
            return MediaTrack(
                is_audio_only=True,
                length=self._get_duration(),
                video_dimensions=(0, 0),
                fps=DEFAULT_FPS,
            )

        if not all([video_track.width, video_track.height]):
            self._log.debug("Video size is not initialized yet")
            if self.is_video_size_required:
                return None

        if all([video_track.frame_rate_num, video_track.frame_rate_den]):
            fps = video_track.frame_rate_num / video_track.frame_rate_den
        else:
            fps = DEFAULT_FPS

        return MediaTrack(
            is_audio_only=False,
            length=self._get_duration(),
            video_dimensions=(video_track.width, video_track.height),
            fps=fps,
        )

    def _init_media_track(self):
        if self.media_track is not None:
            return

        self.media_track = self._get_media_track()

        if self.media_track is None:
            return

        if self.media_track.length == -1 and not self.media_input.is_live:
            self._log.debug("Media length is not known, probably live stream")
            self.media_input.is_live = True

        self.media_input.length = self.media_track.length

    def _get_duration(self):
        if self.media_input.is_live:
            return -1

        return self._media.get_duration() or -1
