from PyQt5.QtCore import QSettings

from gridplayer.params.static import UnsavedChangesMode
from gridplayer.settings import _Settings


def _make_settings(tmp_path, values):
    ini_path = tmp_path / "settings.ini"

    writer = QSettings(str(ini_path), QSettings.IniFormat)
    for key, value in values.items():
        writer.setValue(key, value)
    writer.sync()

    settings = _Settings.__new__(_Settings)
    settings.settings = QSettings(str(ini_path), QSettings.IniFormat)
    return settings


def test_migrate_track_changes_true_to_ask(tmp_path):
    settings = _make_settings(tmp_path, {"playlist/track_changes": True})

    settings._migrate_track_changes_flag()

    assert not settings.settings.contains("playlist/track_changes")
    assert settings.settings.value("playlist/unsaved_changes") == "ask"


def test_migrate_track_changes_false_to_discard(tmp_path):
    settings = _make_settings(tmp_path, {"playlist/track_changes": False})

    settings._migrate_track_changes_flag()

    assert not settings.settings.contains("playlist/track_changes")
    assert settings.settings.value("playlist/unsaved_changes") == "discard"


def test_migrate_track_changes_keeps_existing_mode(tmp_path):
    settings = _make_settings(
        tmp_path,
        {
            "playlist/track_changes": True,
            "playlist/unsaved_changes": UnsavedChangesMode.DISCARD.value,
        },
    )

    settings._migrate_track_changes_flag()

    assert not settings.settings.contains("playlist/track_changes")
    assert settings.settings.value("playlist/unsaved_changes") == "discard"


def test_migrate_track_changes_noop_without_legacy_key(tmp_path):
    settings = _make_settings(tmp_path, {"player/language": "en_US"})

    settings._migrate_track_changes_flag()

    assert not settings.settings.contains("playlist/unsaved_changes")
    assert settings.settings.value("player/language") == "en_US"
