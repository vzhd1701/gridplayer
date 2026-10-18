"""Where a video's picture sits in its pane: against a side or corner, and
moved on from there.

The alignment says where the picture goes when there is room for it to go
somewhere: which part of it is cut off where it is bigger than the pane,
and where in the pane it stands where it is smaller. The position moves it
on from there, in video pixels like the crop, held within the edges, or
let past them as far as leaves half the picture on show.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtCore import QPoint, QRect, QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.playlist import Playlist, PlaylistVideoDefaults
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.params.settings_bindings import VIDEO_DEFAULT_ATTRS
from gridplayer.params.settings_fields.kinds import CheckboxField
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.params.settings_pages import VIDEO_PAGE
from gridplayer.params.static import (
    MAX_SCALE,
    HWCropBorderOffset,
    VideoAnchor,
    VideoAspect,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.player.managers.menu import MenuManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.playlist_settings import PlaylistSettings, overrides_from_playlist
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import calc_view_geometry, calc_vlc_picture
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets import video_block_view as video_block_view_module
from gridplayer.widgets import video_frame_vlc_base as vlc_base
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_loop import LoopControl
from gridplayer.widgets.video_block_view import ViewControl
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP
from tests.conftest import mock_block_parts
from tests.settings_layout import layout_keys, layout_sections

SECTION_OF = layout_sections(VIDEO_PAGE)

URI = "http://example.com/a.mp4"
NO_SHIFT = VideoShift(0, 0)


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


class TestWhereItIsRemembered:
    def test_a_new_video_stands_in_the_middle(self):
        video = Video(uri=URI)

        assert video.anchor == VideoAnchor.CENTER
        assert video.shift == NO_SHIFT

    def test_a_new_video_is_aligned_as_the_defaults_say(self):
        Settings().set("video_defaults/anchor", VideoAnchor.TOP)

        assert Video(uri=URI).anchor == VideoAnchor.TOP

    def test_a_playlist_that_says_nothing_leaves_it_to_the_defaults(self):
        assert PlaylistVideoDefaults().anchor is None

    def test_a_playlist_can_carry_its_own(self):
        defaults = PlaylistVideoDefaults(anchor="bottom_right")

        assert defaults.anchor == VideoAnchor.BOTTOM_RIGHT

    def test_a_playlist_keeps_both_for_each_video(self):
        video = Video(uri=URI, anchor=VideoAnchor.LEFT, shift=VideoShift(-12, 34))

        loaded = Playlist.parse(Playlist(videos=[video]).dumps()).videos[0]

        assert loaded.anchor == VideoAnchor.LEFT
        assert loaded.shift == VideoShift(-12, 34)

    def test_an_older_playlist_opens_in_the_middle(self):
        doc = json.loads(Playlist(videos=[Video(uri=URI)]).dumps())
        del doc["videos"][0]["anchor"]
        del doc["videos"][0]["shift"]

        loaded = Playlist.parse(json.dumps(doc)).videos[0]

        assert loaded.anchor == VideoAnchor.CENTER
        assert loaded.shift == NO_SHIFT


class TestPastTheEdgesIsRemembered:
    def test_a_new_video_is_kept_within_them(self):
        assert not Video(uri=URI).is_shift_past_edges

    def test_a_new_video_is_let_past_them_as_the_defaults_say(self):
        Settings().set("video_defaults/shift_past_edges", True)

        assert Video(uri=URI).is_shift_past_edges

    def test_a_playlist_can_carry_its_own_default(self):
        assert PlaylistVideoDefaults().shift_past_edges is None
        assert PlaylistVideoDefaults(shift_past_edges=True).shift_past_edges

    def test_a_playlist_keeps_it_for_each_video(self):
        video = Video(uri=URI, is_shift_past_edges=True)

        loaded = Playlist.parse(Playlist(videos=[video]).dumps()).videos[0]

        assert loaded.is_shift_past_edges

    def test_an_older_playlist_keeps_within_them(self):
        doc = json.loads(Playlist(videos=[Video(uri=URI)]).dumps())
        del doc["videos"][0]["is_shift_past_edges"]

        assert not Playlist.parse(json.dumps(doc)).videos[0].is_shift_past_edges


class TestZoomToCursorIsRemembered:
    def test_a_new_video_zooms_about_the_alignment(self):
        assert not Video(uri=URI).is_zoom_to_cursor

    def test_a_new_video_zooms_to_the_cursor_as_the_defaults_say(self):
        Settings().set("video_defaults/zoom_to_cursor", True)

        assert Video(uri=URI).is_zoom_to_cursor

    def test_a_playlist_can_carry_its_own_default(self):
        assert PlaylistVideoDefaults().zoom_to_cursor is None
        assert PlaylistVideoDefaults(zoom_to_cursor=True).zoom_to_cursor

    def test_the_playlist_s_default_is_the_one_its_new_videos_get(self):
        playlist = Playlist(video_defaults=PlaylistVideoDefaults(zoom_to_cursor=True))

        overrides = overrides_from_playlist(playlist)
        PlaylistSettings().replace(overrides)

        assert overrides == {"video_defaults/zoom_to_cursor": True}
        assert Video(uri=URI).is_zoom_to_cursor

    def test_a_playlist_keeps_it_for_each_video(self):
        video = Video(uri=URI, is_zoom_to_cursor=True)

        loaded = Playlist.parse(Playlist(videos=[video]).dumps()).videos[0]

        assert loaded.is_zoom_to_cursor

    def test_an_older_playlist_zooms_about_the_alignment(self):
        doc = json.loads(Playlist(videos=[Video(uri=URI)]).dumps())
        del doc["videos"][0]["is_zoom_to_cursor"]

        assert not Playlist.parse(json.dumps(doc)).videos[0].is_zoom_to_cursor


class TestPlaylistSettings:
    def test_the_alignment_sits_under_crop_in_the_video_section(self):
        keys = list(layout_keys(VIDEO_PAGE))
        at = keys.index("video_defaults/crop")

        assert keys[at + 1] == "video_defaults/anchor"

        spec = FIELDS[keys[at + 1]]
        assert SECTION_OF[spec.settings_key] == "Video"
        assert VIDEO_DEFAULT_ATTRS[spec.settings_key] == "anchor"
        assert list(spec.choices()) == list(VideoAnchor)

    def test_letting_it_past_the_edges_sits_under_the_alignment(self):
        keys = list(layout_keys(VIDEO_PAGE))
        at = keys.index("video_defaults/anchor")

        assert keys[at + 1] == "video_defaults/shift_past_edges"

        spec = FIELDS[keys[at + 1]]
        assert SECTION_OF[spec.settings_key] == "Video"
        assert isinstance(spec, CheckboxField)
        assert VIDEO_DEFAULT_ATTRS[spec.settings_key] == "shift_past_edges"

    def test_zooming_to_the_cursor_sits_under_the_zoom(self):
        keys = list(layout_keys(VIDEO_PAGE))
        at = keys.index("video_defaults/scale")

        assert keys[at + 1] == "video_defaults/zoom_to_cursor"

        spec = FIELDS[keys[at + 1]]
        assert SECTION_OF[spec.settings_key] == "Video"
        assert isinstance(spec, CheckboxField)
        assert VIDEO_DEFAULT_ATTRS[spec.settings_key] == "zoom_to_cursor"

    def test_there_is_no_default_for_the_position(self):
        """A place moved to in one video means nothing for another."""

        assert "shift" not in VIDEO_DEFAULT_ATTRS.values()
        assert "video_defaults/shift" not in FIELDS


def _submenu(section, name):
    video = next(
        item
        for item in SECTIONS[section]
        if isinstance(item, tuple) and item[0] == "Video"
    )
    return next(item for item in video if isinstance(item, tuple) and item[0] == name)


def _all_videos_section(name):
    all_videos = next(
        item
        for item in SECTIONS["video_all"]
        if isinstance(item, tuple) and item[0] == "[ALL]"
    )
    return next(
        item for item in all_videos if isinstance(item, tuple) and item[0] == name
    )


def _all_videos_submenu(name):
    video = _all_videos_section("Video")
    return next(item for item in video if isinstance(item, tuple) and item[0] == name)


def _assert_set_for_all(name, param, owner=ViewControl, method=None):
    """On and Off, each setting it so for every video, and ticked where
    every video already has it so; method is what the manager's all_command
    signal is wired to, where it is named otherwise."""

    assert name in SUBMENUS

    for word, value in (("On", True), ("Off", False)):
        action = ACTIONS[f"{name} {word} [ALL]"]
        target, command, arg = action["func"]

        assert (target, arg) == ("all", value)
        assert hasattr(owner, method or command)
        assert hasattr(VideoBlocksManager, f"all_{command}")
        assert action["check_if"] == ("is_all_videos_param_set_to", param, value)


class TestTheMenu:
    def test_it_sits_between_crop_and_transform(self):
        video = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Video"
        )
        submenus = [i[0] for i in video if isinstance(i, tuple)]

        at = submenus.index("Position")
        assert submenus[at - 1 : at + 2] == ["Crop", "Position", "Transform"]
        assert SUBMENUS["Position"]["icon"] == "anchor"

    def test_the_alignments_come_first_middle_then_sides_then_corners(self):
        position = _submenu("video_active", "Position")

        anchors = [ACTIONS[name]["func"][3] for name in position[1:10]]

        assert anchors == list(VideoAnchor)
        assert position[10] == "---"

    def test_every_alignment_reaches_the_video_and_shows_what_is_in_force(self):
        position = _submenu("video_active", "Position")

        for name in position[1:10]:
            action = ACTIONS[name]
            target, manual, command, anchor = action["func"]

            # the viewer's own, for the others to follow where synced
            assert (target, manual, command) == (
                "active",
                "manual_view",
                "view.set_anchor",
            )
            assert hasattr(ViewControl, command.removeprefix("view."))
            assert action["check_if"] == ("is_active_param_set_to", "anchor", anchor)

    @pytest.mark.parametrize(
        ("name", "key", "steps"),
        [
            ("Move Left", "Alt+Left", (-1, 0)),
            ("Move Right", "Alt+Right", (1, 0)),
            ("Move Up", "Alt+Up", (0, -1)),
            ("Move Down", "Alt+Down", (0, 1)),
        ],
    )
    def test_the_moves_are_on_alt_and_the_arrows(self, name, key, steps):
        action = ACTIONS[name]

        assert action["key"] == key
        assert action["func"] == ("active", "manual_view", "view.shift_by", *steps)
        assert name in _submenu("video_active", "Position")

        all_videos = ACTIONS[f"{name} [ALL]"]

        assert all_videos["key"] == f"Shift+{key}"
        assert all_videos["func"] == ("all", "shift_by", *steps)
        assert f"{name} [ALL]" in _all_videos_submenu("Position")

    def test_past_the_edges_is_a_toggle_after_the_moves(self):
        position = _submenu("video_active", "Position")
        action = ACTIONS["Move Past Edges"]

        assert position[position.index("Move Down") + 1] == "Move Past Edges"
        assert action["func"] == ("active", "view.toggle_shift_past_edges")
        assert action["check_if"] == (
            "is_active_param_set_to",
            "is_shift_past_edges",
            True,
        )
        assert hasattr(ViewControl, "toggle_shift_past_edges")

        all_videos = _all_videos_submenu("Position")

        assert all_videos[all_videos.index("Move Down [ALL]") + 1] == (
            "Move Past Edges",
            "Move Past Edges On [ALL]",
            "Move Past Edges Off [ALL]",
        )
        _assert_set_for_all("Move Past Edges", "is_shift_past_edges")

    def test_the_dialog_is_next_to_the_reset(self):
        position = _submenu("video_active", "Position")
        action = ACTIONS["Set Position"]

        assert position[position.index("Position Reset") - 1] == "Set Position"
        assert action["func"] == "position_dialog"
        assert action["show_if"] == "is_active_has_video"

    def test_the_reset_is_last(self):
        assert _submenu("video_active", "Position")[-1] == "Position Reset"
        assert ACTIONS["Position Reset"]["func"] == (
            "active",
            "manual_view",
            "view.shift_reset",
        )
        assert _all_videos_submenu("Position")[-1] == "Position Reset [ALL]"

    def test_every_video_can_be_aligned_at_once(self):
        position = _all_videos_submenu("Position")

        anchors = [ACTIONS[name]["func"] for name in position[1:10]]

        assert anchors == [("all", "set_anchor", a) for a in VideoAnchor]

    def test_zooming_to_the_cursor_is_a_toggle_at_the_bottom_of_zoom(self):
        action = ACTIONS["Zoom to Cursor"]

        assert _submenu("video_active", "Zoom")[-2:] == ("---", "Zoom to Cursor")
        assert action["func"] == ("active", "view.toggle_zoom_to_cursor")
        assert action["check_if"] == (
            "is_active_param_set_to",
            "is_zoom_to_cursor",
            True,
        )
        assert action["show_if"] == "is_active_has_video"
        assert hasattr(ViewControl, "toggle_zoom_to_cursor")

    def test_a_selection_to_zoom_to_is_picked_for_from_zoom(self):
        """The next drag over a video selects; see ZoomSelectManager."""

        from gridplayer.player.managers.zoom_select import ZoomSelectManager

        action = ACTIONS["Zoom to Selection"]
        zoom = _submenu("video_active", "Zoom")

        assert zoom.index("Zoom to Selection") == zoom.index("Zoom Reset") - 1
        assert action["func"] == "arm_zoom_selection"
        assert action["show_if"] == "is_active_has_video"
        assert "key" not in action
        assert "keys" not in action
        assert "arm_zoom_selection" in ZoomSelectManager(context=None).commands

    def test_every_video_can_be_set_to_zoom_to_the_cursor_or_not(self):
        assert _all_videos_submenu("Zoom")[-2:] == (
            "---",
            ("Zoom to Cursor", "Zoom to Cursor On [ALL]", "Zoom to Cursor Off [ALL]"),
        )
        _assert_set_for_all("Zoom to Cursor", "is_zoom_to_cursor")

    def test_every_video_can_be_set_to_loop_at_random_or_not(self):
        loop = next(
            item
            for item in _all_videos_section("Playback")
            if isinstance(item, tuple) and item[0] == "Loop"
        )

        assert loop[1] == (
            "Random Loop",
            "Random Loop On [ALL]",
            "Random Loop Off [ALL]",
        )
        _assert_set_for_all(
            "Random Loop", "is_start_random", owner=LoopControl, method="set_random"
        )

    def test_the_old_flips_for_all_are_gone(self):
        """Each video flipped its own way: mixed, they stayed mixed."""

        for name in ("Zoom to Cursor", "Move Past Edges", "Random Loop"):
            assert f"{name} [ALL]" not in ACTIONS


def _block(anchor=VideoAnchor.CENTER, shift=NO_SHIFT, is_shift_past_edges=False):
    block = Mock(spec=VideoBlock)
    block.video_params = Video(
        uri=URI, anchor=anchor, shift=shift, is_shift_past_edges=is_shift_past_edges
    )
    block.video_tracks = [0]
    block.is_video_initialized = True
    block.video_driver = Mock()
    block.view = ViewControl(block)
    return block


class TestOnOneVideo:
    def test_aligning_puts_the_picture_there(self):
        block = _block()

        block.view.set_anchor(VideoAnchor.TOP)

        assert block.video_params.anchor == VideoAnchor.TOP
        block.video_driver.set_anchor.assert_called_once_with(VideoAnchor.TOP)

    def test_aligning_lets_go_of_a_move_made_before(self):
        block = _block(shift=VideoShift(40, -20))

        block.view.set_anchor(VideoAnchor.BOTTOM)

        assert block.video_params.shift == NO_SHIFT
        block.video_driver.set_shift.assert_called_once_with(NO_SHIFT)
        block.info_change.emit.assert_not_called()

    def test_a_move_goes_where_the_picture_can(self):
        block = _block()
        block.video_driver.shifted_by.return_value = VideoShift(54, 0)

        block.view.shift_by(1, 0)

        block.video_driver.shifted_by.assert_called_once_with(1, 0)
        block.video_driver.set_shift.assert_called_once_with(VideoShift(54, 0))
        assert block.video_params.shift == VideoShift(54, 0)
        block.info_change.emit.assert_called_once_with("Position: X54 Y0")

    def test_a_move_that_goes_nowhere_says_so_all_the_same(self):
        block = _block(shift=VideoShift(420, 0))
        block.video_driver.shifted_by.return_value = VideoShift(420, 0)

        block.view.shift_by(1, 0)

        block.video_driver.set_shift.assert_not_called()
        block.info_change.emit.assert_called_once_with("Position: X420 Y0")

    def test_a_drag_takes_it_along_quietly(self):
        """The whole way, not a word till the drag is let go of."""

        block = _block()
        block.video_driver.dragged_shift.return_value = (VideoShift(-7, 3), (0.5, 0))

        left_over = block.view.pan_by(-8.0, 2.5)

        block.video_driver.dragged_shift.assert_called_once_with(-8.0, 2.5)
        block.video_driver.set_shift.assert_called_once_with(VideoShift(-7, 3))
        assert block.video_params.shift == VideoShift(-7, 3)
        assert left_over == (0.5, 0)
        block.info_change.emit.assert_not_called()

    def test_the_reset_brings_it_back_to_the_alignment(self):
        block = _block(anchor=VideoAnchor.TOP, shift=VideoShift(0, -30))

        block.view.shift_reset()

        assert block.video_params.anchor == VideoAnchor.TOP
        assert block.video_params.shift == NO_SHIFT

    def test_it_can_be_let_past_the_edges(self):
        block = _block()
        block.video_driver.shifted_by.return_value = NO_SHIFT

        block.view.toggle_shift_past_edges()

        assert block.video_params.is_shift_past_edges
        block.video_driver.set_shift_past_edges.assert_called_once_with(True)

    def test_kept_within_them_again_it_stays_where_they_hold_it(self):
        block = _block(shift=VideoShift(0, -960), is_shift_past_edges=True)
        block.video_driver.shifted_by.return_value = VideoShift(0, -420)

        block.view.toggle_shift_past_edges()

        assert not block.video_params.is_shift_past_edges
        block.video_driver.set_shift_past_edges.assert_called_once_with(False)
        block.video_driver.shifted_by.assert_called_once_with(0, 0)
        assert block.video_params.shift == VideoShift(0, -420)
        block.info_change.emit.assert_not_called()

    def test_a_stopped_video_keeps_it_for_when_it_plays(self):
        """Set for every video at once: one stopped has no player to tell."""

        block = _block()
        block.video_driver = None
        block.is_video_initialized = False
        block.video_tracks = []

        block.view.set_shift_past_edges(True)

        assert block.video_params.is_shift_past_edges

    def test_one_still_loading_gets_it_into_its_view(self):
        block = _block()
        block.is_video_initialized = False
        block.video_tracks = []

        block.view.set_shift_past_edges(True)

        assert block.video_params.is_shift_past_edges
        block.video_driver.set_shift_past_edges.assert_called_once_with(True)
        # where it stands is worked out once there is a picture to place
        block.video_driver.shifted_by.assert_not_called()

    def test_a_video_without_a_picture_is_left_alone(self):
        block = _block()
        block.video_tracks = []

        block.view.set_anchor(VideoAnchor.TOP)
        block.view.shift_by(1, 0)

        assert block.video_params.anchor == VideoAnchor.CENTER
        block.video_driver.set_anchor.assert_not_called()
        block.video_driver.shifted_by.assert_not_called()


def _zooming_block(is_zoom_to_cursor=True, scale=1.0, shift=NO_SHIFT, focus=(600, 300)):
    # the steps as they come, whatever this machine has them set to
    PlaylistSettings().set("playlist/zoom_step", 10)
    PlaylistSettings().set("playlist/zoom_proportional", False)

    block = Mock(spec=VideoBlock)
    block.video_params = Video(
        uri=URI, scale=scale, shift=shift, is_zoom_to_cursor=is_zoom_to_cursor
    )
    block.video_tracks = [0]
    block.is_video_initialized = True
    block.video_driver = Mock()
    block.video_driver.zoomed_shift.return_value = VideoShift(-90, 90)
    block.video_driver.selection_zoom.return_value = (3.0, VideoShift(240, 240))
    block.video_driver.pos.return_value = QPoint(0, 0)
    block.view = ViewControl(block)
    block.view._zoom_focus = Mock(return_value=focus)
    return block


class TestZoomingToTheCursor:
    def test_it_zooms_and_moves_the_picture_in_one_go(self):
        block = _zooming_block()

        block.view.scale_increase()

        block.video_driver.zoomed_shift.assert_called_once_with(1.1, (600, 300))
        block.video_driver.set_zoom.assert_called_once_with(1.1, VideoShift(-90, 90))
        block.video_driver.set_scale.assert_not_called()
        assert block.video_params.scale == 1.1
        assert block.video_params.shift == VideoShift(-90, 90)
        block.info_change.emit.assert_called_once_with("Zoom: 1.1")

    def test_out_as_well_as_in(self):
        block = _zooming_block(scale=2.0)

        block.view.scale_decrease()

        block.video_driver.zoomed_shift.assert_called_once_with(1.9, (600, 300))
        assert block.video_params.scale == 1.9

    def test_with_the_pointer_elsewhere_it_zooms_about_the_alignment(self):
        block = _zooming_block(shift=VideoShift(20, 0), focus=None)

        block.view.scale_increase()

        block.video_driver.set_scale.assert_called_once_with(1.1)
        block.video_driver.zoomed_shift.assert_not_called()
        assert block.video_params.shift == VideoShift(20, 0)

    def test_as_far_as_it_goes_it_does_not_move(self):
        block = _zooming_block(scale=MAX_SCALE)

        block.view.scale_increase()

        block.video_driver.zoomed_shift.assert_not_called()
        block.video_driver.set_scale.assert_called_once_with(MAX_SCALE)

    def test_the_reset_puts_the_picture_back_in_its_place(self):
        block = _zooming_block(scale=3.0, shift=VideoShift(-90, 90), focus=None)

        block.view.scale_reset()

        block.video_driver.set_zoom.assert_called_once_with(1.0, NO_SHIFT)
        assert block.video_params.scale == 1.0
        assert block.video_params.shift == NO_SHIFT

    def test_zoomed_about_the_alignment_the_reset_leaves_a_move_alone(self):
        block = _zooming_block(
            is_zoom_to_cursor=False, scale=3.0, shift=VideoShift(-90, 90)
        )

        block.view.scale_reset()

        block.video_driver.set_scale.assert_called_once_with(1.0)
        block.video_driver.set_zoom.assert_not_called()
        assert block.video_params.shift == VideoShift(-90, 90)

    def test_it_can_be_switched_on_and_off(self):
        block = _zooming_block(is_zoom_to_cursor=False)

        block.view.toggle_zoom_to_cursor()
        assert block.video_params.is_zoom_to_cursor

        block.view.toggle_zoom_to_cursor()
        assert not block.video_params.is_zoom_to_cursor

    def test_a_video_without_a_picture_is_left_alone(self):
        block = _zooming_block()
        block.video_tracks = []

        block.view.scale_increase()
        block.view.toggle_zoom_to_cursor()

        block.video_driver.zoomed_shift.assert_not_called()
        assert block.video_params.is_zoom_to_cursor

    def test_a_stopped_video_keeps_it_for_when_it_plays(self):
        block = _zooming_block(is_zoom_to_cursor=False)
        block.video_driver = None
        block.is_video_initialized = False
        block.video_tracks = []

        block.view.set_zoom_to_cursor(True)

        assert block.video_params.is_zoom_to_cursor


class TestZoomingToASelection:
    def test_it_zooms_and_moves_the_picture_in_one_go(self):
        block = _zooming_block(is_zoom_to_cursor=False)

        block.view.zoom_to_selection(QRect(100, 100, 300, 300))

        block.video_driver.selection_zoom.assert_called_once_with((100, 100, 300, 300))
        block.video_driver.set_zoom.assert_called_once_with(3.0, VideoShift(240, 240))
        assert block.video_params.scale == 3.0
        assert block.video_params.shift == VideoShift(240, 240)
        block.info_change.emit.assert_called_once_with("Zoom: 3.0")

    def test_the_selection_is_taken_to_the_frame_s_pixels(self):
        block = _zooming_block()
        block.video_driver.pos.return_value = QPoint(10, 20)

        block.view.zoom_to_selection(QRect(100, 100, 300, 200))

        block.video_driver.selection_zoom.assert_called_once_with((90, 80, 300, 200))

    def test_with_nothing_to_zoom_to_nothing_changes(self):
        block = _zooming_block(shift=VideoShift(20, 0))
        block.video_driver.selection_zoom.return_value = None

        block.view.zoom_to_selection(QRect(0, 0, 50, 50))

        block.video_driver.set_zoom.assert_not_called()
        block.info_change.emit.assert_not_called()
        assert block.video_params.shift == VideoShift(20, 0)
        assert not block.view._is_zoomed_to_selection

    def test_the_reset_puts_the_picture_back_in_its_place(self):
        """As zoomed about the pointer: where it stands is the zoom's doing."""

        block = _zooming_block(is_zoom_to_cursor=False)

        block.view.zoom_to_selection(QRect(100, 100, 300, 300))
        block.view.scale_reset()

        block.video_driver.set_zoom.assert_called_with(1.0, NO_SHIFT)
        block.video_driver.set_scale.assert_not_called()
        assert block.video_params.shift == NO_SHIFT

    def test_moved_on_after_it_the_reset_still_puts_it_back(self):
        block = _zooming_block(is_zoom_to_cursor=False)

        block.view.zoom_to_selection(QRect(100, 100, 300, 300))
        block.view.set_shift(VideoShift(300, 200))
        block.view.scale_reset()

        block.video_driver.set_zoom.assert_called_with(1.0, NO_SHIFT)

    def test_once_reset_the_next_reset_leaves_a_move_alone(self):
        block = _zooming_block(is_zoom_to_cursor=False)

        block.view.zoom_to_selection(QRect(100, 100, 300, 300))
        block.view.scale_reset()
        block.view.set_shift(VideoShift(-90, 90))
        block.view.scale_reset()

        block.video_driver.set_scale.assert_called_once_with(1.0)
        assert block.video_params.shift == VideoShift(-90, 90)

    @pytest.mark.parametrize(
        "put_back",
        [
            lambda block: block.view.shift_reset(),
            lambda block: block.view.set_anchor(VideoAnchor.TOP),
        ],
    )
    def test_put_back_in_its_place_the_zoom_s_reset_is_the_usual_one(self, put_back):
        block = _zooming_block(is_zoom_to_cursor=False)

        block.view.zoom_to_selection(QRect(100, 100, 300, 300))
        put_back(block)
        block.view.set_shift(VideoShift(-90, 90))
        block.view.scale_reset()

        block.video_driver.set_scale.assert_called_once_with(1.0)

    def test_a_video_without_a_picture_is_left_alone(self):
        block = _zooming_block()
        block.video_tracks = []

        block.view.zoom_to_selection(QRect(100, 100, 300, 300))

        block.video_driver.selection_zoom.assert_not_called()


