"""Folder trees looked through off the interface thread, once for every cell.

Looking through a folder and all the ones under it can take seconds on a
network drive, and a grid of cells may all come to the end of a video at
once. The files found are kept, and a cell asking again later is answered
from them while they are looked for again for the next time.
"""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.utils.next_file import FolderScan, ScanRules, scan_folder

_log = logging.getLogger(__name__)

# how long what was found is taken as it is before it is looked for again;
# a library changes seldom, and a file gone since is passed over and has the
# tree looked through again at once
FRESH_SEC = 300

# how long a look may take before it is taken to be stuck, on a drive that
# stopped answering, and another one is let start
STUCK_SEC = 60

# how many trees are kept, the ones looked up last; each one may be thousands
# of paths, and a session may go through any number of folders
MAX_KEPT = 16


@dataclass(frozen=True)
class ScanKey:
    root: Path
    is_recursive: bool
    rules: ScanRules


class FolderIndex(QObject):
    # the key of a scan just finished, its files to be had from lookup
    scanned = pyqtSignal(object)

    # from the scan's thread back to this one
    _found = pyqtSignal(object, object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._scans: OrderedDict[ScanKey, tuple[float, FolderScan]] = OrderedDict()
        # the looks going on, and when each started
        self._in_flight: dict[ScanKey, float] = {}

        self._found.connect(self._on_found)

    def lookup(self, key: ScanKey) -> FolderScan | None:
        """The files last found, however old, None where there are none yet.

        Looked for again where they are not new, the answer coming through
        scanned.
        """

        found = self._scans.get(key)

        if found is None or time.monotonic() - found[0] >= FRESH_SEC:
            self._request(key)

            # one answered there and then is as good as one kept
            found = self._scans.get(key, found)

        if found is None:
            return None

        self._scans.move_to_end(key)

        return found[1]

    def forget(self, key: ScanKey) -> None:
        """Throw away what was found, to be looked for afresh."""

        self._scans.pop(key, None)

    def _request(self, key: ScanKey) -> None:
        started = self._in_flight.get(key)
        now = time.monotonic()

        if started is not None:
            if now - started < STUCK_SEC:
                return

            _log.warning(f"Looking through {key.root} is stuck, starting over")

        self._in_flight[key] = now
        self._start_scan(key)

    def _start_scan(self, key: ScanKey) -> None:
        # a daemon: a drive that stopped answering is no reason to keep
        # the app from closing
        threading.Thread(
            target=self._scan, args=(key,), name="folder-scan", daemon=True
        ).start()

    def _scan(self, key: ScanKey) -> None:
        try:
            scan = scan_folder(key.root, key.is_recursive, key.rules)
        except Exception:
            _log.exception(f"Looking through {key.root} failed")
            scan = FolderScan(root=key.root)

        self._found.emit(key, scan)

    def _on_found(self, key: ScanKey, scan: FolderScan) -> None:
        self._in_flight.pop(key, None)
        self._scans[key] = (time.monotonic(), scan)
        self._scans.move_to_end(key)

        while len(self._scans) > MAX_KEPT:
            self._scans.popitem(last=False)

        _log.debug(
            f"{len(scan.files)} file(s) under {key.root}"
            + (" (cut short)" if scan.is_truncated else "")
        )

        self.scanned.emit(key)


_index: FolderIndex | None = None


def folder_index() -> FolderIndex:
    """The one every cell asks through, made on first use."""

    global _index

    if _index is None:
        _index = FolderIndex()

    return _index
