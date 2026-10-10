"""One cell's way along the list it plays from.

Which item comes next, which one before, and which at random, and whether
the list has been played through by then; the cell itself only puts the
item found in its place. The list is the playlist's and may change under
it, edited in this cell or another one playing from it.
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from gridplayer.models.media_list import ListItem, MediaList
from gridplayer.models.video import Video
from gridplayer.params.static import ListEndAction
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.bookmarks import file_key
from gridplayer.utils.folder_navigator import FolderStep
from gridplayer.utils.next_file import (
    MAX_MISSING_FILES,
    ShuffleBag,
    neighbour_place,
)


class ListPlace(NamedTuple):
    # where the video playing is on the list, or would be where it is not
    # on it any more: taken off, the item after it took its place
    index: int
    is_found: bool


def is_item_there(item: ListItem) -> bool:
    """Whether an item can be played as far as can be told without trying:
    a file that is gone cannot, a link may."""

    if not isinstance(item.uri, Path):
        return True

    try:
        return item.uri.is_file()
    except OSError:
        return False


def list_place(
    media_list: MediaList, video: Video, key: int | None = None
) -> ListPlace:
    """Where the video is on the list.

    The item it was put in by first, wherever that has been moved to; then
    the place it was at, if the file there is still the one; then the first
    place the file is at; then where it was, if it is on it no more.
    """

    items = media_list.items

    index = media_list.index_of_key(key)

    if index is not None and _is_same_file(items[index].uri, video.uri):
        return ListPlace(index, True)

    hint = video.list_index

    if hint is not None and 0 <= hint < len(items):
        if _is_same_file(items[hint].uri, video.uri):
            return ListPlace(hint, True)

    for index, item in enumerate(items):
        if _is_same_file(item.uri, video.uri):
            return ListPlace(index, True)

    if hint is None:
        return ListPlace(0, False)

    return ListPlace(min(max(hint, 0), len(items)), False)


def _is_same_ask(one: tuple, other: tuple) -> bool:
    """The same list's items, by the tuple itself, and the rest alike."""

    return one[0] is other[0] and one[1:] == other[1:]


def _is_same_file(one, other) -> bool:
    return file_key(one) == file_key(other)


def _neighbour(count: int, place: ListPlace, step: int) -> tuple[int, bool]:
    """The place so many on from this one, and whether that went round an
    end of the list to get there."""

    target = neighbour_place(place.index, place.is_found, step)

    return target % count, not 0 <= target < count


def list_neighbour(
    media_list: MediaList,
    place: ListPlace,
    step: int,
    exists: Callable[[ListItem], bool] = is_item_there,
) -> tuple[int | None, bool]:
    """The next item along that can be played, and whether the way to it
    went round an end of the list; None where there is none, or too many in
    a row are gone."""

    items = media_list.items

    if not items:
        return None, False

    is_round = False

    for _ in range(MAX_MISSING_FILES):
        index, is_wrapped = _neighbour(len(items), place, step)
        is_round = is_round or is_wrapped

        if exists(items[index]):
            return index, is_round

        place = ListPlace(index, True)

    return None, is_round


class ListNavigator:
    """Finds the item of the cell's list to take its video's place."""

    def __init__(
        self,
        video: Callable[[], Video | None],
        media_list: Callable[[], MediaList | None],
        item_key: Callable[[], int | None],
        switch: Callable[[int | None], None],
        end_of_list: Callable[[ListEndAction], None],
        open_elsewhere: Callable[[], Iterable],
    ):
        # the video playing now and the list it plays from, the key of the
        # item it was put in by, and what to do with the place on it of the
        # item found for it: put that item in its place, None for none
        self._video = video
        self._media_list = media_list
        self._item_key = item_key
        self._switch = switch
        # what to do instead once the list has been played through
        self._end_of_list = end_of_list
        # the files the other cells have open
        self._open_elsewhere = open_elsewhere

        # the order random items are played in
        self._shuffle_bag = ShuffleBag()

        # the place last found, and what it was found from: asked for again
        # and again by the menu and the overlay, and a video taken off a
        # long list is looked for through all of it
        self._last_place = None

    def place(self) -> ListPlace | None:
        media_list = self._media_list()
        video = self._video()

        if media_list is None or video is None:
            # the list left: its items let go of, a channel list's being
            # tens of megabytes
            self._last_place = None
            return None

        asked = (media_list.items, self._item_key(), video.uri, video.list_index)
        last = self._last_place

        if last is not None and _is_same_ask(last[0], asked):
            return last[1]

        place = list_place(media_list, video, asked[1])
        self._last_place = (asked, place)

        return place

    def step(self, step: FolderStep, is_end=False) -> None:
        media_list = self._media_list()
        video = self._video()

        if media_list is None or video is None:
            return

        place = list_place(media_list, video, self._item_key())

        if step in {FolderStep.RANDOM, FolderStep.BACK}:
            self._shuffle_step(step, media_list, place, video, is_end)
            return

        index, is_round = list_neighbour(
            media_list, place, 1 if step == FolderStep.NEXT else -1
        )

        if is_end and is_round and self._is_list_over(video):
            return

        self._switch(index)

    def _shuffle_step(self, step, media_list, place, video, is_end) -> None:
        items = media_list.items
        keys = [item.key for item in items]
        current = items[place.index].key if place.is_found else None

        self._shuffle_bag.sync(media_list.id, keys, current)

        def exists(key):
            item = media_list.item_by_key(key)
            return item is not None and is_item_there(item)

        if step == FolderStep.RANDOM:
            if is_end and self._shuffle_bag.is_round_over and self._is_list_over(video):
                return

            key = self._shuffle_bag.next(avoid=self._keys_to_avoid(), exists=exists)
        else:
            # with none played before, the one playing starts over
            key = self._shuffle_bag.previous(exists=exists) or current

        self._switch(media_list.index_of_key(key))

    def _is_list_over(self, video: Video) -> bool:
        """Whether the list being played through ends it, rather than
        going round to its start again, and if so, end it."""

        if video.list_end_action == ListEndAction.START_OVER:
            return False

        self._end_of_list(video.list_end_action)

        return True

    def _keys_to_avoid(self) -> set[int]:
        if not PlaylistSettings().get("playlist/shuffle_avoid_open"):
            return set()

        media_list = self._media_list()
        open_elsewhere = {file_key(uri) for uri in self._open_elsewhere()}

        return {
            item.key
            for item in media_list.items
            if file_key(item.uri) in open_elsewhere
        }
