import dataclasses
import logging
import tempfile
from abc import ABC, abstractmethod
from functools import partial
from pathlib import Path
from time import time
from types import MappingProxyType

from gridplayer.models.audio_device import (
    SYSTEM_DEFAULT_DEVICE_ID,
    AudioDevice,
    resolve_device_id,
)
from gridplayer.models.audio_selection import AudioExternal, track_of_file
from gridplayer.models.subtitle_selection import SubtitleExternal
from gridplayer.models.subtitle_selection import track_of_file as subtitle_track_of_file
from gridplayer.params import env
from gridplayer.params.static import AudioChannelMode, VideoTransform
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import calc_resize_scale, calc_view_geometry
from gridplayer.utils.misc import is_url
from gridplayer.vlc_player.libvlc import vlc
from gridplayer.vlc_player.player_event_manager import EventManager
from gridplayer.vlc_player.player_event_waiter import (
    EventWaiter,
    async_timer,
    async_wait,
)
from gridplayer.vlc_player.player_tracks_manager import TracksManager
from gridplayer.vlc_player.static import (
    Media,
    MediaInput,
    NotPausedError,
    is_loop_wrapped,
    wanted_audio_track_id,
    wanted_subtitle_track_id,
)

MEDIA_EXTRACT_RETRY_TIME = 0.1

# An audio file attached to a video that is already playing is opened in
# VLC's own time, and the track it brings shows up whenever that is done.
# Asking again until it does beats guessing how long a disk takes.
SLAVE_TRACK_RETRY_TIME = 0.1

# Nothing rides on the number: only one file is ever attached, and libVLC
# opens it whatever priority it was handed.
SLAVE_PRIORITY = 4

# A file that opens at all is measured in tens of milliseconds; one that
# never will is better handed back quickly, so the video can be loaded with
# it instead while the viewer is still looking at the pane they clicked.
SLAVE_TRACK_RETRIES = 6

# how many of the events around a restart to try putting the tracks back on
RESTART_REAPPLY_TRIES = 12

# VLC loops the input in place: it seeks back inside the same input thread, so
# there is no end of media, no demuxer or decoder teardown and no new video
# output -- unlike the media list player's repeat, which restarts the item.
# Nothing has to be cut off the end to beat the time event round trip, so even
# a 400ms clip loops cleanly, and a finished pass shows up as nothing but the
# time going backwards.
#
# The count has to be positive (a negative one reads as "do not repeat"), so
# "forever" is a number no playback will reach: 2 billion passes of a 400ms
# clip is 25 years.
#
# Adaptive media loops this way too, but the wrap is a seek, and that demuxer
# restarts its elementary streams on one and renumbers them (see
# Stream.is_adaptive). A track picked by hand is held by the number it had, so
# it comes back selecting nothing at all -- hence
# _arm_tracks_reapply_if_renumbered, since no end of media arrives to arm it.
INPUT_REPEAT_FOREVER = 2_000_000_000

