import pytest
from types import SimpleNamespace

from PyQt5.QtWidgets import QApplication, QDialog

from gridplayer.dialogs.crop import QCompactCropPicker, SetCropDialog
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
    dialog = SetCropDialog.for_video_block(block)

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
    dialog = SetCropDialog.for_video_block(block)

    dialog._spins["left"].setValue(15)

    assert block.applied == [(VideoCrop(15, 0, 0, 0), True)]


def test_dialog_ok_commits_crop_loudly():
    block = _FakeBlock()
    dialog = SetCropDialog.for_video_block(block)

    dialog._spins["bottom"].setValue(30)
    dialog.accept()

    assert block.applied[-1] == (VideoCrop(0, 0, 0, 30), False)
    assert dialog.result() == QDialog.Accepted


def test_dialog_cancel_restores_crop_and_aspect():
    block = _FakeBlock(aspect=VideoAspect.FIT)
    dialog = SetCropDialog.for_video_block(block)

    dialog._spins["left"].setValue(15)
    assert block.video_params.aspect_mode is VideoAspect.NONE

    dialog.reject()

    assert block.applied[-1] == (VideoCrop(0, 0, 0, 0), True)
    assert block.video_params.crop == VideoCrop(0, 0, 0, 0)
    assert block.video_params.aspect_mode is VideoAspect.FIT
    assert block.aspect_calls == [VideoAspect.FIT]


def test_dialog_cancel_without_changes_is_noop():
    block = _FakeBlock(VideoCrop(5, 5, 5, 5), VideoAspect.STRETCH)
    dialog = SetCropDialog.for_video_block(block)

    dialog.reject()

    assert block.applied == []
    assert block.aspect_calls == []


def test_dialog_reset_zeroes_crop_live():
    block = _FakeBlock(VideoCrop(10, 10, 10, 10))
    dialog = SetCropDialog.for_video_block(block)

    dialog._on_reset()

    assert block.applied[-1] == (VideoCrop(0, 0, 0, 0), True)


def test_dialog_dimension_fallback_when_unknown():
    block = _FakeBlock()
    block.video_tracks = {1: SimpleNamespace(video_dimensions=(0, 0))}
    dialog = SetCropDialog.for_video_block(block)

    assert dialog._spins["left"].maximum() == 9999


def test_dialog_shows_video_vs_cropped_size():
    block = _FakeBlock()
    dialog = SetCropDialog.for_video_block(block)

    assert dialog._size_label.text() == "Video: 640x360 | Cropped: 640x360"

    dialog._spins["left"].setValue(15)

    assert dialog._size_label.text() == "Video: 640x360 | Cropped: 625x360"


def test_dialog_size_label_swaps_for_rotation():
    block = _FakeBlock()
    block.video_params.transform = VideoTransform.ROTATE_90
    dialog = SetCropDialog.for_video_block(block)

    assert dialog._spins["left"].maximum() == 360

    dialog._spins["left"].setValue(15)

    assert dialog._size_label.text() == "Video: 360x640 | Cropped: 360x625"


def test_dialog_hides_size_label_when_dimensions_unknown():
    block = _FakeBlock()
    block.video_tracks = {1: SimpleNamespace(video_dimensions=(0, 0))}
    dialog = SetCropDialog.for_video_block(block)

    assert dialog._size_label.isHidden()


def test_get_crop_returns_value_on_accept(mocker):
    def fake_exec(self):
        self._spins["left"].setValue(7)
        self.accept()
        return self.result()

    mocker.patch.object(SetCropDialog, "exec_", fake_exec)

    assert SetCropDialog.get_crop(VideoCrop(0, 0, 0, 0)) == VideoCrop(7, 0, 0, 0)


def test_get_crop_returns_none_on_reject(mocker):
    def fake_exec(self):
        self.reject()
        return self.result()

    mocker.patch.object(SetCropDialog, "exec_", fake_exec)

    assert SetCropDialog.get_crop(VideoCrop(0, 0, 0, 0)) is None


def test_dialog_preview_tracks_spins():
    block = _FakeBlock()
    dialog = SetCropDialog.for_video_block(block)

    dialog._spins["left"].setValue(15)

    assert (dialog._preview._frame_w, dialog._preview._frame_h) == (640, 360)
    assert dialog._preview._left == 15


def test_dialog_value_mode_edits_without_block():
    dialog = SetCropDialog(VideoCrop(1, 2, 3, 4))

    assert dialog._block is None
    assert dialog._spins["left"].value() == 1
    assert dialog._size_label.isHidden()
    assert dialog._area_label.isHidden()
    assert dialog._preview.isHidden()

    dialog.accept()

    assert dialog.result() == QDialog.Accepted
    assert dialog._spin_crop() == VideoCrop(1, 2, 3, 4)


def test_compact_picker_opens_value_mode_dialog(mocker):
    picker = QCompactCropPicker()
    captured = {}

    def fake_get_crop(crop, parent):
        captured["crop"] = crop
        return VideoCrop(9, 9, 9, 9)

    mocker.patch.object(SetCropDialog, "get_crop", fake_get_crop)

    picker._open_dialog()

    assert captured["crop"] == VideoCrop(0, 0, 0, 0)
    assert picker.value == VideoCrop(9, 9, 9, 9)
