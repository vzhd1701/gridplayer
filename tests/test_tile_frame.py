from PyQt5.QtCore import QPointF, QRect, QRectF

from gridplayer.utils.layout.free_tiles import MOVE
from gridplayer.widgets.tile_frame import LIT_ARM, _edges, _lit


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
