"""A list of files and links for cells to play one after another.

Kept at the playlist's root rather than with a cell's video, so that several
cells can play from one: a channel list with a cell on each of four channels
is one list, not four copies of it. A cell knows which list it plays from,
and where on it it is; see Video.list_id.
"""

import itertools
import logging
import threading
import weakref
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from gridplayer.params.static import (
    LIST_STEP_END_ACTIONS,
    ListSort,
    ListSourceKind,
    ListUpdate,
    VideoEndAction,
)

# what an item is known by while the app is open: a list may have one file
# on it twice, and its items move about as it is edited
_item_keys = itertools.count(1)


def _next_item_key() -> int:
    return next(_item_keys)


def new_item_key() -> int:
    """A key for an item made without its defaults filled in for it."""

    return _next_item_key()


# where each item is on a list, by its key: a channel list runs to hundreds
# of thousands, and the cells and the menu ask where theirs is all the time.
# Kept by the items tuple, a list never being changed in place, for as long
# as a list that asked lives: lists renamed share their items, and with them
# their places. Each list that asked holds the tuple, so its id is not
# another's while the places are kept; once the last of them goes, so do
# they, a channel list's being tens of megabytes.
_key_places: dict[int, tuple[dict[int, int], set[int]]] = {}
_key_places_lock = threading.RLock()


def _key_places_of(media_list: "MediaList") -> dict[int, int]:
    items = media_list.items

    with _key_places_lock:
        kept = _key_places.get(id(items))

    if kept is None:
        kept = (_places_by_key(items), set())

    return _keep_places(media_list, kept)


def _places_by_key(items: tuple) -> dict[int, int]:
    # the first place of a key, should one be on it twice: the later ones
    # go in first, for the first to be the one left; by index, rather than
    # a pair made for each of a channel list's items
    return {items[index].key: index for index in range(len(items) - 1, -1, -1)}


def _keep_places(media_list: "MediaList", kept: tuple) -> dict[int, int]:
    """The places kept for the list's items, for as long as it lives."""

    with _key_places_lock:
        places, holders = _key_places.setdefault(id(media_list.items), kept)

        if id(media_list) in holders:
            return places

        holders.add(id(media_list))

    weakref.finalize(
        media_list, _let_go_of_places, id(media_list.items), id(media_list)
    )

    return places


def _let_go_of_places(items_id: int, holder_id: int) -> None:
    with _key_places_lock:
        kept = _key_places.get(items_id)

        if kept is None:
            return

        kept[1].discard(holder_id)

        if not kept[1]:
            del _key_places[items_id]


def as_path(uri: Any) -> Any:
    """A path read back as text, from a playlist or another player, as the
    path it is: anything but a link is one.

    Made one once it has been taken for text: before that, read from JSON
    (a cell dragged to another player), a path is not what is expected.
    """

    if isinstance(uri, str) and "://" not in uri:
        return Path(uri)

    return uri


class ItemDetails(BaseModel):
    """What a site says of a video on a list it has: who put it up, how many
    have watched it, when, and the picture it is shown by there."""

    model_config = ConfigDict(frozen=True)

    channel: str | None = None
    view_count: int | None = None

    # when it was put up, in seconds since the epoch: from the list, only
    # as near as the site says it ("3 years ago"), unless it was looked up
    # on its own, as it is to be played
    published: int | None = None
    is_published_exact: bool = False

    # a link to its picture
    thumbnail: str | None = None


def merged_details(
    known: ItemDetails | None, fresh: ItemDetails | None
) -> ItemDetails | None:
    """What a site says of a video now, over what it said before: the
    newer numbers, and what it left out now kept from before. When it was
    put up stays as known to the second, once it is, rather than as near
    as a list page says it."""

    if fresh is None or known is None:
        return known if fresh is None else fresh

    is_known_closer = known.is_published_exact and not fresh.is_published_exact

    if is_known_closer or fresh.published is None:
        published = known.published
        is_exact = known.is_published_exact
    else:
        published = fresh.published
        is_exact = fresh.is_published_exact

    return ItemDetails(
        channel=fresh.channel or known.channel,
        view_count=known.view_count if fresh.view_count is None else fresh.view_count,
        published=published,
        is_published_exact=is_exact,
        thumbnail=fresh.thumbnail or known.thumbnail,
    )


class HttpHeaders(BaseModel):
    """What a channel list says to fetch a channel with: VLC's http access
    takes these two and no more."""

    model_config = ConfigDict(frozen=True)

    user_agent: str | None = None
    referrer: str | None = None

    def as_dict(self) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent, "Referer": self.referrer}

        return {name: value for name, value in headers.items() if value}


