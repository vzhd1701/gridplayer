import ctypes
import logging
import os
import platform
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from gridplayer.params import env


@contextmanager
def importing_embed_vlc():
    if "vlc" in sys.modules:
        yield
        return

    if env.IS_PYINSTALLER and env.IS_MACOS:
        lib_path = os.environ.get("PYTHON_VLC_LIB_PATH")

        if not lib_path:
            raise RuntimeError("PYTHON_VLC_LIB_PATH not set")

        vlc_core = str(Path(lib_path).parent / "libvlccore.dylib")
        ctypes.CDLL(vlc_core)

    yield

    _fix_plugins_path()


def _fix_plugins_path():
    vlc_module = sys.modules["vlc"]

    if vlc_module.plugin_path is not None:
        if Path(vlc_module.plugin_path).name == "plugins":
            return

    vlc_lib_root = _get_libvlc_root_path()
    if vlc_lib_root is None:
        logging.getLogger(__name__).warning(
            "VLC lib root not found, won't be using plugin cache"
        )
        return

    plugin_path_map = {
        "Darwin": str(vlc_lib_root.parent / "plugins"),
        "Windows": str(vlc_lib_root / "plugins"),
        "Linux": str(vlc_lib_root / "vlc" / "plugins"),
    }

    try:
        vlc_module.plugin_path = plugin_path_map[platform.system()]
    except KeyError:
        raise RuntimeError("Unsupported platform")


def _get_libvlc_root_path() -> Optional[Path]:
    vlc_module = sys.modules["vlc"]

    vlc_lib_root = Path(vlc_module.dll._name)  # noqa: WPS437

    if vlc_lib_root.is_absolute():
        return vlc_lib_root.parent

    # this usually happens on linux only
    if not env.IS_LINUX:
        return None

    return _get_libvlc_root_path_linux()


def _get_libvlc_root_path_linux() -> Optional[Path]:
    # https://github.com/videolan/vlc/blob/3.0.16/src/linux/dirs.c#L33

    with open("/proc/self/maps") as f:
        maps = {line.split(" ")[-1] for line in f.readlines()}

    maps_seek = (m for m in maps if "/libvlc.so" in m)

    libvlc_path = next(maps_seek, None)

    if libvlc_path:
        return Path(libvlc_path).parent

    return None
