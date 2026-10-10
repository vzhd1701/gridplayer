"""The files a cell steps through when it moves on to another one.

They are the ones in the video's folder or, with subfolders included, every
one under the folder that was playing when they were. Each folder's own files
come first, then its subfolders' one after the other, all in the order a
person would put them in: by name, numbers counted rather than spelt, so
"Episode 2" comes before "Episode 10".
"""

import os
import random
import re
import stat
import sys
from bisect import bisect_left
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT
from gridplayer.utils.list_progress import ReadingEnough

# folders that operating systems, NAS boxes and file managers keep their own
# things in, not hidden where they were not made on a system that hides them
_CLUTTER_DIRS = frozenset(
    (
        "$recycle.bin",
        "system volume information",
        "lost+found",
        "@eadir",
        "#recycle",
        "#snapshot",
    )
)

# the trash a Linux desktop keeps on a removable drive, one per user
_CLUTTER_DIR_PREFIXES = (".trash-",)

_IS_WINDOWS = sys.platform == "win32"

# what Windows hides by; the attributes are only read there, the names
# being defined everywhere
_WINDOWS_HIDDEN = stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM

# a junction is a link to another folder that Windows does not call one;
# followed, a junction to a folder above it goes round for ever
_JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", None)

# how far back Previous can go in a shuffle
SHUFFLE_HISTORY_LENGTH = 1000

# how many files in a row may be gone from a folder looked through earlier
# before it is taken to be another folder by now, and looked through again;
# each one is asked after on the interface thread, over the network maybe
MAX_MISSING_FILES = 10

_DIGITS = re.compile(r"(\d+)")

# one step of a path from the root: a folder's own files come before its
# subfolders, so a file is 0 and a folder 1
_FILE = 0
_FOLDER = 1


@dataclass(frozen=True)
class ScanRules:
    # whether hidden and system folders and files are passed over
    is_skip_hidden: bool = True
    # how many files and folders to look at before stopping, 0 for no
    # limit: a few videos among a whole drive's files are still a whole
    # drive to go through
    max_entries: int = 0


@dataclass(frozen=True)
class FolderScan:
    """The files found under a root, in the order they are played in."""

    root: Path
    files: tuple[Path, ...] = ()
    # the order each file goes in, kept to find a file's place by
    keys: tuple[tuple, ...] = ()
    # the limit was reached before every folder was looked through
    is_truncated: bool = False

    def _place(self, current: Path) -> tuple[int, bool]:
        """Where the current file is among them, or would be, and whether
        it is there."""

        key = order_key(current, self.root)
        place = bisect_left(self.keys, key)

        # a name told apart by its case alone sorts beside the file it
        # names where the case does not count, which is a file of its own
        # only where it does
        for found in (place, place - 1):
            if 0 <= found < len(self.files) and (
                self.keys[found] == key or self.files[found] == current
            ):
                return found, True

        return place, False

    def neighbour(self, current: Path, step: int) -> Path | None:
        """The file so many places on from the current one, round the end
        back to the start.

        A file that is not among them, renamed or gone since they were
        looked for, is counted from where it would be.
        """

        if not self.files:
            return None

        place, is_found = self._place(current)

        return self.files[neighbour_place(place, is_found, step) % len(self.files)]

    def existing_neighbour(
        self,
        current: Path,
        step: int,
        exists: Callable[[Path], bool] = Path.is_file,
    ) -> Path | None:
        """The next file along that is still there, None where there is
        none, or too many in a row are gone for these to be the files there
        are now."""

        file_path = self.neighbour(current, step)

        for _ in range(MAX_MISSING_FILES):
            if file_path is None or file_path == current or exists(file_path):
                return file_path

            file_path = self.neighbour(file_path, step)

        return None


def neighbour_place(place: int, is_found: bool, step: int) -> int:
    """The place so many on from one, not yet taken round an end. For one
    that is not among them, counted from where it would be: the one there
    now is the one after it, and the one before it the one before that."""

    if not is_found and step > 0:
        return place + step - 1

    return place + step


def natural_key(name: str) -> tuple:
    """A name to sort by the way a person would: by letters without minding
    the case, and by numbers as numbers.

    The name as it is settles a tie, so no two names are ever equal.
    """

    folded = name.casefold()
    parts = _DIGITS.split(folded)

    # split puts the numbers at the odd places, every key alike, so a number
    # is only ever compared with another number
    natural = tuple(int(part) if i % 2 else part for i, part in enumerate(parts))

    return natural, folded, name


