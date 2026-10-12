"""The player's button in the taskbar (the Dock on macOS) taken away, and
put back, for a player that is to live in the tray alone.

Each system has its own way, and Wayland none at all:

* Windows gives no taskbar button to a window that another one owns, and
  still has it in Alt+Tab. Qt sets the owner from the window's transient
  parent every time it is shown, so the player is given one: a window of
  its own that is never shown. A window already on screen keeps the button
  it has until told otherwise, which is what ITaskbarList is for.
* macOS has no Dock icon for an app that is an accessory, which also
  leaves it out of Cmd+Tab and the menu bar its menus.
* X11 window managers leave a window out of the taskbar that says so in
  its _NET_WM_STATE. The window manager clears the state as the window is
  hidden, and Qt keeps what it finds there as it shows it again, so it is
  written before every show. Not with GNOME's: it takes minimizing away
  from such a window, the button in its title bar left doing nothing.
"""

import ctypes
import functools
import logging
from enum import Enum, auto

from PyQt5.QtGui import QGuiApplication, QWindow
from PyQt5.QtWidgets import QWidget

from gridplayer.params import env

_log = logging.getLogger(__name__)


class TaskbarHidingBlocker(Enum):
    # no way to ask for it at all
    WAYLAND = auto()
    # GNOME Shell, and the window managers made from its Mutter: a window
    # left out of the taskbar can't be minimized
    GNOME = auto()


def taskbar_hiding_blocker() -> TaskbarHidingBlocker | None:
    """What keeps the taskbar button from being taken away, if anything."""

    if env.IS_WINDOWS or env.IS_MACOS:
        return None

    if QGuiApplication.platformName() != "xcb":
        return TaskbarHidingBlocker.WAYLAND

    if "mutter" in _x11_wm_name() or "gnome" in _x11_wm_name():
        return TaskbarHidingBlocker.GNOME

    return None


def is_taskbar_hiding_available() -> bool:
    return taskbar_hiding_blocker() is None


def set_hidden_from_taskbar(
    widget: QWidget, is_hidden: bool, *, is_showing: bool = False
) -> None:
    """Take the window's button away, or put it back.

    ``is_showing`` is for a window about to be shown, from its show event,
    which comes before the window is on screen.
    """

    if not is_taskbar_hiding_available():
        return

    try:
        if env.IS_WINDOWS:
            _set_hidden_windows(widget, is_hidden)
        elif env.IS_MACOS:
            _set_hidden_macos(is_hidden)
        else:
            _set_hidden_x11(widget, is_hidden, is_mapped=not is_showing)
    except Exception:
        _log.warning("Could not change the taskbar button", exc_info=True)


# Windows

_GWLP_HWNDPARENT = -8
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2

_CLSID_TASKBAR_LIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
_IID_ITASKBAR_LIST = "{56FDF342-FD6D-11d0-958A-006097C9A090}"

# ITaskbarList's methods, after IUnknown's three
_HR_INIT = 3
_ADD_TAB = 4
_DELETE_TAB = 5

_owner: QWindow | None = None


def _set_hidden_windows(widget: QWidget, is_hidden: bool) -> None:
    global _owner

    hwnd = int(widget.winId())
    window = widget.windowHandle()

    if is_hidden and _owner is None:
        _owner = QWindow()
        _owner.create()

    owner = _owner if is_hidden else None

    if window.transientParent() is owner:
        return

    window.setTransientParent(owner)

    # Qt only hands it on to the window as it is shown
    owner_hwnd = int(owner.winId()) if owner is not None else 0
    _set_window_owner(hwnd, owner_hwnd)

    if widget.isVisible():
        _TaskbarList().set_tab(hwnd, is_shown=not is_hidden)


def _set_window_owner(hwnd: int, owner_hwnd: int) -> None:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")

    # SetWindowLongPtrW is a macro for SetWindowLongW in 32-bit Windows
    set_window_long = getattr(user32, "SetWindowLongPtrW", None)
    if set_window_long is None:
        set_window_long = user32.SetWindowLongW

    set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_window_long.restype = ctypes.c_ssize_t

    set_window_long(hwnd, _GWLP_HWNDPARENT, owner_hwnd)


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_text(cls, text: str) -> "_Guid":
        guid = cls()
        ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(guid))
        return guid


class _TaskbarList:
    """The taskbar's ITaskbarList, called through its table by hand."""

    def __init__(self):
        ole32 = ctypes.oledll.ole32

        # Qt has the GUI thread in a single-threaded apartment already; one
        # more join is a no-op then, and harmless if it has not
        ctypes.windll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)

        self._ptr = ctypes.c_void_p()

        ole32.CoCreateInstance(
            ctypes.byref(_Guid.from_text(_CLSID_TASKBAR_LIST)),
            None,
            _CLSCTX_INPROC_SERVER,
            ctypes.byref(_Guid.from_text(_IID_ITASKBAR_LIST)),
            ctypes.byref(self._ptr),
        )

        try:
            self._call(_HR_INIT)
        except OSError:
            self._release()
            raise

    def set_tab(self, hwnd: int, is_shown: bool) -> None:
        try:
            self._call(_ADD_TAB if is_shown else _DELETE_TAB, hwnd)
        finally:
            self._release()

    def _call(self, index, *hwnds):
        from ctypes import wintypes

        table = ctypes.cast(
            self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents

        prototype = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, *(wintypes.HWND for _ in hwnds)
        )

        return prototype(table[index])(self._ptr, *hwnds)

    def _release(self):
        table = ctypes.cast(
            self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents

        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(self._ptr)


# macOS


def _set_hidden_macos(is_hidden: bool) -> None:
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSApplicationActivationPolicyRegular,
    )

    app = NSApplication.sharedApplication()

    if is_hidden:
        policy = NSApplicationActivationPolicyAccessory
    else:
        policy = NSApplicationActivationPolicyRegular

    if app.activationPolicy() == policy:
        return

    app.setActivationPolicy_(policy)


