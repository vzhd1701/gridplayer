"""The order a list is put in by what its items are: by name, by length and
so on.

A list kept in the playlist keeps the order it was put in, whatever it was.
One read again from its source each time the playlist opens, a linked one,
starts from its source's order each time, and is put in the one it was
sorted in again; see list_refresh.
"""

import contextlib
import random
from pathlib import Path

from gridplayer.models.media_list import ListItem, MediaList
from gridplayer.params.static import ListSort, ListSourceKind
from gridplayer.utils.next_file import natural_key


def item_name(item: ListItem, base: Path | None = None) -> str:
    """What an item goes by on the list: its name, or the file's, told from
    the folder the list was read from where it is under it."""

    if item.title:
        return item.title

    if isinstance(item.uri, Path) and base is not None:
        with contextlib.suppress(ValueError):
            return str(item.uri.relative_to(base))

    return item.uri_name


def list_base(media_list: MediaList) -> Path | None:
    """The folder a list was read from, its files named from there."""

    source = media_list.source

    if source is not None and source.kind == ListSourceKind.FOLDER:
        return Path(source.location)

    return None


def view_count_of(item: ListItem) -> int | None:
    return None if item.details is None else item.details.view_count


def published_of(item: ListItem) -> int | None:
    return None if item.details is None else item.details.published


def sorted_items(items, sort: ListSort, base: Path | None = None) -> list[ListItem]:
    """The items in that order; the ones it cannot tell apart as they were."""

    items = list(items)

    def by_name(item):
        return natural_key(item_name(item, base))

    if sort == ListSort.NAME:
        items.sort(key=by_name)
    elif sort == ListSort.LENGTH:
        items.sort(key=lambda item: (item.duration_ms is None, item.duration_ms or 0))
    elif sort == ListSort.GROUP:
        items.sort(key=lambda item: (natural_key(item.group or ""), by_name(item)))
    elif sort == ListSort.VIEWS:
        # most first, what no one said last
        items.sort(key=lambda item: _sort_down(view_count_of(item)))
    elif sort == ListSort.PUBLISHED:
        # newest first
        items.sort(key=lambda item: _sort_down(published_of(item)))
    elif sort == ListSort.SHUFFLE:
        random.shuffle(items)

    return items


def in_order(media_list: MediaList) -> MediaList:
    """The list put in the order it was sorted in, and back to front where it
    was turned so: as it is, where it was in neither."""

    if media_list.sort is None and not media_list.is_reversed:
        return media_list

    items = media_list.items

    if media_list.sort is not None:
        items = sorted_items(items, media_list.sort, list_base(media_list))

    if media_list.is_reversed:
        items = items[::-1]

    return media_list.model_copy(update={"items": tuple(items)})


def _sort_down(value: int | None) -> tuple:
    """Largest first, and None after all."""

    return (value is None, -(value or 0))
