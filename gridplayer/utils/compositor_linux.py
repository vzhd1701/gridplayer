import ctypes
import ctypes.util
import logging

from gridplayer.params import env
from gridplayer.settings import Settings

_X11_SONAMES = ("libX11.so.6", "libX11.so")

_cached: bool | None = None


def reset_compositor_cache() -> None:
    global _cached
    _cached = None


def is_compositor_running() -> bool:
    global _cached

    if _cached is None:
        _cached = _detect_compositor()

    return _cached


def should_make_overlay_opaque() -> bool:
    return Settings().get("internal/opaque_hw_overlay") or not is_compositor_running()


def _detect_compositor() -> bool:
    if not env.IS_LINUX:
        return True

    try:
        if _qt_platform_name() == "wayland":
            return True
    except Exception:
        logging.getLogger(__name__).debug(
            "Could not read Qt platform name", exc_info=True
        )

    return _x11_compositing_manager_running()


def _qt_platform_name() -> str:
    from PyQt5.QtGui import QGuiApplication

    return QGuiApplication.platformName()


def _x11_compositing_manager_running() -> bool:
    try:
        return _query_net_wm_cm()
    except Exception:
        logging.getLogger(__name__).debug("Compositor detection failed", exc_info=True)
        return True


def _cdll_or_none(name: str):
    try:
        return ctypes.CDLL(name)
    except OSError:
        return None


def _load_libx11():
    name = ctypes.util.find_library("X11")
    if name:
        lib = _cdll_or_none(name)
        if lib is not None:
            return lib
        logging.getLogger(__name__).debug("Could not load libX11 from %s", name)

    for candidate in _X11_SONAMES:
        lib = _cdll_or_none(candidate)
        if lib is not None:
            return lib

    logging.getLogger(__name__).debug("libX11 not found")
    return None


def _query_net_wm_cm() -> bool:
    x11 = _load_libx11()
    if x11 is None:
        return True

    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    x11.XDefaultScreen.restype = ctypes.c_int
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XGetSelectionOwner.restype = ctypes.c_ulong
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int

    dpy = x11.XOpenDisplay(None)
    if not dpy:
        logging.getLogger(__name__).debug("XOpenDisplay failed")
        return True

    try:
        screen = x11.XDefaultScreen(dpy)
        atom = x11.XInternAtom(dpy, f"_NET_WM_CM_S{screen}".encode(), 0)
        owner = x11.XGetSelectionOwner(dpy, atom)
        running = owner != 0
        logging.getLogger(__name__).debug(
            "X11 compositing manager (_NET_WM_CM_S%s) running: %s", screen, running
        )
        return running
    finally:
        x11.XCloseDisplay(dpy)
