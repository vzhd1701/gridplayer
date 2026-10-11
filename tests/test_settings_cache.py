"""The Cache section of the Player page: where it is kept and how much of it
saved and shown again, the size limit greyed out when nothing goes on disk,
and Clear, which empties it at once and says what is left."""

import time
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.models.grid_state import GridState
from gridplayer.params.static import CacheMode
from gridplayer.player.managers import settings as settings_manager
from gridplayer.settings import _default_settings, _Settings
from gridplayer.utils import cache


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


@pytest.fixture
def root(_no_real_cache, monkeypatch):
    monkeypatch.setattr(cache, "_memory", type(cache._memory)())
    monkeypatch.setattr(cache, "_memory_bytes", 0)
    monkeypatch.setattr(cache, "_disk_bytes", None)

    return _no_real_cache


@pytest.fixture
def make_dialog(settings, root):
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


def _put(root, size, name="a"):
    path = root / "thumbnails" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)

    return path


def _choose(combo, value):
    combo.setCurrentIndex(combo.findData(value))


def _said(dialog, text, timeout=5):
    """Whether what the cache comes to was put beside Clear in time: it is
    worked out on a thread."""

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if dialog.cacheSize.text() == text:
            return True
    return False


class TestSavedAndShownAgain:
    def test_out_of_the_box_on_disk_up_to_1024_mb(self, make_dialog):
        dialog = make_dialog()

        assert dialog.cacheMode.currentData() is CacheMode.DISK
        assert dialog.cacheMaxMB.value() == 1024
        assert dialog.cacheMaxMB.isEnabled()

    def test_what_was_stored(self, settings, make_dialog):
        settings.set("cache/mode", CacheMode.MEMORY)
        settings.set("cache/max_mb", 128)

        dialog = make_dialog()

        assert dialog.cacheMode.currentData() is CacheMode.MEMORY
        assert dialog.cacheMaxMB.value() == 128

    def test_what_was_picked_saved(self, settings, make_dialog):
        dialog = make_dialog()

        dialog.cacheMaxMB.setValue(32)
        _choose(dialog.cacheMode, CacheMode.MEMORY)
        dialog.save_settings()

        assert settings.get("cache/mode") is CacheMode.MEMORY
        # greyed out, as it was left
        assert settings.get("cache/max_mb") == 1024


class TestTheSizeLimit:
    def test_greyed_out_when_nothing_goes_on_disk(self, make_dialog):
        dialog = make_dialog()

        _choose(dialog.cacheMode, CacheMode.MEMORY)

        assert not dialog.cacheMaxMB.isEnabled()
        assert not dialog.cacheMaxMBLabel.isEnabled()

        _choose(dialog.cacheMode, CacheMode.DISK)

        assert dialog.cacheMaxMB.isEnabled()

    def test_greyed_out_as_it_opens(self, settings, make_dialog):
        settings.set("cache/mode", CacheMode.MEMORY)

        dialog = make_dialog()

        assert not dialog.cacheMaxMB.isEnabled()


class TestClear:
    def test_what_the_cache_comes_to_beside_it(self, root, make_dialog):
        _put(root, 1536 * 1024)

        dialog = make_dialog()

        assert _said(dialog, "1.5 MB used")
        assert dialog.cacheClear.isEnabled()

    def test_a_little_is_not_nothing(self, root, make_dialog):
        _put(root, 10)

        dialog = make_dialog()

        assert _said(dialog, "0.1 MB used")

    def test_an_empty_one_has_nothing_to_clear(self, make_dialog):
        dialog = make_dialog()

        assert _said(dialog, "Empty")
        assert not dialog.cacheClear.isEnabled()

    def test_emptied_at_once_not_on_ok(self, root, make_dialog):
        path = _put(root, 1024 * 1024)
        dialog = make_dialog()
        assert _said(dialog, "1.0 MB used")

        QTest.mouseClick(dialog.cacheClear, Qt.LeftButton)

        assert _said(dialog, "Empty")
        assert not path.exists()
        assert not dialog.cacheClear.isEnabled()

    def test_says_where_it_is(self, root, make_dialog):
        dialog = make_dialog()

        assert str(root) in dialog.cacheClear.toolTip()


def _manager():
    parent = QWidget()
    ctx = SimpleNamespace(
        commands=SimpleNamespace(apply_grid_config=lambda config: None),
        grid_state=GridState(),
    )
    manager = settings_manager.SettingsManager(context=ctx, parent=parent)
    manager._keep_parent = parent

    return manager


class TestAppliedOnOk:
    @pytest.mark.parametrize(
        ("key", "value"), [("cache/mode", CacheMode.MEMORY), ("cache/max_mb", 8)]
    )
    def test_the_cache_made_to_fit(self, key, value, mocker):
        current = dict(_default_settings)
        current[key] = value
        mocker.patch.object(
            settings_manager.Settings(), "get", side_effect=current.__getitem__
        )
        apply = mocker.patch.object(cache, "apply_settings")
        manager = _manager()

        manager._apply_settings(dict(_default_settings))

        apply.assert_called_once_with()

    def test_left_alone_otherwise(self, mocker):
        mocker.patch.object(
            settings_manager.Settings(),
            "get",
            side_effect=dict(_default_settings).__getitem__,
        )
        apply = mocker.patch.object(cache, "apply_settings")
        manager = _manager()

        manager._apply_settings(dict(_default_settings))

        apply.assert_not_called()


class TestOpenFolder:
    def test_beside_clear(self, make_dialog):
        dialog = make_dialog()

        menu = dialog.cacheClear.menu()

        assert [action.text() for action in menu.actions()] == ["Open Folder"]

    def test_opens_it_made_if_it_is_not_there_yet(self, root, make_dialog, monkeypatch):
        dialog = make_dialog()
        opened = []
        monkeypatch.setattr(dialog, "_open_folder", opened.append)

        dialog.cache_open_action.trigger()

        assert opened == [root]
        assert root.is_dir()

    def test_nothing_on_disk_to_see_kept_in_memory(self, make_dialog):
        dialog = make_dialog()

        _choose(dialog.cacheMode, CacheMode.MEMORY)

        assert not dialog.cache_open_action.isEnabled()

        _choose(dialog.cacheMode, CacheMode.DISK)

        assert dialog.cache_open_action.isEnabled()
