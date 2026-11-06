"""A GL context for the render thread, with Qt left out of it.

Nothing is drawn with GL in the window (see renderer.py), so all mpv needs is
a context current on its thread, and asking Qt for one comes with strings
attached. On X11 the app runs with QT_XCB_GL_INTEGRATION=none, as the VLC
drivers' forked processes crash on a GL inherited from the parent, and Qt can't
make a context like that. And Qt's offscreen platform has none at all on
Windows, which is what the real-app scenarios run on. Made by hand it needs
nothing from the app at startup and nothing changes for VLC.

Everything here runs on the render thread.
"""

import ctypes
import logging

from gridplayer.params import env

_log = logging.getLogger(__name__)

# Qt's platform -> the library for a connection to its display, its calls to open
# and close one, and what mpv calls the result
_NATIVE_DISPLAYS = {
    "xcb": ("libX11.so.6", "XOpenDisplay", "XCloseDisplay", "x11_display"),
    "wayland": (
        "libwayland-client.so.0",
        "wl_display_connect",
        "wl_display_disconnect",
        "wl_display",
    ),
}


class GLContextError(RuntimeError):
    """No GL context to be had; the message says what went wrong."""


class EGLContext:
    """Linux: a pbuffer context on a connection of its own to the display.

    mpv uses the display it is given for VAAPI interop, without which it goes
    no further than vaapi-copy. PyQt5 doesn't give out Qt's on Wayland, and on
    X11 sharing it would have this thread on Qt's connection; both are happy
    with their own. One per renderer, closed along with it.
    """

    _NONE = 0x3038
    _PBUFFER_BIT = 0x0001
    _OPENGL_BIT = 0x0008
    _SURFACE_TYPE = 0x3033
    _RENDERABLE_TYPE = 0x3040
    _RED_SIZE = 0x3024
    _GREEN_SIZE = 0x3023
    _BLUE_SIZE = 0x3022
    _WIDTH = 0x3057
    _HEIGHT = 0x3056
    _OPENGL_API = 0x30A2
    _PLATFORM_SURFACELESS = 0x31DD
    _EXTENSIONS = 0x3055

    def __init__(self, platform: str):
        self._platform = platform
        self._egl = self._load_egl()
        self._libgl = None
        self._native_display = None
        self._native_param = None
        self._native_close = None
        self._display = None
        self._surface = None
        self._context = None

        self._display = self._open_display()

        major, minor = ctypes.c_int(), ctypes.c_int()
        if not self._egl.eglInitialize(
            self._display, ctypes.byref(major), ctypes.byref(minor)
        ):
            raise GLContextError(f"eglInitialize failed: {self._error()}")

        if not self._egl.eglBindAPI(self._OPENGL_API):
            raise GLContextError(f"Desktop OpenGL not offered: {self._error()}")

        self._make_current()

        _log.debug(f"EGL {major.value}.{minor.value} on {platform}")

    @staticmethod
    def _load_egl():
        try:
            egl = ctypes.CDLL("libEGL.so.1")
        except OSError as e:
            raise GLContextError(f"libEGL not found: {e}") from e

        c = ctypes
        for name, restype, argtypes in (
            ("eglGetDisplay", c.c_void_p, [c.c_void_p]),
            ("eglGetPlatformDisplay", c.c_void_p, [c.c_uint, c.c_void_p, c.c_void_p]),
            ("eglInitialize", c.c_uint, [c.c_void_p, c.c_void_p, c.c_void_p]),
            ("eglBindAPI", c.c_uint, [c.c_uint]),
            (
                "eglChooseConfig",
                c.c_uint,
                [c.c_void_p, c.c_void_p, c.c_void_p, c.c_int, c.c_void_p],
            ),
            (
                "eglCreatePbufferSurface",
                c.c_void_p,
                [c.c_void_p, c.c_void_p, c.c_void_p],
            ),
            (
                "eglCreateContext",
                c.c_void_p,
                [c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p],
            ),
            (
                "eglMakeCurrent",
                c.c_uint,
                [c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p],
            ),
            ("eglDestroyContext", c.c_uint, [c.c_void_p, c.c_void_p]),
            ("eglDestroySurface", c.c_uint, [c.c_void_p, c.c_void_p]),
            ("eglTerminate", c.c_uint, [c.c_void_p]),
            ("eglGetError", c.c_int, []),
            ("eglQueryString", c.c_char_p, [c.c_void_p, c.c_int]),
            ("eglGetProcAddress", c.c_void_p, [c.c_char_p]),
        ):
            function = getattr(egl, name, None)
            if function is not None:
                function.restype = restype
                function.argtypes = argtypes

        return egl

    def _open_display(self):
        native = self._connect_to_display()

        if native is None:
            return self._no_display()

        display = self._egl.eglGetDisplay(native)
        if not display:
            raise GLContextError(f"eglGetDisplay failed: {self._error()}")

        return display

    def _connect_to_display(self):
        if self._platform not in _NATIVE_DISPLAYS:
            return None

        library, opener, closer, self._native_param = _NATIVE_DISPLAYS[self._platform]

        try:
            native = ctypes.CDLL(library)
        except OSError as e:
            raise GLContextError(f"{library} not found: {e}") from e

        open_display = getattr(native, opener)
        open_display.restype = ctypes.c_void_p
        open_display.argtypes = [ctypes.c_char_p]

        self._native_close = getattr(native, closer)
        self._native_close.argtypes = [ctypes.c_void_p]

        self._native_display = open_display(None)
        if not self._native_display:
            raise GLContextError(f"Could not reach the {self._platform} display")

        return self._native_display

    def _no_display(self):
        # Qt's offscreen platform, with no display to speak of
        if hasattr(self._egl, "eglGetPlatformDisplay"):
            display = self._egl.eglGetPlatformDisplay(
                self._PLATFORM_SURFACELESS, None, None
            )
            if display:
                return display

        display = self._egl.eglGetDisplay(None)
        if not display:
            raise GLContextError(f"No EGL display: {self._error()}")

        return display

    def _make_current(self):
        # Mesa on Wayland has no pbuffer configs at all, and with this needs
        # none. Rendering only ever goes to our own framebuffers.
        extensions = self._egl.eglQueryString(self._display, self._EXTENSIONS) or b""
        is_surfaceless = b"EGL_KHR_surfaceless_context" in extensions

        config = self._choose_config(0 if is_surfaceless else self._PBUFFER_BIT)

        if not is_surfaceless:
            surface_attrs = (ctypes.c_int * 5)(
                self._WIDTH, 1, self._HEIGHT, 1, self._NONE
            )
            self._surface = self._egl.eglCreatePbufferSurface(
                self._display, config, surface_attrs
            )
            if not self._surface:
                raise GLContextError(f"eglCreatePbufferSurface failed: {self._error()}")

        self._context = self._egl.eglCreateContext(self._display, config, None, None)
        if not self._context:
            raise GLContextError(f"eglCreateContext failed: {self._error()}")

        if not self._egl.eglMakeCurrent(
            self._display, self._surface, self._surface, self._context
        ):
            raise GLContextError(f"eglMakeCurrent failed: {self._error()}")

    def _choose_config(self, surface_type: int):
        attrs = (ctypes.c_int * 11)(
            self._SURFACE_TYPE,
            surface_type,
            self._RENDERABLE_TYPE,
            self._OPENGL_BIT,
            self._RED_SIZE,
            8,
            self._GREEN_SIZE,
            8,
            self._BLUE_SIZE,
            8,
            self._NONE,
        )
        config = ctypes.c_void_p()
        count = ctypes.c_int()

        is_chosen = self._egl.eglChooseConfig(
            self._display, attrs, ctypes.byref(config), 1, ctypes.byref(count)
        )
        if not is_chosen or count.value < 1:
            raise GLContextError(f"No suitable EGL config: {self._error()}")

        return config

    def _error(self) -> str:
        return hex(self._egl.eglGetError())

    def get_proc_address(self, name: bytes) -> int:
        address = self._egl.eglGetProcAddress(name)
        if address:
            return address

        # EGL before 1.5 needn't give the core functions
        if self._libgl is None:
            try:
                self._libgl = ctypes.CDLL("libGL.so.1")
            except OSError:
                return 0

        function = getattr(self._libgl, name.decode(), None)
        return ctypes.cast(function, ctypes.c_void_p).value if function else 0

    def native_params(self) -> dict:
        if self._native_display:
            return {self._native_param: self._native_display}
        return {}

    def close(self) -> None:
        if self._display:
            self._egl.eglMakeCurrent(self._display, None, None, None)
            if self._context:
                self._egl.eglDestroyContext(self._display, self._context)
            if self._surface:
                self._egl.eglDestroySurface(self._display, self._surface)
            self._egl.eglTerminate(self._display)

        if self._native_display:
            self._native_close(self._native_display)

        self._display = self._context = self._surface = None
        self._native_display = None


