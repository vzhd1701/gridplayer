"""Videos following one another: zoom and position, play and pause, speed.

What the viewer has one video do, the others do as well where that is
synced (see VideoBlocksManager); seeking has its own tests.
"""

from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.params.settings_fields.kinds import CheckboxField, layout_sections
from gridplayer.params.settings_fields.playlist import PLAYLIST_FIELDS
from gridplayer.params.settings_pages import PLAYLIST_PAGE
from gridplayer.params.static import (
    SeekSyncMode,
    VideoAnchor,
    VideoInitialState,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.player.manager import Context
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.player.managers.snapshots import SnapshotsManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import SyncedView, calc_shared_view
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_view import ViewControl
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP

SECTION_OF = layout_sections(PLAYLIST_PAGE)

URI = "http://example.com/a.mp4"

SHARED = calc_shared_view((1920, 1080), (640, 360), ViewParams(scale=2.0))


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings
    PlaylistSettings().clear()


class TestTheMenu:
    def test_seek_sync_is_under_sync_with_the_rest_after_it(self):
        sync = next(
            item
            for item in SECTIONS["playlist"]
            if isinstance(item, tuple) and item[0] == "Sync"
        )

        assert sync == (
            "Sync",
            (
                "Seek Sync",
                "Seek Sync (Disabled)",
                "Seek Sync (Percent)",
                "Seek Sync (Timecode)",
            ),
            "---",
            "Sync Zoom and Position",
            "Sync Play / Pause",
            "Sync Speed",
        )
        assert SUBMENUS["Sync"]["icon"]
        assert SUBMENUS["Seek Sync"]["icon"]

    @pytest.mark.parametrize(
        ("name", "flag"),
        [
            ("Sync Zoom and Position", "view_sync"),
            ("Sync Play / Pause", "pause_sync"),
            ("Sync Speed", "rate_sync"),
        ],
    )
    def test_each_is_a_toggle_the_player_has(self, name, flag):
        commands = VideoBlocksManager(context=SimpleNamespace(), parent=None).commands
        action = ACTIONS[name]

        assert action["func"] == f"toggle_{flag}"
        assert action["check_if"] == f"is_{flag}"
        assert action["func"] in commands
        assert action["check_if"] in commands

    def test_syncing_the_others_once_is_out_of_playback_and_has_the_view(self):
        playback = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Playback"
        )
        submenus = [i[0] for i in SECTIONS["video_active"] if isinstance(i, tuple)]
        others = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Sync Others"
        )

        assert "Sync Others" not in [i[0] for i in playback if isinstance(i, tuple)]
        assert submenus[submenus.index("Playback") + 1] == "Sync Others"
        assert others == (
            "Sync Others",
            "Seek Others (Percent)",
            "Seek Others (Timecode)",
            "---",
            "Sync Others (Zoom and Position)",
        )

        action = ACTIONS["Sync Others (Zoom and Position)"]

        assert action["func"] == ("active", "view.sync_others")
        assert action["show_if"] == "is_active_has_video"
        assert hasattr(ViewControl, "sync_others")

    @pytest.mark.parametrize(
        "name",
        [
            "Zoom In",
            "Zoom Out",
            "Zoom Reset",
            "Move Left",
            "Move Right",
            "Move Up",
            "Move Down",
            "Position Reset",
            "Align Center",
            "Align Bottom Right",
        ],
    )
    def test_the_viewer_s_zooms_and_moves_are_for_the_others_to_follow(self, name):
        target, manual, command, *_ = ACTIONS[name]["func"]

        part, _, method = command.partition(".")

        assert (target, manual) == ("active", "manual_view")
        assert part == "view"
        assert hasattr(ViewControl, method)

    @pytest.mark.parametrize("name", ["Faster", "Slower", "Normal"])
    def test_the_viewer_s_speeds_are_for_the_others_to_follow(self, name):
        assert ACTIONS[name]["func"][:2] == ("active", "manual_rate")
        assert hasattr(VideoBlock, ACTIONS[name]["func"][2])

    def test_for_all_they_are_left_as_they_were(self):
        assert ACTIONS["Zoom In [ALL]"]["func"] == ("all", "scale_increase")
        assert ACTIONS["Faster [ALL]"]["func"] == ("all", "rate_increase")


