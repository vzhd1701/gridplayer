from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist
from gridplayer.params.static import GridMode, SeekSyncMode
from gridplayer.player.managers.playlist import PlaylistManager
from gridplayer.settings import Settings


class _Playlist:
    def __init__(self, error=None):
        self.error = error
        self.saved_to = None

    def save(self, filename):
        if self.error is not None:
            raise self.error
        self.saved_to = filename

    def dumps(self):
        return "#GRIDPLAYER\n"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _make_manager():
    parent = QWidget()
    manager = PlaylistManager(context=object(), parent=parent)
    return manager, parent


def test_write_playlist_emits_playlist_saved(mocker):
    manager, _parent = _make_manager()
    playlist = _Playlist()
    mocker.patch.object(manager, "_set_saved_playlist")

    emitted = []
    manager.playlist_saved.connect(emitted.append)

    file_path = Path("saved.gpls")
    assert manager._write_playlist(playlist, file_path) is True

    assert playlist.saved_to == file_path
    assert emitted == [file_path]


def test_write_playlist_does_not_emit_playlist_saved_on_error(mocker):
    manager, _parent = _make_manager()
    playlist = _Playlist(error=OSError("disk full"))
    mocker.patch.object(manager, "_set_saved_playlist")

    emitted = []
    manager.playlist_saved.connect(emitted.append)

    assert manager._write_playlist(playlist, Path("saved.gpls")) is False
    assert playlist.saved_to is None
    assert emitted == []
    manager._set_saved_playlist.assert_not_called()


def _collect_session_signals(manager):
    collected = {
        "seek_sync_mode": [],
        "shuffle_on_load": [],
        "disable_mouse_click_events": [],
        "disable_mouse_wheel_events": [],
        "disable_overlay": [],
        "grid_state": [],
    }
    manager.seek_sync_mode_loaded.connect(collected["seek_sync_mode"].append)
    manager.shuffle_on_load_loaded.connect(collected["shuffle_on_load"].append)
    manager.disable_mouse_click_events_loaded.connect(
        collected["disable_mouse_click_events"].append
    )
    manager.disable_mouse_wheel_events_loaded.connect(
        collected["disable_mouse_wheel_events"].append
    )
    manager.disable_overlay_loaded.connect(collected["disable_overlay"].append)
    manager.grid_state_loaded.connect(collected["grid_state"].append)
    return collected


def _patch_playlist_settings(mocker, overrides):
    settings = Settings()
    real_get = settings.get

    def fake_get(key):
        if key in overrides:
            return overrides[key]
        return real_get(key)

    mocker.patch.object(settings, "get", side_effect=fake_get)


_CUSTOM_PLAYLIST_DEFAULTS = {
    "playlist/seek_sync_mode": SeekSyncMode.PERCENT,
    "playlist/shuffle_on_load": True,
    "playlist/disable_mouse_click_events": True,
    "playlist/disable_mouse_wheel_events": True,
    "playlist/disable_overlay": True,
    "playlist/grid_mode": GridMode.AUTO_COLS,
    "playlist/grid_fit": False,
    "playlist/grid_size": 3,
}


def test_close_playlist_resets_session_to_settings_defaults(mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    _patch_playlist_settings(mocker, _CUSTOM_PLAYLIST_DEFAULTS)

    collected = _collect_session_signals(manager)
    closed = []
    manager.playlist_closed.connect(lambda: closed.append(True))

    assert manager.cmd_close_playlist() is True

    assert closed == [True]
    assert collected["seek_sync_mode"] == [SeekSyncMode.PERCENT]
    assert collected["shuffle_on_load"] == [True]
    assert collected["disable_mouse_click_events"] == [True]
    assert collected["disable_mouse_wheel_events"] == [True]
    assert collected["disable_overlay"] == [True]
    assert collected["grid_state"] == [
        GridState(mode=GridMode.AUTO_COLS, is_fit=False, size=3)
    ]


def test_close_playlist_does_not_reset_when_save_cancelled(mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "check_playlist_save", return_value=False)

    collected = _collect_session_signals(manager)
    closed = []
    manager.playlist_closed.connect(lambda: closed.append(True))

    assert manager.cmd_close_playlist() is False

    assert closed == []
    assert collected == {
        "seek_sync_mode": [],
        "shuffle_on_load": [],
        "disable_mouse_click_events": [],
        "disable_mouse_wheel_events": [],
        "disable_overlay": [],
        "grid_state": [],
    }


def test_load_playlist_applies_file_settings_after_reset(mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    _patch_playlist_settings(mocker, _CUSTOM_PLAYLIST_DEFAULTS)

    collected = _collect_session_signals(manager)

    playlist = Playlist(
        videos=[],
        seek_sync_mode=SeekSyncMode.TIMECODE,
        shuffle_on_load=False,
        disable_mouse_click_events=False,
        disable_mouse_wheel_events=False,
        disable_overlay=False,
        grid_state=GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
    )

    assert manager.load_playlist(playlist) is True

    assert collected["seek_sync_mode"] == [
        SeekSyncMode.PERCENT,
        SeekSyncMode.TIMECODE,
    ]
    assert collected["shuffle_on_load"] == [True, False]
    assert collected["disable_mouse_click_events"] == [True, False]
    assert collected["disable_mouse_wheel_events"] == [True, False]
    assert collected["disable_overlay"] == [True, False]
    assert collected["grid_state"] == [
        GridState(mode=GridMode.AUTO_COLS, is_fit=False, size=3),
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
    ]
