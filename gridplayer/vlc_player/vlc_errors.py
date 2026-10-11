"""What VLC said went wrong lately, in this process: kept whatever the log
level, for a player that fails to tell what VLC said as it did.

One log for every player of the process, so each line is kept with the
thread that said it and the VLC object it said it as. A video is opened,
read and decoded on threads of its own, the ones its player's events come
on; anything said on another video's is that video's. Some of its work is
done on threads no event comes on, though: the segments of a stream are
fetched on one of their own. What is said there is the video's where the
object that says it speaks on the video's own threads as well.
"""

import re
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

# VLC objects told apart on a thread at most, before they are let go: a
# video makes a few dozen, the same ones over and over as it plays
HEARD_OBJECTS = 256

# What VLC says of what it does itself rather than of the video: rewinding a
# stream that cannot be, each time :input-repeat starts it over, which a dead
# one does thousands of times a second. Told by how it is put together, so it
# is never put together at all.
_SAID_OF_ITSELF = (b"INPUT_CONTROL_SET_POSITION",)

# What a server answered VLC's own HTTP client. Said only in its debug lines
# where that client fetches the segments of an adaptive stream (HLS, DASH),
# the one place where why a stream would not play is said nowhere else.
_HTTP_ANSWER = b"incoming response:"
_HTTP_REFUSAL = re.compile(r"^HTTP/\d(?:\.\d)? [45]\d\d\b.*$", re.MULTILINE)

_said: deque[tuple[float, int, int, str]] = deque(maxlen=KEPT)

# each thread's second, and how many it kept in it
_counted: dict[int, tuple[float, int]] = {}

# the VLC objects heard on each thread, and when each was last
_heard: dict[int, dict[int, float]] = {}

# the threads some video's events came on
_video_threads: set[int] = set()


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


def is_said_of_vlc_itself(fmt: bytes | None) -> bool:
    """Whether what VLC says, by how it is put together, is of VLC's own
    doing rather than of the video."""

    return fmt is not None and fmt.startswith(_SAID_OF_ITSELF)


def is_http_answer(fmt: bytes | None) -> bool:
    return fmt is not None and fmt.startswith(_HTTP_ANSWER)


def http_refusal(said: str) -> str | None:
    """Where VLC was told what a server answered and it was turned away,
    as the server put it: "http: HTTP/1.1 403 Forbidden"."""

    found = _HTTP_REFUSAL.search(said)

    if found is None:
        return None

    module, _, _ = said.partition(": ")

    return f"{module}: {found.group(0).strip()}"


def note_vlc_object(vlc_object: int) -> None:
    """VLC said something, anything, as this object on this thread."""

    thread = threading.get_ident()
    heard = _heard.get(thread)

    if heard is None:
        if len(_heard) >= COUNTED_THREADS:
            _heard.clear()

        heard = _heard[thread] = {}
    elif len(heard) >= HEARD_OBJECTS and vlc_object not in heard:
        heard.clear()

    heard[vlc_object] = time.time()


def note_video_thread() -> None:
    """A video's player event came on this thread: what is said on it is
    that video's alone."""

    if len(_video_threads) >= COUNTED_THREADS:
        _video_threads.clear()

    _video_threads.add(threading.get_ident())


def keep_vlc_error(text: str, vlc_object: int = 0) -> None:
    _said.append((time.time(), threading.get_ident(), vlc_object, text))


def vlc_errors_since(
    since: float, threads: Collection[int], opened_at: float | None = None
) -> list[str]:
    """What VLC said went wrong since then, the last few of it: on these
    threads, or as an object heard on them since the video was opened on a
    thread of no video's. A line said over and over is told once, with how
    many times."""

    objects = _objects_heard_on(threads, since if opened_at is None else opened_at)

    counted: dict[str, int] = {}

    for at, thread, vlc_object, text in list(_said):
        if at < since:
            continue

        is_its_own = thread in threads or (
            thread not in _video_threads and vlc_object in objects
        )

        if is_its_own:
            counted[text] = counted.get(text, 0) + 1

    said = [
        text if count == 1 else f"{text} ({count} times)"
        for text, count in counted.items()
    ]

    return said[-TOLD:]


def _objects_heard_on(threads: Collection[int], since: float) -> set[int]:
    objects = set()

    for thread in list(threads):
        heard = _heard.get(thread, {})

        objects.update(
            vlc_object for vlc_object, at in list(heard.items()) if at >= since
        )

    # said as no object at all
    objects.discard(0)

    return objects
