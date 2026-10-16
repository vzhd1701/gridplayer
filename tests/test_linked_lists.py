"""Linked lists: read again from their sources each time the playlist opens,
the playlist keeping only what the viewer did to them."""

import gc
import json
import threading
import time
import weakref
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QPoint, QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QLabel, QWidget

from gridplayer.dialogs.media_list import ListReading, MediaListDialog
from gridplayer.models.media_list import (
    HttpHeaders,
    ItemDetails,
    ListItem,
    ListSource,
    MediaList,
    is_linked_by_default,
)
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.static import ListSort, ListSourceKind, ListUpdate
from gridplayer.player.managers.lists import ListsManager, MediaListsRegistry
from gridplayer.player.managers.playlist import _held_lightly, _is_same_state
from gridplayer.settings import Settings
from gridplayer.utils import list_cache
from gridplayer.utils.list_errors import ReadError, ReadErrorKind
from gridplayer.utils.list_order import in_order, sorted_items
from gridplayer.utils.list_refresh import (
    in_source_order,
    linked,
    linked_items,
    refreshed,
    reloaded,
    uri_key,
    with_removed,
    without_removed,
)
from gridplayer.utils.network import HTTPStatusError

SOURCE = ListSource(kind=ListSourceKind.URL, location="http://tv/get.php")


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _channel(number, **fields):
    return ListItem(uri=f"http://tv/{number}", title=f"Channel {number}", **fields)


def _channels(*numbers):
    return tuple(_channel(number) for number in numbers)


def _linked(*items, **fields):
    return MediaList(
        name="TV", items=tuple(items), source=SOURCE, is_linked=True, **fields
    )


def _numbers(media_list):
    return [str(item.uri).rsplit("/", 1)[1] for item in media_list.items]


