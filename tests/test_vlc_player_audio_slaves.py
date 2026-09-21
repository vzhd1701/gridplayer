"""Handing libVLC the audio files a video is to be played with."""

from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.settings import Settings
from gridplayer.vlc_player import vlc
from gridplayer.vlc_player.player_base import SLAVE_PRIORITY, VlcPlayerBase
from gridplayer.vlc_player.static import AudioTrack, Media, MediaInput

URI = "http://example.com/a.mp4"

FIRST = "file:///audio/Movie.rus.mp3"
SECOND = "file:///audio/Movie.fra.mp3"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


class _MinimalPlayer(VlcPlayerBase):
    """Concrete VlcPlayerBase with the abstractmethods stubbed as no-ops."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.tracks_changes = []

    def notify_snapshot_taken(self, snapshot_path): ...
    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...

    def notify_tracks_changed(self, media_track):
        self.tracks_changes.append(media_track)


class _FakeEventManager:
    def event_attach(self, event_type, callback): ...


class _FakeTrack:
    def __init__(self, track_type, track_id):
        self.type = track_type
        self.id = track_id


class _FakeMedia:
    def __init__(self, tracks=()):
        self.options = []
        self.slaves = []
        self.tracks = list(tracks)
        self.parses = 0

    def parse_with_options(self, parse_flag, timeout):
        self.parses += 1

    def event_manager(self):
        return _FakeEventManager()

    def add_options(self, *options):
        self.options.extend(options)

    def slaves_add(self, slave_type, priority, uri):
        self.slaves.append((slave_type, priority, uri))
        return 0

    def tracks_get(self):
        return list(self.tracks)


class _FakeInstance:
    def __init__(self, media):
        self._media = media

    def media_new(self, uri):
        return self._media

    def media_new_path(self, uri):
        return self._media


class _FakeMediaPlayer:
    def __init__(self, failing=()):
        self.slaves = []
        self._failing = set(failing)

    def add_slave(self, slave_type, uri, is_select):
        self.slaves.append((slave_type, uri, is_select))

        return -1 if uri in self._failing else 0


class _FakeTracksManager:
    def __init__(self, audio_tracks):
        self.updated = []
        self._audio_tracks = audio_tracks
        self.video_tracks = {}
        self.current_video_track_id = None
        self.current_audio_track_id = 1
        self.subtitle_tracks = {}
        self.current_subtitle_track_id = None

    @property
    def audio_tracks(self):
        return self._audio_tracks

    def update_tracks(self, media_tracks):
        self.updated.append(media_tracks)

    def set_subtitle_track_id(self, track_id):
        self.current_subtitle_track_id = track_id


def _media_input(audio_slave=None):
    return MediaInput(
        uri=URI,
        is_live=False,
        is_audio_only=False,
        size=(640, 360),
        video=Video(uri=URI),
        selected_audio_slave=audio_slave,
    )


def _track():
    return AudioTrack(
        codec="mp4a",
        bitrate=131072,
        language=None,
        description=None,
        channels=2,
        rate=48000,
    )


def _parse_event(status):
    return SimpleNamespace(u=SimpleNamespace(new_status=status))


def _load(audio_slave=None, tracks=(), parse_status=vlc.MediaParsedStatus.done):
    """Load a video the way the pipeline does, parse step and all."""

    media = _FakeMedia(tracks)
    player = _MinimalPlayer(vlc_instance=_FakeInstance(media))
    player._media_player = _FakeMediaPlayer()

    player.load_video(_media_input(audio_slave))

    if media.parses:
        player.cb_parse_changed(_parse_event(parse_status))

    return media, player


def _loaded_media(audio_slave=None):
    media, _ = _load(audio_slave)

    return media


def _playing_player(media, audio_tracks=None, failing=()):
    audio_tracks = {0: _track()} if audio_tracks is None else audio_tracks

    player = _MinimalPlayer(vlc_instance=_FakeInstance(media))

    player.is_video_initialized = True
    player._media_player = _FakeMediaPlayer(failing)
    player._media_input_vlc = media
    player._tracks_manager = _FakeTracksManager(audio_tracks)
    player.media_input = _media_input()
    player.media = Media(length=10000, video_tracks={}, audio_tracks=audio_tracks)

    return player


def _audio_tracks(count):
    return [_FakeTrack(vlc.TrackType.audio, index + 1) for index in range(count)]


def _container(audio=1, subtitles=0):
    """A file's own streams, numbered the way libVLC numbers them."""

    tracks = [_FakeTrack(vlc.TrackType.video, 0)]
    tracks += [_FakeTrack(vlc.TrackType.audio, index + 1) for index in range(audio)]
    tracks += [
        _FakeTrack(vlc.TrackType.ext, audio + index + 1) for index in range(subtitles)
    ]

    return tracks


def _slave_audio(container, count=1):
    """What a file attached to it brings, at the end of the list."""

    return [
        _FakeTrack(vlc.TrackType.audio, len(container) + index)
        for index in range(count)
    ]


