"""The playlist's bookmarks, kept by the file they are in.

Shared by every cell playing a file, or kept by each cell for itself, as the
playlist is set to; the cells read theirs from here and write them back here,
so that a cell gone on to another file and back, or a file closed and opened
again, finds them where they were.
"""

from pathlib import Path
from uuid import UUID

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.playlist_bookmarks import PlaylistBookmarksDialog
from gridplayer.models.file_bookmarks import FileBookmarks
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.bookmarks import file_key, in_order, merged
from gridplayer.utils.qt import translate

# how many of the files whose cells disagree a question names, before it
# says how many more there are
MERGE_FILES_LISTED = 8

Key = tuple[str, UUID | None]


def _key(entry: FileBookmarks) -> Key:
    return file_key(entry.uri), entry.cell


def _cell_ids(cells) -> set[UUID]:
    """The ids of cells given as their file and id."""

    return {cell for _uri, cell in cells}


def file_name(uri: Path | str) -> str:
    return uri.name if isinstance(uri, Path) else uri


class BookmarksRegistry(QObject):
    """Every bookmark of the playlist, by file, and by cell where each cell
    keeps its own: a file's entry without a cell is the one its cells share.

    Kept by cell, an entry without a cell is one left from when they were
    shared, for the first cell to open its file to take as its own.
    """

    changed = pyqtSignal()

    # another playlist's, or none, in place of those there were
    replaced = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._entries: dict[Key, FileBookmarks] = {}
        self._is_shared = True

        # what the cells closed meanwhile were called and coloured, to tell
        # the bookmarks they left one from another
        self._cell_looks: dict[UUID, tuple[str, str]] = {}

    @property
    def is_shared(self) -> bool:
        return self._is_shared

    def get(self, uri, cell: UUID | None) -> tuple:
        entry = self._entries.get(self._key(uri, cell))

        return () if entry is None else tuple(entry.bookmarks)

    def set(self, uri, cell: UUID | None, bookmarks) -> None:
        if self._put(self._key(uri, cell), uri, bookmarks):
            self.changed.emit()

    def add(self, uri, cell: UUID | None, bookmarks) -> None:
        """Bookmarks from elsewhere, added to those the file has here."""

        self.set(uri, cell, merged((self.get(uri, cell), bookmarks)))

    def claim(self, uri, cell: UUID) -> None:
        """A file's bookmarks left from when they were shared, for the cell
        that opens it, where each cell keeps its own."""

        if self._is_shared:
            return

        own = (file_key(uri), cell)
        left = (file_key(uri), None)

        if own in self._entries or left not in self._entries:
            return

        self._entries[own] = self._entries.pop(left).model_copy(update={"cell": cell})

        self.changed.emit()

    def entries(self) -> list[FileBookmarks]:
        return list(self._entries.values())

    def load(self, entries, cells=()) -> None:
        """Take the playlist's, in place of any there were.

        The cells are the ids of those the playlist opens. The own of a cell
        not among them -- its video left out when the playlist was read, its
        file not found -- are left for the first cell to open the file, as
        those left from sharing are, rather than lost the next time the
        playlist is saved, as a closed cell's are.
        """

        cells = set(cells)
        self._entries = {}

        for entry in entries:
            if not entry.bookmarks:
                continue

            if entry.cell is not None and entry.cell not in cells:
                entry = entry.model_copy(update={"cell": None})

            key = _key(entry)
            known = self._entries.get(key)

            if known is not None:
                entry = entry.model_copy(
                    update={"bookmarks": merged((known.bookmarks, entry.bookmarks))}
                )

            self._entries[key] = entry

        # a playlist with each cell's own read where they are shared, or one
        # edited by hand: a cell's own are found nowhere then
        if self._is_shared:
            self._share(())

        self.replaced.emit()
        self.changed.emit()

    def clear(self) -> None:
        self._entries = {}
        self._cell_looks = {}

        self.replaced.emit()
        self.changed.emit()

    def remove_entries(self, entries) -> None:
        for entry in entries:
            self._entries.pop(_key(entry), None)

        self.changed.emit()

    def put_entries(self, entries) -> None:
        """Entries as they are, in place of those of their file and cell."""

        for entry in entries:
            if entry.bookmarks:
                self._entries[_key(entry)] = entry
            else:
                self._entries.pop(_key(entry), None)

        self.changed.emit()

    def set_shared(self, is_shared: bool, cells) -> None:
        """Share the bookmarks between the cells, or give each its own.

        The cells are those open, their file and id, first to last in the
        grid. Shared, the lists of a file's cells are made one; those of
        cells closed since go with them, as they would once the playlist is
        saved. Given each its own, every cell playing a file has a copy of
        the file's list.
        """

        if is_shared == self._is_shared:
            return

        self._is_shared = is_shared

        if is_shared:
            self._entries = {
                _key(entry): entry for entry in self.kept_entries(_cell_ids(cells))
            }
            self._share(cells)
        else:
            self._split(cells)

        self.changed.emit()

    def disagreeing(self, cells) -> list[tuple[Path | str, int]]:
        """The files whose cells have lists of their own that differ, each
        with how many there are: what sharing them would merge. The cells are
        those open, as set_shared takes them; the lists of those closed since
        are not counted, being dropped."""

        lists: dict[str, list] = {}
        uris = {}

        for entry in self.kept_entries(_cell_ids(cells)):
            key, _cell = _key(entry)
            lists.setdefault(key, []).append(tuple(entry.bookmarks))
            uris.setdefault(key, entry.uri)

        return [
            (uris[key], len(file_lists))
            for key, file_lists in lists.items()
            if len(set(file_lists)) > 1
        ]

    def kept_entries(self, cells_open) -> list[FileBookmarks]:
        """The entries but those of cells no longer open: what a playlist
        saved now keeps."""

        return [
            entry
            for entry in self._entries.values()
            if entry.cell is None or entry.cell in cells_open
        ]

    def forget_cells_gone(self, cells_open) -> None:
        kept = self.kept_entries(cells_open)

        if len(kept) == len(self._entries):
            return

        self._entries = {_key(entry): entry for entry in kept}

        self.changed.emit()

    def remember_cell(self, cell: UUID, title: str, color: str) -> None:
        self._cell_looks[cell] = (title, color)

    def cell_look(self, cell: UUID) -> tuple[str, str] | None:
        return self._cell_looks.get(cell)

    def _key(self, uri, cell: UUID | None) -> Key:
        return file_key(uri), None if self._is_shared else cell

    def _put(self, key: Key, uri, bookmarks) -> bool:
        """Whether the entry changed: one with none left goes."""

        entry = self._entries.get(key)
        bookmarks = in_order(bookmarks)

        if bookmarks == ([] if entry is None else entry.bookmarks):
            return False

        if not bookmarks:
            del self._entries[key]
            return True

        # the file as it was first seen, of the ways to write it
        if entry is not None:
            uri = entry.uri

        self._entries[key] = FileBookmarks(uri=uri, cell=key[1], bookmarks=bookmarks)

        return True

    def _share(self, cells) -> None:
        """Each file's lists made one: the cells' first to last in the grid,
        then the rest, as they came."""

        order = {cell: index for index, (_uri, cell) in enumerate(cells)}
        by_file: dict[str, list[FileBookmarks]] = {}

        for (key, _cell), entry in self._entries.items():
            by_file.setdefault(key, []).append(entry)

        self._entries = {}

        for key, entries in by_file.items():
            entries.sort(key=lambda entry: order.get(entry.cell, len(order)))

            self._entries[key, None] = FileBookmarks(
                uri=entries[0].uri,
                bookmarks=merged(entry.bookmarks for entry in entries),
            )

    def _split(self, cells) -> None:
        """A copy of each file's list for every cell playing it; those of
        files no cell plays are left for the first to open them."""

        for (key, cell), entry in list(self._entries.items()):
            if cell is not None:
                continue

            playing = [cell for uri, cell in cells if file_key(uri) == key]

            if not playing:
                continue

            del self._entries[key, None]

            for each in playing:
                self._entries[key, each] = entry.model_copy(update={"cell": each})


class BookmarksManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._registry = BookmarksRegistry(parent=self)
        self._registry.set_shared(Settings().get("playlist/bookmarks_shared"), ())

        self._ctx.bookmarks = self._registry

    @property
    def commands(self):
        return {
            "bookmarks_in_playlist": self.cmd_bookmarks_in_playlist,
            "is_bookmarks_shared": lambda: self._registry.is_shared,
            "toggle_bookmarks_shared": self.cmd_toggle_bookmarks_shared,
            "confirm_bookmarks_shared": self.confirm_bookmarks_shared,
            "bookmarks_to_save": self.bookmarks_to_save,
            "forget_bookmarks_of_cells_gone": self.forget_bookmarks_of_cells_gone,
        }

    def set_bookmarks(self, entries, cells):
        self._registry.load(entries, cells)

    def clear(self):
        self._registry.clear()

    def set_bookmarks_shared(self, is_shared):
        self._registry.set_shared(is_shared, self._cells())

    def bookmarks_to_save(self) -> list[FileBookmarks]:
        return self._registry.kept_entries(self._cells_open())

    def forget_bookmarks_of_cells_gone(self):
        self._registry.forget_cells_gone(self._cells_open())

    def cmd_toggle_bookmarks_shared(self):
        is_shared = not self._registry.is_shared

        if not self.confirm_bookmarks_shared(is_shared):
            return

        PlaylistSettings().set("playlist/bookmarks_shared", is_shared)
        self.set_bookmarks_shared(is_shared)

    def confirm_bookmarks_shared(self, is_shared) -> bool:
        """Whether the viewer goes on with sharing the bookmarks, or with
        giving each cell its own, where that changes anything for them."""

        if is_shared == self._registry.is_shared or not self._registry.entries():
            return True

        if is_shared:
            return self._confirm_merge()

        return self._confirm_split()

    def cmd_bookmarks_in_playlist(self):
        dialog = PlaylistBookmarksDialog(
            registry=self._registry,
            cells=self._cell_blocks,
            open_files=self._open_files,
            parent=self.parent(),
        )

        dialog.exec_()
        dialog.deleteLater()

    def _confirm_split(self) -> bool:
        box = QCustomMessageBox(
            QMessageBox.Question,
            translate("Dialog - Bookmarks sharing", "Bookmarks", "Header"),
            "{}\n\n{}".format(
                translate(
                    "Dialog - Bookmarks sharing",
                    "Stop sharing bookmarks between cells?",
                ),
                translate(
                    "Dialog - Bookmarks sharing",
                    "Each cell gets its own copy of its file's bookmarks. From"
                    " then on, a cell's bookmarks are removed with it when it is"
                    " closed and the playlist is saved.",
                ),
            ),
            parent=self.parent(),
        )
        stop = box.addButton(
            translate("Dialog - Bookmarks sharing", "Stop Sharing"),
            QMessageBox.AcceptRole,
        )
        box.addButton(QMessageBox.Cancel)

        box.exec_()

        return box.clickedButton() is stop

    def _confirm_merge(self) -> bool:
        disagreeing = self._registry.disagreeing(self._cells())

        if not disagreeing:
            return True

        files = [
            translate("Dialog - Bookmarks sharing", "{FILE} — {COUNT} cells").format(
                FILE=file_name(uri), COUNT=count
            )
            for uri, count in disagreeing[:MERGE_FILES_LISTED]
        ]

        if len(disagreeing) > MERGE_FILES_LISTED:
            files.append(
                translate("Dialog - Bookmarks sharing", "and {COUNT} more").format(
                    COUNT=len(disagreeing) - MERGE_FILES_LISTED
                )
            )

        box = QCustomMessageBox(
            QMessageBox.Question,
            translate("Dialog - Bookmarks sharing", "Bookmarks", "Header"),
            "{}\n\n{}\n\n{}\n\n{}".format(
                translate(
                    "Dialog - Bookmarks sharing",
                    "Some files have different bookmarks in different cells:",
                ),
                "\n".join(f"    {line}" for line in files),
                translate(
                    "Dialog - Bookmarks sharing",
                    "Merge them into one list for each file? Where two are at the"
                    " same place, the name from the first cell in the grid is"
                    " kept.",
                ),
                translate(
                    "Dialog - Bookmarks sharing",
                    "Keep Separate leaves this playlist's bookmarks to each cell.",
                ),
            ),
            parent=self.parent(),
        )
        merge = box.addButton(
            translate("Dialog - Bookmarks sharing", "Merge"), QMessageBox.AcceptRole
        )
        box.addButton(
            translate("Dialog - Bookmarks sharing", "Keep Separate"),
            QMessageBox.RejectRole,
        )

        box.exec_()

        return box.clickedButton() is merge

    def _cell_blocks(self) -> list:
        """The cells open, first to last in the grid."""

        return self._ctx.video_blocks.blocks_for_ids(self._ctx.commands.layout_order())

    def _cells(self) -> list[tuple]:
        return [
            (block.video_params.uri, block.video_params.id)
            for block in self._cell_blocks()
            if block.video_params is not None
        ]

    def _cells_open(self) -> set[UUID]:
        return {
            block.video_params.id
            for block in self._ctx.video_blocks
            if block.video_params is not None
        }

    def _open_files(self, videos) -> list:
        """The videos opened in new cells: a full grid turns some away."""

        self._ctx.commands.add_videos_to_layout(videos)

        return [
            video
            for video in videos
            if self._ctx.video_blocks.by_video_id(video.id) is not None
        ]
