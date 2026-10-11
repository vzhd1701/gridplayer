"""Whether files are still there, asked off to the side and each told on
the asker's own thread, on a later turn of it."""

import threading
import time
from pathlib import Path

from PyQt5.QtTest import QTest

from gridplayer.utils.file_checks import FileChecks


def _wait_until(condition, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if condition():
            return True
    return False


def test_a_check_done_at_once_is_not_told_while_asking():
    """A future done already calls a callback given it there and then: the
    List window was marking its files missing while still filling its rows,
    on Linux, where a file is looked for quicker."""

    checks = FileChecks(lambda path: True)
    told = []
    checks.checked.connect(
        lambda key, found: told.append((key, found, threading.current_thread()))
    )

    submit = checks._pool.submit

    def submit_and_finish(*args):
        future = submit(*args)
        future.result()
        return future

    checks._pool.submit = submit_and_finish

    try:
        checks.check("a", Path("a"))

        assert told == []

        assert _wait_until(lambda: told)
        assert told == [("a", True, threading.main_thread())]
    finally:
        checks.stop()
