import logging
import os
import sys
from pathlib import Path

from gridplayer.params import env
from gridplayer.utils.libvlc_fixer import importing_embed_vlc


def init_vlc():
    log = logging.getLogger(__name__)

    vlc_plugins_path, vlc_lib_path = _get_embed_vlc_paths()

    if _is_usable_vlc(vlc_plugins_path, vlc_lib_path):
        log.debug("Setting paths for embedded VLC")

        log.debug(f"PYTHON_VLC_MODULE_PATH: {vlc_plugins_path}")
        log.debug(f"PYTHON_VLC_LIB_PATH: {vlc_lib_path}")

        os.environ["PYTHON_VLC_MODULE_PATH"] = str(vlc_plugins_path)
        os.environ["PYTHON_VLC_LIB_PATH"] = str(vlc_lib_path)
    else:
        log.info("Embedded vlc lib not found, will try to find system VLC...")
        _set_system_vlc_paths(log)

    vlc_version, vlc_python_version = _get_vlc_version()

    log.debug(f"python-vlc {vlc_python_version}")
    log.debug(f"VLC {vlc_version}")

    if vlc_version is None:
        raise FileNotFoundError

    return vlc_version, vlc_python_version


def _is_usable_vlc(plugins_path: Path | None, lib_path: Path | None) -> bool:
    if plugins_path is None or lib_path is None:
        return False

    return lib_path.is_file() and plugins_path.is_dir()


def _set_system_vlc_paths(log) -> None:
    """Point python-vlc at a system VLC install.

    PyInstaller builds are expected to carry their own libVLC, but the macOS
    bundle ships an empty libVLC directory. Without PYTHON_VLC_LIB_PATH set,
    importing_embed_vlc() raises RuntimeError and the app dies on startup.
    Falling back to a system install keeps it usable.
    """
    if os.environ.get("PYTHON_VLC_LIB_PATH"):
        log.debug("PYTHON_VLC_LIB_PATH already set, leaving it alone")
        return

    plugins_path, lib_path = _get_system_vlc_paths()

    if not _is_usable_vlc(plugins_path, lib_path):
        log.info("No system VLC found")
        return

    log.info(f"Using system VLC: {lib_path}")

    os.environ["PYTHON_VLC_MODULE_PATH"] = str(plugins_path)
    os.environ["PYTHON_VLC_LIB_PATH"] = str(lib_path)


def _get_system_vlc_paths() -> tuple[Path, Path] | tuple[None, None]:
    for vlc_root in _get_system_vlc_roots():
        plugins_path, lib_path = _vlc_paths_for_root(vlc_root)

        if _is_usable_vlc(plugins_path, lib_path):
            return plugins_path, lib_path

    return None, None


def _get_system_vlc_roots() -> list[Path]:
    if env.IS_MACOS:
        return [
            Path("/Applications/VLC.app/Contents/MacOS"),
            Path.home() / "Applications" / "VLC.app" / "Contents" / "MacOS",
        ]

    return []


def _vlc_paths_for_root(vlc_root: Path) -> tuple[Path, Path] | tuple[None, None]:
    if env.IS_WINDOWS:
        return vlc_root / "plugins", vlc_root / "libvlc.dll"

    if env.IS_MACOS:
        return vlc_root / "plugins", vlc_root / "lib" / "libvlc.dylib"

    if env.IS_LINUX:
        return vlc_root / "vlc" / "plugins", vlc_root / "libvlc.so.5"

    return None, None


def _get_embed_vlc_paths() -> tuple[Path, Path] | tuple[None, None]:
    vlc_root = _get_embed_vlc_root()

    if vlc_root is None:
        return None, None

    return _vlc_paths_for_root(vlc_root)


def _get_embed_vlc_root() -> Path | None:
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
            from gridplayer.vlc_player import vlc
    except (OSError, NotImplementedError):
        return None

    logging.getLogger(__name__).debug("VLC initialized paths")
    logging.getLogger(__name__).debug(f"VLC plugin_path: {vlc.plugin_path}")
    logging.getLogger(__name__).debug(f"VLC dll: {vlc.dll}")

    try:
        vlc_version = vlc.libvlc_get_version()
    except NameError:
        return None

    return vlc_version.decode().split(" ")[0], vlc.__version__
