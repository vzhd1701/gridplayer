"""Windows DWM caption/border chrome. No launch paint tricks."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget

from gridplayer.params import env
from gridplayer.params.theme import current_colors
from gridplayer.utils.darkmode import is_dark_mode

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35
_DWMWA_BORDER_COLOR = 34
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMSBT_NONE = 1

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


def apply_native_background(widget: QWidget, *, create: bool = True) -> None:
    if not _is_windows_11:
        return
    if not create and widget.windowHandle() is None:
        return

    _load_dwmapi()
    hwnd = wintypes.HWND(int(widget.winId()))
    color = widget.palette().color(widget.backgroundRole())
    dark = is_dark_mode()
    _dwm_set(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark))
    _dwm_set(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, _DWMSBT_NONE)
    _dwm_set(hwnd, _DWMWA_CAPTION_COLOR, _colorref(color))
    _dwm_set(hwnd, _DWMWA_BORDER_COLOR, _colorref(QColor(current_colors()["border"])))
