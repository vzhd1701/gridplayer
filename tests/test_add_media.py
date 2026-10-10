"""Files, folders and lists added or dropped, put into cells the way the
playlist says or the viewer picks."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QDialog, QWidget

from gridplayer.models.media_list import (
    HttpHeaders,
    ListItem,
    ListSource,
    MediaList,
)
from gridplayer.models.video import Video
from gridplayer.params.static import AddMode, ListSourceKind, VideoEndAction
from gridplayer.player.managers import add_videos
from gridplayer.player.managers.add_videos import AddVideosManager
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils import list_progress
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.list_progress import ReadingEnough
from gridplayer.utils.media_import import Expanded, ListInput, expand_inputs
from gridplayer.utils.next_file import MAX_MISSING_FILES


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings
    PlaylistSettings().clear()


def _touch(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        files.append(path)

    return files


_STEPPING = {
    VideoEndAction.NEXT_FILE,
    VideoEndAction.PREVIOUS_FILE,
    VideoEndAction.SHUFFLE_FILE,
}


class _Cell:
    """A cell put in the grid: what the manager tells a cell waiting for its
    list is made on its video, as the cell would."""

    def __init__(self, video, lists):
        self.video_params = video
        self.is_closing = False
        self._lists = lists

    def take_list(self, list_id, index):
        self.video_params.list_id = list_id
        self.video_params.list_index = index

        if self.video_params.end_action not in _STEPPING:
            self.video_params.end_action = VideoEndAction.NEXT_FILE

    def play_list_item(self, index):
        media_list = self._lists.get(self.video_params.list_id)
        self.video_params.uri = media_list.items[index].uri
        self.video_params.list_index = index

    def play_read(self, uri):
        self.video_params.uri = uri

    def close(self):
        self.is_closing = True


class _Grid:
    """Takes every video added, up to how many it has room for."""

    def __init__(self, room=None):
        self.room = room
        self.placed = {}
        self.lists = None

    def take(self, videos):
        for video in videos:
            if self.room is not None and len(self.placed) >= self.room:
                return
            self.placed[str(video.id)] = _Cell(video, self.lists)

    def cell_of(self, video):
        return self.placed.get(str(video.id))


@pytest.fixture
def grid():
    return _Grid()


@pytest.fixture
def manager(grid):
    parent = QWidget()
    commands = MagicMock()
    commands.grid_free_capacity.return_value = None
    commands.layout_drop.side_effect = lambda videos, *_args: grid.take(videos)

    ctx = SimpleNamespace(
        commands=commands,
        lists=MediaListsRegistry(),
        video_blocks=SimpleNamespace(by_video_id=lambda _id: grid.placed.get(str(_id))),
    )
    grid.lists = ctx.lists

    manager = AddVideosManager(context=ctx, parent=parent)
    manager.kept_parent = parent

    manager.added = []
    manager.videos_added.connect(manager.added.append)
    manager.videos_added.connect(grid.take)

    manager.errors = []
    manager.error.connect(manager.errors.append)
    manager.warnings = []
    manager.warning.connect(manager.warnings.append)

    return manager


def _wait_for_reading(manager, timeout=5):
    deadline = time.monotonic() + timeout

    while manager._is_reading or manager._requests or manager.cells_reading:
        if time.monotonic() > deadline:
            raise TimeoutError

        QApplication.processEvents()
        time.sleep(0.01)


def _add(manager, uris, **kwargs):
    manager.add_media(uris, **kwargs)
    _wait_for_reading(manager)

    return [video for batch in manager.added for video in batch]


def _list_of(manager, video):
    return manager._ctx.lists.get(video.list_id)


class TestFiles:
    def test_each_in_a_cell_of_its_own(self, manager, tmp_path):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")

        videos = _add(manager, [a, b])

        assert [video.uri for video in videos] == [a, b]
        assert all(video.list_id is None for video in videos)

    def test_a_link_too(self, manager):
        (video,) = _add(manager, ["https://host/a.mp4"])

        assert video.uri == "https://host/a.mp4"

    def test_remembered_as_recent(self, manager, tmp_path):
        (a,) = _touch(tmp_path, "a.mp4")

        _add(manager, [a])

        manager._ctx.commands.add_recent_uris.assert_called_once_with([a])

    def test_one_that_is_gone_tells_so(self, manager, tmp_path):
        _add(manager, [tmp_path / "gone.mp4"])

        assert manager.added == []
        assert manager.errors

    def test_and_is_not_remembered_as_recent(self, manager, tmp_path):
        _add(manager, [tmp_path / "gone.mp4"])

        manager._ctx.commands.add_recent_uris.assert_not_called()

    def test_nor_beside_one_that_is_there(self, manager, tmp_path):
        (a,) = _touch(tmp_path, "a.mp4")

        _add(manager, [a, tmp_path / "gone.mp4"])

        manager._ctx.commands.add_recent_uris.assert_called_once_with([a])


class TestAFolder:
    def test_plays_in_one_cell(self, manager, tmp_path):
        files = _touch(tmp_path / "Shows", "1.mkv", "2.mkv")

        (video,) = _add(manager, [tmp_path / "Shows"])

        media_list = _list_of(manager, video)
        assert media_list.name == "Shows"
        assert [item.uri for item in media_list.items] == files
        assert video.uri == files[0]
        assert video.list_index == 0

    def test_its_cell_goes_on_to_the_next_at_the_end(self, manager, tmp_path):
        _touch(tmp_path / "Shows", "1.mkv")

        (video,) = _add(manager, [tmp_path / "Shows"])

        assert video.end_action is VideoEndAction.NEXT_FILE

    def test_unless_set_to_go_along_another_way(self, manager, tmp_path):
        PlaylistSettings().set("video_defaults/end_action", VideoEndAction.SHUFFLE_FILE)
        _touch(tmp_path / "Shows", "1.mkv")

        (video,) = _add(manager, [tmp_path / "Shows"])

        assert video.end_action is VideoEndAction.SHUFFLE_FILE

    def test_remembered_as_recent_by_the_folder(self, manager, tmp_path):
        _touch(tmp_path / "Shows", "1.mkv")

        _add(manager, [tmp_path / "Shows"])

        manager._ctx.commands.add_recent_uris.assert_called_once_with(
            [tmp_path / "Shows"]
        )

    def test_from_its_first_file_there_is(self, manager, tmp_path):
        path = tmp_path / "list.m3u"
        (b,) = _touch(tmp_path, "b.mp4")
        path.write_text("gone.mp4\nb.mp4\n", encoding="utf-8")

        (video,) = _add(manager, [path])

        assert video.uri == b
        assert video.list_index == 1

    def test_with_nothing_to_play_its_cell_goes_and_tells_so(
        self, manager, grid, tmp_path
    ):
        _touch(tmp_path / "Empty", "notes.txt")

        (video,) = _add(manager, [tmp_path / "Empty"])

        assert grid.cell_of(video).is_closing
        assert str(tmp_path / "Empty") in manager.errors[0]

    def test_one_that_could_not_be_read_leaves_the_others(
        self, manager, grid, tmp_path
    ):
        (a,) = _touch(tmp_path, "a.mp4")
        _touch(tmp_path / "Empty", "notes.txt")

        first, second = _add(manager, [a, tmp_path / "Empty"])

        assert first.uri == a
        assert not grid.cell_of(first).is_closing
        assert grid.cell_of(second).is_closing
        assert str(tmp_path / "Empty") in manager.errors[0]

    def test_with_none_of_its_files_there_its_cell_goes(self, manager, grid, tmp_path):
        path = tmp_path / "list.m3u"
        path.write_text("gone.mp4\n", encoding="utf-8")

        (video,) = _add(manager, [path])

        assert grid.cell_of(video).is_closing
        assert manager._ctx.lists.lists() == []

    def test_not_looked_for_past_a_drive_of_them_gone(self, manager, grid, tmp_path):
        path = tmp_path / "list.m3u"
        _touch(tmp_path, "last.mp4")
        gone = "".join(f"gone{n}.mp4\n" for n in range(MAX_MISSING_FILES))
        path.write_text(f"{gone}last.mp4\n", encoding="utf-8")

        (video,) = _add(manager, [path])

        assert grid.cell_of(video).is_closing


class TestACellWaitingForItsList:
    def test_is_there_before_the_list_is_read(self, manager, grid, tmp_path, mocker):
        _touch(tmp_path / "Shows", "1.mkv")
        reading = mocker.patch.object(add_videos._CellReader, "read")

        manager.add_media([tmp_path / "Shows"])

        ((video,),) = manager.added
        assert grid.cell_of(video) is not None
        assert manager._ctx.lists.is_waiting(video.id)
        assert video.list_id is None
        reading.assert_called_once()

    def test_named_after_where_it_is_read_from(self, manager, tmp_path, mocker):
        _touch(tmp_path / "Shows", "1.mkv")
        mocker.patch.object(add_videos._CellReader, "read")

        manager.add_media([tmp_path / "Shows"])

        ((video,),) = manager.added
        assert video.uri_name == str(tmp_path / "Shows")

    def test_told_how_far_reading_has_got(self, manager, tmp_path, mocker):
        mocker.patch.object(add_videos._CellReader, "read")
        manager.add_media(["http://tv/get.php?type=m3u_plus"])
        ((video,),) = manager.added
        told = []
        manager._ctx.lists.waiting_progress.connect(
            lambda video_id, text, percent: told.append((video_id, text, percent))
        )

        manager._tell_cell(video.id, "items", 45000, 30)

        assert told == [(video.id, "Reading the list… 45,000 items", 30)]

    @pytest.mark.parametrize(
        ("what", "count", "of", "told"),
        [
            (
                "bytes",
                12_300_000,
                45_300_000,
                ("Downloading the list… 12.3 MB of 45.3 MB", 27),
            ),
            ("bytes", 12_300_000, None, ("Downloading the list… 12.3 MB", 0)),
            ("items", 2000, None, ("Reading the list… 2,000 items", 0)),
            ("items", 2000, 40, ("Reading the list… 2,000 items", 40)),
        ],
    )
    def test_said_as_far_as_it_is_known(self, what, count, of, told):
        assert list_progress.reading_txt(what, count, of) == told

    def test_no_longer_waiting_once_read(self, manager, tmp_path):
        _touch(tmp_path / "Shows", "1.mkv")

        (video,) = _add(manager, [tmp_path / "Shows"])

        assert not manager._ctx.lists.is_waiting(video.id)

    def test_closed_meanwhile_is_left_be(self, manager, grid, tmp_path):
        _touch(tmp_path / "Shows", "1.mkv")
        manager.add_media([tmp_path / "Shows"])
        ((video,),) = manager.added
        del grid.placed[str(video.id)]

        _wait_for_reading(manager)

        assert manager._ctx.lists.lists() == []
        assert video.list_id is None

    def test_says_so_should_the_playlist_be_saved(self, manager, tmp_path, mocker):
        _touch(tmp_path / "Shows", "1.mkv")
        mocker.patch.object(add_videos._CellReader, "read")

        manager.add_media([tmp_path / "Shows"])

        ((video,),) = manager.added
        assert video.read_as_list

    def test_and_no_more_once_read(self, manager, tmp_path):
        _touch(tmp_path / "Shows", "1.mkv")

        (video,) = _add(manager, [tmp_path / "Shows"])

        assert video.read_as_list is None
        assert video.list_id is not None

    def test_closed_its_list_is_read_no_further(self, manager, mocker):
        reading = threading.Event()

        def _expand(uris, rules, progress=None, **kwargs):
            while True:
                # stopped, this says so
                progress("items", 1, None)
                reading.set()
                time.sleep(0.01)

        mocker.patch.object(add_videos, "expand_inputs", side_effect=_expand)
        manager.add_media(["http://tv/get.php?type=m3u_plus"])
        ((video,),) = manager.added
        assert reading.wait(5)

        # as the cell closes
        manager._ctx.lists.stop_waiting(video.id)
        _wait_for_reading(manager)

        assert manager.errors == []

    def test_one_saved_as_it_waited_is_read_again(self, manager, grid, tmp_path):
        _touch(tmp_path / "Shows", "1.mkv")
        video = Video(uri=str(tmp_path / "Shows"), read_as_list=True)
        grid.take([video])

        manager.read_for_cell(video)

        assert manager._ctx.lists.is_waiting(video.id)

        _wait_for_reading(manager)

        assert video.uri == tmp_path / "Shows" / "1.mkv"
        assert video.read_as_list is None

    def test_one_turned_away_by_a_full_grid_is_not_read(
        self, manager, grid, tmp_path, mocker
    ):
        grid.room = 0
        _touch(tmp_path / "Shows", "1.mkv")
        reading = mocker.patch.object(add_videos._CellReader, "read")

        manager.add_media([tmp_path / "Shows"])

        reading.assert_not_called()
        assert manager.cells_reading == 0

    def test_a_link_that_turns_out_to_be_one_video_plays_it(self, manager, mocker):
        mocker.patch.object(
            add_videos,
            "fetch_list_url",
            return_value=b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nseg0.ts\n",
        )
        url = "http://tv/live/index.m3u8"

        (video,) = _add(manager, [url])

        assert video.uri == url
        assert video.list_id is None


class TestALinkToAList:
    @pytest.fixture
    def served(self, mocker):
        """What the link answers with, as fetched a chunk at a time."""

        served = {"body": b"", "read": 0}

        def fetch_capped(session, url, limit, on_read=None, keep_reading=None):
            read = bytearray()
            for start in range(0, len(served["body"]), 16 * 1024):
                read += served["body"][start : start + 16 * 1024]
                served["read"] = len(read)
                if len(read) >= limit:
                    break
                if keep_reading is not None and not keep_reading(read):
                    break
            return 200, bytes(read[:limit])

        mocker.patch("gridplayer.utils.network.fetch_capped", side_effect=fetch_capped)
        mocker.patch("gridplayer.utils.network.configure_session")

        return served

    def test_is_read_whole(self, served):
        served["body"] = b"#EXTM3U\n" + b"http://h/1\n" * 20000

        assert add_videos.fetch_list_url("http://h/l.m3u") == served["body"]

    def test_what_is_no_list_is_read_only_far_enough_to_tell(self, served):
        served["body"] = b"\x47" * (4 * 1024 * 1024)

        data = add_videos.fetch_list_url("http://h/live.m3u")

        assert len(data) < 128 * 1024
        assert served["read"] < 128 * 1024

    def test_told_a_list_once(self, served, mocker):
        served["body"] = b"#EXTM3U\n" + b"http://h/1\n" * 40000
        looked = mocker.spy(add_videos, "looks_like_list")

        add_videos.fetch_list_url("http://h/l.m3u")

        assert looked.call_count == 1

    def test_one_larger_than_set_is_not_read(self, served):
        served["body"] = b"#EXTM3U\n" + b"http://h/1\n" * 200_000

        with pytest.raises(ValueError, match="larger than 1 MB"):
            add_videos.fetch_list_url("http://h/l.m3u", max_bytes=2**20)

    def test_the_largest_is_as_set_for_the_app(self):
        Settings().set("player/list_max_mb", 64)

        assert add_videos.list_read_limit() == 64 * 2**20

    def test_a_playlist_has_no_say_in_it(self):
        Settings().set("player/list_max_mb", 64)
        PlaylistSettings().set("player/list_max_mb", 4096)

        assert add_videos.list_read_limit() == 64 * 2**20

    def test_512_mb_unless_said_otherwise(self):
        assert add_videos.list_read_limit() == 512 * 2**20


class TestReadingProgress:
    def test_passed_on_now_and_then(self, mocker):
        times = iter([0.0, 0.1, 0.3, 0.35, 0.7])
        mocker.patch.object(
            list_progress.time, "monotonic", side_effect=lambda: next(times)
        )
        told = []
        tell = list_progress.Throttled(lambda what, count, of: told.append(count))

        for count in (1, 2, 3, 4, 5):
            tell("items", count)

        assert told == [1, 3, 5]


class TestTheWayTheyArePutIntoCells:
    @pytest.fixture
    def things(self, tmp_path):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv")

        return [a, b, tmp_path / "Shows"]

    def test_all_in_one_cell(self, manager, things):
        PlaylistSettings().set("playlist/add_mode", AddMode.ONE_CELL)

        (video,) = _add(manager, things)

        assert len(_list_of(manager, video).items) == 4

    def test_a_cell_for_every_file(self, manager, things):
        PlaylistSettings().set("playlist/add_mode", AddMode.CELL_PER_FILE)

        videos = _add(manager, things)

        assert len(videos) == 4
        assert all(video.list_id is None for video in videos)

    def test_a_channel_in_a_cell_of_its_own_keeps_what_to_fetch_it_with(
        self, manager, tmp_path
    ):
        PlaylistSettings().set("playlist/add_mode", AddMode.CELL_PER_FILE)
        path = tmp_path / "tv.m3u"
        path.write_text(
            "#EXTM3U\n"
            "#EXTINF:-1,One\n"
            "#EXTVLCOPT:http-user-agent=Box/1.0\n"
            "#EXTVLCOPT:http-referrer=https://portal.example/\n"
            "http://tv/1\n"
            "#EXTINF:-1,Two\n"
            "http://tv/2\n",
            encoding="utf-8",
        )

        one, two = _add(manager, [path])

        assert one.http_headers == HttpHeaders(
            user_agent="Box/1.0", referrer="https://portal.example/"
        )
        assert two.http_headers is None

    def test_asked_the_viewer_picks(self, manager, things, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(manager, "_ask", return_value=AddMode.ONE_CELL)

        (video,) = _add(manager, things)

        _groups, choices, _target = asked.call_args.args
        assert choices == [AddMode.CELL_EACH, AddMode.ONE_CELL, AddMode.CELL_PER_FILE]
        assert len(_list_of(manager, video).items) == 4

    def test_asked_the_viewer_may_think_better_of_it(self, manager, things, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        mocker.patch.object(manager, "_ask", return_value=None)

        _add(manager, things)

        assert manager.added == []
        assert manager._ctx.lists.lists() == []

    def test_one_file_is_no_question(self, manager, tmp_path, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(manager, "_ask")
        (a,) = _touch(tmp_path, "a.mp4")

        _add(manager, [a])

        asked.assert_not_called()
        assert len(manager.added) == 1


class TestWhatTheViewerIsOffered:
    @pytest.fixture
    def asked(self, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)

        return mocker.patch.object(add_videos.AddChoiceDialog, "ask", return_value=None)

    def _offered(self, asked):
        question, what, options = asked.call_args.args[:3]

        return question, what, [_option_txt(option) for option in options]

    def test_files_folders_and_playlists(self, manager, tmp_path, asked):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv")

        _add(manager, [a, b, tmp_path / "Shows"])

        assert self._offered(asked) == (
            "How should these be added?",
            ["a.mp4", "b.mp4", "Shows — 2 items"],
            [
                (
                    AddMode.CELL_EACH,
                    "A cell for each file, folder and playlist",
                    "A folder or playlist plays as a list.",
                    "3 cells",
                ),
                (
                    AddMode.ONE_CELL,
                    "One cell for everything",
                    "Plays all 4 videos as a list.",
                    "",
                ),
                (
                    AddMode.CELL_PER_FILE,
                    "A cell for each video",
                    "Including videos inside folders and playlists.",
                    "4 cells",
                ),
            ],
        )

    def test_files_alone(self, manager, tmp_path, asked):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")

        _add(manager, [a, b])

        _question, _what, options = self._offered(asked)
        assert options == [
            (AddMode.CELL_EACH, "A cell for each video", "", "2 cells"),
            (
                AddMode.ONE_CELL,
                "One cell for everything",
                "Plays all 2 videos as a list.",
                "",
            ),
        ]

    def test_one_folder(self, manager, tmp_path, asked):
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv", "3.mkv")

        _add(manager, [tmp_path / "Shows"])

        question, what, options = self._offered(asked)
        assert question == "How should this be added?"
        assert what == ["Shows — 3 items"]
        assert options == [
            (AddMode.CELL_EACH, "One cell", "Plays them as a list.", ""),
            (
                AddMode.CELL_PER_FILE,
                "A cell for each video",
                "Including videos inside folders and playlists.",
                "3 cells",
            ),
        ]

    def test_more_cells_than_fit_says_how_many_do(self, manager, tmp_path, asked):
        manager._ctx.commands.grid_free_capacity.return_value = 2
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv", "3.mkv")

        _add(manager, [tmp_path / "Shows"])

        _question, _what, options = self._offered(asked)
        assert options[1][3] == "3 cells, only 2 fit"

    def test_dropped_in_the_middle_of_a_cell_with_a_video(
        self, manager, tmp_path, asked
    ):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        cell = SimpleNamespace(video_params=Video(uri=a), media_list=None)

        _add(manager, [b], drop=(cell, DropZone.CENTER, False))

        _question, _what, options = asked.call_args.args[:3]
        assert [_option_txt(option) if option else None for option in options] == [
            (AddMode.CELL_EACH, "In a cell of its own", "", ""),
            None,
            (
                add_videos._ADD_TO_CELL,
                "Play in this cell, after its video",
                "Makes a list that starts with its video.",
                "",
            ),
        ]

    @pytest.mark.parametrize(
        ("zone", "is_replace"),
        [(DropZone.AFTER, False), (DropZone.ABOVE, False), (DropZone.CENTER, True)],
    )
    def test_one_file_at_its_edge_or_replacing_its_video_is_not_asked_about(
        self, manager, tmp_path, asked, zone, is_replace
    ):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        cell = SimpleNamespace(video_params=Video(uri=a), media_list=None)

        _add(manager, [b], drop=(cell, zone, is_replace))

        asked.assert_not_called()
        videos, _src, at, in_zone, replaced = (
            manager._ctx.commands.layout_drop.call_args.args
        )
        assert [video.uri for video in videos] == [b]
        assert (at, in_zone, replaced) == (cell, zone, is_replace)

    def test_asked_over_the_player(self, manager, tmp_path, asked):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")

        _add(manager, [a, b])

        assert asked.call_args.args[3] is manager.kept_parent


def _option_txt(option):
    return option.data, option.title, option.about, option.note


class TestDropped:
    def test_where_they_were_dropped(self, manager, tmp_path):
        (a,) = _touch(tmp_path, "a.mp4")
        dst, zone = object(), object()

        _add(manager, [a], drop=(dst, zone, True))

        videos, src, at, in_zone, is_replace = (
            manager._ctx.commands.layout_drop.call_args.args
        )
        assert [video.uri for video in videos] == [a]
        assert (src, at, in_zone, is_replace) == (None, dst, zone, True)
        assert manager.added == []

    def test_a_full_grid_turns_a_list_away_and_it_is_not_kept(
        self, manager, grid, tmp_path
    ):
        grid.room = 1
        (a,) = _touch(tmp_path, "a.mp4")
        _touch(tmp_path / "Shows", "1.mkv")

        _add(manager, [a, tmp_path / "Shows"], drop=(None, None, False))

        assert manager._ctx.lists.lists() == []

    def test_onto_a_linked_list_s_cell_one_file_is_not_asked_about(
        self, manager, tmp_path, mocker
    ):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(add_videos.AddChoiceDialog, "ask")
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        media_list = manager._ctx.lists.add(
            MediaList(
                items=[ListItem(uri="http://tv/1")],
                source=ListSource(kind=ListSourceKind.URL, location="http://tv/l"),
                is_linked=True,
            )
        )
        cell = SimpleNamespace(
            video_params=Video(uri=a, list_id=media_list.id), media_list=media_list
        )

        _add(manager, [b], drop=(cell, None, True))

        asked.assert_not_called()
        videos, _src, at, _zone, is_replace = (
            manager._ctx.commands.layout_drop.call_args.args
        )
        assert [video.uri for video in videos] == [b]
        assert (at, is_replace) == (cell, True)

    def test_onto_a_linked_list_s_cell_several_are_asked_about(
        self, manager, tmp_path, mocker
    ):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(manager, "_ask", return_value=None)
        a, b, c = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")
        media_list = manager._ctx.lists.add(
            MediaList(
                items=[ListItem(uri="http://tv/1")],
                source=ListSource(kind=ListSourceKind.URL, location="http://tv/l"),
                is_linked=True,
            )
        )
        cell = SimpleNamespace(
            video_params=Video(uri=a, list_id=media_list.id), media_list=media_list
        )

        _add(manager, [b, c], drop=(cell, DropZone.CENTER, False))

        asked.assert_called_once()
        assert asked.call_args.args[2] is None
        assert manager._ctx.lists.get(media_list.id).items == media_list.items

    def test_in_the_middle_of_a_cell_asked_it_is_offered(
        self, manager, tmp_path, mocker
    ):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(manager, "_ask", return_value=None)
        (a,) = _touch(tmp_path, "a.mp4")
        cell = SimpleNamespace(video_params=Video(uri=a), media_list=None)

        _add(manager, [a], drop=(cell, DropZone.CENTER, False))

        _groups, _choices, target = asked.call_args.args
        assert target is cell


class TestToldAsAdded:
    @pytest.fixture
    def told(self, manager):
        told = []
        manager._ctx.lists.items_added.connect(lambda *args: told.append(args))
        return told

    def test_a_list_made_of_a_folder(self, manager, tmp_path, told):
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv")

        (video,) = _add(manager, [tmp_path / "Shows"])

        media_list = _list_of(manager, video)
        assert told == [(media_list.id, [item.key for item in media_list.items])]

    def test_a_file_alone_on_no_list(self, manager, tmp_path, told):
        (a,) = _touch(tmp_path, "a.mp4")

        _add(manager, [a])

        assert told == []

    def test_what_is_added_to_a_cells_list(self, manager, tmp_path, told):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        media_list = manager._ctx.lists.add(MediaList(items=[ListItem(uri=a)]))
        cell = SimpleNamespace(
            video_params=Video(uri=a, list_id=media_list.id),
            media_list=media_list,
            tell_added_to_list=MagicMock(),
        )

        _add(manager, [b], drop=(cell, DropZone.CENTER, False))

        added = manager._ctx.lists.get(media_list.id).items[-1]
        assert told == [(media_list.id, [added.key])]


class TestAddedToACell:
    def _cell(self, manager, video, media_list=None):
        cell = SimpleNamespace(video_params=video, media_list=media_list)
        cell.take_list = MagicMock()
        cell.tell_added_to_list = MagicMock()

        return cell

    def test_after_what_its_list_has(self, manager, tmp_path):
        a, b, c = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")
        media_list = manager._ctx.lists.add(MediaList(items=[ListItem(uri=a)]))
        cell = self._cell(manager, Video(uri=a, list_id=media_list.id), media_list)

        _add(manager, [b, c], drop=(cell, DropZone.CENTER, False))

        assert [item.uri for item in manager._ctx.lists.get(media_list.id).items] == [
            a,
            b,
            c,
        ]
        assert manager.added == []
        manager._ctx.commands.layout_drop.assert_not_called()

    def test_one_with_no_list_gets_one_its_video_first(self, manager, tmp_path, mocker):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")
        cell = self._cell(manager, Video(uri=a, title="Mine"))
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        mocker.patch.object(manager, "_ask", return_value=add_videos._ADD_TO_CELL)

        _add(manager, [b], drop=(cell, DropZone.CENTER, False))

        (media_list,) = manager._ctx.lists.lists()
        assert [item.uri for item in media_list.items] == [a, b]
        assert media_list.items[0].title == "Mine"
        cell.take_list.assert_called_once_with(media_list.id, 0)
        cell.tell_added_to_list.assert_called_once_with(1)


class TestAListOnASite:
    LIST = "https://www.youtube.com/playlist?list=PL"
    OPENED = "https://www.youtube.com/watch?v=b&list=PL&t=5"

    @pytest.fixture
    def site(self, mocker):
        from gridplayer.models.media_list import ListSource
        from gridplayer.params.static import ListSourceKind
        from gridplayer.utils.media_import import ListInput

        read = []

        def read_web_list(url, progress=None):
            read.append(url)
            return ListInput(
                name="Site",
                items=tuple(ListItem(uri=f"https://h/{n}") for n in "abc"),
                source=ListSource(kind=ListSourceKind.URL, location=url),
                start=1 if "v=b" in url else 0,
            )

        mocker.patch.object(add_videos, "read_web_list", side_effect=read_web_list)

        return read

    def test_plays_in_one_cell(self, manager, site):
        (video,) = _add(manager, [self.LIST])

        assert site == [self.LIST]
        assert _list_of(manager, video).name == "Site"
        assert video.uri == "https://h/a"

    def test_opened_from_a_video_the_viewer_says_which_is_meant(
        self, manager, site, mocker
    ):
        asked = mocker.patch.object(
            add_videos.AddChoiceDialog, "ask", return_value="playlist"
        )

        (video,) = _add(manager, [self.OPENED])

        assert asked.call_count == 1
        assert site == [self.OPENED]
        assert video.uri == "https://h/b"
        assert video.list_index == 1

    def test_the_video_alone(self, manager, site, mocker):
        mocker.patch.object(add_videos.AddChoiceDialog, "ask", return_value="video")

        (video,) = _add(manager, [self.OPENED])

        assert site == []
        assert video.uri == "https://www.youtube.com/watch?v=b&t=5"
        assert video.list_id is None

    def test_or_neither(self, manager, site, mocker):
        mocker.patch.object(add_videos.AddChoiceDialog, "ask", return_value=None)

        _add(manager, [self.OPENED])

        assert site == []
        assert manager.added == []


class TestReadingInTheBackground:
    def test_one_after_the_other_in_the_order_added(self, manager, tmp_path):
        _touch(tmp_path / "First", "1.mkv")
        (b,) = _touch(tmp_path, "b.mp4")

        manager.add_media([tmp_path / "First"])
        manager.add_media([b])
        _wait_for_reading(manager)

        first, second = (batch[0] for batch in manager.added)
        assert first.list_id is not None
        assert second.uri == b

    def test_a_reader_that_blows_up_leaves_nothing_stuck(
        self, manager, tmp_path, mocker
    ):
        mocker.patch.object(add_videos, "expand_inputs", side_effect=RuntimeError("x"))
        _touch(tmp_path / "Shows", "1.mkv")

        manager.add_media([tmp_path / "Shows"])
        _wait_for_reading(manager)

        assert not manager._is_reading
        assert manager.errors
        assert QApplication.overrideCursor() is None


class TestManyCells:
    """More than MANY_CELLS at once, where the playlist says how: warned of,
    and nothing else."""

    @pytest.fixture(autouse=True)
    def many_is_three(self, mocker):
        mocker.patch.object(add_videos, "MANY_CELLS", 3)

    @pytest.fixture
    def warned(self, mocker):
        return mocker.patch.object(
            add_videos.ManyCellsDialog, "ask", return_value=(True, True)
        )

    def test_added_as_the_playlist_says_once_warned(self, manager, tmp_path, warned):
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        videos = _add(manager, files)

        assert warned.call_args.args[0] == 4
        assert len(videos) == 4

    def test_nothing_added_thought_better_of(self, manager, tmp_path, warned):
        warned.return_value = (False, True)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert manager.added == []

    def test_not_asked_how_instead(self, manager, tmp_path, warned, mocker):
        asked = mocker.patch.object(manager, "_ask")
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        asked.assert_not_called()

    def test_as_many_as_that_unwarned(self, manager, tmp_path, warned):
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")

        assert len(_add(manager, files)) == 3
        warned.assert_not_called()

    def test_none_where_the_playlist_says_not_to(self, manager, tmp_path, warned):
        PlaylistSettings().set("playlist/warn_many_cells", False)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        assert len(_add(manager, files)) == 4
        warned.assert_not_called()

    def test_counted_as_far_as_there_is_room(self, manager, tmp_path, warned):
        manager._ctx.commands.grid_free_capacity.return_value = 2
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        warned.assert_not_called()

    def test_one_cell_is_never_many(self, manager, tmp_path, warned):
        PlaylistSettings().set("playlist/add_mode", AddMode.ONE_CELL)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        warned.assert_not_called()

    def test_a_cell_for_each_video_of_a_folder(self, manager, tmp_path, warned):
        PlaylistSettings().set("playlist/add_mode", AddMode.CELL_PER_FILE)
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv", "3.mkv", "4.mkv")
        warned.return_value = (False, True)

        _add(manager, [tmp_path / "Shows"])

        assert warned.call_args.args[0] == 4
        assert manager.added == []

    def test_folders_waited_for_once_warned(self, manager, tmp_path, warned, mocker):
        folders = []
        for name in "ABCD":
            _touch(tmp_path / name, "1.mkv")
            folders.append(tmp_path / name)
        waited = mocker.spy(manager._ctx.lists, "wait_for_list")

        videos = _add(manager, folders)

        assert warned.call_args.args[0] == 4
        assert waited.call_count == 4
        assert len(videos) == 4

    def test_folders_thought_better_of_none_waited_for(
        self, manager, tmp_path, warned, mocker
    ):
        folders = []
        for name in "ABCD":
            _touch(tmp_path / name, "1.mkv")
            folders.append(tmp_path / name)
        waited = mocker.spy(manager._ctx.lists, "wait_for_list")
        warned.return_value = (False, True)

        _add(manager, folders)

        waited.assert_not_called()
        assert manager.added == []

    def test_dont_warn_again_for_this_playlist_and_after(
        self, manager, tmp_path, warned
    ):
        warned.return_value = (True, False)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert Settings().get("playlist/warn_many_cells") is False
        assert PlaylistSettings().get("playlist/warn_many_cells") is False

    def test_dont_warn_again_over_what_the_playlist_said(
        self, manager, tmp_path, warned
    ):
        PlaylistSettings().set("playlist/warn_many_cells", True)
        warned.return_value = (True, False)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert PlaylistSettings().get("playlist/warn_many_cells") is False

    def test_dont_warn_again_only_once_added(self, manager, tmp_path, warned):
        warned.return_value = (False, False)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert Settings().get("playlist/warn_many_cells") is True

    def test_warned_unless_said_otherwise(self):
        PlaylistSettings().clear()

        assert Settings().get("playlist/warn_many_cells") is True


def test_twenty_cells_at_most_unwarned():
    assert add_videos.MANY_CELLS == 20


class TestManyCellsAsked:
    """Asked how: the way that adds many warned of under it, the first way
    picked as ever."""

    @pytest.fixture(autouse=True)
    def asked_mode(self, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        mocker.patch.object(add_videos, "MANY_CELLS", 3)

    @pytest.fixture
    def asked(self, mocker):
        return mocker.patch.object(add_videos.AddChoiceDialog, "ask", return_value=None)

    def _warnings(self, asked):
        return [option.warning for option in asked.call_args.args[2]]

    def test_warned_under_the_way_that_adds_many(self, manager, tmp_path, asked):
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert asked.call_args.args[0] == "How should these be added?"
        assert self._warnings(asked) == [
            "4 cells at once can freeze the player.",
            "",
        ]

    def test_the_first_way_still_the_one_picked(self, manager, tmp_path, asked):
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert "picked" not in asked.call_args.kwargs

    def test_not_warned_again_once_picked(self, manager, tmp_path, asked, mocker):
        asked.return_value = AddMode.CELL_EACH
        warned = mocker.patch.object(add_videos.ManyCellsDialog, "ask")
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        videos = _add(manager, files)

        warned.assert_not_called()
        assert len(videos) == 4

    def test_none_where_there_is_room_for_no_more(self, manager, tmp_path, asked):
        manager._ctx.commands.grid_free_capacity.return_value = 3
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert self._warnings(asked) == ["", ""]

    def test_none_where_the_playlist_says_not_to(self, manager, tmp_path, asked):
        PlaylistSettings().set("playlist/warn_many_cells", False)
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        _add(manager, files)

        assert self._warnings(asked) == ["", ""]

    def test_counts_as_the_language_writes_them(self):
        big = ListInput(
            name="Big",
            items=tuple(ListItem(uri=f"https://h/{n}") for n in range(1500)),
        )

        assert add_videos._name_of(big) == "Big — 1,500 items"
        assert add_videos._mode_option([big], AddMode.CELL_PER_FILE, None).note == (
            "1,500 cells"
        )
        assert add_videos._warned(
            add_videos._mode_option([big], AddMode.CELL_PER_FILE, None), [big], None
        ).warning == ("1,500 cells at once can freeze the player.")


class _SlowFolder:
    """Folders read a file at a time, for as long as they are not let go:
    or until asked to end, with the files found by then, or to stop."""

    def __init__(self):
        self.gate = threading.Event()

    def __call__(self, uris, rules, progress=None, **kwargs):
        if not any(_is_far(uri) for uri in uris):
            return expand_inputs(uris, rules, progress=progress, **kwargs)

        (uri,) = uris
        items = []

        try:
            while not self.gate.is_set():
                items.append(ListItem(uri=f"https://h/{Path(uri).name}/{len(items)}"))
                progress("files", len(items))
                time.sleep(0.002)
        except ReadingEnough:
            pass

        return Expanded(groups=(ListInput(name=Path(uri).name, items=tuple(items)),))


def slow_files_found(manager) -> int:
    told = manager._told
    return 0 if told is None else told[1]


def _is_far(uri) -> bool:
    """Whether a thing added is one of _SlowFolder's."""

    return str(uri).startswith("D:/")


