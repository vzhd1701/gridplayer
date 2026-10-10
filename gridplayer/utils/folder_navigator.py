"""One cell's way through the files of its folder, or of a tree of them.

Which file comes next, which one before, and which at random, for a video
of the cell's; the cell itself only puts the file found in its place.
"""

import contextlib
from collections.abc import Callable, Iterable
from enum import Enum, auto
from pathlib import Path
from typing import NamedTuple

from gridplayer.models.video import Video
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.folder_index import ScanKey, folder_index
from gridplayer.utils.next_file import FolderScan, ScanRules, ShuffleBag, scan_folder
from gridplayer.utils.qt import translate


class FolderStep(Enum):
    NEXT = auto()
    PREVIOUS = auto()
    # one not played yet, at random
    RANDOM = auto()
    # back to the one played before, at random
    BACK = auto()


def scan_rules() -> ScanRules:
    """How a folder and the folders in it are read, as the playlist says."""

    settings = PlaylistSettings()

    return ScanRules(
        is_skip_hidden=settings.get("playlist/folder_skip_hidden"),
        max_entries=settings.get("playlist/folder_max_entries"),
    )


class _PendingStep(NamedTuple):
    """A step to take once the tree has been looked through."""

    key: ScanKey
    step: FolderStep
    # the file it was asked from, to know it is still the one playing
    uri: Path
    # asked for by the end of the video, rather than by the viewer
    is_end: bool


class FolderNavigator:
    """Finds the file to take a cell's video's place.

    A folder of its own is looked through there and then, as quick as it
    ever was. A tree of them may take a while, and is looked through off
    the interface thread, the step taken once it has been, unless the
    viewer did something else with the video meanwhile (see cancel).
    """

    def __init__(
        self,
        video: Callable[[], Video | None],
        switch: Callable[[Path | None], None],
        tell: Callable[[str], None],
        tell_next: Callable[[str], None],
        hold_end: Callable[[], bool],
        open_elsewhere: Callable[[], Iterable[Path]],
    ):
        # the video playing now, and what to do with the file found for it:
        # put it in its place, None where there is none
        self._video = video
        self._switch = switch
        # a word on the cell's overlay, now or once the next file shows
        self._tell = tell
        self._tell_next = tell_next
        # for a step the end of the video asked for, taken late: hold the
        # video where it is instead if it is to stay, and say whether it did
        self._hold_end = hold_end
        # the files the other cells have open
        self._open_elsewhere = open_elsewhere

        # the order random files are played in
        self._shuffle_bag = ShuffleBag()
        self._pending: _PendingStep | None = None
        # the last tree said to have more files than are looked at
        self._truncation_told: ScanKey | None = None

        folder_index().scanned.connect(self._scanned)

    @property
    def is_waiting(self) -> bool:
        return self._pending is not None

    def step(self, step: FolderStep, is_end=False, is_retry=False) -> None:
        key = self._scan_key()

        self._pending = None

        if not key.is_recursive:
            scan = scan_folder(key.root, is_recursive=False, rules=key.rules)
            self._take_step(step, scan, key, is_end=is_end, is_retry=True)
            return

        scan = folder_index().lookup(key)

        if scan is None:
            self._pending = _PendingStep(
                key=key, step=step, uri=self._video().uri, is_end=is_end
            )
            self._tell(translate("Folder Navigation", "Scanning folders…"))
            return

        self._take_step(step, scan, key, is_end=is_end, is_retry=is_retry)

    def cancel(self) -> None:
        """Take no step for a tree still being looked through: the viewer
        did something else with the video meanwhile."""

        self._pending = None

    def close(self) -> None:
        self._pending = None

        # gone already where the index went first, at the app's end
        with contextlib.suppress(TypeError):
            folder_index().scanned.disconnect(self._scanned)

    def _scan_key(self) -> ScanKey:
        video = self._video()

        if not video.is_dir_recursive:
            is_skip_hidden = PlaylistSettings().get("playlist/folder_skip_hidden")

            return ScanKey(
                root=video.uri.parent,
                is_recursive=False,
                rules=ScanRules(is_skip_hidden=is_skip_hidden),
            )

        # from a playlist saved before there was a root to keep, or with the
        # file moved out from under it
        if video.dir_root is None or not video.uri.is_relative_to(video.dir_root):
            video.dir_root = video.uri.parent

        return ScanKey(root=video.dir_root, is_recursive=True, rules=scan_rules())

    def _scanned(self, key: ScanKey) -> None:
        pending = self._pending

        if pending is None or pending.key != key:
            return

        # another file came some other way meanwhile
        video = self._video()
        if video is None or video.uri != pending.uri:
            self._pending = None
            return

        # thrown away by another cell as soon as it came, and being looked
        # for again: still to wait for
        scan = folder_index().lookup(key)
        if scan is None:
            return

        self._pending = None

        # the bookmarks being edited since the video came to its end keep
        # it where it is, as they would have had they been open at the end
        if pending.is_end and self._hold_end():
            return

        # just looked through, so no use looking through it again
        self._take_step(pending.step, scan, key, is_end=pending.is_end, is_retry=True)

    def _take_step(
        self,
        step: FolderStep,
        scan: FolderScan,
        key: ScanKey,
        is_end: bool,
        is_retry: bool,
    ) -> None:
        if scan.is_truncated and key != self._truncation_told:
            self._truncation_told = key

            self._tell_next(
                translate(
                    "Folder Navigation",
                    "Stopped looking after {COUNT} files and folders",
                ).format(COUNT=key.rules.max_entries)
            )

        current = self._video().uri

        if step in {FolderStep.RANDOM, FolderStep.BACK}:
            self._shuffle_bag.sync((key.root, key.is_recursive), scan.files, current)

        if step == FolderStep.RANDOM:
            new_video = self._shuffle_bag.next(avoid=self._files_to_avoid())
        elif step == FolderStep.BACK:
            # with none played before, the one playing starts over
            new_video = self._shuffle_bag.previous() or current
        else:
            new_video = scan.existing_neighbour(
                current, 1 if step == FolderStep.NEXT else -1
            )

        # a tree looked through a while ago, and gone through since
        if new_video is None and not is_retry:
            folder_index().forget(key)
            self.step(step, is_end=is_end, is_retry=True)
            return

        self._switch(new_video)

    def _files_to_avoid(self) -> set[Path]:
        if not PlaylistSettings().get("playlist/shuffle_avoid_open"):
            return set()

        return set(self._open_elsewhere())
