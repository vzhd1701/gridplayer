from PyQt5.QtCore import QSize

import gridplayer.widgets.video_frame_vlc_base as vlc_base
from gridplayer.params.static import HWCropBorderOffset
from gridplayer.widgets.video_frame_vlc_base import (
    HW_CROP_BORDER_OFFSETS,
    VLC_CROP_BORDER_PX,
    VLC_WINDOWS_CROP_BORDER_PX,
    vlc_hw_crop_border_offset,
)

FRAME = QSize(800, 450)
WINDOW = QSize(1920, 1000)


class _StubSettings:
    def __init__(self, value):
        self.value = value

    def get(self, setting):
        return self.value


def _platform(monkeypatch, *, linux=False, windows=False):
    monkeypatch.setattr(vlc_base.env, "IS_LINUX", linux)
    monkeypatch.setattr(vlc_base.env, "IS_WINDOWS", windows)


def _set_setting(monkeypatch, value):
    monkeypatch.setattr(vlc_base, "Settings", lambda: _StubSettings(value))


def test_default_offset_windows(monkeypatch):
    _set_setting(monkeypatch, HWCropBorderOffset.AUTO)
    _platform(monkeypatch, windows=True)

    assert vlc_hw_crop_border_offset(FRAME, WINDOW) == VLC_WINDOWS_CROP_BORDER_PX


def test_default_offset_macos(monkeypatch):
    _set_setting(monkeypatch, HWCropBorderOffset.AUTO)
    _platform(monkeypatch)

    assert vlc_hw_crop_border_offset(FRAME, WINDOW) == VLC_CROP_BORDER_PX


def test_linux_window_filling_frame_has_no_offset(monkeypatch):
    _set_setting(monkeypatch, HWCropBorderOffset.AUTO)
    _platform(monkeypatch, linux=True)

    assert vlc_hw_crop_border_offset(WINDOW, WINDOW) == 0
    assert vlc_hw_crop_border_offset(FRAME, WINDOW) == VLC_CROP_BORDER_PX


def test_explicit_setting_overrides_platform(monkeypatch):
    _set_setting(monkeypatch, HWCropBorderOffset.PX4)
    _platform(monkeypatch, windows=True)

    assert vlc_hw_crop_border_offset(FRAME, WINDOW) == 4

    _set_setting(monkeypatch, HWCropBorderOffset.PX4)
    _platform(monkeypatch, linux=True)

    assert vlc_hw_crop_border_offset(FRAME, WINDOW) == 4


def test_disabled_setting(monkeypatch):
    _set_setting(monkeypatch, HWCropBorderOffset.DISABLED)
    _platform(monkeypatch, windows=True)

    assert vlc_hw_crop_border_offset(FRAME, WINDOW) == 0


def test_enum_offsets_map():
    assert HW_CROP_BORDER_OFFSETS[HWCropBorderOffset.PX2] == 2
    assert HW_CROP_BORDER_OFFSETS[HWCropBorderOffset.PX4] == 4
    assert HW_CROP_BORDER_OFFSETS[HWCropBorderOffset.PX6] == 6
    assert HW_CROP_BORDER_OFFSETS[HWCropBorderOffset.PX8] == 8
    assert HW_CROP_BORDER_OFFSETS[HWCropBorderOffset.PX10] == 10
    assert HW_CROP_BORDER_OFFSETS[HWCropBorderOffset.PX12] == 12
