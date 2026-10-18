"""In the Settings dialog, the settings the open playlist has its own value
for: a mark on each one's row, and a word at the top of its page."""

import pytest
from PyQt5.QtCore import QEvent, QObject, QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.models.grid_state import GridState
from gridplayer.params.settings_fields import general as general_fields
from gridplayer.playlist_settings import SAVE_ALL_KEY, PlaylistSettings
from gridplayer.settings import _Settings

VOLUME = "video_defaults/volume"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_settings(tmp_path, monkeypatch):
    from gridplayer.utils import cache

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)
    monkeypatch.setattr(cache, "cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(
        general_fields.QSystemTrayIcon,
        "isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(general_fields, "taskbar_hiding_blocker", lambda: None)

    made = []

    def _make():
        dialog = SettingsDialog(None)
        made.append(dialog)
        return dialog

    yield _make

    for dialog in made:
        dialog.close()
        dialog.deleteLater()

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _marks(dialog, key):
    row = dialog.form_of(key)._rows[key]
    return [
        widget.toolTip()
        for widget in row.findChildren(QObject)
        if isinstance(widget, QWidget)
        and widget.toolTip().startswith("The open playlist")
    ]


class TestThePlaylistsOwnInSettings:
    def test_marked_on_its_row_with_its_value(self, make_settings):
        PlaylistSettings().set("playlist/view_sync", True)

        dialog = make_settings()

        assert _marks(dialog, "playlist/view_sync") == [
            "The open playlist has its own value: On"
        ]
        assert _marks(dialog, "playlist/pause_sync") == []

    def test_said_at_the_top_of_its_page(self, make_settings):
        PlaylistSettings().set(VOLUME, 0.5)

        dialog = make_settings()

        assert "marked with the playlist icon" in dialog.notes["video"].text()
        assert "playlist" not in dialog.notes

    def test_a_number_in_words(self, make_settings):
        PlaylistSettings().set("playlist/zoom_step", 30)

        dialog = make_settings()

        (mark,) = _marks(dialog, "playlist/zoom_step")
        assert mark.startswith("The open playlist has its own value: 30")

    def test_all_kept_is_said_once(self, make_settings):
        PlaylistSettings().set(SAVE_ALL_KEY, True)
        PlaylistSettings().keep_all(GridState())

        dialog = make_settings()

        assert "keeps all its settings" in dialog.notes["playlist"].text()
        assert _marks(dialog, "playlist/view_sync") == []

    def test_nothing_said_with_none(self, make_settings):
        dialog = make_settings()

        assert "playlist" not in dialog.notes
        assert "video" not in dialog.notes
