from PyQt6.QtCore import QPointF, QRect, QRectF

from gridplayer.utils.layout.free_tiles import MOVE
from gridplayer.widgets.tile_frame import (
    LANDING,
    LANDING_ROUND,
    LIT_ARM,
    _edges,
    _lit,
    _sides,
)


def test_the_outline_is_along_the_tiles_outermost_pixels():
    rect = QRect(100, 50, 300, 200)

    lines = [line.boundingRect() for line in _edges(rect)]

    for line in lines:
        assert QRectF(rect).contains(line.topLeft())
        assert QRectF(rect).contains(line.bottomRight())
    # the right side, down the last column
    assert QRectF(399.5, 50.5, 0, 199) in lines


def test_a_side_is_lit_short_of_its_ends_a_corner_bends():
    rect = QRect(100, 50, 300, 210)

    (side,) = _lit(rect, (1, 0))
    assert side.boundingRect() == QRectF(395.5, 62.5, 0, 185)

    (corner,) = _lit(rect, (1, 1))
    bounds = corner.boundingRect()
    # its arms out from the corner, as long as they go
    assert bounds.bottomRight() == QPointF(395.5, 255.5)
    assert bounds.width() == bounds.height() == LIT_ARM

    assert _lit(rect, MOVE) == []


def test_the_sides_show_one_outline_each_pixel_by_one_window():
    rect = QRect(100, 50, 300, 200)

    lines = _sides(rect, LANDING, LANDING_ROUND)

    assert len(lines) == 4
    assert len({id(line.path) for line in lines}) == 1
    # the corners the top's and the bottom's, the rest the sides'
    for i, line in enumerate(lines):
        assert not any(line.window.intersects(o.window) for o in lines[i + 1 :])
    assert QRectF(rect).contains(lines[0].path.boundingRect())
    top, bottom, left, _right = (line.window for line in lines)
    assert left.top() == top.bottom() + 1
    assert left.bottom() == bottom.top() - 1


def test_a_flat_tile_has_no_side_pieces_between_its_corners():
    lines = _sides(QRect(0, 0, 300, 8))

    assert len(lines) == 2
