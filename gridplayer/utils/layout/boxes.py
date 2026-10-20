from __future__ import annotations

from typing import NamedTuple


class Box(NamedTuple):
    """Where a cell goes: its edges as shares of the area's width and height.

    Two cells that meet share the very same number for that edge, so once
    turned into pixels they meet with no gap and no overlap, whatever the
    area's size.
    """

    left: float
    top: float
    right: float
    bottom: float


FULL_BOX = Box(0.0, 0.0, 1.0, 1.0)


def grid_box(
    row: int,
    col: int,
    rows: int,
    cols: int,
    rowspan: int = 1,
    colspan: int = 1,
) -> Box:
    return Box(
        col / cols,
        row / rows,
        (col + colspan) / cols,
        (row + rowspan) / rows,
    )


def box_rect(box: Box, width: int, height: int) -> tuple[int, int, int, int]:
    """The box in an area of this size, as (x, y, width, height) in pixels."""

    left = round(box.left * width)
    top = round(box.top * height)
    right = round(box.right * width)
    bottom = round(box.bottom * height)
    return left, top, right - left, bottom - top
