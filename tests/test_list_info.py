"""Looking up what is known of a list's items in the background: put onto the
list as it comes, a few at a time, and how far it has got told; a site that
turns it away stops the rest, kept to be tried again."""

import threading
import time
from pathlib import Path

import pytest
from PyQt5.QtTest import QTest

from gridplayer.models.media_list import ItemDetails, ListItem, MediaList
from gridplayer.player.managers import list_info
from gridplayer.player.managers.list_info import ItemLookups, learned_fields
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.utils.item_info import Found, NotFound, Refused

SITE = "https://vimeo.com/1"


def _watch(n) -> str:
    return f"https://www.youtube.com/watch?v=video{n:06}"


def _id(n) -> str:
    return f"video{n:06}"


def _wait_until(condition, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if condition():
            return True
    return False


class _Site:
    """What the lookups are told, by a test: each answer by link or file, a
    gate holding them back, and what was asked for, in order."""

    def __init__(self):
        self.youtube = {}
        self.links = {}
        self.lengths = {}
        self.asked = []
        self.gate = None
        self.refuse_links = False
        self.refuse_youtube = False

    def _wait(self):
        if self.gate is not None:
            self.gate.wait(5)

    def look_up_youtube(self, ids):
        self.asked.append(("youtube", tuple(ids)))
        self._wait()
        if self.refuse_youtube:
            raise Refused("YouTube")
        return {
            video_id: self.youtube[video_id]
            for video_id in ids
            if video_id in self.youtube
        }

    def look_up_link(self, url):
        self.asked.append(("link", url))
        self._wait()
        if self.refuse_links:
            raise Refused("YouTube")
        if url not in self.links:
            raise NotFound("gone")
        return self.links[url]

    def file_lengths(self, paths):
        self.asked.append(("files", tuple(paths)))
        self._wait()
        return [self.lengths.get(path) for path in paths]


@pytest.fixture
def site():
    return _Site()


@pytest.fixture
def registry():
    return MediaListsRegistry()


@pytest.fixture
def lookups(registry, site):
    lookups = ItemLookups(
        registry,
        look_up_youtube=site.look_up_youtube,
        look_up_link=site.look_up_link,
        file_lengths=site.file_lengths,
        is_site_link=lambda url: url == SITE,
    )

    lookups.done = []
    lookups.finished.connect(lambda *args: lookups.done.append(args))
    lookups.learned_lists = []
    lookups.learned.connect(
        lambda list_id, fields: lookups.learned_lists.append(fields)
    )

    yield lookups

    if site.gate is not None:
        site.gate.set()
    lookups.shutdown()


def _list(registry, *items) -> MediaList:
    return registry.add(MediaList(name="Mine", items=tuple(items)))


def _items(registry, media_list) -> tuple[ListItem, ...]:
    return registry.get(media_list.id).items


def _finished(lookups):
    return _wait_until(lambda: lookups.done)


class TestFiles:
    def test_their_lengths_put_on(self, registry, lookups, site):
        a, b = Path("D:/a.mp4"), Path("D:/gone.mp4")
        site.lengths[a] = 61_000
        media_list = _list(registry, ListItem(uri=a), ListItem(uri=b))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert [item.duration_ms for item in _items(registry, media_list)] == [
            61_000,
            None,
        ]
        assert lookups.done == [(media_list.id, 1, 1, 0)]
        assert lookups.state(media_list.id) is None

    def test_asked_of_a_few_at_a_time(self, registry, lookups, site):
        paths = [Path(f"D:/{n}.mp4") for n in range(list_info.FILES_ASKED_AT_ONCE + 3)]
        media_list = _list(registry, *(ListItem(uri=path) for path in paths))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert [len(paths) for kind, paths in site.asked] == [
            list_info.FILES_ASKED_AT_ONCE,
            3,
        ]


class TestYouTube:
    def test_its_list_then_each_on_its_own(self, registry, lookups, site):
        site.youtube[_id(1)] = Found(
            title="One",
            duration_ms=60_000,
            details=ItemDetails(channel="Chan", thumbnail="pic"),
        )
        site.links[_watch(1)] = Found(
            title="One again",
            details=ItemDetails(
                view_count=1234, published=1000, is_published_exact=True
            ),
        )
        media_list = _list(registry, ListItem(uri=_watch(1)))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert site.asked == [("youtube", (_id(1),)), ("link", _watch(1))]

        (item,) = _items(registry, media_list)
        # the list's title, the first one learned; nothing over it after
        assert item.title == "One"
        assert item.duration_ms == 60_000
        assert item.details == ItemDetails(
            channel="Chan",
            view_count=1234,
            published=1000,
            is_published_exact=True,
            thumbnail="pic",
        )
        assert lookups.done == [(media_list.id, 1, 0, 0)]

    def test_fifty_to_a_list(self, registry, lookups, site):
        count = list_info.YOUTUBE_LIST_MAX + 1
        media_list = _list(registry, *(ListItem(uri=_watch(n)) for n in range(count)))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        lists = [ids for kind, ids in site.asked if kind == "youtube"]
        assert [len(ids) for ids in lists] == [list_info.YOUTUBE_LIST_MAX, 1]

    def test_one_not_on_its_list_looked_up_on_its_own(self, registry, lookups, site):
        site.links[_watch(1)] = Found(title="Found alone")
        media_list = _list(registry, ListItem(uri=_watch(1)), ListItem(uri=_watch(2)))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert [item.title for item in _items(registry, media_list)] == [
            "Found alone",
            None,
        ]
        assert lookups.done == [(media_list.id, 1, 1, 0)]

    def test_no_views_or_dates_had_said(self, registry, lookups, site):
        site.youtube[_id(1)] = Found(title="One")
        media_list = _list(registry, ListItem(uri=_watch(1)))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert lookups.done == [(media_list.id, 1, 0, 1)]
        assert _items(registry, media_list)[0].title == "One"

    def test_views_and_dates_after_the_rest(self, registry, lookups, site):
        site.youtube[_id(1)] = Found(title="One")
        site.links[_watch(1)] = Found(details=ItemDetails(view_count=5))
        media_list = _list(registry, ListItem(uri=_watch(1)))
        site.gate = threading.Event()

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _wait_until(lambda: site.asked)
        state = lookups.state(media_list.id)
        assert (state.count, state.done, state.is_details) == (1, 0, False)

        site.gate.set()
        site.gate = threading.Event()
        assert _wait_until(lambda: len(site.asked) == 2)

        state = lookups.state(media_list.id)
        assert (state.count, state.done, state.is_details) == (1, 0, True)
        # what its list said, put on while the rest is looked up
        assert _wait_until(lambda: _items(registry, media_list)[0].title == "One")

        site.gate.set()
        assert _finished(lookups)


class TestOtherSites:
    def test_each_on_its_own(self, registry, lookups, site):
        site.links[SITE] = Found(title="On Vimeo", duration_ms=5000)
        media_list = _list(
            registry,
            ListItem(uri=SITE),
            ListItem(uri="http://iptv.example/live/1.ts"),
        )

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert site.asked == [("link", SITE)]
        assert _items(registry, media_list)[0].title == "On Vimeo"
        assert lookups.done == [(media_list.id, 1, 0, 0)]


class TestWhatIsLookedUp:
    def test_the_missing_alone(self, registry, lookups, site):
        media_list = _list(
            registry,
            ListItem(uri=Path("D:/a.mp4"), duration_ms=1000),
            ListItem(uri=_watch(1), details=ItemDetails(channel="Known")),
        )

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert site.asked == []
        assert lookups.done == [(media_list.id, 0, 0, 0)]

    def test_asked_for_all_the_same(self, registry, lookups, site):
        media_list = _list(
            registry, ListItem(uri=_watch(1), details=ItemDetails(channel="Known"))
        )

        lookups.look_up(media_list.id, media_list.items, is_missing_only=False)

        assert _finished(lookups)
        assert site.asked[0] == ("youtube", (_id(1),))

    def test_asked_for_again_while_looked_up_once(self, registry, lookups, site):
        media_list = _list(registry, ListItem(uri=SITE))
        site.gate = threading.Event()

        lookups.look_up(media_list.id, media_list.items, is_missing_only=False)
        lookups.look_up(media_list.id, media_list.items, is_missing_only=False)
        site.gate.set()

        assert _finished(lookups)
        assert site.asked == [("link", SITE)]

    def test_more_asked_for_meanwhile_go_along(self, registry, lookups, site):
        a = ListItem(uri=SITE)
        b = ListItem(uri=Path("D:/b.mp4"))
        media_list = _list(registry, a, b)
        site.gate = threading.Event()

        lookups.look_up(media_list.id, [a], is_missing_only=False)
        assert _wait_until(lambda: site.asked)
        lookups.look_up(media_list.id, [b], is_missing_only=False)
        assert _wait_until(lambda: lookups.state(media_list.id).count == 2)
        site.gate.set()

        assert _finished(lookups)
        assert lookups.done == [(media_list.id, 0, 2, 0)]


class TestPutOn:
    def test_many_as_one_change(self, registry, lookups, site, mocker):
        paths = [Path(f"D:/{n}.mp4") for n in range(10)]
        site.lengths = dict.fromkeys(paths, 1000)
        media_list = _list(registry, *(ListItem(uri=path) for path in paths))
        changes = []
        registry.changed.connect(changes.append)

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _finished(lookups)
        assert changes == [media_list.id]
        (learned,) = lookups.learned_lists
        assert len(learned) == 10

    def test_not_onto_an_item_gone_meanwhile(self, registry, lookups, site):
        a = ListItem(uri=SITE)
        site.links[SITE] = Found(title="Late")
        media_list = _list(registry, a, ListItem(uri=Path("D:/b.mp4")))
        site.gate = threading.Event()

        lookups.look_up(media_list.id, [a], is_missing_only=False)
        assert _wait_until(lambda: site.asked)
        registry.put(registry.get(media_list.id).model_copy(update={"items": ()}))
        site.gate.set()

        assert _finished(lookups)
        assert _items(registry, media_list) == ()


class TestStopped:
    def test_the_rest_not_looked_up(self, registry, lookups, site):
        media_list = _list(registry, *(ListItem(uri=SITE + str(n)) for n in range(6)))
        lookups._is_site_link = lambda url: url.startswith(SITE)
        site.gate = threading.Event()

        lookups.look_up(media_list.id, media_list.items, is_missing_only=False)
        assert _wait_until(lambda: len(site.asked) == list_info.LINKS_AT_ONCE)

        lookups.stop(media_list.id)
        site.gate.set()
        QTest.qWait(200)

        assert lookups.state(media_list.id) is None
        assert len(site.asked) == list_info.LINKS_AT_ONCE
        assert lookups.done == []


class TestTurnedAway:
    def test_the_rest_kept_to_be_tried_again(self, registry, lookups, site):
        media_list = _list(registry, *(ListItem(uri=SITE + str(n)) for n in range(5)))
        lookups._is_site_link = lambda url: url.startswith(SITE)
        site.refuse_links = True

        lookups.look_up(media_list.id, media_list.items, is_missing_only=False)

        assert _wait_until(
            lambda: (
                lookups.state(media_list.id) is not None
                and lookups.state(media_list.id).refused == "YouTube"
            )
        )
        QTest.qWait(100)
        asked_once = len(site.asked)
        assert asked_once < 5

        site.refuse_links = False
        site.links = {SITE + str(n): Found(title=str(n)) for n in range(5)}
        lookups.try_again(media_list.id)

        assert _finished(lookups)
        assert [item.title for item in _items(registry, media_list)] == [
            str(n) for n in range(5)
        ]

    def test_youtubes_list_turned_away(self, registry, lookups, site):
        media_list = _list(registry, ListItem(uri=_watch(1)))
        site.refuse_youtube = True

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _wait_until(
            lambda: (
                lookups.state(media_list.id) is not None
                and lookups.state(media_list.id).refused == "YouTube"
            )
        )

    def test_views_and_dates_turned_away_the_rest_kept(self, registry, lookups, site):
        site.youtube[_id(1)] = Found(title="One", details=ItemDetails(channel="C"))
        site.refuse_links = True
        media_list = _list(registry, ListItem(uri=_watch(1)))

        lookups.look_up(media_list.id, media_list.items, is_missing_only=True)

        assert _wait_until(
            lambda: (
                lookups.state(media_list.id) is not None
                and lookups.state(media_list.id).refused == "YouTube"
            )
        )
        state = lookups.state(media_list.id)
        assert (state.is_details, state.count, state.done) == (True, 1, 0)
        assert _wait_until(lambda: _items(registry, media_list)[0].title == "One")

        # tried again: only the views and dates
        site.refuse_links = False
        site.links[_watch(1)] = Found(details=ItemDetails(view_count=7))
        lookups.try_again(media_list.id)

        assert _finished(lookups)
        assert site.asked[-1] == ("link", _watch(1))
        assert lookups.done == [(media_list.id, 1, 0, 0)]
        assert _items(registry, media_list)[0].details.view_count == 7


class TestWhatALookupChanges:
    def test_a_title_only_where_there_is_none(self):
        found = [Found(title="Site's")]

        assert learned_fields(ListItem(uri=SITE), found) == {"title": "Site's"}
        assert learned_fields(ListItem(uri=SITE, title="Mine"), found) == {}

    def test_never_a_files_title(self):
        item = ListItem(uri=Path("D:/a.mp4"))

        assert learned_fields(item, [Found(title="Tag", duration_ms=5)]) == {
            "duration_ms": 5
        }

    def test_what_a_site_says_over_what_it_said(self):
        item = ListItem(uri=SITE, details=ItemDetails(channel="C", view_count=1))

        fields = learned_fields(item, [Found(details=ItemDetails(view_count=2))])

        assert fields == {"details": ItemDetails(channel="C", view_count=2)}

    def test_nothing_new_nothing_changed(self):
        item = ListItem(uri=SITE, title="A", duration_ms=5)

        assert learned_fields(item, [Found(title="B", duration_ms=5)]) == {}


class TestTheRegistry:
    def test_many_items_changed_as_one(self, registry):
        a, b, c = (ListItem(uri=SITE + str(n)) for n in range(3))
        media_list = _list(registry, a, b, c)
        changes = []
        registry.changed.connect(changes.append)

        registry.update_items(
            media_list.id, {a.key: {"title": "A"}, c.key: {"title": "C"}, 999: {}}
        )

        assert [item.title for item in _items(registry, media_list)] == [
            "A",
            None,
            "C",
        ]
        assert changes == [media_list.id]
        # the keys where they were
        assert registry.get(media_list.id).index_of_key(c.key) == 2

    def test_items_added_told(self, registry):
        media_list = _list(registry, ListItem(uri=SITE))
        told = []
        registry.items_added.connect(lambda *args: told.append(args))

        registry.tell_added(media_list.id, [1, 2])
        registry.tell_added(media_list.id, [])

        assert told == [(media_list.id, [1, 2])]