def order_key(path: Path, root: Path) -> tuple:
    """Where a file under the root comes in the order they are played in."""

    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = (path.name,)

    folders = tuple((_FOLDER, natural_key(part)) for part in parts[:-1])

    return (*folders, (_FILE, natural_key(parts[-1])))


def is_media_file_name(name: str) -> bool:
    _, dot, extension = name.rpartition(".")

    return bool(dot) and extension.lower() in SUPPORTED_MEDIA_EXT


def scan_folder(
    root: Path, is_recursive: bool, rules: ScanRules | None = None, progress=None
) -> FolderScan:
    """The media files in a folder, and in its subfolders if asked for.

    Links to folders are not followed: one to a folder above it would go
    round for ever, and one elsewhere would play what was never under the
    root. A folder that cannot be read is passed over.

    progress is told how many files are found so far, after each folder:
    ("files", count); where it raises ReadingEnough, the files found by
    then are all there is.
    """

    rules = rules or ScanRules()

    files: list[Path] = []
    budget = _Budget(rules.max_entries)

    # depth first, a folder's subfolders put on in reverse so the first of
    # them is the next one looked into
    folders = [root]
    seen = set()

    while folders and not budget.is_spent:
        folder = folders.pop()

        folder_files, subfolders = _folder_entries(
            folder, rules, seen, is_recursive, budget
        )

        files.extend(folder_files)
        folders.extend(reversed(subfolders))

        if progress is not None:
            try:
                progress("files", len(files))
            except ReadingEnough:
                break

    return FolderScan(
        root=root,
        files=tuple(files),
        keys=tuple(order_key(file_path, root) for file_path in files),
        is_truncated=budget.is_spent or bool(folders),
    )


class _Budget:
    """How many more files and folders may be looked at."""

    def __init__(self, limit: int):
        self._left = limit or None
        self.is_spent = False

    def take(self) -> bool:
        """Whether one more may be looked at."""

        if self._left is None:
            return True

        if self._left == 0:
            self.is_spent = True
            return False

        self._left -= 1

        return True


def _folder_entries(
    folder: Path, rules: ScanRules, seen: set, is_recursive: bool, budget: _Budget
) -> tuple[list[Path], list[Path]]:
    """A folder's media files and the subfolders to look into, each sorted.

    Without subfolders, a folder is never asked whether it is one to go
    into: a folder named like a video is not a file either way.
    """

    files = []
    subfolders = []

    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if not budget.take():
                    break

                if rules.is_skip_hidden and _is_hidden(entry):
                    continue

                if is_recursive and _is_folder_to_enter(entry, seen):
                    subfolders.append(entry.name)
                elif is_media_file_name(entry.name) and _is_file(entry):
                    files.append(entry.name)
    except OSError:
        return [], []

    files.sort(key=natural_key)
    subfolders.sort(key=natural_key)

    return [folder / name for name in files], [folder / name for name in subfolders]


def _is_file(entry: os.DirEntry) -> bool:
    try:
        return entry.is_file()
    except OSError:
        return False


def _is_folder_to_enter(entry: os.DirEntry, seen: set) -> bool:
    try:
        if not entry.is_dir(follow_symlinks=False):
            return False

        entry_stat = entry.stat(follow_symlinks=False)
    except OSError:
        return False

    if _JUNCTION_TAG is not None and (
        getattr(entry_stat, "st_reparse_tag", 0) == _JUNCTION_TAG
    ):
        return False

    # a folder mounted inside itself is the same folder twice; Windows has
    # no number for a folder without asking for it on its own, and has
    # junctions passed over instead
    if sys.platform != "win32":
        folder_id = (entry_stat.st_dev, entry_stat.st_ino)

        if folder_id in seen:
            return False

        seen.add(folder_id)

    return True


def _is_hidden(entry: os.DirEntry) -> bool:
    name = entry.name

    # macOS leaves a "._" file beside each one it copies to a drive that
    # cannot keep what it adds to files, named like a video but not one,
    # whichever system the drive is read on next
    if name.startswith("._"):
        return True

    folded = name.casefold()

    if folded in _CLUTTER_DIRS or folded.startswith(_CLUTTER_DIR_PREFIXES):
        return True

    # a leading dot hides a file everywhere but on Windows, which hides by
    # an attribute instead, read along with the folder and so for nothing
    if not _IS_WINDOWS:
        return name.startswith(".")

    try:
        attributes = entry.stat(follow_symlinks=False).st_file_attributes
    except OSError:
        return False

    return bool(attributes & _WINDOWS_HIDDEN)


