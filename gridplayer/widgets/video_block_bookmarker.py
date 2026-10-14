"""The bookmarks of a video block.

The places the viewer marked to come back to, kept by the playlist with
the file they are in (see BookmarksRegistry): a cell gone on to another
file finds them again when it comes back. A jump to one is the viewer's
own seek, the same as a click on the bar, so one inside a sponsor is
played rather than skipped. A loop narrows them down to itself, as it
does the chapters. One past the end of what plays -- marked on another
cut of a stream -- is kept, but is nowhere to go.

The bookmarks themselves are the block's (VideoBlock.bookmarks); this is
what is done with them.
"""

from PyQt5.QtGui import QIcon

from gridplayer.dialogs.bookmark_rename_dialog import QBookmarkRenameDialog
from gridplayer.dialogs.bookmarks import BookmarksDialog, held_end_action_txt
from gridplayer.models.bookmark import Bookmark, bookmark_color
from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.params.static import VideoEndAction
from gridplayer.utils.bookmarks import (
    bookmark_at,
    default_bookmark_name,
    is_bookmarked,
    is_in_stretch,
    next_bookmark_index,
    next_bookmark_round,
    previous_bookmark_index,
    with_bookmark,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.time_txt import timed_title
from gridplayer.widgets.bookmark_colors import (
    bookmark_color_menu,
    bookmark_icon,
    color_picked_by_hand,
)
from gridplayer.widgets.custom_menu import CustomMenu
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_seekable,
)


