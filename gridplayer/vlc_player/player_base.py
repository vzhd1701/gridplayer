import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from time import time
from types import MappingProxyType

from gridplayer.params import env
from gridplayer.params.static import (
    VIDEO_END_LOOP_MARGIN_MS,
    AudioChannelMode,
    VideoCrop,
    VideoTransform,
)
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
from gridplayer.vlc_player.player_tracks_manager import TracksManager
from gridplayer.vlc_player.static import Media, MediaInput, NotPausedError

SNAPSHOT_TIMEOUT = 15

MEDIA_EXTRACT_RETRY_TIME = 0.1

# https://github.com/videolan/vlc/blob/c650ce1a4e352cc04192229a8878b8b6c312527d/include/vlc_aout.h#L92
AUDIO_CHANNEL_MODE_MAP = MappingProxyType(
    {
        AudioChannelMode.UNSET: 0,
        AudioChannelMode.STEREO: 1,
        AudioChannelMode.RSTEREO: 2,
        AudioChannelMode.LEFT: 3,
        AudioChannelMode.RIGHT: 4,
        AudioChannelMode.DOLBYS: 5,
        AudioChannelMode.HEADPHONES: 6,
        AudioChannelMode.MONO: 7,
    }
)


def translate(context, text):
    """
    This is just a dummy to make strings discoverable via pylupdate,
    actual translation takes place in Qt app
    """
    return text