def _wait_until(condition, timeout=5):
    deadline = time.monotonic() + timeout

    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError

        QApplication.processEvents()
        time.sleep(0.005)


class TestShownAsItIsRead:
    @pytest.fixture
    def slow(self, manager, mocker):
        slow = _SlowFolder()
        mocker.patch.object(add_videos, "expand_inputs", side_effect=slow)
        mocker.patch.object(add_videos, "_is_read_slowly", side_effect=_is_far)
        manager._show_reading_timer.setInterval(0)

        yield slow

        # nothing left up, or still read, for the tests after it: a dialog
        # left open is one the player's drags make way for
        if manager._dialog is not None:
            manager._dialog.reject()
        slow.gate.set()
        _wait_for_reading(manager)

    @pytest.fixture
    def asked_mode(self):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)

    def _dialog(self, manager):
        _wait_until(lambda: manager._dialog is not None)
        return manager._dialog

    @pytest.mark.usefixtures("asked_mode")
    def test_up_saying_how_far_it_has_got(self, manager, slow):
        manager.add_media(["D:/Big"])

        dialog = self._dialog(manager)
        told = []
        dialog.tell_reading = lambda text, percent=0: told.append(text)

        _wait_until(lambda: told)
        assert told[-1].startswith("Scanning folder…")
        assert dialog.is_reading
        assert dialog.parent() is manager.kept_parent
        assert QApplication.overrideCursor() is None

    @pytest.mark.usefixtures("asked_mode")
    def test_up_saying_how_far_it_had_got_before(self, manager, mocker):
        mocker.patch.object(add_videos.AddChoiceDialog, "open")
        told = mocker.spy(add_videos.AddChoiceDialog, "tell_reading")
        manager._reading = add_videos._Reading(add_videos._Request(["D:/Big"], None))

        manager._tell_reading("files", 25700)
        manager._show_reading()

        assert told.call_args.args[1:] == (
            "Scanning folder… 25,700 files",
            0,
        )
        manager._close_dialog()

    @pytest.mark.usefixtures("asked_mode")
    def test_asked_once_read(self, manager, slow, mocker):
        manager.add_media(["D:/Big"])
        dialog = self._dialog(manager)
        asked = mocker.spy(dialog, "set_question")

        slow.gate.set()
        _wait_until(lambda: asked.called)

        question, what, _options = asked.call_args.args[:3]
        assert question == "How should this be added?"
        assert what[0].startswith("Big — ")
        assert manager.added == []

        dialog.done(QDialog.Accepted)
        _wait_for_reading(manager)

        (batch,) = manager.added
        assert len(batch) == 1

    @pytest.mark.usefixtures("asked_mode")
    def test_stopped_asked_about_what_was_found_by_then(self, manager, slow, mocker):
        manager.add_media(["D:/Big", "D:/Bigger"])
        dialog = self._dialog(manager)
        asked = mocker.spy(dialog, "set_question")

        dialog.stop_asked.emit()
        _wait_until(lambda: asked.called)

        # the second never read
        _question, what, _options = asked.call_args.args[:3]
        assert len(what) == 1
        assert what[0].startswith("Big — ")

    @pytest.mark.usefixtures("asked_mode")
    def test_thought_better_of_nothing_added(self, manager, slow):
        manager.add_media(["D:/Big"])
        dialog = self._dialog(manager)

        dialog.reject()
        _wait_for_reading(manager)

        assert manager.added == []
        assert manager.errors == []
        assert manager._dialog is None

    @pytest.mark.usefixtures("asked_mode")
    def test_what_was_added_next_goes_on_once_it_has(self, manager, slow, tmp_path):
        (b,) = _touch(tmp_path, "b.mp4")
        manager.add_media(["D:/Big"])
        dialog = self._dialog(manager)

        manager.add_media([b])
        dialog.reject()
        _wait_for_reading(manager)

        ((video,),) = manager.added
        assert video.uri == b

    def test_put_in_once_read_where_nothing_is_asked(self, manager, slow):
        PlaylistSettings().set("playlist/add_mode", AddMode.CELL_PER_FILE)
        PlaylistSettings().set("playlist/warn_many_cells", False)
        manager.add_media(["D:/Big"])
        dialog = self._dialog(manager)
        assert dialog.is_reading

        slow.gate.set()
        _wait_for_reading(manager)

        assert manager._dialog is None
        assert manager.added

    def test_warned_once_read_the_dialog_out_of_the_way(self, manager, slow, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.CELL_PER_FILE)
        mocker.patch.object(add_videos, "MANY_CELLS", 3)
        up_when_warned = []

        def warned(count, parent=None):
            up_when_warned.append(manager._dialog)
            return False, True

        mocker.patch.object(add_videos.ManyCellsDialog, "ask", side_effect=warned)
        manager.add_media(["D:/Big"])
        self._dialog(manager)
        _wait_until(lambda: slow_files_found(manager) > 3)

        slow.gate.set()
        _wait_for_reading(manager)

        assert up_when_warned == [None]
        assert manager.added == []

    @pytest.mark.usefixtures("asked_mode")
    def test_stopped_before_anything_was_found_nothing_said(self, manager, mocker):
        def nothing_yet(uris, rules, progress=None, **kwargs):
            while True:
                try:
                    progress("files", 0)
                except ReadingEnough:
                    return Expanded()
                time.sleep(0.002)

        mocker.patch.object(add_videos, "expand_inputs", side_effect=nothing_yet)
        mocker.patch.object(add_videos, "_is_read_slowly", side_effect=_is_far)
        manager._show_reading_timer.setInterval(0)
        manager.add_media(["D:/Big"])
        dialog = self._dialog(manager)

        dialog.stop_asked.emit()
        _wait_for_reading(manager)

        assert manager.errors == []
        assert manager._dialog is None

    @pytest.mark.usefixtures("asked_mode")
    def test_read_quickly_asked_without_it(self, manager, tmp_path, mocker):
        asked = mocker.patch.object(manager, "_ask", return_value=None)
        _touch(tmp_path / "Shows", "1.mkv", "2.mkv")

        _add(manager, [tmp_path / "Shows"])

        asked.assert_called_once()
        assert manager._dialog is None


