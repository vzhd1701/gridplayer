"""Linux: glibc's malloc made to keep less.

Fewer arenas. glibc gives threads that allocate at the same time arenas of
their own, up to 8 a core. Each keeps what was freed in it for its own
threads, so with the many decoder threads of many videos, memory freed by one
is held where the others don't reach it. Measured on 8 cores (docs/archive/MPV_PLAN.md,
10.5): Hardware MPV with 16 videos 985-991 MB, with 8 arenas 807-820; opening
and closing videos for 10 minutes, 2126 MB still held with all closed, with 8
arenas 1105. VLC 1-4% less with 2. Fewer arenas means more threads share one
arena's lock: 8 keeps nearly all that 2 or 4 save, with room for that on a big
machine.

What a closed video freed, given back. Its big buffers (frames: 8 MB at 1080p)
come from the arenas rather than mapped on their own once a few have been
freed, and an arena gives back only what is free at its very end. After 3
minutes of opening and closing (docs/findings/VLC.md, 10.29), with all closed:
Software VLC in a single process 5362 MB, 277 once given back; Hardware MPV
1105, 309.
"""

import ctypes
import os
import sys
import threading

ARENA_MAX = 8

GIVE_BACK_AFTER_S = 2

_M_ARENA_MAX = -8
_ENV = "MALLOC_ARENA_MAX"

_pending_trim: threading.Timer | None = None
_pending_lock = threading.Lock()


def limit_malloc_arenas() -> bool:
    """Limit this process's arenas, and those of the processes it starts.
    Whether it did. Before any thread, as arenas made stay."""

    # someone's own, which glibc has already taken as it started
    if _ENV in os.environ:
        return False

    try:
        mallopt = ctypes.CDLL(None).mallopt
    except (OSError, AttributeError):
        return False

    mallopt.argtypes = (ctypes.c_int, ctypes.c_int)
    mallopt.restype = ctypes.c_int

    # not glibc: musl has mallopt, taking nothing
    if not mallopt(_M_ARENA_MAX, ARENA_MAX):
        return False

    # forked processes keep the limit; processes started fresh (spawn,
    # forkserver) have glibc read it from here
    os.environ[_ENV] = str(ARENA_MAX)

    return True


def give_back_freed_memory() -> None:
    """Give the system what glibc holds freed, a moment after a video is let
    go of: by then its cell, with the frames it showed, is gone too, and the
    rest of a grid closing with it. Nothing outside Linux, or without glibc.

    Tens of milliseconds with gigabytes held, so on a thread of its own; the
    GIL is let go of meanwhile.
    """

    global _pending_trim

    if not sys.platform.startswith("linux"):
        return

    with _pending_lock:
        if _pending_trim is not None:
            return

        _pending_trim = threading.Timer(GIVE_BACK_AFTER_S, _give_back)
        _pending_trim.daemon = True
        _pending_trim.start()


def _give_back() -> None:
    global _pending_trim

    with _pending_lock:
        _pending_trim = None

    try:
        malloc_trim = ctypes.CDLL(None).malloc_trim
    except (OSError, AttributeError):
        return

    malloc_trim.argtypes = (ctypes.c_size_t,)
    malloc_trim.restype = ctypes.c_int

    malloc_trim(0)
