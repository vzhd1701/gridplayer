import ctypes
import logging
import winreg
from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, QTimer
from PyQt5.QtWidgets import QApplication

_WM_SETTINGCHANGE = 0x001A
_WM_THEMECHANGED = 0x031A
_RETRY_MS = 50
_RETRY_MAX = 16

_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


class _MSG(ctypes.Structure):
    _fields_ = (
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    )


def windows_is_dark() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        logging.getLogger(__name__).exception("Could not read system theme")
        return False
    else:
        return value == 0


def _is_color_scheme_message(message) -> bool:
    msg = _MSG.from_address(int(message))
    if msg.message == _WM_THEMECHANGED:
        return True
    if msg.message != _WM_SETTINGCHANGE or not msg.lParam:
        return False
    try:
        return ctypes.wstring_at(msg.lParam) == "ImmersiveColorSet"
    except (ValueError, OSError):
        return False


class _ThemeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, on_change):
        super().__init__()
        self._on_change = on_change

    def nativeEventFilter(self, eventType, message):
        event_type = bytes(eventType)
        if event_type in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            if _is_color_scheme_message(message):
                self._on_change()
        # PyQt5 requires (filter, result) — a bare bool raises TypeError.
        return False, 0


class WindowsThemeWatcher(QObject):
    def __init__(self, callback, parent=None):
        super().__init__(parent)

        self._callback = callback
        self._applied_dark = windows_is_dark()
        self._retries_left = 0

        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(_RETRY_MS)
        self._retry.timeout.connect(self._try_apply)

        self._filter = _ThemeEventFilter(self._on_system_theme)
        app = parent if isinstance(parent, QApplication) else QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    def _on_system_theme(self):
        self._retries_left = _RETRY_MAX
        self._try_apply()

    def _try_apply(self):
        dark = windows_is_dark()
        if dark != self._applied_dark:
            self._applied_dark = dark
            self._callback()
            return

        if self._retries_left > 0:
            self._retries_left -= 1
            self._retry.start()