class TestHowFarReadingHasGot:
    def test_counted_over_all_that_is_added(self, manager, tmp_path, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        mocker.patch.object(manager, "_ask", return_value=None)
        _touch(tmp_path / "A", "1.mkv", "2.mkv")
        _touch(tmp_path / "B", "1.mkv", "2.mkv", "3.mkv")
        told = []
        manager._reader.progress.connect(lambda *args: told.append(args))

        _add(manager, [tmp_path / "A", tmp_path / "B"])

        assert told == [("files", 2, None), ("files", 5, None)]


class TestDroppedInTheMiddleOfAList:
    """Files dropped in the middle of a cell playing a list go on its list,
    as the mark there shows; at an edge, or to replace its video, they go
    as anywhere else."""

    @pytest.fixture
    def cell(self, manager, tmp_path):
        (a,) = _touch(tmp_path, "a.mp4")
        media_list = manager._ctx.lists.add(MediaList(items=[ListItem(uri=a)]))

        return SimpleNamespace(
            video_params=Video(uri=a, list_id=media_list.id),
            media_list=media_list,
            tell_added_to_list=MagicMock(),
        )

    def _items(self, manager, cell):
        return [item.uri for item in manager._ctx.lists.get(cell.media_list.id).items]

    @pytest.mark.parametrize("mode", list(AddMode))
    def test_on_its_list_unasked_however_the_playlist_adds(
        self, manager, tmp_path, cell, mocker, mode
    ):
        PlaylistSettings().set("playlist/add_mode", mode)
        asked = mocker.patch.object(add_videos.AddChoiceDialog, "ask")
        b, c = _touch(tmp_path, "b.mp4", "c.mp4")

        _add(manager, [b, c], drop=(cell, DropZone.CENTER, False))

        asked.assert_not_called()
        assert self._items(manager, cell)[1:] == [b, c]
        manager._ctx.commands.layout_drop.assert_not_called()
        cell.tell_added_to_list.assert_called_once_with(2)

    def test_a_folder_too_with_no_cell_put_in_to_wait_for_it(
        self, manager, tmp_path, cell
    ):
        PlaylistSettings().set("playlist/add_mode", AddMode.CELL_EACH)
        files = _touch(tmp_path / "Shows", "1.mkv", "2.mkv")

        _add(manager, [tmp_path / "Shows"], drop=(cell, DropZone.CENTER, False))

        assert self._items(manager, cell)[1:] == list(files)
        manager._ctx.commands.layout_drop.assert_not_called()
        cell.tell_added_to_list.assert_called_once_with(2)

    @pytest.mark.parametrize("zone", [DropZone.BEFORE, DropZone.BELOW])
    def test_at_its_edge_in_a_cell_of_its_own(self, manager, tmp_path, cell, zone):
        (b,) = _touch(tmp_path, "b.mp4")

        _add(manager, [b], drop=(cell, zone, False))

        videos, _src, at, in_zone, is_replace = (
            manager._ctx.commands.layout_drop.call_args.args
        )
        assert [video.uri for video in videos] == [b]
        assert (at, in_zone, is_replace) == (cell, zone, False)
        assert len(self._items(manager, cell)) == 1
        cell.tell_added_to_list.assert_not_called()

    def test_at_its_edge_asked_its_list_is_not_offered(
        self, manager, tmp_path, cell, mocker
    ):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(manager, "_ask", return_value=None)
        b, c = _touch(tmp_path, "b.mp4", "c.mp4")

        _add(manager, [b, c], drop=(cell, DropZone.AFTER, False))

        _groups, _choices, target = asked.call_args.args
        assert target is None

    def test_to_replace_its_video_in_its_place(self, manager, tmp_path, cell, mocker):
        PlaylistSettings().set("playlist/add_mode", AddMode.ASK)
        asked = mocker.patch.object(add_videos.AddChoiceDialog, "ask")
        (b,) = _touch(tmp_path, "b.mp4")

        _add(manager, [b], drop=(cell, DropZone.CENTER, True))

        asked.assert_not_called()
        videos, _src, at, _zone, is_replace = (
            manager._ctx.commands.layout_drop.call_args.args
        )
        assert [video.uri for video in videos] == [b]
        assert (at, is_replace) == (cell, True)
        assert len(self._items(manager, cell)) == 1
