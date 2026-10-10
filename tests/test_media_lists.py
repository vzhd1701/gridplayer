"""The lists cells play from: what they hold, how a playlist keeps them, and
the registry the cells read them from."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from gridplayer.models.media_list import HttpHeaders, ListItem, ListSource, MediaList
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.static import ListEndAction, ListSourceKind
from gridplayer.player.managers.lists import MediaListsRegistry

URL = "https://www.youtube.com/watch?v=qIP9kb_RPd4"


def _touch(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        files.append(path)

    return files


def _saved(playlist: Playlist, path: Path) -> dict:
    playlist.save(path)

    return json.loads(path.read_text(encoding="utf-8"))


class TestAList:
    def test_each_item_is_known_by_a_key_of_its_own(self):
        media_list = MediaList(items=[ListItem(uri=URL), ListItem(uri=URL)])

        keys = [item.key for item in media_list.items]

        assert len(set(keys)) == 2

    def test_an_item_edited_is_still_the_same_item(self):
        item = ListItem(uri=URL)

        assert item.model_copy(update={"title": "Renamed"}).key == item.key

    def test_the_keys_are_for_while_the_app_is_open(self):
        data = MediaList(items=[ListItem(uri=URL, title="One")]).model_dump(mode="json")

        assert data["items"] == [
            {
                "uri": URL,
                "title": "One",
                "duration_ms": None,
                "group": None,
                "http_headers": None,
                "is_added": False,
                "is_renamed": False,
                "details": None,
            }
        ]

    def test_an_item_that_makes_no_sense_leaves_the_rest(self):
        media_list = MediaList.model_validate(
            {"items": [{"uri": URL}, {"title": "no uri"}, "junk", {"uri": URL}]}
        )

        assert [item.uri for item in media_list.items] == [URL, URL]

    def test_an_item_is_found_by_its_key(self):
        first, second = ListItem(uri=URL), ListItem(uri=URL)
        media_list = MediaList(items=[first, second])

        assert media_list.index_of_key(second.key) == 1
        assert media_list.item_by_key(first.key) is first
        assert media_list.index_of_key(None) is None
        assert media_list.index_of_key(-1) is None


class TestAPlaylistKeepsTheLists:
    def test_at_its_root_with_the_cells_pointing_at_them(self, tmp_path):
        (movie,) = _touch(tmp_path, "a.mp4")
        media_list = MediaList(name="Mine", items=[ListItem(uri=movie)])
        video = Video(uri=movie, list_id=media_list.id, list_index=0)

        doc = _saved(Playlist(videos=[video], lists=[media_list]), tmp_path / "p.gpls")

        assert doc["lists"][0]["id"] == str(media_list.id)
        assert doc["lists"][0]["name"] == "Mine"
        assert doc["videos"][0]["list_id"] == str(media_list.id)
        assert doc["videos"][0]["list_index"] == 0
        assert "lists" not in doc.get("settings", {})

    def test_none_is_said_where_there_are_none(self, tmp_path):
        (movie,) = _touch(tmp_path, "a.mp4")

        doc = _saved(Playlist(videos=[Video(uri=movie)]), tmp_path / "p.gpls")

        assert "lists" not in doc
        assert "list_id" not in doc["videos"][0]

    def test_files_on_them_are_written_the_way_the_videos_are(self, tmp_path):
        movie, other = _touch(tmp_path, "a.mp4", "sub/b.mp4")
        media_list = MediaList(
            items=[ListItem(uri=movie), ListItem(uri=other), ListItem(uri=URL)],
            source=ListSource(kind=ListSourceKind.FOLDER, location=tmp_path / "sub"),
        )

        doc = _saved(
            Playlist(
                videos=[Video(uri=movie)],
                lists=[media_list],
                save_paths_relative=True,
            ),
            tmp_path / "p.gpls",
        )

        assert [item["uri"] for item in doc["lists"][0]["items"]] == [
            "a.mp4",
            "sub/b.mp4",
            URL,
        ]
        assert doc["lists"][0]["source"]["location"] == "sub"

    def test_they_come_back_as_they_were(self, tmp_path):
        movie, other = _touch(tmp_path, "a.mp4", "sub/b.mp4")
        media_list = MediaList(
            name="Mine",
            items=[
                ListItem(uri=movie, title="First", duration_ms=1000),
                ListItem(uri=other, group="News"),
                ListItem(
                    uri=URL,
                    http_headers=HttpHeaders(user_agent="UA", referrer="https://ref/"),
                ),
            ],
            source=ListSource(kind=ListSourceKind.FILE, location=tmp_path / "x.m3u"),
        )
        video = Video(
            uri=other,
            list_id=media_list.id,
            list_index=1,
            list_end_action=ListEndAction.STOP,
        )
        path = tmp_path / "p.gpls"

        Playlist(videos=[video], lists=[media_list], save_paths_relative=True).save(
            path
        )

        loaded = Playlist.read(path)

        (read,) = loaded.lists
        assert read.id == media_list.id
        assert read.name == "Mine"
        assert [item.uri for item in read.items] == [movie, other, URL]
        assert read.items[0].title == "First"
        assert read.items[0].duration_ms == 1000
        assert read.items[1].group == "News"
        assert read.items[2].http_headers == HttpHeaders(
            user_agent="UA", referrer="https://ref/"
        )
        assert read.source.location == tmp_path / "x.m3u"
        assert loaded.videos[0].list_id == media_list.id
        assert loaded.videos[0].list_index == 1
        assert loaded.videos[0].list_end_action is ListEndAction.STOP

    def test_what_was_added_and_taken_off_by_hand_comes_back(self, tmp_path):
        movie, gone = _touch(tmp_path, "a.mp4", "b.mp4")
        media_list = MediaList(
            items=[ListItem(uri=movie), ListItem(uri=URL, is_added=True)],
            source=ListSource(kind=ListSourceKind.FOLDER, location=tmp_path),
            removed=(gone,),
        )
        path = tmp_path / "p.gpls"

        doc = _saved(Playlist(lists=[media_list], save_paths_relative=True), path)

        # said only where it is so, as most items are not
        assert "is_added" not in doc["lists"][0]["items"][0]
        assert doc["lists"][0]["items"][1]["is_added"] is True
        assert doc["lists"][0]["removed"] == ["b.mp4"]

        (read,) = Playlist.read(path).lists
        assert [item.is_added for item in read.items] == [False, True]
        assert read.removed == (gone,)

    def test_none_taken_off_is_not_said(self, tmp_path):
        doc = _saved(
            Playlist(lists=[MediaList(items=[ListItem(uri=URL)])]),
            tmp_path / "p.gpls",
        )

        assert "removed" not in doc["lists"][0]

    def test_a_file_on_a_list_that_is_gone_stays_on_it(self, tmp_path):
        movie, gone = _touch(tmp_path, "a.mp4", "b.mp4")
        media_list = MediaList(items=[ListItem(uri=movie), ListItem(uri=gone)])
        path = tmp_path / "p.gpls"

        Playlist(lists=[media_list]).save(path)
        gone.unlink()

        assert [item.uri for item in Playlist.read(path).lists[0].items] == [
            movie,
            gone,
        ]

    def test_a_list_that_makes_no_sense_leaves_the_playlist(self, tmp_path):
        (movie,) = _touch(tmp_path, "a.mp4")
        path = tmp_path / "p.gpls"
        path.write_text(
            json.dumps(
                {
                    "format": "gridplayer-playlist",
                    "videos": [{"uri": str(movie)}],
                    "lists": [{"id": "not an id"}, "junk", {"items": "nope"}],
                }
            ),
            encoding="utf-8",
        )

        loaded = Playlist.read(path)

        assert len(loaded.videos) == 1
        assert loaded.lists == []


class TestACellWhoseFileIsGone:
    def _saved_with_gone(self, tmp_path, names, playing, gone, list_id=True):
        files = _touch(tmp_path, *names)
        media_list = MediaList(items=[ListItem(uri=file) for file in files])
        video = Video(
            uri=files[playing],
            list_id=media_list.id if list_id else None,
            list_index=playing,
            current_position=5000,
        )
        path = tmp_path / "p.gpls"

        Playlist(videos=[video], lists=[media_list]).save(path)

        for index in gone:
            files[index].unlink()

        return files, Playlist.read(path)

    def test_is_kept_for_the_cell_to_go_on_along_its_list(self, tmp_path):
        files, loaded = self._saved_with_gone(
            tmp_path, ("a.mp4", "b.mp4", "c.mp4"), playing=1, gone=(1,)
        )

        (video,) = loaded.videos
        assert video.uri == files[1]
        assert video.list_index == 1

    def test_one_whose_list_is_not_there_goes(self, tmp_path):
        files = _touch(tmp_path, "a.mp4")
        path = tmp_path / "p.gpls"
        Playlist(videos=[Video(uri=files[0], list_id=uuid4())]).save(path)
        files[0].unlink()

        assert Playlist.read(path).videos == []

    def test_one_without_a_list_goes_as_it_always_did(self, tmp_path):
        _files, loaded = self._saved_with_gone(
            tmp_path, ("a.mp4", "b.mp4"), playing=0, gone=(0,), list_id=False
        )

        assert loaded.videos == []


class TestACellWaitingForItsList:
    """Saved before what it waits for was read: read again as the playlist
    opens."""

    def test_for_a_folder(self, tmp_path):
        folder = tmp_path / "Shows"
        folder.mkdir()
        path = tmp_path / "p.gpls"

        Playlist(videos=[Video(uri=str(folder), read_as_list=True)]).save(path)

        (video,) = Playlist.read(path).videos
        assert video.uri == str(folder)
        assert video.read_as_list

    def test_for_a_list_file(self, tmp_path):
        (list_file,) = _touch(tmp_path, "tv.m3u")
        path = tmp_path / "p.gpls"

        Playlist(videos=[Video(uri=list_file, read_as_list=True)]).save(path)

        (video,) = Playlist.read(path).videos
        assert video.uri == list_file
        assert video.read_as_list

    def test_a_video_says_nothing_of_it(self, tmp_path):
        (movie,) = _touch(tmp_path, "a.mp4")

        doc = _saved(Playlist(videos=[Video(uri=movie)]), tmp_path / "p.gpls")

        assert "read_as_list" not in doc["videos"][0]


class TestTheRegistry:
    @pytest.fixture
    def registry(self):
        registry = MediaListsRegistry()
        registry.changes = []
        registry.changed.connect(registry.changes.append)

        return registry

    def test_a_list_added_is_there_by_its_id(self, registry):
        media_list = registry.add(MediaList(items=[ListItem(uri=URL)]))

        assert registry.get(media_list.id) is media_list
        assert registry.changes == [media_list.id]

    def test_one_from_elsewhere_with_an_id_taken_gets_its_own(self, registry):
        here = registry.add(MediaList(items=[ListItem(uri=URL)]))
        brought = MediaList(id=here.id, items=[ListItem(uri=URL, title="other")])

        added = registry.add(brought)

        assert added.id != here.id
        assert registry.get(here.id) is here
        assert registry.get(added.id).items[0].title == "other"

    def test_put_tells_only_of_a_change(self, registry):
        media_list = registry.add(MediaList(items=[ListItem(uri=URL)]))
        registry.changes.clear()

        registry.put(media_list)
        assert registry.changes == []

        registry.put(media_list.model_copy(update={"name": "New"}))
        assert registry.changes == [media_list.id]

    def test_an_item_renamed_keeps_its_key(self, registry):
        item = ListItem(uri=URL)
        media_list = registry.add(MediaList(items=[item]))

        registry.rename_item(media_list.id, item.key, "Renamed")

        (renamed,) = registry.get(media_list.id).items
        assert renamed.title == "Renamed"
        assert renamed.key == item.key

    def test_renaming_an_item_gone_does_nothing(self, registry):
        media_list = registry.add(MediaList(items=[ListItem(uri=URL)]))

        registry.rename_item(media_list.id, -1, "Renamed")
        registry.rename_item(uuid4(), 1, "Renamed")

        assert registry.get(media_list.id).items[0].title is None

    def test_a_list_left_by_its_cells_goes_once_saved(self, registry):
        left = registry.add(MediaList(name="left"))
        used = registry.add(MediaList(name="used"))
        registry.take_up(left.id)
        registry.take_up(used.id)

        assert [ml.name for ml in registry.kept({used.id})] == ["used"]

        registry.forget_left({used.id})

        assert registry.get(left.id) is None
        assert registry.get(used.id) is used

    def test_one_no_cell_took_up_stays(self, registry):
        """Read with a playlist whose cells' files were not there."""

        parked = registry.add(MediaList(name="parked"))

        registry.forget_left(set())

        assert registry.get(parked.id) is parked

    def test_one_added_for_a_cell_that_never_came_goes_at_once(self, registry):
        turned_away = registry.add(MediaList(name="away"))
        taken = registry.add(MediaList(name="taken"))
        registry.take_up(taken.id)

        registry.drop_if_untaken(turned_away.id)
        registry.drop_if_untaken(taken.id)
        registry.drop_if_untaken(None)

        assert registry.get(turned_away.id) is None
        assert registry.get(taken.id) is taken

    def test_an_item_changed_keeps_its_key(self, registry):
        media_list = registry.add(MediaList(items=[ListItem(uri=URL)]))
        key = media_list.items[0].key

        registry.update_item(media_list.id, key, duration_ms=5000)

        (item,) = registry.get(media_list.id).items
        assert (item.key, item.duration_ms) == (key, 5000)

    def test_an_item_read_from_a_list_file_changed(self, registry):
        from gridplayer.utils.list_files import parse_m3u

        read = parse_m3u("#EXTM3U\n#EXTINF:-1,One\nhttp://h/1\n", None)
        media_list = registry.add(MediaList(items=read.items))

        registry.update_item(media_list.id, read.items[0].key, duration_ms=5000)

        assert registry.get(media_list.id).items[0].duration_ms == 5000

    def test_a_list_removed_is_gone(self, registry):
        media_list = registry.add(MediaList(items=[ListItem(uri=URL)]))
        told = []
        registry.changed.connect(told.append)

        registry.remove(media_list.id)

        assert registry.get(media_list.id) is None
        assert told == [media_list.id]

    def test_tells_a_list_taken_up_from_one_not(self, registry):
        taken = registry.add(MediaList(items=[ListItem(uri=URL)]))
        other = registry.add(MediaList(items=[ListItem(uri=URL)]))

        registry.take_up(taken.id)

        assert registry.is_taken_up(taken.id)
        assert not registry.is_taken_up(other.id)

    def test_another_playlists_in_place_of_these(self, registry):
        registry.add(MediaList(name="old"))
        replaced = []
        registry.replaced.connect(lambda: replaced.append(True))

        new = MediaList(name="new")
        registry.load([new])

        assert registry.lists() == [new]
        assert replaced == [True]


