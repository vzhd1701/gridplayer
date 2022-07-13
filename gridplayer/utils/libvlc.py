import logging
import os
import sys
from importlib.metadata import version as lib_version
from pathlib import Path
from typing import Optional, Tuple, Union

from gridplayer.params import env
from gridplayer.utils.libvlc_fixer import importing_embed_vlc


def init_vlc():
    log = logging.getLogger(__name__)

    vlc_plugins_path, vlc_lib_path = _get_embed_vlc_paths()

    if vlc_plugins_path and vlc_lib_path:
        log.debug("Setting paths for embedded VLC")

        log.debug(f"PYTHON_VLC_MODULE_PATH: {vlc_plugins_path}")
        log.debug(f"PYTHON_VLC_LIB_PATH: {vlc_lib_path}")

        if not vlc_lib_path.is_file() or not vlc_plugins_path.is_dir():
            log.info("Embedded vlc lib not found, will try to find system VLC...")
        else:
            os.environ["PYTHON_VLC_MODULE_PATH"] = str(vlc_plugins_path)
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
    vlc_root = _get_embed_vlc_root()

    if vlc_root is None:
        return None, None

    if env.IS_WINDOWS:
        vlc_plugins_path = vlc_root / "plugins"
        vlc_lib_path = vlc_root / "libvlc.dll"

    elif env.IS_MACOS:
        vlc_plugins_path = vlc_root / "plugins"
        vlc_lib_path = vlc_root / "lib" / "libvlc.dylib"

    elif env.IS_LINUX:
        vlc_plugins_path = vlc_root / "vlc" / "plugins"
        vlc_lib_path = vlc_root / "libvlc.so.5"

    else:
        return None, None

    return vlc_plugins_path, vlc_lib_path


def _get_embed_vlc_root() -> Optional[Path]:
    if env.IS_PYINSTALLER:
        return Path(sys.executable).parent / "libVLC"

    if env.IS_SNAP:
        return Path(os.environ["SNAP"]) / "usr" / "lib" / "x86_64-linux-gnu"

    if env.IS_APPIMAGE:
        return Path(os.environ["APPDIR"]) / "usr" / "lib"

    if env.IS_FLATPAK:
        return Path("/app") / "lib"

    return None


def _get_vlc_version():
    try:
        with importing_embed_vlc():
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
