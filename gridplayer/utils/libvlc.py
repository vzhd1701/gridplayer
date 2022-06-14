import ctypes
import logging
import os
import platform
import sys
from importlib.metadata import version as lib_version
from pathlib import Path
from typing import Tuple, Union

from gridplayer.params import env


def pre_import_embed_vlc():
    if "vlc" in sys.modules:
        return

    if env.IS_PYINSTALLER and platform.system() == "Darwin":
        lib_path = os.environ.get("PYTHON_VLC_LIB_PATH")

        if not lib_path:
            raise RuntimeError("PYTHON_VLC_LIB_PATH not set")

        # test this on MacOS
        # vlc_core = Path(lib_path).parent / "libvlccore.9.dylib"
        vlc_core = Path(lib_path).parent / "libvlccore.dylib"
        ctypes.CDLL(str(vlc_core))


def init_vlc():
    log = logging.getLogger(__name__)

    vlc_path, vlc_lib_path = _get_embed_vlc_paths()

    if vlc_path and vlc_lib_path:
        log.debug("Setting paths for embedded VLC")

        log.debug(f"PYTHON_VLC_MODULE_PATH: {vlc_path}")
        log.debug(f"PYTHON_VLC_LIB_PATH: {vlc_lib_path}")

        if not vlc_lib_path.is_file() or not vlc_path.is_dir():
            log.info("Embedded vlc lib not found, will try to find system VLC...")
        else:
            os.environ["PYTHON_VLC_MODULE_PATH"] = str(vlc_path)
            os.environ["PYTHON_VLC_LIB_PATH"] = str(vlc_lib_path)
    else:
        log.info("No embedded vlc path, will try to find system VLC...")

    vlc_python_version = lib_version("python-vlc")
    vlc_version = _get_vlc_version()

    log.debug(f"python-vlc {vlc_python_version}")
    log.debug(f"VLC {vlc_version}")

    if vlc_version is None:
        raise FileNotFoundError

    return vlc_version, vlc_python_version


def _get_embed_vlc_paths() -> Union[Tuple[Path, Path], Tuple[None, None]]:
    if env.IS_PYINSTALLER and platform.system() == "Windows":
        vlc_path = Path(sys.executable).parent / "libVLC"
        vlc_lib_path = vlc_path / "libvlc.dll"

    elif env.IS_PYINSTALLER and platform.system() == "Darwin":
        root_path = Path(sys.executable).parent / "libVLC"

        vlc_path = root_path / "plugins"
        # vlc_lib_path = root_path / "lib" / "libvlc.5.dylib"
        vlc_lib_path = root_path / "lib" / "libvlc.dylib"

    elif env.IS_SNAP:
        root_path = Path(os.environ["SNAP"]) / "usr" / "lib" / "x86_64-linux-gnu"

        vlc_path = root_path / "vlc"
        vlc_lib_path = root_path / "libvlc.so.5"

    elif env.IS_APPIMAGE:
        root_path = Path(os.environ["APPDIR"]) / "usr" / "lib" / "x86_64-linux-gnu"

        vlc_path = root_path / "vlc"
        vlc_lib_path = root_path / "libvlc.so.5"

    elif env.IS_FLATPAK:
        root_path = Path("/app") / "lib"

        vlc_path = root_path / "vlc"
        vlc_lib_path = root_path / "libvlc.so.5"

    else:
        vlc_path = None
        vlc_lib_path = None

    return vlc_path, vlc_lib_path


def _get_vlc_version():
    pre_import_embed_vlc()

    try:
        import vlc  # noqa: WPS433
    except (OSError, NotImplementedError):
        return None

    logging.getLogger(__name__).debug("VLC initialized paths")
    logging.getLogger(__name__).debug(f"VLC plugin_path: {vlc.plugin_path}")
    logging.getLogger(__name__).debug(f"VLC dll: {vlc.dll}")

    try:
        vlc_version = vlc.libvlc_get_version()
    except NameError:
        return None

    return vlc_version.decode().split(" ")[0]
