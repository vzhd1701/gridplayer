"""Something slow done off the interface thread, told back on it once done."""

import contextlib
import sys
import threading

from PyQt5.QtCore import QObject, pyqtSignal


class OffThread(QObject):
    """Runs a function on a thread of its own, and says what came of it:
    what was asked for, by a word of the caller's, and the result, or the
    error it raised."""

    done = pyqtSignal(str, object, object)

    def run(self, what: str, function, *args) -> None:
        def work():
            try:
                with interface_first():
                    result, error = function(*args), None
            except Exception as e:  # what went wrong is for the caller to say
                result, error = None, e

            # (whoever asked may be gone by the time a slow one is done)
            with contextlib.suppress(RuntimeError):
                self.done.emit(what, result, error)

        threading.Thread(target=work, daemon=True, name=f"off-thread-{what}").start()


# How long a thread runs before another may take its turn, while something
# slow is read off the interface thread. Python's own is 5 ms, and the
# interface handles each of its events in Python, so behind a busy reader it
# waits up to that long for every one of them: an animated cell a frame at a
# time is a stutter of a few hundred ms. A short turn keeps it smooth, for
# the reading taking a little longer.
READING_SWITCH_INTERVAL_S = 0.0005

_readers = 0
_readers_lock = threading.Lock()
_kept_switch_interval = None


@contextlib.contextmanager
def interface_first():
    """Short turns for every thread while this runs, back as they were once
    nothing else is being read either."""

    global _readers, _kept_switch_interval

    with _readers_lock:
        if _readers == 0:
            _kept_switch_interval = sys.getswitchinterval()
            sys.setswitchinterval(READING_SWITCH_INTERVAL_S)
        _readers += 1

    try:
        yield
    finally:
        with _readers_lock:
            _readers -= 1
            if _readers == 0:
                sys.setswitchinterval(_kept_switch_interval)
