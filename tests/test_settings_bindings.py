from gridplayer.models.playlist import Playlist
from gridplayer.params.settings_bindings import PLAYLIST_ATTRS, VIDEO_DEFAULT_ATTRS
from gridplayer.playlist_settings import (
    overrides_from_playlist,
    playlist_kwargs_from_overrides,
)
from gridplayer.settings import default_value


def test_every_bound_setting_round_trips_even_when_explicitly_default():
    overrides = {
        key: default_value(key) for key in (*PLAYLIST_ATTRS, *VIDEO_DEFAULT_ATTRS)
    }
    playlist = Playlist(videos=[], **playlist_kwargs_from_overrides(overrides))
    before = overrides_from_playlist(playlist)

    after = overrides_from_playlist(Playlist.parse(playlist.dumps()))

    assert set(before) == set(overrides)
    assert after == before
