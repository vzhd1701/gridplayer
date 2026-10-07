"""A cell moving on to the next, previous or a random file of its folder, or
of the folders under the one it started in."""

import dataclasses
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.audio_selection import AudioExternal
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.menu import SECTIONS
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.folder_index import FolderIndex, folder_index
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy


class _Frame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=60000
        )


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings
    PlaylistSettings().clear()


@pytest.fixture
def scans_at_once(mocker):
    """Folder trees looked through there and then, not on a thread."""

    mocker.patch.object(FolderIndex, "_start_scan", lambda self, key: self._scan(key))


def _context(blocks=()):
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1
    context.synced_view = None
    context.bookmarks = BookmarksRegistry()
    context.video_blocks = blocks

    return context


def _touch(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        files.append(path)

    return files


@pytest.fixture
def make_block():
    made = []

    def _make(uri: Path, context=None, **video_kwargs):
        parent = QWidget()

        block = VideoBlock(
            video_driver=_Frame, context=context or _context(), parent=parent
        )

        video_kwargs.setdefault("end_action", VideoEndAction.NEXT_FILE)

        block.set_video(
            Video(uri=uri, playback_state=VideoInitialState.PAUSED, **video_kwargs)
        )

        block.notices = []
        block.info_change.connect(block.notices.append)

        made.append((block, parent))

        return block

    yield _make

    for block, _parent in made:
        block.cleanup()
        block.url_resolver.cleanup()


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "videos"

    _touch(root, "a.mp4", "b.mp4", "s1/c.mp4", "s1/deep/d.mp4", "s2/e.mp4")

    return root


def _uri(block):
    return block.video_params.uri


class TestOneFolder:
    def test_next_stays_in_the_folder(self, make_block, tree):
        block = make_block(tree / "b.mp4")

        block.next_video()

        assert _uri(block) == tree / "a.mp4"

    def test_previous_stays_in_the_folder(self, make_block, tree):
        block = make_block(tree / "s1" / "c.mp4")

        block.previous_video()

        assert _uri(block) == tree / "s1" / "c.mp4"


@pytest.mark.usefixtures("scans_at_once")
class TestSubfolders:
    def test_next_goes_through_every_subfolder_and_round(self, make_block, tree):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)

        seen = []
        for _ in range(5):
            block.next_video()
            seen.append(_uri(block).relative_to(tree).as_posix())

        assert seen == ["b.mp4", "s1/c.mp4", "s1/deep/d.mp4", "s2/e.mp4", "a.mp4"]

    def test_previous_goes_back_up(self, make_block, tree):
        block = make_block(tree / "s1" / "c.mp4", is_dir_recursive=True, dir_root=tree)

        block.previous_video()

        assert _uri(block) == tree / "b.mp4"

    def test_turned_on_it_is_the_folder_playing_that_is_gone_through(
        self, make_block, tree
    ):
        block = make_block(tree / "s1" / "c.mp4")

        block.set_dir_recursive(True)

        assert block.video_params.dir_root == tree / "s1"

        block.next_video()
        block.next_video()

        # round within s1, never up to the files beside it
        assert _uri(block) == tree / "s1" / "c.mp4"

    def test_the_root_stays_while_in_a_subfolder(self, make_block, tree):
        block = make_block(tree / "b.mp4")
        block.set_dir_recursive(True)

        block.next_video()
        block.next_video()

        assert _uri(block) == tree / "s1" / "deep" / "d.mp4"
        assert block.video_params.dir_root == tree

    def test_turned_off_the_root_is_forgotten(self, make_block, tree):
        block = make_block(tree / "b.mp4")
        block.set_dir_recursive(True)

        block.set_dir_recursive(False)

        assert block.video_params.dir_root is None

    def test_turned_on_again_it_is_not_moved(self, make_block, tree):
        block = make_block(tree / "b.mp4")
        block.set_dir_recursive(True)
        block.next_video()

        block.set_dir_recursive(True)

        assert block.video_params.dir_root == tree

    def test_on_by_default_it_starts_in_the_folder_it_was_added_from(
        self, make_block, tree
    ):
        block = make_block(tree / "b.mp4", is_dir_recursive=True)

        block.next_video()

        assert block.video_params.dir_root == tree
        assert _uri(block) == tree / "s1" / "c.mp4"

    def test_a_root_the_file_is_not_under_is_moved_to_its_folder(
        self, make_block, tree, tmp_path
    ):
        block = make_block(
            tree / "s2" / "e.mp4", is_dir_recursive=True, dir_root=tmp_path / "other"
        )

        block.next_video()

        assert block.video_params.dir_root == tree / "s2"

    def test_a_file_gone_since_the_tree_was_looked_through_is_passed_over(
        self, make_block, tree
    ):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)
        block.next_video()

        (tree / "s1" / "c.mp4").unlink()
        block.next_video()

        assert _uri(block) == tree / "s1" / "deep" / "d.mp4"

    def test_too_many_files_is_said_once_the_next_one_shows(self, make_block, tree):
        # the four in the root, and none further down
        PlaylistSettings().set("playlist/folder_max_entries", 4)
        block = make_block(tree / "a.mp4", is_dir_recursive=True)

        block.next_video()
        block.next_video()

        assert block.notices == ["Stopped looking after 4 files and folders"]
        assert _uri(block) == tree / "a.mp4"

    def test_a_tree_gone_through_since_is_looked_through_again(self, make_block, tree):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)
        block.next_video()

        for name in ("a.mp4", "s1/c.mp4", "s1/deep/d.mp4", "s2/e.mp4"):
            (tree / name).unlink()
        (fresh,) = _touch(tree, "s3/new.mp4")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("gridplayer.utils.next_file.MAX_MISSING_FILES", 2)
            block.next_video()

        assert _uri(block) == fresh