def _manager(*videos):
    context = SimpleNamespace()
    manager = VideoBlocksManager(context=context, parent=None)
    # in place of the empty one it starts with
    context.video_blocks = [SimpleNamespace(video_params=video) for video in videos]
    return manager


class TestForEveryVideo:
    """A choice made for all of them is the same for every one."""

    @pytest.mark.parametrize(
        "command", ["set_zoom_to_cursor", "set_shift_past_edges", "set_loop_random"]
    )
    @pytest.mark.parametrize("value", [True, False])
    def test_each_one_is_told_what_to_have(self, command, value):
        manager = _manager()
        told = Mock()
        getattr(manager, f"all_{command}").connect(told)

        manager.cmd_all(command, value)

        told.assert_called_once_with(value)

    def test_the_choice_they_all_have_is_ticked(self):
        manager = _manager(
            Video(uri=URI, is_zoom_to_cursor=True),
            Video(uri=URI, is_zoom_to_cursor=True),
        )

        assert manager.is_all_videos_param_set_to("is_zoom_to_cursor", True)
        assert not manager.is_all_videos_param_set_to("is_zoom_to_cursor", False)

    def test_neither_is_ticked_while_they_differ(self):
        manager = _manager(
            Video(uri=URI, is_zoom_to_cursor=True),
            Video(uri=URI, is_zoom_to_cursor=False),
        )

        assert not manager.is_all_videos_param_set_to("is_zoom_to_cursor", True)
        assert not manager.is_all_videos_param_set_to("is_zoom_to_cursor", False)

    def test_neither_is_ticked_with_no_videos(self):
        manager = _manager()

        assert not manager.is_all_videos_param_set_to("is_zoom_to_cursor", False)

    def test_one_between_videos_does_not_count(self):
        """Reloading, it has no video for a moment."""

        manager = _manager(Video(uri=URI, is_start_random=True), None)

        assert manager.is_all_videos_param_set_to("is_start_random", True)

    def test_a_video_loops_at_random_as_it_is_told(self):
        block = Mock(spec=VideoBlock)
        block.video_params = Video(uri=URI)
        block.is_live = False
        block.loop = LoopControl(block)

        block.loop.set_random(True)
        assert block.video_params.is_start_random

        block.loop.toggle_random()
        assert not block.video_params.is_start_random


