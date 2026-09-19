from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.settings import Settings
from gridplayer.vlc_player.player_base import (
    INPUT_REPEAT_FOREVER,
    RESTART_REAPPLY_TRIES,
    VlcPlayerBase,
)
from gridplayer.vlc_player.static import Media, MediaInput

URI = "http://example.com/a.mp4"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


class _MinimalPlayer(VlcPlayerBase):
    """Concrete VlcPlayerBase with the abstractmethods stubbed as no-ops."""

    def notify_snapshot_taken(self, snapshot_path): ...
    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _FakeEventManager:
    def event_attach(self, event_type, callback): ...


class _FakeMedia:
    def __init__(self):
        self.options = []

    def event_manager(self):
        return _FakeEventManager()

    def add_options(self, *options):
        self.options.extend(options)


class _FakeInstance:
    def __init__(self, media):
        self._media = media

    def media_new(self, uri):
        return self._media

    def media_new_path(self, uri):
        return self._media


class _FakeMediaPlayer:
    def __init__(self):
        self.times = []

    def set_time(self, seek_ms):
        self.times.append(seek_ms)


def _media_input(is_live, is_adaptive=False):
    return MediaInput(
        uri=URI,
        is_live=is_live,
        is_audio_only=False,
        is_adaptive=is_adaptive,
        size=(640, 360),
        video=Video(uri=URI),
    )


def _loaded_media(is_live, is_adaptive=False):
    media = _FakeMedia()
    player = _MinimalPlayer(vlc_instance=_FakeInstance(media))

    player.load_video(_media_input(is_live, is_adaptive))

    return media


def _seeking_player(length, is_live=False, is_adaptive=False):
    player = _MinimalPlayer(vlc_instance=None)

    player.is_video_initialized = True
    player._media_player = _FakeMediaPlayer()
    player._tracks_manager = _FakeTracksManager()
    player.media_input = _media_input(is_live, is_adaptive)
    player.media = Media(length=length, video_tracks={}, audio_tracks={})

    return player


def test_seekable_media_loops_in_place():
    """VLC wraps the input around itself, no restart and nothing cut off."""
    media = _loaded_media(is_live=False)

    assert f":input-repeat={INPUT_REPEAT_FOREVER}" in media.options


def test_live_media_is_not_repeated():
    media = _loaded_media(is_live=True)

    assert not [opt for opt in media.options if opt.startswith(":input-repeat")]


def test_adaptive_media_loops_in_place_too():
    """It renumbers its streams on the wrap, which the re-apply answers."""
    media = _loaded_media(is_live=False, is_adaptive=True)

    assert f":input-repeat={INPUT_REPEAT_FOREVER}" in media.options


class _FakeTracksManager:
    def __init__(self, is_ready=True):
        self.is_ready = is_ready
        self.reapplied = 0

    def reapply(self):
        self.reapplied += 1
        return self.is_ready


def _playing_player(length=10000, last_time=None):
    player = _MinimalPlayer(vlc_instance=None)

    player.is_video_initialized = True
    player.media_input = _media_input(is_live=False, is_adaptive=True)
    player.media = Media(length=length, video_tracks={1: object()}, audio_tracks={})
    player._tracks_manager = _FakeTracksManager()
    player._last_time = last_time

    return player


def _time_event(new_time):
    return SimpleNamespace(u=SimpleNamespace(new_time=new_time))


def test_video_output_rebuilt_puts_tracks_back():
    """A restarted decoder renumbers the streams, and nothing else says so."""
    player = _playing_player()

    player.cb_vout(None)

    assert player._tracks_manager.reapplied == 1


def test_video_output_at_load_is_not_a_restart():
    player = _playing_player()
    player.is_video_initialized = False

    player.cb_vout(None)

    assert player._tracks_manager.reapplied == 0


def test_wrap_puts_tracks_back_without_a_picture():
    """Audio only has no video output to go by, only the time falling back."""
    player = _playing_player(last_time=9655)

    player.cb_time_changed(_time_event(401))

    assert player._tracks_manager.reapplied == 1


def test_plain_media_keeps_its_tracks_across_a_wrap():
    """Nothing was renumbered, and asking again would flush the sound."""
    player = _playing_player(last_time=9655)
    player.media_input = _media_input(is_live=False, is_adaptive=False)

    player.cb_time_changed(_time_event(401))
    player.cb_vout(None)

    assert player._tracks_manager.reapplied == 0


def test_time_jitter_leaves_tracks_alone():
    player = _playing_player(last_time=2318)

    player.cb_time_changed(_time_event(2317))

    assert player._tracks_manager.reapplied == 0
    assert player._last_time == 2317


def test_short_video_is_seekable():
    """Every seek in a 400ms video used to be dropped by the 500ms margin."""
    player = _seeking_player(400)

    player.set_time(0)
    player.set_time(250)

    assert player._media_player.times == [0, 250]


def test_seek_past_the_end_is_clamped():
    player = _seeking_player(400)

    player.set_time(600)

    assert player._media_player.times == [399]


def test_seek_before_the_start_is_clamped():
    player = _seeking_player(2000)

    player.set_time(-100)

    assert player._media_player.times == [0]


def test_seek_with_unknown_length_is_left_alone():
    player = _seeking_player(0)

    player.set_time(250)

    assert player._media_player.times == [250]


def test_live_seek_is_ignored():
    player = _seeking_player(2000, is_live=True)

    player.set_time(100)

    assert player._media_player.times == []


def test_adaptive_seek_puts_tracks_back():
    """The viewer dragging the bar renumbers the streams just as a wrap does."""
    player = _seeking_player(30000, is_adaptive=True)

    player.set_time(21000)

    assert player._restart_reapply_tries == RESTART_REAPPLY_TRIES


def test_seek_without_a_picture_puts_tracks_back():
    """Audio only has nothing else to go by.

    There is no video output to announce the restart, and a seek forward
    leaves the time no lower than it found it, so the wrap check sees
    nothing either.
    """
    player = _seeking_player(30000, is_adaptive=True)
    player.media = Media(length=30000, video_tracks={}, audio_tracks={1: object()})

    player.set_time(21000)

    assert player._restart_reapply_tries == RESTART_REAPPLY_TRIES


def test_plain_seek_leaves_tracks_alone():
    """A plain seek comes back on the tracks it left on."""
    player = _seeking_player(30000)

    player.set_time(21000)

    assert player._restart_reapply_tries == 0
