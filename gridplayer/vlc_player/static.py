import random
from dataclasses import dataclass, field

from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioLanguage,
    AudioTrackId,
)
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleDisabled,
    SubtitleLanguage,
    SubtitleTrackId,
)
from gridplayer.models.video import Video
from gridplayer.utils.track_language import pick_track

DISABLED_TRACK = -1
NO_TRACK = frozenset((None, DISABLED_TRACK))

# How much of the video the time has to give up at once to count as a finished
# pass. A stream reports its time a few ms backwards now and then all on its
# own, and an eighth of the length sits far above that and far below what
# starting over really hands back.
LOOP_WRAP_DROP_FRACTION = 8


def is_loop_wrapped(last_time: int | None, new_time: int, length: int) -> bool:
    """Whether the time falling this far back means another pass has begun.

    A pass that came to an end leaves no event behind: VLC loops the input
    without ending the media, and where the media does end and the item is
    played again, that is the player's own business. What both have in common
    is the time dropping back to the beginning.
    """

    if last_time is None or length <= 0:
        return False

    return last_time - new_time > length / LOOP_WRAP_DROP_FRACTION


def wanted_audio_track_id(video, tracks: dict):
    """Which of these tracks a video's settings call for, None for any.

    Both the load and a switch made while playing have to answer this the
    same way, or the track would change under the viewer the next time
    anything reloaded. A pick of a file of the video's own is not answered
    here: only whoever knows which track each file brought can answer it.

    A pick that these tracks cannot honour -- a language this source does
    not carry, an id it no longer has -- falls back to the preference,
    which is what the viewer would be left with had they picked nothing.
    """

    selection = video.audio_selection

    if isinstance(selection, AudioDisabled):
        return DISABLED_TRACK

    if isinstance(selection, AudioDefault):
        # nothing is asked of libVLC, so it opens on whichever track the
        # file itself puts forward
        return None

    if isinstance(selection, AudioLanguage):
        picked = pick_track(selection.tag, tracks)

        if picked is not None:
            return picked

    if isinstance(selection, AudioTrackId) and selection.id in tracks:
        return selection.id

    return pick_track(video.audio_languages, tracks)


def wanted_subtitle_track_id(video, tracks: dict, external_ids=()):
    """Which of these tracks a video's settings call for, None to leave be.

    Where the sound gives up and takes whatever it can get, this gives up
    and shows nothing: a track in a language nobody asked for is worse than
    a bare picture, which is not true of a sound track nobody asked for.

    Tracks a file of their own brought are kept out of the language
    matching. libVLC writes that file's name where an embedded track's
    language goes, so matching against them is matching against a path.
    A pick of one is not answered here at all: only whoever knows which
    track came out of which file can answer that.
    """

    selection = video.subtitle_selection

    if isinstance(selection, SubtitleDisabled):
        return DISABLED_TRACK

    if isinstance(selection, SubtitleDefault):
        # nothing is asked of libVLC, so what it opened on stands, and that
        # is whichever track the container marks
        return None

    if isinstance(selection, SubtitleTrackId) and selection.id in tracks:
        return selection.id

    own_tracks = {
        track_id: track
        for track_id, track in tracks.items()
        if track_id not in external_ids
    }

    if isinstance(selection, SubtitleLanguage):
        picked = pick_track(selection.tag, own_tracks)

        if picked is not None:
            return picked

    picked = pick_track(video.subtitle_languages, own_tracks)

    return DISABLED_TRACK if picked is None else picked


@dataclass
class MediaTrack:
    codec: str
    bitrate: int
    language: str | None
    description: str | None

    @property
    def codec_info(self):
        info = [self.codec]

        if self.bitrate:
            info += [f"{self.bitrate // 1024} kbps"]

        return ", ".join(info)

    @property
    def info(self):
        info = [self.codec_info]

        if self.language and self.description:
            info += [f"{self.language} ({self.description})"]
        else:
            if self.language:
                info += [f"{self.language}"]

            if self.description:
                info += [f"{self.description}"]

        return ", ".join(info)


@dataclass
class VideoTrack(MediaTrack):
    video_dimensions: tuple[int, int]
    fps: float | None

    @property
    def codec_info(self):
        info = [self.codec]

        if all(self.video_dimensions):
            info += ["{}x{}".format(*self.video_dimensions)]

        if self.fps:
            info += [f"{self.fps} FPS"]

        if self.bitrate:
            info += [f"{self.bitrate // 1024} kbps"]

        return ", ".join(info)


