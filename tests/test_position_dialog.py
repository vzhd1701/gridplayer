from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication, QDialog

from gridplayer.dialogs.position import SetPositionDialog
from gridplayer.params.static import (
    VideoAnchor,
    VideoAspect,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


NO_SHIFT = VideoShift(0, 0)


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


class _Block:
    """What of a VideoBlock the dialog works through, over a real frame.

    A 1920x1080 video, not stretched, in a 900x900 pane: 900x506.25 of
    it, with 420 frame pixels of room up or down from the middle.
    """

    def __init__(self, anchor=VideoAnchor.CENTER, shift=NO_SHIFT, is_past=False):
        self.video_params = SimpleNamespace(
            anchor=anchor, shift=shift, is_shift_past_edges=is_past
        )
        self.shifts = []

        self.video_driver = _StubFrame(vlc_options=[])
        self.video_driver.resize(900, 900)
        self.video_driver.media = MagicMock(is_audio_only=False)
        self.video_driver.media.cur_video_track = VideoTrack(
            codec="h264",
            bitrate=0,
            language=None,
            description=None,
            video_dimensions=(1920, 1080),
            fps=None,
            orientation=VideoTransform.NONE,
        )
        self.video_driver._view = ViewParams(
            aspect=VideoAspect.NONE,
            anchor=anchor,
            shift=shift,
            is_shift_past_edges=is_past,
        )

    # as VideoBlock does them

    def set_anchor(self, anchor):
        self.video_params.anchor = anchor
        self.video_driver.set_anchor(anchor)
        self.set_shift(NO_SHIFT, is_silent=True)

    def set_shift(self, shift, is_silent=False):
        self.video_params.shift = shift
        self.video_driver.set_shift(shift)
        self.shifts.append((shift, is_silent))

    def set_shift_past_edges(self, is_shift_past_edges):
        self.video_params.is_shift_past_edges = is_shift_past_edges
        self.video_driver.set_shift_past_edges(is_shift_past_edges)
        self.set_shift(self.video_driver.shifted_by(0, 0), is_silent=True)


def _ranges(dialog):
    return [(spin.minimum(), spin.maximum()) for spin in dialog._spins.values()]


def _offsets(dialog):
    return [spin.value() for spin in dialog._spins.values()]


def test_it_opens_on_where_the_picture_is():
    dialog = SetPositionDialog(_Block(VideoAnchor.TOP, VideoShift(0, 40)))

    assert dialog._anchor_buttons[VideoAnchor.TOP].isChecked()
    assert _offsets(dialog) == [0, 40]
    assert not dialog._past_edges.isChecked()


def test_the_offset_goes_as_far_as_the_picture_can():
    """Against the top it can only go down; across there is no room."""

    dialog = SetPositionDialog(_Block(VideoAnchor.TOP))

    assert _ranges(dialog) == [(0, 0), (0, 840)]
    assert not dialog._spins["x"].isEnabled()
    assert dialog._spins["y"].isEnabled()


def test_an_offset_moves_the_picture_as_it_is_set():
    block = _Block()
    dialog = SetPositionDialog(block)

    dialog._spins["y"].setValue(100)

    assert block.shifts == [(VideoShift(0, 100), True)]
    assert block.video_driver._view.shift == VideoShift(0, 100)


def test_an_alignment_lets_go_of_the_offset():
    block = _Block(shift=VideoShift(0, 40))
    dialog = SetPositionDialog(block)

    dialog._anchor_buttons[VideoAnchor.BOTTOM_LEFT].click()

    assert block.video_params.anchor == VideoAnchor.BOTTOM_LEFT
    assert block.video_params.shift == NO_SHIFT
    assert _offsets(dialog) == [0, 0]
    assert _ranges(dialog) == [(0, 0), (-840, 0)]


def test_past_the_edges_the_offset_goes_further():
    # until half the picture is out, 960 frame pixels every way
    block = _Block()
    dialog = SetPositionDialog(block)

    dialog._past_edges.setChecked(True)

    assert block.video_params.is_shift_past_edges
    assert _ranges(dialog) == [(-960, 960), (-960, 960)]
    assert dialog._spins["x"].isEnabled()


def test_back_within_the_edges_the_picture_is_brought_back_in():
    block = _Block(shift=VideoShift(0, 900), is_past=True)
    dialog = SetPositionDialog(block)

    dialog._past_edges.setChecked(False)

    assert block.video_params.shift == VideoShift(0, 420)
    assert _offsets(dialog) == [0, 420]


def test_reset_takes_the_picture_back_to_the_alignment():
    block = _Block(VideoAnchor.TOP, VideoShift(0, 40))
    dialog = SetPositionDialog(block)

    dialog._on_reset()

    assert block.video_params.shift == NO_SHIFT
    assert block.video_params.anchor == VideoAnchor.TOP
    assert _offsets(dialog) == [0, 0]


def test_ok_says_where_the_picture_ended_up():
    block = _Block()
    dialog = SetPositionDialog(block)

    dialog._spins["y"].setValue(-30)
    dialog.accept()

    assert block.shifts[-1] == (VideoShift(0, -30), False)
    assert dialog.result() == QDialog.Accepted


def test_cancel_puts_back_what_there_was():
    block = _Block(VideoAnchor.BOTTOM, VideoShift(0, -30))
    dialog = SetPositionDialog(block)

    dialog._anchor_buttons[VideoAnchor.TOP_RIGHT].click()
    dialog._past_edges.setChecked(True)
    dialog._spins["x"].setValue(-500)
    dialog.reject()

    params = block.video_params
    view = block.video_driver._view

    assert (params.anchor, params.shift, params.is_shift_past_edges) == (
        VideoAnchor.BOTTOM,
        VideoShift(0, -30),
        False,
    )
    assert (view.anchor, view.shift, view.is_shift_past_edges) == (
        VideoAnchor.BOTTOM,
        VideoShift(0, -30),
        False,
    )


def test_cancel_with_nothing_changed_leaves_it_be():
    block = _Block(shift=VideoShift(0, 40))
    dialog = SetPositionDialog(block)

    dialog.reject()

    assert block.shifts == []


def test_the_preview_has_the_pane_and_all_of_the_picture():
    block = _Block(shift=VideoShift(0, -420))
    dialog = SetPositionDialog(block)

    preview = dialog._preview

    assert (preview._pane_w, preview._pane_h) == (900, 900)
    assert preview._picture.getRect() == pytest.approx((0, 0, 900, 506.25))

    dialog._past_edges.setChecked(True)
    dialog._spins["y"].setValue(-960)

    # half of it up past the top
    assert preview._picture.getRect() == pytest.approx((0, -253.125, 900, 506.25))


def test_every_alignment_has_a_button_named_as_the_menu_names_it():
    dialog = SetPositionDialog(_Block())

    assert set(dialog._anchor_buttons) == set(VideoAnchor)
    assert dialog._anchor_buttons[VideoAnchor.TOP_LEFT].toolTip() == "Top Left"
    assert all(not button.icon().isNull() for button in dialog._anchor_buttons.values())