def _focus(
    monkeypatch, pointer, menu_pos=None, is_zoom_to_cursor=True, is_visible=True
):
    """Where a 400x300 cell at (100, 100) on the screen zooms about."""

    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI, is_zoom_to_cursor=is_zoom_to_cursor)
    block._ctx = SimpleNamespace(context_menu_pos=menu_pos)
    block.isVisible.return_value = is_visible
    block.rect.return_value = QRect(0, 0, 400, 300)
    block.mapFromGlobal.side_effect = lambda pos: pos - QPoint(100, 100)
    block.video_driver = Mock()
    block.video_driver.mapFromGlobal.side_effect = lambda pos: pos - QPoint(100, 100)

    monkeypatch.setattr(
        video_block_view_module, "QCursor", Mock(pos=Mock(return_value=pointer))
    )

    return ViewControl(block)._zoom_focus()


class TestWhereTheZoomGoesAbout:
    def test_the_pointer_over_the_video(self, monkeypatch):
        assert _focus(monkeypatch, QPoint(250, 180)) == (150, 80)

    def test_nowhere_with_the_pointer_outside_the_cell(self, monkeypatch):
        assert _focus(monkeypatch, QPoint(550, 180)) is None

    def test_nowhere_where_the_video_zooms_about_the_alignment(self, monkeypatch):
        assert _focus(monkeypatch, QPoint(250, 180), is_zoom_to_cursor=False) is None

    def test_nowhere_for_a_video_out_of_sight(self, monkeypatch):
        """Single mode hides the rest where they were: not under the pointer."""

        assert _focus(monkeypatch, QPoint(250, 180), is_visible=False) is None

    def test_where_the_menu_was_opened_for_a_zoom_picked_from_it(self, monkeypatch):
        # the menu's item is off to the side, outside the cell
        focus = _focus(monkeypatch, QPoint(700, 180), menu_pos=QPoint(150, 120))

        assert focus == (50, 20)

    def test_nowhere_for_a_cell_the_menu_was_not_opened_over(self, monkeypatch):
        focus = _focus(monkeypatch, QPoint(250, 180), menu_pos=QPoint(700, 120))

        assert focus is None


