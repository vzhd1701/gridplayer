"""MPV's Direct output, the view: where mpv's window goes and how mpv is told to
place the picture in it (widgets/video_frame_mpv_window.py, player.WindowPicture)."""

import random
import struct

import pytest

from gridplayer.mpv_player.player import WindowPicture, _placing_options
from gridplayer.params import env
from gridplayer.utils.aspect_calc import ViewPlacement
from gridplayer.widgets.video_frame_mpv_window import (
    _covering,
    _is_window_whole,
    _on_picture_pixels,
    _whole_picture,
)
from gridplayer.widgets.video_frame_vlc_base import native_px
from tests.test_mpv_driver import _player


def _f32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def _mpv_cut(window: int, margin_a: str, margin_b: str, display: int, pixels: int,
             scale: str, pan: str):  # fmt: skip
    """mpv's sums for one side (video/out/aspect.c), keepaspect, video-unscaled
    and the picture aligned to the start: its own pixels from and to, and the
    window's pixels they're stretched over. In single floats, as mpv has them."""

    before = int(_f32(_f32(float(margin_a)) * window))
    after = int(_f32(_f32(float(margin_b)) * window))
    room = window - before - after

    scaled = int(_f32(display * _f32(float(scale))))
    dst_start = int(_f32(_f32(float(pan)) * scaled))
    dst_end = dst_start + scaled

    src_start, src_end = 0, pixels
    s_src, s_dst = src_end - src_start, dst_end - dst_start

    if dst_start < 0:
        src_start += -dst_start * s_src // s_dst
        dst_start = 0
    if dst_end > room:
        src_end -= (dst_end - room) * s_src // s_dst
        dst_end = room

    return src_start, src_end, before + dst_start, before + dst_end


@pytest.mark.parametrize("seed", range(4))
def test_mpv_cuts_the_picture_on_the_pixel_edges_picked(seed):
    rng = random.Random(seed)

    for _ in range(500):
        pixels = rng.randint(16, 4000)
        # a pixel of the picture a screen pixel or more, up to 40
        size = rng.randint(pixels, pixels * 40)
        start = rng.randint(-size + 20, 50)
        display = pixels if rng.random() < 0.5 else rng.randint(pixels // 2, pixels * 2)

        shown_from = max(start, 0) + rng.randint(0, 5)
        shown_to = min(start + size, 2000) - rng.randint(0, 5)
        if shown_to - shown_from < 2:
            continue

        left, right = _on_picture_pixels(start, size, pixels, shown_from, shown_to)

        assert left <= shown_from
        assert right >= shown_to

        # the window a little past those, mpv leaving that out as margins
        before, after = rng.randint(0, 3), rng.randint(0, 3)
        window = right - left + before + after

        options = _placing_options(
            WindowPicture(
                window=(window, window),
                margins=(before, before, after, after),
                picture=(start - left, start - left, size, size),
            ),
            (display, display),
        )
        cut = _mpv_cut(
            window,
            options["video-margin-ratio-left"],
            options["video-margin-ratio-right"],
            display,
            pixels,
            options["video-scale-x"],
            options["video-pan-x"],
        )
        src_from, src_to, dst_from, dst_to = cut

        # on the edges picked, and stretched over exactly what's between them
        assert left == start - (-src_from * size // pixels), cut
        assert right == start + src_to * size // pixels, cut
        assert (dst_from, dst_to) == (before, before + right - left), cut


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 1.75, 2.0])
def test_the_surface_covers_what_mpv_draws_on_whole_pixels_of_qt(ratio):
    for start in range(-30, 30):
        for end in range(start + 1, start + 40):
            first, last = _covering(start, end, ratio)

            assert native_px(first, ratio) <= start
            assert native_px(last, ratio) >= end
            # the least that does
            assert native_px(first + 1, ratio) > start
            assert native_px(last - 1, ratio) < end


def test_all_of_the_picture_from_the_part_on_show():
    # the middle half of a 640x360 frame, zoomed to a 1000x500 pane
    placement = ViewPlacement(source=(160, 90, 320, 180), target=(0, 0, 1000, 500))

    assert _whole_picture(placement, (640, 360)) == (-500, -250, 2000, 1000)


