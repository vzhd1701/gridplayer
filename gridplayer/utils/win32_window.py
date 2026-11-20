"""Windows 11: the windows' title bars and borders in the theme's colours.

The player's title bar is its background, the videos below it; a dialog's
stands apart from what it holds. Light or dark title bar text and buttons
are Qt's: it marks every window dark or light by the colour scheme it is
told (theme._tell_qt_the_scheme).
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import QApplication, QWidget

from gridplayer.params import env
from gridplayer.params.theme import current_colors
from gridplayer.utils.qt import CAPTION_AS_BACKGROUND

_DWMWA_CAPTION_COLOR = 35
_DWMWA_BORDER_COLOR = 34
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMSBT_NONE = 1

# the kinds of window with a title bar, unless frameless
_TITLED = frozenset({Qt.WindowType.Window, Qt.WindowType.Dialog, Qt.WindowType.Tool})

_dwmapi = None

_WIN11_BUILD = 22000  # first Windows 11 build number


def _is_windows_11() -> bool:
    if not env.IS_WINDOWS:
        return False
    try:
        return sys.getwindowsversion().build >= _WIN11_BUILD
    except AttributeError:
        # sys.getwindowsversion only exists on Windows; defensive fallback
        return False


def _colorref(color: QColor) -> int:
    return int(color.red()) | (int(color.green()) << 8) | (int(color.blue()) << 16)


def _load_dwmapi():
    global _dwmapi
    if _dwmapi is not None:
        return
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long


def _dwm_set(hwnd, attribute, value: int) -> None:
    data = ctypes.c_int(value)
    _dwmapi.DwmSetWindowAttribute(
        hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data)
    )


def _palette(widget: QWidget):
    """The one it is drawn with once the theme has changed. A window that
    hasn't its own takes the application's in an event yet to come, while
    apply_theme asks: a dialog's would still be the old theme's."""

    if widget.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
        return widget.palette()
    return QApplication.palette(widget)


def _has_title_bar(widget: QWidget) -> bool:
    return (
        widget.windowType() in _TITLED
        and not widget.windowFlags() & Qt.WindowType.FramelessWindowHint
    )


def _caption_color(widget: QWidget) -> QColor:
    if widget.property(CAPTION_AS_BACKGROUND):
        return _palette(widget).color(widget.backgroundRole())
    return QColor(current_colors()["caption"])


def apply_native_background(widget: QWidget, *, create: bool = True) -> None:
    if not _is_windows_11() or not _has_title_bar(widget):
        return
    if not create and widget.windowHandle() is None:
        return

    _load_dwmapi()
    hwnd = wintypes.HWND(int(widget.winId()))
    _dwm_set(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, _DWMSBT_NONE)
    _dwm_set(hwnd, _DWMWA_CAPTION_COLOR, _colorref(_caption_color(widget)))
    _dwm_set(hwnd, _DWMWA_BORDER_COLOR, _colorref(QColor(current_colors()["border"])))


class _TitleBars(QObject):
    """Each window coloured as it is shown, before it is on the screen."""

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            apply_native_background(watched)
        return False


def color_title_bars(app) -> None:
    """Every window's title bar in the theme's colours, on Windows 11; again
    as the theme changes (theme._apply_native_window_chrome)."""

    if QGuiApplication.platformName() != "windows" or not _is_windows_11():
        return

    app._title_bars = _TitleBars(app)
    app.installEventFilter(app._title_bars)
