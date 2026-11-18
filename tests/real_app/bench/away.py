"""Windows: a real window, on a virtual desktop the user isn't on, never activated.

Import it before the player is made. A window there is cloaked, so the compositor doesn't draw it:
what it costs to reach the screen is still missing from a run, only the app's own path is real.

Should the user's desktop change, or something of the run's come to the foreground, the run ends
with EXIT_DESKTOP_CHANGED at once, and run.py stops there.
"""

import ctypes
import os
import threading
import time
import uuid
import winreg
from ctypes import wintypes
from pathlib import Path

import psutil
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QWindow
from PyQt6.QtWidgets import QWidget

EXIT_DESKTOP_CHANGED = 77
WINDOW_GEOMETRY = (0, 0, 1920, 1080)

_DESKTOPS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
_GWL_STYLE = -16
_WS_CHILD = 0x40000000
_WS_POPUP = 0x80000000
_PW_RENDERFULLCONTENT = 2
_POLL_S = 0.1

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.UINT,
]
gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]

_SRCCOPY = 0x00CC0020
_CAPTUREBLT = 0x40000000


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]


def _desktops() -> tuple[bytes, list[bytes]]:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _DESKTOPS_KEY) as key:
        current = winreg.QueryValueEx(key, "CurrentVirtualDesktop")[0]
        ids = winreg.QueryValueEx(key, "VirtualDesktopIDs")[0]

    return current, [ids[i : i + 16] for i in range(0, len(ids), 16)]


def _desktop_manager():
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    clsid = _GUID.from_buffer_copy(
        uuid.UUID("aa509086-5ca9-4c25-8f95-589d3c07b48a").bytes_le
    )
    iid = _GUID.from_buffer_copy(
        uuid.UUID("a5cd92ff-29be-454c-8d04-d82879fb3f1b").bytes_le
    )
    manager = ctypes.c_void_p()
    hresult = ole32.CoCreateInstance(
        ctypes.byref(clsid),
        None,
        1 | 4,  # in-process or local server
        ctypes.byref(iid),
        ctypes.byref(manager),
    )
    if hresult != 0:
        raise OSError(f"IVirtualDesktopManager: {hresult:#x}")

    return manager


def _move_to_desktop(hwnd: int, desktop: bytes) -> None:
    manager = _desktop_manager()
    vtable = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    move = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(_GUID)
    )(vtable[5])
    guid = _GUID.from_buffer_copy(desktop)

    hresult = move(manager, hwnd, ctypes.byref(guid))
    if hresult != 0:
        raise OSError(f"MoveWindowToDesktop: {hresult & 0xFFFFFFFF:#x}")


class _ThrottlingState(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    ]


def _never_throttled() -> None:
    """Run as if seen. Windows 11 makes a process whose windows no one sees
    slower to wake, a few seconds in: every timer to 15.6 ms, which held a
    120 fps video to 64 frames a second and had mpv drop the rest."""

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]

    process_power_throttling = 4
    # execution speed and timer resolution, both never throttled
    state = _ThrottlingState(Version=1, ControlMask=0x1 | 0x4, StateMask=0)

    if not kernel32.SetProcessInformation(
        kernel32.GetCurrentProcess(),
        process_power_throttling,
        ctypes.byref(state),
        ctypes.sizeof(state),
    ):
        raise ctypes.WinError()


def _ignore(*_args, **_kwargs) -> None:
    pass


def _child_before_parent(real_set_parent):
    def set_parent(self, *args):
        # Win32's SetParent activates what is still a popup then, even hidden
        hwnd = int(self.winId())
        style = user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, (style & ~_WS_POPUP) | _WS_CHILD)
        return real_set_parent(self, *args)

    return set_parent


def _watch(user_desktop: bytes, out: Path) -> None:
    me = psutil.Process()

    while True:
        time.sleep(_POLL_S)

        current, _ids = _desktops()
        if current != user_desktop:
            _stop(out, "the desktop changed")

        pid = wintypes.DWORD()
        foreground = user32.GetForegroundWindow()
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
        ours = {me.pid} | {c.pid for c in me.children(recursive=True)}
        if pid.value in ours:
            _stop(
                out,
                f"process {pid.value} came to the foreground: {_described(foreground)}",
            )