class _HeldScans:
    """Folder trees left unlooked at until a test says so."""

    def __init__(self):
        self.keys = []

    def finish(self):
        index = folder_index()

        for key in self.keys:
            index._scan(key)

        self.keys.clear()


@pytest.fixture
def held_scans(mocker):
    held = _HeldScans()
    mocker.patch.object(
        FolderIndex, "_start_scan", lambda _self, key: held.keys.append(key)
    )

    return held


class TestWhileTheTreeIsLookedThrough:
    def test_it_says_so(self, make_block, tree, held_scans):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)

        block.next_video()

        assert block.notices == ["Looking through the folders…"]

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda block: block.seek(1000), id="seek"),
            pytest.param(lambda block: block.stop_playback(), id="stop"),
            pytest.param(
                lambda block: block.set_end_action(VideoEndAction.LOOP_FILE),
                id="end action",
            ),
            pytest.param(
                lambda block: block.set_dir_recursive(False), id="subfolders off"
            ),
        ],
    )
    def test_the_viewer_doing_something_else_takes_no_step(
        self, make_block, tree, held_scans, action
    ):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)
        block.next_video(is_end=True)

        action(block)
        held_scans.finish()

        assert _uri(block) == tree / "a.mp4"

    def test_bookmarks_edited_since_the_end_hold_the_video(
        self, make_block, tree, held_scans
    ):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)
        block.next_video(is_end=True)

        block._is_editing_bookmark = True
        held_scans.finish()
        block._is_editing_bookmark = False

        assert _uri(block) == tree / "a.mp4"
        assert block.notices[-1].startswith("Paused at the start instead of")

    def test_a_step_the_viewer_asked_for_is_taken_all_the_same(
        self, make_block, tree, held_scans
    ):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)
        block.next_video()

        block._is_editing_bookmark = True
        held_scans.finish()
        block._is_editing_bookmark = False

        assert _uri(block) == tree / "b.mp4"

    def test_a_tree_thrown_away_as_it_came_is_still_waited_for(
        self, make_block, tree, held_scans
    ):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)
        block.next_video()
        (key,) = held_scans.keys

        folder_index().forget(key)
        folder_index().scanned.emit(key)

        assert block._folder_navigator.is_waiting

    def test_a_tree_just_looked_through_is_not_looked_through_twice(
        self, make_block, tmp_path, held_scans
    ):
        (only,) = _touch(tmp_path, "root/a.mp4")
        block = make_block(only, is_dir_recursive=True)

        block.next_video()
        only.unlink()
        held_scans.finish()

        assert held_scans.keys == []
        assert block._is_error


class TestOffTheInterfaceThread:
    def test_the_step_is_taken_once_the_tree_has_been_looked_through(
        self, make_block, tree
    ):
        block = make_block(tree / "b.mp4", is_dir_recursive=True)

        block.next_video()

        deadline = time.monotonic() + 5
        while _uri(block) == tree / "b.mp4" and time.monotonic() < deadline:
            QApplication.processEvents()

        assert _uri(block) == tree / "s1" / "c.mp4"

    def test_a_file_that_came_meanwhile_is_left_alone(self, make_block, tree):
        block = make_block(tree / "a.mp4", is_dir_recursive=True)

        block.next_video()
        block.switch_video(tree / "s2" / "e.mp4")

        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            QApplication.processEvents()

        assert _uri(block) == tree / "s2" / "e.mp4"


