from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.player.managers.playlist import PlaylistManager


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
