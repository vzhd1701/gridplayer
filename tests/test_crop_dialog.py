import pytest
from types import SimpleNamespace

from PyQt5.QtWidgets import QApplication, QDialog

from gridplayer.dialogs.crop import SetCropDialog
from gridplayer.params.static import VideoAspect, VideoCrop, VideoTransform


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _FakeBlock:
    def __init__(self, crop=VideoCrop(0, 0, 0, 0), aspect=VideoAspect.FIT):
        self.applied = []
        self.aspect_calls = []
        self.video_params = SimpleNamespace(
            crop=crop,
            aspect_mode=aspect,
            video_track_id=1,
            transform=VideoTransform.NONE,
        )
        self.video_tracks = {1: SimpleNamespace(video_dimensions=(640, 360))}

    def set_crop(self, crop, is_silent=False):
        clamped = VideoCrop(*(max(v, 0) for v in crop))
        if self.video_params.crop != clamped:
            self.video_params.aspect_mode = VideoAspect.NONE
            self.video_params.crop = clamped
        self.applied.append((self.video_params.crop, is_silent))

    def set_aspect(self, aspect):
        self.aspect_calls.append(aspect)
        self.video_params.aspect_mode = aspect


def test_dialog_initializes_from_current_crop_and_bounds():
    block = _FakeBlock(VideoCrop(10, 20, 30, 40))
    dialog = SetCropDialog(block)

    assert [dialog._spins[k].value() for k in ("left", "top", "right", "bottom")] == [
        10,
        20,
        30,
        40,
    ]
    assert dialog._spins["left"].maximum() == 640
    assert dialog._spins["top"].maximum() == 360


def test_dialog_applies_crop_live_silently():
    block = _FakeBlock()
    dialog = SetCropDialog(block)

    dialog._spins["left"].setValue(15)

    assert block.applied == [(VideoCrop(15, 0, 0, 0), True)]


def test_dialog_ok_commits_crop_loudly():
    block = _FakeBlock()
    dialog = SetCropDialog(block)

    dialog._spins["bottom"].setValue(30)
    dialog.accept()

    assert block.applied[-1] == (VideoCrop(0, 0, 0, 30), False)
    assert dialog.result() == QDialog.Accepted


def test_dialog_cancel_restores_crop_and_aspect():
    block = _FakeBlock(aspect=VideoAspect.FIT)
    dialog = SetCropDialog(block)

    dialog._spins["left"].setValue(15)
    assert block.video_params.aspect_mode is VideoAspect.NONE

    dialog.reject()

    assert block.applied[-1] == (VideoCrop(0, 0, 0, 0), True)
    assert block.video_params.crop == VideoCrop(0, 0, 0, 0)
    assert block.video_params.aspect_mode is VideoAspect.FIT
    assert block.aspect_calls == [VideoAspect.FIT]


def test_dialog_cancel_without_changes_is_noop():
    block = _FakeBlock(VideoCrop(5, 5, 5, 5), VideoAspect.STRETCH)
    dialog = SetCropDialog(block)

    dialog.reject()

    assert block.applied == []
    assert block.aspect_calls == []


def test_dialog_reset_zeroes_crop_live():
    block = _FakeBlock(VideoCrop(10, 10, 10, 10))
    dialog = SetCropDialog(block)

    dialog._on_reset()

    assert block.applied[-1] == (VideoCrop(0, 0, 0, 0), True)


def test_dialog_dimension_fallback_when_unknown():
    block = _FakeBlock()
    block.video_tracks = {1: SimpleNamespace(video_dimensions=(0, 0))}
    dialog = SetCropDialog(block)

    assert dialog._spins["left"].maximum() == 9999


def test_dialog_shows_video_vs_cropped_size():
    block = _FakeBlock()
    dialog = SetCropDialog(block)

    assert dialog._size_label.text() == "Video: 640x360 | Cropped: 640x360"

    dialog._spins["left"].setValue(15)

    assert dialog._size_label.text() == "Video: 640x360 | Cropped: 625x360"


def test_dialog_size_label_swaps_for_rotation():
    block = _FakeBlock()
    block.video_params.transform = VideoTransform.ROTATE_90
    dialog = SetCropDialog(block)

    assert dialog._spins["left"].maximum() == 360

    dialog._spins["left"].setValue(15)

    assert dialog._size_label.text() == "Video: 360x640 | Cropped: 360x625"


def test_dialog_hides_size_label_when_dimensions_unknown():
    block = _FakeBlock()
    block.video_tracks = {1: SimpleNamespace(video_dimensions=(0, 0))}
    dialog = SetCropDialog(block)

    assert dialog._size_label.isHidden()