@dataclass
class AudioTrack(MediaTrack):
    channels: int
    rate: int

    @property
    def codec_info(self):
        info = [self.codec]

        if self.channels:
            info += [f"{self.channels} ch"]

        if self.rate:
            info += [f"{self.rate // 1000} kHz"]

        if self.bitrate:
            info += [f"{self.bitrate // 1024} kbps"]

        return ", ".join(info)


@dataclass
class SubtitleTrack(MediaTrack):
    """One subtitle track, whether the video carried it or a file brought it.

    ``bitrate`` is nothing here -- libVLC reports zero for every subtitle
    track -- so the codec and the encoding are all there is to show.
    """

    encoding: str | None = None

    @property
    def codec_info(self):
        info = [self.codec]

        if self.encoding:
            info += [self.encoding]

        return ", ".join(info)


@dataclass
class Media:
    length: int

    video_tracks: dict[int, VideoTrack]
    audio_tracks: dict[int, AudioTrack]

    cur_audio_track_id: int | None = None
    cur_video_track_id: int | None = None

    # the tracks that came out of the file attached to this video, in the
    # order libVLC put them in
    external_audio_ids: tuple[int, ...] = ()

    # the track libVLC opened on before anything was asked of it, which is
    # the one the file itself puts forward
    default_audio_track_id: int | None = None

    # Subtitles. Defaulted, unlike the picture and the sound, since a media
    # that has none is the ordinary case rather than a broken one.
    subtitle_tracks: dict[int, SubtitleTrack] = field(default_factory=dict)
    cur_subtitle_track_id: int | None = None

    # the tracks the subtitle files brought, in the order they were opened
    external_subtitle_ids: tuple[int, ...] = ()

    # the track libVLC would have shown had it been left alone, which is
    # the one the container marks default or forced
    default_subtitle_track_id: int | None = None

    @property
    def is_live(self) -> bool:
        return self.length == -1

    @property
    def is_audio_only(self) -> bool:
        return not self.video_tracks or self.cur_video_track_id == DISABLED_TRACK

    @property
    def cur_video_track(self):
        if self.cur_video_track_id in NO_TRACK:
            return None
        return self.video_tracks[self.cur_video_track_id]

    @property
    def cur_audio_track(self):
        if self.cur_audio_track_id in NO_TRACK:
            return None
        return self.audio_tracks[self.cur_audio_track_id]

    @property
    def cur_subtitle_track(self):
        if self.cur_subtitle_track_id in NO_TRACK:
            return None
        return self.subtitle_tracks.get(self.cur_subtitle_track_id)

    @property
    def has_subtitles(self) -> bool:
        """Whether there is anything to show, picture to show it on included.

        A track with the video switched off has nowhere to be drawn: VLC
        blends subtitles into the picture, and without one there is no
        video output to blend into.
        """

        return bool(self.subtitle_tracks) and not self.is_audio_only


@dataclass
class MediaInput:
    uri: str
    is_live: bool
    is_audio_only: bool
    size: tuple[int, int]
    video: Video

    video_codec: str | None = None
    is_adaptive: bool = False
    length: int | None = None

    # the audio file to open along with the video, where one was picked.
    # Only ever one: libVLC never says which stream came from which file,
    # so a second would leave the two of them to be told apart by guesswork.
    selected_audio_slave: str | None = None

    # the subtitle files to open along with the video, in the order they
    # were picked. Several is allowed here where audio gets one: libVLC
    # opens each as a track of its own and writes the file's name into the
    # track description, so which came from where is never in doubt.
    selected_subtitle_slaves: tuple[str, ...] = ()

    _initial_seek_ms: int | None = None

    @property
    def initial_time(self) -> int:
        if self._initial_seek_ms is None:
            is_video_start = self.video.current_position == 0

            if not self.is_live and is_video_start and self.video.is_start_random:
                self._initial_seek_ms = self._get_random_position()
            else:
                self._initial_seek_ms = self.video.current_position

        return self._initial_seek_ms

    @initial_time.setter
    def initial_time(self, initial_seek_ms: int):
        self._initial_seek_ms = initial_seek_ms

    def _get_random_position(self) -> int:
        if self.length is None:
            raise ValueError("Length is not set")

        loop_start = self.video.loop_start or 0
        loop_end = self.video.loop_end or self.length

        return random.randint(loop_start, loop_end)


class NotPausedError(Exception):
    """Exception risen when video didn't pause at the beginning"""
