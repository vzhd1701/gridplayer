"""Importing python-mpv against the libmpv that was found.

python-mpv loads the library as it is imported, asking ctypes.util.find_library
where it is, and has no setting to say otherwise. So the import is made with
that answered for it, which leaves the vendored file as it is.
"""

import ctypes.util
import locale
import logging
import os
from contextlib import contextmanager
from functools import cache

from gridplayer.params import env
from gridplayer.utils.media_libs import find_libmpv

_log = logging.getLogger(__name__)

# mpv 0.35, the oldest anything here has been tried on
MIN_CLIENT_API = (2, 0)


class LibmpvTooOldError(OSError):
    """Something that goes by the name, without what is asked of it."""


@contextmanager
def _answering_find_library(path: str):
    find_library = ctypes.util.find_library
    ctypes.util.find_library = lambda _name: path

    try:
        yield
    finally:
        ctypes.util.find_library = find_library


def check_client_api(version: tuple[int, int]) -> None:
    if version < MIN_CLIENT_API:
        raise LibmpvTooOldError(f"Client API {version}, need {MIN_CLIENT_API}")


@cache
def load_mpv():
    """The python-mpv module, with libmpv loaded on the first call.

    Raises OSError if there is no libmpv or it won't load, and LibmpvTooOldError,
    which is one too, if it won't do.
    """

    path = find_libmpv()

    if path is None:
        raise OSError("libmpv not found")

    _log.debug(f"Loading libmpv: {path}")

    # On Windows 10 and up mpv asks for 1 ms timers for each wait and lets the
    # request go after it, which a process has one of: the 1 ms Qt's timers
    # asked for too. With two videos open the app's timers came every 15.6 ms,
    # and of 9 videos at 120 fps each showed 97 frames a second, 110 with
    # this. Asked once and kept, read by mpv as its first player starts.
    if env.IS_WINDOWS:
        os.environ.setdefault("MPV_HRT", "always")

    try:
        with _answering_find_library(path):
            from gridplayer.mpv_player import mpv
    # python-mpv's own version check, and a function it asks for not being there
    except (RuntimeError, AttributeError) as e:
        raise LibmpvTooOldError(str(e)) from e

    check_client_api(mpv.MPV_VERSION)

    env.MPV_PYTHON_VERSION = mpv.__version__

    # Qt sets the locale when it starts, and mpv refuses to run without this
    locale.setlocale(locale.LC_NUMERIC, "C")

    return mpv
