from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from gridplayer.params import theme
from gridplayer.params.static import ColorScheme
from gridplayer.utils import darkmode


class _FakeSettings:
    def __init__(self, scheme):
        self._scheme = scheme

    def get(self, key):
        assert key == "player/color_scheme"
        return self._scheme


def test_is_dark_mode_light_setting_ignores_system(monkeypatch):
    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.LIGHT))
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: True)
    assert darkmode.is_dark_mode() is False


def test_is_dark_mode_dark_setting_ignores_system(monkeypatch):
    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.DARK))
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: False)
    assert darkmode.is_dark_mode() is True


def test_is_dark_mode_system_follows_os(monkeypatch):
    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.SYSTEM))
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: True)
    assert darkmode.is_dark_mode() is True
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: False)
    assert darkmode.is_dark_mode() is False


def test_on_system_theme_changed_skipped_when_manual(monkeypatch):
    called = []
    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.DARK))
    monkeypatch.setattr(theme, "apply_theme", lambda app=None: called.append(app))

    theme.on_system_theme_changed()
    assert called == []


def test_on_system_theme_changed_applies_when_system(monkeypatch):
    called = []
    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.SYSTEM))
    monkeypatch.setattr(theme, "apply_theme", lambda app=None: called.append(True))

    theme.on_system_theme_changed()
    assert called == [True]


def test_system_asked_once_until_the_theme_is_applied_again(monkeypatch):
    asked = []

    def color_scheme():
        asked.append(True)
        return Qt.ColorScheme.Dark

    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.SYSTEM))
    monkeypatch.setattr(darkmode.env, "IS_LINUX", False)
    hints = SimpleNamespace(colorScheme=color_scheme)
    monkeypatch.setattr(
        darkmode, "QGuiApplication", SimpleNamespace(styleHints=lambda: hints)
    )
    # nothing to put the theme on: only what it asks again
    monkeypatch.setattr(theme, "QApplication", SimpleNamespace(instance=lambda: None))
    darkmode.is_system_dark_mode.cache_clear()

    try:
        assert darkmode.is_dark_mode() is True
        assert darkmode.is_dark_mode() is True
        assert len(asked) == 1

        theme.apply_theme()

        assert darkmode.is_dark_mode() is True
        assert len(asked) == 2
    finally:
        darkmode.is_system_dark_mode.cache_clear()


@pytest.mark.parametrize(
    ("qt_says", "dark"),
    [
        (Qt.ColorScheme.Dark, True),
        (Qt.ColorScheme.Light, False),
        # high contrast, or nothing known
        (Qt.ColorScheme.Unknown, False),
    ],
)
def test_windows_and_macos_system_scheme_is_qts(monkeypatch, qt_says, dark):
    monkeypatch.setattr(darkmode.env, "IS_LINUX", False)
    hints = SimpleNamespace(colorScheme=lambda: qt_says)
    monkeypatch.setattr(
        darkmode, "QGuiApplication", SimpleNamespace(styleHints=lambda: hints)
    )
    darkmode.is_system_dark_mode.cache_clear()

    try:
        assert darkmode.is_system_dark_mode() is dark
    finally:
        darkmode.is_system_dark_mode.cache_clear()


@pytest.mark.parametrize(("is_linux", "watched"), [(True, True), (False, False)])
def test_own_watcher_on_linux_alone(monkeypatch, is_linux, watched):
    """Elsewhere init_app hears a switch from Qt's colorSchemeChanged."""

    import gridplayer.utils.darkmode_linux as darkmode_linux

    monkeypatch.setattr(darkmode.env, "IS_LINUX", is_linux)
    monkeypatch.setattr(
        darkmode_linux, "LinuxThemeWatcher", lambda callback, parent: "watcher"
    )

    assert (darkmode.watch_system_theme(lambda: None) == "watcher") is watched
