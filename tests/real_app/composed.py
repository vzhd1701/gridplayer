"""A widget as Windows composes it, or as the X server has it, for what grab()
can't see: MPV's Direct output, where mpv draws into a native window of its own.
Only for a real window: on Windows the windows platform (see bench/away.py), on
screen or on another virtual desktop; on Linux xcb."""

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtGui import QGuiApplication, QImage
from PyQt5.QtWidgets import QApplication, QWidget

# the client area only, with what DirectComposition draws in it
_PW_CLIENTONLY = 1
_PW_RENDERFULLCONTENT = 2

# a frame or two of the screen's, for a window hidden to be gone from what's composed
_COMPOSE_WAIT_S = 0.05

_DIB_RGB_COLORS = 0
_BI_RGB = 0


# GNOME Shell takes a screenshot for the one that owns org.gnome.Screenshot on
# the session bus, and only for that one. argv: path x y width height.
_GNOME_SHOT = """
import sys
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtDBus import QDBusConnection, QDBusInterface

app = QCoreApplication(sys.argv)
bus = QDBusConnection.sessionBus()
if not bus.registerService("org.gnome.Screenshot"):
    sys.exit(bus.lastError().message())
shell = QDBusInterface(
    "org.gnome.Shell.Screenshot",
    "/org/gnome/Shell/Screenshot",
    "org.gnome.Shell.Screenshot",
    bus,
)
x, y, w, h = map(int, sys.argv[2:6])
reply = shell.call("ScreenshotArea", x, y, w, h, False, sys.argv[1])
if reply.errorMessage():
    sys.exit(reply.errorMessage())
"""


def has_own_window_video(widget: QWidget) -> bool:
    """Whether a video in it is drawn by mpv into a window of its own."""

    from gridplayer.widgets.video_frame_mpv_window import VideoFrameMpvWindow

    return isinstance(widget, VideoFrameMpvWindow) or bool(
        widget.findChildren(VideoFrameMpvWindow)
    )


def is_direct(block) -> bool:
    """Whether a cell's video is on MPV's Direct output, mpv drawing into a
    window of its own: no frames here to count or to read."""

    return block.video_driver is not None and has_own_window_video(block.video_driver)


def has_direct_picture(block) -> bool:
    """A cell on Direct has its picture on show as soon as the loading status is
    off it."""

    return block.is_video_initialized and not block.video_status.isVisible()


def _origin(widget: QWidget) -> QPoint:
    """Where the widget is in its window."""

    window = widget.window()

    return widget.mapTo(window, QPoint(0, 0)) if widget is not window else QPoint()


def grab_composed(widget: QWidget) -> QImage:
    """As grab() gives it: in the screen's pixels, at the widget's ratio. The
    cells' overlays and loading statuses taken off for it, which are windows of
    their own over the video, as grab() leaves them out."""

    over = _windows_over_videos(widget)

    for one in over:
        one.hide()

    if over:
        # for Windows to compose the window without them
        QApplication.processEvents()
        time.sleep(_COMPOSE_WAIT_S)

    try:
        return _grab_composed(widget)
    finally:
        for one in over:
            one.show()


def _windows_over_videos(widget: QWidget) -> list[QWidget]:
    from gridplayer.widgets.video_block import VideoBlock

    window = widget.window()
    blocks = window.findChildren(VideoBlock)

    return [
        one
        for block in blocks
        for one in (getattr(block, "overlay", None), block.video_status)
        if one is not None and one.isVisible()
    ]


def _grab_composed(widget: QWidget) -> QImage:
    if not sys.platform.startswith("win"):
        return _grab_from_x11(widget)

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

    origin = _origin(widget)
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


def _grab_from_x11(widget: QWidget) -> QImage:
    """What the X server has in the window there, mpv's window in it included.
    Under XWayland the X server has nothing of what GL draws: the screen is
    taken from the compositor instead, by grim where it's there (sway), or by
    asking GNOME Shell."""

    grim = shutil.which("grim")
    is_gnome = shutil.which("gnome-shell") is not None
    if os.environ.get("WAYLAND_DISPLAY") and (grim or is_gnome):
        # what was hidden or drawn just now, which the compositor shows a frame on
        QApplication.processEvents()
        time.sleep(_COMPOSE_WAIT_S)

        at = widget.mapToGlobal(QPoint(0, 0))
        area = (at.x(), at.y(), widget.width(), widget.height())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grab.png"
            # the compositor's socket is in the session's own, which a run moves
            runtime = f"/run/user/{os.getuid()}"
            env = {**os.environ, "XDG_RUNTIME_DIR": runtime}
            if grim:
                x, y, w, h = area
                command = [grim, "-g", f"{x},{y} {w}x{h}", str(path)]
            else:
                # the run has no session bus of its own: the desktop's
                env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
                env["QT_QPA_PLATFORM"] = "offscreen"
                command = [
                    sys.executable,
                    "-c",
                    _GNOME_SHOT,
                    str(path),
                    *map(str, area),
                ]
            subprocess.run(command, check=True, env=env)
            return QImage(str(path))

    origin = _origin(widget)

    return (
        QGuiApplication.primaryScreen()
        .grabWindow(
            int(widget.window().winId()),
            origin.x(),
            origin.y(),
            widget.width(),
            widget.height(),
        )
        .toImage()
    )
