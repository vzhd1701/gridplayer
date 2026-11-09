from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication, QWidget

import gridplayer.widgets.video_frame_base as vlc_base
from gridplayer.params.static import VideoCellViewMode, VideoTransform
from gridplayer.utils import darkmode
from gridplayer.utils.aspect_calc import ViewPlacement
from gridplayer.widgets.video_frame_base import apply_native_surface_geometry
from gridplayer.widgets.video_frame_mpv_hw import VideoFrameMPVHW
from gridplayer.widgets.video_frame_mpv_sw import VideoFrameMPVSW


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubHWFrame(VideoFrameMPVHW):
    def __init__(self, **kwargs):
        super().__init__(process_manager=MagicMock(), **kwargs)

    def driver_setup(self):
        return MagicMock()


class _StubSWFrame(VideoFrameMPVSW):
    def __init__(self, **kwargs):
        super().__init__(process_manager=MagicMock(), **kwargs)

    def driver_setup(self):
        return MagicMock()


DEFAULT_SIZE = QSize(800, 450)


def _frame_and_surface(size=DEFAULT_SIZE):
    frame = QWidget()
    frame.resize(size)
    clip = QWidget(frame)
    surface = QWidget(clip)
    return frame, clip, surface


def test_surface_geometry_still_sizes_surface_without_offset():
    """The native surface is not in the layout, so nothing else would size it."""
    frame, clip, surface = _frame_and_surface()
    surface.setGeometry(-8, -8, 816, 466)

    apply_native_surface_geometry(frame, clip, surface)

    assert surface.geometry().getRect() == (0, 0, 800, 450)


def test_surface_goes_over_the_picture():
    """VLC fills its window with the picture, so the window places it."""
    frame, clip, surface = _frame_and_surface()

    apply_native_surface_geometry(frame, clip, surface, (100, 50, 400, 225))

    assert surface.geometry().getRect() == (100, 50, 400, 225)


def test_surface_takes_in_a_pixel_the_picture_is_partly_in():
    frame, clip, surface = _frame_and_surface()

    apply_native_surface_geometry(frame, clip, surface, (0, 87.5, 800, 224.5))

    assert surface.geometry().getRect() == (0, 87, 800, 225)


def test_surface_edges_on_whole_pixels_stay_there():
    frame, clip, surface = _frame_and_surface()

    apply_native_surface_geometry(
        frame, clip, surface, (0.1 + 0.2 - 0.3, 100.00000000001, 800, 250)
    )

    assert surface.geometry().getRect() == (0, 100, 800, 250)


def test_surface_geometry_ignores_unlaid_out_frame():
    frame, clip, surface = _frame_and_surface(QSize(0, 0))
    surface.setGeometry(-8, -8, 816, 466)

    apply_native_surface_geometry(frame, clip, surface)

    assert surface.geometry().getRect() == (-8, -8, 816, 466)


def test_the_clip_is_the_frame_with_no_part_on_show_to_cut_to():
    frame, clip, surface = _frame_and_surface()

    apply_native_surface_geometry(frame, clip, surface, (100, 50, 400, 225))

    assert clip.geometry().getRect() == (0, 0, 800, 450)


def test_the_clip_cuts_the_surface_down_to_the_part_on_show():
    """VLC draws all of the frame, crop and all, and only a part is on show."""
    frame, clip, surface = _frame_and_surface()

    apply_native_surface_geometry(
        frame, clip, surface, (-100, -200, 1000, 900), (150.5, 0, 500, 450)
    )

    assert clip.geometry().getRect() == (150, 0, 501, 450)
    # still over all of it, from where the clip is
    assert surface.geometry().getRect() == (-250, -200, 1000, 900)


def test_the_clip_is_no_bigger_than_the_frame():
    frame, clip, surface = _frame_and_surface()

    apply_native_surface_geometry(
        frame, clip, surface, (-100, -200, 1000, 900), (-50, -20, 1000, 900)
    )

    assert clip.geometry().getRect() == (0, 0, 800, 450)


