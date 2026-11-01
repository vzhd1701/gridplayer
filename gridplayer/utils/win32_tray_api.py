"""The Windows calls behind WindowsTrayIcon (see win32_tray), Windows only."""

import ctypes
import logging
from ctypes import wintypes

_log = logging.getLogger(__name__)

_CLASS_NAME = "GridPlayerTrayIconWindow"
_ERROR_CLASS_ALREADY_EXISTS = 1410
_SM_CXSMICON = 49
_MSGFLT_ALLOW = 1
_S_OK = 0

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        # uTimeout too, the two being one
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", GUID),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class Api:
    """The icons' windows, of a class of their own whose messages go to
    on_message(hwnd, message, wparam, lparam, taskbar_created), True for
    one it took; and the calls to the shell."""

    ctypes = ctypes
    GUID = GUID
    NOTIFYICONDATAW = NOTIFYICONDATAW

    def __init__(self, on_message):
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._declare()

        self._on_message = on_message
        # sent to every top window when Explorer starts again
        self.taskbar_created = self._user32.RegisterWindowMessageW("TaskbarCreated")

        # kept, or the window's messages go to a callback that is gone
        self._proc = WNDPROC(self._window_proc)
        self._instance = self._kernel32.GetModuleHandleW(None)

        window_class = WNDCLASSW()
        window_class.lpfnWndProc = self._proc
        window_class.hInstance = self._instance
        window_class.lpszClassName = _CLASS_NAME
        if not self._user32.RegisterClassW(ctypes.byref(window_class)):
            error = ctypes.get_last_error()
            if error != _ERROR_CLASS_ALREADY_EXISTS:
                raise ctypes.WinError(error)

    def make_window(self) -> int:
        """A window never shown, for the icon's messages: a top one, not
        message-only, as those are not told that Explorer started again."""

        hwnd = self._user32.CreateWindowExW(
            0, _CLASS_NAME, "", 0, 0, 0, 0, 0, None, None, self._instance, None
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        # told of it run as admin too, from an Explorer that is not
        self._user32.ChangeWindowMessageFilterEx(
            hwnd, self.taskbar_created, _MSGFLT_ALLOW, None
        )
        return hwnd

    def destroy_window(self, hwnd: int) -> None:
        self._user32.DestroyWindow(hwnd)

    def destroy_icon(self, hicon: int) -> None:
        self._user32.DestroyIcon(hicon)

    def small_icon_size(self) -> int:
        return self._user32.GetSystemMetrics(_SM_CXSMICON) or 16

    def notify(self, message: int, data: NOTIFYICONDATAW) -> bool:
        return bool(self._shell32.Shell_NotifyIconW(message, ctypes.byref(data)))

    def is_up(self, guid: bytes) -> bool:
        """Whether an icon with the GUID is in the tray, anyone's."""

        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(ident)
        ident.guidItem = GUID.from_buffer_copy(guid)
        rect = wintypes.RECT()
        found = self._shell32.Shell_NotifyIconGetRect(
            ctypes.byref(ident), ctypes.byref(rect)
        )
        return found == _S_OK

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if self._on_message(hwnd, message, wparam, lparam, self.taskbar_created):
                return 0
        except Exception:
            _log.exception("Tray icon message %s failed", message)
        return self._user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _declare(self) -> None:
        user32, shell32, kernel32 = self._user32, self._shell32, self._kernel32

        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = LRESULT
        user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterWindowMessageW.restype = wintypes.UINT
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        shell32.Shell_NotifyIconW.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(NOTIFYICONDATAW),
        ]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        shell32.Shell_NotifyIconGetRect.argtypes = [
            ctypes.POINTER(NOTIFYICONIDENTIFIER),
            ctypes.POINTER(wintypes.RECT),
        ]
        shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
        user32.ChangeWindowMessageFilterEx.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        user32.ChangeWindowMessageFilterEx.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
