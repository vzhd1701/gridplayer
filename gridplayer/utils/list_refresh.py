"""A list read again from where it came from, with what was done to it since.

A list made from a folder, a list file or a link is a copy of what was
there then. Reading it again brings in what is new and takes off what is
gone, and leaves be what the viewer did: items added by hand stay, items
taken off by hand stay off, and the names and the order given stay.

A linked list is read again each time the playlist opens, and the
playlist keeps only what the viewer did to it, see linked_items: it has
what its source has, but for what was taken off, in its source's order
or the one it was sorted in.
"""

import threading
import weakref
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gridplayer.models.media_list import ListItem, MediaList, merged_details
from gridplayer.utils.list_order import in_order

# what an item read again may bring that the one on the list had wrong or
# not at all; and its name, unless the viewer gave it one
_REFRESHED_FIELDS = ("duration_ms", "group", "http_headers")

# what an item read again has as its source says it now, none included:
# a shape the source no longer gives is gone
_SOURCE_FIELDS = ("shape",)

# what of an item read from the source a linked list keeps in the playlist
# besides where it is: what it is told by, and what it is fetched and shown
# with to be played before the source is read. Not what changes from one reading
# to the next, its views, nor what a cell found out by playing it: the
# playlist would be changed each time it opens.
_LINKED_DROPPED = {"duration_ms": None, "details": None}

# What each linked list keeps, by the list's id, as last found. The window
# title asks whether the playlist changed twice a second, and going through
# a channel list for it took tens of milliseconds each time. Good for as
# long as the list it was found for is alive and has the same items, held
# weakly: a channel list's items are a hundred megabytes.
_kept_found: dict = {}
_kept_found_lock = threading.Lock()


@dataclass(frozen=True)
class Refreshed:
    media_list: MediaList
    added: int
    gone: int


def uri_key(uri: Path | str) -> str:
    """What an item is matched by: the same file or link is the same item."""

    if isinstance(uri, Path):
        return str(uri).casefold() if _is_case_blind() else str(uri)

    return uri


def _is_case_blind() -> bool:
    from gridplayer.params import env

    return env.IS_WINDOWS or env.IS_MACOS


def refreshed(media_list: MediaList, fresh: Sequence[ListItem]) -> Refreshed:
    """The list with what its source has now, the viewer's changes kept.

    New items go where they come in the source, among the others, while the
    list is still in the source's order; once it has been put in an order of
    the viewer's, they go at the end.

    An item is the source's by its link; or, where the link it had is gone,
    by its name in its group, the one item called that on both sides: a
    channel provider gives out new links each time, a new token in each.
    """

    removed = {uri_key(uri) for uri in media_list.removed}
    removed_names = set(media_list.removed_names)

    # the source's items, each that many times as it lists it, in its order
    fresh_keys = [uri_key(item.uri) for item in fresh]
    fresh_left = Counter(fresh_keys)
    fresh_order, fresh_by_key = _first_of_each(fresh, fresh_keys)

    # each item as the source has it by its link, or None where it has
    # not got that link
    matched = []

    for item in media_list.items:
        key = uri_key(item.uri)

        # the viewer's own stays, and is the source's one as well if it
        # has it now, for that not to come in twice
        if item.is_added:
            if fresh_left[key] > 0:
                fresh_left[key] -= 1
            matched.append(item)
        elif fresh_left[key] > 0:
            fresh_left[key] -= 1
            matched.append(_updated(item, fresh_by_key[key]))
        else:
            matched.append(None)

    # the source's items no item has the link of
    unmatched = []
    for item, key in zip(fresh, fresh_keys, strict=True):
        if fresh_left[key] > 0:
            fresh_left[key] -= 1
            unmatched.append(item)

    # and of those, the ones the items whose links are gone are called:
    # looked through only where there are such items, a channel list read
    # for a linked one bringing in hundreds of thousands
    names_gone = Counter(
        name_key(item)
        for item, match in zip(media_list.items, matched, strict=True)
        if match is None
    )
    by_name = _by_unique_name(unmatched) if names_gone else {}

    kept = []
    taken = set()
    gone = 0

    for item, match in zip(media_list.items, matched, strict=True):
        if match is not None:
            kept.append(match)
            continue

        name = name_key(item)
        fresh_item = by_name.get(name) if names_gone[name] == 1 else None

        if fresh_item is None:
            gone += 1
            continue

        taken.add(id(fresh_item))
        kept.append(
            _updated(item, fresh_item).model_copy(update={"uri": fresh_item.uri})
        )

    new_items = [
        item
        for item in unmatched
        if id(item) not in taken
        and uri_key(item.uri) not in removed
        and not (removed_names and name_key(item) in removed_names)
    ]

    items = _with_new(kept, new_items, fresh_order)

    # the ones taken off by hand that the source still has; others will not
    # be back to keep off
    removed_kept = tuple(
        uri for uri in media_list.removed if uri_key(uri) in fresh_order
    )
    names_there = (
        {name_key(item) for item in fresh} if media_list.removed_names else set()
    )
    removed_names_kept = tuple(
        name for name in media_list.removed_names if name in names_there
    )

    merged = media_list.model_copy(
        update={
            "items": tuple(items),
            "removed": removed_kept,
            "removed_names": removed_names_kept,
        }
    )

    if media_list.is_linked:
        items = _source_ordered(merged, fresh_order, fresh_by_key)
        merged = in_order(merged.model_copy(update={"items": items}))

    return Refreshed(media_list=merged, added=len(new_items), gone=gone)