def test_native_surface_is_kept_out_of_the_layout():
    """QStackedLayout would reset the surface to the frame rect on every
    resize, undoing the hw crop border offset between our updates."""
    frame = _StubHWFrame()

    layout = frame.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]

    assert frame.is_native_surface
    assert frame.video_surface not in items
    assert frame.video_clip not in items
    assert frame.video_surface.parent() is frame.video_clip
    assert frame.video_clip.parent() is frame


def test_software_surface_stays_in_the_layout():
    frame = _StubSWFrame()

    layout = frame.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]

    assert not frame.is_native_surface
    assert frame.video_surface in items


@pytest.mark.parametrize("frame_class", [_StubHWFrame, _StubSWFrame])
def test_no_snapshot_over_a_video_loaded_paused(frame_class):
    """The layout shows the first widget it is given: with the surface kept
    out of it, the snapshot, black over a video that never played."""
    window = QWidget()
    frame = frame_class(parent=window)
    window.show()

    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))
    frame.playback_status_changed_emit(True)

    assert not frame.pause_snapshot.isVisible()
    assert frame.video_surface.isVisible()

    window.close()


def _platform(monkeypatch, *, windows):
    monkeypatch.setattr(vlc_base.env, "IS_WINDOWS", windows)
    monkeypatch.setattr(vlc_base.env, "IS_LINUX", not windows)

    # the pretend platform would be asked for its colour scheme the real way
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: False)


def _placed_at(frame, monkeypatch, target):
    placement = ViewPlacement(source=(0, 0, 1, 1), target=target)
    monkeypatch.setattr(frame, "view_placement", lambda: placement)


def test_native_frame_stays_clear_for_audio_only(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame()

    frame.load_video_finish(MagicMock(is_audio_only=True))

    assert not frame.autoFillBackground()


def test_software_frame_keeps_default_background(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubSWFrame()

    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))

    assert not frame.autoFillBackground()


def test_native_surface_is_taken_out_of_the_qt_paint_path(monkeypatch):
    """Qt flushing its backing store over the vout window is the X11 flicker."""
    _platform(monkeypatch, windows=False)

    frame = _StubHWFrame()

    assert not frame.video_surface.updatesEnabled()


def test_native_surface_keeps_qt_painting_on_windows(monkeypatch):
    """VLC has its own child windows there; Qt never paints over the video."""
    _platform(monkeypatch, windows=True)

    frame = _StubHWFrame()

    assert frame.video_surface.updatesEnabled()


def test_software_surface_keeps_qt_painting(monkeypatch):
    """The software surface is a QLabel we paint ourselves."""
    _platform(monkeypatch, windows=False)

    frame = _StubSWFrame()

    assert frame.video_surface.updatesEnabled()


def test_native_frame_coalesces_resize_view_updates(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame()
    calls = []
    monkeypatch.setattr(type(frame), "adjust_view", lambda self: calls.append(1))

    for _ in range(3):
        frame._adjust_view_on_resize()

    # leading edge only; the rest is left to the trailing timer
    assert len(calls) == 1
    assert frame._resize_view_timer.isActive()


def test_coalesced_update_lands_once_the_resize_stops(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame()
    calls = []
    monkeypatch.setattr(type(frame), "adjust_view", lambda self: calls.append(1))

    frame._adjust_view_on_resize()
    frame._adjust_view_now()

    assert len(calls) == 2
    assert not frame._resize_view_timer.isActive()


def test_software_frame_applies_every_resize(monkeypatch):
    frame = _StubSWFrame()
    calls = []
    monkeypatch.setattr(type(frame), "adjust_view", lambda self: calls.append(1))

    for _ in range(3):
        frame._adjust_view_on_resize()

    assert len(calls) == 3
    assert not frame._resize_view_timer.isActive()


def _height_of_width(width, height):
    """A picture filling its window across, its height following."""
    return width * 9 // 16


def _playing_1080p(frame, cell_view_mode=VideoCellViewMode.FILL):
    frame.media = SimpleNamespace(
        cur_video_track=SimpleNamespace(
            video_dimensions=(1920, 1080),
            is_turned=False,
            orientation=VideoTransform.NONE,
            pixel_aspect=1,
        )
    )
    frame._view = frame._view._replace(cell_view_mode=cell_view_mode)
    frame.resize(550, 500)