# One of each there is, for every item fetched with the same to share: a
# channel list gives the same user agent for hundreds of thousands of
# channels. Held weakly, for those of a list gone to go with it.
_shared_headers: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def shared_http_headers(
    user_agent: str | None, referrer: str | None
) -> HttpHeaders | None:
    """The headers to fetch with, the same one for every item fetched with
    them; None for none."""

    if not user_agent and not referrer:
        return None

    pair = (user_agent, referrer)
    headers = _shared_headers.get(pair)

    if headers is None:
        headers = _shared_headers.setdefault(
            pair, HttpHeaders(user_agent=user_agent, referrer=referrer)
        )

    return headers


class ItemShape(BaseModel):
    """The shape a channel list says to show a channel in, as VLC's options
    say it: "16:9", "2.35:1"; None where it says none. Shown where the cell
    has none picked."""

    model_config = ConfigDict(frozen=True)

    aspect_ratio: str | None = None
    crop_ratio: str | None = None


# One of each, shared as the headers are: a channel list gives the same few
# to thousands of channels
_shared_shapes: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def shared_item_shape(
    aspect_ratio: str | None, crop_ratio: str | None
) -> ItemShape | None:
    """The shape to show in, the same one for every item shown in it; None
    for none."""

    if not aspect_ratio and not crop_ratio:
        return None

    pair = (aspect_ratio or None, crop_ratio or None)
    shape = _shared_shapes.get(pair)

    if shape is None:
        shape = _shared_shapes.setdefault(
            pair, ItemShape(aspect_ratio=pair[0], crop_ratio=pair[1])
        )

    return shape


class ListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    # a file that is gone stays a path, to be seen on the list and passed
    # over, and a URL stays a URL
    uri: str | Path

    # what the list calls it, its name in a playlist file or on the site,
    # or what it was renamed to; None for the file's own name
    title: str | None = None

    # how long the list says it is, None where it does not say or where it
    # never ends: a live channel
    duration_ms: int | None = None

    # the group a channel list puts it in
    group: str | None = None

    # what a channel list says to fetch it with
    http_headers: HttpHeaders | None = None

    # and to show it in
    shape: ItemShape | None = None

    # put on the list by hand, rather than read from where the list was:
    # reading it again leaves such an item be
    is_added: bool = False

    # its title given by the viewer, rather than read with it: reading
    # the list again leaves it be
    is_renamed: bool = False

    # what the site it is on says of it; None for a file, or a link the
    # site has said nothing of yet. One field rather than several: a
    # channel list has hundreds of thousands of items, and past ten fields
    # the table each one keeps them in grows from 272 bytes to 464
    details: ItemDetails | None = None

    key: int = Field(default_factory=_next_item_key, exclude=True)

    @field_validator("uri", mode="after")
    @classmethod
    def _path_as_path(cls, uri: Any) -> Any:
        return as_path(uri)

    @field_validator("http_headers", mode="after")
    @classmethod
    def _shared_http_headers(cls, headers: HttpHeaders | None) -> HttpHeaders | None:
        # read back from the playlist or the cache, each its own otherwise
        if headers is None:
            return None

        return shared_http_headers(headers.user_agent, headers.referrer)

    @field_validator("shape", mode="after")
    @classmethod
    def _shared_shape(cls, shape: ItemShape | None) -> ItemShape | None:
        if shape is None:
            return None

        return shared_item_shape(shape.aspect_ratio, shape.crop_ratio)

    @property
    def is_local_file(self) -> bool:
        return isinstance(self.uri, Path)

    @property
    def uri_name(self) -> str:
        if isinstance(self.uri, Path):
            return self.uri.name

        return self.uri


def item_of_video(video) -> ListItem:
    """A cell's video as an item of a list: what it is called, and what
    it is fetched with."""

    return ListItem(uri=video.uri, title=video.title, http_headers=video.http_headers)


class ListSource(BaseModel):
    """Where the items were read from, to read them again."""

    model_config = ConfigDict(frozen=True)

    kind: ListSourceKind
    location: str | Path
    # a folder's subfolders were read as well
    is_recursive: bool = False

    @field_validator("location", mode="after")
    @classmethod
    def _pathas_path(cls, location: Any) -> Any:
        return as_path(location)


def is_linked_by_default(source: ListSource | None) -> bool:
    """Whether a list read from there is read from it again each time the
    playlist opens: one from a link or a list file, which change where
    they are and may be long. A folder's is kept in the playlist, as it
    was found: what the viewer would expect of their own files."""

    return source is not None and source.kind != ListSourceKind.FOLDER