# VLC's adaptive demuxer restarts the video decoder on every seek, and picking
# that decoder rebuilds the video output -- once per hardware format avcodec
# tries before settling. Every driver pays for that, each in its own way: the
# ones drawing into our window handle lose it to VLC's own window while the
# outgoing output still holds it, and the ones taking frames through shared
# memory re-negotiate the buffer under a decoder that is still writing to it.
# Naming the decoder up front keeps the output alive across a restart.
#
# "avcodec-hw=none" makes it worse rather than better: avcodec still walks
# every hardware format, and rebuilds the video output for each one it rejects.
SOFTWARE_DECODERS = MappingProxyType({"av01": "dav1d"})

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
        self._timer_audio_slave = None
        self._timer_subtitle_slave = None

        # how many audio tracks the file has of its own, counted before any
        # external audio went on; None where it could not be counted
        self._own_audio_count = None

        # the same for subtitles, counted in the same pass
        self._own_subtitle_count = None

        self._is_parse_for_slaves = False

        self.media_input: MediaInput | None = None
        self.media: Media | None = None

        self._playlist_player = None
        self._media_player = None
        self._media_input_vlc = None
        self._media_options = []
        self._tracks_manager: TracksManager | None = None
        self._last_video_size = (0, 0)

        # counts down the events after the media ends, while the tracks are
        # put back on the new pass; see _reapply_tracks_after_restart
        self._restart_reapply_tries = 0

        # last time update seen, to tell a finished pass from a running one
        self._last_time = None

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

        # backstop for whatever :input-repeat does not cover: restarting the
        # item beats ending on a black frame, even though every pass costs a
        # decoder and video output rebuild
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
            "vout": self.cb_vout,
        }

        for event_name, callback in callbacks.items():
            self._event_manager.subscribe(event_name, callback)

    def cb_buffering(self, event):
        buffered_percent = int(event.u.new_cache)
        self.notify_update_status(
            translate("Video Status", "Buffering"), buffered_percent
        )

    def cb_vout(self, event):
        # macOS: _adjust_view_initial skips the synchronous vout wait, so
        # its initial crop/aspect calls run before the video output exists and
        # are dropped — the video renders uncropped until the next resize.
        # Re-apply once the output is up. Setting the crop doesn't change
        # the vout count, so this won't re-fire itself.
        #
        # Linux: synchronous vout wait doesn't help sometimes
        # Windows: seems fine with sync wait, but re-apply here too just in case
        #
        # The re-apply is DEFERRED off the libvlc event thread via
        # _schedule_view_reapply: cb_vout runs inside a libvlc event callback,
        # so re-entering libvlc setters synchronously here risks a deadlock.

        if self.media is None or self.media.is_audio_only or self.media_input is None:
            return
        self._log.debug(
            f"Video output ready, re-applying view at {self.media_input.size}"
        )

        self._schedule_view_reapply()

        # A video output arriving once the media is up is the decoder having
        # been restarted under us. Nothing else announces it.
        self._arm_tracks_reapply_if_renumbered()

        self._reapply_tracks_after_restart()

    def cb_playing(self, event):
        self._log.debug("Media playing")

        if not self.is_video_initialized:
            return

        self._reapply_tracks_after_restart()

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

        # the player is set to repeat, so this is the start of a new pass
        self._arm_tracks_reapply()

    def cb_error(self, event):
        self.error(translate("Video Error", "Player error"))

    def cb_parse_changed(self, event):
        self._log.debug("Media parse changed")

        if self._is_parse_for_slaves:
            self._load_video_with_slaves(event.u.new_status)
            return

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

        # a pass ending without a picture to rebuild -- audio only -- leaves
        # the time falling back as the only sign the streams were restarted
        if self.media is not None:
            if is_loop_wrapped(self._last_time, new_time, self.media.length):
                self._arm_tracks_reapply_if_renumbered()

        self._last_time = new_time

        self.notify_time_changed(new_time)

        self._reapply_tracks_after_restart()

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

        if self._timer_audio_slave is not None:
            self._timer_audio_slave.cancel()

        if self._timer_subtitle_slave is not None:
            self._timer_subtitle_slave.cancel()

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

    def notify_tracks_changed(self, media_track: Media) -> None:  # noqa: B027
        """Forward a track list that changed after the load. No-op by default."""

    def notify_video_dimensions(self, width: int, height: int) -> None:  # noqa: B027
        """Forward decoded size to the widget. Default is a no-op."""

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
        self._last_video_size = (0, 0)
        self._last_time = None
        self._own_audio_count = None
        self._own_subtitle_count = None

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

        if not self.media_input.is_live:
            # let VLC wrap the input around on its own, seamlessly
            self._media_options.append(f":input-repeat={INPUT_REPEAT_FOREVER}")

        if self.media_input.is_audio_only:
            self._media_options.append(":no-video")

        if self._preferred_decoder is not None:
            # a preference, not a demand -- VLC still falls back to the rest
            self._log.debug(
                f"Preferring {self._preferred_decoder}"
                f" for {self.media_input.video_codec}"
            )
            self._media_options.append(f"codec={self._preferred_decoder}")

        if self.media_input.video.subtitle_encoding:
            # a fallback rather than an override: VLC reads the file as UTF-8
            # wherever it is valid UTF-8 and only reaches for this when it is
            # not, so a file that was already UTF-8 comes out the same either
            # way. Text subtitles only -- ASS and SSA go through libass, which
            # this never reaches.
            self._media_options.append(
                f":subsdec-encoding={self.media_input.video.subtitle_encoding}"
            )

        self._media_input_vlc.add_options(*self._media_options)

        # Files of their own have to go on before the video starts, and what
        # the video has of its own has to be counted before that -- afterwards
        # there is no telling the two apart. Reading the file is the only way
        # to count them, so a video with either kind attached is parsed first.
        self._is_parse_for_slaves = (
            self.media_input.selected_audio_slave is not None
            or bool(self.media_input.selected_subtitle_slaves)
        )

        if self.is_preparse_required or self._is_parse_for_slaves:
            self._media_input_vlc.parse_with_options(parse_flag, parse_timeout)

            self.notify_update_status(translate("Video Status", "Parsing media"))
        else:
            self.loopback_load_video_st2_set_media()

    def _load_video_with_slaves(self, parse_status) -> None:
        """Step 1b. Count what the video has of its own, then add the files.

        A video that will not parse still plays: it only loses the ability
        to say which of its tracks came from where.
        """

        self._is_parse_for_slaves = False

        if parse_status == vlc.MediaParsedStatus.done:
            self._count_own_tracks()
        else:
            self._log.warning(f"Media parse came back {parse_status}")

        self._attach_audio_slave()
        self._attach_subtitle_slaves()

        self.loopback_load_video_st2_set_media()

    def _count_own_tracks(self) -> None:
        media_tracks = self._read_media_tracks()

        if media_tracks is None:
            return

        self._own_audio_count = sum(
            1 for track in media_tracks if track.type == vlc.TrackType.audio
        )

        self._own_subtitle_count = sum(
            1 for track in media_tracks if track.type == vlc.TrackType.ext
        )

        self._log.debug(
            f"Video has {self._own_audio_count} audio"
            f" and {self._own_subtitle_count} subtitle tracks of its own"
        )

    def _attach_audio_slave(self) -> None:
        """Hand VLC the audio file this video is to be played with."""

        uri = self.media_input.selected_audio_slave

        if uri is None:
            return

        self._log.debug(f"Attaching audio slave {uri}")

        self._media_input_vlc.slaves_add(vlc.MediaSlaveType.audio, SLAVE_PRIORITY, uri)

    def _attach_subtitle_slaves(self) -> None:
        """Hand VLC the subtitle files this video is to be shown with.

        As many as were picked, where the sound gets one: libVLC opens each
        as a track of its own and writes the file's name into the track
        description, so nothing has to be told apart by counting alone.
        """

        for uri in self.media_input.selected_subtitle_slaves:
            self._log.debug(f"Attaching subtitle slave {uri}")

            self._media_input_vlc.slaves_add(
                vlc.MediaSlaveType.subtitle, SLAVE_PRIORITY, uri
            )

    @only_initialized_player
    def add_subtitle_slave(self, uri: str) -> None:
        """Show a subtitle file on a video that is already loaded.

        No reload is needed for this, unlike an audio file: the tracks a
        subtitle file brings can be told from the video's own whatever else
        is attached, so there is never a reason to start over.
        """

        if self.media is None or not uri:
            return

        if uri in self.media_input.selected_subtitle_slaves:
            return

        self._log.debug(f"Adding subtitle slave {uri}")

        # not selected here: which subtitle to show is settled by what was
        # picked for this video, once the track it brought has turned up.
        # Letting libVLC choose would put the file on screen even where the
        # video is being watched with its subtitles off.
        if self._media_player.add_slave(vlc.MediaSlaveType.subtitle, uri, False) != 0:
            self._log.warning(f"Failed to add subtitle slave {uri}")
            return

        self.media_input.selected_subtitle_slaves = (
            *self.media_input.selected_subtitle_slaves,
            uri,
        )

        self._await_subtitle_slave_track(
            len(self.media.subtitle_tracks) + 1, SLAVE_TRACK_RETRIES
        )

    def _await_subtitle_slave_track(self, wanted_count: int, tries_left: int) -> None:
        """Wait for VLC to open what it was handed, then take the list again.

        The same wait an audio file needs, and for the same reason: the
        file is opened in VLC's own time and the track shows up whenever
        that is done.
        """

        media_tracks = self._read_media_tracks()

        is_arrived = media_tracks is not None and (
            sum(1 for t in media_tracks if t.type == vlc.TrackType.ext) >= wanted_count
        )

        if not is_arrived and tries_left > 0:
            self._timer_subtitle_slave = async_wait(
                SLAVE_TRACK_RETRY_TIME,
                partial(self._await_subtitle_slave_track, wanted_count, tries_left - 1),
            )
            return

        if media_tracks is None:
            return

        if not is_arrived:
            self._log.warning("Subtitle slave brought no track")

        if self._tracks_manager is not None:
            self._tracks_manager.update_tracks(media_tracks)

        # the file was picked to be read, so put it on screen now that
        # there is something to put on. Before the refresh, so that the
        # pane is told once, with the track already showing.
        self._apply_wanted_subtitle_track()

        self._refresh_media_tracks(media_tracks)

    @only_initialized_player
    def add_audio_slave(self, uri: str) -> None:
        """Play an audio file alongside a video that is already loaded.

        The same thing _attach_audio_slave does at load, done without
        taking the video down and putting it back up for it. Only sound to
        be heard right away comes this way: a video that already has a file
        attached is loaded again instead, since libVLC will not take one
        back and two of them cannot be told apart.
        """

        if self.media is None or not uri:
            return

        self._log.debug(f"Adding audio slave {uri}")

        if self._media_player.add_slave(vlc.MediaSlaveType.audio, uri, True) != 0:
            self._log.warning(f"Failed to add audio slave {uri}")
            return

        self.media_input.selected_audio_slave = uri

        self._await_audio_slave_track(
            len(self.media.audio_tracks) + 1, SLAVE_TRACK_RETRIES
        )

    def _await_audio_slave_track(self, wanted_count: int, tries_left: int) -> None:
        """Wait for VLC to open what it was handed, then take the list again.

        A file is opened in VLC's own time and the tracks show up whenever
        that is done, so there is nothing to do but ask again.
        """

        media_tracks = self._read_media_tracks()

        is_arrived = media_tracks is not None and (
            sum(1 for t in media_tracks if t.type == vlc.TrackType.audio)
            >= wanted_count
        )

        if not is_arrived and tries_left > 0:
            self._timer_audio_slave = async_wait(
                SLAVE_TRACK_RETRY_TIME,
                partial(self._await_audio_slave_track, wanted_count, tries_left - 1),
            )
            return

        if media_tracks is None:
            return

        if not is_arrived:
            self._log.warning("Audio slave brought no track")

        self._refresh_media_tracks(media_tracks)

    def _read_media_tracks(self):
        # the player is released before the media is, and a wait that
        # outlived it has nothing left to ask
        if self._media_input_vlc is None or self._media_player is None:
            return None

        media_tracks = self._media_input_vlc.tracks_get()

        return list(media_tracks) if media_tracks else None

    def _refresh_media_tracks(self, media_tracks) -> None:
        """Take the track list again, after something changed what is in it."""

        if self._tracks_manager is None or self.media is None:
            return

        if self._media_player is None:
            return

        self._tracks_manager.update_tracks(media_tracks)

        self.media = dataclasses.replace(
            self.media,
            video_tracks=self._tracks_manager.video_tracks,
            audio_tracks=self._tracks_manager.audio_tracks,
            cur_video_track_id=self._tracks_manager.current_video_track_id,
            cur_audio_track_id=self._tracks_manager.current_audio_track_id,
            external_audio_ids=self._external_audio_ids(),
            subtitle_tracks=self._tracks_manager.subtitle_tracks,
            cur_subtitle_track_id=self._tracks_manager.current_subtitle_track_id,
            external_subtitle_ids=self._external_subtitle_ids(),
        )

        self.notify_tracks_changed(self.media)

    def _wanted_audio_track_id(self) -> int | None:
        """Which track this video's settings call for, its own file included."""

        selection = self.media_input.video.audio_selection

        if isinstance(selection, AudioExternal):
            picked = track_of_file(selection, self._external_audio_ids())

            if picked is not None:
                return picked

        return wanted_audio_track_id(
            self.media_input.video, self._tracks_manager.audio_tracks
        )

    def _external_audio_ids(self) -> tuple[int, ...]:
        """Which audio tracks came out of the file attached to the video.

        The video's own are counted before anything goes on, and libVLC
        puts what a file brings after them, so everything past that count
        is the file's. One file is attached at a time for exactly this
        reason: libVLC never says which stream came from where, and with
        one file there is nothing left to say -- all of these are its own,
        however many it turns out to hold.
        """

        if self._own_audio_count is None:
            return ()

        return tuple(self._tracks_manager.audio_tracks)[self._own_audio_count :]

    def _wanted_subtitle_track_id(self) -> int | None:
        """Which subtitle this video's settings call for, its own files included.

        Only the player knows which track came out of which file, so a pick
        of one is answered here; everything else the video can answer for
        itself.
        """

        selection = self.media_input.video.subtitle_selection

        if isinstance(selection, SubtitleExternal):
            picked = subtitle_track_of_file(selection, self._external_subtitle_ids())

            if picked is not None:
                return picked

        return wanted_subtitle_track_id(
            self.media_input.video,
            self._tracks_manager.subtitle_tracks,
            self._external_subtitle_ids(),
        )

    def _external_subtitle_ids(self) -> tuple[int, ...]:
        """Which subtitle tracks came out of the files attached to the video.

        Counted the same way the audio's are: what the video has of its own
        is counted before anything goes on, and libVLC puts what a file
        brings after that. Several files can be attached here where audio
        takes one, since each is named in its own track description and the
        order they were attached in is the order they come back in.
        """

        if self._own_subtitle_count is None:
            return ()

        return tuple(self._tracks_manager.subtitle_tracks)[self._own_subtitle_count :]

    @property
    def _audio_devices(self) -> tuple[AudioDevice, ...]:
        """Every way out of the machine the output module in force offers.

        Asked of the player rather than of the instance, which is where
        libVLC keeps it, and answerable before anything has played. The
        entry with no id of its own is left out: it stands for whichever
        way out the machine is using, which is what a video that chose
        nothing is already getting.
        """

        devices = []

        devices_head = self._media_player.audio_output_device_enum()

        device_ptr = devices_head

        while device_ptr:
            device = device_ptr.contents

            if device.device:
                devices.append(
                    AudioDevice(
                        id=_decode_device_field(device.device),
                        name=_decode_device_field(device.description),
                    )
                )

            device_ptr = device.next

        if devices_head:
            vlc.libvlc_audio_output_device_list_release(devices_head)

        return tuple(devices)

    def _apply_wanted_audio_device(self, available: tuple[AudioDevice, ...]) -> None:
        """Send this video's sound the way it was told to, if it still can.

        Asked for on every load because the player forgets it: stopping one
        drops the choice, and what opens next comes back on the machine's
        own way out with nothing anywhere to say it ever moved.
        """

        wanted = self.media_input.video.audio_device

        if wanted is None:
            return

        device_id = resolve_device_id(wanted, available)

        if device_id is None:
            # the window says so too, having been handed the same list;
            # here it is worth a line because silence is the alternative
            self._log.warning(
                f"Audio device {wanted.name or wanted.id} is not here,"
                " leaving the sound where the machine puts it"
            )
            return

        self._log.debug(f"Set audio device {device_id}")

        self._media_player.audio_output_device_set(None, device_id)

    def _apply_wanted_subtitle_track(self) -> None:
        """Show whichever subtitle this video's settings call for.

        A media with none to show is left alone rather than switched off:
        there is nothing to switch off, and leaving it alone is what keeps
        a video with no subtitles in it from paying for them on every loop.
        """

        if self._tracks_manager is None or not self._tracks_manager.subtitle_tracks:
            return

        self._tracks_manager.set_subtitle_track_id(self._wanted_subtitle_track_id())

    @property
    def _preferred_decoder(self) -> str | None:
        """Decoder to ask for, where the one VLC would pick costs us the window."""

        if not self.media_input.is_adaptive:
            return None

        return SOFTWARE_DECODERS.get(self.media_input.video_codec)

    def load_video_st2_set_media(self):
        """Step 2. Start video player with parsed file"""

        # Can happen if spam reload
        if not self._playlist_player:
            return

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

        self._fill_missing_track_dimensions()

        self.is_video_initialized = True

        self.notify_load_video_done(self.media)

        self.notify_playback_status_changed(self._is_paused)
        self.notify_time_changed(self.media_input.initial_time)

    @only_initialized_player
    def snapshot(self):
        tmp_root = env.FLATPAK_RUNTIME_DIR if env.IS_FLATPAK else None

        file_path = Path(tempfile.mkdtemp(dir=tmp_root)) / "snapshot.png"

        self._log.debug(f"Taking snapshot to {file_path}")

        # libvlc_video_take_snapshot returns 0 whenever a vout exists, even if
        # the vout-side grab times out (VLC waits 500ms) and nothing is
        # written. The save is synchronous in VLC 3.x, so the file itself is
        # the reliable result. The MediaPlayerSnapshotTaken event can't be
        # used: it is only emitted on success and it is broadcast to every
        # media player sharing the libvlc instance, so another player's
        # snapshot would wake this player's waiter.
        res = self._media_player.video_take_snapshot(0, str(file_path), 0, 0)

        if res != 0 or not file_path.is_file():
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

        # Seeks close to the end used to be dropped, to keep the player from
        # running the media out; with :input-repeat it wraps instead of ending,
        # so clamping is enough -- and a video shorter than the old margin can
        # be seeked at all now.
        seek_ms = max(seek_ms, 0)

        # a media with no length known yet has no end to clamp to
        if self.media.length > 0:
            seek_ms = min(seek_ms, self.media.length - 1)

        self._media_player.set_time(seek_ms)

        # An adaptive seek restarts the streams and renumbers them whether it
        # came from a loop or from the viewer dragging the bar. A video stream
        # says so by rebuilding its output; one without a picture says nothing
        # at all, and a seek forward leaves the time no lower than it found it,
        # so nothing else here would notice.
        self._arm_tracks_reapply_if_renumbered()

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
    def set_subtitle_track(self, track_id):
        self._tracks_manager.set_subtitle_track_id(track_id)

    @only_initialized_player
    def set_audio_device(self, device: AudioDevice | None):
        """Send this video's sound another way out, while it plays.

        It moves at once, which the track and the delay do not: passing no
        module name asks libVLC to move the sound rather than to note it
        down for whatever opens next.

        Kept on the media input as well, since that is what the next load
        reads, and a load is where the choice would otherwise be dropped.
        """

        self.media_input.video.audio_device = device

        if device is None:
            self._log.debug("Set audio device to the machine's own")

            # an id of nothing at all, which is not the same as asking for
            # nothing: asking for nothing leaves the player where it is
            self._media_player.audio_output_device_set(None, SYSTEM_DEFAULT_DEVICE_ID)
            return

        self._apply_wanted_audio_device(self._audio_devices)

    @only_initialized_player
    def set_audio_channel_mode(self, mode: AudioChannelMode):
        self._media_player.audio_set_channel(AUDIO_CHANNEL_MODE_MAP[mode])

    @only_initialized_player
    def set_audio_delay(self, delay_ms: int):
        self._tracks_manager.set_audio_delay_ms(delay_ms)

    @only_initialized_player
    def set_subtitle_delay(self, delay_ms: int):
        self._tracks_manager.set_subtitle_delay_ms(delay_ms)

    @property
    def video_dimensions(self):
        if self._media_player is None or self.media is None:
            return 0, 0

        video_size = self._media_player.video_get_size()
        if all(video_size):
            self._last_video_size = video_size
        elif all(self._last_video_size):
            # Live stop/play recreates the vout; cb_vout can fire before
            # video_get_size() is populated again. Reuse the last decoded size
            # so FIT/STRETCH crop geometry is not computed as letterbox.
            video_size = self._last_video_size

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
        # Keep the pane size current on every call so the post-vout re-apply
        # (cb_vout) and _adjust_view_initial use the real laid-out size, not a
        # stale pre-layout value captured at load. Live streams stop/play on
        # pause, which recreates the vout and re-applies from media_input —
        # crop/aspect/scale must be persisted here too (the widget copy of
        # Video is a different object after the multiprocess pickle).
        if self.media_input is not None:
            self.media_input.size = size
            self.media_input.video.aspect_mode = aspect
            self.media_input.video.scale = scale
            self.media_input.video.crop = crop

        if self.media is None:
            # video not loaded yet, video frame resized on init
            return

        if self._fill_missing_track_dimensions():
            width, height = self._media_player.video_get_size()
            self.notify_video_dimensions(width, height)

        aspect_override, crop_geometry_fmt = calc_view_geometry(
            self.video_dimensions, size, aspect, crop
        )

        self._log.debug(
            f"size: {size}"
            f", aspect: {aspect}"
            f", scale: {scale}"
            f", crop: {crop}"
            f", aspect_override: {aspect_override}"
            f", crop_geo_fmt: {crop_geometry_fmt}"
        )

        resize_scale = calc_resize_scale(
            self.video_dimensions, size, aspect, scale, crop
        )

        self._media_player.video_set_aspect_ratio(aspect_override)
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

        self._adjust_view_initial()

        # Play first (no :start-paused). That option shows frame 0 but
        # leaves set_time-while-paused broken until the file has actually
        # played. Seek while playing, then pause

        self._set_time_initial(self.media_input.initial_time)

        self._set_pause_initial(self.media_input.video.is_paused)

        # If paused seek again to ensure actual position
        # in case time drifted while _set_pause_initial
        if self.media_input.video.is_paused:
            self._set_time_initial(self.media_input.initial_time)

    def _adjust_view_initial(self):
        if self.media.is_audio_only:
            return

        # wait for video output init
        # otherwise adjust_view won't work
        # doesn't work on MacOS for some reason — cb_vout re-applies there
        if not env.IS_MACOS:
            self._event_waiter.wait_for("vout", self.init_time_left)

        self._apply_media_input_view()

    def _schedule_view_reapply(self):
        # Default: apply directly. Threaded subclasses override this to marshal
        # the call off the libvlc event thread onto their event loop, since
        # cb_vout runs inside a libvlc event callback and must not re-enter libvlc.
        self._apply_media_input_view()

    def _schedule_tracks_reapply(self):
        # Deferred for the same reason as the view: cb_playing runs inside a
        # libvlc event callback and must not re-enter libvlc.
        self._reapply_tracks()

    def _arm_tracks_reapply(self):
        """Put the chosen tracks back over the events that follow."""

        if not self.is_video_initialized:
            return

        self._restart_reapply_tries = RESTART_REAPPLY_TRIES

    def _arm_tracks_reapply_if_renumbered(self):
        """The same, for streams restarted where the media never ended.

        Only the adaptive demuxer does that, and only it renumbers the
        streams it restarts. Everything else comes back on the tracks it
        left on, and asking again would flush the sound for nothing.
        """

        if self.media_input is None or not self.media_input.is_adaptive:
            return

        self._arm_tracks_reapply()

    def _reapply_tracks_after_restart(self):
        """Put the tracks back after a loop, once the new pass will take it.

        The events that say a restart is under way all arrive before the
        new input has its streams, so this runs on each of them in turn
        until the player agrees, rather than chasing a media that is
        never going to answer.
        """

        if self._restart_reapply_tries <= 0:
            return

        self._restart_reapply_tries -= 1

        self._schedule_tracks_reapply()

    def _reapply_tracks(self):
        if self._tracks_manager is None:
            self._restart_reapply_tries = 0
            return

        if self._tracks_manager.reapply():
            self._log.debug("Media restarted, tracks re-applied")
            self._restart_reapply_tries = 0

    def _apply_media_input_view(self):
        self.adjust_view(
            size=self.media_input.size,
            aspect=self.media_input.video.aspect_mode,
            scale=self.media_input.video.scale,
            crop=self.media_input.video.crop,
        )

    def _set_pause_initial(self, is_paused):
        if not self.media_input.is_live and is_paused:
            if self._media_player.get_state() != vlc.State.Paused:
                with self._event_waiter.waiting_for("paused", self.init_time_left):
                    self.set_pause(True)

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
            media_uri=self.media_input.uri,
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

        if (
            self._own_audio_count is None
            and self.media_input.selected_audio_slave is None
        ):
            # nothing was attached, so everything it has it has of its own,
            # and anything added later can be told apart from it
            self._own_audio_count = len(self._tracks_manager.audio_tracks)

        if (
            self._own_subtitle_count is None
            and not self.media_input.selected_subtitle_slaves
        ):
            self._own_subtitle_count = len(self._tracks_manager.subtitle_tracks)

        # what libVLC opened on before anything was asked of it, which is
        # the track the file itself puts forward
        default_audio_track_id = self._tracks_manager.current_audio_track_id

        # the same for subtitles. VLC turns one on by itself wherever the
        # container marks it default or forced, so this has to be read
        # before anything is asked of it -- and then, for most videos,
        # promptly switched off again just below.
        default_subtitle_track_id = self._tracks_manager.current_subtitle_track_id

        self._tracks_manager.set_video_track_id(self.media_input.video.video_track_id)
        self._tracks_manager.set_audio_track_id(self._wanted_audio_track_id())
        self._tracks_manager.set_audio_delay_ms(self.media_input.video.audio_delay_ms)

        # read once, since the choice is settled against the same list the
        # window is about to be handed
        audio_devices = self._audio_devices

        self._apply_wanted_audio_device(audio_devices)

        self._apply_wanted_subtitle_track()

        if self.media_input.video.subtitle_delay_ms:
            self._tracks_manager.set_subtitle_delay_ms(
                self.media_input.video.subtitle_delay_ms
            )

        return Media(
            length=length,
            video_tracks=self._tracks_manager.video_tracks,
            audio_tracks=self._tracks_manager.audio_tracks,
            cur_video_track_id=self._tracks_manager.current_video_track_id,
            cur_audio_track_id=self._tracks_manager.current_audio_track_id,
            external_audio_ids=self._external_audio_ids(),
            default_audio_track_id=default_audio_track_id,
            subtitle_tracks=self._tracks_manager.subtitle_tracks,
            cur_subtitle_track_id=self._tracks_manager.current_subtitle_track_id,
            external_subtitle_ids=self._external_subtitle_ids(),
            default_subtitle_track_id=default_subtitle_track_id,
            audio_devices=audio_devices,
        )

    def _fill_missing_track_dimensions(self) -> bool:
        """Copy decoded size onto tracks that have no metadata size.

        Live streams often report 0x0 in the container; video_get_size() is
        known after vout. Returns True if any track was updated.
        """
        if self.media is None or self._media_player is None:
            return False

        width, height = self._media_player.video_get_size()
        if not width or not height:
            return False

        tracks = getattr(self.media, "video_tracks", None)
        if not isinstance(tracks, dict):
            return False

        updated = False
        for track in tracks.values():
            if not all(track.video_dimensions):
                track.video_dimensions = (width, height)
                updated = True

        return updated

    def _get_duration(self):
        if self.media_input.is_live:
            return -1

        return self._media_input_vlc.get_duration() or -1


def _decode_device_field(value) -> str:
    """What libVLC wrote there, as text.

    The description is whatever the sound card's driver put in it, and a
    name that will not decode is no reason to lose the device it belongs
    to -- it is still a way out of the machine, and still pickable.
    """

    if value is None:
        return ""

    return value.decode(errors="replace")
