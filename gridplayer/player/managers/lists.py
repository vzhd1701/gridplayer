"""The playlist's lists of files and links, which cells play from.

One list can be played from by several cells, each at its own place on it:
a channel list with a cell on each of four channels. A cell reads its list
from here as it steps along it, so a list edited in one is the list the
others step through too.
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox

from gridplayer.dialogs.make_list import MakeFrom, MakeListDialog
from gridplayer.dialogs.media_list import ListReading, MediaListDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.playlist_lists import PlaylistListsDialog
from gridplayer.models.media_list import ListItem, MediaList, item_of_video
from gridplayer.models.video import Video
from gridplayer.params.static import AddMode, ListView
from gridplayer.player.managers.add_videos import (
    list_end_action,
    list_read_limit,
    list_readers,
    media_name_filters,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.player.managers.list_info import ItemLookups
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.folder_navigator import scan_rules
from gridplayer.utils.list_cache import kept_read
from gridplayer.utils.list_errors import ReadError, read_error_of
from gridplayer.utils.list_progress import ReadingStopped, Throttled
from gridplayer.utils.list_refresh import refreshed, uri_key
from gridplayer.utils.list_update import is_due
from gridplayer.utils.media_import import (
    expand_inputs,
    folder_list,
    plan_cells,
    read_source,
)
from gridplayer.utils.off_thread import OffThread
from gridplayer.utils.qt import translate
from gridplayer.utils.thumbnails import fetch_thumbnail


class MediaListsRegistry(QObject):
    """Every list of the playlist, by its id.

    A list taken up by a cell and left by it since, the cell closed or put
    on another list, goes once the playlist is saved, as the bookmarks of a
    closed cell do. One no cell has taken up yet stays: read with the
    playlist while its cells' files were not there, it is still theirs.
    """

    # the id of the list that changed
    changed = pyqtSignal(object)

    # another playlist's, or none, in place of those there were
    replaced = pyqtSignal()

    # how far reading a list has got, for the cell waiting for it: the
    # cell's video id, what to say, and how far in percent, 0 for not known
    waiting_progress = pyqtSignal(object, str, int)

    # items the viewer put on a list, a list made by adding things among
    # them: the list's id and the items' keys
    items_added = pyqtSignal(object, object)

    # a linked list's source being read again as the playlist opens: the
    # list's id, as it starts and as it ends
    reading_changed = pyqtSignal(object)

    # and how far it has got: the list's id, and what
    # list_progress.Throttled was told
    reading_progress = pyqtSignal(object, str, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._lists: dict[UUID, MediaList] = {}

        # the lists a cell has played from since they were read or made
        self._taken_up: set[UUID] = set()

        # the cells, by their videos' ids, waiting for a list being read,
        # with what to set to stop reading it
        self._waiting: dict[UUID, threading.Event] = {}

        # the group each list's window was on last, to open on it again; for
        # as long as the playlist is open
        self._viewed_groups: dict[UUID, str | None] = {}

        # and what its items were shown by there
        self._views: dict[UUID, ListView] = {}

        # the lists being read again, with what to set to stop it; and
        # what came of the last time each could not be
        self._being_read: dict[UUID, threading.Event] = {}
        self._read_errors: dict[UUID, ReadError] = {}

        # the linked lists the playlist opened with, to be read again as it
        # opens; and those not read yet, with only the items cells play
        self._to_read: set[UUID] = set()
        self._as_saved: set[UUID] = set()

    def get(self, list_id: UUID | None) -> MediaList | None:
        if list_id is None:
            return None

        return self._lists.get(list_id)

    def lists(self) -> list[MediaList]:
        return list(self._lists.values())

    def add(self, media_list: MediaList) -> MediaList:
        """A list made or brought from elsewhere, under an id of its own.

        One that came from the same playlist as one already here may have
        the same id and still be another list by now; the one here stays
        what it is.
        """

        known = self._lists.get(media_list.id)

        if known is not None and known != media_list:
            media_list = media_list.model_copy(update={"id": MediaList().id})

        # one read from its source just now, for that to be said
        if media_list.source is not None and media_list.read_at is None:
            media_list = media_list.model_copy(update={"read_at": int(time.time())})

        self._lists[media_list.id] = media_list

        self.changed.emit(media_list.id)

        return media_list

    def put(self, media_list: MediaList) -> None:
        """A list as it is now, in place of the one with its id."""

        # (by the object: told apart item by item, a long list takes a while)
        if self._lists.get(media_list.id) is media_list:
            return

        self._lists[media_list.id] = media_list

        self.changed.emit(media_list.id)

    def rename_item(self, list_id: UUID, key: int, title: str | None) -> None:
        """An item given a name by the viewer, or its own back for None:
        reading the list again leaves a name given be."""

        self.update_item(list_id, key, title=title, is_renamed=title is not None)

    def update_item(self, list_id: UUID, key: int, **fields) -> None:
        """An item of a list, by its key, with these fields changed."""

        self.update_items(list_id, {key: fields})

    def update_items(self, list_id: UUID, fields_by_key: dict[int, dict]) -> None:
        """Items of a list, by their keys, with these fields changed: as one
        change, for the cells and the List window to take in once."""

        media_list = self._lists.get(list_id)

        if media_list is None:
            return

        changed = media_list.with_fields(fields_by_key)

        if changed is not media_list:
            self.put(changed)

    def tell_added(self, list_id: UUID, keys) -> None:
        """Items put on a list by the viewer, rather than read from where it
        came from: for what is known of them to be looked up, where the
        playlist says to."""

        if keys:
            self.items_added.emit(list_id, list(keys))

    def remove(self, list_id: UUID) -> None:
        """A list gone, taken away by the viewer."""

        self._lists.pop(list_id)
        self._taken_up.discard(list_id)

        self.changed.emit(list_id)

    def remember_group(self, list_id: UUID, group: str | None) -> None:
        """The group of a list looked at in its window: None for all of
        them, an empty one for the items of none."""

        self._viewed_groups[list_id] = group

    def remembered_group(self, list_id: UUID) -> str | None:
        return self._viewed_groups.get(list_id)

    def remember_view(self, list_id: UUID, view: ListView) -> None:
        """What the items of a list were shown by in its window."""

        self._views[list_id] = view

    def remembered_view(self, list_id: UUID) -> ListView | None:
        return self._views.get(list_id)

    def wait_for_list(self, video_id: UUID) -> threading.Event:
        """The cell with this video is to play a list still being read: it
        says so, and loads nothing until it is told to. What is set once it
        waits no more, for the reading to stop: the cell closed."""

        stop = self._waiting.get(video_id)

        if stop is None:
            stop = self._waiting[video_id] = threading.Event()

        return stop

    def is_waiting(self, video_id: UUID) -> bool:
        return video_id in self._waiting

    def tell_waiting(self, video_id: UUID, text: str, percent: int = 0) -> None:
        if video_id in self._waiting:
            self.waiting_progress.emit(video_id, text, percent)

    def stop_waiting(self, video_id: UUID) -> None:
        stop = self._waiting.pop(video_id, None)

        if stop is not None:
            stop.set()

    def start_reading(self, list_id: UUID, stop: threading.Event) -> None:
        """A linked list being read again from its source: its window says
        so, and waits for it to be read to be edited."""

        self._being_read[list_id] = stop
        self._read_errors.pop(list_id, None)

        self.reading_changed.emit(list_id)

    def tell_reading(self, list_id: UUID, what: str, count, of) -> None:
        if list_id in self._being_read:
            self.reading_progress.emit(list_id, what, count, of)

    def expect_reading(self, list_ids) -> None:
        """Linked lists the playlist opened with, to be read again as it
        opens."""

        list_ids = set(list_ids)

        self._to_read |= list_ids
        self._as_saved |= list_ids

    def is_read_expected(self, list_id: UUID) -> bool:
        """Whether the list is still to be read again as the playlist
        opens, or is being read."""

        return list_id in self._to_read

    def is_as_saved(self, list_id: UUID) -> bool:
        """Whether the list has only what the playlist kept of it, not read
        again since it opened: a linked one, the items cells play."""

        return list_id in self._as_saved

    def mark_read(self, list_id: UUID) -> None:
        """Read again since the playlist opened, from the cache or its
        source."""

        self._as_saved.discard(list_id)

    def finish_reading(self, list_id: UUID, error: ReadError | None = None) -> None:
        """Read, or not, and what it could not be read for."""

        was_expected = list_id in self._to_read
        self._to_read.discard(list_id)

        if self._being_read.pop(list_id, None) is None:
            # let go of unread, taken away meanwhile
            if was_expected:
                self.reading_changed.emit(list_id)
            return

        if error is not None:
            self._read_errors[list_id] = error

        self.reading_changed.emit(list_id)

    def stop_reading(self, list_id: UUID) -> None:
        """Reading it stopped, the list left as it is."""

        stop = self._being_read.get(list_id)

        if stop is not None:
            stop.set()
            self.finish_reading(list_id)

    def is_being_read(self, list_id: UUID) -> bool:
        return list_id in self._being_read

    def read_error(self, list_id: UUID) -> ReadError | None:
        """Why the list could not be read again, the last time it was."""

        return self._read_errors.get(list_id)

    def remember_read_error(self, list_id: UUID, error: ReadError) -> None:
        """Why the list could not be read again from its List window: said
        again when the window opens next."""

        self._read_errors[list_id] = error

    def forget_read_error(self, list_id: UUID) -> None:
        self._read_errors.pop(list_id, None)

    def take_up(self, list_id: UUID) -> None:
        """A cell plays from this list now."""

        self._taken_up.add(list_id)

    def is_taken_up(self, list_id: UUID) -> bool:
        """Whether a cell has played from this list since it was read."""

        return list_id in self._taken_up

    def drop_if_untaken(self, list_id: UUID | None) -> None:
        """A list added for a cell that never came, a full grid turning it
        away: no cell to play from it, and none ever will."""

        if list_id is None or list_id in self._taken_up:
            return

        if self._lists.pop(list_id, None) is not None:
            self.changed.emit(list_id)

    def load(self, lists) -> None:
        """Take the playlist's, in place of any there were."""

        for stop in (*self._being_read.values(), *self._waiting.values()):
            stop.set()

        self._lists = {media_list.id: media_list for media_list in lists}
        self._taken_up = set()
        self._waiting = {}
        self._viewed_groups = {}
        self._views = {}
        self._being_read = {}
        self._read_errors = {}
        self._to_read = set()
        self._as_saved = set()

        self.replaced.emit()

    def clear(self) -> None:
        self.load(())

    def kept(self, lists_in_use) -> list[MediaList]:
        """The lists but those left by every cell that played from them:
        what a playlist saved now keeps."""

        return [
            media_list
            for media_list in self._lists.values()
            if media_list.id in lists_in_use or media_list.id not in self._taken_up
        ]

    def forget_left(self, lists_in_use) -> None:
        kept = self.kept(lists_in_use)

        if len(kept) == len(self._lists):
            return

        gone = set(self._lists) - {media_list.id for media_list in kept}

        self._lists = {media_list.id: media_list for media_list in kept}
        self._taken_up -= gone