class TestWhatASiteSaysOfAVideo:
    def _said(self, **fields):
        from gridplayer.models.media_list import ItemDetails

        return ItemDetails(**fields)

    def test_the_newer_numbers(self):
        from gridplayer.models.media_list import merged_details

        merged = merged_details(
            self._said(view_count=1, channel="Old", thumbnail="https://a/1.jpg"),
            self._said(view_count=2, channel="New"),
        )

        assert merged.view_count == 2
        assert merged.channel == "New"
        # what it left out now, from before
        assert merged.thumbnail == "https://a/1.jpg"

    def test_a_date_to_the_second_over_one_as_near_as_a_page_says(self):
        from gridplayer.models.media_list import merged_details

        known = self._said(published=100, is_published_exact=True)

        assert merged_details(known, self._said(published=50)).published == 100
        assert merged_details(self._said(published=50), known).published == 100

    def test_nothing_said_now_is_what_was_said(self):
        from gridplayer.models.media_list import merged_details

        known = self._said(view_count=1)

        assert merged_details(known, None) is known
        assert merged_details(None, known) is known

    def test_kept_in_the_playlist_without_what_goes_without_saying(self, tmp_path):
        from gridplayer.models.media_list import ItemDetails

        item = ListItem(
            uri=URL,
            details=ItemDetails(channel="C", view_count=5, published=100),
        )
        playlist = Playlist(lists=[MediaList(items=[item])])

        (saved,) = _saved(playlist, tmp_path / "p.gpls")["lists"][0]["items"]

        assert saved["details"] == {"channel": "C", "view_count": 5, "published": 100}

    def test_read_back_from_the_playlist(self, tmp_path):
        from gridplayer.models.media_list import ItemDetails

        details = ItemDetails(
            channel="C", view_count=5, published=100, is_published_exact=True
        )
        playlist = Playlist(
            lists=[MediaList(items=[ListItem(uri=URL, details=details)])]
        )
        playlist.save(tmp_path / "p.gpls")

        read = Playlist.read(tmp_path / "p.gpls")

        assert read.lists[0].items[0].details == details

    def test_an_item_read_from_a_channel_list_is_no_bigger_for_it(self):
        import sys

        from gridplayer.utils.list_files import _item

        item = _item("http://x/1.ts", {"title": "One", "group": "News"})

        # past ten fields, the table they are kept in grows from the size of
        # one of eight
        eight = {f"field{n}": None for n in range(8)}

        assert len(item.__dict__) <= 10
        assert sys.getsizeof(item.__dict__) == sys.getsizeof(eight)