def _wait_until(condition, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if condition():
            return True
    return False


class TestWhichAreLinked:
    def test_a_link_and_a_list_file_are(self):
        assert is_linked_by_default(SOURCE)
        assert is_linked_by_default(
            ListSource(kind=ListSourceKind.FILE, location="/lists/tv.m3u")
        )

    def test_a_folder_is_not(self):
        assert not is_linked_by_default(
            ListSource(kind=ListSourceKind.FOLDER, location="/shows")
        )

    def test_nor_a_list_from_nowhere(self):
        assert not is_linked_by_default(None)


class TestWhatThePlaylistKeeps:
    def test_nothing_done_to_it_is_nothing_kept(self):
        assert linked_items(_linked(*_channels(1, 2, 3))) == ()

    def test_what_was_renamed(self):
        renamed = _channel(2).model_copy(update={"title": "News", "is_renamed": True})
        media_list = _linked(_channel(1), renamed, _channel(3))

        assert [item.title for item in linked_items(media_list)] == ["News"]

    def test_what_the_cells_play(self):
        media_list = _linked(*_channels(1, 2, 3))

        kept = linked_items(media_list, {uri_key("http://tv/3")})

        assert [item.title for item in kept] == ["Channel 3"]

    def test_of_an_item_read_not_what_changes_from_reading_to_reading(self):
        item = _channel(
            1,
            duration_ms=60_000,
            http_headers=HttpHeaders(user_agent="Box/1.0"),
            details=ItemDetails(view_count=12),
            is_renamed=True,
        )

        (kept,) = linked_items(_linked(item))

        assert kept.duration_ms is None
        assert kept.details is None
        assert kept.http_headers == HttpHeaders(user_agent="Box/1.0")
        assert kept.key == item.key

    def test_an_item_added_by_hand_all_the_same_kept_whole(self):
        # in a playlist written by hand: nothing to read it from
        added = ListItem(uri="http://mine/1", duration_ms=5_000, is_added=True)

        assert linked_items(_linked(added)) == (added,)


class TestReadAgain:
    def test_what_was_kept_is_the_list_once_its_source_is_read(self):
        renamed = _channel(2).model_copy(update={"title": "News", "is_renamed": True})
        whole = _linked(_channel(1), renamed, _channel(3), _channel(4))

        kept = whole.model_copy(update={"items": linked_items(whole)})
        again = refreshed(kept, _channels(1, 2, 3, 4)).media_list

        assert _numbers(again) == ["1", "2", "3", "4"]
        assert again.items[1].title == "News"

    def test_what_was_taken_off_stays_off(self):
        kept = _linked(removed=("http://tv/2",))

        again = refreshed(kept, _channels(1, 2, 3)).media_list

        assert _numbers(again) == ["1", "3"]

    def test_in_the_sources_order_whatever_it_was_in(self):
        media_list = _linked(*_channels(3, 1, 2))

        again = refreshed(media_list, _channels(1, 2, 3, 4)).media_list

        assert _numbers(again) == ["1", "2", "3", "4"]

    def test_in_the_order_it_was_sorted_in(self):
        media_list = _linked(sort=ListSort.NAME)

        again = refreshed(
            media_list,
            (
                ListItem(uri="http://tv/1", title="Zulu"),
                ListItem(uri="http://tv/2", title="Alpha"),
            ),
        ).media_list

        assert [item.title for item in again.items] == ["Alpha", "Zulu"]

    def test_turned_round_where_it_was(self):
        media_list = _linked(is_reversed=True)

        again = refreshed(media_list, _channels(1, 2, 3)).media_list

        assert _numbers(again) == ["3", "2", "1"]

    def test_the_names_the_source_gives_now(self):
        kept = _linked(_channel(1))

        again = refreshed(kept, (ListItem(uri="http://tv/1", title="Uno"),))

        assert again.media_list.items[0].title == "Uno"

    def test_the_cells_stay_on_their_items(self):
        kept = _linked(_channel(2))

        again = refreshed(kept, _channels(1, 2, 3)).media_list

        assert again.items[1].key == kept.items[0].key

    def test_a_list_kept_whole_keeps_its_order(self):
        media_list = MediaList(items=_channels(3, 1), source=SOURCE)

        again = refreshed(media_list, _channels(1, 2, 3)).media_list

        assert _numbers(again) == ["3", "1", "2"]


class TestOrders:
    def test_sorting_by_name(self):
        items = (
            ListItem(uri="http://tv/1", title="Episode 10"),
            ListItem(uri="http://tv/2", title="Episode 9"),
        )

        assert [item.title for item in sorted_items(items, ListSort.NAME)] == [
            "Episode 9",
            "Episode 10",
        ]

    def test_by_views_most_first_none_last(self):
        items = (
            _channel(1),
            _channel(2, details=ItemDetails(view_count=5)),
            _channel(3, details=ItemDetails(view_count=50)),
        )

        assert [str(item.uri)[-1] for item in sorted_items(items, ListSort.VIEWS)] == [
            "3",
            "2",
            "1",
        ]

    def test_a_list_in_no_order_of_its_own_is_left_as_it_is(self):
        media_list = _linked(*_channels(2, 1))

        assert in_order(media_list) is media_list

    def test_the_sources_order_undoes_the_sort(self):
        media_list = MediaList(
            items=_channels(2, 1), source=SOURCE, sort=ListSort.NAME, is_reversed=True
        )

        ordered = in_source_order(media_list, _channels(1, 2))

        assert ordered.sort is None
        assert not ordered.is_reversed
        assert _numbers(ordered) == ["1", "2"]

    def test_a_linked_list_stays_turned_round(self):
        media_list = _linked(*_channels(1, 3, 2), sort=ListSort.NAME, is_reversed=True)

        ordered = in_source_order(media_list, _channels(1, 2, 3))

        assert ordered.sort is None
        assert ordered.is_reversed
        assert _numbers(ordered) == ["3", "2", "1"]

    def test_reloading_undoes_it(self):
        media_list = _linked(*_channels(2, 1), sort=ListSort.NAME)

        assert reloaded(media_list, _channels(1, 2)).sort is None


class TestLinking:
    def test_a_list_kept_whole_linked_is_in_its_sources_order(self):
        media_list = MediaList(items=_channels(3, 1, 2), source=SOURCE)

        result = linked(media_list, _channels(1, 2, 3)).media_list

        assert result.is_linked
        assert _numbers(result) == ["1", "2", "3"]

    def test_what_was_added_by_hand_is_taken_off(self):
        added = ListItem(uri="http://mine/1", is_added=True)
        media_list = MediaList(items=(_channel(1), added), source=SOURCE)

        result = linked(media_list, _channels(1, 2)).media_list

        assert _numbers(result) == ["1", "2"]
        assert not any(item.is_added for item in result.items)


def _playlist(media_list, *videos):
    return Playlist(lists=[media_list], videos=list(videos))


class TestThePlaylistFile:
    def test_a_linked_list_keeps_what_was_done_to_it_and_its_source(self):
        renamed = _channel(2).model_copy(update={"title": "News", "is_renamed": True})
        media_list = _linked(_channel(1), renamed, _channel(3))

        (data,) = json.loads(_playlist(media_list).dumps())["lists"]

        assert data["is_linked"] is True
        assert data["source"]["location"] == "http://tv/get.php"
        assert data["items"] == [
            {"uri": "http://tv/2", "title": "News", "is_renamed": True}
        ]

    def test_and_the_items_its_cells_play(self):
        media_list = _linked(*_channels(1, 2, 3))
        video = Video(uri="http://tv/3", list_id=media_list.id, list_index=2)

        (data,) = json.loads(_playlist(media_list, video).dumps())["lists"]

        assert data["items"] == [{"uri": "http://tv/3", "title": "Channel 3"}]

    def test_a_list_kept_whole_is_kept_whole(self):
        media_list = MediaList(items=_channels(1, 2), source=SOURCE)

        (data,) = json.loads(_playlist(media_list).dumps())["lists"]

        assert "is_linked" not in data
        assert len(data["items"]) == 2

    def test_its_order_is_kept(self):
        media_list = _linked(*_channels(1), sort=ListSort.VIEWS, is_reversed=True)

        (data,) = json.loads(_playlist(media_list).dumps())["lists"]

        assert data["sort"] == "views"
        assert data["is_reversed"] is True

    def test_read_back_as_it_was_kept(self):
        renamed = _channel(2).model_copy(update={"title": "News", "is_renamed": True})
        media_list = _linked(_channel(1), renamed, sort=ListSort.NAME)

        (back,) = Playlist.parse(_playlist(media_list).dumps()).lists

        assert back.is_linked
        assert back.sort == ListSort.NAME
        assert [item.title for item in back.items] == ["News"]
        assert back.items[0].is_renamed


class TestChanged:
    def _state(self, media_list, *videos):
        playlist = _playlist(media_list, *videos)
        rest = playlist.model_copy(update={"lists": None}).dumps()

        return hash(rest), tuple(playlist.lists_as_saved())

    def test_not_by_being_read_again(self):
        renamed = _channel(2).model_copy(update={"title": "News", "is_renamed": True})
        kept = _linked(renamed)

        again = refreshed(kept, _channels(1, 2, 3)).media_list

        assert _is_same_state(self._state(kept), self._state(again))

    def test_by_what_the_viewer_does_to_it(self):
        media_list = _linked(*_channels(1, 2))
        renamed = media_list.model_copy(
            update={
                "items": (
                    media_list.items[0].model_copy(
                        update={"title": "News", "is_renamed": True}
                    ),
                    media_list.items[1],
                )
            }
        )

        assert not _is_same_state(self._state(media_list), self._state(renamed))

    def test_a_list_kept_whole_by_being_another_list(self):
        media_list = MediaList(items=_channels(1, 2), source=SOURCE)
        same_items = media_list.model_copy()

        assert not _is_same_state(self._state(media_list), self._state(same_items))

    def test_one_kept_whole_and_not_changed_is_the_same(self):
        media_list = MediaList(items=_channels(1, 2), source=SOURCE)

        saved = _held_lightly(self._state(media_list))

        assert _is_same_state(self._state(media_list), saved)

    def test_one_kept_whole_and_changed_is_let_go_of(self):
        media_list = MediaList(items=_channels(1, 2), source=SOURCE)
        saved = _held_lightly(self._state(media_list))
        held = weakref.ref(media_list)

        changed = media_list.model_copy(update={"items": _channels(1)})
        del media_list
        gc.collect()

        assert held() is None
        assert not _is_same_state(self._state(changed), saved)


class TestKeptInTheCache:
    def test_what_a_link_had_is_there_next_time(self):
        list_cache.keep_read(SOURCE, _channels(1, 2))

        kept = list_cache.kept_read(SOURCE)

        assert [item.title for item in kept.items] == ["Channel 1", "Channel 2"]

    def test_and_when_it_was_read(self):
        list_cache.keep_read(SOURCE, _channels(1), at=1_700_000_000)

        assert list_cache.kept_read(SOURCE).at == 1_700_000_000

    def test_each_item_its_own_again(self):
        list_cache.keep_read(SOURCE, _channels(1, 1))

        first, second = list_cache.kept_read(SOURCE).items

        assert first.key != second.key

    def test_not_a_file_on_the_disk(self, tmp_path):
        source = ListSource(kind=ListSourceKind.FILE, location=tmp_path / "tv.m3u")

        list_cache.keep_read(source, _channels(1))

        assert list_cache.kept_read(source) is None

    def test_what_makes_no_sense_is_let_go_of(self):
        list_cache.cache.keep(list_cache.LISTS_DIR, list_cache._key(SOURCE), b"junk")

        assert list_cache.kept_read(SOURCE) is None
        assert (
            list_cache.cache.cached(list_cache.LISTS_DIR, list_cache._key(SOURCE))
            is None
        )


class TestRenamed:
    def test_a_name_given_is_told_from_one_read(self):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(1)))
        key = media_list.items[0].key

        registry.rename_item(media_list.id, key, "News")

        assert registry.get(media_list.id).items[0].is_renamed

    def test_and_its_own_back_is_none(self):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(1)))
        key = media_list.items[0].key
        registry.rename_item(media_list.id, key, "News")

        registry.rename_item(media_list.id, key, None)

        assert not registry.get(media_list.id).items[0].is_renamed


class _Source:
    """A list's source, read off the interface thread, held back until let
    go where a gate is given."""

    def __init__(self, items, gate=None):
        self.items = items
        self.gate = gate
        self.read = 0
        self.stopped = False

    def reader(self):
        def read(_source, progress=None):
            self.read += 1
            if self.gate is not None:
                while not self.gate.wait(0.01):
                    if progress is not None:
                        try:
                            progress("items", 1, None)
                        except Exception:
                            self.stopped = True
                            raise
            if isinstance(self.items, Exception):
                raise self.items
            return self.items

        return read


@pytest.fixture
def manager(monkeypatch):
    parent = QWidget()
    ctx = SimpleNamespace(
        commands=MagicMock(), active_block=None, video_blocks=MagicMock()
    )
    ctx.video_blocks.blocks_for_ids.return_value = []
    ctx.video_blocks.__iter__ = lambda _self: iter(())

    manager = ListsManager(context=ctx, parent=parent)

    yield manager

    manager.close_list_window()
    manager.cleanup()
    QApplication.processEvents()
    parent.deleteLater()


def _reading_from(manager, monkeypatch, source):
    monkeypatch.setattr(manager, "_source_reader", source.reader)