@dataclass
class _LinkedReading:
    """A linked list being read again from its source: as the playlist
    is loaded, from the cache first, where what it had last time is kept,
    then from the source itself where it is due to be; while it is open,
    from the source once it is."""

    list_id: UUID
    stop: threading.Event
    serial: int
    # "kept", then "source"
    phase: str
    is_loading: bool
    # a copy of what the source had found in the cache, to show
    has_copy: bool = False


# how often the linked lists are looked at while the playlist is open
LINKED_CHECK_MS = 60_000

# a source that could not be read is not asked again for this long, while
# the playlist is open: a site turning it away, or no network
LINKED_RETRY_AFTER_S = 15 * 60


class ListsManager(ManagerBase):
    error = pyqtSignal(str)

    # how far reading a linked list has got, from the thread reading it:
    # the list's id, and what list_progress.Throttled was told
    _linked_progress = pyqtSignal(object, str, object, object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._registry = MediaListsRegistry(parent=self)

        self._ctx.lists = self._registry

        # a folder read for a cell to play as a list, off the interface
        # thread, and the cell it is read for
        self._off_thread = OffThread(self)
        self._off_thread.done.connect(self._folder_read)
        self._reading_for = None

        # the List window open on a cell, beside the player: one at a time,
        # for the cell it plays in to be the one marked
        self._window: MediaListDialog | None = None

        # where the one closed for another was, for that to open in its place
        self._window_place = None

        # what is known of items put on lists, looked up for as long as it
        # takes, the List window it was asked from closed or not
        self._lookups = ItemLookups(self._registry, parent=self)
        self._registry.items_added.connect(self._on_items_added)

        # the linked lists read again from their sources as the playlist
        # opens, one after the other: kinder to the sites they are on, and
        # a channel list takes all the memory one reading needs; each
        # reading by a number of its own, for one of a playlist since
        # replaced to be let go of
        self._linked = OffThread(self)
        self._linked.done.connect(self._on_linked_read)
        self._linked_progress.connect(self._registry.tell_reading)
        self._linked_to_read: list[tuple[UUID, bool]] = []
        self._linked_reading: _LinkedReading | None = None
        self._linked_serial = 0

        # and while it is open, once their copies are as old as it lets
        # them be; one that could not be read is let be for a while
        self._linked_retry_at: dict[UUID, float] = {}
        self._linked_timer = QTimer(self)
        self._linked_timer.setInterval(LINKED_CHECK_MS)
        self._linked_timer.timeout.connect(self._read_due_linked)
        self._linked_timer.start()

        # the list a List window opened over another window is open on,
        # not read again from under it
        self._modal_list_id: UUID | None = None

    @property
    def commands(self):
        return {
            "lists_to_save": self.lists_to_save,
            "forget_left_lists": self.forget_left_lists,
            "is_active_list_cell": self.is_active_list_cell,
            "is_any_videos_list_cell": self.is_any_videos_list_cell,
            "is_active_video_set": self.is_active_video_set,
            "manage_list": self.cmd_manage_list,
            "list_window_for": self.list_window_for,
            "lists_in_playlist": self.cmd_lists_in_playlist,
            "open_list_in_new_cell": self.open_list_in_new_cell,
        }

    def set_lists(self, lists):
        self._stop_linked_reading()

        self._registry.load(lists)

        self._linked_to_read = [
            (media_list.id, True)
            for media_list in lists
            if media_list.is_linked and media_list.source is not None
        ]
        self._registry.expect_reading(
            list_id for list_id, _is_loading in self._linked_to_read
        )
        self._read_next_linked()

    def clear(self):
        self._stop_linked_reading()

        self._registry.clear()

    def cleanup(self):
        self._linked_timer.stop()
        self._stop_linked_reading()

        self._lookups.shutdown()

    # linked lists, read again as the playlist opens

    def _stop_linked_reading(self):
        self._linked_serial += 1
        self._linked_to_read = []
        self._linked_retry_at = {}

        reading, self._linked_reading = self._linked_reading, None

        if reading is not None:
            reading.stop.set()
            self._registry.finish_reading(reading.list_id)

    def _read_next_linked(self):
        while self._linked_to_read:
            list_id, is_loading = self._linked_to_read.pop(0)
            media_list = self._registry.get(list_id)

            # taken away, or unlinked, meanwhile
            if (
                media_list is None
                or not media_list.is_linked
                or media_list.source is None
            ):
                self._registry.finish_reading(list_id)
                continue

            reading = _LinkedReading(
                list_id=list_id,
                stop=threading.Event(),
                serial=self._linked_serial,
                phase="kept",
                is_loading=is_loading,
            )
            self._linked_reading = reading

            self._registry.start_reading(list_id, reading.stop)

            # while it is open, what it has is newer than what was kept
            if not is_loading:
                reading.has_copy = True
                self._read_linked_source(reading)
                return

            self._linked.run(f"kept:{reading.serial}", _merged_with_kept, media_list)
            return

    def _read_due_linked(self):
        """The linked lists whose copies are as old as the playlist lets
        them be read again while it is open, one after the other; none
        while others are, nor one a List window is open on, nor one that
        could not be read a while ago."""

        if self._linked_reading is not None or self._linked_to_read:
            return

        mode = PlaylistSettings().get("playlist/list_update")
        now = time.time()
        shown = self._lists_shown()

        self._linked_to_read = [
            (media_list.id, False)
            for media_list in self._registry.lists()
            if media_list.is_linked
            and media_list.source is not None
            and media_list.id not in shown
            and now >= self._linked_retry_at.get(media_list.id, 0)
            and is_due(media_list, True, False, mode, now)
        ]

        self._read_next_linked()

    def _lists_shown(self) -> set[UUID]:
        shown = {self._modal_list_id} - {None}

        if self._window is not None:
            shown.add(self._window.list_id)

        return shown

    def _is_linked_due(self, reading: _LinkedReading) -> bool:
        media_list = self._registry.get(reading.list_id)

        if media_list is None:
            return False

        return is_due(
            media_list,
            reading.has_copy,
            reading.is_loading,
            PlaylistSettings().get("playlist/list_update"),
            time.time(),
        )

    def _read_linked_source(self, reading: _LinkedReading):
        media_list = self._registry.get(reading.list_id)

        if media_list is None:
            self._end_linked_reading(reading)
            return

        list_id = reading.list_id
        tell = Throttled(
            lambda what, count, of=None: self._linked_progress.emit(
                list_id, what, count, of
            ),
            stop=reading.stop,
        )

        reading.phase = "source"
        self._linked.run(
            f"source:{reading.serial}",
            _merged_with_source,
            media_list,
            self._source_reader(),
            tell,
        )

    def _on_linked_read(self, name, result, error):
        _, _, serial = name.partition(":")
        reading = self._linked_reading

        # of a playlist since replaced, or stopped
        if reading is None or int(serial) != reading.serial:
            return

        if reading.stop.is_set():
            self._end_linked_reading(reading)
            return

        if error is not None:
            if isinstance(error, ReadingStopped):
                self._end_linked_reading(reading)
                return

            self._log.warning(f"Linked list not read again: {error}")

            media_list = self._registry.get(reading.list_id)
            source = None if media_list is None else media_list.source

            self._end_linked_reading(reading, read_error_of(error, source))
            return

        if result is not None:
            reading.has_copy = True

            media_list, fresh, merged, read_at = result

            # changed meanwhile, a cell learning how long an item is: told
            # apart again from the list as it is now
            now = self._registry.get(reading.list_id)

            if now is None:
                self._end_linked_reading(reading)
                return

            if now is not media_list:
                self._linked.run(name, _merged, now, fresh, read_at)
                return

            self._registry.mark_read(reading.list_id)
            self._registry.put(merged)

        if reading.phase == "kept" and self._is_linked_due(reading):
            self._read_linked_source(reading)
        else:
            self._end_linked_reading(reading)

    def _end_linked_reading(self, reading, error: ReadError | None = None):
        self._linked_reading = None

        # not asked again every minute while it says no
        if error is not None:
            self._linked_retry_at[reading.list_id] = time.time() + LINKED_RETRY_AFTER_S

        self._registry.finish_reading(reading.list_id, error)

        self._read_next_linked()

    def _on_items_added(self, list_id, keys):
        """What the viewer put on a list looked up, where the playlist says
        to: what has nothing known of it yet."""

        if not PlaylistSettings().get("playlist/list_get_info"):
            return

        media_list = self._registry.get(list_id)

        if media_list is None:
            return

        keys = set(keys)
        items = [item for item in media_list.items if item.key in keys]

        self._lookups.look_up(list_id, items, is_missing_only=True)

    def lists_to_save(self) -> list[MediaList]:
        return self._registry.kept(self._lists_in_use())

    def forget_left_lists(self):
        self._registry.forget_left(self._lists_in_use())

    def is_active_list_cell(self) -> bool:
        block = self._ctx.active_block

        return block is not None and block.media_list is not None

    def is_any_videos_list_cell(self) -> bool:
        return any(block.media_list is not None for block in self._ctx.video_blocks)

    def is_active_video_set(self) -> bool:
        """A cell to make a list of or edit the list of: one with a video,
        and not one still waiting for its list to be read."""

        block = self._ctx.active_block

        return (
            block is not None
            and block.video_params is not None
            and not self._registry.is_waiting(block.video_params.id)
        )

    def cmd_manage_list(self):
        """The List window of the active cell's list; a cell that plays one
        video is asked about first, and made to play a list if so."""

        block = self._ctx.active_block

        if block is None or block.video_params is None or self._reading_for:
            return

        if block.media_list is not None:
            self.list_window_for(block)
            return

        params = block.video_params
        folder = params.uri.parent if isinstance(params.uri, Path) else None

        choice = MakeListDialog.ask(folder, params.is_dir_recursive, self.parent())

        if choice is None:
            return

        if choice.make_from == MakeFrom.VIDEO:
            media_list = self._registry.add(
                MediaList(
                    name=params.title or params.uri_name,
                    items=(item_of_video(params),),
                )
            )

            block.navigation.take_list(media_list.id, 0)
            self.open_list_window(media_list.id, block)
            return

        self._reading_for = block
        QApplication.setOverrideCursor(Qt.BusyCursor)

        self._off_thread.run(
            "folder", folder_list, folder, scan_rules(), choice.is_recursive
        )

    def _folder_read(self, _what, folder, error):
        QApplication.restoreOverrideCursor()

        block, self._reading_for = self._reading_for, None

        # the cell gone, or on a list some other way, meanwhile
        if (
            block is None
            or block.is_closing
            or block.video_params is None
            or block.media_list is not None
        ):
            return

        if error is not None or folder is None:
            self.error.emit(
                translate("Lists", "No media files found in the folder")
                if error is None
                else translate("Lists", "Could not read the folder: {ERROR}").format(
                    ERROR=str(error)
                )
            )
            return

        params = block.video_params
        items = list(folder.items)

        index = next(
            (
                place
                for place, item in enumerate(items)
                if uri_key(item.uri) == uri_key(params.uri)
            ),
            None,
        )

        # the video not among the folder's, its kind passed over by the
        # rules: on the list in front of them all the same
        if index is None:
            items.insert(0, ListItem(uri=params.uri, is_added=True))
            index = 0

        if params.title:
            items[index] = items[index].model_copy(
                update={"title": params.title, "is_renamed": True}
            )

        media_list = self._registry.add(
            MediaList(name=folder.name, items=tuple(items), source=folder.source)
        )
        self._registry.tell_added(media_list.id, [item.key for item in items])

        block.navigation.take_list(media_list.id, index)
        self.open_list_window(media_list.id, block)

    def list_window_for(self, block):
        """The List window on a list cell's list: brought up, where it is
        open on it already."""

        if block.media_list is None or self._reading_for:
            return

        if not self.show_list_window(block):
            self.open_list_window(block.video_params.list_id, block)

    def open_list_window(self, list_id, block=None, parent=None):
        """The List window, on a cell's list, beside the player; or on one
        of the playlist's, over the window it is opened from."""

        if block is not None and not self._let_go_of_window():
            return

        dialog = MediaListDialog(
            registry=self._registry,
            list_id=list_id,
            reading=self._reading(),
            block=block,
            cells=self._cell_blocks,
            open_in_new_cell=self.open_list_in_new_cell,
            parent=parent or self.parent(),
        )

        if block is None:
            self._modal_list_id = list_id
            try:
                dialog.exec_()
            finally:
                self._modal_list_id = None
            dialog.deleteLater()
            return

        self._window = dialog
        dialog.finished.connect(lambda _result: self._list_window_closed(dialog))

        place, self._window_place = self._window_place, None
        if place is not None:
            dialog.restoreGeometry(place)

        block.navigation.set_list_window_shown(True)

        dialog.show()

    def show_list_window(self, block) -> bool:
        """The List window brought up, where it is open on the cell's list
        already: whether it was."""

        dialog = self._window

        if dialog is None or dialog.block is not block:
            return False

        params = block.video_params

        if params is None or params.list_id != dialog.list_id:
            return False

        _bring_up(dialog)

        return True

    def _let_go_of_window(self) -> bool:
        """The List window open on a cell closed for another to open: the
        changes made in it kept or undone as the viewer says, where there
        are any, and where it was kept for the next. False where the viewer
        would rather it stayed open."""

        dialog = self._window

        if dialog is None:
            return True

        is_kept = True

        if dialog.is_edited:
            is_kept = self._ask_keep_changes(dialog)

            if is_kept is None:
                _bring_up(dialog)
                return False

        self._window_place = dialog.saveGeometry()

        if is_kept:
            dialog.accept()
        else:
            dialog.reject()

        return True

    def _ask_keep_changes(self, dialog) -> bool | None:
        """Whether the changes made in the List window are kept: True to
        keep them, False to undo them, None to leave the window open."""

        media_list = self._registry.get(dialog.list_id)
        name = media_list.name if media_list is not None else None

        if name:
            question = translate(
                "Dialog - List", "Keep your changes to “{NAME}”?"
            ).format(NAME=name)
        else:
            question = translate("Dialog - List", "Keep your changes to the list?")

        box = QCustomMessageBox(
            QMessageBox.Question,
            translate("Dialog - List", "List", "Header"),
            question,
            parent=dialog,
        )
        box.setInformativeText(
            translate(
                "Dialog - List",
                "Discarding puts the list back to how it was when you opened it.",
            )
        )

        keep = box.addButton(
            translate("Dialog - List", "Keep Changes"), QMessageBox.AcceptRole
        )
        discard = box.addButton(
            translate("Dialog - List", "Discard Changes"), QMessageBox.DestructiveRole
        )
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(keep)

        box.exec_()

        clicked = box.clickedButton()

        if clicked is keep:
            return True

        if clicked is discard:
            return False

        return None

    def close_list_window(self):
        """The List window open on a cell closed, as with OK: its edits
        kept."""

        if self._window is not None:
            self._window.accept()

    def _list_window_closed(self, dialog):
        if self._window is dialog:
            self._window = None

        block = dialog.block

        if not block.is_closing:
            block.navigation.set_list_window_shown(False)

        dialog.deleteLater()

    def cmd_lists_in_playlist(self):
        # over the player and what is open beside it: the List window open
        # on a cell would be out of reach under it
        if not self._let_go_of_window():
            return

        # its windows open over it, not where that one was
        self._window_place = None

        dialog = PlaylistListsDialog(
            registry=self._registry,
            cells=self._cell_blocks,
            edit_list=lambda list_id: self.open_list_window(list_id, parent=dialog),
            open_in_new_cell=self.open_list_in_new_cell,
            parent=self.parent(),
        )

        dialog.exec_()
        dialog.deleteLater()

    def open_list_in_new_cell(self, list_id, place: int):
        """An item of a list played in a cell of its own, which goes along
        the list from there."""

        media_list = self._registry.get(list_id)

        if media_list is None or not 0 <= place < len(media_list.items):
            return

        try:
            video = Video(
                uri=media_list.items[place].uri,
                list_id=list_id,
                list_index=place,
                end_action=list_end_action(),
            )
        except ValidationError:
            self.error.emit(translate("Error", "No supported files or URLs!"))
            return

        self._ctx.commands.add_videos_to_layout([video])

    def _reading(self) -> ListReading:
        rules = scan_rules()
        max_bytes = list_read_limit()

        def expand(uris, progress=None):
            expanded = expand_inputs(uris, rules, **list_readers(progress, max_bytes))
            items = plan_cells(expanded.groups, AddMode.CELL_PER_FILE)

            return tuple(items), expanded.failed

        return ListReading(
            expand=expand,
            read_source=self._source_reader(),
            kept_source=_kept_items,
            name_filters=media_name_filters(),
            fetch_thumbnail=fetch_thumbnail,
            lookups=self._lookups,
        )

    def _source_reader(self):
        """How a list is read again from its source, off the interface
        thread: by the playlist's rules as they are now."""

        rules = scan_rules()
        max_bytes = list_read_limit()

        def read(source, progress=None):
            return read_source(source, rules, **list_readers(progress, max_bytes))

        return read

    def _cell_blocks(self) -> list:
        """The cells open, first to last in the grid."""

        return self._ctx.video_blocks.blocks_for_ids(self._ctx.commands.layout_order())

    def _lists_in_use(self) -> set[UUID]:
        return {
            block.video_params.list_id
            for block in self._ctx.video_blocks
            if block.video_params is not None and block.video_params.list_id is not None
        }


def _merged_with_kept(media_list):
    """The list with what its source had the last time it was read, kept
    in the cache; None where nothing is."""

    kept = kept_read(media_list.source)

    if kept is None:
        return None

    return _merged(media_list, kept.items, kept.at)


def _merged_with_source(media_list, read, tell):
    """What its source has now, and the list with it: off the interface
    thread, a channel list taking seconds to read and one to tell apart
    from the list."""

    return _merged(media_list, read(media_list.source, tell), int(time.time()))


def _merged(media_list, fresh, read_at):
    """The list with what was read from its source, saying when that was
    read: what was kept from before a time it was read since, as the
    playlist was saved, being older still."""

    merged = refreshed(media_list, fresh).media_list
    merged = merged.model_copy(
        update={"read_at": max(read_at, media_list.read_at or 0)}
    )

    # worked out here, for the cells finding their items on it not to wait
    # for that on the interface thread
    merged.know_places()

    return media_list, fresh, merged, read_at


def _kept_items(source):
    """What the source had the last time it was read, if that is kept."""

    kept = kept_read(source)

    return None if kept is None else kept.items


def _bring_up(dialog):
    dialog.showNormal()
    dialog.raise_()
    dialog.activateWindow()
