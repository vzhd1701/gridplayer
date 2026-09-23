"""Frames Qt draws itself on Wayland are made again when the theme changes.

The decoration plugin reads the palette once, as a frame is made, so a
frame left alone keeps the colors of the theme it was made under.
"""

from PyQt5.QtCore import QMargins, Qt

from gridplayer.utils import wayland_window

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

    monkeypatch.setattr(wayland_window, "QGuiApplication", _FakeApp)

    wayland_window.refresh_window_frames()


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