class TestReadAsThePlaylistOpens:
    def test_a_linked_list_is_read_again(self, manager, monkeypatch):
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        kept = _linked(_channel(2))

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: not registry.is_being_read(kept.id))
        assert _numbers(registry.get(kept.id)) == ["1", "2", "3"]

    def test_what_was_kept_last_time_is_there_before_it_is_read(
        self, manager, monkeypatch
    ):
        list_cache.keep_read(SOURCE, _channels(1, 2))
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2, 3), gate))
        kept = _linked()

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 2)
        assert registry.is_being_read(kept.id)

        gate.set()
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 3)

    def test_a_list_kept_whole_is_not(self, manager, monkeypatch):
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        media_list = MediaList(items=_channels(1), source=SOURCE)

        manager.set_lists([media_list])
        QTest.qWait(50)

        assert source.read == 0
        assert not manager._ctx.lists.is_being_read(media_list.id)

    def test_one_after_the_other(self, manager, monkeypatch):
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1), gate))
        first, second = _linked(), _linked()

        manager.set_lists([first, second])

        registry = manager._ctx.lists
        assert _wait_until(lambda: registry.is_being_read(first.id))
        assert not registry.is_being_read(second.id)

        gate.set()
        # (the first's source is the second's, kept by then: there before)
        assert _wait_until(
            lambda: (
                len(registry.get(second.id).items) == 1
                and not registry.is_being_read(second.id)
            )
        )

    def test_what_it_could_not_be_read_for(self, manager, monkeypatch):
        _reading_from(manager, monkeypatch, _Source(HTTPStatusError(404)))
        kept = _linked(_channel(2))

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: not registry.is_being_read(kept.id))
        error = registry.read_error(kept.id)
        assert error.kind is ReadErrorKind.HTTP
        assert error.status == 404
        assert registry.get(kept.id) is kept

    def test_each_is_waited_for_until_read(self, manager, monkeypatch):
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2, 3), gate))
        first, second = _linked(_channel(2)), _linked(_channel(3))

        manager.set_lists([first, second])

        registry = manager._ctx.lists
        assert registry.is_read_expected(first.id)
        assert registry.is_read_expected(second.id)
        assert registry.is_as_saved(second.id)

        gate.set()

        assert _wait_until(lambda: not registry.is_read_expected(second.id))
        assert not registry.is_as_saved(first.id)
        assert not registry.is_as_saved(second.id)

    def test_one_not_read_is_as_saved_still(self, manager, monkeypatch):
        _reading_from(manager, monkeypatch, _Source(HTTPStatusError(404)))
        kept = _linked(_channel(2))

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: not registry.is_read_expected(kept.id))
        assert registry.is_as_saved(kept.id)

    def test_stopped_it_leaves_the_list_be(self, manager, monkeypatch):
        gate = threading.Event()
        source = _Source(_channels(1, 2, 3), gate)
        _reading_from(manager, monkeypatch, source)
        kept = _linked(_channel(2))
        manager.set_lists([kept])
        registry = manager._ctx.lists
        # past what was kept, reading the source itself
        assert _wait_until(lambda: source.read == 1)

        registry.stop_reading(kept.id)

        assert _wait_until(lambda: source.stopped)
        assert registry.get(kept.id) is kept
        assert registry.read_error(kept.id) is None

    def test_another_playlist_lets_it_go(self, manager, monkeypatch):
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2, 3), gate))
        kept = _linked()
        manager.set_lists([kept])

        manager.set_lists([])
        gate.set()
        QTest.qWait(100)

        assert manager._ctx.lists.get(kept.id) is None

    def test_edited_meanwhile_it_is_told_apart_again(self, manager, monkeypatch):
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2, 3), gate))
        kept = _linked(_channel(2))
        manager.set_lists([kept])
        registry = manager._ctx.lists
        assert _wait_until(lambda: registry.is_being_read(kept.id))

        registry.update_item(kept.id, kept.items[0].key, duration_ms=5_000)
        gate.set()

        assert _wait_until(lambda: not registry.is_being_read(kept.id))
        again = registry.get(kept.id)
        assert _numbers(again) == ["1", "2", "3"]
        assert again.items[1].duration_ms == 5_000


class _Reading:
    def __init__(self, fresh=()):
        self.fresh = fresh

    def as_reading(self):
        return ListReading(
            expand=lambda uris, progress=None: ((), ()),
            read_source=lambda _source, progress=None: self.fresh,
        )


@pytest.fixture
def window():
    made = []

    def _make(registry, media_list, reading=None):
        dialog = MediaListDialog(
            registry=registry,
            list_id=media_list.id,
            reading=(reading or _Reading()).as_reading(),
        )
        # unlinking asks first: yes, unless a test says otherwise
        dialog._is_unlink_confirmed = lambda media_list: True
        made.append(dialog)
        return dialog

    yield _make

    for dialog in made:
        dialog.done(0)
        dialog.deleteLater()


class TestTheWindow:
    def test_says_a_list_is_linked(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))

        dialog = window(registry, media_list)

        assert not dialog._linked_tag.isHidden()

    def test_not_a_list_kept_whole(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(MediaList(items=_channels(1, 2), source=SOURCE))

        dialog = window(registry, media_list)

        assert dialog._linked_tag.isHidden()

    def test_no_rows_dragged_about_in_a_linked_one(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))

        dialog = window(registry, media_list)

        model = dialog._model
        assert not model.flags(model.index(0, 1)) & Qt.ItemIsDragEnabled

    def test_sorted_it_says_how(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(2, 1)))
        dialog = window(registry, media_list)

        dialog._sort("name")

        assert registry.get(media_list.id).sort == ListSort.NAME

    def test_turned_round_it_says_so(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(2, 1), sort=ListSort.NAME))
        dialog = window(registry, media_list)

        dialog._sort("reverse")

        changed = registry.get(media_list.id)
        assert changed.sort == ListSort.NAME
        assert changed.is_reversed

    def test_moved_by_hand_it_is_in_no_order_of_a_sort(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(
            MediaList(items=_channels(1, 2), source=SOURCE, sort=ListSort.NAME)
        )
        dialog = window(registry, media_list)

        dialog._move((media_list.items[1].key,), 0)

        assert registry.get(media_list.id).sort is None

    def test_unlinked_it_is_kept_whole(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        dialog = window(registry, media_list)

        dialog._unlink()

        assert not registry.get(media_list.id).is_linked
        assert dialog._linked_tag.isHidden()

    def test_linked_it_is_read_again(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(MediaList(items=_channels(3, 1), source=SOURCE))
        reading = _Reading(fresh=_channels(1, 2, 3))
        dialog = window(registry, media_list, reading)

        dialog._link()

        assert _wait_until(lambda: registry.get(media_list.id).is_linked)
        assert _numbers(registry.get(media_list.id)) == ["1", "2", "3"]
        assert not dialog._linked_tag.isHidden()

    def test_waits_for_it_being_read_as_the_playlist_opens(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(2)))
        stop = threading.Event()
        registry.start_reading(media_list.id, stop)

        dialog = window(registry, media_list)

        assert dialog._is_reading
        assert dialog._model._is_locked

        registry.put(media_list.model_copy(update={"items": _channels(1, 2, 3)}))
        registry.finish_reading(media_list.id)

        assert not dialog._is_reading
        assert not dialog._model._is_locked

    def test_stops_it(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(2)))
        stop = threading.Event()
        registry.start_reading(media_list.id, stop)
        dialog = window(registry, media_list)

        dialog._stop_reading()

        assert stop.is_set()
        assert not registry.is_being_read(media_list.id)
        assert not dialog._is_reading

    def test_says_what_it_could_not_be_read_for(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(2)))
        registry.start_reading(media_list.id, threading.Event())
        dialog = window(registry, media_list)

        registry.finish_reading(
            media_list.id,
            ReadError(kind=ReadErrorKind.HTTP, raw="HTTP 404", status=404),
        )

        assert not dialog._error_box.isHidden()
        assert dialog._error_title.text() == "Not found"
        assert dialog._error_tag.tag == ("Server", "HTTP 404")
        assert "HTTP 404" not in dialog._hint.text()

    def test_its_details_in_full(self, window, mocker):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(2)))
        registry.start_reading(media_list.id, threading.Event())
        dialog = window(registry, media_list)
        registry.finish_reading(
            media_list.id,
            ReadError(
                kind=ReadErrorKind.HTTP,
                raw="404 Client Error: Not Found for url",
                status=404,
                host="provider.example",
            ),
        )
        shown = []
        mocker.patch(
            "gridplayer.dialogs.media_list.ErrorDetailsDialog.exec_",
            lambda details_dialog: shown.append(details_dialog),
        )

        dialog._error_details_button.click()

        (details_dialog,) = shown
        error = details_dialog._error
        rows = dict(details_dialog._rows)
        assert error.title == "Not found"
        assert (error.where, error.code) == ("Server", "HTTP 404")
        assert rows["Code"] == "HTTP 404 Not Found"
        assert rows["Server"] == "provider.example"
        assert error.raw == "404 Client Error: Not Found for url"

    def test_edited_after_and_cancelled_it_is_as_read(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(2)))
        registry.start_reading(media_list.id, threading.Event())
        dialog = window(registry, media_list)
        read = media_list.model_copy(update={"items": _channels(1, 2, 3)})
        registry.put(read)
        registry.finish_reading(media_list.id)

        dialog._unlink()
        dialog.reject()

        assert registry.get(media_list.id) is read

    def test_cancelled_it_leaves_what_was_read_meanwhile(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(_channel(2)))
        registry.start_reading(media_list.id, threading.Event())
        dialog = window(registry, media_list)

        read = media_list.model_copy(update={"items": _channels(1, 2, 3)})
        registry.put(read)
        registry.finish_reading(media_list.id)
        dialog.reject()

        assert registry.get(media_list.id) is read


