"""The aspect ratio and the crop shape a channel list says for a channel, in
VLC's #EXTVLCOPT tags: read with the list, shown where the cell has none
picked, and never kept as picked."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.crop import SetCropDialog
from gridplayer.models.media_list import ItemShape, ListItem, MediaList
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.static import (
    NO_CROP_RATIO,
    OWN_ASPECT_RATIO,
    VideoCrop,
    VideoTransform,
    ViewParams,
)
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.add_videos import _with_list_shape
from gridplayer.utils.list_files import m3u_text, parse_m3u
from gridplayer.utils.list_refresh import _updated
from gridplayer.vlc_player.static import MediaInput, VideoTrack
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_view import ViewControl
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP
from tests.test_cb_vout import _make_player
from tests.test_crop_dialog import _FakeBlock

URI = "http://example.com/a.ts"

NO_CROP = VideoCrop(0, 0, 0, 0)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _read(*tags):
    text = "#EXTM3U\n#EXTINF:-1,One\n" + "".join(f"{t}\n" for t in tags) + URI + "\n"
    return parse_m3u(text, None).items[0]


class TestRead:
    def test_both_as_vlc_writes_them(self):
        item = _read("#EXTVLCOPT:aspect-ratio=4:3", "#EXTVLCOPT:crop=16:9")

        assert item.shape == ItemShape(aspect_ratio="4:3", crop_ratio="16:9")

    def test_quoted_or_in_capitals(self):
        item = _read('#EXTVLCOPT:ASPECT-RATIO="2.35:1"')

        assert item.shape.aspect_ratio == "2.35:1"

    @pytest.mark.parametrize(
        "tag",
        [
            "#EXTVLCOPT:aspect-ratio=wide",
            "#EXTVLCOPT:aspect-ratio=16:0",
            # a window and margins go by a frame size the list cannot know
            "#EXTVLCOPT:crop=400x300+10+10",
            "#EXTVLCOPT:crop=10+10+10+10",
        ],
    )
    def test_no_shape_none(self, tag):
        assert _read(tag).shape is None

    def test_only_for_the_entry_after(self):
        text = "#EXTM3U\n#EXTVLCOPT:aspect-ratio=4:3\nhttp://x/1.ts\nhttp://x/2.ts\n"

        items = parse_m3u(text, None).items

        assert items[0].shape is not None
        assert items[1].shape is None

    def test_one_shared_by_every_channel_shown_in_it(self):
        text = (
            "#EXTM3U\n"
            "#EXTVLCOPT:aspect-ratio=4:3\nhttp://x/1.ts\n"
            "#EXTVLCOPT:aspect-ratio=4:3\nhttp://x/2.ts\n"
        )

        first, second = parse_m3u(text, None).items

        assert first.shape is second.shape

    def test_written_back(self):
        item = _read("#EXTVLCOPT:aspect-ratio=4:3", "#EXTVLCOPT:crop=16:9")

        text = m3u_text("", [item], None)

        assert "#EXTVLCOPT:aspect-ratio=4:3" in text
        assert "#EXTVLCOPT:crop=16:9" in text
        assert parse_m3u(text, None).items[0].shape == item.shape


class TestKept:
    def test_with_the_playlist(self, tmp_path):
        shape = ItemShape(aspect_ratio="4:3")
        playlist = Playlist(lists=[MediaList(items=[ListItem(uri=URI, shape=shape)])])
        playlist.save(tmp_path / "p.gpls")

        read = Playlist.read(tmp_path / "p.gpls")

        assert read.lists[0].items[0].shape == shape

    def test_none_not_written(self):
        data = json.loads(MediaList(items=[ListItem(uri=URI)]).model_dump_json())

        assert data["items"][0]["shape"] is None

    def test_read_again_from_the_source(self):
        known = ListItem(uri=URI)
        fresh = ListItem(uri=URI, shape=ItemShape(crop_ratio="16:9"))

        assert _updated(known, fresh).shape == fresh.shape


class TestTheView:
    def test_the_list_s_where_none_is_picked(self):
        view = ViewParams().with_list("4:3", "16:9")

        assert (view.aspect_ratio, view.is_aspect_ratio_listed) == ("4:3", True)
        assert (view.crop_ratio, view.is_crop_ratio_listed) == ("16:9", True)

    def test_a_pick_over_the_list_s(self):
        view = ViewParams(aspect_ratio="1:1", crop_ratio="5:4").with_list("4:3", "16:9")

        assert (view.aspect_ratio, view.is_aspect_ratio_listed) == ("1:1", False)
        assert (view.crop_ratio, view.is_crop_ratio_listed) == ("5:4", False)

    def test_margins_are_a_pick_too(self):
        view = ViewParams(crop=VideoCrop(1, 0, 0, 0)).with_list("", "16:9")

        assert (view.crop_ratio, view.is_crop_ratio_listed) == ("", False)

    def test_as_picked_without_the_list_s(self):
        view = (
            ViewParams().with_list("4:3", "16:9")._replace(crop=VideoCrop(8, 0, 8, 0))
        )

        assert view.picked() == ViewParams()


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame(list_aspect_ratio="", list_crop_ratio="", **picked):
    frame = _StubFrame(vlc_options=[])
    frame.resize(900, 900)
    frame.load_video(
        MediaInput(
            uri=URI,
            is_live=False,
            is_audio_only=False,
            size=(900, 900),
            video=Video(uri=URI, **picked),
            list_aspect_ratio=list_aspect_ratio,
            list_crop_ratio=list_crop_ratio,
        )
    )
    frame.media = MagicMock()
    frame.media.is_audio_only = False
    frame.media.cur_video_track = VideoTrack(
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        video_dimensions=(1920, 1080),
        fps=None,
        orientation=VideoTransform.NONE,
    )
    return frame


class TestInTheWidget:
    def test_loaded_with_the_list_s(self):
        frame = _frame("4:3", "")

        assert frame._view.aspect_ratio == "4:3"
        assert frame._view.is_aspect_ratio_listed

    def test_a_pick_over_it_and_default_back_to_it(self):
        frame = _frame("4:3", "")

        frame.set_aspect_ratio("1:1")
        assert (frame._view.aspect_ratio, frame._view.is_aspect_ratio_listed) == (
            "1:1",
            False,
        )

        frame.set_aspect_ratio("")
        assert (frame._view.aspect_ratio, frame._view.is_aspect_ratio_listed) == (
            "4:3",
            True,
        )

    def test_its_crop_cuts_by_the_margins_of_its_shape(self):
        frame = _frame("", "4:3")
        frame.adjust_view()

        assert frame.shown_crop() == VideoCrop(240, 0, 240, 0)

    def test_margins_over_it_and_none_back_to_it(self):
        frame = _frame("", "4:3")

        frame.set_crop(VideoCrop(1, 0, 0, 0))
        assert (frame._view.crop_ratio, frame._view.crop) == ("", VideoCrop(1, 0, 0, 0))

        frame.set_crop(NO_CROP)
        assert frame._view.is_crop_ratio_listed
        assert frame.shown_crop() == VideoCrop(240, 0, 240, 0)

    def test_off_the_list_none(self):
        frame = _frame("4:3", "4:3")

        frame.forget_list_ratios()

        assert frame._view == ViewParams()


class TestInThePlayer:
    def test_kept_without_the_list_s(self):
        player, _ = _make_player()
        player.media = None
        # the list's crop as the widget sends it, worked out into margins
        view = (
            ViewParams()
            .with_list("4:3", "16:9")
            ._replace(crop=VideoCrop(240, 0, 240, 0))
        )

        player.adjust_view((640, 360), view)

        video = player.media_input.video
        assert (video.aspect_ratio, video.crop_ratio, video.crop) == ("", "", NO_CROP)

    def test_the_list_s_again_when_shown_again(self):
        player, _ = _make_player()
        player.media_input.list_aspect_ratio = "4:3"
        player.adjust_view = Mock()

        player._apply_media_input_view()

        view = player.adjust_view.call_args.kwargs["view"]
        assert (view.aspect_ratio, view.is_aspect_ratio_listed) == ("4:3", True)

    def test_the_list_s_crop_again_by_the_margins_last_sent(self):
        player, _ = _make_player()
        player.media = None
        player.media_input.list_crop_ratio = "4:3"
        sent = ViewParams().with_list("", "4:3")._replace(crop=VideoCrop(80, 0, 80, 0))
        player.adjust_view((640, 360), sent)
        player.adjust_view = Mock()

        player._apply_media_input_view()

        view = player.adjust_view.call_args.kwargs["view"]
        assert (view.crop, view.is_crop_ratio_listed) == (VideoCrop(80, 0, 80, 0), True)

    def test_none_once_shown_without(self):
        player, _ = _make_player()
        player.media = None
        player.media_input.list_aspect_ratio = "4:3"
        player.media_input.list_crop_ratio = "16:9"

        player.adjust_view((640, 360), ViewParams())

        assert player.media_input.list_aspect_ratio == ""
        assert player.media_input.list_crop_ratio == ""


def _block(list_aspect_ratio="", list_crop_ratio="", **picked):
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI, **picked)
    block.video_tracks = [0]
    block.is_video_initialized = True
    block.video_driver = Mock()
    block.list_aspect_ratio = list_aspect_ratio
    block.list_crop_ratio = list_crop_ratio
    block.view = ViewControl(block)
    return block


class TestOnTheCell:
    def test_default_says_the_list_s(self):
        block = _block("4:3")

        block.view.set_aspect_ratio("")

        block.info_change.emit.assert_called_once_with("Aspect Ratio: 4:3 (list)")

    def test_off_says_the_list_s(self):
        block = _block("", "16:9")

        block.view.crop_reset()

        block.info_change.emit.assert_called_once_with("Crop: 16:9 (list)")

    def test_a_nudge_goes_on_from_the_list_s_margins(self):
        block = _block("", "4:3")
        block.video_driver.shown_crop.return_value = VideoCrop(240, 0, 240, 0)

        block.view.crop(0, 1, 0, 0)

        assert block.video_params.crop == VideoCrop(240, 1, 240, 0)

    def test_margins_of_its_own_over_the_list_s(self):
        block = _block("", "4:3", crop=VideoCrop(1, 2, 3, 4))

        assert block.view.shown_crop() == VideoCrop(1, 2, 3, 4)
        block.video_driver.shown_crop.assert_not_called()


def _menu(list_aspect_ratio="", list_crop_ratio="", **picked):
    block = SimpleNamespace(
        video_params=Video(uri=URI, **picked),
        list_aspect_ratio=list_aspect_ratio,
        list_crop_ratio=list_crop_ratio,
        is_video_initialized=True,
        video_tracks=[0],
    )
    manager = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    manager._ctx.active_block = block
    return manager


class TestTheMenu:
    def test_the_list_s_shown_ticked_with_nothing_picked(self):
        manager = _menu("4:3", "16:9")

        assert manager.is_active_list_aspect_ratio()
        assert manager.active_list_aspect_ratio_title() == "4:3 (list)"
        assert manager.is_active_param_set_to("aspect_ratio", "")
        assert not manager.is_active_aspect_ratio_default()

        assert manager.is_active_list_crop_ratio()
        assert manager.active_list_crop_ratio_title() == "16:9 (list)"
        assert manager.is_active_crop_listed()
        assert not manager.is_active_crop_off()

    def test_default_and_off_picked_over_them(self):
        manager = _menu(
            "4:3", "16:9", aspect_ratio=OWN_ASPECT_RATIO, crop_ratio=NO_CROP_RATIO
        )

        assert manager.is_active_aspect_ratio_default()
        assert manager.is_active_crop_off()
        assert not manager.is_active_crop_listed()

    def test_none_without_a_list_s(self):
        manager = _menu()

        assert not manager.is_active_list_aspect_ratio()
        assert not manager.is_active_list_crop_ratio()
        assert manager.is_active_aspect_ratio_default()
        assert manager.is_active_crop_off()

    def test_the_menu_can_ask(self):
        commands = _menu().commands

        for action in ("Aspect Ratio List", "Crop List"):
            assert ACTIONS[action]["title"] == "%v"
            assert commands[ACTIONS[action]["value_getter"]]
            assert commands[ACTIONS[action]["show_if"]]

        assert commands[ACTIONS["Crop List"]["check_if"]]
        assert commands[ACTIONS["Aspect Ratio Default"]["check_if"]]

    def test_the_list_s_follows_it_again(self):
        assert ACTIONS["Aspect Ratio List"]["func"] == (
            "active",
            "view.set_aspect_ratio",
            "",
        )
        assert ACTIONS["Crop List"]["func"] == ("active", "view.crop_reset")

    def test_off_keeps_its_shortcut_name(self):
        assert ACTIONS["Crop Reset"]["keymap_title"] == "Crop Reset"
        assert ACTIONS["Crop Reset"]["func"] == ("active", "view.crop_off")


class TestPickedOverTheList:
    def test_default_over_the_list_s_is_the_video_s_own(self):
        block = _block("4:3")

        block.view.set_aspect_ratio_own()

        assert block.video_params.aspect_ratio == OWN_ASPECT_RATIO
        block.video_driver.set_aspect_ratio.assert_called_once_with(OWN_ASPECT_RATIO)
        block.info_change.emit.assert_called_once_with("Aspect Ratio: Default")

    def test_default_without_one_is_nothing_picked(self):
        block = _block()

        block.view.set_aspect_ratio_own()

        assert block.video_params.aspect_ratio == ""

    def test_off_over_the_list_s_cuts_nothing(self):
        block = _block("", "16:9")

        block.view.crop_off()

        assert block.video_params.crop_ratio == NO_CROP_RATIO
        assert block.view.shown_crop() == NO_CROP
        block.info_change.emit.assert_called_once_with("Crop: Off")

    def test_off_without_one_is_no_margins(self):
        block = _block(crop=VideoCrop(1, 0, 0, 0))

        block.view.crop_off()

        assert (block.video_params.crop_ratio, block.video_params.crop) == ("", NO_CROP)

    def test_kept_with_the_playlist(self):
        video = Video(uri=URI, aspect_ratio=OWN_ASPECT_RATIO, crop_ratio=NO_CROP_RATIO)

        read = Video.model_validate(json.loads(video.model_dump_json()))

        assert (read.aspect_ratio, read.crop_ratio) == (OWN_ASPECT_RATIO, NO_CROP_RATIO)

    def test_each_only_for_its_own(self):
        video = Video(uri=URI, aspect_ratio=NO_CROP_RATIO, crop_ratio=OWN_ASPECT_RATIO)

        assert (video.aspect_ratio, video.crop_ratio) == ("", "")

    def test_shown_so_in_the_widget(self):
        frame = _frame("4:3", "4:3", aspect_ratio=OWN_ASPECT_RATIO)

        frame.set_crop_ratio(NO_CROP_RATIO)

        assert not frame._view.is_aspect_ratio_listed
        assert not frame._view.is_crop_ratio_listed
        assert frame.shown_crop() == NO_CROP
        assert frame._pixel_aspect() == 1


def _dialog_on_the_list_s():
    block = _FakeBlock()
    block.list_crop_ratio = "4:3"
    block.ratio_crop = VideoCrop(80, 0, 80, 0)
    return block, SetCropDialog.for_video_block(block)


class TestTheSetCropDialog:
    def test_opens_on_the_list_s_margins(self):
        _block, dialog = _dialog_on_the_list_s()

        assert dialog._spin_crop() == VideoCrop(80, 0, 80, 0)

    def test_left_as_it_was_still_the_list_s(self):
        block, dialog = _dialog_on_the_list_s()

        dialog.accept()

        assert block.video_params.crop == NO_CROP
        assert block.video_params.crop_ratio == ""

    def test_cancelled_the_list_s_again(self):
        block, dialog = _dialog_on_the_list_s()
        dialog._spins["left"].setValue(90)

        dialog.reject()

        assert block.video_params.crop == NO_CROP

    def test_changed_margins_of_its_own(self):
        block, dialog = _dialog_on_the_list_s()
        dialog._spins["left"].setValue(90)

        dialog.accept()

        assert block.video_params.crop == VideoCrop(90, 0, 80, 0)


class TestACellOfItsOwn:
    def test_shown_as_the_list_says(self):
        shape = ItemShape(aspect_ratio="4:3", crop_ratio="16:9")

        video = _with_list_shape(Video(uri=URI), shape)

        assert (video.aspect_ratio, video.crop_ratio) == ("4:3", "16:9")

    def test_unless_new_videos_pick_one(self):
        shape = ItemShape(aspect_ratio="4:3", crop_ratio="16:9")

        video = _with_list_shape(
            Video(uri=URI, aspect_ratio="1:1", crop=VideoCrop(1, 0, 0, 0)), shape
        )

        assert (video.aspect_ratio, video.crop_ratio) == ("1:1", "")
