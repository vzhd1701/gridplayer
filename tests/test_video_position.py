"""Where a video's picture sits in its pane: against a side or corner, and
moved on from there.

The alignment says where the picture goes when there is room for it to go
somewhere: which part of it is cut off where it is bigger than the pane,
and where in the pane it stands where it is smaller. The position moves it
on from there, in video pixels like the crop, held within the edges.
"""

import json
from functools import partial
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.playlist import Playlist, PlaylistVideoDefaults
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.defaults_fields import VIDEO_FIELDS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.params.static import VideoAnchor, VideoAspect, VideoShift, ViewParams
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP

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


class TestPlaylistSettings:
    def test_the_alignment_sits_under_crop_in_the_video_section(self):
        keys = [f.settings_key for f in VIDEO_FIELDS]
        at = keys.index("video_defaults/crop")

        assert keys[at + 1] == "video_defaults/anchor"

        spec = VIDEO_FIELDS[at + 1]
        assert spec.section == "Video"
        assert spec.video_attr == "anchor"
        assert list(spec.combo_values()) == list(VideoAnchor)

    def test_there_is_no_default_for_the_position(self):
        """A place moved to in one video means nothing for another."""

        assert not [f for f in VIDEO_FIELDS if "shift" in f.settings_key]


def _submenu(section, name):
    video = next(
        item
        for item in SECTIONS[section]
        if isinstance(item, tuple) and item[0] == "Video"
    )
    return next(item for item in video if isinstance(item, tuple) and item[0] == name)


def _all_videos_submenu(name):
    all_videos = next(
        item
        for item in SECTIONS["video_all"]
        if isinstance(item, tuple) and item[0] == "[ALL]"
    )
    video = next(
        item for item in all_videos if isinstance(item, tuple) and item[0] == "Video"
    )
    return next(item for item in video if isinstance(item, tuple) and item[0] == name)


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

        anchors = [ACTIONS[name]["func"][2] for name in position[1:10]]

        assert anchors == list(VideoAnchor)
        assert position[10] == "---"

    def test_every_alignment_reaches_the_video_and_shows_what_is_in_force(self):
        position = _submenu("video_active", "Position")

        for name in position[1:10]:
            action = ACTIONS[name]
            target, command, anchor = action["func"]

            assert (target, command) == ("active", "set_anchor")
            assert hasattr(VideoBlock, command)
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
        assert action["func"] == ("active", "shift_by", *steps)
        assert name in _submenu("video_active", "Position")

        all_videos = ACTIONS[f"{name} [ALL]"]

        assert all_videos["key"] == f"Shift+{key}"
        assert all_videos["func"] == ("all", "shift_by", *steps)
        assert f"{name} [ALL]" in _all_videos_submenu("Position")

    def test_the_reset_is_last(self):
        assert _submenu("video_active", "Position")[-1] == "Position Reset"
        assert ACTIONS["Position Reset"]["func"] == ("active", "shift_reset")
        assert _all_videos_submenu("Position")[-1] == "Position Reset [ALL]"

    def test_every_video_can_be_aligned_at_once(self):
        position = _all_videos_submenu("Position")

        anchors = [ACTIONS[name]["func"] for name in position[1:10]]

        assert anchors == [("all", "set_anchor", a) for a in VideoAnchor]


def _block(anchor=VideoAnchor.CENTER, shift=NO_SHIFT):
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI, anchor=anchor, shift=shift)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block.video_driver = Mock()
    for name in ("set_anchor", "set_shift", "shift_by", "shift_reset"):
        setattr(block, name, partial(getattr(VideoBlock, name), block))
    return block


class TestOnOneVideo:
    def test_aligning_puts_the_picture_there(self):
        block = _block()

        block.set_anchor(VideoAnchor.TOP)

        assert block.video_params.anchor == VideoAnchor.TOP
        block.video_driver.set_anchor.assert_called_once_with(VideoAnchor.TOP)

    def test_aligning_lets_go_of_a_move_made_before(self):
        block = _block(shift=VideoShift(40, -20))

        block.set_anchor(VideoAnchor.BOTTOM)

        assert block.video_params.shift == NO_SHIFT
        block.video_driver.set_shift.assert_called_once_with(NO_SHIFT)
        block.info_change.emit.assert_not_called()

    def test_a_move_goes_where_the_picture_can(self):
        block = _block()
        block.video_driver.shifted_by.return_value = VideoShift(54, 0)

        block.shift_by(1, 0)

        block.video_driver.shifted_by.assert_called_once_with(1, 0)
        block.video_driver.set_shift.assert_called_once_with(VideoShift(54, 0))
        assert block.video_params.shift == VideoShift(54, 0)
        block.info_change.emit.assert_called_once_with("Position: X54 Y0")

    def test_a_move_that_goes_nowhere_says_so_all_the_same(self):
        block = _block(shift=VideoShift(420, 0))
        block.video_driver.shifted_by.return_value = VideoShift(420, 0)

        block.shift_by(1, 0)

        block.video_driver.set_shift.assert_not_called()
        block.info_change.emit.assert_called_once_with("Position: X420 Y0")

    def test_the_reset_brings_it_back_to_the_alignment(self):
        block = _block(anchor=VideoAnchor.TOP, shift=VideoShift(0, -30))

        block.shift_reset()

        assert block.video_params.anchor == VideoAnchor.TOP
        assert block.video_params.shift == NO_SHIFT

    def test_a_video_without_a_picture_is_left_alone(self):
        block = _block()
        block.video_tracks = []

        block.set_anchor(VideoAnchor.TOP)
        block.shift_by(1, 0)

        assert block.video_params.anchor == VideoAnchor.CENTER
        block.video_driver.set_anchor.assert_not_called()
        block.video_driver.shifted_by.assert_not_called()


def test_a_snapshot_puts_the_picture_back_where_it_was():
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block._default_title = "a"

    snapshot = Video(uri=URI, anchor=VideoAnchor.RIGHT, shift=VideoShift(0, 25))
    VideoBlock.apply_snapshot(block, snapshot)

    block.set_anchor.assert_called_once_with(VideoAnchor.RIGHT)
    block.set_shift.assert_called_once_with(VideoShift(0, 25), is_silent=True)


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame(shift=NO_SHIFT, anchor=VideoAnchor.CENTER):
    """A 1920x1080 video in a 900x900 pane: 1080 of its 1920 across on show."""

    frame = _StubFrame(vlc_options=[])
    frame.resize(900, 900)
    frame.media = MagicMock()
    frame.media.is_audio_only = False
    frame.media.cur_video_track.video_dimensions = (1920, 1080)
    frame._view = ViewParams(anchor=anchor, shift=shift)
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
        """Not after as many presses as it was pushed past the edge."""

        assert _frame(VideoShift(-5000, 0)).shifted_by(-1, 0) == VideoShift(-366, 0)

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

    def test_the_view_carries_it(self):
        frame = _frame()
        frame.set_anchor(VideoAnchor.TOP_LEFT)
        frame.set_shift(VideoShift(-5, 0))

        assert frame._view.anchor == VideoAnchor.TOP_LEFT
        assert frame._view.shift == VideoShift(-5, 0)
