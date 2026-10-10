"""A list read again from where it came from, what the viewer did kept."""

from pathlib import Path

import pytest

from gridplayer.models.media_list import (
    HttpHeaders,
    ItemDetails,
    ListItem,
    ListSource,
    MediaList,
)
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.list_refresh import (
    as_added,
    in_source_order,
    refreshed,
    reloaded,
    with_removed,
    without_removed,
)

ROOT = Path("/shows/season")

SOURCE = ListSource(kind=ListSourceKind.FOLDER, location=ROOT)


def _file(name):
    return ROOT / name


def _items(*names, **fields):
    return tuple(ListItem(uri=_file(name), **fields) for name in names)


def _list(*items, removed=()):
    return MediaList(name="Season", items=tuple(items), source=SOURCE, removed=removed)


def _names(media_list):
    return [item.uri.name for item in media_list.items]


class TestReadAgain:
    def test_what_is_new_comes_in_where_it_goes(self):
        media_list = _list(*_items("01.mkv", "03.mkv"))

        result = refreshed(media_list, _items("01.mkv", "02.mkv", "03.mkv"))

        assert _names(result.media_list) == ["01.mkv", "02.mkv", "03.mkv"]
        assert result.added == 1
        assert result.gone == 0

    def test_what_is_gone_goes(self):
        media_list = _list(*_items("01.mkv", "02.mkv", "03.mkv"))

        result = refreshed(media_list, _items("01.mkv", "03.mkv"))

        assert _names(result.media_list) == ["01.mkv", "03.mkv"]
        assert result.gone == 1

    def test_the_items_staying_are_the_same_items(self):
        media_list = _list(*_items("01.mkv", "02.mkv"))

        result = refreshed(media_list, _items("01.mkv", "02.mkv", "03.mkv"))

        assert [item.key for item in result.media_list.items[:2]] == [
            item.key for item in media_list.items
        ]

    def test_names_given_stay(self):
        media_list = _list(
            ListItem(uri=_file("01.mkv"), title="Pilot", is_renamed=True)
        )

        result = refreshed(
            media_list, (ListItem(uri=_file("01.mkv"), title="Episode One"),)
        )

        assert result.media_list.items[0].title == "Pilot"

    def test_a_name_the_source_gave_is_its_name_now(self):
        media_list = _list(ListItem(uri=_file("01.mkv"), title="Pilot"))

        result = refreshed(
            media_list, (ListItem(uri=_file("01.mkv"), title="Episode One"),)
        )

        assert result.media_list.items[0].title == "Episode One"

    def test_a_name_found_out_stays_where_the_source_gives_none(self):
        media_list = _list(ListItem(uri=_file("01.mkv"), title="Pilot"))

        result = refreshed(media_list, _items("01.mkv"))

        assert result.media_list.items[0].title == "Pilot"

    def test_what_a_channel_list_says_of_it_now_is_taken(self):
        media_list = MediaList(
            items=(ListItem(uri="http://tv/1", title="One", group="Old"),),
            source=ListSource(kind=ListSourceKind.URL, location="http://tv/list.m3u"),
        )

        result = refreshed(
            media_list,
            (
                ListItem(
                    uri="http://tv/1",
                    title="Uno",
                    group="News",
                    http_headers=HttpHeaders(user_agent="UA"),
                ),
            ),
        )

        item = result.media_list.items[0]
        assert item.title == "Uno"
        assert item.group == "News"
        assert item.http_headers == HttpHeaders(user_agent="UA")

    def test_new_ones_go_at_the_end_of_a_list_put_in_order_by_hand(self):
        media_list = _list(*_items("03.mkv", "01.mkv"))

        result = refreshed(media_list, _items("01.mkv", "02.mkv", "03.mkv"))

        assert _names(result.media_list) == ["03.mkv", "01.mkv", "02.mkv"]

    def test_what_was_added_by_hand_stays_where_it_is(self):
        extra = ListItem(uri=Path("/elsewhere/extra.mkv"), is_added=True)
        media_list = _list(*_items("01.mkv"), extra, *_items("03.mkv"))

        result = refreshed(media_list, _items("01.mkv", "02.mkv", "03.mkv"))

        assert _names(result.media_list) == ["01.mkv", "extra.mkv", "02.mkv", "03.mkv"]

    def test_what_was_taken_off_by_hand_stays_off(self):
        media_list = _list(*_items("01.mkv"), removed=(_file("02.mkv"),))

        result = refreshed(media_list, _items("01.mkv", "02.mkv"))

        assert _names(result.media_list) == ["01.mkv"]
        assert result.added == 0

    def test_one_taken_off_and_gone_since_is_forgotten(self):
        media_list = _list(*_items("01.mkv"), removed=(_file("02.mkv"),))

        result = refreshed(media_list, _items("01.mkv"))

        assert result.media_list.removed == ()

    def test_one_added_by_hand_that_the_source_has_now_is_not_had_twice(self):
        media_list = _list(*_items("01.mkv"), *_items("02.mkv", is_added=True))

        result = refreshed(media_list, _items("01.mkv", "02.mkv"))

        assert _names(result.media_list) == ["01.mkv", "02.mkv"]

    def test_one_listed_twice_is_had_twice(self):
        media_list = _list(*_items("01.mkv"))

        result = refreshed(media_list, _items("01.mkv", "01.mkv"))

        assert _names(result.media_list) == ["01.mkv", "01.mkv"]

    @pytest.mark.parametrize("fresh", [(), ("01.mkv",)])
    def test_nothing_new_is_nothing_done(self, fresh):
        media_list = _list(*_items(*fresh))

        result = refreshed(media_list, _items(*fresh))

        assert result.media_list == media_list
        assert (result.added, result.gone) == (0, 0)