def list_step_action(end_action: VideoEndAction) -> VideoEndAction:
    """What a cell playing a list does at the end of each item: what it is
    set to, where that goes along the list, else on to the next."""

    if end_action in LIST_STEP_END_ACTIONS:
        return end_action

    return VideoEndAction.NEXT_FILE


def _valid_item(item: Any) -> ListItem | None:
    try:
        return ListItem.model_validate(item)
    except ValidationError as e:
        logging.getLogger("MediaList").debug(f"List item left out: {e}")
        return None


class MediaList(BaseModel):
    model_config = ConfigDict(frozen=True)

    @classmethod
    def read_from(
        cls, name: str, items: tuple[ListItem, ...], source: ListSource | None
    ) -> "MediaList":
        """A list as it was read, linked to where it was read from if a list
        read from there is."""

        return cls(
            name=name,
            items=items,
            source=source,
            is_linked=is_linked_by_default(source),
        )

    id: UUID4 = Field(default_factory=uuid4)
    name: str = ""
    items: tuple[ListItem, ...] = ()
    source: ListSource | None = None

    # what was taken off the list by hand of what its source has, for
    # reading the source again not to put it back
    removed: tuple[str | Path, ...] = ()

    # Read again from its source each time the playlist opens, rather
    # than kept in it: the playlist keeps only what the viewer did to it,
    # see list_refresh.linked_items. A channel list of hundreds of
    # thousands would be tens of megabytes of it, and out of date.
    is_linked: bool = False

    # the order it was put in by what its items are, None for one of its
    # source's or the viewer's; and that, back to front
    sort: ListSort | None = None
    is_reversed: bool = False

    # when it was last read from its source, in seconds since the epoch;
    # None where that is not known
    read_at: int | None = None

    # how often a linked one is read again, its own; None for as the
    # playlist says. CUSTOM: once what was read is update_every_s old
    update: ListUpdate | None = None
    update_every_s: int | None = None

    # and what they were called, in their groups, see
    # list_refresh.name_key: kept off as well where the source gives them
    # out with new links each time it is read
    removed_names: tuple[str, ...] = ()

    @field_validator("removed", mode="after")
    @classmethod
    def _removed_paths_as_paths(cls, removed: Any) -> Any:
        return tuple(as_path(uri) for uri in removed)

    @field_validator("items", mode="before")
    @classmethod
    def _drop_broken_items(cls, items: Any) -> Any:
        """Leave out an item that makes no sense, rather than the list.

        A playlist is a text file anybody can edit, and one entry gone wrong
        is no reason to lose the hundreds around it.
        """

        if not isinstance(items, (list, tuple)):
            return items

        kept = (
            item if isinstance(item, ListItem) else _valid_item(item) for item in items
        )

        return tuple(item for item in kept if item is not None)

    def index_of_key(self, key: int | None) -> int | None:
        if key is None:
            return None

        return _key_places_of(self).get(key)

    def know_places(self) -> None:
        """Where each item is, worked out now rather than at the first one
        looked up: off the interface thread, for a channel list."""

        _key_places_of(self)

    def with_item(self, index: int, item: ListItem) -> "MediaList":
        """The list with the item at that place in place of the one there:
        every key where it was, so the places known go with it."""

        return self.with_items({index: item})

    def with_items(self, items_at: dict[int, ListItem]) -> "MediaList":
        """The list with the items at those places in place of the ones
        there, at once: what was learned of many of them, put in as one
        change rather than one change each."""

        items = list(self.items)
        for index, item in items_at.items():
            items[index] = item

        changed = self.model_copy(update={"items": tuple(items)})

        if all(item.key == self.items[index].key for index, item in items_at.items()):
            with _key_places_lock:
                kept = _key_places.get(id(self.items))

            if kept is not None:
                _keep_places(changed, (kept[0], set()))

        return changed

    def with_fields(self, fields_by_key: dict[int, dict]) -> "MediaList":
        """The list with these fields of the items with these keys changed,
        at once; the list itself where it has none of them."""

        items_at = {}

        for key, fields in fields_by_key.items():
            index = self.index_of_key(key)

            if index is not None:
                items_at[index] = self.items[index].model_copy(update=fields)

        return self.with_items(items_at) if items_at else self

    def item_by_key(self, key: int | None) -> ListItem | None:
        index = self.index_of_key(key)

        return None if index is None else self.items[index]
