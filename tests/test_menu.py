from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.menu import SECTIONS
from gridplayer.player.managers.menu import MenuManager


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _submenu_names(items):
    return [item[0] for item in items if isinstance(item, tuple)]


def test_empty_window_menu_has_playlist_session_settings():
    manager = MenuManager(
        context=SimpleNamespace(video_blocks=[], active_block=None),
        parent=None,
    )
    names = _submenu_names(manager._menu_sections())
    assert names == ["Seek Sync", "Grid", "Playlist Settings", "Add"]
    assert "[ALL]" not in names
    assert "Snapshots" not in names


def test_videos_menu_puts_all_videos_above_playlist():
    manager = MenuManager(
        context=SimpleNamespace(video_blocks=[object()], active_block=None),
        parent=None,
    )
    names = _submenu_names(manager._menu_sections())
    assert names == [
        "[ALL]",
        "Snapshots",
        "Seek Sync",
        "Grid",
        "Playlist Settings",
        "Add",
    ]


def test_playlist_section_is_not_duplicated_in_video_all():
    video_all_names = _submenu_names(SECTIONS["video_all"])
    playlist_names = _submenu_names(SECTIONS["playlist"])
    assert video_all_names == ["[ALL]", "Snapshots"]
    assert playlist_names == ["Seek Sync", "Grid", "Playlist Settings"]
    assert not set(video_all_names) & set(playlist_names)