class Bookmarker(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the bookmarks manager while it is open, to close with the video
        self._manager: BookmarksDialog | None = None

        # a bookmark's new name being typed, or its colour picked
        self._is_editing_one = False

    def replace(self, bookmarks):
        """Put these in place of the file's bookmarks, in order and one to a
        place; every cell they are shared with marks them too."""

        video_params = self._block.video_params

        self._block._ctx.bookmarks.set(video_params.uri, video_params.id, bookmarks)

        self._block.update_seek_marks()

    def name(self, index: int) -> str:
        return self._block.bookmarks[index].name or default_bookmark_name(index)

    def marks(self, length_ms: int) -> tuple[SeekMark, ...]:
        """The bookmarks as the bar marks them, those short of the end of a
        video this long."""

        return tuple(
            SeekMark(
                time_ms=bookmark.time_ms,
                label=bookmark.name or default_bookmark_name(index),
                kind=SeekMarkKind.BOOKMARK,
                color=bookmark.color,
            )
            for index, bookmark in enumerate(self._block.bookmarks)
            if bookmark.time_ms < length_ms
        )

    def _is_on_the_bar(self, bookmark: Bookmark) -> bool:
        if not self._block.is_video_initialized or self._block.is_live:
            return False

        return bookmark.time_ms < self._block.video_driver.length

    def is_reachable_at(self, index: int) -> bool:
        """Whether a jump to this bookmark would land inside the loop."""

        bookmarks = self._block.bookmarks

        if not 0 <= index < len(bookmarks):
            return False

        return self.is_reachable(bookmarks[index])

    def is_reachable(self, bookmark: Bookmark) -> bool:
        """Whether a jump to this bookmark would land inside the loop; for
        going through all of them, with the list read once."""

        if not self._is_on_the_bar(bookmark):
            return False

        return is_in_stretch(
            bookmark.time_ms, self._block.loop_start, self._block.loop_end
        )

    @property
    def here(self) -> int | None:
        """The bookmark the video is at, None where it is at none."""

        if not self._block.is_video_initialized or self._block.is_live:
            return None

        return bookmark_at(self._block.bookmarks, self._block.arriving_time)

    @property
    def time_to_add(self) -> int:
        """Where a bookmark added now goes: where the video is.

        A seek still on its way is where the viewer means, not where the
        stream reports it has got to so far. At the very end, the last moment
        before it: one at the end itself would be past the bar, never drawn
        and never reached.
        """

        last = max(self._block.video_driver.length - 1, 0)

        return min(max(self._block.arriving_time, 0), last)

    @property
    def is_editing(self) -> bool:
        """The bookmarks manager is open, or a bookmark's name being typed or
        its colour picked."""

        return self._manager is not None or self._is_editing_one

    @only_initialized
    @only_seekable
    def add(self):
        bookmarks = self._block.bookmarks
        time_ms = self.time_to_add

        if is_bookmarked(bookmarks, time_ms):
            self._block.info_change.emit(translate("Bookmarks", "Already bookmarked"))
            return

        self.replace(with_bookmark(bookmarks, Bookmark(time_ms=time_ms)))

        self._block.info_change.emit(translate("Bookmarks", "Bookmark added"))

    @only_initialized
    @only_seekable
    def next(self):
        bookmarks = self._block.bookmarks

        if not bookmarks:
            return False

        index = next_bookmark_index(
            bookmarks,
            self._block.arriving_time,
            self._block.loop_start,
            self._block.loop_end,
        )

        if index is None:
            self._block.info_change.emit(translate("Bookmarks", "No next bookmark"))
            return False

        self._seek(index)

        return True

    @only_initialized
    @only_seekable
    def previous(self):
        bookmarks = self._block.bookmarks

        if not bookmarks:
            return False

        index = previous_bookmark_index(
            bookmarks,
            self._block.arriving_time,
            self._block.loop_start,
            self._block.loop_end,
        )

        if index is None:
            self._block.info_change.emit(translate("Bookmarks", "No previous bookmark"))
            return False

        self._seek(index)

        return True

    @only_initialized
    @only_seekable
    def seek(self, index: int):
        if not self.is_reachable_at(index):
            return False

        self._seek(index)

        return True

    def _seek(self, index: int):
        self._block.seek(self._block.bookmarks[index].time_ms)

        self._block.info_change.emit(self.name(index))

    def _indexes(self, times) -> list[int]:
        return [
            index
            for index, bookmark in enumerate(self._block.bookmarks)
            if bookmark.time_ms in times
        ]

    def jump_to_marker(self, times):
        """Go to a bookmark of a marker clicked on, as from the menu: one
        click after another, to each of those it stands for in turn."""

        index = self.marker_to_go(times)

        if index is not None:
            self._block.manual_seek("bookmarker.seek", index)

    def marker_to_go(self, times) -> int | None:
        """Which of a marker's bookmarks a click on it goes to: the one after
        the one the video is on, round to the first after the last, of those
        in reach; None for none in reach."""

        bookmarks = self._block.bookmarks

        indexes = [
            index for index in self._indexes(times) if self.is_reachable_at(index)
        ]

        picked = next_bookmark_round(
            [bookmarks[index] for index in indexes], self._block.arriving_time
        )

        return None if picked is None else indexes[picked]

    def show_marker_menu(self, global_pos, times):
        """What can be done with the bookmarks of a marker, where it was
        right-clicked."""

        menu = self.marker_menu(times)

        if menu is None:
            return

        menu.exec_(global_pos)

        # parented to the window, which would otherwise keep every one
        menu.deleteLater()

    def marker_menu(self, times) -> CustomMenu | None:
        """The menu of a marker: Jump to, Rename, Color and Remove for its
        bookmark, or a menu of those for each where it stands for more than
        one, those being too close together to click one by one; then Manage
        Bookmarks, with its own picked out."""

        indexes = self._indexes(times)

        if not indexes or not self._block.is_video_initialized:
            return None

        menu = CustomMenu(parent=self._block.window())

        if len(indexes) == 1:
            self._add_menu_actions(menu, indexes[0])
        else:
            self._add_submenus(menu, indexes)

        menu.addSeparator()

        manage = menu.addAction(
            QIcon.fromTheme("bookmark-manage"),
            translate("Actions", "Manage Bookmarks…"),
        )
        manage.triggered.connect(self._if_unchanged(lambda: self.manage(indexes)))

        return menu

    def _if_unchanged(self, func):
        """func, for a menu to call, done only while the bookmarks are as they
        were when it was made.

        A menu stays open while the video plays on, to its end and from there
        to another file, or closed; what it was made for is gone then.
        """

        uri = self._block.video_params.uri
        bookmarks = self._block.bookmarks

        def call(_=False):
            if self._is_gone(uri, bookmarks):
                return

            func()

        return call

    def _is_gone(self, uri, bookmarks) -> bool:
        block = self._block

        return (
            block.is_closing
            or block.video_params is None
            or block.video_params.uri != uri
            or block.bookmarks != bookmarks
        )

    def _add_submenus(self, menu, indexes):
        bookmarks = self._block.bookmarks

        for index in indexes:
            submenu = CustomMenu(parent=menu)
            submenu.setTitle(
                timed_title(
                    self.name(index),
                    bookmarks[index].time_ms,
                    self._block.video_driver.length,
                )
            )
            # each in its own colour, to be told from the others by it too
            submenu.setIcon(bookmark_icon([bookmarks[index].color]))
            menu.addMenu(submenu)

            self._add_menu_actions(submenu, index)

    def _add_menu_actions(self, menu, index: int):
        jump = menu.addAction(
            QIcon.fromTheme("jump-to"), translate("Actions", "Jump to Bookmark")
        )
        # grayed out where it is out of reach, as it is in the list
        jump.setEnabled(self.is_reachable_at(index))
        jump.triggered.connect(
            self._if_unchanged(
                lambda: self._block.manual_seek("bookmarker.seek", index)
            )
        )

        menu.addSeparator()

        rename = menu.addAction(
            QIcon.fromTheme("bookmark-rename"), translate("Actions", "Rename Bookmark…")
        )
        rename.triggered.connect(self._if_unchanged(lambda: self.rename(index)))

        menu.addMenu(
            bookmark_color_menu(
                menu,
                [self._block.bookmarks[index].color],
                slot_for=lambda color: self._if_unchanged(
                    lambda: self.set_color(index, color)
                ),
                custom_slot=self._if_unchanged(lambda: self.pick_color(index)),
            )
        )

        remove = menu.addAction(
            QIcon.fromTheme("bookmark-remove"), translate("Actions", "Remove Bookmark")
        )
        remove.triggered.connect(self._if_unchanged(lambda: self.remove(index)))

    @only_initialized
    @only_seekable
    def rename(self, index: int):
        """Name a bookmark, and colour it; a name left empty takes it away."""

        uri = self._block.video_params.uri
        bookmarks = self._block.bookmarks
        bookmark = bookmarks[index]

        # the video plays on while the name is typed, held at its start
        # rather than taken away at its end (see loop_end_action)
        self._is_editing_one = True

        try:
            edits = QBookmarkRenameDialog.get_edits(
                parent=self._block.parent(),
                title=translate(
                    "Dialog - Rename bookmark", "Rename bookmark", "Header"
                ),
                name=bookmark.name or "",
                placeholder=self.name(index),
                color=bookmark.color,
            )
        finally:
            self._is_editing_one = False

        # and may still be gone at the end of it, closed from elsewhere, or
        # another file put in its place: the name goes with it then
        if edits is None or self._is_gone(uri, bookmarks):
            return

        name, color = edits

        self._edit(index, name=name.strip() or None, color=color)

    @only_initialized
    @only_seekable
    def set_color(self, index: int, color: str | None):
        """Colour a bookmark; None gives it back the bookmarks' own."""

        self._edit(index, color=color)

    @only_initialized
    @only_seekable
    def pick_color(self, index: int):
        """Colour a bookmark in one picked by hand."""

        uri = self._block.video_params.uri
        bookmarks = self._block.bookmarks

        # held as it is while it is named
        self._is_editing_one = True

        try:
            color = color_picked_by_hand(self._block.parent(), bookmarks[index].color)
        finally:
            self._is_editing_one = False

        if color is None or self._is_gone(uri, bookmarks):
            return

        self._edit(index, color=color)

    def _edit(self, index: int, **changes):
        bookmark = self._block.bookmarks[index]

        if "color" in changes:
            changes["color"] = bookmark_color(changes["color"])

        edited = bookmark.model_copy(update=changes)

        if edited == bookmark:
            return

        bookmarks = list(self._block.bookmarks)
        bookmarks[index] = edited

        self.replace(bookmarks)

    @only_initialized
    @only_seekable
    def remove(self, index: int):
        remaining = list(self._block.bookmarks)
        del remaining[index]

        self.replace(remaining)

        self._block.info_change.emit(translate("Bookmarks", "Bookmark removed"))

    @only_initialized
    @only_seekable
    def manage(self, indexes=None):
        """The bookmarks manager, the ones told picked out in it, or the one
        the video is at."""

        if indexes is None:
            here = self.here
            indexes = () if here is None else (here,)

        dialog = BookmarksDialog(
            self._block, selected=indexes, parent=self._block.parent()
        )

        self._manager = dialog
        dialog.exec_()
        self._manager = None

        dialog.deleteLater()

    def close_manager(self):
        """Close the bookmarks manager with the video it is open on: the video
        closed, or another file put in its place. What was done in it stays
        done, as it would with OK."""

        if self._manager is not None:
            self._manager.accept()

    def tell_end_held(self, end_action: VideoEndAction):
        """Say the video was paused at its start in place of the end action,
        the bookmarks being edited."""

        if self._manager is not None:
            self._manager.hold_end(end_action)
            return

        # the box the name is typed in, or the colour picked in, has no room
        # to say it: the video does
        self._block.info_change.emit(
            translate("Bookmarks", "Paused at the start instead of “{ACTION}”").format(
                ACTION=held_end_action_txt(end_action)
            )
        )
