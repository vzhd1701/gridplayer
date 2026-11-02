from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
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


class Weights(NamedTuple):
    """How much of the area's width each column takes, and of its height
    each row, the lines between them moved by hand (see GridLines).

    And in Auto, for a row (a column, in Columns First) whose lines are its
    own, how much of it each of its videos takes, by the row's index: a
    short last row that Fill Gaps spreads, or any row with Link Rows off.
    One with none takes the columns' (see line_weights).

    Kept for as many columns, rows or videos as there were then: with
    another count, they all take the same.
    """

    cols: tuple[float, ...] = ()
    rows: tuple[float, ...] = ()
    lines: tuple[tuple[float, ...], ...] = ()

    def line_weights(
        self, line: int, count: int, shared: tuple[float, ...]
    ) -> tuple[float, ...]:
        """A row's own weights, for as many videos as it has, else those
        it shares with the others."""

        own = self.lines[line] if line < len(self.lines) else ()
        return own if len(own) == count else shared

    def with_line(self, line: int, weights: tuple[float, ...]) -> Weights:
        """These, with a row's own weights set."""

        lines = list(self.lines) + [()] * (line + 1 - len(self.lines))
        lines[line] = weights
        while lines and not lines[-1]:
            lines.pop()
        return self._replace(lines=tuple(lines))


EVEN = Weights()


def line_edges(count: int, weights: Sequence[float] = ()) -> tuple[float, ...]:
    """Where the edges of count columns (or rows) are, as shares of the
    area from 0 to 1: as the weights have them, if there is one for each,
    else all the same width."""

    count = max(count, 1)

    if len(weights) != count or min(weights) <= 0:
        return tuple(index / count for index in range(count + 1))

    total = sum(weights)
    edges = [0.0]
    for weight in weights[:-1]:
        edges.append(edges[-1] + weight / total)
    edges.append(1.0)
    return tuple(edges)


def grid_box(
    row: int,
    col: int,
    rows: int,
    cols: int,
    rowspan: int = 1,
    colspan: int = 1,
    weights: Weights = EVEN,
) -> Box:
    col_edges = line_edges(cols, weights.cols)
    row_edges = line_edges(rows, weights.rows)
    return Box(
        col_edges[col],
        row_edges[row],
        col_edges[min(col + colspan, len(col_edges) - 1)],
        row_edges[min(row + rowspan, len(row_edges) - 1)],
    )


def box_rect(box: Box, width: int, height: int) -> tuple[int, int, int, int]:
    """The box in an area of this size, as (x, y, width, height) in pixels."""

    left = round(box.left * width)
    top = round(box.top * height)
    right = round(box.right * width)
    bottom = round(box.bottom * height)
    return left, top, right - left, bottom - top


def picture_score(
    placed: Iterable[tuple[Box, float]], width: int, height: int
) -> float:
    """How well pictures of these shapes (width for height) show in their
    boxes, in an area of this size.

    The sum of the logs of the pictures' areas, each fitted whole into its
    box: more picture scores higher, and one picture left small for the
    others to be big scores lower than all of them a fair size.
    """

    score = 0.0
    for box, shape in placed:
        box_width = (box.right - box.left) * width
        box_height = (box.bottom - box.top) * height
        picture_width = min(box_width, box_height * shape)
        score += math.log(picture_width * picture_width / shape)
    return score
