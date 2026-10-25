import pytest

from gridplayer.params.static import StripSide
from gridplayer.utils.layout.boxes import Weights
from gridplayer.utils.layout.lines import Line, SnapKind
from gridplayer.utils.layout.strip import (
    STRIP_MOST,
    STRIP_PER_LINE,
    StripLines,
    strip_layout,
    strip_share,
    strip_weights,
)

WIDE = 16 / 9


def _px(box, width, height):
    return (
        round(box.left * width),
        round(box.top * height),
        round(box.right * width),
        round(box.bottom * height),
    )


def test_a_wide_window_has_the_strip_on_the_right():
    strip = strip_layout(3, 1920, 1080, WIDE)

    assert strip.is_side
    # four to a line at first, a quarter of the height each
    assert [_px(b, 1920, 1080) for b in strip.boxes] == [
        (1440, 135, 1920, 405),
        (1440, 405, 1920, 675),
        (1440, 675, 1920, 945),
    ]
    assert _px(strip.main, 1920, 1080) == (0, 0, 1440, 1080)


def test_a_tall_window_has_the_strip_along_the_bottom():
    strip = strip_layout(2, 1080, 1920, WIDE)

    assert not strip.is_side
    main = _px(strip.main, 1080, 1920)
    assert main[:3] == (0, 0, 1080)
    for box in strip.boxes:
        left, top, right, bottom = _px(box, 1080, 1920)
        assert top >= main[3]
        # tiles of the videos' shape
        assert (right - left) / (bottom - top) == pytest.approx(WIDE, rel=0.02)


def test_more_videos_take_more_lines_not_smaller_tiles():
    # a window wide enough for two lines
    one = strip_layout(STRIP_PER_LINE, 2560, 1080, WIDE)
    two = strip_layout(STRIP_PER_LINE + 1, 2560, 1080, WIDE)

    width_of = [b.right - b.left for b in one.boxes]
    assert {round(w, 6) for w in width_of} == {round(one.share, 6)}
    assert two.share == pytest.approx(2 * one.share)
    assert sorted({round(b.left, 6) for b in two.boxes}) == [
        round(1 - two.share, 6),
        round(1 - two.share / 2, 6),
    ]


def test_the_strip_takes_at_most_its_share_its_tiles_then_smaller():
    strip = strip_layout(20, 1920, 1080, WIDE)

    assert strip.share == STRIP_MOST
    # all in the strip, none over another
    for box in strip.boxes:
        assert box.left >= 1 - STRIP_MOST - 1e-9
        assert 0 <= box.top < box.bottom <= 1
    corners = {(round(b.left, 6), round(b.top, 6)) for b in strip.boxes}
    assert len(corners) == 20


def test_a_strip_moved_by_hand_keeps_its_share():
    strip = strip_layout(3, 1920, 1080, WIDE, share=0.3)

    assert strip.share == pytest.approx(0.3)
    assert strip_share(strip_weights(0.3)) == pytest.approx(0.3)
    assert strip_share(Weights()) is None


def test_the_strip_line_moves_and_snaps_where_the_big_video_fits():
    lines = StripLines(3, 1920, 1080, WIDE, main_shape=4 / 3)
    line = lines.line_at(1440, 500, 4)

    assert line == Line(True, 0)
    assert lines.line_at(1400, 500, 4) is None
    assert lines.position(line) == 1440
    assert lines.is_even()

    snaps = lines.snaps(line)
    # the 4:3 one fits 1440 wide; the three fill the height in one line
    assert (1440, SnapKind.FITS, -1) in [
        (round(t.position), t.kind, t.side) for t in snaps
    ]
    assert any(t.side == 1 for t in snaps)

    moved = lines.moved(line, 1200)
    assert lines.position(line, moved) == 1200
    assert strip_share(moved) == pytest.approx(0.375)
    # as at first
    assert lines.evened(line) == Weights()
    assert lines.weights() == Weights()


def test_the_strip_goes_on_the_side_picked():
    right = strip_layout(3, 1920, 1080, WIDE)
    left = strip_layout(3, 1920, 1080, WIDE, side=StripSide.LEFT)

    # the right one turned round
    assert left.is_side
    assert left.is_before
    assert [_px(b, 1920, 1080) for b in left.boxes] == [
        (0, 135, 480, 405),
        (0, 405, 480, 675),
        (0, 675, 480, 945),
    ]
    assert _px(left.main, 1920, 1080) == (480, 0, 1920, 1080)
    assert left.share == right.share

    # along the bottom, or the top, of a wide window too
    bottom = strip_layout(3, 1920, 1080, WIDE, side=StripSide.BOTTOM)
    top = strip_layout(3, 1920, 1080, WIDE, side=StripSide.TOP)
    assert not bottom.is_side
    assert not top.is_side
    assert _px(bottom.main, 1920, 1080)[:2] == (0, 0)
    assert _px(top.main, 1920, 1080)[3] == 1080
    for box in top.boxes:
        assert _px(box, 1920, 1080)[3] <= _px(top.main, 1920, 1080)[1]

    # and on the right of a tall one
    assert strip_layout(3, 1080, 1920, WIDE, side=StripSide.RIGHT).is_side


def test_the_strip_line_on_the_left_moves_and_snaps_turned_round():
    lines = StripLines(3, 1920, 1080, WIDE, main_shape=4 / 3, side=StripSide.LEFT)
    line = lines.line_at(480, 500, 4)

    assert line == Line(True, 0)
    assert lines.position(line) == 480

    # the 4:3 one fits 1440 wide, on the right of the line now
    assert (480, SnapKind.FITS, 1) in [
        (round(t.position), t.kind, t.side) for t in lines.snaps(line)
    ]

    moved = lines.moved(line, 720)
    assert lines.position(line, moved) == 720
    # the same share as a right one's line moved to 1200
    assert strip_share(moved) == pytest.approx(0.375)


def test_an_area_with_no_size_yet_is_laid_out_all_the_same():
    for width, height in ((0, 0), (800, 0), (0, 600)):
        strip = strip_layout(3, width, height, WIDE)
        assert len(strip.boxes) == 3
