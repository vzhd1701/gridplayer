"""Looking up what is known of the items of lists, off the interface thread,
for as long as it takes: the List window it was asked from may be closed
meanwhile, and what is learned still goes onto the list.

What is looked up and how is in utils/item_info.py. Here, it is done a few
at a time and put onto the lists as it comes, the way a cell playing an
item puts on what it learns of it, and how far it has got is told for the
List window to show. A site that turns lookups away stops the rest; they
are kept, to be tried again.
"""

import functools
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal

from gridplayer.models.media_list import ListItem, merged_details
from gridplayer.utils.item_info import (
    YOUTUBE_LIST_MAX,
    FileLengths,
    Found,
    NotFound,
    Refused,
    plan,
    youtube_id,
)
from gridplayer.utils.item_info import look_up_link as site_look_up_link
from gridplayer.utils.item_info import look_up_youtube as site_look_up_youtube

_log = logging.getLogger(__name__)

# how many videos are looked up on their own at once: a site asked more
# often than a person would turns them away
LINKS_AT_ONCE = 2

# how many files the process reading them is asked of at a time
FILES_ASKED_AT_ONCE = 16

# what was learned is put onto its list this often, rather than as each
# item's comes: a list put in anew is shown anew
LEARNED_PUT_ON_MS = 200

# what a lookup is of: a file's length, YouTube's list of the videos, a
# video on its own, and a YouTube video on its own after its list said the
# rest of it, for its views and when it was put up
_FILES = "files"
_YOUTUBE = "youtube"
_LINK = "link"
_DETAILS = "details"

# how many items of each kind are asked about at once
_ASKED_AT_ONCE = {
    _FILES: FILES_ASKED_AT_ONCE,
    _YOUTUBE: YOUTUBE_LIST_MAX,
    _LINK: 1,
    _DETAILS: 1,
}


@dataclass(frozen=True)
class LookupState:
    """How far looking up a list's items has got."""

    count: int
    done: int
    found: int
    not_found: int
    # what the rest is known, and the YouTube videos' views and when each
    # was put up are being looked up, each on its own
    is_details: bool = False
    # the site that turned lookups away; the rest stopped for it, to be
    # tried again
    refused: str | None = None


class _Run:
    """Looking up the items of one list."""

    def __init__(self, list_id: UUID):
        self.list_id = list_id

        # the items asked for, by key: one asked for again while it is
        # looked up is not looked up twice
        self.keys: set[int] = set()

        self.count = 0
        self.done = 0
        self.found = 0
        self.not_found = 0

        self.details_count = 0
        self.details_done = 0
        self.details_found = 0

        # lists of items still to be told apart: which can be looked up
        self.planning = 0

        self.pending: dict[Future, tuple[str, tuple[ListItem, ...]]] = {}

        self.refused: str | None = None
        # what was not looked up for it, and how it was to be
        self.left: list[tuple[str, ListItem]] = []

        # set off the interface thread as a site turns a lookup away, or
        # here as it is stopped: the lookups waiting their turn see it
        # before they ask, rather than once the turning away is told here
        self.halt = threading.Event()

    @property
    def state(self) -> LookupState:
        is_details = (
            self.planning == 0 and self.done >= self.count and self.details_count > 0
        )

        if is_details:
            count, done = self.details_count, self.details_done
        else:
            count, done = self.count, self.done

        return LookupState(
            count=count,
            done=done,
            found=self.found,
            not_found=self.not_found,
            is_details=is_details,
            refused=self.refused,
        )

    @property
    def is_finished(self) -> bool:
        return self.refused is None and self.planning == 0 and not self.pending


class _Halted(Exception):
    """Not looked up: the lookup was stopped, or a site turned another away."""


