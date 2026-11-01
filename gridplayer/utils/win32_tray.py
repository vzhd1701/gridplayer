"""A tray icon of the player's own on Windows, for a player run by python.exe.

Windows keeps what is chosen for a tray icon, shown or hidden in the
overflow, by the program that put it up and the icon's number. Qt numbers
its icons from 1, so to Windows every app run by the same python.exe with
a Qt tray icon has the same one: hidden or shown, they go together. This
icon is told apart by a GUID instead, made from the python.exe's path, as
Windows ties a GUID to the program that first used it and refuses it to any
other.

GridPlayer.exe is a program of its own, and keeps Qt's icon. So does a
player that can't put this one up: another one run by the same python.exe
has it up already (see TrayManager).
"""

import functools
import logging
import re
import sys
import uuid
import weakref
from pathlib import Path

from PyQt5.QtCore import QObject, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QGuiApplication, QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon

from gridplayer.params import env

_log = logging.getLogger(__name__)

# python.exe, pythonw.exe, python3.12.exe as the Microsoft Store has it
_PYTHON_EXE = re.compile(r"pythonw?(\d+(\.\d+)*)?\.exe", re.IGNORECASE)

# the message the icon's clicks come in, WM_APP and a number of ours
CALLBACK_MESSAGE = 0x8000 + 0x47

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10
NIF_GUID = 0x20
NIF_SHOWTIP = 0x80

NOTIFYICON_VERSION_4 = 4

NIN_SELECT = 0x400
NIN_KEYSELECT = 0x401
NIN_BALLOONUSERCLICK = 0x405
WM_CONTEXTMENU = 0x7B
WM_LBUTTONDBLCLK = 0x203
WM_MBUTTONUP = 0x208

_NOTE_ICONS = {
    QSystemTrayIcon.NoIcon: 0,
    QSystemTrayIcon.Information: 1,
    QSystemTrayIcon.Warning: 2,
    QSystemTrayIcon.Critical: 3,
}


def is_own_icon_wanted() -> bool:
    """Whether the player is run by a python.exe, on the Windows desktop
    (not offscreen, as in the tests)."""

    if not env.IS_WINDOWS or env.IS_PYINSTALLER:
        return False

    if QGuiApplication.platformName() != "windows":
        return False

    return is_python_exe(process_path())


def is_python_exe(path: Path) -> bool:
    return _PYTHON_EXE.fullmatch(path.name) is not None


@functools.cache
def process_path() -> Path:
    """The program the process runs: the python.exe of a venv only starts
    the one it was made from, which is the one Windows sees."""

    import ctypes

    size = 32768
    buffer = ctypes.create_unicode_buffer(size)
    ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, size)
    return Path(buffer.value or sys.executable)


def icon_guid(path: Path) -> uuid.UUID:
    """The icon's GUID, the same each time the program at path runs it."""

    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/vzhd1701/gridplayer/tray/{str(path).lower()}",
    )


