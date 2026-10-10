"""What is kept so it is not downloaded again, such as the thumbnails of the
videos on lists: on disk up to a size, the things used longest ago going
first, or only in memory for as long as the app runs, as the settings say.

Each kind of thing kept has a folder of its own; the size is of all of them
together.
"""

import contextlib
import hashlib
import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple

from gridplayer.params.static import CacheMode
from gridplayer.settings import Settings
from gridplayer.utils.app_dir import get_app_cache_dir

_log = logging.getLogger(__name__)

CACHE_SETTINGS = ("cache/mode", "cache/max_mb")

MB = 1024 * 1024

# kept in memory, the cache comes to at most this much, whatever the disk
# is allowed: a few thousand thumbnails
MAX_MEMORY_BYTES = 32 * MB

# grown past its size, the cache is cut to this much of it, so that it is
# not cut again for each thing kept after
TRIMMED_TO = 0.9

_lock = threading.Lock()

# one cut at a time
_trim_lock = threading.Lock()

# what the files on disk come to, once looked over in a run, and counted
# from then on
_disk_bytes: int | None = None

_memory: OrderedDict[tuple[str, str], bytes] = OrderedDict()
_memory_bytes = 0


class _File(NamedTuple):
    path: Path
    size: int
    mtime: float


def cached(kind: str, key: str) -> bytes | None:
    """What was kept under this key, if it still is."""

    if _mode() == CacheMode.MEMORY:
        with _lock:
            data = _memory.get((kind, key))

            if data is not None:
                _memory.move_to_end((kind, key))

            return data

    path = _path(kind, key)

    try:
        data = path.read_bytes()
    except OSError:
        return None

    # the one used last is the one kept longest
    with contextlib.suppress(OSError):
        os.utime(path)

    return data


def keep(kind: str, key: str, data: bytes) -> None:
    """Kept, and the things used longest ago let go of if that takes the
    cache past its size."""

    if _mode() == CacheMode.MEMORY:
        _keep_in_memory((kind, key), data)
    else:
        _keep_on_disk(_path(kind, key), data)


def forget(kind: str, key: str) -> None:
    """No longer kept: what was turned out not to be what was wanted."""

    _forget_in_memory((kind, key))

    path = _path(kind, key)

    with contextlib.suppress(OSError):
        size = path.stat().st_size
        path.unlink()
        _counted(-size)


def kept_bytes() -> int:
    """What the cache comes to now, on disk and in memory."""

    on_disk = sum(file.size for file in _files(cache_root()))

    with _lock:
        return on_disk + _memory_bytes


def clear() -> None:
    """Everything kept let go of, on disk and in memory. A file being read
    at that moment can be left behind."""

    _forget_memory()
    _remove_files()


def apply_settings() -> None:
    """The cache made to fit settings just changed: taken off the disk when
    it is to be kept in memory, cut to a smaller size, its memory let go of
    when it is kept on disk again.

    The disk is seen to in the background: a large cache is a lot of files.
    """

    if _mode() == CacheMode.MEMORY:
        _in_background(_remove_files)
        return

    _forget_memory()

    max_bytes = _max_bytes()

    def trim():
        with _trim_lock:
            _trim(max_bytes)

    _in_background(trim)


def cache_root() -> Path:
    return get_app_cache_dir()


def _mode() -> CacheMode:
    return Settings().get("cache/mode")


def _max_bytes() -> int:
    return Settings().get("cache/max_mb") * MB


def _path(kind: str, key: str) -> Path:
    name = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()

    return cache_root() / kind / name


def _keep_in_memory(key: tuple[str, str], data: bytes) -> None:
    global _memory_bytes

    if len(data) > MAX_MEMORY_BYTES:
        return

    _forget_in_memory(key)

    with _lock:
        _memory[key] = data
        _memory_bytes += len(data)

        while _memory_bytes > MAX_MEMORY_BYTES:
            _, gone = _memory.popitem(last=False)
            _memory_bytes -= len(gone)


def _forget_in_memory(key: tuple[str, str]) -> None:
    global _memory_bytes

    with _lock:
        data = _memory.pop(key, None)

        if data is not None:
            _memory_bytes -= len(data)


def _forget_memory() -> None:
    global _memory_bytes

    with _lock:
        _memory.clear()
        _memory_bytes = 0


def _keep_on_disk(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        replaced = _size(path)
        _write_whole(path, data)
    except OSError as e:
        _log.debug(f"Not kept in the cache: {e}")
        return

    _counted(len(data) - replaced)
    _trim_if_over()


def _write_whole(path: Path, data: bytes) -> None:
    """Written to a file of its own, then put in place whole: never read
    half written by another thread, nor left so by a crash."""

    part = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.part")

    try:
        part.write_bytes(data)
        part.replace(path)
    except OSError:
        with contextlib.suppress(OSError):
            part.unlink()
        raise


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _counted(change: int) -> None:
    global _disk_bytes

    with _lock:
        if _disk_bytes is not None:
            _disk_bytes += change


def _trim_if_over() -> None:
    """Cut once the cache has grown past its size. The files are looked over
    the first time anything is kept in a run, and counted from then on."""

    max_bytes = _max_bytes()

    with _lock:
        if _disk_bytes is not None and _disk_bytes <= max_bytes:
            return

    # a cut under way will do for this one too
    if not _trim_lock.acquire(blocking=False):
        return

    try:
        _trim(max_bytes)
    finally:
        _trim_lock.release()


def _trim(max_bytes: int) -> None:
    """The files used longest ago removed, when the cache is over its size,
    until it is down to TRIMMED_TO of it."""

    global _disk_bytes

    files = sorted(_files(cache_root()), key=lambda file: file.mtime)
    total = sum(file.size for file in files)

    if total > max_bytes:
        left = max_bytes * TRIMMED_TO

        for file in files:
            if total <= left:
                break

            with contextlib.suppress(OSError):
                file.path.unlink()
                total -= file.size

    with _lock:
        _disk_bytes = total


def _remove_files() -> None:
    global _disk_bytes

    with _trim_lock:
        for file in list(_files(cache_root())):
            with contextlib.suppress(OSError):
                file.path.unlink()

        # looked over again the next time anything is kept
        with _lock:
            _disk_bytes = None


def _files(folder: Path) -> Iterator[_File]:
    """Every file in the cache, in the folders of each kind."""

    try:
        entries = list(os.scandir(folder))
    except OSError:
        return

    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                yield from _files(Path(entry.path))
                continue

            if not entry.is_file(follow_symlinks=False):
                continue

            stat = entry.stat(follow_symlinks=False)
        except OSError:
            continue

        yield _File(Path(entry.path), stat.st_size, stat.st_mtime)


def _in_background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="cache", daemon=True).start()
