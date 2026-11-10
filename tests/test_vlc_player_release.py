"""What a VLC player lets go of. Each video and video list libVLC makes holds
the instance it was made by: one kept keeps the instance, its threads and its
memory, after the instance itself is released. And vlc.py keeps every object
whose events were asked for, with all that is called back."""

import gc
import weakref
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.settings import Settings
from gridplayer.vlc_player import vlc
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import MediaInput

URI = "/videos/a.mp4"


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


class _Player(VlcPlayerBase):
    def notify_snapshot_taken(self, snapshot_path): ...
    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error, vlc_lines=()): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _Released:
    """Something of libVLC's, which says when it is let go of."""

    def __init__(self, name, released):
        self.name = name
        self._released = released

    def release(self):
        self._released.append(self.name)

    # as vlc.py has it
    @vlc.memoize_parameterless
    def event_manager(self):
        return Mock()


class _Media(_Released):
    def add_options(self, *options): ...


class _MediaList(_Released):
    def add_media(self, media): ...


class _ListPlayer(_Released):
    def set_media_list(self, media_list): ...

    def play_item_at_index(self, index): ...


class _Instance:
    def __init__(self, released):
        self._released = released
        self._made = 0

    def media_new_path(self, uri):
        self._made += 1
        return _Media(f"media {self._made}", self._released)

    def media_list_new(self):
        return _MediaList("list", self._released)


def _media_input():
    return MediaInput(
        uri=URI,
        is_live=False,
        is_audio_only=False,
        size=(640, 360),
        video=Video(uri=URI),
    )


@pytest.fixture
def released():
    return []


@pytest.fixture
def player(released):
    player = _Player(vlc_instance=_Instance(released))

    player._event_waiter = Mock()
    player._playlist_player = _ListPlayer("list player", released)
    player._media_player = _Released("media player", released)

    return player


def test_a_played_video_and_its_list_are_released_after_the_players(player, released):
    player.load_video(_media_input())
    player.load_video_st2_set_media()

    player.cleanup()

    assert released == ["list player", "media player", "list", "media 1"]


def test_a_video_never_played_is_released(player, released):
    player.load_video(_media_input())

    player.cleanup()

    assert released == ["list player", "media player", "media 1"]


def test_loading_again_releases_the_video_before(player, released):
    player.load_video(_media_input())
    player.load_video(_media_input())

    assert released == ["media 1"]

    player.cleanup()

    assert released[-1] == "media 2"


def test_nothing_loaded_releases_only_the_players(player, released):
    player.cleanup()

    assert released == ["list player", "media player"]


def test_nothing_kept_of_what_events_came_from_once_released(player, released):
    player._event_manager.attach_to_media_player(player._media_player)
    player.load_video(_media_input())
    player.load_video_st2_set_media()

    kept = vars(_Released)["event_manager"]._cache
    assert len(kept) == 2

    player.cleanup()

    assert kept == {}


def test_the_player_goes_once_released(released):
    player = _Player(vlc_instance=_Instance(released))
    player._event_waiter = Mock()
    player._media_player = _Released("media player", released)
    player._event_manager.attach_to_media_player(player._media_player)
    player.load_video(_media_input())

    player.cleanup()

    gone = weakref.ref(player)
    del player
    gc.collect()

    assert gone() is None
