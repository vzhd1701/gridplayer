"""A playlist that keeps all its settings: every value saved with it, the
whole grid too, and each one its own once saved."""

import pytest
from PyQt5.QtCore import QSettings

from gridplayer import playlist_settings as session_module
from gridplayer.models.grid_state import GridState
from gridplayer.params.settings_bindings import (
    GRID_STATE_ATTR,
    PLAYLIST_ATTRS,
    VIDEO_DEFAULT_ATTRS,
)
from gridplayer.playlist_settings import (
    SAVE_ALL_KEY,
    PlaylistSettings,
    grid_state_for_dump,
)
from gridplayer.settings import _Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(session_module, "Settings", lambda: store)

    return store


class TestTheSession:
    def test_keeping_all_saves_every_value(self, settings):
        PlaylistSettings().set(SAVE_ALL_KEY, True)

        kwargs = PlaylistSettings().playlist_kwargs()

        assert set(PLAYLIST_ATTRS.values()) <= set(kwargs)
        assert set(VIDEO_DEFAULT_ATTRS.values()) == set(kwargs["video_defaults"])

    def test_keeping_all_saves_the_whole_grid(self):
        PlaylistSettings().set(SAVE_ALL_KEY, True)

        dumped = grid_state_for_dump(GridState())

        assert set(GRID_STATE_ATTR.values()) <= dumped.model_fields_set

    def test_once_saved_every_value_is_its_own(self):
        PlaylistSettings().set(SAVE_ALL_KEY, True)

        PlaylistSettings().keep_all(GridState(rows=5))

        for key in (*PLAYLIST_ATTRS, *VIDEO_DEFAULT_ATTRS, *GRID_STATE_ATTR):
            assert PlaylistSettings().is_overridden(key), key
        assert PlaylistSettings().get("playlist/grid_rows") == 5

    def test_otherwise_only_its_own(self):
        PlaylistSettings().set("playlist/zoom_step", 30)

        assert PlaylistSettings().kept() == {"playlist/zoom_step": 30}
