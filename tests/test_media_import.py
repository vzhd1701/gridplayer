"""What is added is read into files, links and lists, and put into cells."""

from pathlib import Path

import pytest

from gridplayer.models.media_list import ListItem, ListSource
from gridplayer.params.static import AddMode, ListSourceKind
from gridplayer.utils import list_files
from gridplayer.utils.list_progress import ReadingEnough
from gridplayer.utils.media_import import (
    Expanded,
    ListInput,
    choices_for,
    count_cells,
    expand_inputs,
    folder_list,
    is_list_url,
    plan_cells,
    read_source,
    recent_uris,
)
from gridplayer.utils.next_file import ScanRules

RULES = ScanRules()


def _touch(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        files.append(path)

    return files


def _expand(uris, fetch=None):
    return expand_inputs([str(uri) for uri in uris], RULES, fetch)


class TestReadingWhatIsAdded:
    def test_a_file_is_itself(self, tmp_path):
        (movie,) = _touch(tmp_path, "a.mp4")

        (group,) = _expand([movie]).groups

        assert group == ListItem(uri=movie, key=group.key)

    def test_a_link_is_itself(self):
        (group,) = _expand(["https://host/a.mp4"]).groups

        assert group.uri == "https://host/a.mp4"

    def test_a_folder_is_a_list_of_what_is_in_it_and_under_it(self, tmp_path):
        folder = tmp_path / "Season 1"
        _touch(folder, "Ep 10.mkv", "Ep 2.mkv", "notes.txt", "Extras/x.mp4")

        (group,) = _expand([folder]).groups

        assert group.name == "Season 1"
        assert [item.uri.name for item in group.items] == [
            "Ep 2.mkv",
            "Ep 10.mkv",
            "x.mp4",
        ]
        assert group.source.kind is ListSourceKind.FOLDER
        assert group.source.location == folder
        assert group.source.is_recursive

    def test_a_folder_with_nothing_to_play_could_not_be_read(self, tmp_path):
        _touch(tmp_path / "empty", "readme.txt")

        expanded = _expand([tmp_path / "empty"])

        assert expanded.groups == ()
        assert expanded.failed == ((str(tmp_path / "empty"), "no media files"),)

    def test_a_list_file_is_its_list(self, tmp_path):
        path = tmp_path / "shows.m3u"
        path.write_text("#PLAYLIST:Shows\na.mp4\nb.mp4\n", encoding="utf-8")

        (group,) = _expand([path]).groups

        assert group.name == "Shows"
        assert [item.uri for item in group.items] == [
            tmp_path / "a.mp4",
            tmp_path / "b.mp4",
        ]
        assert group.source.kind is ListSourceKind.FILE
        assert group.source.location == path

    def test_a_list_file_named_by_its_file_where_it_says_no_name(self, tmp_path):
        path = tmp_path / "shows.m3u"
        path.write_text("a.mp4\n", encoding="utf-8")

        (group,) = _expand([path]).groups

        assert group.name == "shows"

    def test_an_hls_stream_saved_to_a_file_is_one_video(self, tmp_path):
        path = tmp_path / "stream.m3u8"
        path.write_text("#EXTM3U\n#EXT-X-TARGETDURATION:6\nseg.ts\n", encoding="utf-8")

        (group,) = _expand([path]).groups

        assert isinstance(group, ListItem)
        assert group.uri == path

    def test_an_empty_list_could_not_be_read(self, tmp_path):
        path = tmp_path / "empty.m3u"
        path.write_text("#EXTM3U\n", encoding="utf-8")

        expanded = _expand([path])

        assert expanded.groups == ()
        assert expanded.failed[0][0] == str(path)

    def test_a_link_to_a_list_is_its_list(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            return b"#EXTM3U\n#EXTINF:-1,One\nhttp://iptv/1.ts\n"

        url = "http://provider/get.php?username=u&password=p&type=m3u_plus"
        (group,) = _expand([url], fetch).groups

        assert fetched == [url]
        assert group.items[0].title == "One"
        assert group.source.kind is ListSourceKind.URL
        assert group.source.location == url

    def test_a_link_to_an_hls_stream_is_one_video(self):
        url = "https://cdn/live/index.m3u8"

        (group,) = _expand(
            [url], lambda _url: b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow.m3u8\n"
        ).groups

        assert isinstance(group, ListItem)
        assert group.uri == url

    def test_a_link_to_a_page_that_is_not_a_list_is_one_video(self):
        url = "https://site/watch.m3u"

        (group,) = _expand([url], lambda _url: b"<html>sign in</html>").groups

        assert group.uri == url

    def test_a_list_link_that_cannot_be_fetched_could_not_be_read(self):
        def fetch(_url):
            raise OSError("HTTP 404")

        expanded = _expand(["https://host/list.m3u"], fetch)

        assert expanded.groups == ()
        assert expanded.failed == (("https://host/list.m3u", "HTTP 404"),)

    def test_without_fetching_a_link_is_a_video_as_always(self):
        (group,) = _expand(["https://host/list.m3u"]).groups

        assert group.uri == "https://host/list.m3u"

    def test_the_rest_goes_on_past_one_that_could_not_be_read(self, tmp_path):
        (movie,) = _touch(tmp_path, "a.mp4")
        _touch(tmp_path / "empty", "x.txt")

        expanded = _expand([tmp_path / "empty", movie])

        assert [group.uri for group in expanded.groups] == [movie]
        assert len(expanded.failed) == 1


class TestAFolderAsAList:
    def test_with_its_subfolders(self, tmp_path):
        top, under = _touch(tmp_path, "a.mp4", "sub/b.mp4")

        folder = folder_list(tmp_path, RULES)

        assert [item.uri for item in folder.items] == [top, under]
        assert folder.source.is_recursive

    def test_or_without(self, tmp_path):
        top, _under = _touch(tmp_path, "a.mp4", "sub/b.mp4")

        folder = folder_list(tmp_path, RULES, is_recursive=False)

        assert [item.uri for item in folder.items] == [top]
        assert not folder.source.is_recursive

    def test_none_with_nothing_to_play(self, tmp_path):
        _touch(tmp_path, "notes.txt")

        assert folder_list(tmp_path, RULES) is None


class TestEndedEarly:
    def test_a_folder_what_was_found_of_it(self, tmp_path):
        _touch(tmp_path, "a.mp4", "sub/b.mp4", "sub/c.mp4")

        def progress(what, count, of=None):
            if count == 1:
                raise ReadingEnough

        expanded = expand_inputs([tmp_path], RULES, progress=progress)

        (folder,) = expanded.groups
        assert [item.uri.name for item in folder.items] == ["a.mp4"]

    def test_a_list_still_downloaded_let_go(self):
        def fetch(url):
            raise ReadingEnough

        expanded = expand_inputs(["https://host/channels.m3u"], RULES, fetch=fetch)

        assert expanded == Expanded()


class TestReadingAListAgain:
    def test_from_its_folder_as_it_was_read(self, tmp_path):
        top, _under = _touch(tmp_path, "a.mp4", "sub/b.mp4")
        source = ListSource(kind=ListSourceKind.FOLDER, location=tmp_path)

        items = read_source(source, RULES)

        assert [item.uri for item in items] == [top]

    def test_a_folder_gone_cannot_be_read(self, tmp_path):
        source = ListSource(kind=ListSourceKind.FOLDER, location=tmp_path / "gone")

        with pytest.raises(OSError, match="not found"):
            read_source(source, RULES)

    def test_from_its_list_file(self, tmp_path):
        list_file = tmp_path / "tv.m3u"
        list_file.write_text("#EXTM3U\n#EXTINF:-1,One\nhttp://tv/1\n", "utf-8")
        source = ListSource(kind=ListSourceKind.FILE, location=list_file)

        (item,) = read_source(source, RULES)

        assert (item.uri, item.title) == ("http://tv/1", "One")

    def test_from_a_link_to_a_list_file(self):
        source = ListSource(kind=ListSourceKind.URL, location="http://tv/list.m3u")

        (item,) = read_source(
            source, RULES, fetch=lambda url: b"#EXTM3U\n#EXTINF:-1,One\nhttp://tv/1\n"
        )

        assert item.uri == "http://tv/1"

    @pytest.mark.parametrize("kind", [ListSourceKind.FILE, ListSourceKind.URL])
    def test_how_far_it_has_got_told(self, tmp_path, mocker, kind):
        mocker.patch.object(list_files, "PROGRESS_EVERY_ITEMS", 1)
        text = "#EXTM3U\nhttp://tv/1\nhttp://tv/2\n"
        list_file = tmp_path / "tv.m3u"
        list_file.write_text(text, "utf-8")
        location = list_file if kind == ListSourceKind.FILE else "http://tv/l.m3u"
        told = []

        read_source(
            ListSource(kind=kind, location=location),
            RULES,
            fetch=lambda url: text.encode(),
            progress=lambda *said: told.append(said[:2]),
        )

        assert told == [("items", 1), ("items", 2)]

    def test_a_link_to_what_is_not_a_list_cannot_be_read(self):
        source = ListSource(kind=ListSourceKind.URL, location="http://tv/list.m3u")

        with pytest.raises(ValueError, match="Not a list"):
            read_source(source, RULES, fetch=lambda url: b"<html></html>")

    def test_from_a_site(self):
        source = ListSource(kind=ListSourceKind.URL, location="https://site/playlist")
        items = (ListItem(uri="https://site/1"), ListItem(uri="https://site/2"))

        read = read_source(
            source, RULES, read_web=lambda url: ListInput(name="P", items=items)
        )

        assert read == items

    def test_a_site_with_one_video_on_it_now(self):
        source = ListSource(kind=ListSourceKind.URL, location="https://site/playlist")
        item = ListItem(uri="https://site/1")

        assert read_source(source, RULES, read_web=lambda url: item) == (item,)


class TestListLinks:
    @pytest.mark.parametrize(
        "url",
        [
            "https://host/channels.m3u",
            "https://host/channels.M3U8?token=1",
            "http://host/radio.pls",
            "http://host/saved.xspf",
            "http://host:8080/get.php?username=a&password=b&type=m3u_plus&output=ts",
        ],
    )
    def test_ones_that_may_lead_to_a_list(self, url):
        assert is_list_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://host/video.mp4",
            "https://www.youtube.com/watch?v=x",
            "rtsp://cam/stream.m3u8",
            "https://host/get.php?type=video",
        ],
    )
    def test_ones_that_do_not(self, url):
        assert not is_list_url(url)


