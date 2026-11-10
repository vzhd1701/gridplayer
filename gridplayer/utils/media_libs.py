"""Which video libraries this system has, and loading the one in use.

Looking takes a millisecond or so and loads nothing, so asking is cheap. Loading
is what costs, up to 80 ms for libmpv on Linux, and only the library of the driver
in use is ever loaded. Whether one really works is only known by loading it, so
what that finds is kept here too.

Each library is looked for once a run: installing one takes a restart to notice.
"""

import ctypes.util
import logging
import os
import shutil
import sys
import sysconfig
from enum import Enum, auto
from functools import cache
from pathlib import Path

from gridplayer.params import env
from gridplayer.params.static import VideoDriver
from gridplayer.utils.libvlc import get_embed_vlc_paths, get_embed_vlc_root, init_vlc
from gridplayer.utils.qt import translate

_log = logging.getLogger(__name__)

LIBVLC_WINDOWS = "libvlc.dll"
LIBVLC_MACOS_APP = Path("/Applications/VLC.app/Contents/MacOS/lib/libvlc.dylib")
LIBVLC_LINUX = "libvlc.so.5"

# python-mpv's own names, those of the versions with the API we use
LIBMPV_WINDOWS = ("libmpv-2.dll", "mpv-2.dll")
LIBMPV_MACOS = ("libmpv.2.dylib", "libmpv.dylib")
LIBMPV_LINUX = "libmpv.so.2"

LIBMPV_MACOS_DIRS = ("/opt/homebrew/lib", "/usr/local/lib", "/opt/local/lib")


class MediaLib(Enum):
    VLC = auto()
    MPV = auto()


class LibProblem(Enum):
    MISSING = auto()
    WONT_LOAD = auto()
    TOO_OLD = auto()


VLC_DRIVERS = (
    VideoDriver.VLC_SW,
    VideoDriver.VLC_SW_SP,
    VideoDriver.VLC_HW,
    VideoDriver.VLC_HW_SP,
)
MPV_DRIVERS = (VideoDriver.MPV_HW, VideoDriver.MPV_SW)
# drawing into a native window of VLC's, over which the app's overlay floats
VLC_HW_DRIVERS = (VideoDriver.VLC_HW, VideoDriver.VLC_HW_SP)

# what came of loading each one tried: None if it loaded, or why it didn't
_load_results: dict[MediaLib, LibProblem | None] = {}


def lib_of_driver(driver: VideoDriver) -> MediaLib | None:
    if driver in VLC_DRIVERS:
        return MediaLib.VLC

    if driver in MPV_DRIVERS:
        return MediaLib.MPV

    return None


def lib_problem(lib: MediaLib) -> LibProblem | None:
    """Why a library can't be used, None if as far as is known it can."""

    if lib in _load_results:
        return _load_results[lib]

    return None if _find(lib) else LibProblem.MISSING


def lib_problem_text(lib: MediaLib) -> str | None:
    """Why a library can't be used, in words, None if it can."""

    problem = lib_problem(lib)

    if problem is None:
        return None

    return {
        (MediaLib.VLC, LibProblem.MISSING): translate(
            "SettingsDialog", "VLC not found"
        ),
        (MediaLib.VLC, LibProblem.WONT_LOAD): translate(
            "SettingsDialog", "VLC won't load"
        ),
        (MediaLib.MPV, LibProblem.MISSING): translate(
            "SettingsDialog", "libmpv not found"
        ),
        (MediaLib.MPV, LibProblem.WONT_LOAD): translate(
            "SettingsDialog", "libmpv won't load"
        ),
        (MediaLib.MPV, LibProblem.TOO_OLD): translate(
            "SettingsDialog", "libmpv is too old"
        ),
    }[(lib, problem)]


def load_lib(lib: MediaLib | None) -> bool:
    """Load a library if it hasn't been, False if it can't be used.

    None is for the driver that needs no library.
    """

    if lib is None:
        return True

    if lib not in _load_results:
        _load_results[lib] = _load_vlc() if lib == MediaLib.VLC else _load_mpv()

    return _load_results[lib] is None


def forget_libs() -> None:
    """Look again the next time, for tests: a library stays loaded regardless."""

    _load_results.clear()
    find_libvlc.cache_clear()
    find_libmpv.cache_clear()


def _find(lib: MediaLib) -> str | None:
    return find_libvlc() if lib == MediaLib.VLC else find_libmpv()


def _load_vlc() -> LibProblem | None:
    try:
        env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    except FileNotFoundError:
        # the reason is in the log, written by init_vlc
        return LibProblem.WONT_LOAD if find_libvlc() else LibProblem.MISSING

    return None