@pytest.mark.usefixtures("scans_at_once")
class TestRandom:
    def test_every_file_once_before_any_comes_again(self, make_block, tree):
        block = make_block(
            tree / "a.mp4",
            is_dir_recursive=True,
            end_action=VideoEndAction.SHUFFLE_FILE,
        )

        played = []
        for _ in range(4):
            block.shuffle_video()
            played.append(_uri(block))

        assert sorted(played) == sorted(
            [
                tree / "b.mp4",
                tree / "s1" / "c.mp4",
                tree / "s1" / "deep" / "d.mp4",
                tree / "s2" / "e.mp4",
            ]
        )

    def test_play_previous_goes_back_through_those_played(self, make_block, tree):
        block = make_block(tree / "a.mp4", end_action=VideoEndAction.SHUFFLE_FILE)

        block.next_video()
        first = _uri(block)

        block.previous_video()
        assert _uri(block) == tree / "a.mp4"

        block.next_video()
        assert _uri(block) == first

    def test_play_random_file_while_looping_the_file(self, make_block, tree):
        block = make_block(tree / "a.mp4", end_action=VideoEndAction.LOOP_FILE)

        block.shuffle_video()
        first = _uri(block)
        block.shuffle_video()

        assert first == tree / "b.mp4"
        assert _uri(block) == tree / "a.mp4"
        assert block.video_params.end_action == VideoEndAction.LOOP_FILE

    def test_with_none_played_before_previous_starts_it_over(self, make_block, tree):
        block = make_block(tree / "a.mp4", end_action=VideoEndAction.SHUFFLE_FILE)

        block.previous_video()

        assert _uri(block) == tree / "a.mp4"

    def test_previous_passes_over_a_file_gone_since_it_played(
        self, make_block, tmp_path
    ):
        _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")
        block = make_block(tmp_path / "a.mp4", end_action=VideoEndAction.SHUFFLE_FILE)

        block.next_video()
        gone = _uri(block)
        block.next_video()

        gone.unlink()
        block.previous_video()

        assert _uri(block) == tmp_path / "a.mp4"

    def test_a_file_open_in_another_cell_is_put_off(self, make_block, tmp_path):
        PlaylistSettings().set("playlist/shuffle_avoid_open", True)
        a, b, _c = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")

        blocks = []
        context = _context(blocks)
        block = make_block(a, context=context, end_action=VideoEndAction.SHUFFLE_FILE)
        other = make_block(b, context=context, end_action=VideoEndAction.LOOP_FILE)
        blocks.extend([block, other])

        for _ in range(10):
            block.shuffle_video()
            assert _uri(block) != b

    def test_with_avoiding_off_any_file_may_come(self, make_block, tmp_path):
        a, b = _touch(tmp_path, "a.mp4", "b.mp4")

        blocks = []
        context = _context(blocks)
        block = make_block(a, context=context, end_action=VideoEndAction.SHUFFLE_FILE)
        other = make_block(b, context=context, end_action=VideoEndAction.LOOP_FILE)
        blocks.extend([block, other])

        block.shuffle_video()

        assert _uri(block) == b


class TestSwitching:
    def test_the_audio_file_picked_for_the_last_one_stays_with_it(
        self, make_block, tmp_path
    ):
        a, _b, commentary = _touch(tmp_path, "a.mp4", "b.mp4", "commentary.mka")
        block = make_block(
            a,
            external_audio=[commentary],
            audio_selection=AudioExternal(file=commentary),
        )

        block.next_video()

        assert block.video_params.external_audio == []
        assert not isinstance(block.video_params.audio_selection, AudioExternal)


class TestPlaylist:
    def test_the_root_is_kept_relative_to_the_playlist(self, tmp_path):
        Settings().set("playlist/save_paths_relative", True)
        video_file, *_ = _touch(tmp_path, "videos/sub/a.mp4")

        playlist = Playlist(
            videos=[
                Video(
                    uri=video_file,
                    is_dir_recursive=True,
                    dir_root=tmp_path / "videos",
                )
            ]
        )

        text = playlist.dumps(base_dir=tmp_path)

        assert '"dir_root": "videos"' in text

        (video,) = Playlist.parse(text, base_dir=tmp_path).videos

        assert video.dir_root == tmp_path / "videos"
        assert video.is_dir_recursive

    def test_an_old_playlist_has_no_root(self, tmp_path):
        (video_file,) = _touch(tmp_path, "a.mp4")

        text = Playlist(videos=[Video(uri=video_file)]).dumps(base_dir=tmp_path)

        (video,) = Playlist.parse(text, base_dir=tmp_path).videos

        assert video.dir_root is None


def test_the_menu_offers_it():
    def items(menu):
        for item in menu:
            if isinstance(item, tuple):
                yield from items(item)
            else:
                yield item

    offered = {name for section in SECTIONS.values() for name in items(section)}

    assert "Include Subfolders" in offered
    assert "Play Random File" in offered
    assert "Play Random File [ALL]" in offered
    assert "Include Subfolders On [ALL]" in offered
    assert "Include Subfolders Off [ALL]" in offered
