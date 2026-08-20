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
