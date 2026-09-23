"""Running on Wayland natively, where Qt draws the frame and the cursor.

The decoration plugin reads the palette once, as a frame is made, so a
frame left alone keeps the colors of the theme it was made under. The
cursor theme comes from XCURSOR_THEME, which GNOME doesn't export.
"""

import os

import pytest
from PyQt5.QtCore import QMargins, Qt

from gridplayer.utils import darkmode_linux, wayland

CLIENT_FRAME = QMargins(3, 30, 3, 3)


class _FakeWindow:
    def __init__(self, *, flags=Qt.Window, visible=True, margins=CLIENT_FRAME):
        self._flags = flags
        self._visible = visible
        self._margins = margins
        self.set_flags_calls = []

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        self.set_flags_calls.append(flags)
        self._flags = flags

    def isVisible(self):
        return self._visible

    def frameMargins(self):
        return self._margins


def _run(monkeypatch, platform, windows):
    class _FakeApp:
        @staticmethod
        def platformName():
            return platform

        @staticmethod
        def topLevelWindows():
            return windows

    monkeypatch.setattr(wayland, "QGuiApplication", _FakeApp)

    wayland.refresh_window_frames()


def test_frame_taken_off_and_put_back(monkeypatch):
    flags = Qt.Window | Qt.WindowTitleHint
    window = _FakeWindow(flags=flags)

    _run(monkeypatch, "wayland", [window])

    assert window.set_flags_calls == [flags | Qt.FramelessWindowHint, flags]
    assert window.flags() == flags


def test_left_alone_off_wayland(monkeypatch):
    window = _FakeWindow()

    _run(monkeypatch, "xcb", [window])

    assert window.set_flags_calls == []


def test_skips_windows_without_client_frame(monkeypatch):
    hidden = _FakeWindow(visible=False)
    frameless = _FakeWindow(flags=Qt.Tool | Qt.FramelessWindowHint)
    # the compositor's own frame (KDE), or fullscreen
    server_frame = _FakeWindow(margins=QMargins())

    _run(monkeypatch, "wayland", [hidden, frameless, server_frame])

    assert hidden.set_flags_calls == []
    assert frameless.set_flags_calls == []
    assert server_frame.set_flags_calls == []


class _FakePortal:
    def __init__(self, values):
        self.values = values
        self.reads = []

    def __call__(self, namespace, key):
        self.reads.append((namespace, key))
        return self.values.get(key)


def _follow_cursor(monkeypatch, platform, portal_values):
    portal = _FakePortal(portal_values)

    class _FakeApp:
        @staticmethod
        def platformName():
            return platform

    monkeypatch.setattr(wayland, "QGuiApplication", _FakeApp)
    monkeypatch.setattr(darkmode_linux, "portal_read", portal)

    wayland.follow_desktop_cursor()

    return portal


@pytest.fixture
def _no_cursor_env(monkeypatch):
    monkeypatch.delenv("XCURSOR_THEME", raising=False)
    monkeypatch.delenv("XCURSOR_SIZE", raising=False)


@pytest.mark.usefixtures("_no_cursor_env")
def test_cursor_from_desktop(monkeypatch):
    _follow_cursor(monkeypatch, "wayland", {"cursor-theme": "Yaru", "cursor-size": 48})

    assert os.environ["XCURSOR_THEME"] == "Yaru"
    assert os.environ["XCURSOR_SIZE"] == "48"


@pytest.mark.usefixtures("_no_cursor_env")
def test_cursor_set_by_session_kept(monkeypatch):
    monkeypatch.setenv("XCURSOR_THEME", "breeze_cursors")
    monkeypatch.setenv("XCURSOR_SIZE", "32")

    portal = _follow_cursor(
        monkeypatch, "wayland", {"cursor-theme": "Yaru", "cursor-size": 48}
    )

    assert os.environ["XCURSOR_THEME"] == "breeze_cursors"
    assert os.environ["XCURSOR_SIZE"] == "32"
    assert portal.reads == []


@pytest.mark.usefixtures("_no_cursor_env")
def test_cursor_left_to_qt_without_answer(monkeypatch):
    _follow_cursor(monkeypatch, "wayland", {"cursor-theme": "", "cursor-size": 0})

    assert "XCURSOR_THEME" not in os.environ
    assert "XCURSOR_SIZE" not in os.environ


@pytest.mark.usefixtures("_no_cursor_env")
def test_cursor_left_alone_off_wayland(monkeypatch):
    portal = _follow_cursor(monkeypatch, "xcb", {"cursor-theme": "Yaru"})

    assert "XCURSOR_THEME" not in os.environ
    assert portal.reads == []