def _list(name, *uris):
    return ListInput(name=name, items=tuple(ListItem(uri=uri) for uri in uris))


class TestPuttingThemIntoCells:
    FILE_A = ListItem(uri="https://h/a")
    FILE_B = ListItem(uri="https://h/b")
    FOLDER = _list("Folder", "https://h/1", "https://h/2")

    def test_a_cell_each_for_files_folders_and_lists(self):
        groups = [self.FILE_A, self.FOLDER, self.FILE_B]

        assert plan_cells(groups, AddMode.CELL_EACH) == groups

    def test_all_in_one_cell(self):
        (cell,) = plan_cells([self.FILE_A, self.FOLDER], AddMode.ONE_CELL)

        assert [item.uri for item in cell.items] == [
            "https://h/a",
            "https://h/1",
            "https://h/2",
        ]

    @pytest.mark.parametrize(
        ("mode", "cells"),
        [
            (AddMode.CELL_EACH, 3),
            (AddMode.ONE_CELL, 1),
            (AddMode.CELL_PER_FILE, 4),
        ],
    )
    def test_counted_as_they_would_be_put(self, mode, cells):
        groups = [self.FILE_A, self.FOLDER, self.FILE_B]

        assert count_cells(groups, mode) == cells == len(plan_cells(groups, mode))

    def test_none_for_nothing(self):
        assert count_cells([], AddMode.ONE_CELL) == 0

    def test_all_in_one_cell_for_one_list_is_that_list(self):
        assert plan_cells([self.FOLDER], AddMode.ONE_CELL) == [self.FOLDER]

    def test_all_in_one_cell_named_after_the_first_files_folder(self, tmp_path):
        a, b = _touch(tmp_path / "Shows", "a.mp4", "b.mp4")

        (cell,) = plan_cells([ListItem(uri=a), ListItem(uri=b)], AddMode.ONE_CELL)

        assert cell.name == "Shows"

    def test_a_cell_for_every_file_spreads_the_lists(self):
        cells = plan_cells([self.FILE_A, self.FOLDER], AddMode.CELL_PER_FILE)

        assert [cell.uri for cell in cells] == [
            "https://h/a",
            "https://h/1",
            "https://h/2",
        ]

    def test_one_file_is_no_question(self):
        assert choices_for([self.FILE_A]) == [AddMode.CELL_EACH]

    def test_one_list_could_be_spread(self):
        assert choices_for([self.FOLDER]) == [AddMode.CELL_EACH, AddMode.CELL_PER_FILE]

    def test_several_files_could_be_one_cell(self):
        assert choices_for([self.FILE_A, self.FILE_B]) == [
            AddMode.CELL_EACH,
            AddMode.ONE_CELL,
        ]

    def test_files_and_a_list_could_be_any_way(self):
        assert choices_for([self.FILE_A, self.FOLDER]) == [
            AddMode.CELL_EACH,
            AddMode.ONE_CELL,
            AddMode.CELL_PER_FILE,
        ]

    def test_a_list_is_remembered_by_where_it_was_read_from(self, tmp_path):
        _touch(tmp_path, "f/a.mp4")
        groups = _expand([tmp_path / "f", "https://h/x"]).groups

        assert recent_uris(groups) == [tmp_path / "f", "https://h/x"]