def only_initialized_player(func):
    def wrapper(*args, **kwargs):
        self = args[0]
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
        self._get_time_retries = 0

        self._timer_unpause_failsafe = None
        self._timer_extract_media_track = None

        self.media_input: MediaInput | None = None
        self.media: Media | None = None

        self._playlist_player = None
        self._media_player = None
        self._media_input_vlc = None
        self._media_options = []
        self._tracks_manager: TracksManager | None = None

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
        self._playlist_player = self.instance.media_list_player_new()
        self._playlist_player.set_playback_mode(vlc.PlaybackMode.repeat)

        self._media_player = self._playlist_player.get_media_player()

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
        if self.media.is_live:
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
            self._init_media_tracks()

        elif event.u.new_status == vlc.MediaParsedStatus.timeout:
            return self.error(translate("Video Error", "Media parse timeout"))

        else:
            return self.error(translate("Video Error", "Media parse failed"))

        if self.is_preparse_required:
            self.loopback_load_video_st2_set_media()

    def cb_time_changed(self, event):
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

        if self._playlist_player is not None:
            self._log.debug("Releasing playlist player")

            playlist_player = self._playlist_player
            self._playlist_player = None

            playlist_player.release()

            self._log.debug("Playlist player released")

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
    def notify_update_status(self, status, percent=0): ...

    @abstractmethod
    def notify_error(self, error): ...

    @abstractmethod
    def notify_time_changed(self, new_time): ...

    @abstractmethod
    def notify_playback_status_changed(self, new_status): ...

    @abstractmethod
    def notify_load_video_done(self, media_track: Media): ...

    @abstractmethod
    def notify_snapshot_taken(self, snapshot_path): ...

    @abstractmethod
    def loopback_load_video_st2_set_media(self): ...

    @abstractmethod
    def loopback_load_video_st3_extract_media_track(self): ...

    @abstractmethod
    def loopback_load_video_st4_loaded(self): ...

    def load_video(self, media_input: MediaInput):
        """Step 1. Load & parse video file"""

        self._timeout_init = Settings().sync_get("player/video_init_timeout")
        self._timeout_init_start = time()
        self._get_time_retries = 0

        self.media_input = media_input

        self._log.info(f"Loading {self.media_input.uri}")

        if is_url(self.media_input.uri):
            self._log.debug("Loading URL")
            parse_flag = vlc.MediaParseFlag.network
            parse_timeout = 60 * 1000
            self._media_input_vlc = self.instance.media_new(self.media_input.uri)
        else:
            self._log.debug("Loading local file")
            parse_flag = vlc.MediaParseFlag.local
            parse_timeout = -1
            self._media_input_vlc = self.instance.media_new_path(self.media_input.uri)

        if self._media_input_vlc is None:
            return self.error(translate("Video Error", "Failed to load media"))

        self._event_manager.attach_to_media(self._media_input_vlc)

        if not self.media_input.is_live and self.media_input.video.is_paused:
            self._media_options.append(":start-paused")

        if self.media_input.is_audio_only:
            self._media_options.append(":no-video")

        self._media_input_vlc.add_options(*self._media_options)

        if self.is_preparse_required:
            self._media_input_vlc.parse_with_options(parse_flag, parse_timeout)

            self.notify_update_status(translate("Video Status", "Parsing media"))
        else:
            self.loopback_load_video_st2_set_media()

    def load_video_st2_set_media(self):
        """Step 2. Start video player with parsed file"""

        self._log.debug("Setting parsed media to player and waiting for buffering")

        playlist = self.instance.media_list_new()
        playlist.add_media(self._media_input_vlc)

        self._playlist_player.set_media_list(playlist)

        self._event_waiter.async_wait_for(
            event="buffering",
            on_completed=self.loopback_load_video_st3_extract_media_track,
            on_timeout=lambda: self.error(
                translate("Video Error", "Buffering timeout")
            ),
            timeout=self.init_time_left,
        )

        self._playlist_player.play_item_at_index(0)

    def load_video_st3_extract_media_track(self):
        """Step 3. Extract media track"""

        self.notify_update_status(translate("Video Status", "Preparing video output"))

        self._log.debug("Extracting media track")

        self._init_media_tracks()

        if not self.media:
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

        self.notify_load_video_done(self.media)

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

        if seek_ms > self.media.length - VIDEO_END_LOOP_MARGIN_MS:
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

    @only_initialized_player
    def set_audio_track(self, track_id):
        self._tracks_manager.set_audio_track_id(track_id)

    @only_initialized_player
    def set_video_track(self, track_id):
        self._tracks_manager.set_video_track_id(track_id)

    @only_initialized_player
    def set_audio_channel_mode(self, mode: AudioChannelMode):
        self._media_player.audio_set_channel(AUDIO_CHANNEL_MODE_MAP[mode])

    @property
    def video_dimensions(self):
        if self._media_player is None or self.media is None:
            return 0, 0

        video_size = self._media_player.video_get_size()

        rotation_transforms = {
            VideoTransform.ROTATE_90,
            VideoTransform.ROTATE_270,
            VideoTransform.TRANSPOSE,
            VideoTransform.ANTITRANSPOSE,
        }

        if self.media_input.video.transform in rotation_transforms:
            return tuple(reversed(video_size))

        return video_size

    @only_initialized_player
    def adjust_view(self, size, aspect, scale, crop):
        if self.media is None:
            # video not loaded yet, video frame resized on init
            if self.media_input:
                self.media_input.size = size
            return

        crop_aspect, crop_geometry = calc_crop(self.video_dimensions, size, aspect)

        if crop == VideoCrop(0, 0, 0, 0):
            crop_geometry_fmt = "{}:{}".format(*crop_geometry)
        else:
            crop_geometry_fmt = "+{}+{}+{}+{}".format(*crop)

        self._log.debug(
            f"size: {size}"
            f", aspect: {aspect}"
            f", scale: {scale}"
            f", crop: {crop}"
            f", crop_aspect: {crop_aspect}"
            f", crop_geo: {crop_geometry}"
            f", crop_geo_fmt: {crop_geometry_fmt}"
        )

        resize_scale = calc_resize_scale(self.video_dimensions, size, aspect, scale)

        self._media_player.video_set_aspect_ratio("{}:{}".format(*crop_aspect))
        # https://github.com/videolan/vlc/blob/e9eceaed4d838dbd84638bfb2e4bdd08294163b1/src/video_output/display.c#L887
        self._media_player.video_set_crop_geometry(crop_geometry_fmt)
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
        if self.media.is_audio_only:
            return

        # wait for video output init
        # otherwise adjust_view won't work
        # if video is paused it happens on seek
        # doesn't work on MacOS for some reason
        if not env.IS_MACOS and not self.media_input.video.is_paused:
            self._event_waiter.wait_for("vout", self.init_time_left)

        self.adjust_view(
            size=self.media_input.size,
            aspect=self.media_input.video.aspect_mode,
            scale=self.media_input.video.scale,
            crop=self.media_input.video.crop,
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
            # Event waiting hangs on init in MacOS
            if env.IS_MACOS:
                self._media_player.set_time(seek_ms)
            else:
                with self._event_waiter.waiting_for("buffering", self.init_time_left):
                    self._media_player.set_time(seek_ms)

                if not self.media.is_audio_only:
                    self._event_waiter.wait_for("vout", self.init_time_left)

    def _init_media_tracks(self):
        if self.media is not None:
            return

        self.media = self._get_loaded_media()

        if self.media is None:
            return

        if self.media.length == -1 and not self.media_input.is_live:
            self._log.debug("Media length is not known, probably live stream")
            self.media_input.is_live = True

        self.media_input.length = self.media.length

    def _get_loaded_media(self):
        media_tracks = self._media_input_vlc.tracks_get()

        if not media_tracks:
            self._log.debug("No media tracks found")
            return None

        self._tracks_manager = TracksManager(
            media_player=self._media_player,
            media_tracks=list(media_tracks),
            is_audio_only=self.media_input.is_audio_only,
        )

        if not self._tracks_manager.is_video_size_initialized:
            self._log.debug("Video size is not initialized yet")
            if self.is_video_size_required:
                return None

        length = self._get_duration()

        if not self.media_input.is_live and length == -1:
            if self._get_time_retries < 10:
                self._get_time_retries += 1
                self._log.debug(
                    f"Video time not initialized yet,"
                    f" attempt {self._get_time_retries}..."
                )
                return None

            self._log.debug("Failed to initialize video time, probably live")

        self._tracks_manager.set_video_track_id(self.media_input.video.video_track_id)
        self._tracks_manager.set_audio_track_id(self.media_input.video.audio_track_id)

        return Media(
            length=length,
            video_tracks=self._tracks_manager.video_tracks,
            audio_tracks=self._tracks_manager.audio_tracks,
            cur_video_track_id=self._tracks_manager.current_video_track_id,
            cur_audio_track_id=self._tracks_manager.current_audio_track_id,
        )

    def _get_duration(self):
        if self.media_input.is_live:
            return -1

        return self._media_input_vlc.get_duration() or -1