def _load_mpv() -> LibProblem | None:
    # here, as this is what libmpv.py asks where the library is
    from gridplayer.mpv_player.libmpv import LibmpvTooOldError, load_mpv

    try:
        load_mpv()
    except LibmpvTooOldError:
        _log.exception("libmpv is too old")
        return LibProblem.TOO_OLD
    except OSError:
        _log.exception("Failed to load libmpv")
        return LibProblem.WONT_LOAD if find_libmpv() else LibProblem.MISSING

    return None


# -- libVLC. What python-vlc looks through as it is imported, only that it loads
# what it finds there, and it is vendored: so the same search again.


@cache
def find_libvlc() -> str | None:
    """Where libVLC is, loading nothing. None if it isn't anywhere."""

    _, embedded = get_embed_vlc_paths()

    if embedded is not None and embedded.is_file():
        return str(embedded)

    path = os.environ.get("PYTHON_VLC_LIB_PATH")

    if path:
        return path if Path(path).is_file() else None

    if env.IS_WINDOWS:
        return _find_libvlc_windows()

    if env.IS_MACOS:
        if LIBVLC_MACOS_APP.is_file():
            return str(LIBVLC_MACOS_APP)
        return ctypes.util.find_library("vlc")

    return _find_linux(LIBVLC_LINUX, "vlc")


def _find_libvlc_windows() -> str | None:
    found = ctypes.util.find_library(LIBVLC_WINDOWS)

    if found:
        return found

    places = [_vlc_registry_dir()]

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        places += [
            Path(program_files) / "VideoLAN" / "VLC",
            Path(program_files) / "VLC",
        ]

    places.append(Path.cwd())

    return _first_file((place for place in places if place), (LIBVLC_WINDOWS,))


def _vlc_registry_dir() -> Path | None:
    import winreg

    def install_dir(root) -> Path | None:
        try:
            with winreg.OpenKey(root, "Software\\VideoLAN\\VLC") as key:
                return Path(winreg.QueryValueEx(key, "InstallDir")[0])
        except OSError:
            return None

    return install_dir(winreg.HKEY_LOCAL_MACHINE) or install_dir(
        winreg.HKEY_CURRENT_USER
    )


# -- libmpv


@cache
def find_libmpv() -> str | None:
    """Where libmpv is, loading nothing. None if it isn't anywhere."""

    path = os.environ.get("GP_LIBMPV_PATH")

    if path:
        return path if Path(path).is_file() else None

    if env.IS_WINDOWS:
        return _find_libmpv_windows()

    if env.IS_MACOS:
        return _find_libmpv_macos()

    bundled = _first_file(_libmpv_bundled_dirs(), (LIBMPV_LINUX,))

    return bundled or _find_linux(LIBMPV_LINUX, "mpv")


def _libmpv_bundled_dirs() -> list[Path]:
    if env.IS_PYINSTALLER:
        return [Path(sys.executable).parent / "libmpv"]

    # in the packages, whatever goes with VLC goes in the same place
    root = get_embed_vlc_root()

    return [root] if root else []


def _find_libmpv_windows() -> str | None:
    bundled = _first_file(_libmpv_bundled_dirs(), LIBMPV_WINDOWS)

    if bundled:
        return bundled

    for name in LIBMPV_WINDOWS:
        found = ctypes.util.find_library(name)
        if found:
            return found

    return _first_file(_libmpv_windows_dirs(), LIBMPV_WINDOWS)


def _libmpv_windows_dirs() -> list[Path]:
    dirs = [Path(sys.executable).parent]

    mpv_exe = shutil.which("mpv")
    if mpv_exe:
        dirs.append(Path(mpv_exe).parent)

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        dirs.append(Path(program_files) / "mpv")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        dirs.append(Path(local_app_data) / "Programs" / "mpv")

    scoop = os.environ.get("SCOOP")
    scoop_root = Path(scoop) if scoop else Path.home() / "scoop"
    dirs.append(scoop_root / "apps" / "mpv" / "current")

    return dirs


def _find_libmpv_macos() -> str | None:
    places = [*_libmpv_bundled_dirs(), *map(Path, LIBMPV_MACOS_DIRS)]

    return _first_file(places, LIBMPV_MACOS) or ctypes.util.find_library("mpv")


# -- both


def _find_linux(file_name: str, short_name: str) -> str | None:
    # The folders first: if it isn't in the linker's list, find_library goes on to
    # run gcc and ld, 8 to 45 ms, and that is the answer most people here will get
    found = _first_file(_linux_lib_dirs(), (file_name,))

    return found or ctypes.util.find_library(short_name)


def _linux_lib_dirs() -> list[Path]:
    from_env = os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)
    multiarch = sysconfig.get_config_var("MULTIARCH")

    dirs = [
        *from_env,
        f"/usr/lib/{multiarch}" if multiarch else "",
        "/usr/lib64",
        "/usr/lib",
        "/usr/local/lib",
    ]

    return [Path(d) for d in dirs if d]


def _first_file(places, names) -> str | None:
    for place in places:
        for name in names:
            path = place / name
            if path.is_file():
                return str(path)

    return None