class TestKeptWhereverRead:
    M3U = b"#EXTM3U\n#EXTINF:-1,One\nhttp://tv/1\n#EXTINF:-1,Two\nhttp://tv/2\n"

    def test_added(self):
        from gridplayer.utils.media_import import expand_inputs
        from gridplayer.utils.next_file import ScanRules

        expand_inputs(["http://tv/tv.m3u"], ScanRules(), fetch=lambda _url: self.M3U)

        source = ListSource(kind=ListSourceKind.URL, location="http://tv/tv.m3u")
        assert [item.title for item in list_cache.kept_read(source).items] == [
            "One",
            "Two",
        ]

    def test_read_again(self):
        from gridplayer.utils.media_import import read_source
        from gridplayer.utils.next_file import ScanRules

        source = ListSource(kind=ListSourceKind.URL, location="http://tv/tv.m3u")

        read_source(source, ScanRules(), fetch=lambda _url: self.M3U)

        assert len(list_cache.kept_read(source).items) == 2

    def test_a_sites_list(self):
        from gridplayer.utils.media_import import ListInput, expand_inputs
        from gridplayer.utils.next_file import ScanRules

        url = "https://www.youtube.com/playlist?list=PL1"
        source = ListSource(kind=ListSourceKind.URL, location=url)

        def read_web(_url):
            return ListInput(name="Mine", items=_channels(1, 2), source=source)

        expand_inputs([url], ScanRules(), read_web=read_web)

        assert len(list_cache.kept_read(source).items) == 2


class _MenuReading(_Reading):
    def __init__(self, fresh=(), kept=None):
        super().__init__(fresh)
        self.kept = kept
        self.read = 0

    def as_reading(self):
        def read_source(_source, progress=None):
            self.read += 1
            return self.fresh

        return ListReading(
            expand=lambda uris, progress=None: ((), ()),
            read_source=read_source,
            kept_source=lambda _source: self.kept,
        )


def _sort_menu(dialog):
    dialog._fill_sort_menu()
    return {
        action.text(): action
        for action in dialog._sort_menu.actions()
        if not action.isSeparator()
    }


