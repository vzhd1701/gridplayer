"""Whether files are still there, asked off to the side: telling that can
take a while on a network drive that is gone, so it is asked a few at a
time, and each told as it is known."""

import contextlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

FILE_CHECKS_AT_ONCE = 4


class FileChecks(QObject):
    """What look makes of each file asked about, told by the key it was
    asked by."""

    checked = pyqtSignal(str, object)

    def __init__(self, look: Callable[[Path], object], parent=None):
        super().__init__(parent)

        self._look = look
        self._pool = ThreadPoolExecutor(max_workers=FILE_CHECKS_AT_ONCE)

    def check(self, key: str, path: Path):
        future = self._pool.submit(self._look, path)
        future.add_done_callback(lambda done: self._tell(key, done))

    def stop(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _tell(self, key, done):
        if done.cancelled():
            return

        # (the dialog may be gone by the time a slow one is known)
        with contextlib.suppress(RuntimeError):
            self.checked.emit(key, done.result())
