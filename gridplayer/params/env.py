import os
import platform
import sys
from pathlib import Path

# not platform.system(): on Windows it asks WMI, which holds up every
# startup by a few dozen milliseconds to say what sys.platform already does
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

# The macOS package's libmpv is made for 12 and up, and won't load before
IS_MACOS_BEFORE_12 = (
    IS_MACOS and int((platform.mac_ver()[0] or "12").split(".")[0]) < 12
)


def _is_kde() -> bool:
    if not IS_LINUX:
        return False

    blob = ":".join(
        (
            os.environ.get("XDG_CURRENT_DESKTOP", ""),
            os.environ.get("DESKTOP_SESSION", ""),
            os.environ.get("XDG_SESSION_DESKTOP", ""),
        )
    ).lower()
    return "kde" in blob or "plasma" in blob


def has_x_server() -> bool:
    """Linux: an X server to run on, Xwayland on a Wayland desktop."""

    return bool(os.environ.get("DISPLAY"))


def has_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


IS_PYINSTALLER = getattr(sys, "frozen", False)
IS_SNAP = IS_LINUX and "SNAP" in os.environ
# APPDIR, not APPIMAGE: the AppRun sets it to an AppImage unpacked and run as
# it is too, where there is no AppImage file
IS_APPIMAGE = IS_LINUX and "APPDIR" in os.environ
IS_FLATPAK = IS_LINUX and "FLATPAK_ID" in os.environ
IS_KDE = _is_kde()

# Qt set up for MPV's frames drawn by GL, as the app started: see
# init_app_env
MPV_GL_OUTPUT = False

# The Qt platform plugin to run on, None to leave it to Qt. Given by
# --platform, or else picked by init_app_env from the settings, on Linux
QT_PLATFORM = None
# picked from the settings, not given: changing them can call for another
IS_QT_PLATFORM_PICKED = False

PYINSTALLER_LIB_ROOT = Path(sys._MEIPASS) if IS_PYINSTALLER else Path.cwd()


def _resolve_resources_dir() -> Path:
    # When frozen, resources are collected as data files under sys._MEIPASS;
    # importlib.resources is unreliable there because the package lives in the
    # PYZ archive.
    if IS_PYINSTALLER:
        return PYINSTALLER_LIB_ROOT / "gridplayer" / "resources"

    import importlib.resources

    return Path(str(importlib.resources.files("gridplayer") / "resources"))


RESOURCES_DIR = _resolve_resources_dir()


VLC_VERSION = None
VLC_PYTHON_VERSION = None
MPV_VERSION = None
MPV_PYTHON_VERSION = None

if IS_FLATPAK:
    FLATPAK_RUNTIME_DIR = (
        Path(os.environ["XDG_RUNTIME_DIR"])
        / "app"
        / os.environ["FLATPAK_ID"]
        / "gridplayer"
    )
    FLATPAK_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
else:
    FLATPAK_RUNTIME_DIR = None
