"""Linux: fewer of glibc's malloc arenas.

glibc gives threads that allocate at the same time arenas of their own, up to
8 a core. Each keeps what was freed in it for its own threads, so with the
many decoder threads of many videos, memory freed by one is held where the
others don't reach it. Measured on 8 cores (MPV_PLAN.md, 10.5): Hardware MPV
with 16 videos 985-991 MB, with 8 arenas 807-820; opening and closing videos
for 10 minutes, 2126 MB still held with all closed, with 8 arenas 1105. VLC
1-4% less with 2.

Fewer arenas means more threads share one arena's lock: 8 keeps nearly all
that 2 or 4 save, with room for that on a big machine.
"""

import ctypes
import os

ARENA_MAX = 8

_M_ARENA_MAX = -8
_ENV = "MALLOC_ARENA_MAX"


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
