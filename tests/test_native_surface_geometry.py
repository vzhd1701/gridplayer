from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QMargins, QSize, Qt
from PyQt5.QtWidgets import QApplication, QWidget

import gridplayer.widgets.video_frame_vlc_base as vlc_base
from gridplayer.params.static import (
    HWCropBorderOffset,
    VideoCellViewMode,
    VideoTransform,
)
from gridplayer.utils import darkmode
from gridplayer.utils.aspect_calc import ViewPlacement
from gridplayer.widgets.video_frame_vlc_base import (
    apply_vlc_hw_surface_geometry,
    calc_picture_block_padding,
)
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


DEFAULT_SIZE = QSize(800, 450)


def _frame_and_surface(size=DEFAULT_SIZE):
    frame = QWidget()
    frame.resize(size)
    clip = QWidget(frame)
    surface = QWidget(clip)
    return frame, clip, surface


def test_surface_geometry_applies_offset():
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(frame, clip, surface, 8)

    assert surface.geometry().getRect() == (-8, -8, 816, 466)


def test_surface_geometry_still_sizes_surface_without_offset():
    """The native surface is not in the layout, so nothing else would size it."""
    frame, clip, surface = _frame_and_surface()
    surface.setGeometry(-8, -8, 816, 466)

    apply_vlc_hw_surface_geometry(frame, clip, surface, 0)

    assert surface.geometry().getRect() == (0, 0, 800, 450)


def test_surface_goes_over_the_picture():
    """VLC fills its window with the picture, so the window places it."""
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(frame, clip, surface, 8, (100, 50, 400, 225))

    assert surface.geometry().getRect() == (92, 42, 416, 241)


def test_surface_takes_in_a_pixel_the_picture_is_partly_in():
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(frame, clip, surface, 0, (0, 87.5, 800, 224.5))

    assert surface.geometry().getRect() == (0, 87, 800, 225)


def test_surface_edges_on_whole_pixels_stay_there():
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(
        frame, clip, surface, 0, (0.1 + 0.2 - 0.3, 100.00000000001, 800, 250)
    )

    assert surface.geometry().getRect() == (0, 100, 800, 250)


def test_surface_geometry_ignores_unlaid_out_frame():
    frame, clip, surface = _frame_and_surface(QSize(0, 0))
    surface.setGeometry(-8, -8, 816, 466)

    apply_vlc_hw_surface_geometry(frame, clip, surface, 8)

    assert surface.geometry().getRect() == (-8, -8, 816, 466)


def test_the_clip_is_the_frame_with_no_part_on_show_to_cut_to():
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(frame, clip, surface, 8, (100, 50, 400, 225))

    assert clip.geometry().getRect() == (0, 0, 800, 450)


def test_the_clip_cuts_the_surface_down_to_the_part_on_show():
    """VLC draws all of the frame, crop and all, and only a part is on show."""
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(
        frame, clip, surface, 8, (-100, -200, 1000, 900), (150.5, 0, 500, 450)
    )

    assert clip.geometry().getRect() == (150, 0, 501, 450)
    # still over all of it, from where the clip is
    assert surface.geometry().getRect() == (-258, -208, 1016, 916)


def test_the_clip_is_no_bigger_than_the_frame():
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(
        frame, clip, surface, 8, (-100, -200, 1000, 900), (-50, -20, 1000, 900)
    )

    assert clip.geometry().getRect() == (0, 0, 800, 450)


def test_native_surface_is_kept_out_of_the_layout():
    """QStackedLayout would reset the surface to the frame rect on every
    resize, undoing the hw crop border offset between our updates."""
    frame = _StubHWFrame(vlc_options=[])

    layout = frame.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]

    assert frame.is_native_surface
    assert frame.video_surface not in items
    assert frame.video_clip not in items
    assert frame.video_surface.parent() is frame.video_clip
    assert frame.video_clip.parent() is frame


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

    # the pretend platform would be asked for its colour scheme the real way
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: False)


def test_native_frame_fills_uncovered_area_black_once_loaded(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])

    # the loading status shows through the frame until a track is playing
    assert not frame.autoFillBackground()

    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))

    assert frame.autoFillBackground()
    assert frame.palette().color(frame.backgroundRole()) == Qt.black


def test_native_frame_is_not_filled_on_x11(monkeypatch):
    """Measured on X11: the cell is ~85% filler through a drag whatever we do,
    so a fill only adds a second colour and reads as tearing."""
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=False)
    frame = _StubHWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))

    assert not frame.autoFillBackground()


def _placed_at(frame, monkeypatch, target):
    placement = ViewPlacement(source=(0, 0, 1, 1), target=target)
    monkeypatch.setattr(frame, "view_placement", lambda: placement)