def test_the_menu_says_where_it_was_opened_while_it_is_open():
    context = SimpleNamespace(video_blocks=[], active_block=None, commands=Mock())
    manager = MenuManager(context=context, parent=None)
    seen = []

    menu = Mock()
    menu.exec_.side_effect = lambda _pos: seen.append(context.context_menu_pos)
    manager.make_menu = Mock(return_value=menu)

    event = Mock()
    event.globalPos.return_value = QPoint(150, 120)

    manager.contextMenuEvent(event)

    assert seen == [QPoint(150, 120)]
    assert context.context_menu_pos is None


def test_a_snapshot_puts_the_picture_back_where_it_was():
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block._default_title = "a"
    mock_block_parts(block)

    snapshot = Video(
        uri=URI,
        anchor=VideoAnchor.RIGHT,
        shift=VideoShift(0, 25),
        is_shift_past_edges=True,
    )
    VideoBlock.apply_snapshot(block, snapshot)

    block.view.set_anchor.assert_called_once_with(VideoAnchor.RIGHT)
    block.view.set_shift_past_edges.assert_called_once_with(True)
    block.view.set_shift.assert_called_once_with(VideoShift(0, 25), is_silent=True)


def test_a_snapshot_puts_back_what_the_zoom_goes_about():
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block._default_title = "a"
    mock_block_parts(block)

    VideoBlock.apply_snapshot(block, Video(uri=URI, is_zoom_to_cursor=True))

    block.view.set_zoom_to_cursor.assert_called_once_with(True)


