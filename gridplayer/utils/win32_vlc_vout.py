"""VLC's own windows inside a hardware video's surface, on Windows.

VLC does not draw into the window it is given. It makes a "VLC video main"
window inside it, the size of it, and a "VLC video output" window inside that
one, where the picture goes, and presents into the latter. It sizes them to
the window it was given only when its video output thread next looks, which
measured anywhere from at once to ~70ms after the window changed. Until then
the old picture stays its old size: in the top left corner of a cell that
just grew, the rest black, or cut down to its top left corner, zoomed in,
in one that just shrank.

So whoever resizes the surface sizes VLC's windows along with it. VLC's
presentation is stretched over the window it presents into, so its last
picture fills the new size until it draws one for it. Measured entering and
leaving single mode in a 3x3 grid, in every aspect mode: the old picture
showed in 189 of 200 switches without this, in none of 240 with it.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QWidget

Rect = tuple[int, int, int, int]

VLC_MAIN_WINDOW_CLASS = "VLC video main"

_GW_HWNDNEXT = 2
_GW_CHILD = 5

_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_NOOWNERZORDER = 0x0200
# Posted to the thread that owns the window rather than waited for: VLC's
# windows belong to a thread of its own, in another process with VLC_HW.
_SWP_ASYNCWINDOWPOS = 0x4000

_SWP_FLAGS = _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_NOOWNERZORDER | _SWP_ASYNCWINDOWPOS

_user32 = None


def fit_vlc_vout_windows(surface: QWidget) -> None:
    """Size VLC's windows to the surface, just resized.

    Not before resizing it: Qt moves the cell before it resizes what is in
    it, and VLC, seeing the surface moved but not yet resized, could size
    its windows back to the old size after this sized them to the new one.
    Whatever VLC does once the surface has its new size agrees with this,
    and VLC places its picture window itself then, which this only stands
    in for until it does. So tell VLC about the view after this, not before
    (see VideoFrameVLCHW.adjust_view): woken by it in between this reading
    its windows and resizing them, VLC could place the picture window there
    and then and be overruled by this, with nothing left to make it look
    again.

    Nothing to do where nobody sees it: VLC catches up by itself.
    """
    if QGuiApplication.platformName() != "windows":
        return

    if not surface.isVisible():
        return

    _fit_vlc_windows(int(surface.winId()))


def _fit_vlc_windows(surface: int) -> None:
    width, height = _client_size(surface)
    if width <= 0 or height <= 0:
        return

    for main in _children(surface):
        if not _class_name(main).startswith(VLC_MAIN_WINDOW_CLASS):
            continue

        main_width, main_height = _client_size(main)
        if main_width <= 0 or main_height <= 0:
            continue

        if (main_width, main_height) == (width, height):
            continue

        # the picture window first: read where VLC has it in the old size
        scale_x = width / main_width
        scale_y = height / main_height
        pictures = [(child, _rect_in(child, main)) for child in _children(main)]

        _set_rect(main, (0, 0, width, height))

        for child, (x, y, w, h) in pictures:
            _set_rect(
                child,
                (
                    round(x * scale_x),
                    round(y * scale_y),
                    round(w * scale_x),
                    round(h * scale_y),
                ),
            )


def _load_user32():
    global _user32
    if _user32 is not None:
        return _user32

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.MapWindowPoints.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.POINTER(wintypes.POINT),
        wintypes.UINT,
    ]
    user32.MapWindowPoints.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    _user32 = user32
    return _user32


def _children(hwnd: int) -> list[int]:
    user32 = _load_user32()

    children = []
    child = user32.GetWindow(hwnd, _GW_CHILD)
    while child:
        children.append(child)
        child = user32.GetWindow(child, _GW_HWNDNEXT)

    return children


def _class_name(hwnd: int) -> str:
    name = ctypes.create_unicode_buffer(64)
    _load_user32().GetClassNameW(hwnd, name, len(name))
    return name.value


def _client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not _load_user32().GetClientRect(hwnd, ctypes.byref(rect)):
        return 0, 0
    return rect.right, rect.bottom


def _rect_in(hwnd: int, parent: int) -> Rect:
    """Where the window is in the parent's client area."""

    user32 = _load_user32()

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    corners = (wintypes.POINT * 2)(
        wintypes.POINT(rect.left, rect.top),
        wintypes.POINT(rect.right, rect.bottom),
    )
    user32.MapWindowPoints(None, parent, corners, 2)

    top_left, bottom_right = corners
    return (
        top_left.x,
        top_left.y,
        bottom_right.x - top_left.x,
        bottom_right.y - top_left.y,
    )


def _set_rect(hwnd: int, rect: Rect) -> None:
    x, y, width, height = rect
    _load_user32().SetWindowPos(hwnd, None, x, y, width, height, _SWP_FLAGS)