class TestEditedByHand:
    def test_taken_off_is_remembered(self):
        media_list = _list(*_items("01.mkv", "02.mkv"))

        edited = with_removed(media_list, media_list.items[1:])

        assert edited.removed == (_file("02.mkv"),)

    def test_but_not_what_was_added_by_hand(self):
        added = ListItem(uri=_file("x.mkv"), is_added=True)

        assert with_removed(_list(added), (added,)).removed == ()

    def test_nor_on_a_list_read_from_nowhere(self):
        media_list = MediaList(items=_items("01.mkv"))

        assert with_removed(media_list, media_list.items).removed == ()

    def test_added_is_marked_so(self):
        (item,) = as_added(_list(), _items("x.mkv"))

        assert item.is_added

    def test_but_not_on_a_list_read_from_nowhere(self):
        (item,) = as_added(MediaList(), _items("x.mkv"))

        assert not item.is_added

    def test_put_back_by_hand_is_no_longer_kept_off(self):
        media_list = _list(removed=(_file("02.mkv"), _file("03.mkv")))

        assert without_removed(media_list, _items("02.mkv")).removed == (
            _file("03.mkv"),
        )


class TestReloaded:
    """Read again with everything done to it by hand undone."""

    @pytest.fixture
    def edited(self):
        # put in another order, one renamed, one added and one taken off
        added = as_added(_list(), _items("bonus.mkv"))[0]
        return _list(
            *_items("03.mkv"),
            _items("01.mkv")[0].model_copy(update={"title": "Pilot"}),
            added,
            removed=(_file("02.mkv"),),
        )

    def test_as_the_source_has_it(self, edited):
        fresh = _items("01.mkv", "02.mkv", "03.mkv")

        media_list = reloaded(edited, fresh)

        assert _names(media_list) == ["01.mkv", "02.mkv", "03.mkv"]
        assert [item.title for item in media_list.items] == [None, None, None]
        assert not any(item.is_added for item in media_list.items)
        assert media_list.removed == ()

    def test_named_as_the_source_names_them(self, edited):
        fresh = (ListItem(uri=_file("01.mkv"), title="Episode One"),)

        media_list = reloaded(edited, fresh)

        assert [item.title for item in media_list.items] == ["Episode One"]

    def test_an_item_still_there_keeps_its_key(self, edited):
        """For a cell playing it to stay on it."""

        was = {item.uri.name: item.key for item in edited.items}

        media_list = reloaded(edited, _items("01.mkv", "02.mkv", "03.mkv"))
        keys = {item.uri.name: item.key for item in media_list.items}

        assert keys["01.mkv"] == was["01.mkv"]
        assert keys["03.mkv"] == was["03.mkv"]
        assert keys["02.mkv"] not in set(was.values())

    def test_the_same_item_twice_keys_of_its_own(self):
        media_list = _list(*_items("01.mkv", "01.mkv"))

        again = reloaded(media_list, _items("01.mkv", "01.mkv", "01.mkv"))

        keys = [item.key for item in again.items]
        assert keys[:2] == [item.key for item in media_list.items]
        assert len(set(keys)) == 3

    def test_how_long_it_was_found_to_be_kept(self):
        media_list = _list(*_items("01.mkv", duration_ms=60_000))

        assert reloaded(media_list, _items("01.mkv")).items[0].duration_ms == 60_000
        assert (
            reloaded(media_list, _items("01.mkv", duration_ms=50_000))
            .items[0]
            .duration_ms
            == 50_000
        )

    def test_its_name_and_source_kept(self, edited):
        media_list = reloaded(edited, _items("01.mkv"))

        assert media_list.name == edited.name
        assert media_list.source == edited.source
        assert media_list.id == edited.id


