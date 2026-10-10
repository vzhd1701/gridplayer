"""A cell that plays one video made to play a list, asked about first; and
an item of a list opened in a new cell."""

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QWidget

from gridplayer.dialogs.make_list import MakeFrom, MakeListChoice, MakeListDialog
from gridplayer.models.media_list import ListItem, MediaList
from gridplayer.params.static import VideoEndAction
from gridplayer.player.managers import lists as lists_module
from gridplayer.player.managers.lists import ListsManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings


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


class TestTheQuestion:
    def test_a_file_offers_its_folder(self, tmp_path):
        dialog = MakeListDialog(tmp_path, is_recursive=False)

        assert not dialog._folder_choice.isHidden()
        assert dialog.choice() == MakeListChoice(MakeFrom.FOLDER, False)

    def test_its_subfolders_as_the_cell_has_them(self, tmp_path):
        dialog = MakeListDialog(tmp_path, is_recursive=True)

        assert dialog.choice() == MakeListChoice(MakeFrom.FOLDER, True)

    def test_subfolders_only_for_the_folder(self, tmp_path):
        dialog = MakeListDialog(tmp_path, is_recursive=True)

        dialog._video_choice.setChecked(True)

        assert not dialog._recursive_box.isEnabled()
        assert dialog.choice() == MakeListChoice(MakeFrom.VIDEO)

    def test_a_link_has_just_itself(self):
        dialog = MakeListDialog(None, is_recursive=False)

        assert dialog._folder_choice.isHidden()
        assert dialog.choice() == MakeListChoice(MakeFrom.VIDEO)


class _Cell:
    def __init__(self, uri, title=None):
        self.video_params = SimpleNamespace(
            uri=uri,
            title=title,
            uri_name=uri.name if isinstance(uri, Path) else uri,
            is_dir_recursive=False,
            list_id=None,
            http_headers=None,
        )
        self.media_list = None
        self.is_closing = False
        self.taken = []

    def take_list(self, list_id, index):
        self.taken.append((list_id, index))
        self.video_params.list_id = list_id


@pytest.fixture
def manager(mocker):
    parent = QWidget()
    ctx = SimpleNamespace(
        commands=MagicMock(), active_block=None, video_blocks=MagicMock()
    )

    manager = ListsManager(context=ctx, parent=parent)
    manager.windows = []
    mocker.patch.object(
        manager,
        "open_list_window",
        side_effect=lambda list_id, block=None, parent=None: manager.windows.append(
            (list_id, block)
        ),
    )

    yield manager

    parent.deleteLater()


def _answer(mocker, answer):
    return mocker.patch.object(lists_module.MakeListDialog, "ask", return_value=answer)


def _wait_until(condition, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if condition():
            return True
    return False


class TestMakingAList:
    def test_of_just_the_video(self, manager, mocker, tmp_path):
        (video,) = _touch(tmp_path, "a.mp4")
        cell = _Cell(video, title="Mine")
        manager._ctx.active_block = cell
        _answer(mocker, MakeListChoice(MakeFrom.VIDEO))

        manager.cmd_manage_list()

        (media_list,) = manager._ctx.lists.lists()
        assert [(item.uri, item.title) for item in media_list.items] == [
            (video, "Mine")
        ]
        assert cell.taken == [(media_list.id, 0)]
        assert manager.windows == [(media_list.id, cell)]

    def test_of_its_folder_from_where_it_is(self, manager, mocker, tmp_path):
        first, second, _under = _touch(tmp_path, "a.mp4", "b.mp4", "sub/c.mp4")
        cell = _Cell(second)
        manager._ctx.active_block = cell
        _answer(mocker, MakeListChoice(MakeFrom.FOLDER, False))

        manager.cmd_manage_list()

        assert _wait_until(lambda: cell.taken)
        (media_list,) = manager._ctx.lists.lists()
        assert [item.uri for item in media_list.items] == [first, second]
        assert media_list.source.location == tmp_path
        assert not media_list.source.is_recursive
        assert cell.taken == [(media_list.id, 1)]

    def test_what_is_on_it_told_as_added(self, manager, mocker, tmp_path):
        _touch(tmp_path, "a.mp4", "b.mp4")
        (second,) = _touch(tmp_path, "c.mp4")
        cell = _Cell(second)
        manager._ctx.active_block = cell
        _answer(mocker, MakeListChoice(MakeFrom.FOLDER, False))
        told = []
        manager._ctx.lists.items_added.connect(lambda *args: told.append(args))

        manager.cmd_manage_list()

        assert _wait_until(lambda: told)
        (media_list,) = manager._ctx.lists.lists()
        assert told == [(media_list.id, [item.key for item in media_list.items])]

    def test_of_its_folder_and_under_it(self, manager, mocker, tmp_path):
        _touch(tmp_path, "a.mp4", "sub/c.mp4")
        cell = _Cell(tmp_path / "a.mp4")
        manager._ctx.active_block = cell
        _answer(mocker, MakeListChoice(MakeFrom.FOLDER, True))

        manager.cmd_manage_list()

        assert _wait_until(lambda: cell.taken)
        (media_list,) = manager._ctx.lists.lists()
        assert len(media_list.items) == 2

    def test_not_when_the_viewer_thinks_better_of_it(self, manager, mocker, tmp_path):
        cell = _Cell(tmp_path / "a.mp4")
        manager._ctx.active_block = cell
        _answer(mocker, None)

        manager.cmd_manage_list()

        assert manager._ctx.lists.lists() == []
        assert manager.windows == []

    def test_a_cell_with_a_list_is_not_asked(self, manager, mocker, tmp_path):
        cell = _Cell(tmp_path / "a.mp4")
        cell.media_list = MediaList()
        cell.video_params.list_id = cell.media_list.id
        manager._ctx.active_block = cell
        ask = _answer(mocker, None)

        manager.cmd_manage_list()

        ask.assert_not_called()
        assert manager.windows == [(cell.media_list.id, cell)]


class TestOpeningAnItemInANewCell:
    def test_goes_along_the_list_from_there(self, manager):
        media_list = manager._ctx.lists.add(
            MediaList(items=(ListItem(uri="http://a"), ListItem(uri="http://b")))
        )

        manager.open_list_in_new_cell(media_list.id, 1)

        ((video,),), _ = manager._ctx.commands.add_videos_to_layout.call_args
        assert (video.uri, video.list_id, video.list_index) == (
            "http://b",
            media_list.id,
            1,
        )
        assert video.end_action == VideoEndAction.NEXT_FILE


class TestLookedUpAsAdded:
    @pytest.fixture
    def looked_up(self, manager, mocker):
        return mocker.patch.object(manager._lookups, "look_up")

    def _added(self, manager):
        a, b, c = (ListItem(uri=Path(f"D:/{n}.mp4")) for n in "abc")
        media_list = manager._ctx.lists.add(MediaList(items=(a, b, c)))

        manager._ctx.lists.tell_added(media_list.id, [c.key, a.key])

        return media_list, [a, c]

    def test_where_the_playlist_says_to(self, manager, looked_up):
        PlaylistSettings().set("playlist/list_get_info", True)

        media_list, added = self._added(manager)

        looked_up.assert_called_once_with(media_list.id, added, is_missing_only=True)

    def test_not_by_default(self, manager, looked_up):
        self._added(manager)

        looked_up.assert_not_called()

    def test_lookups_stopped_as_the_player_closes(self, manager, mocker):
        shutdown = mocker.patch.object(manager._lookups, "shutdown")

        manager.cleanup()

        shutdown.assert_called_once()

    def test_the_window_told_of_them(self, manager):
        assert manager._reading().lookups is manager._lookups