def test_native_frame_fills_the_letterbox_black_on_x11(monkeypatch):
    """The surface is over the picture only, the rest is Qt's to paint."""
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=False)
    frame = _StubHWFrame(vlc_options=[])
    frame.resize(DEFAULT_SIZE)
    _placed_at(frame, monkeypatch, (0, 0, 400, 450))

    frame._place_native_surface()

    assert frame.video_surface.geometry().getRect() == (-8, -8, 416, 466)
    assert frame.autoFillBackground()
    assert frame.palette().color(frame.backgroundRole()) == Qt.black


def test_native_frame_is_not_filled_on_x11_while_covered(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=False)
    frame = _StubHWFrame(vlc_options=[])
    frame.resize(DEFAULT_SIZE)
    _placed_at(frame, monkeypatch, (0, 0, 800, 450))

    frame._place_native_surface()

    assert frame.video_surface.geometry().getRect() == (-8, -8, 816, 466)
    assert not frame.autoFillBackground()


def test_native_surface_covers_the_frame_with_no_picture_to_go_by(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])
    frame.resize(DEFAULT_SIZE)
    monkeypatch.setattr(frame, "view_placement", lambda: None)

    frame._place_native_surface()

    assert frame.video_surface.geometry().getRect() == (-8, -8, 816, 466)


def test_native_frame_stays_clear_for_audio_only(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=True))

    assert not frame.autoFillBackground()


def test_software_frame_keeps_default_background(monkeypatch):
    _platform(monkeypatch, windows=True)
    frame = _StubSWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))

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


def _height_of_width(width, height):
    """A picture filling its window across, its height following."""
    return width * 9 // 16


def test_no_padding_where_the_picture_is_whole_blocks_already():
    assert calc_picture_block_padding(QSize(448, 260), 1.0, _height_of_width) == (
        QMargins()
    )


def test_padding_across_where_the_width_makes_the_height():
    """442 across makes the picture 248, 444 makes it 249: 442 is kept,
    but 443 needs growing to the next width that comes out whole."""
    padding = calc_picture_block_padding(QSize(443, 260), 1.0, _height_of_width)

    width = 443 + padding.left() + padding.right()
    assert _height_of_width(width, 260) % 4 == 0
    assert padding.top() == padding.bottom() == 0
    assert abs(padding.left() - padding.right()) <= 1


def test_padding_down_where_the_picture_fills_the_height():
    padding = calc_picture_block_padding(QSize(300, 249), 1.0, lambda w, h: h)

    assert padding == QMargins(0, 1, 0, 2)


def test_padding_in_the_windows_own_pixels():
    """At 150% one Qt pixel more is one or two of the window's."""
    padding = calc_picture_block_padding(QSize(300, 166), 1.5, lambda w, h: h)

    height = int((166 + padding.top() + padding.bottom()) * 1.5 + 0.5)
    assert height % 4 == 0


def test_no_padding_where_the_picture_is_not_known():
    assert calc_picture_block_padding(QSize(300, 249), 1.0, lambda w, h: None) == (
        QMargins()
    )


def test_surface_grown_by_the_padding():
    frame, clip, surface = _frame_and_surface()

    apply_vlc_hw_surface_geometry(frame, clip, surface, 8, padding=QMargins(1, 0, 2, 0))

    assert surface.geometry().getRect() == (-9, -8, 819, 466)


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


def test_paused_picture_goes_where_vlc_draws_it(monkeypatch):
    """VLC scales its picture up into the surface's hidden margin, so the
    snapshot of it goes past the pane as far: not over the bare target."""
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])
    _playing_1080p(frame)

    assert frame.view_placement().target == (0, 0, 550, 500)
    # the surface is (-8, -8, 567, 516), a pixel wider for whole blocks
    assert frame._shown_picture_rect() == (-8, -8, 567, 516)


def test_paused_picture_a_row_lower_under_opengl(monkeypatch):
    """VLC's OpenGL output puts an odd row left over above the picture."""
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=False)
    frame = _StubHWFrame(vlc_options=[])
    _playing_1080p(frame, cell_view_mode=VideoCellViewMode.FIT)

    # surface (-8, 87, 566, 326), the picture 317 rows of it, VLC working
    # out 4 above and 5 below
    assert frame._shown_picture_rect() == (-8, 92, 566, 317)


def test_paused_picture_of_a_software_frame_is_the_target(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubSWFrame(vlc_options=[])
    frame.resize(DEFAULT_SIZE)
    _placed_at(frame, monkeypatch, (100, 0, 600, 450))

    assert frame._shown_picture_rect() == (100, 0, 600, 450)


def test_paused_picture_nowhere_with_no_frame_size(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])
    frame.resize(DEFAULT_SIZE)

    assert frame._shown_picture_rect() is None


def test_the_aspect_ratio_picked_shapes_the_picture(monkeypatch):
    _stub_offset_setting(monkeypatch)
    _platform(monkeypatch, windows=True)
    frame = _StubHWFrame(vlc_options=[])
    _playing_1080p(frame, cell_view_mode=VideoCellViewMode.FIT)

    frame._view = frame._view._replace(aspect_ratio="1:1")

    assert frame.picture_rect() == pytest.approx((25, 0, 500, 500))