def _said(views, published, is_exact=False):
    return ItemDetails(
        channel="Channel",
        view_count=views,
        published=published,
        is_published_exact=is_exact,
        thumbnail="https://i.ytimg.com/vi/a/mqdefault.jpg",
    )


class TestWhatTheSiteSaysReadAgain:
    def test_the_views_as_they_are_now(self):
        (item,) = _items("01.mkv", details=_said(100, 1000))
        (fresh,) = _items("01.mkv", details=_said(250, 1000))

        result = refreshed(_list(item), [fresh]).media_list

        assert result.items[0].details.view_count == 250

    def test_a_date_known_to_the_second_stays(self):
        (item,) = _items("01.mkv", details=_said(100, 1273312425, is_exact=True))
        (fresh,) = _items("01.mkv", details=_said(250, 1286582400))

        result = refreshed(_list(item), [fresh]).media_list

        assert result.items[0].details.published == 1273312425
        assert result.items[0].details.is_published_exact
        assert result.items[0].details.view_count == 250

    def test_and_on_reloading(self):
        (item,) = _items("01.mkv", details=_said(100, 1273312425, is_exact=True))
        (fresh,) = _items("01.mkv", details=_said(250, 1286582400))

        result = reloaded(_list(item), [fresh])

        assert result.items[0].details.published == 1273312425
        assert result.items[0].details.view_count == 250

    def test_an_item_said_nothing_of_is_left_be(self):
        items = _items("01.mkv")

        result = refreshed(_list(*items), _items("01.mkv")).media_list

        assert result.items[0] is items[0]


class TestInTheSourcesOrder:
    def test_after_an_order_of_the_viewers(self):
        media_list = _list(*_items("03.mkv", "01.mkv", "02.mkv"))

        result = in_source_order(media_list, _items("01.mkv", "02.mkv", "03.mkv"))

        assert _names(result) == ["01.mkv", "02.mkv", "03.mkv"]

    def test_nothing_added_or_taken_off(self):
        media_list = _list(*_items("02.mkv", "01.mkv", "gone.mkv"))

        result = in_source_order(media_list, _items("01.mkv", "02.mkv", "new.mkv"))

        assert sorted(_names(result)) == ["01.mkv", "02.mkv", "gone.mkv"]

    def test_one_the_source_has_not_stays_after_the_one_it_follows(self):
        media_list = _list(
            *_items("mine first.mkv", is_added=True),
            *_items("03.mkv"),
            *_items("mine.mkv", is_added=True),
            *_items("01.mkv", "02.mkv"),
        )

        result = in_source_order(media_list, _items("01.mkv", "02.mkv", "03.mkv"))

        assert _names(result) == [
            "mine first.mkv",
            "01.mkv",
            "02.mkv",
            "03.mkv",
            "mine.mkv",
        ]

    def test_the_items_stay_the_items_they_were(self):
        items = _items("02.mkv", "01.mkv")

        result = in_source_order(_list(*items), _items("01.mkv", "02.mkv"))

        assert [item.key for item in result.items] == [items[1].key, items[0].key]

    def test_with_what_the_site_says_now(self):
        (item,) = _items("01.mkv", details=_said(100, 1000))

        result = in_source_order(
            _list(item), _items("01.mkv", details=_said(250, 1000))
        )

        assert result.items[0].details.view_count == 250
        assert result.items[0].key == item.key