def _first_of_each(fresh: Sequence[ListItem], fresh_keys=None) -> tuple[dict, dict]:
    """Where the source has each item first, and that item, by uri_key."""

    if fresh_keys is None:
        fresh_keys = [uri_key(item.uri) for item in fresh]

    fresh_order = {}
    fresh_by_key = {}

    for place, (key, item) in enumerate(zip(fresh_keys, fresh, strict=True)):
        if key not in fresh_order:
            fresh_order[key] = place
            fresh_by_key[key] = item

    return fresh_order, fresh_by_key


def linked(media_list: MediaList, fresh: Sequence[ListItem]) -> Refreshed:
    """The list read again from its source each time the playlist opens
    from now on: refreshed, and in its source's order, or the one it was
    sorted in; an order of the viewer's is undone, and what was added by
    hand taken off, a linked list having only what its source has."""

    return refreshed(
        media_list.model_copy(
            update={
                "is_linked": True,
                "items": tuple(item for item in media_list.items if not item.is_added),
            }
        ),
        fresh,
    )


def reloaded(media_list: MediaList, fresh: Sequence[ListItem]) -> MediaList:
    """The list as its source has it now, as though read from it for the
    first time: what was added and taken off by hand, the names given and
    the order it was put in all undone.

    An item still there keeps its key, for a cell playing it to stay on it,
    and how long it was found to be, where the source does not say, and
    when it was put up, where that was found out to the second.
    """

    # the items there were, by what they are, as many as there were of each
    were = defaultdict(list)
    for item in media_list.items:
        were[uri_key(item.uri)].append(item)

    items = []
    for item in fresh:
        same = were.get(uri_key(item.uri))

        if not same:
            items.append(item)
            continue

        was = same.pop(0)
        changes = {"key": was.key}
        if item.duration_ms is None and was.duration_ms is not None:
            changes["duration_ms"] = was.duration_ms
        if was.details is not None:
            changes["details"] = merged_details(was.details, item.details)

        items.append(item.model_copy(update=changes))

    return media_list.model_copy(
        update={
            "items": tuple(items),
            "removed": (),
            "removed_names": (),
            "sort": None,
            "is_reversed": False,
        }
    )


