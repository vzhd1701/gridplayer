import logging
import os
import threading
from datetime import datetime, timezone

from gridplayer.vlc_player import vlc
from gridplayer.vlc_player.static import NO_TRACK, AudioTrack, VideoTrack

_log = logging.getLogger(__name__)


class TracksManager:
    def __init__(self, media_player, media_tracks, is_audio_only, media_uri=None):
        self._media_player = media_player
        self._media_tracks = media_tracks
        self._is_audio_only = is_audio_only
        self._media_uri = media_uri

        self._log = logging.getLogger(self.__class__.__name__)

    @property
    def video_tracks(self) -> dict[int, VideoTrack]:
        if self._is_audio_only:
            return {}

        return {
            t.id: _convert_video_track(t, self._media_uri)
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

    def set_audio_track_id(self, track_id) -> None:
        real_track_id = self._get_real_track_id(track_id)

        if real_track_id is None:
            return

        if real_track_id == -1 and self.current_video_track_id in NO_TRACK:
            self._log.warning("Cannot disable both audio & video tracks")
            return

        self._log.debug(f"Set audio track {track_id} [{real_track_id}]")
        self._media_player.audio_set_track(real_track_id)

    def set_video_track_id(self, track_id) -> None:
        real_track_id = self._get_real_track_id(track_id)

        if real_track_id is None:
            return

        if real_track_id == -1 and self.current_audio_track_id in NO_TRACK:
            self._log.warning("Cannot disable both audio & video tracks")
            return

        self._log.debug(f"Set video track {track_id} [{real_track_id}]")
        self._media_player.video_set_track(real_track_id)

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


def _convert_video_track(video_track, media_uri=None):
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

    return VideoTrack(
        video_dimensions=(vt_content.width, vt_content.height),
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