class TestTheSortMenu:
    def test_a_linked_list_s_says_what_it_is_in(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2), sort=ListSort.NAME))
        dialog = window(registry, media_list)

        actions = _sort_menu(dialog)

        assert actions["By Name"].isChecked()
        assert not actions["Source Order"].isChecked()
        assert not actions["Reverse"].isChecked()
        assert all(action.isCheckable() for action in actions.values())

    def test_in_its_source_s_order_that_is_checked(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2), is_reversed=True))
        dialog = window(registry, media_list)

        actions = _sort_menu(dialog)

        assert actions["Source Order"].isChecked()
        assert actions["Reverse"].isChecked()

    def test_a_list_kept_whole_s_puts_it_in_an_order_once(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(
            MediaList(items=_channels(1, 2), source=SOURCE, sort=ListSort.NAME)
        )
        dialog = window(registry, media_list)

        actions = _sort_menu(dialog)

        assert not any(action.isCheckable() for action in actions.values())

    def test_what_it_is_sorted_by_offered_whatever_its_items_say(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2), sort=ListSort.VIEWS))
        dialog = window(registry, media_list)

        assert _sort_menu(dialog)["By Views"].isChecked()

    def test_sorted_another_way_it_stays_turned_round(self, window):
        registry = MediaListsRegistry()
        items = (
            ListItem(uri="http://tv/1", title="Alpha"),
            ListItem(uri="http://tv/2", title="Zulu"),
        )
        media_list = registry.add(_linked(*items, is_reversed=True))
        dialog = window(registry, media_list)

        dialog._sort("name")

        changed = registry.get(media_list.id)
        assert changed.is_reversed
        assert [item.title for item in changed.items] == ["Zulu", "Alpha"]

    def test_sorting_a_list_kept_whole_is_what_it_says(self, window):
        registry = MediaListsRegistry()
        items = (
            ListItem(uri="http://tv/1", title="Alpha"),
            ListItem(uri="http://tv/2", title="Zulu"),
        )
        media_list = registry.add(
            MediaList(items=items[::-1], source=SOURCE, is_reversed=True)
        )
        dialog = window(registry, media_list)

        dialog._sort("name")

        assert [item.title for item in registry.get(media_list.id).items] == [
            "Alpha",
            "Zulu",
        ]

    def test_the_source_s_order_from_what_was_read_last_time(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(3, 1, 2), sort=ListSort.NAME))
        reading = _MenuReading(kept=_channels(1, 2, 3))
        dialog = window(registry, media_list, reading)

        dialog._put_in_source_order()

        assert _wait_until(lambda: registry.get(media_list.id).sort is None)
        assert _numbers(registry.get(media_list.id)) == ["1", "2", "3"]
        assert reading.read == 0

    def test_read_again_where_nothing_was_kept(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(3, 1, 2), sort=ListSort.NAME))
        reading = _MenuReading(fresh=_channels(1, 2, 3))
        dialog = window(registry, media_list, reading)

        dialog._put_in_source_order()

        assert _wait_until(lambda: registry.get(media_list.id).sort is None)
        assert reading.read == 1

    def test_a_linked_list_in_its_source_s_order_already_is_left_be(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        reading = _MenuReading(fresh=_channels(1, 2))
        dialog = window(registry, media_list, reading)

        dialog._put_in_source_order()
        QTest.qWait(50)

        assert reading.read == 0
        assert not dialog._is_reading


def _uris_mime(*uris):
    from PyQt5.QtCore import QMimeData, QUrl

    data = QMimeData()
    data.setUrls([QUrl(uri) for uri in uris])
    return data


class TestNothingAdded:
    def test_the_buttons_to_add_say_to_unlink_it(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))

        dialog = window(registry, media_list)

        for button in (
            dialog._add_files_button,
            dialog._add_folder_button,
            dialog._add_links_button,
        ):
            assert not button.isEnabled()
            assert "Unlink" in button.toolTip()

    def test_a_list_kept_whole_is_added_to(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(MediaList(items=_channels(1, 2), source=SOURCE))

        dialog = window(registry, media_list)

        assert dialog._add_files_button.isEnabled()
        assert not dialog._add_files_button.toolTip()

    def test_unlinked_it_is_added_to(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        dialog = window(registry, media_list)

        dialog._unlink()

        assert dialog._add_links_button.isEnabled()

    def test_what_is_added_another_way_is_turned_away_saying_why(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        dialog = window(registry, media_list)

        dialog._add_uris(["http://mine/1"])

        assert not dialog._is_reading
        assert registry.get(media_list.id) is media_list
        assert "Unlink" in dialog._hint.text()

    def test_nothing_dropped_in(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        dialog = window(registry, media_list)

        model = dialog._model
        assert not model.canDropMimeData(
            _uris_mime("http://mine/1"), Qt.CopyAction, -1, -1, model.index(-1, -1)
        )

    def test_but_into_a_list_kept_whole(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(MediaList(items=_channels(1, 2), source=SOURCE))
        dialog = window(registry, media_list)

        model = dialog._model
        assert model.canDropMimeData(
            _uris_mime("http://mine/1"), Qt.CopyAction, -1, -1, model.index(-1, -1)
        )

    def test_says_how_to_have_it_when_empty(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked())

        dialog = window(registry, media_list)

        assert "Refresh" in dialog._list.empty_txt[1]

    def test_dropped_in_the_middle_of_its_cell_it_is_not_added_to(self):
        from gridplayer.utils.drop_zone import DropZone, adds_to_list

        cell = SimpleNamespace(media_list=_linked(*_channels(1, 2)))

        assert not adds_to_list(cell, DropZone.CENTER, False)

    def test_but_a_list_kept_whole_is(self):
        from gridplayer.utils.drop_zone import DropZone, adds_to_list

        cell = SimpleNamespace(media_list=MediaList(items=_channels(1, 2)))

        assert adds_to_list(cell, DropZone.CENTER, False)


class TestLinkingInTheWindow:
    def test_what_was_added_by_hand_goes_once_the_viewer_says_so(
        self, window, monkeypatch
    ):
        registry = MediaListsRegistry()
        added = ListItem(uri="http://mine/1", is_added=True)
        media_list = registry.add(MediaList(items=(_channel(1), added), source=SOURCE))
        dialog = window(registry, media_list, _Reading(fresh=_channels(1, 2)))
        asked = []
        monkeypatch.setattr(
            dialog, "_is_link_confirmed", lambda count: asked.append(count) or True
        )

        dialog._link()

        assert asked == [1]
        assert _wait_until(lambda: registry.get(media_list.id).is_linked)
        assert _numbers(registry.get(media_list.id)) == ["1", "2"]

    def test_left_as_it_was_where_the_viewer_would_rather(self, window, monkeypatch):
        registry = MediaListsRegistry()
        added = ListItem(uri="http://mine/1", is_added=True)
        media_list = registry.add(MediaList(items=(_channel(1), added), source=SOURCE))
        dialog = window(registry, media_list, _Reading(fresh=_channels(1, 2)))
        monkeypatch.setattr(dialog, "_is_link_confirmed", lambda count: False)

        dialog._link()

        assert not dialog._is_reading
        assert registry.get(media_list.id) is media_list

    def test_nothing_asked_with_nothing_added(self, window, monkeypatch):
        registry = MediaListsRegistry()
        media_list = registry.add(MediaList(items=_channels(1), source=SOURCE))
        dialog = window(registry, media_list, _Reading(fresh=_channels(1, 2)))
        asked = []
        monkeypatch.setattr(
            dialog, "_is_link_confirmed", lambda count: asked.append(count) or True
        )

        dialog._link()

        assert _wait_until(lambda: registry.get(media_list.id).is_linked)
        assert asked == []


class TestUnlinking:
    def test_asked_first(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        dialog = window(registry, media_list)
        asked = []
        dialog._is_unlink_confirmed = lambda media_list: asked.append(media_list)

        dialog._unlink()

        assert asked == [media_list]
        assert registry.get(media_list.id).is_linked

    def test_by_the_cross_in_the_tag(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        dialog = window(registry, media_list)

        dialog._unlink_button.click()

        assert not registry.get(media_list.id).is_linked
        assert dialog._linked_tag.isHidden()

    def test_not_while_it_is_read_again(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))
        registry.start_reading(media_list.id, threading.Event())
        dialog = window(registry, media_list)
        dialog._reading_timer.stop()
        dialog._show_reading()

        assert not dialog._unlink_button.isEnabled()

    def test_the_cross_says_what_it_does(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1, 2)))

        dialog = window(registry, media_list)

        assert dialog._unlink_button.toolTip() == "Unlink"


class TestHowBigItMakesThePlaylist:
    def test_about_what_it_comes_to_written_out(self):
        from gridplayer.models.playlist import saved_list_bytes

        items = tuple(
            ListItem(
                uri=f"http://tv/{n}",
                title=f"Channel {n}" + "x" * (n % 40),
                group=f"Group {n % 7}",
            )
            for n in range(5_000)
        )
        media_list = _linked(*items)
        kept = media_list.model_copy(update={"is_linked": False})
        written = len(Playlist(lists=[kept]).dumps().encode("utf-8"))
        nothing = len(
            Playlist(lists=[kept.model_copy(update={"items": ()})]).dumps().encode()
        )

        estimate = saved_list_bytes(media_list)

        assert abs(estimate - (written - nothing)) < 0.05 * (written - nothing)

    def test_nothing_for_nothing(self):
        from gridplayer.models.playlist import saved_list_bytes

        assert saved_list_bytes(_linked()) == 0


class TestTheQuestion:
    def test_a_long_list_warned_of(self):
        from gridplayer.dialogs.unlink_list import BIG_LIST_BYTES, UnlinkListDialog

        dialog = UnlinkListDialog("TV", BIG_LIST_BYTES * 35)

        assert dialog.is_warned
        assert any("35.0 MB" in label.text() for label in dialog.findChildren(QLabel))
        dialog.deleteLater()

    def test_a_short_one_not(self):
        from gridplayer.dialogs.unlink_list import UnlinkListDialog

        dialog = UnlinkListDialog("TV", 20_000)

        assert not dialog.is_warned
        assert not any("MB" in label.text() for label in dialog.findChildren(QLabel))
        dialog.deleteLater()

    def test_warned_enter_does_not_unlink(self):
        from PyQt5.QtWidgets import QDialogButtonBox

        from gridplayer.dialogs.unlink_list import BIG_LIST_BYTES, UnlinkListDialog

        dialog = UnlinkListDialog("TV", BIG_LIST_BYTES * 2)
        buttons = dialog.findChild(QDialogButtonBox)

        default = next(button for button in buttons.buttons() if button.isDefault())

        assert buttons.buttonRole(default) == QDialogButtonBox.RejectRole
        dialog.deleteLater()


class TestWhenRead:
    def test_a_list_read_from_somewhere_says_when(self):
        registry = MediaListsRegistry()

        media_list = registry.add(MediaList(items=_channels(1), source=SOURCE))

        assert abs(media_list.read_at - time.time()) < 5

    def test_not_one_from_nowhere(self):
        registry = MediaListsRegistry()

        assert registry.add(MediaList(items=_channels(1))).read_at is None

    def test_read_again_as_the_playlist_opens(self, manager, monkeypatch):
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2)))
        kept = _linked(read_at=1_700_000_000)

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: not registry.is_being_read(kept.id))
        assert abs(registry.get(kept.id).read_at - time.time()) < 5

    def test_what_was_kept_says_when_it_was_read(self, manager, monkeypatch):
        list_cache.keep_read(SOURCE, _channels(1, 2), at=1_700_000_500)
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2, 3), gate))
        kept = _linked(read_at=1_700_000_000)

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 2)
        assert registry.get(kept.id).read_at == 1_700_000_500
        gate.set()

    def test_not_older_than_the_playlist_says(self, manager, monkeypatch):
        list_cache.keep_read(SOURCE, _channels(1, 2), at=1_700_000_000)
        gate = threading.Event()
        _reading_from(manager, monkeypatch, _Source(_channels(1, 2, 3), gate))
        kept = _linked(read_at=1_700_000_500)

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 2)
        assert registry.get(kept.id).read_at == 1_700_000_500
        gate.set()

    def test_refreshed_in_the_window(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1), read_at=1_700_000_000))
        dialog = window(registry, media_list, _Reading(fresh=_channels(1, 2)))

        dialog._refresh()

        assert _wait_until(lambda: len(registry.get(media_list.id).items) == 2)
        assert abs(registry.get(media_list.id).read_at - time.time()) < 5

    def test_put_in_order_from_what_was_kept_it_was_not_read(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(
            _linked(*_channels(2, 1), sort=ListSort.NAME, read_at=1_700_000_000)
        )
        dialog = window(registry, media_list, _MenuReading(kept=_channels(1, 2)))

        dialog._put_in_source_order()

        assert _wait_until(lambda: registry.get(media_list.id).sort is None)
        assert registry.get(media_list.id).read_at == 1_700_000_000

    def test_kept_in_the_playlist(self):
        media_list = MediaList(items=_channels(1), source=SOURCE, read_at=1_700_000_000)

        (data,) = json.loads(_playlist(media_list).dumps())["lists"]

        assert data["read_at"] == 1_700_000_000

    def test_read_at_another_time_is_no_change_of_the_playlist(self):
        media_list = _linked(_channel(1), read_at=1_700_000_000)
        read_again = media_list.model_copy(update={"read_at": 1_700_009_000})

        assert _is_same_state(
            TestChanged()._state(media_list), TestChanged()._state(read_again)
        )


class TestSaidInTheWindow:
    def test_just_now(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1), read_at=int(time.time())))

        dialog = window(registry, media_list)

        assert dialog._updated_button.texts[0] == "Updated just now"

    def test_how_long_ago(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(
            _linked(*_channels(1), read_at=int(time.time()) - 3 * 86_400)
        )

        dialog = window(registry, media_list)

        assert dialog._updated_button.texts == ("Updated 3 days ago", "3 days ago")
        assert dialog._updated_button.toolTip().startswith("Last updated: ")

    def test_nothing_where_not_known(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        registry.put(registry.get(media_list.id).model_copy(update={"read_at": None}))

        dialog = window(registry, media_list)

        # how often it is read can still be picked
        assert dialog._updated_button.texts == ("Update",)

    def test_said_again_once_read_again(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(
            _linked(*_channels(1), read_at=int(time.time()) - 3 * 86_400)
        )
        dialog = window(registry, media_list)

        registry.put(
            registry.get(media_list.id).model_copy(update={"read_at": int(time.time())})
        )

        assert dialog._updated_button.texts[0] == "Updated just now"


class TestTheTagsCross:
    def test_as_tall_as_the_tag_has_room_for_and_as_wide(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)
        dialog.show()
        QTest.qWait(20)

        button = dialog._unlink_button
        room = dialog._linked_tag.contentsRect().height()

        assert button.height() == room - 2
        assert button.width() == button.height()

    def test_its_sign_in_the_very_middle(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)
        dialog.show()
        QTest.qWait(20)

        button = dialog._unlink_button

        assert (button.height() - button.iconSize().height()) % 2 == 0


class TestFittedButton:
    def _label(self, width, *texts):
        from gridplayer.dialogs.media_list import FittedButton

        label = FittedButton()
        label.set_texts(*texts)
        label.resize(width, 20)
        return label

    def test_the_longest_there_is_room_for(self):
        label = self._label(1000, "Updated 4 days ago", "4 days ago")

        assert label.shown_text() == "Updated 4 days ago"

    def test_a_shorter_one_where_not(self):
        label = self._label(10, "Updated 4 days ago", "4 days ago")
        label.resize(label.fontMetrics().horizontalAdvance("4 days ago") + 10, 20)

        assert label.shown_text() == "4 days ago"

    def test_none_rather_than_one_cut_short(self):
        label = self._label(10, "Updated 4 days ago", "4 days ago")

        assert label.shown_text() == ""


NOW = 1_800_000_000
HOUR = 3600


class TestWhenDue:
    def _due(self, mode, read_ago=None, has_copy=True, is_loading=True, source=SOURCE):
        from gridplayer.player.managers.lists import is_due

        media_list = MediaList(
            source=source,
            is_linked=True,
            read_at=None if read_ago is None else NOW - read_ago,
        )

        return is_due(media_list, has_copy, is_loading, mode, NOW)

    def test_on_load_each_time_it_is_loaded(self):
        assert self._due(ListUpdate.ON_LOAD, read_ago=60)

    def test_on_load_not_while_it_is_open(self):
        assert not self._due(
            ListUpdate.ON_LOAD, read_ago=7 * 24 * HOUR, is_loading=False
        )

    def test_every_hour_not_before_it_is_an_hour_old(self):
        assert not self._due(ListUpdate.HOURLY, read_ago=HOUR - 1)
        assert self._due(ListUpdate.HOURLY, read_ago=HOUR)

    def test_as_it_is_loaded_and_while_it_is_open(self):
        assert self._due(ListUpdate.SIX_HOURS, read_ago=6 * HOUR, is_loading=False)
        assert not self._due(ListUpdate.DAILY, read_ago=6 * HOUR, is_loading=False)

    def test_when_it_was_read_not_known(self):
        assert self._due(ListUpdate.DAILY)

    def test_manually_never(self):
        assert not self._due(ListUpdate.MANUAL, read_ago=365 * 24 * HOUR)
        assert not self._due(ListUpdate.MANUAL, is_loading=False)

    def test_with_no_copy_to_show_read_as_it_is_loaded_all_the_same(self):
        assert self._due(ListUpdate.MANUAL, has_copy=False)
        assert self._due(ListUpdate.DAILY, read_ago=60, has_copy=False)

    def test_a_file_on_the_disk_as_it_is_loaded_all_the_same(self):
        file = ListSource(kind=ListSourceKind.FILE, location="/lists/tv.m3u")

        assert self._due(ListUpdate.MANUAL, source=file)


def _due_setting(mode):
    from gridplayer.playlist_settings import PlaylistSettings

    PlaylistSettings().replace({"playlist/list_update": mode})


@pytest.fixture
def no_overrides():
    from gridplayer.playlist_settings import PlaylistSettings

    yield

    PlaylistSettings().replace({})


class TestReadAsOftenAsThePlaylistSays:
    def test_kept_copy_fresh_enough_not_read_again(
        self, manager, monkeypatch, no_overrides
    ):
        _due_setting(ListUpdate.HOURLY)
        list_cache.keep_read(SOURCE, _channels(1, 2), at=int(time.time()) - 60)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        kept = _linked()

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 2)
        assert _wait_until(lambda: not registry.is_being_read(kept.id))
        QTest.qWait(50)
        assert source.read == 0

    def test_kept_copy_too_old_read_again(self, manager, monkeypatch, no_overrides):
        _due_setting(ListUpdate.HOURLY)
        list_cache.keep_read(SOURCE, _channels(1, 2), at=int(time.time()) - 2 * HOUR)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        kept = _linked()

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 3)
        assert source.read == 1

    def test_manually_from_what_was_kept(self, manager, monkeypatch, no_overrides):
        _due_setting(ListUpdate.MANUAL)
        list_cache.keep_read(SOURCE, _channels(1, 2), at=1_700_000_000)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        kept = _linked()

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: not registry.is_being_read(kept.id))
        assert len(registry.get(kept.id).items) == 2
        assert source.read == 0

    def test_manually_with_nothing_kept_read_all_the_same(
        self, manager, monkeypatch, no_overrides
    ):
        _due_setting(ListUpdate.MANUAL)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        kept = _linked()

        manager.set_lists([kept])

        registry = manager._ctx.lists
        assert _wait_until(lambda: len(registry.get(kept.id).items) == 3)

    def test_while_it_is_open_once_it_is_old_enough(
        self, manager, monkeypatch, no_overrides
    ):
        _due_setting(ListUpdate.HOURLY)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        registry = manager._ctx.lists
        registry.load([_linked(*_channels(1), read_at=int(time.time()) - 2 * HOUR)])
        (media_list,) = registry.lists()

        manager._read_due_linked()

        assert _wait_until(lambda: len(registry.get(media_list.id).items) == 3)
        assert abs(registry.get(media_list.id).read_at - time.time()) < 5

    def test_not_while_it_is_fresh(self, manager, monkeypatch, no_overrides):
        _due_setting(ListUpdate.HOURLY)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        registry = manager._ctx.lists
        registry.load([_linked(*_channels(1), read_at=int(time.time()) - 60)])

        manager._read_due_linked()
        QTest.qWait(50)

        assert source.read == 0

    def test_not_while_its_window_is_open(self, manager, monkeypatch, no_overrides):
        _due_setting(ListUpdate.HOURLY)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        registry = manager._ctx.lists
        registry.load([_linked(*_channels(1), read_at=int(time.time()) - 2 * HOUR)])
        (media_list,) = registry.lists()
        manager._modal_list_id = media_list.id

        manager._read_due_linked()
        QTest.qWait(50)

        assert source.read == 0

    def test_one_that_could_not_be_read_let_be_for_a_while(
        self, manager, monkeypatch, no_overrides
    ):
        _due_setting(ListUpdate.HOURLY)
        source = _Source(HTTPStatusError(429))
        _reading_from(manager, monkeypatch, source)
        registry = manager._ctx.lists
        registry.load([_linked(*_channels(1), read_at=int(time.time()) - 2 * HOUR)])
        (media_list,) = registry.lists()

        manager._read_due_linked()
        assert _wait_until(lambda: registry.read_error(media_list.id) is not None)
        assert registry.read_error(media_list.id).status == 429

        manager._read_due_linked()
        QTest.qWait(50)

        assert source.read == 1

    def test_on_load_not_while_open(self, manager, monkeypatch, no_overrides):
        _due_setting(ListUpdate.ON_LOAD)
        source = _Source(_channels(1, 2, 3))
        _reading_from(manager, monkeypatch, source)
        registry = manager._ctx.lists
        registry.load([_linked(*_channels(1), read_at=1_700_000_000)])

        manager._read_due_linked()
        QTest.qWait(50)

        assert source.read == 0


