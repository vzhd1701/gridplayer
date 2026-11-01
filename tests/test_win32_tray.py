"""The tray icon of the player's own on Windows, for a player run by
python.exe: when it is wanted, its GUID, and what the shell says to it."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon

from gridplayer.utils import win32_tray
from gridplayer.utils.win32_tray import (
    NIF_SHOWTIP,
    NIM_ADD,
    NIM_DELETE,
    NIM_MODIFY,
    NIN_BALLOONUSERCLICK,
    NIN_SELECT,
    WM_CONTEXTMENU,
    WM_LBUTTONDBLCLK,
    WM_MBUTTONUP,
    WindowsTrayIcon,
    icon_guid,
    is_python_exe,
)


@pytest.mark.parametrize(
    ("name", "is_python"),
    [
        ("python.exe", True),
        ("pythonw.exe", True),
        ("Python.EXE", True),
        ("python3.12.exe", True),
        ("GridPlayer.exe", False),
        ("python-launcher.exe", False),
    ],
)
def test_python_exe_told_apart(name, is_python):
    assert is_python_exe(Path("C:/Python") / name) is is_python


def test_guid_is_the_programs():
    one = Path("C:/Python312/python.exe")

    assert icon_guid(one) == icon_guid(Path("c:/python312/PYTHON.exe"))
    assert icon_guid(one) != icon_guid(Path("C:/Python313/python.exe"))


def test_not_wanted_off_the_desktop(monkeypatch):
    # the tests run offscreen
    monkeypatch.setattr(win32_tray.env, "IS_WINDOWS", True)

    assert not win32_tray.is_own_icon_wanted()


def test_not_wanted_in_gridplayer_exe(monkeypatch):
    monkeypatch.setattr(win32_tray.env, "IS_WINDOWS", True)
    monkeypatch.setattr(win32_tray.env, "IS_PYINSTALLER", True)
    monkeypatch.setattr(win32_tray, "QGuiApplication", _platform("windows"))
    monkeypatch.setattr(win32_tray, "process_path", lambda: Path("python.exe"))

    assert not win32_tray.is_own_icon_wanted()


def test_wanted_run_by_python_on_the_desktop(monkeypatch):
    monkeypatch.setattr(win32_tray.env, "IS_WINDOWS", True)
    monkeypatch.setattr(win32_tray.env, "IS_PYINSTALLER", False)
    monkeypatch.setattr(win32_tray, "QGuiApplication", _platform("windows"))
    monkeypatch.setattr(win32_tray, "process_path", lambda: Path("pythonw.exe"))

    assert win32_tray.is_own_icon_wanted()


def _platform(name):
    return SimpleNamespace(platformName=lambda: name)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows shell's icon")
class TestIcon:
    @pytest.fixture
    def shell(self, monkeypatch):
        """The shell's answers, said in calls: nothing put up for real."""

        calls = []
        answers = {}

        def notify(message, data):
            calls.append((message, data.uFlags, data.szTip, data.szInfo))
            return answers.get(message, True)

        monkeypatch.setattr(win32_tray._win32(), "notify", notify)
        return SimpleNamespace(calls=calls, answers=answers)

    @pytest.fixture
    def icon(self, shell):
        icon = WindowsTrayIcon(QIcon())
        yield icon
        icon.deleteLater()

    def test_put_up_and_taken_down(self, shell, icon):
        icon.setToolTip("GridPlayer")

        assert icon.show()
        assert icon.isVisible()
        assert [c[0] for c in shell.calls] == [NIM_ADD, 4]
        assert shell.calls[0][2] == "GridPlayer"

        icon.hide()

        assert not icon.isVisible()
        assert shell.calls[-1][0] == NIM_DELETE

    def test_refused_takes_nothing_down(self, shell, icon):
        # another player run by the same python.exe has the GUID: taking
        # it down by the GUID would take theirs
        shell.answers[NIM_ADD] = False

        assert not icon.show()
        assert not icon.isVisible()

        icon.hide()

        assert [c[0] for c in shell.calls] == [NIM_ADD]

    def test_clicks_as_qt_says_them(self, icon):
        reasons = []
        notes = []
        icon.activated.connect(reasons.append)
        icon.messageClicked.connect(lambda: notes.append(True))

        for event in (
            NIN_SELECT,
            # a double click, then the button let go of again
            WM_LBUTTONDBLCLK,
            NIN_SELECT,
            WM_MBUTTONUP,
            NIN_BALLOONUSERCLICK,
        ):
            icon.on_callback(event)

        assert reasons == [
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.MiddleClick,
        ]
        assert notes == [True]

    def test_menu_on_a_right_click(self, icon):
        menu = QMenu()
        menu.addAction("Quit")
        icon.setContextMenu(menu)
        reasons = []
        icon.activated.connect(reasons.append)

        icon.on_callback(WM_CONTEXTMENU)

        assert reasons == [QSystemTrayIcon.Context]
        assert menu.isVisible()
        menu.hide()

    def test_back_after_explorer_starts_again(self, shell, icon):
        icon.show()
        shell.calls.clear()

        icon.on_taskbar_created()

        assert shell.calls[0][0] == NIM_ADD

    def test_kept_as_the_taskbar_scale_changes(self, shell, icon):
        # sent then too, the icon still up: put up again it is refused
        icon.show()
        shell.calls.clear()
        shell.answers[NIM_ADD] = False

        icon.on_taskbar_created()
        icon.hide()

        assert [c[0] for c in shell.calls] == [NIM_ADD, NIM_MODIFY, NIM_DELETE]

    def test_not_put_back_once_hidden(self, shell, icon):
        icon.show()
        icon.hide()
        shell.calls.clear()

        icon.on_taskbar_created()

        assert shell.calls == []

    def test_note_and_tip_changed_while_up(self, shell, icon):
        icon.showMessage("GridPlayer", "Still running")
        assert shell.calls == []

        icon.show()
        icon.showMessage("GridPlayer", "Still running")
        icon.setToolTip("GridPlayer 2")

        assert shell.calls[-2][3] == "Still running"
        assert shell.calls[-1][0] == NIM_MODIFY
        assert shell.calls[-1][2] == "GridPlayer 2"
        # each change says to keep the tip, or the shell takes it away
        for message, flags, *_ in shell.calls:
            if message in {NIM_ADD, NIM_MODIFY}:
                assert flags & NIF_SHOWTIP

    def test_menu_by_the_icon(self, icon):
        # from the keyboard, the pointer anywhere
        menu = QMenu()
        menu.addAction("Quit")
        icon.setContextMenu(menu)

        icon.on_callback(WM_CONTEXTMENU, QPoint(100, 120))

        assert menu.pos() == QPoint(100, 120)
        menu.hide()

    def test_taken_by_another(self, shell, icon, monkeypatch):
        shell.answers[NIM_ADD] = False
        monkeypatch.setattr(win32_tray._win32(), "is_up", lambda guid: True)
        icon.show()

        assert icon.is_taken()

        monkeypatch.setattr(win32_tray._win32(), "is_up", lambda guid: False)

        assert not icon.is_taken()