class TestOpeningThemWithTheVideo:
    def test_a_video_with_none_of_them_gets_none(self):
        assert _loaded_media().slaves == []

    def test_a_video_with_none_of_them_is_not_parsed_either(self):
        """The parse is only there to count what the file has of its own."""

        media, _ = _load()

        assert media.parses == 0

    def test_a_video_with_one_is_read_before_it_goes_on(self):
        media, _ = _load(FIRST, tracks=_container(audio=2))

        assert media.parses == 1

    def test_reading_it_is_what_tells_its_own_tracks_apart(self):
        _, player = _load(FIRST, tracks=_container(audio=4, subtitles=2))

        assert player._own_audio_count == 4

    def test_a_video_that_will_not_read_still_gets_it(self):
        """It only loses the ability to say which track came from where."""

        media, player = _load(FIRST, parse_status=vlc.MediaParsedStatus.failed)

        assert player._own_audio_count is None
        assert media.slaves == [(vlc.MediaSlaveType.audio, SLAVE_PRIORITY, FIRST)]

    def test_the_chosen_one_goes_on_as_audio(self):
        media = _loaded_media(FIRST)

        assert media.slaves == [(vlc.MediaSlaveType.audio, SLAVE_PRIORITY, FIRST)]

    def test_only_ever_one_of_them(self):
        """libVLC never says which stream came from which file."""

        media = _loaded_media(FIRST)

        assert len(media.slaves) == 1


class TestAddingOneToAVideoAlreadyPlaying:
    def test_it_goes_on_as_audio_and_is_played(self):
        media = _FakeMedia(_audio_tracks(2))
        player = _playing_player(media)

        player.add_audio_slave(FIRST)

        assert player._media_player.slaves == [(vlc.MediaSlaveType.audio, FIRST, True)]

    def test_it_becomes_the_file_the_video_is_playing_with(self):
        """What a later load has to open it with again."""

        media = _FakeMedia(_audio_tracks(2))
        player = _playing_player(media)

        player.add_audio_slave(FIRST)

        assert player.media_input.selected_audio_slave == FIRST

    def test_the_track_list_is_taken_again_once_the_track_is_there(self):
        media = _FakeMedia(_audio_tracks(2))
        player = _playing_player(media)

        player.add_audio_slave(FIRST)

        assert player._tracks_manager.updated == [media.tracks]
        assert len(player.tracks_changes) == 1

    def test_the_new_list_is_the_one_handed_on(self):
        media = _FakeMedia(_audio_tracks(2))
        player = _playing_player(media)

        player.add_audio_slave(FIRST)

        assert player.tracks_changes[0].cur_audio_track_id == 1
        assert player.media.cur_audio_track_id == 1

    def test_a_track_that_has_not_arrived_is_waited_for(self, mocker):
        """VLC opens a file in its own time, so there is nothing else to do."""

        waits = mocker.patch("gridplayer.vlc_player.player_base.async_wait")
        media = _FakeMedia(_audio_tracks(1))
        player = _playing_player(media)

        player.add_audio_slave(FIRST)

        waits.assert_called_once()
        assert player.tracks_changes == []

    def test_one_libvlc_would_not_take_changes_nothing(self, mocker):
        """Nothing was added, so there is nothing to wait for or announce."""

        waits = mocker.patch("gridplayer.vlc_player.player_base.async_wait")
        media = _FakeMedia(_audio_tracks(1))
        player = _playing_player(media, failing=[FIRST])

        player.add_audio_slave(FIRST)

        waits.assert_not_called()
        assert player.tracks_changes == []

    def test_a_video_that_is_not_loaded_yet_takes_none(self):
        media = _FakeMedia(_audio_tracks(2))
        player = _playing_player(media)
        player.media = None

        player.add_audio_slave(FIRST)

        assert player._media_player.slaves == []

    def test_one_that_would_not_open_is_not_taken_as_what_is_playing(self):
        media = _FakeMedia(_audio_tracks(1))
        player = _playing_player(media, failing=[FIRST])

        player.add_audio_slave(FIRST)

        assert player.media_input.selected_audio_slave is None

    def test_a_player_released_mid_wait_asks_nothing_more(self):
        """The player goes before the media does, and the wait outlives both."""

        media = _FakeMedia(_audio_tracks(1))
        player = _playing_player(media)
        player._media_player = None

        player._await_audio_slave_track(2, 0)

        assert player.tracks_changes == []


class TestWhichTrackCameFromTheFile:
    """libVLC will not say, so the player counts before and reads after."""

    def _player(self, own_count, audio_track_ids):
        player = _MinimalPlayer(vlc_instance=None)
        player.media_input = _media_input(FIRST)
        player._own_audio_count = own_count
        player._tracks_manager = _FakeTracksManager(
            {track_id: _track() for track_id in audio_track_ids}
        )

        return player

    def test_the_one_past_the_video_s_own_came_from_the_file(self):
        player = self._player(4, [1, 2, 3, 4, 7])

        assert player._external_audio_ids() == (7,)

    def test_a_track_of_the_video_s_own_is_never_taken_for_it(self):
        """A file that brought nothing must not cost the last built-in track."""

        player = self._player(4, [1, 2, 3, 4])

        assert player._external_audio_ids() == ()

    def test_a_file_bringing_two_tracks_is_credited_with_both(self):
        """With one file attached there is nothing left to tell apart."""

        player = self._player(4, [1, 2, 3, 4, 7, 8])

        assert player._external_audio_ids() == (7, 8)

    def test_a_video_that_could_not_be_read_claims_nothing(self):
        player = self._player(None, [1, 2, 3, 4, 7])

        assert player._external_audio_ids() == ()

    def test_a_video_playing_only_its_own_has_none_of_it(self):
        player = self._player(2, [1, 2])

        assert player._external_audio_ids() == ()