class TestTheSetting:
    def test_on_playlist_load_out_of_the_box(self):
        from gridplayer.settings import _default_settings

        assert _default_settings["playlist/list_update"] == ListUpdate.ON_LOAD

    def test_in_the_lists_section_of_the_playlist_s(self):
        from gridplayer.params.settings_bindings import PLAYLIST_ATTRS
        from gridplayer.params.settings_fields.playlist import PLAYLIST_FIELDS

        field = next(
            spec
            for spec in PLAYLIST_FIELDS
            if spec.settings_key == "playlist/list_update"
        )

        assert PLAYLIST_ATTRS[field.settings_key] == "list_update"
        assert field.label == "Update linked lists"
        assert list(field.choices().values()) == [
            "On playlist load",
            "Every 5 minutes",
            "Every 15 minutes",
            "Every hour",
            "Every 6 hours",
            "Every day",
            "Manually",
        ]


def _tv(number, title, group="News", token="a"):
    return ListItem(uri=f"http://tv/{number}?token={token}", title=title, group=group)


class TestNewLinksForTheSameChannels:
    def test_each_still_itself(self):
        media_list = _linked(_tv(1, "One"), _tv(2, "Two"))

        again = refreshed(
            media_list, (_tv(1, "One", token="b"), _tv(2, "Two", token="b"))
        )

        assert [item.key for item in again.media_list.items] == [
            item.key for item in media_list.items
        ]
        assert str(again.media_list.items[0].uri) == "http://tv/1?token=b"
        assert again.added == again.gone == 0

    def test_not_one_called_the_same_as_another(self):
        media_list = _linked(_tv(1, "Movie"), _tv(2, "Movie"))

        again = refreshed(
            media_list, (_tv(1, "Movie", token="b"), _tv(2, "Movie", token="b"))
        )

        assert not {item.key for item in again.media_list.items} & {
            item.key for item in media_list.items
        }

    def test_told_apart_by_their_groups(self):
        media_list = _linked(_tv(1, "News", group="UK"), _tv(2, "News", group="US"))

        again = refreshed(
            media_list,
            (
                _tv(2, "News", group="US", token="b"),
                _tv(1, "News", group="UK", token="b"),
            ),
        ).media_list

        keys = {str(item.uri): item.key for item in again.items}
        assert keys["http://tv/1?token=b"] == media_list.items[0].key
        assert keys["http://tv/2?token=b"] == media_list.items[1].key

    def test_one_taken_off_stays_off(self):
        media_list = _linked(_tv(1, "One"), _tv(2, "Two"))
        media_list = with_removed(media_list, [media_list.items[1]]).model_copy(
            update={"items": media_list.items[:1]}
        )

        again = refreshed(
            media_list, (_tv(1, "One", token="b"), _tv(2, "Two", token="b"))
        ).media_list

        assert [item.title for item in again.items] == ["One"]
        assert again.removed_names == media_list.removed_names

    def test_put_back_by_hand_it_comes_back(self):
        media_list = _linked(_tv(1, "One"), _tv(2, "Two"))
        gone = with_removed(media_list, [media_list.items[1]])

        back = without_removed(gone, [_tv(2, "Two")])

        assert back.removed_names == ()

    def test_reloaded_nothing_is_kept_off(self):
        media_list = _linked(_tv(1, "One"), _tv(2, "Two"))
        gone = with_removed(media_list, [media_list.items[1]])

        assert reloaded(gone, (_tv(1, "One"),)).removed_names == ()

    def test_what_was_taken_off_kept_in_the_playlist(self):
        media_list = _linked(_tv(1, "One"), _tv(2, "Two"))
        gone = with_removed(media_list, [media_list.items[1]])

        (data,) = json.loads(_playlist(gone).dumps())["lists"]
        (back,) = Playlist.parse(_playlist(gone).dumps()).lists

        assert data["removed_names"] == ["Two\x1fNews"]
        assert back.removed_names == ("Two\x1fNews",)


