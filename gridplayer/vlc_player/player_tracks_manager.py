import logging

from gridplayer.vlc_player import vlc
from gridplayer.vlc_player.static import NO_TRACK, AudioTrack, VideoTrack


class TracksManager:
    def __init__(self, media_player, media_tracks, is_audio_only):
        self._media_player = media_player
        self._media_tracks = media_tracks
        self._is_audio_only = is_audio_only

        self._log = logging.getLogger(self.__class__.__name__)

    @property
    def video_tracks(self) -> dict[int, VideoTrack]:
        if self._is_audio_only:
            return {}

        return {
            t.id: _convert_video_track(t)
            for t in self._media_tracks
            if t.type == vlc.TrackType.video
        }

    @property
    def current_video_track_id(self) -> int | None:
        return self.tracks_map.get(self._media_player.video_get_track())

    @property
    def audio_tracks(self) -> dict[int, AudioTrack]:
        return {
            t.id: _convert_audio_track(t)
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


def _convert_video_track(video_track):
    vt_content = video_track.u.video.contents

    if all([vt_content.frame_rate_num, vt_content.frame_rate_den]):
        fps = round(vt_content.frame_rate_num / vt_content.frame_rate_den, 3)
    else:
        fps = None

    return VideoTrack(
        video_dimensions=(vt_content.width, vt_content.height),
        fps=fps,
        bitrate=video_track.bitrate,
        language=video_track.language.decode("utf-8") if video_track.language else None,
        description=(
            video_track.description.decode("utf-8") if video_track.description else None
        ),
        codec=vlc.libvlc_media_get_codec_description(
            video_track.type, video_track.codec
        ).decode("utf-8"),
    )


def _convert_audio_track(audio_track):
    at_content = audio_track.u.audio.contents

    return AudioTrack(
        channels=at_content.channels,
        rate=at_content.rate,
        bitrate=audio_track.bitrate,
        language=audio_track.language.decode("utf-8") if audio_track.language else None,
        description=(
            audio_track.description.decode("utf-8") if audio_track.description else None
        ),
        codec=vlc.libvlc_media_get_codec_description(
            audio_track.type, audio_track.codec
        ).decode("utf-8"),
    )
