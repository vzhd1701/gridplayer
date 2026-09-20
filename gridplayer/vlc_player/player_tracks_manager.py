import logging
import os
import threading
from datetime import datetime, timezone

from gridplayer.vlc_player import vlc
from gridplayer.vlc_player.static import DISABLED_TRACK, AudioTrack, VideoTrack

_log = logging.getLogger(__name__)

MICROSECONDS_IN_MS = 1000


class TracksManager:
    def __init__(self, media_player, media_tracks, is_audio_only, media_uri=None):
        self._media_player = media_player
        self._media_tracks = media_tracks
        self._is_audio_only = is_audio_only
        self._media_uri = media_uri

        self._log = logging.getLogger(self.__class__.__name__)

        # the last track asked for, which is both what "switched off" means
        # here and what to ask for again after a loop; see is_video_track_off
        self._wanted_video_track_id = None
        self._wanted_audio_track_id = None

        # the head start the sound was given over the picture, which the
        # player forgets every time it opens a media; see reapply
        self._wanted_audio_delay_ms = 0

    def update_tracks(self, media_tracks) -> None:
        """Take the track list again, keeping what has been picked so far.

        An audio file attached while the video plays adds a track to a
        media that was read once at load. Only the list changes: the picks
        this manager is holding on to outlive it, since a loop wrap still
        has to put them back.
        """

        self._media_tracks = media_tracks

    @property
    def video_tracks(self) -> dict[int, VideoTrack]:
        if self._is_audio_only:
            return {}

        fallback_size = (0, 0)
        if self._media_player is not None:
            fallback_size = self._media_player.video_get_size()

        return {
            t.id: _convert_video_track(t, self._media_uri, fallback_size=fallback_size)
            for t in self._media_tracks
            if t.type == vlc.TrackType.video
        }

    @property
    def current_video_track_id(self) -> int | None:
        return self.tracks_map.get(self._media_player.video_get_track())

    @property
    def audio_tracks(self) -> dict[int, AudioTrack]:
        return {
            t.id: _convert_audio_track(t, self._media_uri)
            for t in self._media_tracks
            if t.type == vlc.TrackType.audio
        }

    @property
    def current_audio_track_id(self) -> int | None:
        return self.tracks_map.get(self._media_player.audio_get_track())

    @property
    def tracks_map(self) -> dict[int, int]:
        tracks_map = {}

        video_track_real_ids = [
            t_id for t_id, _ in self._media_player.video_get_track_description()[1:]
        ]

        tracks_map.update(dict(zip(video_track_real_ids, self.video_tracks)))

        audio_track_real_ids = [
            t_id for t_id, _ in self._media_player.audio_get_track_description()[1:]
        ]

        tracks_map.update(dict(zip(audio_track_real_ids, self.audio_tracks)))

        return tracks_map

    @property
    def is_video_size_initialized(self) -> bool:
        return self.video_tracks and all(self._media_player.video_get_size())

    @property
    def is_video_track_off(self) -> bool:
        """Whether the picture has been switched off.

        Not a question libVLC can answer. ``video_get_track`` replies -1
        both for a track that was disabled and for one it has lost track
        of, which an adaptive stream causes routinely: restarting its
        elementary streams renumbers them, and from then on the player
        reports -1 for a picture it is still happily rendering. Only what
        we switched off ourselves is worth going by.
        """

        return self._wanted_video_track_id == DISABLED_TRACK or not self.video_tracks

    @property
    def is_audio_track_off(self) -> bool:
        """Whether the sound has been switched off. See is_video_track_off."""

        return self._wanted_audio_track_id == DISABLED_TRACK or not self.audio_tracks

    def set_audio_track_id(self, track_id) -> None:
        real_track_id = self._get_real_track_id(track_id)

        if real_track_id is None:
            return

        if real_track_id == DISABLED_TRACK and self.is_video_track_off:
            self._log.warning("Cannot disable both audio & video tracks")
            return

        self._log.debug(f"Set audio track {track_id} [{real_track_id}]")
        self._media_player.audio_set_track(real_track_id)

        self._wanted_audio_track_id = track_id

    def set_video_track_id(self, track_id) -> None:
        real_track_id = self._get_real_track_id(track_id)

        if real_track_id is None:
            return

        if real_track_id == DISABLED_TRACK and self.is_audio_track_off:
            self._log.warning("Cannot disable both audio & video tracks")
            return

        self._log.debug(f"Set video track {track_id} [{real_track_id}]")
        self._media_player.video_set_track(real_track_id)

        self._wanted_video_track_id = track_id

    def set_audio_delay_ms(self, delay_ms: int) -> None:
        """Move the sound against the picture, by milliseconds, later positive.

        libVLC counts in microseconds and drops the whole thing whenever it
        opens a media, which is why what was asked for is kept here.
        """

        self._log.debug(f"Set audio delay {delay_ms} ms")

        is_set = self._media_player.audio_set_delay(delay_ms * MICROSECONDS_IN_MS) == 0

        if delay_ms and not is_set:
            # most likely nothing is playing for the sound to be moved
            # against; what was asked for is kept all the same, and the
            # next pass to start is asked again
            self._log.warning(f"Failed to set audio delay {delay_ms} ms")

        self._wanted_audio_delay_ms = delay_ms

    def reapply(self) -> bool:
        """Ask for the chosen tracks again after the player restarted.

        Looping replays the media from the top, and libVLC starts it the
        way it would any other time: on whichever tracks it considers the
        defaults, with the sound back level with the picture. Anything
        picked since the media was loaded, a disabled audio track above
        all, has to be asked for again.

        Returns whether the sound has landed where it was asked to be.
        The restart takes a moment, and asking too early only reaches the
        input that is on its way out, so the caller tries again.
        """

        is_nothing_wanted = (
            self._wanted_audio_track_id is None
            and self._wanted_video_track_id is None
            and not self._wanted_audio_delay_ms
        )

        if is_nothing_wanted:
            # nothing was ever picked, so the defaults it comes back on
            # are the right ones
            return True

        if not self._is_new_pass_ready:
            return False

        if self._wanted_video_track_id is not None:
            self.set_video_track_id(self._wanted_video_track_id)

        if self._wanted_audio_track_id is not None:
            self.set_audio_track_id(self._wanted_audio_track_id)

        # after the track, since which track is playing is the one thing a
        # delay is measured against
        if self._wanted_audio_delay_ms:
            self.set_audio_delay_ms(self._wanted_audio_delay_ms)

        if self._wanted_audio_track_id is None:
            return True

        real_track_id = self._get_real_track_id(self._wanted_audio_track_id)

        return (
            real_track_id is not None
            and self._media_player.audio_get_track() == real_track_id
        )

    @property
    def _is_new_pass_ready(self) -> bool:
        """Whether the player is answering for the pass that is now running.

        Between the two it reports the selection the old one had and no
        tracks at all, so anything set then looks as though it took and
        the new pass starts on the defaults regardless.
        """

        # [1:] drops the "Disable" entry libVLC puts in front, the same way
        # the id map does; what is left is the tracks the pass really has
        return bool(
            self._media_player.audio_get_track_description()[1:]
            or self._media_player.video_get_track_description()[1:]
        )

    def _get_real_track_id(self, track_id) -> int | None:
        if track_id == -1:
            return -1

        try:
            return next(
                real_id
                for real_id, inner_id in self.tracks_map.items()
                if inner_id == track_id
            )
        except StopIteration:
            return None


