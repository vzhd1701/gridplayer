"""Finding libmpv, and saying which one it is."""

import logging
import os
import sys
from pathlib import Path

from gridplayer.params import env

MPV_DIR_ENV = "GRIDPLAYER_MPV_DIR"
LIB_NAME = "libmpv-2.dll"


def init_mpv() -> str:
    """Make libmpv loadable here and in the processes started from here.

    Children inherit PATH, which is where python-mpv looks on Windows.
    Returns the version; raises FileNotFoundError where there is no libmpv.
    """

    log = logging.getLogger(__name__)

    lib_dir = _find_lib_dir()

    if lib_dir is not None:
        log.debug(f"Using libmpv from {lib_dir}")
        os.environ["PATH"] = f"{lib_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    try:
        import mpv

        player = mpv.MPV(config=False, vo="null", ao="null")
    except (OSError, AttributeError) as exc:
        log.info(f"libmpv could not be loaded: {exc}")
        raise FileNotFoundError from exc

    try:
        return str(player.mpv_version).removeprefix("mpv ")
    finally:
        player.terminate()


def _find_lib_dir() -> Path | None:
    if not env.IS_WINDOWS:
        return None

    for candidate in _candidate_dirs():
        if (candidate / LIB_NAME).is_file():
            return candidate

    return None


def _candidate_dirs():
    if os.environ.get(MPV_DIR_ENV):
        yield Path(os.environ[MPV_DIR_ENV])

    if env.IS_PYINSTALLER:
        yield Path(sys.executable).parent / "libmpv"

    # a checkout, with libmpv unpacked beside the code for development
    yield Path(__file__).resolve().parents[2] / ".local-tools" / "mpv"
