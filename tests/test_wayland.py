"""Running on Wayland natively, where Qt draws the frame and the cursor.

The decoration plugin reads the palette once, as a frame is made, so a
frame left alone keeps the colors of the theme it was made under. The
cursor theme comes from XCURSOR_THEME, which GNOME doesn't export.
"""

import os
from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QMargins, QObject, QRect, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from gridplayer.utils import darkmode_linux, wayland

CLIENT_FRAME = QMargins(3, 30, 3, 3)


class _FakeWindow:
    def __init__(
        self, *, flags=Qt.WindowType.Window, visible=True, margins=CLIENT_FRAME
    ):
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
    flags = Qt.WindowType.Window | Qt.WindowType.WindowTitleHint
    window = _FakeWindow(flags=flags)

    _run(monkeypatch, "wayland", [window])

    assert window.set_flags_calls == [flags | Qt.WindowType.FramelessWindowHint, flags]
    assert window.flags() == flags


def test_left_alone_off_wayland(monkeypatch):
    window = _FakeWindow()

    _run(monkeypatch, "xcb", [window])

    assert window.set_flags_calls == []


def test_skips_windows_without_client_frame(monkeypatch):
    hidden = _FakeWindow(visible=False)
    frameless = _FakeWindow(
        flags=Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
    )
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


# -- the line under the header Qt draws (GNOME)


@pytest.fixture
def header_lines(monkeypatch):
    """The lines' event filter on the app, with every window taken to have
    a header Qt draws, unless told otherwise."""

    has_header = {"value": True}
    monkeypatch.setattr(wayland, "_has_client_frame", lambda _w: has_header["value"])

    app = QApplication.instance()
    lines = wayland._HeaderLines()
    app.installEventFilter(lines)
    windows = []

    def window():
        made = QWidget()
        made.resize(300, 200)
        windows.append(made)
        return made

    yield SimpleNamespace(window=window, has_header=has_header, lines=lines)

    app.removeEventFilter(lines)
    for made in windows:
        if not sip.isdeleted(made):
            sip.delete(made)
    sip.delete(lines)


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def test_a_window_with_a_header_gets_the_line(header_lines):
    window = header_lines.window()
    QWidget(window).setGeometry(0, 0, 300, 200)
    window.show()
    _settle()

    line = window._header_line
    assert line.isVisible()
    assert line.geometry() == QRect(0, 0, 300, 1)
    assert window.children()[-1] is line


def test_the_line_follows_the_width(header_lines):
    window = header_lines.window()
    window.show()
    _settle()

    window.resize(500, 200)
    _settle()

    assert window._header_line.width() == 500


def test_a_child_raised_or_added_goes_under_the_line(header_lines):
    window = header_lines.window()
    first = QWidget(window)
    window.show()
    _settle()

    first.raise_()
    assert window.children()[-1] is window._header_line

    added = QWidget(window)
    added.show()
    assert window.children()[-1] is window._header_line


def test_no_line_without_a_header(header_lines):
    """Fullscreen, or the compositor's own frame."""

    window = header_lines.window()
    window.show()
    _settle()

    header_lines.has_header["value"] = False
    window.setWindowState(Qt.WindowState.WindowFullScreen)
    _settle()

    assert not window._header_line.isVisible()


def test_a_window_gone_before_its_turn_is_skipped(header_lines):
    window = header_lines.window()
    window.show()
    sip.delete(window)

    _settle()


def test_lines_only_where_qt_draws_the_header(monkeypatch):
    from gridplayer.utils import wayland_frames

    installed = []

    class _App(QObject):
        def installEventFilter(self, watcher):
            installed.append(watcher)

    app = _App()

    for platform, compositor_draws, wanted in (
        ("xcb", False, 0),
        ("wayland", True, 0),
        ("wayland", False, 1),
    ):
        monkeypatch.setattr(
            wayland.QGuiApplication, "platformName", staticmethod(lambda p=platform: p)
        )
        monkeypatch.setattr(
            wayland_frames, "compositor_draws_frames", lambda d=compositor_draws: d
        )
        installed.clear()

        wayland.draw_header_lines(app)

        assert len(installed) == wanted