def _track(size, orientation=VideoTransform.NONE):
    return VideoTrack(
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        video_dimensions=size,
        fps=None,
        orientation=orientation,
    )


def _drawn_at(frame, x, y):
    """Where a frame point is drawn in the pane."""

    source_x, source_y, source_w, source_h = frame.view_placement().source
    shown_x, shown_y, shown_w, shown_h = frame._shown_picture_rect()

    return (
        shown_x + (x - source_x) * shown_w / source_w,
        shown_y + (y - source_y) * shown_h / source_h,
    )


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame(shift=NO_SHIFT, anchor=VideoAnchor.CENTER, is_shift_past_edges=False):
    """A 1920x1080 video in a 900x900 pane: 1080 of its 1920 across on show."""

    frame = _StubFrame(vlc_options=[])
    frame.resize(900, 900)
    frame.media = MagicMock()
    frame.media.is_audio_only = False
    frame.media.cur_video_track = _track((1920, 1080))
    frame._view = ViewParams(
        anchor=anchor, shift=shift, is_shift_past_edges=is_shift_past_edges
    )
    return frame


class TestMovingInThePane:
    def test_a_step_is_a_twentieth_of_what_is_on_show(self):
        assert abs(_frame().shifted_by(1, 0).X) == 54
        assert abs(_frame().shifted_by(-2, 0).X) == 108

    def test_right_brings_more_of_a_bigger_picture_s_right_side_in(self):
        """Like looking further right: the picture itself slides left."""

        assert _frame().shifted_by(1, 0) == VideoShift(-54, 0)
        assert _frame().shifted_by(-1, 0) == VideoShift(54, 0)

    def test_down_takes_a_smaller_picture_down(self):
        frame = _frame()
        frame._view = frame._view._replace(aspect=VideoAspect.NONE)

        # 900x506.25 letterboxed; 96x54 frame pixels a step
        assert frame.shifted_by(0, 1) == VideoShift(0, 54)
        assert frame.shifted_by(0, -1) == VideoShift(0, -54)

    def test_it_stops_at_the_edge(self):
        # 420 frame pixels of room either side of the middle
        assert _frame(VideoShift(-400, 0)).shifted_by(1, 0) == VideoShift(-420, 0)

    def test_there_is_nowhere_to_go_where_it_fits_the_pane(self):
        assert _frame().shifted_by(0, 1) == NO_SHIFT

    def test_it_comes_back_from_the_edge_at_once(self):
        """Not after as many presses as it was pushed past the edge: from
        where it stopped, -420, to the next whole step."""

        assert _frame(VideoShift(-5000, 0)).shifted_by(-1, 0) == VideoShift(-378, 0)

    def test_back_the_other_way_it_is_where_it_was(self):
        for is_shift_past_edges in (False, True):
            frame = _frame(is_shift_past_edges=is_shift_past_edges)

            for steps in (1, 1, 1, -1, -1, -1, -1, 1):
                frame.set_shift(frame.shifted_by(steps, 0))

            assert frame._view.shift == NO_SHIFT

    def test_from_an_edge_it_comes_back_to_the_anchor(self):
        frame = _frame(VideoShift(-5000, 0))

        for _ in range(8):
            frame.set_shift(frame.shifted_by(-1, 0))

        assert frame._view.shift == NO_SHIFT

    def test_past_the_edges_a_step_goes_as_far(self):
        """The part on show gets smaller as the picture goes past an edge;
        the step does not."""

        frame = _frame(is_shift_past_edges=True)
        frame._view = frame._view._replace(aspect=VideoAspect.NONE)
        moved = []

        for _ in range(12):
            before = frame._view.shift.Y
            frame.set_shift(frame.shifted_by(0, -1))
            moved.append(before - frame._view.shift.Y)

        # 1080 of it on show at 5%, till it stops with half of it out
        assert set(moved[:10]) == {54}

    def test_it_goes_from_the_alignment(self):
        """Aligned right, the right side is on show already: there is only
        left to look."""

        frame = _frame(anchor=VideoAnchor.RIGHT)

        assert frame.shifted_by(1, 0) == NO_SHIFT
        assert frame.shifted_by(-1, 0) == VideoShift(54, 0)

    def test_it_is_nowhere_to_go_before_the_video_has_a_size(self):
        frame = _frame(VideoShift(10, 0))
        frame.media.cur_video_track.video_dimensions = (0, 0)

        assert frame.shifted_by(1, 0) == VideoShift(10, 0)

    def test_past_the_edges_it_goes_on(self):
        frame = _frame(VideoShift(-400, 0), is_shift_past_edges=True)

        # onto the next whole step: 8 of 54
        assert frame.shifted_by(1, 0) == VideoShift(-432, 0)

    def test_past_the_edges_it_stops_with_half_the_pane_left_covered(self):
        # 450 of the 900 pane pixels, 960 frame pixels on from the middle
        frame = _frame(VideoShift(-5000, 0), is_shift_past_edges=True)

        assert frame.shifted_by(0, 0) == VideoShift(-960, 0)

    def test_the_view_carries_it(self):
        frame = _frame()
        frame.set_anchor(VideoAnchor.TOP_LEFT)
        frame.set_shift(VideoShift(-5, 0))
        frame.set_shift_past_edges(True)

        assert frame._view.anchor == VideoAnchor.TOP_LEFT
        assert frame._view.shift == VideoShift(-5, 0)
        assert frame._view.is_shift_past_edges