def in_source_order(media_list: MediaList, fresh: Sequence[ListItem]) -> MediaList:
    """The list put back in the order its source has its items in, after
    being put in an order of the viewer's: nothing added or taken off.

    An item the source does not have, added by hand or gone from it since,
    stays after the item it comes after now.

    A linked list stays turned back to front where it was: there that is
    a setting of its own, the source's order the other way round.
    """

    items = _source_ordered(media_list, *_first_of_each(fresh))

    if media_list.is_linked:
        return in_order(media_list.model_copy(update={"items": items, "sort": None}))

    return media_list.model_copy(
        update={"items": items, "sort": None, "is_reversed": False}
    )


def _source_ordered(
    media_list: MediaList, fresh_order: dict, fresh_by_key: dict
) -> tuple[ListItem, ...]:
    """The items in the order the source has them, each the source does
    not have after the one it comes after now: going the source's way, on
    a list turned back to front. fresh_order and fresh_by_key are where
    the source has each item first, and that item, see _first_of_each."""

    # each item of the source's, with the run of others after it; the run
    # before the first stays first. The runs by where each starts on one
    # list: a list each would be hundreds of thousands of them on a channel
    # list, for the garbage collector to go through
    items = []
    run_starts = [0]
    run_places = [-1]

    for item in _source_way(media_list):
        key = uri_key(item.uri)
        place = None if item.is_added else fresh_order.get(key)

        if place is not None:
            run_starts.append(len(items))
            run_places.append(place)
            item = _updated(item, fresh_by_key[key])

        items.append(item)

    run_ends = [*run_starts[1:], len(items)]
    ordered = sorted(range(len(run_places)), key=run_places.__getitem__)

    return tuple(
        items[at] for run in ordered for at in range(run_starts[run], run_ends[run])
    )


def _source_way(media_list: MediaList) -> tuple[ListItem, ...]:
    """The items going the way the source has them: a list turned back
    to front turned round again."""

    if media_list.is_reversed:
        return media_list.items[::-1]

    return media_list.items


def linked_items(media_list: MediaList, playing=frozenset()) -> tuple:
    """What a linked list keeps in the playlist of its items: those the
    viewer renamed, and those cells play, by uri_key in playing, for them
    to go on with as the playlist opens, before the source is read again.
    Of each, what it is told by and fetched with only.

    Nothing is added to a linked list by hand; one that has an item added
    all the same, in a playlist written by hand, has it kept whole,
    nowhere else to read it from.
    """

    playing = frozenset(playing)

    with _kept_found_lock:
        found = _kept_found.get(media_list.id)

    if found is not None:
        found_for, found_playing, kept = found
        was = found_for()

        if (
            was is not None
            and was.items is media_list.items
            and was.is_reversed == media_list.is_reversed
            and found_playing == playing
        ):
            return kept

    kept = _linked_items(media_list, playing)

    with _kept_found_lock:
        _kept_found[media_list.id] = (weakref.ref(media_list), playing, kept)

    return kept


def _linked_items(media_list: MediaList, playing: frozenset) -> tuple:
    kept = []

    for item in media_list.items:
        if item.is_added:
            kept.append(item)
        elif item.is_renamed or (playing and uri_key(item.uri) in playing):
            kept.append(item.model_copy(update=_LINKED_DROPPED))

    return tuple(kept)


def _updated(item: ListItem, fresh_item: ListItem) -> ListItem:
    changes = {
        field: getattr(fresh_item, field)
        for field in _REFRESHED_FIELDS
        if getattr(fresh_item, field) != getattr(item, field)
        and getattr(fresh_item, field) is not None
    }
    changes.update(
        {
            field: getattr(fresh_item, field)
            for field in _SOURCE_FIELDS
            if getattr(fresh_item, field) != getattr(item, field)
        }
    )

    if (
        not item.is_renamed
        and fresh_item.title is not None
        and fresh_item.title != item.title
    ):
        changes["title"] = fresh_item.title

    details = merged_details(item.details, fresh_item.details)
    if details != item.details:
        changes["details"] = details

    return item.model_copy(update=changes) if changes else item


