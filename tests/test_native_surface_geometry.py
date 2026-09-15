from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QApplication, QWidget

import gridplayer.widgets.video_frame_vlc_base as vlc_base
from gridplayer.params.static import HWCropBorderOffset
from gridplayer.widgets.video_frame_vlc_base import apply_vlc_hw_surface_geometry
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP
from gridplayer.widgets.video_frame_vlc_sw_sp import VideoFrameVLCSWSP


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubHWFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


class _StubSWFrame(VideoFrameVLCSWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame_and_surface(size=QSize(800, 450)):
    frame = QWidget()
    frame.resize(size)
    surface = QWidget(frame)
    return frame, surface


def test_surface_geometry_applies_offset():
    frame, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(frame, surface, 8)

    assert surface.geometry().getRect() == (-8, -8, 816, 466)


def test_surface_geometry_still_sizes_surface_without_offset():
    """The native surface is not in the layout, so nothing else would size it."""
    frame, surface = _frame_and_surface()
    surface.setGeometry(-8, -8, 816, 466)

    apply_vlc_hw_surface_geometry(frame, surface, 0)

    assert surface.geometry().getRect() == (0, 0, 800, 450)


def test_surface_geometry_ignores_unlaid_out_frame():
    frame = QWidget()
    frame.resize(0, 0)
    surface = QWidget(frame)
    surface.setGeometry(-8, -8, 816, 466)

    apply_vlc_hw_surface_geometry(frame, surface, 8)

    assert surface.geometry().getRect() == (-8, -8, 816, 466)


def test_native_surface_is_kept_out_of_the_layout():
    """QStackedLayout would reset the surface to the frame rect on every
    resize, undoing the hw crop border offset between our updates."""
    frame = _StubHWFrame(vlc_options=[])

    layout = frame.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]

    assert frame.is_native_surface
    assert frame.video_surface not in items
    assert frame.video_surface.parent() is frame


def test_software_surface_stays_in_the_layout():
    frame = _StubSWFrame(vlc_options=[])

    layout = frame.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]

    assert not frame.is_native_surface
    assert frame.video_surface in items


def _stub_offset_setting(monkeypatch):
    monkeypatch.setattr(
        vlc_base,
        "Settings",
        lambda: MagicMock(get=lambda _: HWCropBorderOffset.PX8),
    )


def _platform(monkeypatch, *, windows):
    monkeypatch.setattr(vlc_base.env, "IS_WINDOWS", windows)
    monkeypatch.setattr(vlc_base.env, "IS_LINUX", not windows)


def test_native_frame_fills_uncovered_area_black_once_loaded(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])

    # the loading status shows through the frame until a track is playing
    assert not frame.autoFillBackground()

    frame.load_video_finish(MagicMock(is_audio_only=False))

    assert frame.autoFillBackground()
    assert frame.palette().color(frame.backgroundRole()) == Qt.black


def test_native_frame_is_not_filled_on_x11(monkeypatch):
    """Measured on X11: the cell is ~85% filler through a drag whatever we do,
    so a fill only adds a second colour and reads as tearing."""
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=False)
    frame = _StubHWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=False))

    assert not frame.autoFillBackground()


def test_native_frame_stays_clear_for_audio_only(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=True))

    assert not frame.autoFillBackground()


def test_software_frame_keeps_default_background(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubSWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=False))

    assert not frame.autoFillBackground()


def test_native_surface_is_taken_out_of_the_qt_paint_path(monkeypatch):
    """Qt flushing its backing store over the vout window is the X11 flicker."""
    _platform(monkeypatch, windows=False)

    frame = _StubHWFrame(vlc_options=[])

    assert not frame.video_surface.updatesEnabled()


def test_native_surface_keeps_qt_painting_on_windows(monkeypatch):
    """VLC has its own child windows there; Qt never paints over the video."""
    _platform(monkeypatch, windows=True)

    frame = _StubHWFrame(vlc_options=[])

    assert frame.video_surface.updatesEnabled()


def test_software_surface_keeps_qt_painting(monkeypatch):
    """The software surface is a QLabel we paint ourselves."""
    _platform(monkeypatch, windows=False)

    frame = _StubSWFrame(vlc_options=[])

    assert frame.video_surface.updatesEnabled()


def test_native_frame_coalesces_resize_view_updates(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])
    calls = []
    monkeypatch.setattr(type(frame), "adjust_view", lambda self: calls.append(1))

    for _ in range(3):
        frame._adjust_view_on_resize()

    # leading edge only; the rest is left to the trailing timer
    assert len(calls) == 1
    assert frame._resize_view_timer.isActive()


def test_coalesced_update_lands_once_the_resize_stops(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])
    calls = []
    monkeypatch.setattr(type(frame), "adjust_view", lambda self: calls.append(1))

    frame._adjust_view_on_resize()
    frame._adjust_view_now()

    assert len(calls) == 2
    assert not frame._resize_view_timer.isActive()


def test_software_frame_applies_every_resize(monkeypatch):
    frame = _StubSWFrame(vlc_options=[])
    calls = []
    monkeypatch.setattr(type(frame), "adjust_view", lambda self: calls.append(1))

    for _ in range(3):
        frame._adjust_view_on_resize()

    assert len(calls) == 3
    assert not frame._resize_view_timer.isActive()