class TestZoomingInThePane:
    @pytest.fixture(autouse=True)
    def _drawn_where_the_view_has_it(self):
        """No margin: the picture is where the view puts it, as on the
        software drivers. See TestTheHardwareSurface for one drawn bigger."""

        Settings().set("internal/hw_crop_border_offset", HWCropBorderOffset.DISABLED)

    @pytest.fixture
    def kept(self, monkeypatch):
        """What each zoom about a point was handed to keep."""

        handed = []
        real = vlc_base.calc_zoomed_shift

        def _spy(*args, **kwargs):
            handed.append(args[-1])
            return real(*args, **kwargs)

        monkeypatch.setattr(vlc_base, "calc_zoomed_shift", _spy)

        return handed

    @staticmethod
    def _zoom(frame, scale, focus=(600, 300)):
        frame.set_zoom(scale, frame.zoomed_shift(scale, focus))

    def test_about_a_point_the_point_stays(self):
        # (1140, 360) under (600, 300); see TestZoomedShift
        assert _frame().zoomed_shift(2.0, (600, 300)) == VideoShift(-90, 90)

    def test_a_selection_goes_into_the_middle(self):
        # see TestSelectionZoom
        assert _frame().selection_zoom((100, 100, 300, 300)) == (
            3.0,
            VideoShift(240, 240),
        )

    def test_selected_is_over_the_picture_within_the_pane(self):
        """1600x900 from -350 across, cut to the pane."""

        assert _frame().shown_picture_area() == (0, 0, 900, 900)

    def test_letterboxed_it_is_over_the_picture_alone(self):
        """506.25 tall from 196.875 down, as VLC places it in whole pixels."""

        frame = _frame()
        frame._view = frame._view._replace(aspect=VideoAspect.NONE)

        assert frame.shown_picture_area() == pytest.approx(
            (0, 196.875, 900, 506.25), abs=2
        )

    def test_the_picture_is_zoomed_and_moved_in_one_go(self):
        frame = _frame()
        frame.adjust_view = Mock()

        frame.set_zoom(2.0, VideoShift(-90, 90))

        frame.adjust_view.assert_called_once_with()
        assert frame._view.scale == 2.0
        assert frame._view.shift == VideoShift(-90, 90)

    def test_the_next_zoom_about_the_same_point_keeps_the_same_one(self, kept):
        frame = _frame()

        self._zoom(frame, 1.1)
        self._zoom(frame, 1.2)

        assert kept[0] == (None, None)
        assert kept[1] == pytest.approx((1140, 360))

    def test_with_the_pointer_moved_it_starts_again(self, kept):
        frame = _frame()

        self._zoom(frame, 1.1)
        self._zoom(frame, 1.2, focus=(601, 300))

        assert kept[1] == (None, None)

    def test_with_the_picture_moved_in_between_it_starts_again(self, kept):
        frame = _frame()

        self._zoom(frame, 1.1)
        frame.set_shift(frame.shifted_by(1, 0))
        self._zoom(frame, 1.2)

        assert kept[1] == (None, None)

    def test_with_the_pane_resized_in_between_it_starts_again(self, kept):
        frame = _frame()

        self._zoom(frame, 1.1)
        frame.resize(900, 800)
        self._zoom(frame, 1.2)

        assert kept[1] == (None, None)


