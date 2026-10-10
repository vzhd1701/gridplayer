"""Where each item is on a list, by its key: known for as long as a list
that asked lives, and no longer, a channel list's being tens of megabytes."""

import gc

from gridplayer.models import media_list as media_list_module
from gridplayer.models.media_list import ListItem, MediaList


def _a_list(count=5, name=""):
    return MediaList(
        name=name, items=tuple(ListItem(uri=f"http://tv/{n}") for n in range(count))
    )


def _kept_for(media_list):
    return media_list_module._key_places.get(id(media_list.items))


def test_found_by_key():
    media_list = _a_list()

    assert media_list.index_of_key(media_list.items[3].key) == 3
    assert media_list.index_of_key(-1) is None
    assert media_list.index_of_key(None) is None


def test_the_first_of_a_key_on_twice():
    item = ListItem(uri="http://tv/1")
    media_list = MediaList(items=(ListItem(uri="http://tv/0"), item, item))

    assert media_list.index_of_key(item.key) == 1


def test_let_go_of_with_the_list():
    media_list = _a_list()
    media_list.index_of_key(media_list.items[0].key)
    items_id = id(media_list.items)
    assert items_id in media_list_module._key_places

    del media_list
    gc.collect()

    assert items_id not in media_list_module._key_places


def test_shared_by_a_list_renamed_and_kept_while_either_lives():
    media_list = _a_list()
    media_list.index_of_key(media_list.items[0].key)
    renamed = media_list.model_copy(update={"name": "Renamed"})
    places = _kept_for(media_list)[0]

    renamed.index_of_key(renamed.items[0].key)
    del media_list
    gc.collect()

    assert _kept_for(renamed)[0] is places
    assert renamed.index_of_key(renamed.items[4].key) == 4


def test_an_item_changed_in_place_keeps_them():
    media_list = _a_list()
    media_list.index_of_key(media_list.items[0].key)

    item = media_list.items[2].model_copy(update={"duration_ms": 1000})
    changed = media_list.with_item(2, item)

    assert _kept_for(changed)[0] is _kept_for(media_list)[0]
    assert changed.items[2].duration_ms == 1000
    assert changed.index_of_key(item.key) == 2


def test_another_item_in_its_place_is_looked_for_again():
    media_list = _a_list()
    media_list.index_of_key(media_list.items[0].key)

    other = ListItem(uri="http://tv/other")
    changed = media_list.with_item(2, other)

    assert _kept_for(changed) is None
    assert changed.index_of_key(other.key) == 2
    assert changed.index_of_key(media_list.items[2].key) is None


def test_items_put_in_another_order_are_looked_for_again():
    media_list = _a_list()
    media_list.index_of_key(media_list.items[0].key)

    reversed_list = media_list.model_copy(
        update={"items": tuple(reversed(media_list.items))}
    )

    assert reversed_list.index_of_key(media_list.items[0].key) == 4
