"""The aspect ratio picked for a video: the shape its picture is shown in,
as it is shown, out of the ones VLC offers."""

import json
from unittest.mock import Mock

import pytest

from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.params.settings_fields import choices
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_view import ViewControl

URI = "http://example.com/a.mp4"

# VLC's own, in its order
PRESETS = ["16:9", "4:3", "1:1", "16:10", "2.21:1", "2.35:1", "2.39:1", "5:4"]


def _submenu(section, name):
    video = next(
        item
        for item in SECTIONS[section]
        if isinstance(item, tuple) and item[0] == "Video"
    )
    return next(item for item in video if isinstance(item, tuple) and item[0] == name)


def _all_videos_submenu(name):
    every = next(
        item
        for item in SECTIONS["video_all"]
        if isinstance(item, tuple) and item[0] == "[ALL]"
    )
    video = next(i for i in every if isinstance(i, tuple) and i[0] == "Video")
    return next(i for i in video if isinstance(i, tuple) and i[0] == name)


class TestTheMenu:
    def test_it_comes_after_the_view_mode(self):
        video = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Video"
        )
        submenus = [i[0] for i in video if isinstance(i, tuple)]

        at = submenus.index("Aspect Ratio")
        assert submenus[at - 1] == "View Mode"
        assert "Aspect Ratio" in SUBMENUS

    def test_the_list_s_and_default_first_then_vlc_s_ratios(self):
        items = _submenu("video_active", "Aspect Ratio")[1:]

        assert list(items[:2]) == ["Aspect Ratio List", "Aspect Ratio Default"]

        values = [ACTIONS[name]["func"][2] for name in items[2:]]

        assert values == PRESETS
        assert [ACTIONS[name]["title"] for name in items[2:]] == PRESETS

    def test_default_is_the_video_s_own(self):
        action = ACTIONS["Aspect Ratio Default"]

        assert action["func"] == ("active", "view.set_aspect_ratio_own")
        assert action["check_if"] == "is_active_aspect_ratio_default"
        assert action["is_choice"]

    def test_each_reaches_the_video_and_is_ticked_when_in_force(self):
        for name in _submenu("video_active", "Aspect Ratio")[3:]:
            action = ACTIONS[name]
            target, command, ratio = action["func"]

            assert (target, command) == ("active", "view.set_aspect_ratio")
            assert action["check_if"] == (
                "is_active_param_set_to",
                "aspect_ratio",
                ratio,
            )
            assert action["is_choice"]

    def test_the_same_for_all_videos(self):
        items = _all_videos_submenu("Aspect Ratio")[1:]

        assert [ACTIONS[name]["func"] for name in items] == [
            ("all", "set_aspect_ratio", ratio) for ratio in ["", *PRESETS]
        ]
        assert hasattr(VideoBlocksManager, "all_set_aspect_ratio")

    def test_new_videos_offer_the_same(self):
        assert list(choices.aspect_ratios()) == ["", *PRESETS]


def _block():
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block.video_driver = Mock()
    block.list_aspect_ratio = ""
    block.list_crop_ratio = ""
    block.view = ViewControl(block)
    return block


class TestOnOneVideo:
    def test_picking_one_shows_the_picture_so(self):
        block = _block()

        block.view.set_aspect_ratio("4:3")

        assert block.video_params.aspect_ratio == "4:3"
        block.video_driver.set_aspect_ratio.assert_called_once_with("4:3")
        block.info_change.emit.assert_called_once_with("Aspect Ratio: 4:3")

    def test_default_is_said_as_such(self):
        block = _block()

        block.view.set_aspect_ratio("")

        block.info_change.emit.assert_called_once_with("Aspect Ratio: Default")

    def test_silently_when_restored(self):
        block = _block()

        block.view.set_aspect_ratio("16:9", is_silent=True)

        block.info_change.emit.assert_not_called()


class TestSaved:
    def test_a_video_keeps_its_own(self):
        video = Video(uri=URI, aspect_ratio="2.35:1")

        dumped = json.loads(Playlist(videos=[video]).dumps())["videos"][0]

        assert dumped["aspect_ratio"] == "2.35:1"
        assert Video(uri=URI, aspect_ratio=dumped["aspect_ratio"]).aspect_ratio == (
            "2.35:1"
        )

    @pytest.mark.parametrize("text", ["16:0", "wide", "100:1"])
    def test_one_that_is_no_shape_is_the_video_s_own(self, text):
        assert Video(uri=URI, aspect_ratio=text).aspect_ratio == ""

    def test_a_playlist_s_default_for_new_videos(self):
        playlist = Playlist.model_validate(
            {"videos": [], "video_defaults": {"aspect_ratio": "4:3"}}
        )

        assert playlist.video_defaults.aspect_ratio == "4:3"