def name_key(item: ListItem) -> str | None:
    """What an item is called and the group it is in, to tell it by where
    its link changed; None for one called nothing but its file's name."""

    if not item.title:
        return None

    return f"{item.title}\x1f{item.group or ''}"


def _by_unique_name(items) -> dict[str, ListItem]:
    """The items by name_key, of the names only one of them has."""

    counts = Counter(name_key(item) for item in items)

    return {
        name: item
        for item in items
        if (name := name_key(item)) is not None and counts[name] == 1
    }


def _with_new(kept, new_items, fresh_order) -> list[ListItem]:
    if not new_items:
        return kept

    places = [fresh_order[uri_key(item.uri)] for item in kept if not item.is_added]

    if places != sorted(places):
        return kept + new_items

    # each before the first item of the source's that comes after it there,
    # so that what was added by hand after an item stays after it: the two
    # gone through side by side, a channel list read for a linked one that
    # kept a few of its items bringing in hundreds of thousands new; put in
    # order by their places, rather than as a pair each with its place
    new_places = [fresh_order[uri_key(item.uri)] for item in new_items]
    new_order = sorted(range(len(new_items)), key=new_places.__getitem__)

    items = []
    new_at = 0

    for item in kept:
        if not item.is_added:
            place = fresh_order.get(uri_key(item.uri), -1)

            while new_at < len(new_order) and new_places[new_order[new_at]] < place:
                items.append(new_items[new_order[new_at]])
                new_at += 1

        items.append(item)

    items.extend(new_items[at] for at in new_order[new_at:])

    return items


def with_removed(media_list: MediaList, gone_items: Sequence[ListItem]) -> MediaList:
    """The list remembering the items of its source taken off by hand, for
    reading it again not to put them back."""

    if media_list.source is None:
        return media_list

    known = {uri_key(uri) for uri in media_list.removed}
    names = list(media_list.removed_names)
    known_names = set(names)

    removed = list(media_list.removed)
    for item in gone_items:
        if item.is_added:
            continue

        key = uri_key(item.uri)

        if key in known:
            continue

        known.add(key)
        removed.append(item.uri)

        name = name_key(item)
        if name is not None and name not in known_names:
            known_names.add(name)
            names.append(name)

    return media_list.model_copy(
        update={"removed": tuple(removed), "removed_names": tuple(names)}
    )


def as_added(media_list: MediaList, items: Sequence[ListItem]) -> tuple[ListItem, ...]:
    """Items put on a list by hand: on a list read from somewhere, they are
    the viewer's own, left be when it is read again."""

    if media_list.source is None:
        return tuple(items)

    return tuple(item.model_copy(update={"is_added": True}) for item in items)


def with_added(
    media_list: MediaList, items: Sequence[ListItem], place: int | None = None
) -> tuple[MediaList, tuple[ListItem, ...]]:
    """The list with items put on it by hand, at that place or after what
    it has; and the items as they are on it, the viewer's own on a list
    read from somewhere, which reading it again leaves be."""

    added = as_added(media_list, items)

    if place is None:
        place = len(media_list.items)

    items = media_list.items[:place] + added + media_list.items[place:]

    return without_removed(media_list, added).model_copy(update={"items": items}), added


def without_removed(media_list: MediaList, items: Sequence[ListItem]) -> MediaList:
    """The list no longer keeping off items put back on it by hand."""

    if not media_list.removed and not media_list.removed_names:
        return media_list

    back = {uri_key(item.uri) for item in items}
    names_back = {name_key(item) for item in items}

    return media_list.model_copy(
        update={
            "removed": tuple(
                uri for uri in media_list.removed if uri_key(uri) not in back
            ),
            "removed_names": tuple(
                name for name in media_list.removed_names if name not in names_back
            ),
        }
    )
