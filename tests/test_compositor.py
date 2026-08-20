from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gridplayer.utils import compositor_linux as compositor


@pytest.fixture(autouse=True)
def _reset_compositor_cache():
    compositor.reset_compositor_cache()
    yield
    compositor.reset_compositor_cache()


class _FakeSettings:
    def __init__(self, opaque_hw_overlay):
        self._opaque_hw_overlay = opaque_hw_overlay

    def get(self, key):
        assert key == "internal/opaque_hw_overlay"
        return self._opaque_hw_overlay


def _fake_x11(*, owner, display=123, screen=0, atom=42):
    x11 = MagicMock()
    x11.XOpenDisplay.return_value = display
    x11.XDefaultScreen.return_value = screen
    x11.XInternAtom.return_value = atom
    x11.XGetSelectionOwner.return_value = owner
    return x11


def test_non_linux_is_running(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", False)
    assert compositor.is_compositor_running() is True


def test_wayland_platform_skips_x11(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "wayland")
    load = MagicMock(side_effect=AssertionError("X11 should not be queried"))
    monkeypatch.setattr(compositor, "_load_libx11", load)

    assert compositor.is_compositor_running() is True
    load.assert_not_called()


def test_x11_no_selection_owner(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "xcb")
    x11 = _fake_x11(owner=0)
    monkeypatch.setattr(compositor, "_load_libx11", lambda: x11)

    assert compositor.is_compositor_running() is False
    x11.XCloseDisplay.assert_called_once()
    atom_name = x11.XInternAtom.call_args.args[1]
    assert atom_name == b"_NET_WM_CM_S0"


def test_x11_selection_owner_present(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "xcb")
    x11 = _fake_x11(owner=99, screen=1)
    monkeypatch.setattr(compositor, "_load_libx11", lambda: x11)

    assert compositor.is_compositor_running() is True
    atom_name = x11.XInternAtom.call_args.args[1]
    assert atom_name == b"_NET_WM_CM_S1"


def test_missing_libx11_fails_open(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "xcb")
    monkeypatch.setattr(compositor, "_load_libx11", lambda: None)

    assert compositor.is_compositor_running() is True


def test_xopen_display_failure_fails_open(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "xcb")
    x11 = _fake_x11(owner=0, display=None)
    monkeypatch.setattr(compositor, "_load_libx11", lambda: x11)

    assert compositor.is_compositor_running() is True
    x11.XCloseDisplay.assert_not_called()


def test_x11_exception_fails_open(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "xcb")

    def boom():
        raise OSError("broken")

    monkeypatch.setattr(compositor, "_load_libx11", boom)

    assert compositor.is_compositor_running() is True


def test_result_is_cached(monkeypatch):
    monkeypatch.setattr(compositor.env, "IS_LINUX", True)
    monkeypatch.setattr(compositor, "_qt_platform_name", lambda: "xcb")
    x11 = _fake_x11(owner=0)
    load = MagicMock(return_value=x11)
    monkeypatch.setattr(compositor, "_load_libx11", load)

    assert compositor.is_compositor_running() is False
    assert compositor.is_compositor_running() is False
    load.assert_called_once()


def test_opaque_when_setting_enabled(monkeypatch):
    monkeypatch.setattr(compositor, "Settings", lambda: _FakeSettings(True))
    monkeypatch.setattr(compositor, "is_compositor_running", lambda: True)
    assert compositor.should_make_overlay_opaque() is True


def test_opaque_when_no_compositor(monkeypatch):
    monkeypatch.setattr(compositor, "Settings", lambda: _FakeSettings(False))
    monkeypatch.setattr(compositor, "is_compositor_running", lambda: False)
    assert compositor.should_make_overlay_opaque() is True


def test_transparent_when_compositor_and_setting_off(monkeypatch):
    monkeypatch.setattr(compositor, "Settings", lambda: _FakeSettings(False))
    monkeypatch.setattr(compositor, "is_compositor_running", lambda: True)
    assert compositor.should_make_overlay_opaque() is False


def test_load_libx11_tries_soname_fallback(monkeypatch):
    monkeypatch.setattr(compositor.ctypes.util, "find_library", lambda _name: None)
    cdll = MagicMock(side_effect=[OSError("no"), SimpleNamespace()])
    monkeypatch.setattr(compositor.ctypes, "CDLL", cdll)

    assert compositor._load_libx11() is not None
    assert cdll.call_args_list[0].args[0] == "libX11.so.6"
    assert cdll.call_args_list[1].args[0] == "libX11.so"


def test_load_libx11_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(compositor.ctypes.util, "find_library", lambda _name: None)
    monkeypatch.setattr(compositor.ctypes, "CDLL", MagicMock(side_effect=OSError("no")))

    assert compositor._load_libx11() is None