class WGLContext:
    """Windows: a context on a window nobody sees.

    A message-only one: a hidden top-level window gets broadcasts like
    WM_SETTINGCHANGE, and with no message loop on this thread to answer, every
    sender would wait on it. Desktop OpenGL by design: ANGLE only gets as far
    as d3d11va-copy, where this gets NVDEC.
    """

    _CLASS_NAME = "GridPlayerMpvGL"
    _HWND_MESSAGE = -3

    def __init__(self):
        from ctypes import wintypes

        self._wintypes = wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._opengl32 = ctypes.WinDLL("opengl32", use_last_error=True)
        self._declare()

        self._hwnd = None
        self._hdc = None
        self._context = None

        self._make_window()

        self._hdc = self._user32.GetDC(self._hwnd)
        if not self._hdc:
            raise GLContextError(f"GetDC failed: {ctypes.get_last_error()}")

        self._set_pixel_format()

        self._context = self._opengl32.wglCreateContext(self._hdc)
        if not self._context:
            raise GLContextError(f"wglCreateContext failed: {ctypes.get_last_error()}")

        if not self._opengl32.wglMakeCurrent(self._hdc, self._context):
            raise GLContextError(f"wglMakeCurrent failed: {ctypes.get_last_error()}")

    def _declare(self):
        w = self._wintypes
        c = ctypes

        self._user32.CreateWindowExW.restype = w.HWND
        self._user32.CreateWindowExW.argtypes = [
            w.DWORD,
            w.LPCWSTR,
            w.LPCWSTR,
            w.DWORD,
            c.c_int,
            c.c_int,
            c.c_int,
            c.c_int,
            w.HWND,
            w.HMENU,
            w.HINSTANCE,
            w.LPVOID,
        ]
        self._user32.GetDC.restype = w.HDC
        self._user32.GetDC.argtypes = [w.HWND]
        self._user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
        self._user32.DestroyWindow.argtypes = [w.HWND]
        self._user32.UnregisterClassW.argtypes = [w.LPCWSTR, w.HINSTANCE]
        self._kernel32.GetModuleHandleW.restype = w.HMODULE
        self._kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self._kernel32.GetProcAddress.restype = c.c_void_p
        self._kernel32.GetProcAddress.argtypes = [w.HMODULE, c.c_char_p]
        self._gdi32.ChoosePixelFormat.argtypes = [w.HDC, c.c_void_p]
        self._gdi32.SetPixelFormat.argtypes = [w.HDC, c.c_int, c.c_void_p]
        self._opengl32.wglCreateContext.restype = w.HANDLE
        self._opengl32.wglCreateContext.argtypes = [w.HDC]
        self._opengl32.wglMakeCurrent.argtypes = [w.HDC, w.HANDLE]
        self._opengl32.wglDeleteContext.argtypes = [w.HANDLE]
        self._opengl32.wglGetProcAddress.restype = c.c_void_p
        self._opengl32.wglGetProcAddress.argtypes = [c.c_char_p]

    def _make_window(self):
        from gridplayer.utils.win32_tray_api import WNDCLASSW, WNDPROC

        w = self._wintypes

        CS_OWNDC = 0x0020

        self._instance = self._kernel32.GetModuleHandleW(None)

        window_class = WNDCLASSW()
        window_class.style = CS_OWNDC
        window_class.lpfnWndProc = ctypes.cast(self._user32.DefWindowProcW, WNDPROC)
        window_class.hInstance = self._instance
        window_class.lpszClassName = self._CLASS_NAME

        # a second renderer in the same run finds it registered already
        self._user32.RegisterClassW(ctypes.byref(window_class))

        self._hwnd = self._user32.CreateWindowExW(
            0,
            self._CLASS_NAME,
            "",
            0,
            0,
            0,
            1,
            1,
            w.HWND(self._HWND_MESSAGE),
            None,
            self._instance,
            None,
        )
        if not self._hwnd:
            raise GLContextError(f"CreateWindowExW failed: {ctypes.get_last_error()}")

    def _set_pixel_format(self):
        w = self._wintypes

        class PIXELFORMATDESCRIPTOR(ctypes.Structure):
            _fields_ = [
                ("nSize", w.WORD),
                ("nVersion", w.WORD),
                ("dwFlags", w.DWORD),
                ("iPixelType", ctypes.c_ubyte),
                ("cColorBits", ctypes.c_ubyte),
                ("cRedBits", ctypes.c_ubyte),
                ("cRedShift", ctypes.c_ubyte),
                ("cGreenBits", ctypes.c_ubyte),
                ("cGreenShift", ctypes.c_ubyte),
                ("cBlueBits", ctypes.c_ubyte),
                ("cBlueShift", ctypes.c_ubyte),
                ("cAlphaBits", ctypes.c_ubyte),
                ("cAlphaShift", ctypes.c_ubyte),
                ("cAccumBits", ctypes.c_ubyte),
                ("cAccumRedBits", ctypes.c_ubyte),
                ("cAccumGreenBits", ctypes.c_ubyte),
                ("cAccumBlueBits", ctypes.c_ubyte),
                ("cAccumAlphaBits", ctypes.c_ubyte),
                ("cDepthBits", ctypes.c_ubyte),
                ("cStencilBits", ctypes.c_ubyte),
                ("cAuxBuffers", ctypes.c_ubyte),
                ("iLayerType", ctypes.c_ubyte),
                ("bReserved", ctypes.c_ubyte),
                ("dwLayerMask", w.DWORD),
                ("dwVisibleMask", w.DWORD),
                ("dwDamageMask", w.DWORD),
            ]

        PFD_DRAW_TO_WINDOW = 0x00000004
        PFD_SUPPORT_OPENGL = 0x00000020
        PFD_TYPE_RGBA = 0

        descriptor = PIXELFORMATDESCRIPTOR()
        descriptor.nSize = ctypes.sizeof(PIXELFORMATDESCRIPTOR)
        descriptor.nVersion = 1
        descriptor.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL
        descriptor.iPixelType = PFD_TYPE_RGBA
        descriptor.cColorBits = 32

        pixel_format = self._gdi32.ChoosePixelFormat(
            self._hdc, ctypes.byref(descriptor)
        )
        if not pixel_format:
            raise GLContextError(f"ChoosePixelFormat failed: {ctypes.get_last_error()}")

        if not self._gdi32.SetPixelFormat(
            self._hdc, pixel_format, ctypes.byref(descriptor)
        ):
            raise GLContextError(f"SetPixelFormat failed: {ctypes.get_last_error()}")

    def get_proc_address(self, name: bytes) -> int:
        address = self._opengl32.wglGetProcAddress(name)

        # 0 and these small values are how WGL says it hasn't got it, and it
        # hasn't got anything from OpenGL 1.1: those are opengl32's own
        if address in (None, 1, 2, 3, ctypes.c_size_t(-1).value):
            address = self._kernel32.GetProcAddress(self._opengl32._handle, name)

        return address or 0

    def native_params(self) -> dict:
        return {}

    def close(self) -> None:
        if self._context:
            self._opengl32.wglMakeCurrent(None, None)
            self._opengl32.wglDeleteContext(self._context)
        if self._hdc:
            self._user32.ReleaseDC(self._hwnd, self._hdc)
        if self._hwnd:
            self._user32.DestroyWindow(self._hwnd)
            self._user32.UnregisterClassW(self._CLASS_NAME, self._instance)

        self._context = self._hdc = self._hwnd = None


class QtGLContext:
    """macOS: Qt's, which needs no trick there and hasn't been run yet."""

    def __init__(self, surface):
        from PyQt5.QtGui import QOpenGLContext

        self._surface = surface
        self._context = QOpenGLContext()
        self._context.setFormat(surface.format())

        if not self._context.create():
            raise GLContextError("Could not create a GL context")

        if not self._context.makeCurrent(surface):
            raise GLContextError("Could not make the GL context current")

    def get_proc_address(self, name: bytes) -> int:
        from PyQt5.QtCore import QByteArray

        # sip gives None for a function the driver doesn't have
        address = self._context.getProcAddress(QByteArray(name))
        return int(address) if address else 0

    def native_params(self) -> dict:
        return {}

    def close(self) -> None:
        self._context.doneCurrent()


def create_gl_context(qt_platform: str, qt_surface=None):
    """A context current on this thread.

    `qt_surface` is a QOffscreenSurface made on the GUI thread, as Qt wants
    it, for macOS, where Qt's context is used.
    """

    if env.IS_LINUX:
        return EGLContext(qt_platform)

    if env.IS_WINDOWS:
        return WGLContext()

    return QtGLContext(qt_surface)