def _described(hwnd) -> str:
    """Which window it is: its class and title, and its parent's."""

    def one(handle):
        name = ctypes.create_unicode_buffer(256)
        title = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(handle, name, 256)
        user32.GetWindowTextW(handle, title, 256)
        style = user32.GetWindowLongPtrW(handle, _GWL_STYLE)
        return f"{name.value!r} {title.value!r} style {style & 0xFFFFFFFF:#x}"

    parent = user32.GetParent(hwnd)
    return one(hwnd) + (f", parent {one(parent)}" if parent else "")


def _stop(out: Path, why: str) -> None:
    (out / "desktop_watch.txt").write_text(why)
    os._exit(EXIT_DESKTOP_CHANGED)


def install(out: Path) -> None:
    """Every window of the app goes to the other desktop from here on."""

    user_desktop, ids = _desktops()
    others = [one for one in ids if one != user_desktop]
    if not others:
        raise RuntimeError("There's no other virtual desktop to run on")
    desktop = others[0]

    def place(window, show_now) -> None:
        window.setGeometry(-4000, -4000, *WINDOW_GEOMETRY[2:])
        show_now()
        _move_to_desktop(int(window.winId()), desktop)
        window.setGeometry(*WINDOW_GEOMETRY)

    _never_activated(place)

    threading.Thread(
        target=_watch, args=(user_desktop, out), daemon=True, name="desktop-watch"
    ).start()


def install_on_screen() -> None:
    """The player on the user's own screen instead, still never activated, so
    what reaching the screen costs is in the run. For someone who has said yes
    to a window over their work for that long."""

    def place(window, show_now) -> None:
        window.setGeometry(*WINDOW_GEOMETRY)
        show_now()

    _never_activated(place)


def _never_activated(place) -> None:
    """The player shown by `place(window, show_now)`, which calls show_now()
    to show it, and nothing of the app ever activated or made to fill the
    screen."""

    real_show = QWidget.show

    def show(self):
        # only the player has these, and everything else goes along with it
        if not hasattr(self, "_context"):
            real_show(self)
            return

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
        place(self, lambda: real_show(self))
        self._context.commands.activate_window = _ignore

    QWidget.show = show
    _never_throttled()
    QWidget.activateWindow = _ignore
    QWidget.showMaximized = _ignore
    QWidget.showFullScreen = _ignore
    QWindow.setParent = _child_before_parent(QWindow.setParent)


def capture(widget, path: Path) -> None:
    """The window as the compositor would have it, video output included."""

    hwnd = int(widget.winId())
    _grab(
        path,
        widget.width(),
        widget.height(),
        lambda dc, _screen: user32.PrintWindow(hwnd, dc, _PW_RENDERFULLCONTENT),
    )


def capture_screen(widget, path: Path) -> None:
    """The window as it is on the screen right now, as far as it is shown:
    an on-screen run's (install_on_screen), mid-resize."""

    top_left = widget.mapToGlobal(widget.rect().topLeft())
    x, y = top_left.x(), top_left.y()
    width, height = widget.width(), widget.height()

    def blit(dc, screen):
        gdi32.BitBlt(dc, 0, 0, width, height, screen, x, y, _SRCCOPY | _CAPTUREBLT)

    _grab(path, width, height, blit)


def _grab(path: Path, width: int, height: int, draw) -> None:
    screen = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(dc, bitmap)
    draw(dc, screen)

    image = QImage(width, height, QImage.Format.Format_RGB32)
    header = (ctypes.c_int32 * 10)(40, width, -height, 0x200001)
    pixels = ctypes.c_void_p(int(image.bits()))
    gdi32.GetDIBits(dc, bitmap, 0, height, pixels, header, 0)
    image.save(str(path))

    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    user32.ReleaseDC(None, screen)