class TestTheSettings:
    def test_they_are_off_by_default(self):
        for key in ("playlist/view_sync", "playlist/pause_sync", "playlist/rate_sync"):
            assert Settings().get(key) is False

    def test_they_are_together_with_seek_sync_in_a_section_of_their_own(self):
        fields = [
            field
            for field in PLAYLIST_FIELDS
            if SECTION_OF[field.settings_key] == "Sync"
        ]

        assert [field.settings_key for field in fields] == [
            "playlist/seek_sync_mode",
            "playlist/view_sync",
            "playlist/pause_sync",
            "playlist/rate_sync",
        ]
        assert [field.attr for field in fields[1:]] == [
            "view_sync",
            "pause_sync",
            "rate_sync",
        ]
        assert all(isinstance(field, CheckboxField) for field in fields[1:])


def _block(is_initialized=True, has_picture=True, is_live=False):
    """What of a VideoBlock syncing goes through, its own methods for it."""

    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI)
    block.is_video_initialized = is_initialized
    block.video_tracks = {0: object()} if has_picture else {}
    block.is_live = is_live
    block._is_state_change_in_progress = False
    block._ctx = SimpleNamespace(synced_view=None)
    block.video_driver = Mock()
    block.video_driver.shared_view.return_value = SHARED

    for name in (
        "manual_view",
        "manual_rate",
        "follow_rate",
        "play_pause",
    ):
        setattr(block, name, partial(getattr(VideoBlock, name), block))

    block.view = Mock(spec=ViewControl)
    block.view._block = block
    block.view._is_zoomed_to_selection = False
    block.view._view_to_follow = None

    for name in (
        "sync_others",
        "synced",
        "follow",
        "remember_followed",
        "follow_synced",
        "forget_view_to_follow",
    ):
        setattr(block.view, name, partial(getattr(ViewControl, name), block.view))

    return block


class TestTheViewersOwnView:
    def test_it_is_changed_and_given_for_the_others_to_follow(self):
        block = _block()
        block.view.pan_by.return_value = (0.5, 0.0)

        assert block.manual_view("view.pan_by", 3, 4) == (0.5, 0.0)

        block.view.pan_by.assert_called_once_with(3, 4)
        block.sync_view.emit.assert_called_once_with(SyncedView(SHARED, False))

    def test_it_says_where_the_picture_is_from_a_zoom_to_a_selection(self):
        block = _block()
        block.view._is_zoomed_to_selection = True

        block.manual_view("view.scale_reset")

        block.sync_view.emit.assert_called_once_with(SyncedView(SHARED, True))

    def test_with_no_picture_there_is_nothing_to_follow(self):
        block = _block(has_picture=False)

        block.manual_view("view.scale_increase")

        block.view.scale_increase.assert_called_once_with()
        block.sync_view.emit.assert_not_called()

    def test_the_others_can_be_given_it_once(self):
        block = _block()

        block.view.sync_others()

        block.sync_view_single.emit.assert_called_once_with(SyncedView(SHARED, False))
        block.sync_view.emit.assert_not_called()


class TestFollowingAnothersView:
    def test_it_shows_what_the_other_does_and_keeps_it(self):
        block = _block()
        view = ViewParams(scale=2.0, anchor=VideoAnchor.TOP, shift=VideoShift(10, 20))
        block.video_driver.follow_view.return_value = view

        block.view.follow(SyncedView(SHARED, True))

        block.video_driver.follow_view.assert_called_once_with(SHARED)
        assert block.video_params.scale == 2.0
        assert block.video_params.anchor == VideoAnchor.TOP
        assert block.video_params.shift == VideoShift(10, 20)
        assert block.view._is_zoomed_to_selection is True
        # quietly: the other says what it shows
        block.info_change.emit.assert_not_called()
        block.sync_view.emit.assert_not_called()

    def test_waiting_for_its_frame_size_it_keeps_its_own_until_then(self):
        block = _block()
        block.video_driver.follow_view.return_value = None

        block.view.follow(SyncedView(SHARED, False))

        assert block.video_params.scale == 1.0

    def test_not_playing_yet_it_shows_it_once_it_is(self):
        block = _block(is_initialized=False)
        synced = SyncedView(SHARED, False)

        block.view.follow(synced)

        block.video_driver.follow_view.assert_not_called()
        assert block.view._view_to_follow == synced

    def test_without_a_picture_there_is_nothing_to_show_it_in(self):
        block = _block(has_picture=False)

        block.view.follow(SyncedView(SHARED, True))

        block.video_driver.follow_view.assert_not_called()
        assert block.view._is_zoomed_to_selection is False

    def test_loaded_it_shows_the_one_it_was_to_follow(self):
        block = _block()
        kept = SyncedView(SHARED, True)
        block.view._view_to_follow = kept
        block._ctx.synced_view = SyncedView(SHARED, False)
        block.view.follow = Mock()

        block.view.follow_synced()

        block.view.follow.assert_called_once_with(kept)
        assert block.view._view_to_follow is None

    def test_loaded_otherwise_it_shows_the_one_they_are_synced_to(self):
        block = _block()
        synced = SyncedView(SHARED, False)
        block._ctx.synced_view = synced
        block.view.follow = Mock()

        block.view.follow_synced()

        block.view.follow.assert_called_once_with(synced)

    def test_loaded_with_neither_it_shows_its_own(self):
        block = _block()
        block.view.follow = Mock()

        block.view.follow_synced()

        block.view.follow.assert_not_called()

    def test_a_snapshot_s_view_is_not_overruled_by_one_to_follow(self):
        block = _block(is_initialized=False)
        block._default_title = None
        block.view._view_to_follow = SyncedView(SHARED, False)
        block.apply_snapshot = partial(VideoBlock.apply_snapshot, block)

        block.apply_snapshot(Video(uri=URI, playback_state=VideoInitialState.STOPPED))

        assert block.view._view_to_follow is None