def _decode_track_field(
    value, *, media_uri, track_type, track_id, field_name, default=None
):
    """Decode a libVLC track metadata field (ctypes ``c_char_p``) into text.

    libVLC hands this back as raw bytes copied straight out of the
    container's own metadata (track name/language tag), with no guarantee
    it's valid UTF-8 -- some muxers write it in a local codepage instead.
    A single mangled tag must not take down the whole player process, so
    invalid bytes are replaced rather than left to raise.
    """
    if value is None:
        return default

    if isinstance(value, str):
        return value

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            _log.warning(
                "Invalid UTF-8 in %s track #%s field %r (media=%r, pid=%s, tid=%s, "
                "at=%s): %r (%s) -- using replacement characters",
                track_type,
                track_id,
                field_name,
                media_uri,
                os.getpid(),
                threading.get_ident(),
                datetime.now(timezone.utc).isoformat(),
                value,
                exc,
            )
            return value.decode("utf-8", errors="replace")

    _log.error(
        "Unexpected type for %s track #%s field %r (media=%r): %s %r",
        track_type,
        track_id,
        field_name,
        media_uri,
        type(value),
        value,
    )
    return default


def _convert_video_track(video_track, media_uri=None, fallback_size=(0, 0)):
    vt_content = video_track.u.video.contents

    if all([vt_content.frame_rate_num, vt_content.frame_rate_den]):
        fps = round(vt_content.frame_rate_num / vt_content.frame_rate_den, 3)
    else:
        fps = None

    track_kwargs = {
        "media_uri": media_uri,
        "track_type": "video",
        "track_id": video_track.id,
    }

    width, height = vt_content.width, vt_content.height
    if not (width and height) and all(fallback_size):
        width, height = fallback_size

    return VideoTrack(
        video_dimensions=(width, height),
        fps=fps,
        bitrate=video_track.bitrate,
        language=_decode_track_field(
            video_track.language, field_name="language", **track_kwargs
        ),
        description=_decode_track_field(
            video_track.description, field_name="description", **track_kwargs
        ),
        codec=_decode_track_field(
            vlc.libvlc_media_get_codec_description(video_track.type, video_track.codec),
            field_name="codec",
            default="",
            **track_kwargs,
        ),
    )


def _convert_audio_track(audio_track, media_uri=None):
    at_content = audio_track.u.audio.contents

    track_kwargs = {
        "media_uri": media_uri,
        "track_type": "audio",
        "track_id": audio_track.id,
    }

    return AudioTrack(
        channels=at_content.channels,
        rate=at_content.rate,
        bitrate=audio_track.bitrate,
        language=_decode_track_field(
            audio_track.language, field_name="language", **track_kwargs
        ),
        description=_decode_track_field(
            audio_track.description, field_name="description", **track_kwargs
        ),
        codec=_decode_track_field(
            vlc.libvlc_media_get_codec_description(audio_track.type, audio_track.codec),
            field_name="codec",
            default="",
            **track_kwargs,
        ),
    )