class TestEachListsOwnUpdate:
    def _due(self, own, playlist, read_ago, every_s=None, is_loading=False):
        from gridplayer.utils.list_update import is_due

        media_list = MediaList(
            source=SOURCE,
            is_linked=True,
            read_at=NOW - read_ago,
            update=own,
            update_every_s=every_s,
        )

        return is_due(media_list, True, is_loading, playlist, NOW)

    def test_its_own_rather_than_the_playlist_s(self):
        assert self._due(ListUpdate.FIVE_MINUTES, ListUpdate.DAILY, 6 * 60)
        assert not self._due(ListUpdate.MANUAL, ListUpdate.HOURLY, 7 * 24 * HOUR)

    def test_the_playlist_s_where_it_has_none(self):
        assert self._due(None, ListUpdate.HOURLY, HOUR)

    def test_custom_by_its_own_time(self):
        assert not self._due(ListUpdate.CUSTOM, ListUpdate.ON_LOAD, 39 * 60, 40 * 60)
        assert self._due(ListUpdate.CUSTOM, ListUpdate.ON_LOAD, 40 * 60, 40 * 60)

    def test_when_next(self):
        from gridplayer.utils.list_update import next_update_at

        media_list = MediaList(read_at=NOW, update=ListUpdate.HOURLY)

        assert next_update_at(media_list, ListUpdate.ON_LOAD) == NOW + HOUR
        assert next_update_at(media_list, ListUpdate.ON_LOAD) is not None
        assert next_update_at(MediaList(read_at=NOW), ListUpdate.ON_LOAD) is None

    def test_warned_of_only_from_a_link_and_more_often_than_15_minutes(self):
        from gridplayer.utils.list_update import is_short

        file = ListSource(kind=ListSourceKind.FILE, location="/lists/tv.m3u")

        assert is_short(5 * 60, SOURCE)
        assert not is_short(15 * 60, SOURCE)
        assert not is_short(5 * 60, file)
        assert not is_short(None, SOURCE)

    def test_kept_in_the_playlist(self):
        media_list = _linked(update=ListUpdate.CUSTOM, update_every_s=2400)

        (back,) = Playlist.parse(_playlist(media_list).dumps()).lists

        assert back.update == ListUpdate.CUSTOM
        assert back.update_every_s == 2400

    def test_set_the_playlist_is_changed(self):
        media_list = _linked(_channel(1))
        own = media_list.model_copy(update={"update": ListUpdate.DAILY})

        assert not _is_same_state(
            TestChanged()._state(media_list), TestChanged()._state(own)
        )


