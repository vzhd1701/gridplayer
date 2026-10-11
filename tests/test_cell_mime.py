"""A cell dragged: what it says of itself at once, and the list it plays
from only for another player that asks; read back as it was, paths and
links alike."""

from pathlib import Path

import pytest
from PyQt5.QtCore import QMimeData, QUrl
from PyQt5.QtWidgets import QApplication

from gridplayer.models.media_list import ListItem, ListSource, MediaList
from gridplayer.models.video import Video, VideoBlockMime
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.files import (
    LIST_MIME,
    VIDEO_MIME,
    cell_mime_data,
    extract_mime_list,
    extract_mime_uris,
    extract_mime_video,
)

ROOT = Path("/shows")


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def channels():
    return MediaList(
        name="Channels",
        items=(ListItem(uri=ROOT / "a.mkv"), ListItem(uri="http://tv/1")),
        source=ListSource(kind=ListSourceKind.FILE, location=ROOT / "tv.m3u"),
        removed=(ROOT / "gone.mkv", "http://tv/2"),
    )


def _drag(media_list):
    video = Video(
        uri="http://tv/1", list_id=None if media_list is None else media_list.id
    )
    return cell_mime_data(VideoBlockMime(id="cell", video=video), media_list)


class TestTheCell:
    def test_read_back(self, channels):
        dropped = extract_mime_video(_drag(channels))

        assert dropped.id == "cell"
        assert dropped.video.uri == "http://tv/1"

    def test_without_its_list(self, channels):
        assert b"Channels" not in bytes(_drag(channels).data(VIDEO_MIME))

    def test_one_that_makes_no_sense_is_none(self):
        mime_data = QMimeData()
        mime_data.setData(VIDEO_MIME, b'{"id": 1, "video": "nothing"}')

        assert extract_mime_video(mime_data) is None

    def test_none_for_what_is_no_cell(self):
        mime_data = QMimeData()
        mime_data.setText("http://tv/1")

        assert extract_mime_video(mime_data) is None


class TestItsList:
    def test_offered(self, channels):
        mime_data = _drag(channels)

        assert LIST_MIME in mime_data.formats()
        assert mime_data.hasFormat(LIST_MIME)

    def test_not_for_a_cell_with_none(self):
        mime_data = _drag(None)

        assert LIST_MIME not in mime_data.formats()
        assert not mime_data.hasFormat(LIST_MIME)
        assert extract_mime_list(mime_data) is None

    def test_written_only_once_asked_for(self, channels, mocker):
        dumped = mocker.spy(MediaList, "model_dump_json")

        mime_data = _drag(channels)
        extract_mime_video(mime_data)
        assert dumped.call_count == 0

        extract_mime_list(mime_data)
        extract_mime_list(mime_data)
        assert dumped.call_count == 1

    def test_read_back_as_it_was(self, channels):
        read = extract_mime_list(_drag(channels))

        assert read.name == "Channels"
        assert read.source == channels.source
        assert read.removed == (ROOT / "gone.mkv", "http://tv/2")
        assert [item.uri for item in read.items] == [ROOT / "a.mkv", "http://tv/1"]
        assert isinstance(read.items[0].uri, Path)
        assert isinstance(read.items[1].uri, str)

    def test_one_that_makes_no_sense_is_none(self):
        mime_data = QMimeData()
        mime_data.setData(LIST_MIME, b'{"items": 5}')

        assert extract_mime_list(mime_data) is None


@pytest.mark.parametrize(
    "location",
    [ROOT / "tv.m3u", "http://tv/get.php?type=m3u_plus"],
)
def test_where_a_list_came_from_read_back_from_text(location):
    kind = ListSourceKind.URL if isinstance(location, str) else ListSourceKind.FILE
    source = ListSource(kind=kind, location=location)

    assert ListSource.model_validate_json(source.model_dump_json()) == source


def test_an_item_read_back_from_text_is_a_path_or_a_link():
    assert ListItem.model_validate_json('{"uri": "http://tv/1"}').uri == "http://tv/1"
    assert ListItem.model_validate_json('{"uri": "/shows/a.mkv"}').uri == Path(
        "/shows/a.mkv"
    )


class TestFilesDropped:
    @pytest.fixture
    def folder(self, tmp_path):
        for name in ("a.mkv", "b.MP3", "c.m3u", "d.gpls", "notes.txt", "photo.jpg"):
            (tmp_path / name).write_bytes(b"")
        (tmp_path / "no_extension").write_bytes(b"")
        (tmp_path / "sub").mkdir()
        return tmp_path

    def _dropped(self, paths):
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        return [Path(uri).name for uri in extract_mime_uris(mime_data)]

    def test_media_lists_playlists_and_folders_taken(self, folder):
        names = ("a.mkv", "b.MP3", "c.m3u", "d.gpls", "sub")

        assert self._dropped(folder / name for name in names) == list(names)

    @pytest.mark.parametrize("name", ["notes.txt", "photo.jpg", "no_extension"])
    def test_other_files_left_out(self, folder, name):
        assert self._dropped([folder / name]) == []

    def test_left_out_from_among_the_rest(self, folder):
        assert self._dropped([folder / "notes.txt", folder / "a.mkv"]) == ["a.mkv"]

    def test_missing_file_left_out(self, folder):
        assert self._dropped([folder / "gone.mkv"]) == []

    def test_links_taken_whatever_they_end_in(self):
        mime_data = QMimeData()
        mime_data.setText("http://tv/notes.txt\nhttps://youtu.be/x")

        assert extract_mime_uris(mime_data) == [
            "http://tv/notes.txt",
            "https://youtu.be/x",
        ]