class TestTheViewersOwnPlayAndPause:
    def test_played_or_paused_the_others_are_told_which(self):
        block = _block()
        block.video_params.playback_state = VideoInitialState.PLAYING

        block.play_pause()

        block.set_pause.assert_called_once_with(True)
        block.sync_pause.emit.assert_called_once_with(True)

    def test_while_it_is_still_on_its_way_nothing_is_done(self):
        block = _block()
        block._is_state_change_in_progress = True

        block.play_pause()

        block.set_pause.assert_not_called()
        block.sync_pause.emit.assert_not_called()


class TestTheViewersOwnSpeed:
    def test_it_is_changed_and_given_for_the_others_to_follow(self):
        block = _block()
        block.video_params.rate = 1.3

        block.manual_rate("rate_increase")

        block.rate_increase.assert_called_once_with()
        block.sync_rate.emit.assert_called_once_with(1.3)

    @pytest.mark.parametrize(
        "block", [_block(is_live=True), _block(is_initialized=False)]
    )
    def test_with_no_speed_to_it_there_is_none_to_follow(self, block):
        block.manual_rate("rate_reset")

        block.sync_rate.emit.assert_not_called()

    def test_another_s_is_taken_quietly(self):
        block = _block()

        block.follow_rate(0.5)

        assert block.video_params.rate == 0.5
        block.set_rate.assert_called_once_with(0.5, is_silent=True)

    def test_a_live_stream_has_none(self):
        block = _block(is_live=True)

        block.follow_rate(0.5)

        assert block.video_params.rate == 1.0
        block.set_rate.assert_not_called()


def _stub(name, is_hidden=False):
    block = Mock(spec=VideoBlock)
    block.view = Mock(spec=ViewControl)
    block.id = name
    block.video_id = name
    block.video_params = Video(uri=URI)
    block.isHidden.return_value = is_hidden
    return block


def _manager(*blocks, **ctx):
    context = SimpleNamespace(**ctx)
    manager = VideoBlocksManager(context=context, parent=None)

    for block in blocks:
        context.video_blocks.append(block)

    return manager


