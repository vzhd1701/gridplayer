"""A widget as Windows composes it, for what grab() can't see: MPV's Direct output,
where mpv draws into a native window of its own. Only for a real window (the
windows platform, see bench/away.py), on screen or on another virtual desktop."""

import ctypes
from ctypes import wintypes

from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QWidget

# the client area only, with what DirectComposition draws in it
_PW_CLIENTONLY = 1
_PW_RENDERFULLCONTENT = 2

_DIB_RGB_COLORS = 0
_BI_RGB = 0


def has_own_window_video(widget: QWidget) -> bool:
    """Whether a video in it is drawn by mpv into a window of its own."""

    from gridplayer.widgets.video_frame_mpv_window import VideoFrameMpvWindow

    return isinstance(widget, VideoFrameMpvWindow) or bool(
        widget.findChildren(VideoFrameMpvWindow)
    )


def grab_composed(widget: QWidget) -> QImage:
    """As grab() gives it: in the screen's pixels, at the widget's ratio."""

    window = widget.window()
    ratio = window.devicePixelRatioF()
    width = round(window.width() * ratio)
    height = round(window.height() * ratio)

    user32 = ctypes.WinDLL("user32")
    gdi32 = ctypes.WinDLL("gdi32")
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
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

    screen = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(dc, bitmap)

    user32.PrintWindow(int(window.winId()), dc, _PW_CLIENTONLY | _PW_RENDERFULLCONTENT)

    image = QImage(width, height, QImage.Format_RGB32)
    # BITMAPINFOHEADER: top-down, 32 bits a pixel
    header = (ctypes.c_int32 * 10)(40, width, -height, (32 << 16) | 1, _BI_RGB)
    gdi32.GetDIBits(dc, bitmap, 0, height, int(image.bits()), header, _DIB_RGB_COLORS)

    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    user32.ReleaseDC(None, screen)

    origin = widget.mapTo(window, QPoint(0, 0)) if widget is not window else QPoint()
    part = image.copy(
        QRect(
            round(origin.x() * ratio),
            round(origin.y() * ratio),
            round(widget.width() * ratio),
            round(widget.height() * ratio),
        )
    )
    part.setDevicePixelRatio(ratio)

    return part
