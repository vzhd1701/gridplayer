"""What VLC said went wrong lately, in this process: kept whatever the log
level, for a player that fails to tell what VLC said as it did.

One log for every player of the process, so each line is kept with the
thread that said it. A video is opened, read and decoded on threads of
its own, the ones its player's events come on; anything said on another
may be another video's.
"""

import threading
import time
from collections import deque
from collections.abc import Collection

# how many are kept, for every video of the process, and how many told with
# an error
KEPT = 256
TOLD = 8

# How many a thread keeps a second at most. A stream gone bad can say the
# same thing hundreds of times a second, and each has to be put together
# before it can be kept, on the thread VLC is playing on.
KEPT_A_SECOND = 20

# threads counted at most, before the count of the ones long gone is let go
COUNTED_THREADS = 1024

_said: deque[tuple[float, int, str]] = deque(maxlen=KEPT)

# each thread's second, and how many it kept in it
_counted: dict[int, tuple[float, int]] = {}


def is_keeping_vlc_errors() -> bool:
    """Whether the error VLC says now, on this thread, is to be kept."""

    thread = threading.get_ident()
    now = time.monotonic()

    began, count = _counted.get(thread, (now, 0))

    if now - began >= 1:
        began, count = now, 0

    if len(_counted) >= COUNTED_THREADS:
        _counted.clear()

    _counted[thread] = (began, count + 1)

    return count < KEPT_A_SECOND


def keep_vlc_error(text: str) -> None:
    _said.append((time.time(), threading.get_ident(), text))


def vlc_errors_since(since: float, threads: Collection[int]) -> list[str]:
    """What VLC said went wrong since then on these threads, the last few
    of it: a line said over and over once, with how many times."""

    counted: dict[str, int] = {}

    for at, thread, text in list(_said):
        if at >= since and thread in threads:
            counted[text] = counted.get(text, 0) + 1

    said = [
        text if count == 1 else f"{text} ({count} times)"
        for text, count in counted.items()
    ]

    return said[-TOLD:]
