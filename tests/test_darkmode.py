from types import SimpleNamespace

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
    monkeypatch.setattr(theme, "Settings", lambda: _FakeSettings(ColorScheme.DARK))
    monkeypatch.setattr(theme, "apply_theme", lambda app=None: called.append(app))

    theme.on_system_theme_changed()
    assert called == []


def test_on_system_theme_changed_applies_when_system(monkeypatch):
    called = []
    monkeypatch.setattr(theme, "Settings", lambda: _FakeSettings(ColorScheme.SYSTEM))
    monkeypatch.setattr(theme, "apply_theme", lambda app=None: called.append(True))

    theme.on_system_theme_changed()
    assert called == [True]


def test_system_asked_once_until_the_theme_is_applied_again(monkeypatch):
    asked = []

    def macos_is_dark():
        asked.append(True)
        return True

    monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(ColorScheme.SYSTEM))
    monkeypatch.setattr(darkmode.env, "IS_MACOS", True)
    monkeypatch.setattr(darkmode, "_macos_is_dark", macos_is_dark)
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
