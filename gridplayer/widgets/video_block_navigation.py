"""Where a video block goes from the video it plays: along the list it
plays from, or through the folder of its file; and the list itself as the
cell plays it, its place on it and its List window.

Which list and item the cell is on is the block's to say (see
VideoBlock.media_list and VideoBlock.list_item); this is what is done with
them.
"""

from pathlib import Path

from PyQt5.QtCore import QTimer

from gridplayer.models.media_list import (
    ItemDetails,
    ListItem,
    ListSource,
    MediaList,
    list_step_action,
    merged_details,
)
from gridplayer.params.static import (
    NO_CROP_RATIO,
    OWN_ASPECT_RATIO,
    ListEndAction,
    ListSourceKind,
    VideoCrop,
    VideoEndAction,
    VideoInitialState,
)
from gridplayer.utils.bookmarks import file_key
from gridplayer.utils.folder_navigator import FolderNavigator, FolderStep
from gridplayer.utils.list_errors import ReadErrorKind
from gridplayer.utils.list_navigator import ListNavigator
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.url_resolve.static import ResolvedList
from gridplayer.utils.video_errors import ShownError, file_error
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_local_file,
    only_navigable,
)

# the place, over the video, of one taken off its list while it played
NOT_ON_LIST_TXT = "\u2013"


class NavigationControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the next, previous or a random file of the folder, to put in this
        # one's place
        self._folder_navigator = FolderNavigator(
            video=lambda: block.video_params,
            switch=self.switch_video,
            tell=block.info_change.emit,
            tell_next=self._tell_once_loaded,
            hold_end=block._hold_end_for_bookmarks,
            open_elsewhere=self._files_open_elsewhere,
        )
        # a word to say once the next file is on show, the overlay being
        # hidden while it loads
        self._notice_once_loaded: str | None = None

        # the item of its list the video was put in by, to know it by its
        # key when the list is edited: the same file may be on it more than
        # once; and by its link then, to know when its source gave it a new
        # one
        self.held_item: ListItem | None = None

        # the next, previous or a random item of the list, for a cell that
        # plays one instead of going through its folder
        self._list_navigator = ListNavigator(
            video=lambda: block.video_params,
            media_list=lambda: block.media_list,
            item_key=lambda: None if self.held_item is None else self.held_item.key,
            switch=self.play_list_item,
            end_of_list=self._end_list,
            open_elsewhere=self._uris_open_elsewhere,
        )

        # the List window is open on the cell, and plays in it
        self._is_list_window_shown = False

        # its file gone as the playlist opened, waiting for its list to be
        # read again to go on along it from there
        self.is_waiting_for_list_read = False

        # shared with other cells, the list may change in any of them
        block._ctx.lists.changed.connect(self._list_changed)
        block._ctx.lists.reading_changed.connect(self._on_list_reading)

    def close(self):
        self._folder_navigator.close()

    def place(self):
        """Where the video playing is on the cell's list, None where it
        plays none."""

        return self._list_navigator.place()

    def take_notice(self) -> str | None:
        """The word to say now that the next file is on show, once."""

        notice = self._notice_once_loaded
        self._notice_once_loaded = None

        return notice

    def set_list_end_action(self, list_end_action: ListEndAction):
        """What to do once the list has been played through. Kept for a
        cell with no list too, for when it has one."""

        self._block.video_params.list_end_action = list_end_action

    @property
    def _navigator(self) -> FolderNavigator | ListNavigator:
        """The way to the next video: along the list, for a cell that plays
        one, or through the folder of the file."""

        if self._block.media_list is not None:
            return self._list_navigator

        return self._folder_navigator

    @only_navigable
    def previous(self, is_end=False):
        # where files come at random, the one before is the one played before
        if self._block.video_params.end_action == VideoEndAction.SHUFFLE_FILE:
            self._navigator.step(FolderStep.BACK, is_end=is_end)
        else:
            self._navigator.step(FolderStep.PREVIOUS, is_end=is_end)

    @only_navigable
    def next(self, is_end=False):
        if self._block.video_params.end_action == VideoEndAction.SHUFFLE_FILE:
            self._navigator.step(FolderStep.RANDOM, is_end=is_end)
        else:
            self._navigator.step(FolderStep.NEXT, is_end=is_end)

    @only_navigable
    def shuffle(self, is_end=False):
        self._navigator.step(FolderStep.RANDOM, is_end=is_end)

    def cancel_steps(self):
        """Take no step for the end of the video still on its way: the
        viewer did something else with it meanwhile."""

        self._folder_navigator.cancel()
        self._block.recovery.stop_skip()

    def link_was_a_list(self, resolved: ResolvedList):
        """The link leads to a list of videos rather than to one: the cell
        plays the list from its first video, and an item of a list that is
        one has the list's videos take its place on it.

        After the resolver is done telling: putting a video in the cell's
        place starts the resolver over.
        """

        QTimer.singleShot(0, lambda: self._play_link_as_list(resolved))

    def _play_link_as_list(self, resolved: ResolvedList):
        if self._block._is_closing or self._block.video_params is None:
            return

        media_list = self._block.media_list
        item = self._block.list_item

        if media_list is not None and item is not None:
            index = media_list.index_of_key(item.key)

            self._block._ctx.lists.put(
                media_list.model_copy(
                    update={
                        "items": media_list.items[:index]
                        + resolved.items
                        + media_list.items[index + 1 :]
                    }
                )
            )

            self.play_list_item(index)
            return

        url = self._block.video_params.uri

        source = ListSource(kind=ListSourceKind.URL, location=url)

        new_list = self._block._ctx.lists.add(
            MediaList.read_from(
                self._block.video_params.title or resolved.title, resolved.items, source
            )
        )

        self.take_list(new_list.id, 0)
        self.play_list_item(0)

    def play_read(self, uri: Path | str) -> None:
        """Play the one file or link that what the cell waited for turned
        out to be: a link to a stream rather than a list, or a folder with
        one video in it."""

        self.switch_to(uri)

    def take_list(self, list_id, index: int):
        """Play from a list from now on, the video playing being the item
        at that place on it.

        Its name goes with it onto the list, where a cell playing a list
        keeps the names; and it goes along the list at its end, unless it is
        set to already.
        """

        params = self._block.video_params

        self.cancel_steps()

        params.list_id = list_id
        params.list_index = index
        params.title = None

        params.end_action = list_step_action(params.end_action)

        media_list = self._block.media_list
        item = None if media_list is None else media_list.items[index]
        self.held_item = item

        self._block._ctx.lists.take_up(list_id)

        # An item that is not the video yet is put in its place next: its
        # place is told then. Looked for now, the video would be looked for
        # all along the list, which a channel list makes a long look.
        if item is not None and file_key(item.uri) != file_key(params.uri):
            return

        self._show_list_state()

    def play_list_item(self, index: int | None):
        """Put an item of the cell's list in the cell, by its place on it."""

        media_list = self._block.media_list

        if media_list is None:
            return

        # none to play, every one around gone
        if index is None or not 0 <= index < len(media_list.items):
            self._block.status.last_error = ShownError(
                title=translate("Lists", "Nothing on the list to play")
            )
            self._block.error()
            return

        item = media_list.items[index]

        self.held_item = item
        self._block.video_params.list_index = index

        # the same file played again stays: its place is told here. Another
        # put in its place tells its own, once it is the video
        if file_key(item.uri) == file_key(self._block.video_params.uri):
            self.show_list_place()

        self.switch_to(item.uri)

    def show_list_window(self):
        """The List window on the cell's list, which item of it it plays
        clicked over the video."""

        if self._block.media_list is not None:
            self._block._ctx.commands.list_window_for(self._block)

    @property
    def is_list_window_shown(self) -> bool:
        return self._is_list_window_shown

    def set_list_window_shown(self, is_shown: bool):
        """The List window open on the cell, beside the player, playing what
        is picked in it here: the overlay stays up while it is, saying so
        under the title, for the cell to be found among the others; unless
        there is to be none."""

        self._is_list_window_shown = is_shown

        self._block.overlay.set_list_window_shown(is_shown)

        if is_shown:
            self._block.overlay_hide_timer.stop()

        # up as long as the window is, and gone after the usual while once
        # it is closed
        self._block.show_overlay()

    def tell_added_to_list(self, count: int):
        """Files dropped on the cell put on its list: said under its title
        for a moment, nothing else showing that they were."""

        self._block.show_overlay()
        self._block.info_change.emit(
            translate("Lists", "Added to the list: {COUNT}").format(
                COUNT=count_txt(count)
            )
        )

    def leave_list(self):
        """Play the item it is on as a video of its own from now on: Next
        goes through its folder again, as for any file.

        The name the item had on the list stays the cell's. The list stays
        for any other cell playing it, and goes when the playlist is saved
        if none does.
        """

        params = self._block.video_params

        if params is None or params.list_id is None:
            return

        item = self._block.list_item

        # and the shapes it said to show it in, as the cell's own
        self._keep_list_shape(params)

        self.cancel_steps()

        params.title = None if item is None else item.title
        params.list_id = None
        params.list_index = None
        self.held_item = None

        # and what the list said to fetch it with
        if item is not None:
            params.http_headers = item.http_headers

        self._show_list_state()

    def _keep_list_shape(self, params):
        """The aspect ratio and the crop shape the list says, where none is
        picked, picked: the picture stays as it is once off the list. Its
        own shape and no crop, picked over the list's, are nothing picked
        without it."""

        aspect_ratio = _kept_off_the_list(
            params.aspect_ratio, OWN_ASPECT_RATIO, self._block.list_aspect_ratio
        )
        crop_ratio = (
            None
            if any(params.crop)
            else _kept_off_the_list(
                params.crop_ratio, NO_CROP_RATIO, self._block.list_crop_ratio
            )
        )
        picked = {}

        if aspect_ratio is not None:
            params.aspect_ratio = aspect_ratio
            picked["aspect_ratio"] = aspect_ratio

        if crop_ratio is not None:
            params.crop_ratio = crop_ratio
            picked.update(crop=VideoCrop(0, 0, 0, 0), crop_ratio=crop_ratio)

        if self._block.video_driver is not None:
            self._block.video_driver.forget_list_ratios(**picked)

    def learn_item_length(self):
        """How long an item turned out to be, where its list did not say:
        the list says from now on, for its window to show."""

        item = self._block.list_item

        if item is None or item.duration_ms is not None or self._block.is_live:
            return

        length = self._block.video_driver.length

        if not length or length <= 0:
            return

        self._block._ctx.lists.update_item(
            self._block.video_params.list_id, item.key, duration_ms=int(length)
        )

    def learn_item_details(self, details: ItemDetails | None):
        """What the site said of the item as it was looked up to be played:
        its list says it from now on, when it was put up to the second
        rather than as near as the list page said it, and its views as
        they are now."""

        item = self._block.list_item

        if item is None or details is None:
            return

        learned = merged_details(item.details, details)

        if learned != item.details:
            self._block._ctx.lists.update_item(
                self._block.video_params.list_id, item.key, details=learned
            )

    def show_list_place(self):
        """Say over the video which item of its list the cell plays."""

        self._block.list_place_change.emit(self.list_place_txt)

    @property
    def list_place_txt(self) -> str:
        """Which item of its list the cell plays, "3/12"; empty where it
        plays no list."""

        media_list = self._block.media_list

        if media_list is None:
            return ""

        place = self._list_navigator.place()
        count = len(media_list.items)

        # the video playing taken off the list meanwhile
        if place is None or not place.is_found:
            return f"{NOT_ON_LIST_TXT}/{count}"

        return f"{place.index + 1}/{count}"

    def _end_list(self, list_end_action: ListEndAction):
        """The list has been played through, and this is what is done."""

        if list_end_action == ListEndAction.PAUSE:
            self._block._pause_at_start()
        elif list_end_action == ListEndAction.STOP:
            self._block.stop_playback()
        elif list_end_action == ListEndAction.CLOSE:
            QTimer.singleShot(0, self._block.close)

    def _list_changed(self, list_id):
        """The list edited, in this cell or another one playing from it."""

        if (
            self._block.video_params is None
            or list_id != self._block.video_params.list_id
        ):
            return

        self._follow_new_link()

        place = self._list_navigator.place()

        if place is None:
            return

        # where it is on the list now, for the playlist to say
        if place.is_found:
            self._block.video_params.list_index = place.index
            self.held_item = self._block.media_list.items[place.index]

        self._show_list_state()

    def _show_list_state(self):
        """Where the cell is on its list, and its name as the item is now
        called: renamed on the list, maybe in another cell."""

        self.show_list_place()

        if self._block._default_title is not None:
            self._block.title = self._block._custom_title or self._block._default_title

    @property
    def is_list_file_gone(self) -> bool:
        """Whether the cell plays a list and the file it is on is gone."""

        params = self._block.video_params

        if params.list_id is None or not isinstance(params.uri, Path):
            return False

        try:
            return not params.uri.is_file()
        except OSError:
            return True

    def go_on_from_gone_file(self):
        """The file the cell is on gone, its drive not plugged in: the next
        item there is on its list in its place.

        A linked list still to be read again as the playlist opens is
        waited for, having only the items cells play until then; one that
        could not be read is not gone along, and the cell says the file is
        not there.
        """

        list_id = self._block.video_params.list_id

        if self._block._ctx.lists.is_read_expected(list_id):
            self.is_waiting_for_list_read = True
            self._block._present_waiting()
            return

        if self._block._ctx.lists.is_as_saved(list_id):
            self._block._present_gone_file()
            return

        self._list_navigator.step(FolderStep.NEXT)

    def _on_list_reading(self, list_id):
        """Its list read again as the playlist opened, or not: the cell
        waiting for it goes on."""

        if (
            not self.is_waiting_for_list_read
            or self._block.video_params is None
            or list_id != self._block.video_params.list_id
            or self._block._ctx.lists.is_read_expected(list_id)
        ):
            return

        self._block._start_load()

    def _follow_new_link(self):
        """Its item read again from the source with a new link, the same
        item still: a channel provider gives out new links each time, a new
        token in each. The stream playing goes on; a reload takes the new
        link, and so does the playlist."""

        held = self.held_item

        if held is None:
            return

        item = self._block.media_list.item_by_key(held.key)

        if item is None or item.uri == held.uri:
            return

        # gone on to another video meanwhile
        if file_key(held.uri) != file_key(self._block.video_params.uri):
            return

        self._block.video_params.uri = item.uri
        self.held_item = item

    def _uris_open_elsewhere(self) -> list:
        return [
            block.video_params.uri
            for block in self._block._ctx.video_blocks
            if block is not self._block and block.video_params is not None
        ]

    @only_local_file
    def toggle_dir_recursive(self):
        self.set_dir_recursive(not self._block.video_params.is_dir_recursive)

    def set_dir_recursive(self, is_dir_recursive: bool):
        """Look for the next, previous or a random file in the subfolders as
        well, or only in the folder of the file playing.

        The subfolders are the ones under the folder of the file playing
        now, and stay so until they are left out again. Kept for a video
        stopped or still loading too, and for a URL, which has no folder
        to go through.
        """

        params = self._block.video_params

        if is_dir_recursive == params.is_dir_recursive:
            return

        self.cancel_steps()

        params.is_dir_recursive = is_dir_recursive

        if is_dir_recursive and params.is_local_file:
            params.dir_root = params.uri.parent
        else:
            params.dir_root = None

    def _tell_once_loaded(self, notice: str):
        self._notice_once_loaded = notice

    def _files_open_elsewhere(self) -> list[Path]:
        return [
            block.video_params.uri
            for block in self._block._ctx.video_blocks
            if block is not self._block
            and block.video_params is not None
            and block.video_params.is_local_file
        ]

    @only_local_file
    def switch_video(self, new_video: Path):
        # If single file in the dir and was removed, highly unlikely but still
        if new_video is None:
            self._block.status.last_error = file_error(
                ReadErrorKind.MISSING, self._block.video_params.uri
            )
            self._block.error()
            return

        self.switch_to(new_video)

    def switch_to(self, new_video: Path | str):
        """Put another file or link in the cell's place, the one after
        this one or before it, in the folder or on the list; the cell's
        settings stay as they are."""

        if new_video == self._block.video_params.uri:
            if self._block.is_video_initialized:
                self._block._seek_loop_start()
                return
            self._block._load_and_play()
            return

        self._block.bookmarker.close_manager()

        self.cancel_steps()

        self._block.loop.reset()
        self._block.video_params.current_position = 0
        self._forget_files_of_previous_video()
        # its bookmarks, if it has any, come with the file: see bookmarks
        self._block.video_params.uri = new_video
        self._block.video_params.playback_state = VideoInitialState.PLAYING
        self._block._title = None
        self._block._default_title = None

        self._block.set_video(self._block.video_params)

    def _forget_files_of_previous_video(self):
        """Leave the audio and subtitle files picked for the video that was
        here behind with it.

        They were picked for that one; files of the next one's own are found
        again where they are looked for by themselves.
        """

        self._block.audio.drop_external()
        self._block.subtitles.drop_external()


def _kept_off_the_list(picked: str, over_list: str, listed: str) -> str | None:
    """What a shape picked becomes once off the list: the list's, where
    none was picked; nothing, where the list's was picked against; None to
    stay as it is."""

    if picked == over_list:
        return ""

    if not picked and listed:
        return listed

    return None