# X11

_CLIENT_MESSAGE = 33
_SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
_SUBSTRUCTURE_REDIRECT_MASK = 1 << 20
_PROP_MODE_APPEND = 2
_XA_ATOM = 4
_XA_WINDOW = 33

_NET_WM_STATE_REMOVE = 0
_NET_WM_STATE_ADD = 1
# what the request comes from: an ordinary application
_SOURCE_APPLICATION = 1


@functools.cache
def _x11_wm_name() -> str:
    """The window manager's name, lower case, as it gives it on its check
    window: "GNOME Shell", "KWin", "Xfwm4", "Mutter (Muffin)". Empty where
    it can't be read."""

    try:
        return _read_x11_wm_name().lower()
    except Exception:
        _log.debug("Could not read the window manager's name", exc_info=True)
        return ""


def _read_x11_wm_name() -> str:
    from gridplayer.utils.compositor_linux import _load_libx11

    x11 = _load_libx11()
    if x11 is None:
        return ""

    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XGetWindowProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    dpy = x11.XOpenDisplay(None)
    if not dpy:
        return ""

    def read(window, name, kind):
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        count = ctypes.c_ulong()
        left = ctypes.c_ulong()
        data = ctypes.c_void_p()

        x11.XGetWindowProperty(
            dpy,
            window,
            x11.XInternAtom(dpy, name, 0),
            0,
            1024,
            0,
            kind,
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(count),
            ctypes.byref(left),
            ctypes.byref(data),
        )

        if not data.value:
            return None

        try:
            if actual_format.value == 32:
                return ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0]
            return ctypes.string_at(data, count.value).decode("utf-8", "replace")
        finally:
            x11.XFree(data)

    try:
        check = read(
            x11.XDefaultRootWindow(dpy), b"_NET_SUPPORTING_WM_CHECK", _XA_WINDOW
        )
        if not check:
            return ""

        utf8 = x11.XInternAtom(dpy, b"UTF8_STRING", 0)

        return read(check, b"_NET_WM_NAME", utf8) or ""
    finally:
        x11.XCloseDisplay(dpy)


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [("xclient", _XClientMessageEvent), ("pad", ctypes.c_long * 24)]


def _set_hidden_x11(widget: QWidget, is_hidden: bool, is_mapped: bool) -> None:
    from gridplayer.utils.compositor_linux import _load_libx11

    x11 = _load_libx11()
    if x11 is None:
        return

    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XSendEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.POINTER(_XEvent),
    ]
    x11.XChangeProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    window_id = int(widget.winId())

    dpy = x11.XOpenDisplay(None)
    if not dpy:
        _log.debug("XOpenDisplay failed")
        return

    try:
        wm_state = x11.XInternAtom(dpy, b"_NET_WM_STATE", 0)
        skips = (ctypes.c_ulong * 2)(
            x11.XInternAtom(dpy, b"_NET_WM_STATE_SKIP_TASKBAR", 0),
            x11.XInternAtom(dpy, b"_NET_WM_STATE_SKIP_PAGER", 0),
        )

        if is_mapped:
            event = _XEvent()
            event.xclient.type = _CLIENT_MESSAGE
            event.xclient.send_event = 1
            event.xclient.window = window_id
            event.xclient.message_type = wm_state
            event.xclient.format = 32
            event.xclient.data[0] = (
                _NET_WM_STATE_ADD if is_hidden else _NET_WM_STATE_REMOVE
            )
            event.xclient.data[1] = skips[0]
            event.xclient.data[2] = skips[1]
            event.xclient.data[3] = _SOURCE_APPLICATION

            x11.XSendEvent(
                dpy,
                x11.XDefaultRootWindow(dpy),
                0,
                _SUBSTRUCTURE_NOTIFY_MASK | _SUBSTRUCTURE_REDIRECT_MASK,
                ctypes.byref(event),
            )

        # not on screen, the state is the window's own to write: cleared by
        # the window manager as it was hidden, there is nothing to take out
        elif is_hidden:
            x11.XChangeProperty(
                dpy,
                window_id,
                wm_state,
                _XA_ATOM,
                32,
                _PROP_MODE_APPEND,
                ctypes.cast(skips, ctypes.c_void_p),
                len(skips),
            )

        x11.XFlush(dpy)
    finally:
        x11.XCloseDisplay(dpy)
