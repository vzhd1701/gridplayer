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
import math
from ctypes import wintypes

from PyQt5.QtCore import QRect
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QWidget

Rect = tuple[int, int, int, int]
# a rect in fractions of a pixel, as a Qt one comes out in the window's own
Area = tuple[float, float, float, float]

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


def fit_vlc_vout_windows(surface: QWidget, was_shown: QRect, shown: QRect) -> None:
    """Size VLC's windows to the surface, just resized.

    `was_shown` and `shown` are the parts of the surface on show before and
    after, in its own coordinates: VLC's last picture is stretched so that
    what was on show of it is on show again, at the new size.

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

    if was_shown.isEmpty() or shown.isEmpty():
        return

    ratio = surface.devicePixelRatioF()
    _fit_vlc_windows(
        int(surface.winId()), _native(was_shown, ratio), _native(shown, ratio)
    )


def _native(rect: QRect, ratio: float) -> Area:
    return (
        rect.x() * ratio,
        rect.y() * ratio,
        rect.width() * ratio,
        rect.height() * ratio,
    )


def _fit_vlc_windows(surface: int, was_shown: Area, shown: Area) -> None:
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
        pictures = [(child, _rect_in(child, main)) for child in _children(main)]

        _set_rect(main, (0, 0, width, height))

        for child, rect in pictures:
            if rect[2] > 0 and rect[3] > 0:
                _set_rect(child, _mapped(rect, was_shown, shown))


def _mapped(rect: Rect, was_shown: Area, shown: Area) -> Rect:
    """Where the picture window goes for what was on show to fill what is.

    Not all of VLC's picture is on show: the surface is grown past it by a
    margin on every side (see vlc_hw_crop_border_offset), and what VLC draws
    there stays out of sight. It leaves strips of black there, and rows of
    black at the bottom where its picture window is not whole 4-row blocks
    (see VLC_WINDOWS_PICTURE_ROW_BLOCK). Fitted into the new size whole, the
    picture brought them into sight, stretched by the ~3x of a cell going
    single: a black line at the bottom. Taken from inside what was on show,
    a pixel in on every side for the rounding, they stay out of sight at any
    scale.

    The picture is stretched where the cell changes shape, for the moment
    it takes VLC to draw one of its own.
    """
    from_x, from_y, from_width, from_height = was_shown
    if from_width > 2 and from_height > 2:
        from_x, from_y = from_x + 1, from_y + 1
        from_width, from_height = from_width - 2, from_height - 2

    to_x, to_y, to_width, to_height = shown
    scale_x = to_width / from_width
    scale_y = to_height / from_height

    x, y, width, height = rect
    left = math.floor(to_x + (x - from_x) * scale_x)
    top = math.floor(to_y + (y - from_y) * scale_y)
    right = math.ceil(to_x + (x + width - from_x) * scale_x)
    bottom = math.ceil(to_y + (y + height - from_y) * scale_y)

    return left, top, right - left, bottom - top


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