def test_a_window_over_all_of_the_picture_only_while_it_stays_small(monkeypatch):
    monkeypatch.setattr(env, "IS_WINDOWS", True)
    shown = (0, 0, 960, 540)

    # filled, a quarter of it cut off either side
    assert _is_window_whole((-480, 0, 1920, 1080), shown, 1.0)
    # zoomed 4x: 16 times what's on show, past the 4 allowed and the floor
    assert not _is_window_whole((-1440, -810, 3840, 2160), shown, 1.0)
    # a small cell zoomed in: not past 1080p, whatever its share
    assert _is_window_whole((0, 0, 1920, 1080), (0, 0, 200, 100), 1.0)
    # never as wide as Direct3D could refuse
    assert not _is_window_whole((0, 0, 9000, 100), (0, 0, 9000, 100), 1.0)


def test_never_a_window_past_the_part_on_show_off_windows(monkeypatch):
    monkeypatch.setattr(env, "IS_WINDOWS", False)

    assert not _is_window_whole((-480, 0, 1920, 1080), (0, 0, 960, 540), 1.0)


def _params(player, dw=640, dh=360, rotate=0):
    player.mpv.observers["video-params"](
        "video-params", {"w": dw, "h": dh, "dw": dw, "dh": dh, "rotate": rotate}
    )


def _sets(player):
    return {args[1]: args[2] for args in player.mpv.commands if args[0] == "set"}


_PLACED = WindowPicture(
    window=(400, 300), margins=(0, 0, 0, 2), picture=(-100, -50, 1280, 720)
)


def test_the_picture_is_placed_once_its_size_is_known():
    player = _player(wid=1234)

    player.set_window_picture(_PLACED)
    assert _sets(player) == {"keepaspect": "no"}

    _params(player)

    assert _sets(player)["keepaspect"] == "yes"
    assert float(_sets(player)["video-scale-x"]) == pytest.approx(1280.5 / 640)
    assert float(_sets(player)["video-pan-y"]) == pytest.approx(-50.25 / 720)


def test_only_what_changed_is_sent_again():
    player = _player(wid=1234)
    _params(player)
    player.set_window_picture(_PLACED)
    player.mpv.commands.clear()

    player.set_window_picture(_PLACED)
    assert _sets(player) == {}

    player.set_window_picture(_PLACED._replace(picture=(-101, -50, 1280, 720)))
    assert set(_sets(player)) == {"video-pan-x"}
    player.mpv.commands.clear()

    player.set_window_picture(None)
    assert _sets(player) == {"keepaspect": "no"}


def test_a_turn_places_the_picture_by_its_turned_size():
    player = _player(wid=1234)
    _params(player, rotate=90)

    player.set_window_picture(_PLACED)

    assert float(_sets(player)["video-scale-x"]) == pytest.approx(1280.5 / 360)


def test_nothing_is_placed_without_a_window_of_its_own():
    player = _player()
    _params(player)
    player.mpv.commands.clear()

    player.set_window_picture(_PLACED)

    assert _sets(player) == {}


def _raw(width=2, height=1, pixels=b"\x00\x00\xff\x00\xff\x00\x00\x00"):
    """screenshot-raw's answer: blue, green, red and a byte left out."""

    return {
        "w": width,
        "h": height,
        "stride": width * 4,
        "format": "bgr0",
        "data": pixels,
    }


def _screenshot(player):
    taken = []
    player.take_screenshot(taken.append)
    return taken


def test_a_screenshot_is_mpvs_picture_as_it_is():
    player = _player(wid=1234)

    taken = _screenshot(player)
    callback = player.mpv.callbacks[("screenshot-raw", "video")]
    callback(None, _raw())

    (image,) = taken
    assert (image.width(), image.height()) == (2, 1)
    assert image.pixelColor(0, 0).name() == "#ff0000"
    assert image.pixelColor(1, 0).name() == "#0000ff"


@pytest.mark.parametrize(
    ("error", "result"),
    [
        (RuntimeError("no video"), None),
        (None, {**_raw(), "format": "rgba64"}),
        (None, _raw(pixels=b"\x00" * 4)),
    ],
)
def test_no_screenshot_where_mpv_has_none_to_give(error, result):
    player = _player(wid=1234)

    taken = _screenshot(player)
    player.mpv.callbacks[("screenshot-raw", "video")](error, result)

    assert taken == [None]


