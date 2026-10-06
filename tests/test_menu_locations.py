"""The File and URL submenus, and copying every video's location at once."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtWidgets import QApplication

from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.player.managers.locations import LocationsManager
from gridplayer.utils import show_in_folder
from gridplayer.utils.show_in_folder import FolderRevealer, existing_place
from gridplayer.utils.url_at_time import url_at_time
from gridplayer.widgets.keymap_tree_view import DATA_ACTION_ID, fill_keymap_model

FILE_ACTIONS = ("Copy File Name", "Copy File Path", "Show in Folder")
URL_ACTIONS = ("Copy URL", "Copy URL at Current Time", "Open in Browser")
ALL_ACTION = "Copy Paths and URLs [ALL]"

ICONS = Path(__file__).parent.parent / "gridplayer" / "resources" / "icons"

FILE = Path(__file__).resolve()
STREAM = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _names(items):
    return [item[0] if isinstance(item, tuple) else item for item in items]


def _submenu(items, *path):
    for name in path:
        items = next(i for i in items if isinstance(i, tuple) and i[0] == name)[1:]

    return list(items)


def _block(uri, *, time_ms=0, is_initialized=True, is_live=False, youtube_id=None):
    return SimpleNamespace(
        video_params=SimpleNamespace(uri=uri),
        is_video_initialized=is_initialized,
        is_live=is_live,
        time=time_ms,
        youtube_id=youtube_id,
    )


def _manager(active=None, blocks=(), order=None):
    blocks = list(blocks)
    ids = [str(n) for n in range(len(blocks))]
    by_id = dict(zip(ids, blocks, strict=True))

    ctx = SimpleNamespace(
        active_block=active,
        video_blocks=SimpleNamespace(
            blocks_for_ids=lambda video_ids: [by_id[i] for i in video_ids]
        ),
        commands=SimpleNamespace(layout_order=lambda: order or ids),
    )

    manager = LocationsManager(context=ctx)
    manager._revealer = Mock()

    return manager


@pytest.fixture
def clipboard():
    board = QApplication.clipboard()
    board.setText("untouched")

    return board


class TestWhereTheyAre:
    def test_both_submenus_sit_between_stream_quality_and_rename(self):
        names = _names(SECTIONS["video_active"])

        at = names.index("Stream Quality")

        assert names[at : at + 4] == ["Stream Quality", "File", "URL", "Rename"]

    def test_the_file_submenu_copies_then_shows(self):
        assert _submenu(SECTIONS["video_active"], "File") == [
            "Copy File Name",
            "Copy File Path",
            "---",
            "Show in Folder",
        ]

    def test_the_url_submenu_copies_then_opens(self):
        assert _submenu(SECTIONS["video_active"], "URL") == [
            "Copy URL",
            "Copy URL at Current Time",
            "---",
            "Open in Browser",
        ]

    def test_copying_them_all_ends_the_all_menu_after_reloading(self):
        everything = _submenu(SECTIONS["video_all"], "[ALL]")

        assert everything[-4:] == [
            "Reload [ALL]",
            "Auto Reload [ALL]",
            "---",
            ALL_ACTION,
        ]

    def test_only_one_of_the_submenus_shows_for_a_video(self):
        assert {ACTIONS[a]["show_if"] for a in FILE_ACTIONS} == {"is_active_file"}
        assert [ACTIONS[a]["show_if"] for a in URL_ACTIONS] == [
            "is_active_url",
            "is_active_url_at_time",
            "is_active_web_url",
        ]

    def test_none_has_a_key_of_its_own(self):
        for action in (*FILE_ACTIONS, *URL_ACTIONS, ALL_ACTION):
            assert "key" not in ACTIONS[action]
            assert "keys" not in ACTIONS[action]

    def test_every_one_can_be_given_a_key(self):
        model = QStandardItemModel()
        fill_keymap_model(model)

        action_ids = set()
        pending = [model.item(row) for row in range(model.rowCount())]

        while pending:
            item = pending.pop()
            action_ids.add(item.data(DATA_ACTION_ID))
            pending += [item.child(row) for row in range(item.rowCount())]

        assert {*FILE_ACTIONS, *URL_ACTIONS, ALL_ACTION} <= action_ids

    def test_every_icon_is_drawn_in_both_themes(self):
        icon_ids = {ACTIONS[a]["icon"] for a in (*FILE_ACTIONS, *URL_ACTIONS)}
        icon_ids |= {SUBMENUS["File"]["icon"], SUBMENUS["URL"]["icon"]}

        for icon_id in icon_ids:
            for theme in ("light", "dark"):
                assert (ICONS / theme / "scalable" / f"{icon_id}.svg").is_file(), (
                    icon_id,
                    theme,
                )


class TestWhichShows:
    def test_a_file_shows_the_file_items(self):
        manager = _manager(_block(FILE))

        assert manager.is_active_file()
        assert not manager.is_active_url()
        assert not manager.is_active_web_url()
        assert not manager.is_active_url_at_time()

    def test_a_url_shows_the_url_items(self):
        manager = _manager(_block(STREAM, time_ms=5000))

        assert not manager.is_active_file()
        assert manager.is_active_url()
        assert manager.is_active_web_url()
        assert manager.is_active_url_at_time()

    def test_one_that_has_not_loaded_still_has_its_address(self):
        """A file gone or a stream failing is when its name is wanted most."""

        assert _manager(_block(FILE, is_initialized=False)).is_active_file()

        stream = _manager(_block(STREAM, is_initialized=False))

        assert stream.is_active_url()
        assert stream.is_active_web_url()
        # but it is nowhere yet to be opened at
        assert not stream.is_active_url_at_time()

    def test_a_live_stream_has_no_time_to_be_opened_at(self):
        assert not _manager(_block(STREAM, is_live=True)).is_active_url_at_time()

    def test_a_site_that_takes_no_time_has_none(self):
        assert not _manager(_block("https://example.com/v.mp4")).is_active_url_at_time()

    def test_a_camera_is_not_for_a_browser(self):
        manager = _manager(_block("rtsp://user:pass@camera/stream"))

        assert manager.is_active_url()
        assert not manager.is_active_web_url()

    def test_nothing_shows_without_a_video(self):
        manager = _manager(None)

        assert not manager.is_active_file()
        assert not manager.is_active_url()
        assert not manager.is_active_url_at_time()


class TestWhatIsCopied:
    def test_the_file_name(self, clipboard):
        _manager(_block(FILE)).cmd_copy_active_file_name()

        assert clipboard.text() == FILE.name

    def test_the_file_path_as_the_system_writes_it(self, clipboard):
        _manager(_block(FILE)).cmd_copy_active_file_path()

        assert clipboard.text() == str(FILE)

    def test_the_url_as_it_was_given(self, clipboard):
        url = "rtsp://user:pass@camera/stream?a=1&b=%20"

        _manager(_block(url)).cmd_copy_active_url()

        assert clipboard.text() == url

    def test_the_url_at_the_time_playing(self, clipboard):
        _manager(_block(STREAM, time_ms=83_900)).cmd_copy_active_url_at_time()

        assert clipboard.text() == f"{STREAM}&t=83s"

    def test_a_file_has_no_url_and_a_url_no_file(self, clipboard):
        _manager(_block(FILE)).cmd_copy_active_url()
        _manager(_block(STREAM)).cmd_copy_active_file_path()
        _manager(_block(STREAM)).cmd_copy_active_file_name()

        assert clipboard.text() == "untouched"

    def test_every_location_a_line_each_as_the_grid_has_them(self, clipboard):
        blocks = [_block(FILE), _block(STREAM), _block("rtsp://camera/1")]

        _manager(blocks=blocks, order=["2", "0", "1"]).cmd_copy_all_locations()

        assert clipboard.text().split("\n") == ["rtsp://camera/1", str(FILE), STREAM]

    def test_no_videos_leave_the_clipboard_alone(self, clipboard):
        _manager().cmd_copy_all_locations()

        assert clipboard.text() == "untouched"


class TestShowInFolder:
    def test_only_a_file_is_shown(self):
        manager = _manager(_block(STREAM))
        manager.cmd_show_active_in_folder()

        manager._revealer.show.assert_not_called()

        manager = _manager(_block(FILE))
        manager.cmd_show_active_in_folder()

        manager._revealer.show.assert_called_once_with(FILE)

    def test_a_file_that_is_there_is_itself(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.touch()

        assert existing_place(video) == video

    def test_a_file_gone_is_the_nearest_folder_left(self, tmp_path):
        assert existing_place(tmp_path / "gone" / "deeper" / "video.mp4") == tmp_path

    def test_a_drive_gone_is_nothing(self, mocker):
        mocker.patch.object(Path, "is_file", return_value=False)
        mocker.patch.object(Path, "is_dir", return_value=False)

        assert existing_place(Path("/nowhere/video.mp4").absolute()) is None

    def test_an_error_looking_is_nothing(self, mocker):
        mocker.patch.object(Path, "is_file", side_effect=PermissionError)

        assert existing_place(FILE) is None

    @pytest.mark.parametrize("is_there", [True, False])
    def test_windows_shows_it_from_the_thread_that_looked(
        self, mocker, tmp_path, is_there
    ):
        video = tmp_path / "video.mp4"
        if is_there:
            video.touch()

        mocker.patch.object(show_in_folder.env, "IS_WINDOWS", True)
        shown = mocker.patch.object(show_in_folder, "_show_windows")

        FolderRevealer()._look(video)

        shown.assert_called_once_with(video if is_there else tmp_path, is_file=is_there)

    def test_elsewhere_it_is_shown_on_the_gui_thread(self, mocker, tmp_path):
        video = tmp_path / "video.mp4"
        video.touch()

        mocker.patch.object(show_in_folder.env, "IS_WINDOWS", False)

        revealer = FolderRevealer()
        shown = mocker.patch.object(revealer, "_show")
        revealer._found.disconnect()
        revealer._found.connect(shown)

        revealer._look(video)

        shown.assert_called_once_with(video, True)

    def test_nothing_left_shows_nothing(self, mocker):
        mocker.patch.object(show_in_folder, "existing_place", return_value=None)
        shown = mocker.patch.object(show_in_folder, "_show_windows")

        FolderRevealer()._look(FILE)

        shown.assert_not_called()

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="QtDBus")
    def test_without_a_session_bus_linux_opens_the_folder(self, mocker, tmp_path):
        """conftest points the session bus at nothing."""

        video = tmp_path / "video.mp4"
        opened = mocker.patch.object(show_in_folder, "open_folder")

        FolderRevealer()._show_linux(video, is_file=True)

        opened.assert_called_once_with(tmp_path)


class TestUrlAtTime:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "https://www.youtube.com/watch?v=ID",
                "https://www.youtube.com/watch?v=ID&t=83s",
            ),
            (
                "https://www.youtube.com/watch?v=ID&t=10s&list=PL",
                "https://www.youtube.com/watch?v=ID&list=PL&t=83s",
            ),
            (
                "https://www.youtube.com/watch?v=ID&start=10",
                "https://www.youtube.com/watch?v=ID&t=83s",
            ),
            (
                "https://youtube.com/watch?v=ID#t=10",
                "https://youtube.com/watch?v=ID&t=83s",
            ),
            ("https://youtu.be/ID", "https://youtu.be/ID?t=83s"),
            ("https://youtu.be/ID?si=abc&t=5", "https://youtu.be/ID?si=abc&t=83s"),
            (
                "https://m.youtube.com/watch?v=ID&feature=a%20b",
                "https://m.youtube.com/watch?v=ID&feature=a%20b&t=83s",
            ),
            (
                "https://www.twitch.tv/videos/123456",
                "https://www.twitch.tv/videos/123456?t=00h01m23s",
            ),
            (
                "https://twitch.tv/videos/123456?t=1h0m0s",
                "https://twitch.tv/videos/123456?t=00h01m23s",
            ),
        ],
    )
    def test_the_time_goes_in_as_the_site_reads_it(self, url, expected):
        assert url_at_time(url, 83_900) == expected

    def test_twitch_counts_hours(self):
        assert url_at_time("https://www.twitch.tv/videos/1", 3_723_000).endswith(
            "?t=01h02m03s"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/shorts/ID",
            "https://www.youtube.com/embed/ID",
            "https://www.youtube.com/live/ID",
        ],
    )
    def test_youtube_without_a_time_is_its_watch_page(self, url):
        assert url_at_time(url, 83_900, youtube_id="ID") == (
            "https://www.youtube.com/watch?v=ID&t=83s"
        )
        # which is not known before it is resolved
        assert url_at_time(url, 83_900) is None

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/video.mp4",
            "https://www.twitch.tv/somechannel",
            "https://www.twitch.tv/somechannel/clip/Abc",
            "https://notyoutube.com/watch?v=ID",
            "rtsp://www.youtube.com/watch?v=ID",
            "http://[::1",
        ],
    )
    def test_anywhere_else_has_none(self, url):
        assert url_at_time(url, 83_900, youtube_id="ID") is None
