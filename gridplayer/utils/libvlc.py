import ctypes
import logging
import os
import platform
import re
import sys
from importlib.util import find_spec

from gridplayer import params_env

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    EMBED_VLC_PATH = os.path.join(os.path.dirname(sys.executable), "libVLC")
    EMBED_VLC_LIB_PATH = os.path.join(EMBED_VLC_PATH, "libvlc.dll")
elif platform.system() == "Darwin":
    EMBED_VLC_PATH_ROOT = os.path.join(os.path.dirname(sys.executable), "libVLC")

    EMBED_VLC_PATH = os.path.join(EMBED_VLC_PATH_ROOT, "plugins")
    EMBED_VLC_LIB_PATH = os.path.join(EMBED_VLC_PATH_ROOT, "lib", "libvlc.5.dylib")
elif params_env.IS_SNAP:
    EMBED_VLC_PATH_ROOT = os.path.join(
        os.environ["SNAP"], "usr", "lib", "x86_64-linux-gnu"
    )

    EMBED_VLC_PATH = os.path.join(EMBED_VLC_PATH_ROOT, "vlc")
    EMBED_VLC_LIB_PATH = os.path.join(EMBED_VLC_PATH_ROOT, "libvlc.so.5")
elif params_env.IS_APPIMAGE:
    EMBED_VLC_PATH_ROOT = os.path.join(
        os.environ["APPDIR"], "usr", "lib", "x86_64-linux-gnu"
    )

    EMBED_VLC_PATH = os.path.join(EMBED_VLC_PATH_ROOT, "vlc")
    EMBED_VLC_LIB_PATH = os.path.join(EMBED_VLC_PATH_ROOT, "libvlc.so.5")
else:
    EMBED_VLC_PATH = None
    EMBED_VLC_LIB_PATH = None


def pre_import_embed_vlc():
    if "vlc" in sys.modules:
        return

    if platform.system() == "Darwin" and "PYTHON_VLC_LIB_PATH" in os.environ:
        vlc_core = os.path.join(EMBED_VLC_PATH_ROOT, "lib", "libvlccore.9.dylib")
        ctypes.CDLL(vlc_core)


def get_python_vlc_version_pyinstaller():
    version_file = os.path.join(sys._MEIPASS, "python-vlc.version")  # noqa: WPS437

    with open(version_file, "r", encoding="utf-8") as f:
        version_txt = f.read()

    return version_txt.strip()


def get_python_vlc_version():
    vlc_lib_path = find_spec("vlc").origin

    with open(vlc_lib_path, "r", encoding="utf-8") as f:
        vlc_src = f.read()

    return re.search('__version__ = "([^"]*)', vlc_src).group(1)


def get_vlc_version():
    pre_import_embed_vlc()

    try:
        import vlc  # noqa: WPS433
    except (OSError, NotImplementedError):
        return None

    logger.debug(f"VLC lib: {vlc.dll}")

    try:
        vlc_version = vlc.libvlc_get_version()
    except NameError:
        return None

    return vlc_version.decode().split(" ")[0]


def init_vlc():
    if EMBED_VLC_PATH:
        logger.debug(f"EMBED_VLC_PATH: {EMBED_VLC_PATH}")
        logger.debug(f"EMBED_VLC_LIB_PATH: {EMBED_VLC_LIB_PATH}")

        if not os.path.isfile(EMBED_VLC_LIB_PATH) or not os.path.isdir(EMBED_VLC_PATH):
            logger.info("Embedded vlc lib not found, will try to find system VLC...")
        else:
            os.environ["PYTHON_VLC_MODULE_PATH"] = EMBED_VLC_PATH
            os.environ["PYTHON_VLC_LIB_PATH"] = EMBED_VLC_LIB_PATH
    else:
        logger.info("No embedded vlc path, will try to find system VLC...")

    if params_env.IS_PYINSTALLER:
        vlc_python_version = get_python_vlc_version_pyinstaller()
    else:
        vlc_python_version = get_python_vlc_version()

    vlc_version = get_vlc_version()

    logger.debug(f"python-vlc {vlc_python_version}")
    logger.debug(f"VLC {vlc_version}")

    if vlc_version is None:
        raise FileNotFoundError

    return vlc_version, vlc_python_version