class WindowsTrayIcon(QObject):
    """As much of QSystemTrayIcon as TrayManager uses, put up by the Windows
    shell itself with a GUID.

    show() says whether it is up: Windows refuses the GUID while another
    player has it up (see is_taken), and any icon before Explorer is ready.
    """

    activated = pyqtSignal(int)
    messageClicked = pyqtSignal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(parent)

        self._guid = icon_guid(process_path())
        self._tip = ""
        self._menu: QMenu | None = None
        self._is_wanted = False
        self._is_added = False
        # a double click is a click first, then another let go of
        self._is_skipping_select = False

        self._handles = {"hwnd": _win32().make_window(), "hicon": None}
        _icons[self._handles["hwnd"]] = self
        self.destroyed.connect(functools.partial(_release, self._handles))

        self._source = icon
        self._make_hicon()

    # --- as QSystemTrayIcon ---

    def show(self) -> bool:
        self._is_wanted = True
        if not self._is_added:
            self._is_added = self._add()
        return self._is_added

    def hide(self) -> None:
        self._is_wanted = False
        if self._is_added:
            # only an icon of its own: the GUID would take another
            # player's down
            self._notify(NIM_DELETE, 0)
            self._is_added = False

    def isVisible(self) -> bool:
        """Up in the tray: not while Explorer starts again, the icon to be
        put back once it has."""

        return self._is_added

    def setIcon(self, icon: QIcon) -> None:
        self._source = icon
        self._make_hicon()
        if self._is_added:
            self._notify(NIM_MODIFY, NIF_ICON)

    def setToolTip(self, text: str) -> None:
        self._tip = text
        if self._is_added:
            self._notify(NIM_MODIFY, 0)

    def setContextMenu(self, menu: QMenu) -> None:
        self._menu = menu

    def showMessage(
        self,
        title: str,
        text: str,
        icon=QSystemTrayIcon.Information,
        msecs: int = 10000,
    ) -> None:
        if not self._is_added:
            return

        def fill(data):
            data.szInfoTitle = title[:63]
            data.szInfo = text[:255]
            data.dwInfoFlags = _NOTE_ICONS.get(icon, 0)
            data.uVersion = msecs

        self._notify(NIM_MODIFY, NIF_INFO, fill)

    # --- from the shell ---

    def is_taken(self) -> bool:
        """Whether an icon with its GUID is up, that is not its own: another
        player's, run by the same python.exe."""

        return not self._is_added and _win32().is_up(self._guid.bytes_le)

    def on_callback(self, event: int, anchor: QPoint | None = None) -> None:
        """A click on the icon, or on its note, as NOTIFYICON_VERSION_4
        says it, the way Qt's own icon tells it on; anchor is where the
        icon is, for its menu, in the screen's own pixels."""

        if event in {NIN_SELECT, NIN_KEYSELECT}:
            if self._is_skipping_select:
                self._is_skipping_select = False
            else:
                self.activated.emit(QSystemTrayIcon.Trigger)
        elif event == WM_LBUTTONDBLCLK:
            self._is_skipping_select = True
            self.activated.emit(QSystemTrayIcon.DoubleClick)
        elif event == WM_CONTEXTMENU:
            self.activated.emit(QSystemTrayIcon.Context)
            self._show_menu(anchor)
        elif event == WM_MBUTTONUP:
            self.activated.emit(QSystemTrayIcon.MiddleClick)
        elif event == NIN_BALLOONUSERCLICK:
            self.messageClicked.emit()

    def on_taskbar_created(self) -> None:
        """Explorer started again, with no icons: put it back. Also sent as
        the taskbar's scale changes, the icon still up."""

        if not self._is_wanted:
            return

        # made again at the taskbar's scale
        self._make_hicon()

        if self._add():
            self._is_added = True
        elif self._is_added:
            # still up, as it was: shown as it is now
            self._notify(NIM_MODIFY, NIF_ICON)

    # --- inside ---

    def _add(self) -> bool:
        if not self._notify(NIM_ADD, NIF_MESSAGE | NIF_ICON):
            _log.info("Tray icon %s refused", self._guid)
            return False

        def version(data):
            data.uVersion = NOTIFYICON_VERSION_4

        self._notify(NIM_SETVERSION, 0, version)
        return True

    def _notify(self, message: int, flags: int, fill=None) -> bool:
        win32 = _win32()

        if message in {NIM_ADD, NIM_MODIFY}:
            # each time, or with NOTIFYICON_VERSION_4 the shell takes the
            # tip away
            flags |= NIF_TIP | NIF_SHOWTIP

        data = win32.NOTIFYICONDATAW()
        data.cbSize = win32.ctypes.sizeof(data)
        data.hWnd = self._handles["hwnd"]
        data.uFlags = flags | NIF_GUID
        data.guidItem = win32.GUID.from_buffer_copy(self._guid.bytes_le)
        data.uCallbackMessage = CALLBACK_MESSAGE
        data.hIcon = self._handles["hicon"]
        data.szTip = self._tip[:127]
        if fill is not None:
            fill(data)

        return win32.notify(message, data)

    def _make_hicon(self) -> None:
        old = self._handles["hicon"]
        self._handles["hicon"] = _hicon(self._source)
        if old:
            _win32().destroy_icon(old)

    def _show_menu(self, anchor: QPoint | None) -> None:
        if self._menu is None:
            return

        # by the icon, opened from the keyboard too
        at = _from_native(anchor) if anchor is not None else None
        self._menu.popup(at if at is not None else QCursor.pos())
        # in front, so that a click anywhere else takes it away: the
        # shell lets the app whose icon was clicked come forward
        self._menu.activateWindow()


# the icons by their windows, for the messages the windows get
_icons: "weakref.WeakValueDictionary[int, WindowsTrayIcon]" = (
    weakref.WeakValueDictionary()
)


def _release(handles: dict) -> None:
    _icons.pop(handles["hwnd"], None)
    _win32().destroy_window(handles["hwnd"])
    if handles["hicon"]:
        _win32().destroy_icon(handles["hicon"])


def _from_native(point: QPoint) -> QPoint | None:
    """A point in the screen's own pixels as Qt has it, None where no
    screen is."""

    for screen in QGuiApplication.screens():
        geometry = screen.geometry()
        ratio = screen.devicePixelRatio()
        origin = geometry.topLeft()
        if QRect(origin, geometry.size() * ratio).contains(point):
            return origin + (point - origin) / ratio
    return None


def _hicon(icon: QIcon) -> int | None:
    from PyQt5.QtWinExtras import QtWin

    size = _win32().small_icon_size()
    pixmap = icon.pixmap(QSize(size, size))
    if pixmap.isNull():
        return None

    if pixmap.width() != size or pixmap.height() != size:
        pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    hicon = QtWin.toHICON(pixmap)
    return int(hicon) if hicon else None


@functools.cache
def _win32():
    """The Windows calls, made on first use: the module is imported on
    every system."""

    from gridplayer.utils import win32_tray_api

    return win32_tray_api.Api(_on_window_message)


def _on_window_message(
    hwnd: int, message: int, wparam: int, lparam: int, taskbar_created: int
):
    """A message to an icon's window: True if it was one of the icon's."""

    icon = _icons.get(hwnd)
    if icon is None:
        return False

    if message == CALLBACK_MESSAGE:
        # with NOTIFYICON_VERSION_4, what happened is in lparam's low word,
        # where the icon is in wparam
        icon.on_callback(
            lparam & 0xFFFF, QPoint(_signed(wparam), _signed(wparam >> 16))
        )
        return True

    if message == taskbar_created:
        icon.on_taskbar_created()

    return False


def _signed(word: int) -> int:
    word &= 0xFFFF
    return word - 0x10000 if word & 0x8000 else word
