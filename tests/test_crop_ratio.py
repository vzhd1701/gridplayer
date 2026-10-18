"""The shape a video's picture is cut to, as it is shown, out of the ones VLC
offers: or margins of its own, never both."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS
from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import When
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.params.static import VideoCrop, VideoTransform, ViewParams
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_view import ViewControl
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP

URI = "http://example.com/a.mp4"

NO_CROP = VideoCrop(0, 0, 0, 0)

# VLC's own, in its order
PRESETS = [
    "16:10",
    "16:9",
    "4:3",
    "1.85:1",
    "2.21:1",
    "2.35:1",
    "2.39:1",
    "5:3",
    "5:4",
    "1:1",
]


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _named(items, name):
    return next(i for i in items if isinstance(i, tuple) and i[0] == name)


def _crop_submenu():
    return list(_named(_named(SECTIONS["video_active"], "Video"), "Crop")[1:])


def _all_videos_crop_submenu():
    every = _named(SECTIONS["video_all"], "[ALL]")
    return list(_named(_named(every, "Video"), "Crop")[1:])


class TestTheMenu:
    def test_off_then_vlc_s_shapes_then_custom_then_the_nudges(self):
        items = _crop_submenu()

        assert items[: len(PRESETS) + 4] == [
            "Crop List",
            "Crop Reset",
            *(f"Crop {ratio}" for ratio in PRESETS),
            "Set Crop",
            "---",
        ]
        assert items[len(PRESETS) + 4 :] == [
            "Crop Left +",
            "Crop Left -",
            "Crop Top +",
            "Crop Top -",
            "Crop Right +",
            "Crop Right -",
            "Crop Bottom +",
            "Crop Bottom -",
        ]

    def test_each_shape_reaches_the_video_and_is_ticked_when_in_force(self):
        for ratio in PRESETS:
            action = ACTIONS[f"Crop {ratio}"]

            assert action["title"] == ratio
            assert action["func"] == ("active", "view.set_crop_ratio", ratio)
            assert action["check_if"] == (
                "is_active_param_set_to",
                "crop_ratio",
                ratio,
            )
            assert action["is_choice"]

    def test_off_and_custom_are_ticked_too_and_keep_their_shortcut_names(self):
        off, custom = ACTIONS["Crop Reset"], ACTIONS["Set Crop"]

        assert off["func"] == ("active", "view.crop_off")
        assert off["check_if"] == "is_active_crop_off"
        assert off["keymap_title"] == "Crop Reset"
        assert custom["func"] == "crop_dialog"
        assert custom["check_if"] == "is_active_crop_custom"
        assert custom["keymap_title"] == "Set Crop"
        assert off["is_choice"]
        assert custom["is_choice"]

    def test_the_same_for_all_videos_but_custom(self):
        items = _all_videos_crop_submenu()

        assert items[: len(PRESETS) + 2] == [
            "Crop Reset [ALL]",
            *(f"Crop {ratio} [ALL]" for ratio in PRESETS),
            "---",
        ]
        assert [ACTIONS[f"Crop {r} [ALL]"]["func"] for r in PRESETS] == [
            ("all", "set_crop_ratio", ratio) for ratio in PRESETS
        ]
        assert hasattr(VideoBlocksManager, "all_set_crop_ratio")

    def test_each_nudge_for_all_is_there_once(self):
        items = [i for i in _all_videos_crop_submenu() if i != "---"]

        assert len(items) == len(set(items))


def _active(crop=NO_CROP, crop_ratio=""):
    block = SimpleNamespace(
        video_params=SimpleNamespace(crop=crop, crop_ratio=crop_ratio),
        list_crop_ratio="",
        is_video_initialized=True,
        video_tracks=[0],
    )
    manager = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    manager._ctx.active_block = block
    return manager


class TestTicked:
    def test_off_with_neither(self):
        assert _active().is_active_crop_off()
        assert not _active().is_active_crop_custom()

    def test_custom_with_margins(self):
        manager = _active(crop=VideoCrop(0, 8, 0, 8))

        assert manager.is_active_crop_custom()
        assert not manager.is_active_crop_off()

    def test_the_menu_can_ask(self):
        commands = _active().commands

        assert commands["is_active_crop_off"]
        assert commands["is_active_crop_custom"]

    def test_neither_with_a_shape(self):
        manager = _active(crop_ratio="4:3")

        assert not manager.is_active_crop_off()
        assert not manager.is_active_crop_custom()
        assert manager.is_active_param_set_to("crop_ratio", "4:3")


def _block(crop=NO_CROP, crop_ratio=""):
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI, crop=crop, crop_ratio=crop_ratio)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block.video_driver = Mock()
    block.list_aspect_ratio = ""
    block.list_crop_ratio = ""
    block.view = ViewControl(block)
    return block


class TestOnOneVideo:
    def test_picking_one_cuts_the_picture_so_and_its_margins_go(self):
        block = _block(crop=VideoCrop(5, 5, 5, 5))

        block.view.set_crop_ratio("4:3")

        assert block.video_params.crop_ratio == "4:3"
        assert block.video_params.crop == NO_CROP
        block.video_driver.set_crop_ratio.assert_called_once_with("4:3")
        block.info_change.emit.assert_called_once_with("Crop: 4:3")

    def test_none_is_said_as_off(self):
        block = _block()

        block.view.set_crop_ratio("")

        block.info_change.emit.assert_called_once_with("Crop: Off")

    def test_a_nudge_goes_on_from_the_shape_s_margins(self):
        block = _block(crop_ratio="4:3")
        block.video_driver.shown_crop.return_value = VideoCrop(240, 0, 240, 0)

        block.view.crop(0, 1, 0, 0)

        assert block.video_params.crop_ratio == ""
        assert block.video_params.crop == VideoCrop(240, 1, 240, 0)
        block.video_driver.set_crop.assert_called_once_with(VideoCrop(240, 1, 240, 0))

    def test_margins_of_its_own_are_asked_of_nobody(self):
        block = _block(crop=VideoCrop(1, 2, 3, 4))

        assert block.view.shown_crop() == VideoCrop(1, 2, 3, 4)
        block.video_driver.shown_crop.assert_not_called()

    def test_off_lets_go_of_the_shape(self):
        block = _block(crop_ratio="2.35:1")

        block.view.crop_reset()

        assert block.video_params.crop_ratio == ""
        block.video_driver.set_crop.assert_called_once_with(NO_CROP)


class TestSaved:
    def test_a_video_keeps_its_own(self):
        video = Video(uri=URI, crop_ratio="2.35:1")

        dumped = json.loads(Playlist(videos=[video]).dumps())["videos"][0]

        assert dumped["crop_ratio"] == "2.35:1"
        assert Video(uri=URI, crop_ratio=dumped["crop_ratio"]).crop_ratio == "2.35:1"

    @pytest.mark.parametrize("text", ["16:0", "wide", "100:1"])
    def test_one_that_is_no_shape_is_no_cut(self, text):
        assert Video(uri=URI, crop_ratio=text).crop_ratio == ""

    def test_with_both_the_shape_wins(self):
        video = Video(uri=URI, crop=VideoCrop(5, 5, 5, 5), crop_ratio="4:3")

        assert video.crop == NO_CROP

    def test_a_playlist_s_default_for_new_videos(self):
        playlist = Playlist.model_validate(
            {"videos": [], "video_defaults": {"crop_ratio": "4:3"}}
        )

        assert playlist.video_defaults.crop_ratio == "4:3"

    def test_new_videos_offer_the_same(self):
        assert list(choices.crop_ratios()) == ["", *PRESETS]

    def test_new_videos_margins_only_without_a_shape(self):
        assert FIELDS["video_defaults/crop"].enabled_when == When(
            "video_defaults/crop_ratio", ("",)
        )


def _adopting(update, crop=NO_CROP, crop_ratio=""):
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI, crop=crop, crop_ratio=crop_ratio)
    block.is_video_initialized = False

    VideoBlock.adopt_defaults(block, update)

    return block.video_params


class TestNewVideosDefaultsTaken:
    def test_a_shape_takes_the_margins_away(self):
        video = _adopting({"crop_ratio": "4:3"}, crop=VideoCrop(5, 5, 5, 5))

        assert (video.crop_ratio, video.crop) == ("4:3", NO_CROP)

    def test_margins_take_the_shape_away(self):
        video = _adopting({"crop": VideoCrop(5, 5, 5, 5)}, crop_ratio="4:3")

        assert (video.crop_ratio, video.crop) == ("", VideoCrop(5, 5, 5, 5))


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame(size=(1920, 1080)):
    frame = _StubFrame(vlc_options=[])
    frame.resize(900, 900)
    frame.media = MagicMock()
    frame.media.is_audio_only = False
    frame.media.cur_video_track = VideoTrack(
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        video_dimensions=size,
        fps=None,
        orientation=VideoTransform.NONE,
    )
    frame._view = ViewParams()
    return frame


class TestInTheWidget:
    def test_the_shape_s_margins_are_what_the_view_is_cut_by(self):
        frame = _frame()

        frame.set_crop_ratio("4:3")

        assert frame._view.crop == VideoCrop(240, 0, 240, 0)
        assert frame.shown_crop() == VideoCrop(240, 0, 240, 0)

    def test_they_follow_the_aspect_ratio_picked(self):
        """1920x1080 shown 4:3, cut to 16:9, loses its top and bottom."""

        frame = _frame()
        frame.set_crop_ratio("16:9")

        frame.set_aspect_ratio("4:3")

        assert frame._view.crop == VideoCrop(0, 135, 0, 135)

    def test_none_until_the_frame_is_known(self):
        frame = _frame(size=(0, 0))

        frame.set_crop_ratio("4:3")

        assert frame.shown_crop() == NO_CROP

    def test_margins_let_go_of_the_shape(self):
        frame = _frame()
        frame.set_crop_ratio("4:3")

        frame.set_crop(VideoCrop(1, 0, 0, 0))

        assert frame._view.crop_ratio == ""
        assert frame._view.crop == VideoCrop(1, 0, 0, 0)