class ItemLookups(QObject):
    """Looks up the items of lists, and puts what it learns onto them."""

    # how far a list's lookup has got changed: its id
    changed = pyqtSignal(object)

    # a list's lookup done: its id, how many were found, how many not, and
    # how many YouTube videos were found with no views or date: those looked
    # up on their own and not found that way
    finished = pyqtSignal(object, int, int, int)

    # what was put onto a list: its id, and the fields changed by key
    learned = pyqtSignal(object, object)

    # a lookup done, on a thread of its own: what to do with it here
    _came = pyqtSignal(object)

    def __init__(
        self,
        registry,
        look_up_youtube: Callable[[list[str]], dict[str, Found]] = site_look_up_youtube,
        look_up_link: Callable[[str], Found] = site_look_up_link,
        file_lengths: Callable[[list[Path]], list[int | None]] | None = None,
        is_site_link: Callable[[str], bool] | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self._registry = registry

        self._look_up_youtube = look_up_youtube
        self._look_up_link = look_up_link
        self._is_site_link = is_site_link

        self._file_reader = None
        if file_lengths is None:
            self._file_reader = FileLengths()
            file_lengths = self._file_reader.lengths
        self._file_lengths = file_lengths

        self._runs: dict[UUID, _Run] = {}

        self._planner = ThreadPoolExecutor(max_workers=1)
        self._executors = {
            _FILES: ThreadPoolExecutor(max_workers=1),
            _YOUTUBE: ThreadPoolExecutor(max_workers=1),
            _LINK: ThreadPoolExecutor(max_workers=LINKS_AT_ONCE),
        }
        self._executors[_DETAILS] = self._executors[_LINK]

        # learned and not put onto the lists yet: by list, by item
        self._learned: dict[UUID, dict[int, list[Found]]] = {}
        self._learned_timer = QTimer(self)
        self._learned_timer.setSingleShot(True)
        self._learned_timer.setInterval(LEARNED_PUT_ON_MS)
        self._learned_timer.timeout.connect(self._put_on_learned)

        # queued even from here: a future cancelled here is told at once
        self._came.connect(self._on_came, Qt.QueuedConnection)

    def look_up(self, list_id: UUID, items, is_missing_only: bool) -> None:
        """The items of a list looked up, those with nothing known of them
        alone where is_missing_only says so; along with any being looked up
        already."""

        run = self._runs.get(list_id)

        if run is None or run.refused is not None:
            run = _Run(list_id)
            self._runs[list_id] = run

        items = tuple(item for item in items if item.key not in run.keys)
        run.keys.update(item.key for item in items)

        run.planning += 1

        future = self._planner.submit(plan, items, is_missing_only, self._is_site_link)
        future.add_done_callback(
            lambda done: self._came.emit(functools.partial(self._planned, run, done))
        )

        self.changed.emit(list_id)

    def stop(self, list_id: UUID) -> None:
        """What is still to be looked up of a list, not; what is being
        looked up still goes onto it."""

        run = self._runs.pop(list_id, None)

        if run is None:
            return

        run.halt.set()

        for future in list(run.pending):
            future.cancel()

        self._release_files_unless_asked()

        self.changed.emit(list_id)

    def try_again(self, list_id: UUID) -> None:
        """What a site turned away, looked up again."""

        run = self._runs.get(list_id)

        if run is None or run.refused is None:
            return

        again = _Run(list_id)
        self._runs[list_id] = again

        by_kind: dict[str, list[ListItem]] = {}
        for kind, item in run.left:
            by_kind.setdefault(kind, []).append(item)
            again.keys.add(item.key)

        self._submit_all(again, by_kind)

        self.changed.emit(list_id)
        self._after(again)

    def state(self, list_id: UUID) -> LookupState | None:
        """How far looking up a list's items has got; None for none being
        looked up."""

        run = self._runs.get(list_id)

        return None if run is None else run.state

    def shutdown(self) -> None:
        for list_id in list(self._runs):
            self.stop(list_id)

        self._learned_timer.stop()

        self._planner.shutdown(wait=False, cancel_futures=True)
        for executor in set(self._executors.values()):
            executor.shutdown(wait=False, cancel_futures=True)

        if self._file_reader is not None:
            self._file_reader.release()

    # off the interface thread

    def _read_files(self, run, items):
        if run.halt.is_set():
            raise _Halted

        lengths = self._file_lengths([item.uri for item in items])

        return [
            (item, None if length is None else Found(duration_ms=length))
            for item, length in zip(items, lengths)
        ]

    def _read_youtube(self, run, items):
        if run.halt.is_set():
            raise _Halted

        try:
            found = self._look_up_youtube([youtube_id(item.uri) for item in items])
        except Refused:
            run.halt.set()
            raise

        return [(item, found.get(youtube_id(item.uri))) for item in items]

    def _read_link(self, run, items):
        if run.halt.is_set():
            raise _Halted

        (item,) = items

        try:
            return [(item, self._look_up_link(item.uri))]
        except Refused:
            run.halt.set()
            raise
        except NotFound as e:
            _log.debug(f"Nothing found of {item.uri}: {e}")
            return [(item, None)]

    # back here

    def _on_came(self, then):
        then()

    def _planned(self, run: _Run, future: Future):
        run.planning -= 1

        try:
            planned = future.result()
        except Exception:
            _log.exception("Items not told apart for looking up")
            planned = None

        if planned is not None and self._is_current(run) and run.refused is None:
            self._submit_all(
                run,
                {
                    _FILES: planned.files,
                    _YOUTUBE: planned.youtube,
                    _LINK: planned.links,
                },
            )

        self._after(run)

    def _submit_all(self, run: _Run, by_kind: dict):
        for kind, items in by_kind.items():
            if kind == _DETAILS:
                run.details_count += len(items)
            else:
                run.count += len(items)

            at_once = _ASKED_AT_ONCE[kind]

            for start in range(0, len(items), at_once):
                self._submit(run, kind, items[start : start + at_once])

    def _submit(self, run: _Run, kind: str, items):
        items = tuple(items)

        if run.refused is not None or not self._is_current(run):
            run.left.extend((kind, item) for item in items)
            return

        reader = {
            _FILES: self._read_files,
            _YOUTUBE: self._read_youtube,
            _LINK: self._read_link,
            _DETAILS: self._read_link,
        }[kind]

        future = self._executors[kind].submit(reader, run, items)
        run.pending[future] = (kind, items)

        future.add_done_callback(
            lambda done: self._came.emit(functools.partial(self._looked_up, run, done))
        )

    def _looked_up(self, run: _Run, future: Future):
        kind, items = run.pending.pop(future, (None, ()))

        if kind is None or future.cancelled():
            return

        error = future.exception()

        if isinstance(error, Refused):
            self._refuse(run, error.site, kind, items)
            self._after(run)
            return

        # turned away with another, or stopped: kept, to be tried again
        if isinstance(error, _Halted):
            run.left.extend((kind, item) for item in items)
            self._after(run)
            return

        if error is not None:
            _log.error(f"Looking up {len(items)} items failed: {error}")
            results = [(item, None) for item in items]
        else:
            results = future.result()

        is_current = self._is_current(run)

        for item, found in results:
            if found is not None:
                self._learn(run.list_id, item.key, found)

            if not is_current:
                continue

            if kind == _DETAILS:
                run.details_done += 1
                run.details_found += found is not None
            elif kind == _YOUTUBE and found is None:
                # not on YouTube's list of them: looked up on its own
                run.count -= 1
                self._submit_all(run, {_LINK: (item,)})
            else:
                run.done += 1

                if found is not None:
                    run.found += 1
                else:
                    run.not_found += 1

                # the rest of a YouTube video, from its own page
                if kind == _YOUTUBE:
                    self._submit_all(run, {_DETAILS: (item,)})

        self._after(run)

    def _refuse(self, run: _Run, site: str, kind: str, items):
        if run.refused is None:
            run.refused = site

        run.left.extend((kind, item) for item in items)

        for future, (pending_kind, pending_items) in list(run.pending.items()):
            if future.cancel():
                del run.pending[future]
                run.left.extend((pending_kind, item) for item in pending_items)

    def _after(self, run: _Run):
        if not self._is_current(run):
            return

        if run.is_finished:
            del self._runs[run.list_id]

            # what was learned on the list before it is said to be done
            self._put_on_learned()

            found, not_found = run.found, run.not_found
            without_details = run.details_done - run.details_found

            # what a site turned away of the videos' views and dates, tried
            # again: those are what was looked up
            if not run.count and run.details_count:
                found, not_found = run.details_found, without_details
                without_details = 0

            self.finished.emit(run.list_id, found, not_found, without_details)

        self._release_files_unless_asked()

        self.changed.emit(run.list_id)

    def _is_current(self, run: _Run) -> bool:
        return self._runs.get(run.list_id) is run

    def _release_files_unless_asked(self):
        if self._file_reader is None:
            return

        is_asked = any(
            kind == _FILES
            for run in self._runs.values()
            for kind, _items in run.pending.values()
        )

        if not is_asked:
            self._file_reader.release()

    # onto the lists

    def _learn(self, list_id: UUID, key: int, found: Found):
        self._learned.setdefault(list_id, {}).setdefault(key, []).append(found)

        if not self._learned_timer.isActive():
            self._learned_timer.start()

    def _put_on_learned(self):
        self._learned_timer.stop()

        learned, self._learned = self._learned, {}

        for list_id, by_key in learned.items():
            media_list = self._registry.get(list_id)

            if media_list is None:
                continue

            fields_by_key = {}

            for key, founds in by_key.items():
                item = media_list.item_by_key(key)

                if item is None:
                    continue

                fields = learned_fields(item, founds)

                if fields:
                    fields_by_key[key] = fields

            if fields_by_key:
                self._registry.update_items(list_id, fields_by_key)
                self.learned.emit(list_id, fields_by_key)


def learned_fields(item: ListItem, founds: list[Found]) -> dict:
    """What changes of an item with what was learned of it: a title where it
    has none (never over one the viewer gave it, or its list did), the
    length, and what the site says of it over what it said before."""

    fields = {}
    details = item.details

    for found in founds:
        # the first title learned: a YouTube video's list says it first
        is_untitled = item.title is None and "title" not in fields

        if found.title and is_untitled and not isinstance(item.uri, Path):
            fields["title"] = found.title

        if found.duration_ms and found.duration_ms != item.duration_ms:
            fields["duration_ms"] = found.duration_ms

        details = merged_details(details, found.details)

    if details != item.details:
        fields["details"] = details

    return fields