@dataclass
class ShuffleBag:
    """Every file once, in an order of its own, before any comes round again.

    What was played is kept, so Previous goes back through it and Next comes
    forward again through the same ones. Kept for one cell, and only for as
    long as the app is open.
    """

    rng: random.Random = field(default_factory=random.Random)

    # the files played, the one playing last
    _played: list[Path] = field(default_factory=list, init=False)
    # the ones still to come before the order starts over
    _pending: list[Path] = field(default_factory=list, init=False)
    # the files there were, to tell those added and those gone from
    _known: frozenset[Path] = field(default=frozenset(), init=False)
    # the root and whether subfolders are included, which a change in
    # starts the order over
    _scope: object = field(default=None, init=False)

    def sync(self, scope, files: Sequence[Path], current: Path) -> None:
        """Bring the order up to date with the files there are now, and with
        the one playing, which may have come some other way."""

        files_set = frozenset(files)

        if scope != self._scope or not self._played:
            self._scope = scope
            self._known = files_set
            self._played = [current]
            self._pending = self._shuffled(f for f in files if f != current)
            return

        added = [f for f in files if f not in self._known]
        gone = self._known - files_set
        self._known = files_set

        if gone:
            self._pending = [f for f in self._pending if f not in gone]

            # the one playing stays, even gone: it is where Previous counts from
            self._played = [
                f for f in self._played[:-1] if f not in gone
            ] + self._played[-1:]

        # put in at random among those still to come
        for file_path in added:
            if file_path != current:
                self._pending.insert(self.rng.randint(0, len(self._pending)), file_path)

        if self._played[-1] != current:
            self._remove_pending(current)
            self._push_played(current)

    @property
    def is_round_over(self) -> bool:
        """Whether every one has been played since the order last started,
        so that the next one starts it over."""

        return bool(self._played) and not self._pending

    def next(
        self,
        avoid: Iterable[Path] = (),
        exists: Callable[[Path], bool] = Path.is_file,
    ) -> Path | None:
        """The next one in the order, starting a new order once every file
        has been played.

        One open elsewhere is put off till later where there is another to
        play, and one that is gone is left out.
        """

        avoid = frozenset(avoid)
        current = self._played[-1] if self._played else None

        while True:
            if not self._pending:
                self._start_over(current)

            if not self._pending:
                return None

            pick = self._first_free(avoid)

            if pick is None:
                # every one still to come is open elsewhere: the next order
                # starts now, with those still owed first in it
                owed = self._pending
                self._start_over(current, owed=owed)
                self._pending = owed + self._pending

                pick = self._first_free(avoid | {current})

                if pick is None:
                    pick = self._first_free(avoid) or 0

            file_path = self._pending.pop(pick)

            if exists(file_path):
                self._push_played(file_path)
                return file_path

            self._known = self._known - {file_path}

    def previous(self, exists: Callable[[Path], bool] = Path.is_file) -> Path | None:
        """The one played before this one that is still there, None where
        there was none.

        This one goes back to be the next to come, and those gone since are
        left out.
        """

        if len(self._played) < 2:
            return None

        current = self._played.pop()

        while self._played and not exists(self._played[-1]):
            self._known = self._known - {self._played.pop()}

        if not self._played:
            self._played.append(current)
            return None

        self._pending.insert(0, current)

        return self._played[-1]

    def _first_free(self, avoid: frozenset[Path]) -> int | None:
        return next((i for i, f in enumerate(self._pending) if f not in avoid), None)

    def _start_over(self, current: Path | None, owed: Sequence[Path] = ()) -> None:
        order = self._shuffled(self._known.difference(owed))

        # not the one that just played first, where there is any other
        if len(order) > 1 and order[0] == current:
            swap = self.rng.randint(1, len(order) - 1)
            order[0], order[swap] = order[swap], order[0]

        self._pending = order

    def _shuffled(self, files: Iterable[Path]) -> list[Path]:
        # sorted first, so the order depends on nothing but the rng
        order = sorted(files)
        self.rng.shuffle(order)

        return order

    def _remove_pending(self, file_path: Path) -> None:
        self._pending = [f for f in self._pending if f != file_path]

    def _push_played(self, file_path: Path) -> None:
        self._played.append(file_path)

        del self._played[:-SHUFFLE_HISTORY_LENGTH]