def _update_menu(dialog):
    from gridplayer.widgets.custom_menu import CustomMenu

    menu = CustomMenu(parent=dialog)
    dialog._fill_update_menu(menu)
    return {
        action.text(): action for action in menu.actions() if not action.isSeparator()
    }


class TestTheUpdateButton:
    def test_a_linked_list_s_picks_how_often(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))

        dialog = window(registry, media_list)

        assert dialog._updated_button.is_choosable
        assert dialog._updated_button.menu() is dialog._update_menu

    def test_a_list_kept_whole_s_only_says_when(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(MediaList(items=_channels(1), source=SOURCE))

        dialog = window(registry, media_list)

        assert not dialog._updated_button.is_choosable
        assert dialog._updated_button.menu() is None

    def test_the_playlist_s_default_checked_out_of_the_box(self, window, no_overrides):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)

        actions = _update_menu(dialog)

        assert actions["Playlist default (On playlist load)"].isChecked()
        assert [title for title, action in actions.items() if action.isChecked()] == [
            "Playlist default (On playlist load)"
        ]
        assert list(actions) == [
            "Playlist default (On playlist load)",
            "On playlist load",
            "Every 5 minutes",
            "Every 15 minutes",
            "Every hour",
            "Every 6 hours",
            "Every day",
            "Custom…",
            "Manually",
        ]

    def test_says_what_the_playlist_s_default_is(self, window, no_overrides):
        _due_setting(ListUpdate.SIX_HOURS)
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)

        assert "Playlist default (Every 6 hours)" in _update_menu(dialog)

    def test_picked_it_is_the_list_s_own(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)

        _update_menu(dialog)["Every hour"].trigger()

        assert registry.get(media_list.id).update == ListUpdate.HOURLY
        assert _update_menu(dialog)["Every hour"].isChecked()

    def test_back_to_the_playlist_s(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1), update=ListUpdate.DAILY))
        dialog = window(registry, media_list)

        _update_menu(dialog)["Playlist default (On playlist load)"].trigger()

        assert registry.get(media_list.id).update is None

    def test_a_custom_one_said_as_it_is(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)
        dialog._ask_update_every = lambda every_s, is_from_site: 2400

        _update_menu(dialog)["Custom…"].trigger()

        changed = registry.get(media_list.id)
        assert (changed.update, changed.update_every_s) == (ListUpdate.CUSTOM, 2400)
        assert _update_menu(dialog)["Every 40 minutes"].isChecked()

    def test_custom_starts_from_how_often_it_is(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1), update=ListUpdate.SIX_HOURS))
        dialog = window(registry, media_list)
        asked = []
        dialog._ask_update_every = lambda every_s, is_from_site: asked.append(
            (every_s, is_from_site)
        )

        _update_menu(dialog)["Custom…"].trigger()

        assert asked == [(6 * HOUR, True)]
        assert registry.get(media_list.id).update == ListUpdate.SIX_HOURS

    def test_when_next_under_the_pointer(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(
            _linked(
                *_channels(1),
                update=ListUpdate.HOURLY,
                read_at=int(time.time()) - 5 * 60,
            )
        )

        dialog = window(registry, media_list)

        assert "Next update: in 54 minutes" in dialog._updated_button.toolTip() or (
            "Next update: in 55 minutes" in dialog._updated_button.toolTip()
        )

    def test_next_as_the_playlist_loads(self, window, no_overrides):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))

        dialog = window(registry, media_list)

        assert dialog._updated_button.toolTip().endswith(
            "Next update: when the playlist opens"
        )

    def test_only_by_refresh(self, window):
        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1), update=ListUpdate.MANUAL))

        dialog = window(registry, media_list)

        assert dialog._updated_button.toolTip().endswith("Updates only on Refresh")

    def test_in_the_right_click_menu_too(self, window):
        from gridplayer.widgets import custom_menu

        registry = MediaListsRegistry()
        media_list = registry.add(_linked(*_channels(1)))
        dialog = window(registry, media_list)
        shown = []
        plain_exec = custom_menu.CustomMenu.exec_
        custom_menu.CustomMenu.exec_ = lambda menu, *args: shown.append(
            [action.text() for action in menu.actions()]
        )
        try:
            dialog._show_source_menu(QPoint(10, 10))
        finally:
            custom_menu.CustomMenu.exec_ = plain_exec

        (texts,) = shown
        assert texts.index("Update") == texts.index("Unlink") - 1


class TestCustomUpdate:
    def _dialog(self, every_s, is_from_site=True):
        from gridplayer.dialogs.update_every import UpdateEveryDialog

        return UpdateEveryDialog(every_s, is_from_site)

    def test_in_the_largest_unit_it_is_a_whole_number_of(self):
        assert self._dialog(2400)._count.value() == 40
        assert self._dialog(3 * HOUR)._unit.currentText() == "hours"
        assert self._dialog(2 * 86_400)._count.value() == 2

    def test_how_often_it_comes_to(self):
        dialog = self._dialog(3600)
        dialog._count.setValue(90)
        dialog._unit.setCurrentIndex(0)

        assert dialog.every_s == 90 * 60

    def test_warned_more_often_than_15_minutes_from_a_link(self):
        dialog = self._dialog(3600)
        dialog._unit.setCurrentIndex(0)
        dialog._count.setValue(5)

        assert dialog.is_warned

        dialog._count.setValue(15)

        assert not dialog.is_warned

    def test_not_from_a_folder(self):
        dialog = self._dialog(60, is_from_site=False)

        assert not dialog.is_warned

    def test_said_as_the_menu_says_it(self):
        from gridplayer.dialogs.update_every import every_txt, in_txt

        assert every_txt(2400) == "Every 40 minutes"
        assert every_txt(3600) == "Every hour"
        assert every_txt(2 * 86_400) == "Every 2 days"
        assert in_txt(30) == "soon"
        assert in_txt(55 * 60) == "in 55 minutes"
        assert in_txt(5 * HOUR) == "in 5 hours"