class TestSyncingTheView:
    def test_off_the_others_are_left_alone(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)

        manager.sync_view(leader, SyncedView(SHARED, False))

        other.view.follow.assert_not_called()
        assert manager._ctx.synced_view is None

    def test_on_the_others_follow_and_it_is_kept_for_those_loading_after(self):
        leader, other, third = _stub("a"), _stub("b"), _stub("c")
        manager = _manager(leader, other, third)
        manager.set_view_sync(True)
        synced = SyncedView(SHARED, False)

        manager.sync_view(leader, synced)

        leader.view.follow.assert_not_called()
        other.view.follow.assert_called_once_with(synced)
        third.view.follow.assert_called_once_with(synced)
        assert manager._ctx.synced_view == synced

    def test_once_the_others_follow_synced_or_not(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)
        synced = SyncedView(SHARED, False)

        manager.sync_view_single(leader, synced)

        other.view.follow.assert_called_once_with(synced)
        assert manager._ctx.synced_view is None

    def test_once_with_their_views_synced_is_the_view_to_sync_to(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)
        manager.set_view_sync(True)
        synced = SyncedView(SHARED, False)

        manager.sync_view_single(leader, synced)

        other.view.follow.assert_called_once_with(synced)
        assert manager._ctx.synced_view == synced

    def test_switched_off_and_on_it_starts_afresh(self):
        leader = _stub("a")
        manager = _manager(leader)
        manager.set_view_sync(True)
        manager.sync_view(leader, SyncedView(SHARED, False))

        manager.toggle_view_sync()

        assert manager._ctx.synced_view is None
        assert PlaylistSettings().get("playlist/view_sync") is False

    def test_set_again_as_it_is_the_view_is_kept(self):
        # the playlist's settings are all put in place again on each edit
        leader = _stub("a")
        manager = _manager(leader)
        manager.set_view_sync(True)
        synced = SyncedView(SHARED, False)
        manager.sync_view(leader, synced)

        manager.set_view_sync(True)

        assert manager._ctx.synced_view == synced

    def test_zoomed_for_all_the_view_is_taken_again_from_where_it_came(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)
        manager.set_view_sync(True)
        manager.sync_view(leader, SyncedView(SHARED, False))
        zoomed = SyncedView(SHARED, True)
        leader.view.synced.return_value = zoomed

        manager.cmd_all("scale_increase")

        assert manager._ctx.synced_view == zoomed

    def test_for_all_anything_else_leaves_it_be(self):
        leader = _stub("a")
        manager = _manager(leader)
        manager.set_view_sync(True)
        synced = SyncedView(SHARED, False)
        manager.sync_view(leader, synced)

        manager.cmd_all("rate_increase")

        leader.view.synced.assert_not_called()
        assert manager._ctx.synced_view == synced

    def test_forgotten_those_loading_after_show_their_own(self):
        leader = _stub("a")
        manager = _manager(leader)
        manager.set_view_sync(True)
        manager.sync_view(leader, SyncedView(SHARED, False))

        manager.forget_synced_view()

        assert manager._ctx.synced_view is None


class TestSyncingPlayAndPause:
    def test_off_the_others_are_left_alone(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)

        manager.sync_pause(leader, True)

        other.set_pause.assert_not_called()

    def test_on_the_others_follow(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)
        manager.toggle_pause_sync()

        manager.sync_pause(leader, False)

        leader.set_pause.assert_not_called()
        other.set_pause.assert_called_once_with(False)
        assert PlaylistSettings().get("playlist/pause_sync") is True

    def test_those_single_mode_keeps_paused_stay_paused(self):
        leader, hidden = _stub("a"), _stub("b", is_hidden=True)
        manager = _manager(
            leader, hidden, is_single_mode=True, is_pause_background_videos=True
        )
        manager.set_pause_sync(True)

        manager.sync_pause(leader, False)

        hidden.set_pause.assert_not_called()

    def test_hidden_by_single_mode_alone_they_follow(self):
        leader, hidden = _stub("a"), _stub("b", is_hidden=True)
        manager = _manager(
            leader, hidden, is_single_mode=True, is_pause_background_videos=False
        )
        manager.set_pause_sync(True)

        manager.sync_pause(leader, False)

        hidden.set_pause.assert_called_once_with(False)


class TestAStepToAnotherFrame:
    def _paused(self, manager):
        paused = []
        manager.set_pause.connect(paused.append)
        manager.sync_frame_step_pause(True)
        return paused

    def test_nothing_synced_the_others_play_on(self):
        assert self._paused(_manager()) == []

    def test_with_play_and_pause_synced_they_pause(self):
        manager = _manager()
        manager.set_pause_sync(True)

        assert self._paused(manager) == [True]

    @pytest.mark.parametrize("mode", [SeekSyncMode.PERCENT, SeekSyncMode.TIMECODE])
    def test_with_the_seek_synced_they_pause_to_step_along(self, mode):
        manager = _manager()
        manager.set_seek_sync_mode(mode)

        assert self._paused(manager) == [True]


class TestSyncingTheSpeed:
    def test_off_the_others_are_left_alone(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)

        manager.sync_rate(leader, 2.0)

        other.follow_rate.assert_not_called()

    def test_on_the_others_follow(self):
        leader, other = _stub("a"), _stub("b")
        manager = _manager(leader, other)
        manager.toggle_rate_sync()

        manager.sync_rate(leader, 2.0)

        leader.follow_rate.assert_not_called()
        other.follow_rate.assert_called_once_with(2.0)
        assert PlaylistSettings().get("playlist/rate_sync") is True