class TestTheHardwareSurface:
    """VLC fills its window with the picture: the window is what places it."""

    @pytest.fixture(autouse=True)
    def _margin(self, monkeypatch):
        Settings().set("internal/hw_crop_border_offset", HWCropBorderOffset.PX8)

        # on Windows the window grows a little more for VLC's picture in it
        # to be whole 4-row blocks: see test_vlc_picture_is_whole_blocks
        monkeypatch.setattr(vlc_base.env, "IS_WINDOWS", False)

    def test_vlc_picture_is_whole_blocks(self, monkeypatch):
        """1080x1080 of the frame on show in a 900x901 pane: in the 916x917
        window the margin makes, VLC's picture would be 915x917, 917 tall,
        a row past a whole block; grown to 918x920 it is 918x920."""
        monkeypatch.setattr(vlc_base.env, "IS_WINDOWS", True)
        frame = _frame()
        frame.resize(900, 901)

        frame.adjust_view()

        surface = frame.video_surface.geometry()
        geometry = calc_view_geometry((1920, 1080), (900, 901), frame._view)
        picture = calc_vlc_picture(
            (1920, 1080), geometry, (surface.width(), surface.height())
        )
        assert picture[3] % 4 == 0
        assert surface.getRect() == (-9, -9, 918, 920)

    def test_it_covers_the_pane_where_the_picture_does(self):
        frame = _frame()

        frame.adjust_view()

        assert frame.video_surface.geometry().getRect() == (-8, -8, 916, 916)

    def test_it_is_over_the_picture_where_that_is_against_a_side(self):
        # 900x506.25 at the top of the pane
        frame = _frame(anchor=VideoAnchor.TOP)
        frame._view = frame._view._replace(aspect=VideoAspect.NONE)

        frame.adjust_view()

        assert frame.video_surface.geometry().getRect() == (-8, -8, 916, 523)

    def test_it_is_over_the_picture_of_a_file_shown_on_its_side(self):
        """VLC turns it before showing it: 1080x1920 as it is on show, which
        stands 506.25x900 against the left side of the pane."""
        frame = _frame(anchor=VideoAnchor.LEFT)
        frame.media.cur_video_track = _track((1920, 1080), VideoTransform.ROTATE_90)
        frame._view = frame._view._replace(aspect=VideoAspect.NONE)

        frame.adjust_view()

        assert frame.video_surface.geometry().getRect() == (-8, -8, 523, 916)

    def test_it_is_over_all_of_a_picture_vlc_turns(self):
        """VLC crops a picture it turns wrong: all of it is drawn, and the
        pane cuts it. On its side it covers 900x900 at 900x1600."""
        frame = _frame()
        frame.media.cur_video_track = _track((1920, 1080), VideoTransform.ROTATE_90)

        frame.adjust_view()

        assert frame.video_clip.geometry().getRect() == (0, 0, 900, 900)
        assert frame.video_surface.geometry().getRect() == (-8, -358, 916, 1616)

    def test_it_is_cut_to_what_a_crop_keeps_of_a_picture_vlc_turns(self):
        """All of it is drawn, what the crop takes off too. On its side, the
        1080x960 kept fits 900x900 at 900x800, 50 down; the 480 cut off
        above it is 400 more up, and all of it is 900x1600."""
        frame = _frame()
        frame.media.cur_video_track = _track((1920, 1080), VideoTransform.ROTATE_90)
        frame._view = frame._view._replace(
            aspect=VideoAspect.NONE, crop=VideoCrop(0, 480, 0, 480)
        )

        frame.adjust_view()

        assert frame.video_clip.geometry().getRect() == (0, 50, 900, 800)
        # (-8, -358) in the pane
        assert frame.video_surface.geometry().getRect() == (-8, -408, 916, 1616)
        assert frame.native_surface_rect().getRect() == (0, 50, 900, 800)
        assert frame.screenshot_view().view == frame._view

    def test_a_screenshot_of_a_picture_vlc_turns_is_cut_here(self):
        frame = _frame()
        frame.media.cur_video_track = _track((1920, 1080), VideoTransform.ROTATE_90)

        view = frame.screenshot_view()

        assert view.view == frame._view
        assert view.frame_size == (1080, 1920)
        assert view.orientation == VideoTransform.ROTATE_90

    def test_a_screenshot_of_any_other_is_cut_by_vlc(self):
        view = _frame().screenshot_view()

        assert view.view is None
        assert view.orientation == VideoTransform.NONE

    def test_a_zoom_about_a_point_keeps_what_is_drawn_there(self):
        """VLC draws the picture 916/900 as big as the view has it, so what
        is on show at a point off the middle is what the view has a little
        nearer it. That stays under the point; zoomed about the point as
        the view has it, it would slide 15 pixels away at 4x."""

        frame = _frame()

        point = _drawn_at(frame, 1300, 300)

        frame.set_zoom(4.0, frame.zoomed_shift(4.0, point))

        # half a frame pixel: 900/1080 pane pixels each at 1x, drawn bigger
        assert _drawn_at(frame, 1300, 300) == pytest.approx(point, abs=1.75)

    def test_a_selection_is_fitted_into_the_cell_as_drawn(self):
        """Fitted as the view has it, it would be drawn 916/900 as big as
        the cell, and go past each side of it by 8 pixels."""

        frame = _frame()

        left, top = _drawn_at(frame, 1100, 200)
        right, bottom = _drawn_at(frame, 1400, 500)

        frame.set_zoom(*frame.selection_zoom((left, top, right - left, bottom - top)))

        left, top = _drawn_at(frame, 1100, 200)
        right, bottom = _drawn_at(frame, 1400, 500)

        assert min(left, top) >= -0.5
        assert max(right, bottom) <= 900.5
        # as big as it goes, in hundredths of the zoom
        assert right - left > 900 * (1 - 0.01 / 3.5)
        # off by half a frame pixel, 900/1080 pane pixels each at 1x, drawn
        # bigger
        assert ((left + right) / 2, (top + bottom) / 2) == pytest.approx(
            (450, 450), abs=1.5
        )

    def test_it_goes_where_the_picture_is_moved(self):
        frame = _frame(anchor=VideoAnchor.TOP)
        frame._view = frame._view._replace(aspect=VideoAspect.NONE)

        frame.set_shift(frame.shifted_by(0, 1))

        # 54 frame pixels down at 900/1920 pane pixels each: 25.3125 to
        # 531.5625, all of pixels 25 to 531 grown by the margin
        assert frame.video_surface.geometry().getRect() == (-8, 17, 916, 523)