def test_no_screenshot_asked_of_an_mpv_going():
    player = _player(wid=1234)
    player.close()
    player.mpv.commands.clear()

    assert _screenshot(player) == [None]
    assert not any(args[0] == "screenshot-raw" for args in player.mpv.commands)


@pytest.mark.parametrize(
    ("is_windows", "is_linux", "platform", "is_direct"),
    [
        (True, False, "windows", True),
        (False, True, "xcb", True),
        # a surface on Wayland is only its own client's to draw into
        (False, True, "wayland", False),
        # no windows to give mpv
        (True, False, "offscreen", False),
        (False, True, "offscreen", False),
        (False, False, "cocoa", False),
    ],
)
def test_direct_where_mpv_can_have_a_window(
    monkeypatch, is_windows, is_linux, platform, is_direct
):
    from gridplayer.params.static import MpvOutput
    from gridplayer.utils import video_driver

    monkeypatch.setattr(env, "IS_WINDOWS", is_windows)
    monkeypatch.setattr(env, "IS_LINUX", is_linux)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: platform)

    assert video_driver.is_mpv_window_output(MpvOutput.WINDOW) is is_direct
    assert not video_driver.is_mpv_window_output(MpvOutput.READBACK)


def test_a_window_with_no_room_gets_the_picture_stretched_over_it():
    player = _player(wid=1234)
    _params(player)

    player.set_window_picture(_PLACED._replace(window=(400, 0)))

    assert _sets(player) == {"keepaspect": "no"}


def test_a_picture_less_than_a_pixel_high_is_placed_one_high():
    from unittest.mock import MagicMock

    from PyQt5.QtCore import QSize

    from gridplayer.widgets.video_frame_mpv_window import VideoFrameMpvWindow

    frame = MagicMock()
    frame.video_surface.devicePixelRatioF.return_value = 1.0
    frame._view_frame_size.return_value = (6400, 10)
    frame._transform = None
    frame.size.return_value = QSize(400, 300)
    frame._shown_flip.return_value = None
    frame._whole_rows.return_value = 0

    # a very wide clip fitted in a cell: 0.625 of a pixel high
    placement = ViewPlacement(source=(0, 0, 6400, 10), target=(0, 150, 400, 0.625))
    picture = _whole_picture(placement, (6400, 10))

    view = VideoFrameMpvWindow._placed(frame, placement, picture, placement.target)

    assert view.window_picture.picture[2:] == (400, 1)

    player = _player(wid=1234)
    _params(player, dw=6400, dh=10)
    player.set_window_picture(view.window_picture)


def _subtitle_view_pushed(view):
    """What a frame tells mpv of the line for a view, with no frame made."""

    from unittest.mock import MagicMock

    from gridplayer.widgets.video_frame_mpv_window import VideoFrameMpvWindow

    frame = MagicMock()
    frame._is_subtitle_on_show.return_value = True
    frame._view_frame_size.return_value = (640, 360)
    frame._full_render_size.return_value = (1200, 675)
    frame.video_surface.devicePixelRatioF.return_value = 1.0

    VideoFrameMpvWindow._push_subtitle_view(frame, view)

    return frame.video_driver.set_subtitle_view.call_args.args[0]


def test_a_line_over_part_of_the_picture_is_laid_out_by_all_of_it():
    # Fill in a wide cell, the bottom cut off: the same, whether mpv's window
    # is over all of the picture or only the part on show
    from gridplayer.mpv_player.subtitles import subtitle_view
    from gridplayer.widgets.video_frame_mpv_window import _SurfaceView

    placement = ViewPlacement(source=(0, 0, 640, 160), target=(0, 0, 1200, 300))
    whole = _SurfaceView(((0, 0), (0, 0, 1200, 675), None, None), None, placement)
    part = _SurfaceView(
        whole.layout,
        WindowPicture(
            window=(1200, 300), margins=(0, 0, 0, 0), picture=(0, 0, 1200, 675)
        ),
        placement,
    )

    expected = subtitle_view((0, 0, 640, 160), (640, 360), (1200, 675), 675)

    assert _subtitle_view_pushed(whole) == expected
    assert _subtitle_view_pushed(part) == expected
