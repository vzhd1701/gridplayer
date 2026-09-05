import pytest

from gridplayer.playlist_settings import PlaylistSettings


@pytest.fixture(autouse=True)
def _clear_playlist_settings():
    PlaylistSettings().clear()
    yield
    PlaylistSettings().clear()