def test_a_snapshot_s_views_are_not_overruled_by_the_synced_one():
    order = []
    block = _stub("a")
    block.apply_snapshot.side_effect = lambda _video: order.append("applied")
    context = SimpleNamespace(
        video_blocks=MagicMock(is_all_initialized=True, __len__=lambda _self: 1),
        commands=SimpleNamespace(forget_synced_view=lambda: order.append("forgot")),
    )
    context.video_blocks.by_video_id.return_value = block
    manager = SnapshotsManager(context=context, parent=None)
    manager.set_snapshots(
        {1: SimpleNamespace(videos=[Video(uri=URI)], grid_state=GridState())}
    )

    manager.cmd_load_snapshot(1)

    assert order == ["forgot", "applied"]


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame(video_dimensions):
    frame = _StubFrame(vlc_options=[])
    frame.resize(640, 360)
    track = VideoTrack(
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        video_dimensions=video_dimensions,
        fps=None,
        orientation=VideoTransform.NONE,
    )
    frame.media = MagicMock(is_audio_only=False, video_tracks={0: track})
    frame.media.cur_video_track = track
    return frame


class TestTheFrameFollowing:
    def test_it_shows_what_the_other_does(self):
        frame = _frame((1920, 1080))

        view = frame.follow_view(SHARED)

        assert view == SHARED.view
        assert frame._view == SHARED.view

    def test_its_own_is_shared(self):
        frame = _frame((1920, 1080))
        frame._view = ViewParams(scale=2.0)

        assert frame.shared_view() == SHARED

    def test_without_its_frame_size_it_waits_for_it(self):
        frame = _frame((0, 0))
        followed = []
        frame.view_followed.connect(followed.append)

        assert frame.follow_view(SHARED) is None
        assert frame._view == ViewParams()

        frame.set_track_dimensions(1920, 1080)

        assert followed == [SHARED.view]
        assert frame._view == SHARED.view

    def test_once_followed_it_is_done_with(self):
        frame = _frame((0, 0))
        frame.follow_view(SHARED)
        frame.set_track_dimensions(1920, 1080)
        followed = []
        frame.view_followed.connect(followed.append)

        frame.media.cur_video_track.video_dimensions = (0, 0)
        frame.set_track_dimensions(1280, 720)

        assert followed == []


@pytest.fixture
def grid(tmp_path):
    """Videos in a player, as many as a test adds, all loaded at once."""

    parent = QWidget()
    context = Context()
    context.video_driver = lambda: VideoFrameDummy
    context.bookmarks = BookmarksRegistry()
    context.lists = MediaListsRegistry()
    context.commands = MagicMock()
    manager = VideoBlocksManager(context=context, parent=parent)
    blocks = []

    def _add(count=1):
        for _ in range(count):
            video_file = tmp_path / f"movie{len(blocks)}.mkv"
            video_file.touch()

            (block,) = manager.add_videos(
                [Video(uri=video_file, playback_state=VideoInitialState.PAUSED)]
            )
            block.video_driver._fake_player_timer.stop()
            blocks.append(block)

        return blocks

    yield manager, _add

    for block in blocks:
        block.cleanup()
        block.url_resolver.cleanup()

    parent.deleteLater()


class TestInThePlayer:
    def test_a_zoom_is_followed_by_the_others_and_by_one_loaded_after(self, grid):
        manager, add = grid
        leader, other = add(2)
        manager.set_view_sync(True)

        leader.manual_view("view.scale_increase")

        assert other.video_params.scale == pytest.approx(1.1)
        assert other.video_driver._view == leader.video_driver._view

        (*_, third) = add()

        assert third.video_params.scale == pytest.approx(1.1)

    def test_the_others_are_shown_the_view_once(self, grid):
        manager, add = grid
        leader, other = add(2)
        leader.view.scale_increase()

        leader.view.sync_others()

        assert other.video_params.scale == pytest.approx(1.1)
        assert manager._ctx.synced_view is None

    def test_a_pause_is_followed(self, grid):
        manager, add = grid
        leader, other = add(2)
        manager.set_pause_sync(True)

        leader.play_pause()

        assert not leader.video_params.is_paused
        assert not other.video_params.is_paused

    def test_a_speed_is_followed(self, grid):
        manager, add = grid
        leader, other = add(2)
        manager.set_rate_sync(True)

        leader.manual_rate("rate_decrease")

        assert other.video_params.rate == pytest.approx(0.9)
