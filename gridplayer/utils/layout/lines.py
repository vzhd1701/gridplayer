from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from enum import Enum, auto
from typing import NamedTuple

from gridplayer.utils.layout.boxes import Box, Weights, line_edges

# a cell is never made narrower or shorter than this by a line moved, in
# pixels, unless the cells next to the line have not that much between them
MIN_CELL = 48

# how near a line moved comes to where it snaps before it does, and how far
# it then has to go to let go: further, or it would flicker at the edge
SNAP_REACH = 8
SNAP_HOLD = 12

# two edges are the same line if they are this near, as shares
_SAME = 1e-9


class Line(NamedTuple):
    """A line between the columns (or the rows) of a grid: the one after
    the column (row) of this index. Or one between the videos of a row
    (column) whose lines are its own, the row of index own (see
    Weights.lines)."""

    is_column: bool
    index: int
    own: int | None = None


class SnapKind(Enum):
    # a video next to the line just fits its cell, no bars
    FITS = auto()
    # in line with one in the row (column) before or after, of a row whose
    # lines are its own
    ALIGNED = auto()
    # the cells on either side of the line the same size
    EVEN = auto()


class Target(NamedTuple):
    """A place a line being moved snaps to, in pixels, and why."""

    position: float
    kind: SnapKind


# the name of a set of lines: "cols", "rows", or a row's own by its index
LineSet = str | int


class GridLines:
    """The lines between the cells of a grid laid out in an area, as they
    are and as they can be moved.

    cells has each cell's box and its picture's width for its height, None
    for one with no picture. own has the rows (the columns, if is_columns:
    Auto in Columns First) whose lines between the videos are their own,
    and how many places each has for them (see FlowLayout.own_lines). The
    grid's columns go only between the other rows' cells.
    """

    def __init__(
        self,
        cells: Sequence[tuple[Box, float | None]],
        cols: int,
        rows: int,
        weights: Weights,
        width: int,
        height: int,
        own: Mapping[int, int] | None = None,
        is_columns: bool = False,
    ):
        self.cols = max(cols, 1)
        self.rows = max(rows, 1)
        self.own = dict(own or {})
        self.width = width
        self.height = height

        self._weights = weights
        self._is_columns = is_columns

        # the lines along a row, those of the grid, and those across
        self._along, self._across = ("rows", "cols") if is_columns else ("cols", "rows")

        self._counts: dict[LineSet, int] = {"cols": self.cols, "rows": self.rows}
        if set(range(self._counts[self._across])) <= set(self.own):
            # every row's are its own: the grid has none along them
            del self._counts[self._along]
        self._counts.update(self.own)

        self._edges = self._edges_for(weights)

        # the cells by the row whose own lines they go between, None for
        # the others
        across_edges = self._edges[self._across]
        self._cells: dict[int | None, list] = {None: []}
        for box, shape in cells:
            start = box.left if is_columns else box.top
            row = next(
                (
                    row
                    for row in self.own
                    if row < len(across_edges) - 1
                    and abs(across_edges[row] - start) < _SAME
                ),
                None,
            )
            self._cells.setdefault(row, []).append((box, shape))

    def weights(self) -> Weights:
        """The lines as they are, whether moved or not."""

        weights = self._weights
        for name in ("cols", "rows"):
            if name in self._edges:
                weights = weights._replace(**{name: _shares(self._edges[name])})
        for row in self.own:
            weights = weights.with_line(row, _shares(self._edges[row]))
        return weights

    def is_even(self) -> bool:
        return all(
            edges == line_edges(len(edges) - 1) for edges in self._edges.values()
        )

    def is_at(self, weights: Weights) -> bool:
        """Whether every line is where the weights have it, to the pixel."""

        for name, other in self._edges_for(weights).items():
            size = self.width if self._is_column(name) else self.height
            for edge, moved in zip(self._edges[name], other):
                if round(edge * size) != round(moved * size):
                    return False
        return True

    def evened(self, line: Line) -> Weights:
        """The lines with all those the way of this one even: of the grid,
        or of the row whose own it is."""

        name = self._set_of(line)
        if line.own is not None:
            count = self._counts[name]
            return self.weights().with_line(name, (1 / count,) * count)
        return self.weights()._replace(**{name: ()})

    def position(self, line: Line, weights: Weights | None = None) -> int:
        """Where the line is, in pixels from the area's left (top), as the
        cells' edges are; or where it is with the lines as the weights have
        them."""

        edges = self._edges if weights is None else self._edges_for(weights)
        return round(edges[self._set_of(line)][line.index + 1] * self._size(line))

    def span(self, line: Line) -> tuple[int, int]:
        """Where the line goes from and to, across its cells, in pixels."""

        starts, ends = [], []
        for box, _shape in self._next_to(line):
            start, end = (
                (box.top, box.bottom) if line.is_column else (box.left, box.right)
            )
            starts.append(start)
            ends.append(end)

        across = self.height if line.is_column else self.width
        return round(min(starts) * across), round(max(ends) * across)

    def line_at(self, x: float, y: float, reach: float) -> Line | None:
        """The line that a point in the area is this near, in pixels, the
        nearest if there are two."""

        found = []
        for name, edges in self._edges.items():
            is_column = self._is_column(name)
            along, across = (x, y) if is_column else (y, x)
            across_size = self.height if is_column else self.width
            own = name if isinstance(name, int) else None

            for index in range(len(edges) - 2):
                line = Line(is_column, index, own)
                distance = abs(along - edges[index + 1] * self._size(line))
                if distance > reach:
                    continue

                for box, _shape in self._next_to(line):
                    start, end = (
                        (box.top, box.bottom) if is_column else (box.left, box.right)
                    )
                    if start * across_size <= across <= end * across_size:
                        found.append((distance, line))
                        break

        if not found:
            return None
        return min(found)[1]

    def moved(self, line: Line, position: float) -> Weights:
        """The lines with this one moved to a position, in pixels, as far
        as the cells on either side of it can give."""

        name = self._set_of(line)
        edges = list(self._edges[name])
        low, high = self._room(line)
        edges[line.index + 1] = min(max(position / self._size(line), low), high)

        if line.own is not None:
            return self.weights().with_line(name, _shares(edges))
        return self.weights()._replace(**{name: _shares(edges)})

    def snaps(self, line: Line) -> list[Target]:
        """Where the line snaps to: where a video next to it just fits its
        cell; for one of a row whose lines are its own, in line with one of
        the row before or after; and where the cells on either side are the
        same size. Where two are the same place, it is the first of those.
        """

        size = self._size(line)
        edges = self._edges[self._set_of(line)]
        edge = edges[line.index + 1]

        fits = []

        for box, shape in self._next_to(line):
            if not shape:
                continue

            if line.is_column:
                start, end = box.left * size, box.right * size
                fitting = (box.bottom - box.top) * self.height * shape
            else:
                start, end = box.top * size, box.bottom * size
                fitting = (box.right - box.left) * self.width / shape

            if abs((box.right if line.is_column else box.bottom) - edge) < _SAME:
                fits.append(start + fitting)
            if abs((box.left if line.is_column else box.top) - edge) < _SAME:
                fits.append(end - fitting)

        aligned = []
        if line.own is not None:
            for row in (line.own - 1, line.own + 1):
                name = row if row in self.own else self._along
                if 0 <= row < self._counts[self._across] and name in self._edges:
                    aligned.extend(e * size for e in self._edges[name][1:-1])

        even = (edges[line.index] + edges[line.index + 2]) / 2 * size

        targets = []
        for kind, positions in (
            (SnapKind.FITS, fits),
            (SnapKind.ALIGNED, aligned),
            (SnapKind.EVEN, [even]),
        ):
            for position in positions:
                if all(abs(t.position - position) >= 0.5 for t in targets):
                    targets.append(Target(position, kind))

        low, high = self._room(line)
        return sorted(
            {t for t in targets if low * size <= t.position <= high * size},
            key=lambda t: t.position,
        )

    def _edges_for(self, weights: Weights) -> dict[LineSet, tuple[float, ...]]:
        """Where the lines are with the weights, as shares of the area."""

        along = getattr(weights, self._along)
        edges = {}
        for name, count in self._counts.items():
            if isinstance(name, int):
                edges[name] = line_edges(
                    count, weights.line_weights(name, count, along)
                )
            else:
                edges[name] = line_edges(count, getattr(weights, name))
        return edges

    def _set_of(self, line: Line) -> LineSet:
        """Which set of lines the line is in."""

        if line.own is not None:
            return line.own
        return "cols" if line.is_column else "rows"

    def _is_column(self, name: LineSet) -> bool:
        if isinstance(name, int):
            return not self._is_columns
        return name == "cols"

    def _next_to(self, line: Line) -> list[tuple[Box, float | None]]:
        """The cells with an edge on the line."""

        name = self._set_of(line)
        edge = self._edges[name][line.index + 1]

        if line.own is not None:
            cells = self._cells.get(line.own, [])
        elif name == self._along:
            cells = self._cells[None]
        else:
            cells = [cell for row_cells in self._cells.values() for cell in row_cells]

        def is_on(box: Box) -> bool:
            if line.is_column:
                sides = (box.left, box.right)
            else:
                sides = (box.top, box.bottom)
            return any(abs(side - edge) < _SAME for side in sides)

        return [(box, shape) for box, shape in cells if is_on(box)]

    def _room(self, line: Line) -> tuple[float, float]:
        """How far the line can go either way, as shares."""

        edges = self._edges[self._set_of(line)]
        low, high = edges[line.index], edges[line.index + 2]
        least = min(MIN_CELL / max(self._size(line), 1), (high - low) / 4)
        return low + least, high - least

    def _size(self, line: Line) -> int:
        return self.width if line.is_column else self.height


class Snap:
    """Where a line being moved goes: to a place it snaps to once near
    enough, and from it only once far enough (see SNAP_REACH, SNAP_HOLD).
    """

    def __init__(self, reach: float = SNAP_REACH, hold: float = SNAP_HOLD):
        self.reach = reach
        self.hold = hold
        self.target: Target | None = None

    def __call__(self, position: float, targets: Sequence[Target]) -> float:
        target = self.target
        if target is not None and abs(position - target.position) <= self.hold:
            return target.position

        near = [t for t in targets if abs(position - t.position) <= self.reach]
        if near:
            self.target = min(near, key=lambda t: abs(position - t.position))
            return self.target.position

        self.target = None
        return position

    def let_go(self) -> None:
        self.target = None


class Span(NamedTuple):
    """Which lines a cell's width (or height) goes between: from the one
    before the column (row) of this index, of the set named (see
    GridLines), over this many."""

    lines: LineSet
    start: int
    count: int = 1


class FitCell(NamedTuple):
    """A cell for fit_weights: the lines its width and its height go
    between, and its picture's width for its height."""

    width: Span
    height: Span
    shape: float

    @classmethod
    def at(cls, row, col, shape, rowspan=1, colspan=1) -> FitCell:
        """A cell of the grid, its width and height between its lines."""

        return cls(Span("cols", col, colspan), Span("rows", row, rowspan), shape)


# how hard fit_weights rounds off the corner where a picture stops filling
# its cell's width and starts filling its height, from soft to all but
# sharp, and how many steps it takes at each
_FIT_SOFTNESS = (0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002)
_FIT_STEPS = 120

# how strongly fit_weights keeps the lines even where moving them shows no
# more of any picture
_FIT_EVENNESS = 0.002

# the narrowest a line is made, for its share of an even grid
_FIT_LEAST = 0.2


def fit_weights(
    cells: Sequence[FitCell],
    cols: int,
    rows: int,
    width: int,
    height: int,
    own: Mapping[int, int] | None = None,
) -> Weights:
    """The lines that show the pictures in these cells best, in an area of
    this size, with these rows having lines of their own (see GridLines):
    as picture_score has it, the sum of the logs of the pictures' areas,
    each fitted whole into its cell.

    That is the most of every picture, none of them left small for the
    others. Where moving a line shows no more of any picture, as when the
    bars cannot all go, the lines are kept as near even as they can be.

    The score is a concave function of the lines' shares, so it is climbed
    with no fear of stopping short, on a slightly rounded copy of it,
    rounded less at each round (_FIT_SOFTNESS).
    """

    counts: dict[LineSet, int] = {"cols": max(cols, 1), "rows": max(rows, 1)}
    counts.update((row, max(count, 1)) for row, count in (own or {}).items())
    if not cells or width <= 0 or height <= 0:
        return Weights()

    params = {name: [0.0] * count for name, count in counts.items()}

    step = 0.1
    for softness in _FIT_SOFTNESS:
        value, slopes = _fit_slopes(cells, params, width, height, softness)
        for _ in range(_FIT_STEPS):
            # the longest step that still climbs
            while step > 1e-9:
                stepped = {
                    name: [p + step * s for p, s in zip(params[name], slopes[name])]
                    for name in params
                }
                next_value, next_slopes = _fit_slopes(
                    cells, stepped, width, height, softness
                )
                if next_value >= value:
                    params, value, slopes = stepped, next_value, next_slopes
                    step *= 1.5
                    break
                step *= 0.5
            else:
                step = 1e-3
                break

    fitted = {name: _from_params(p) for name, p in params.items()}
    even = {name: _from_params([0.0] * count) for name, count in counts.items()}

    # no better than even, it would only move the lines for nothing
    if _fit_score(cells, fitted, width, height) <= _fit_score(
        cells, even, width, height
    ) + 1e-6 * len(cells):
        return Weights()

    # those between no cells, as the grid's columns where every row has
    # its own, are left out
    used = {span.lines for cell in cells for span in (cell.width, cell.height)}

    def rounded(name):
        if name not in used:
            return ()
        return tuple(round(share, 5) for share in fitted[name])

    weights = Weights(rounded("cols"), rounded("rows"))
    for row in sorted(own or {}):
        weights = weights.with_line(row, rounded(row))
    return weights


def _from_params(params: Sequence[float]) -> tuple[float, ...]:
    """Shares from free numbers: each at least _FIT_LEAST of an even one."""

    count = len(params)
    least = _FIT_LEAST / count
    top = max(params)
    powers = [math.exp(p - top) for p in params]
    total = sum(powers)
    return tuple(least + (1 - count * least) * p / total for p in powers)


def _span_share(shares, span: Span) -> tuple[range, float]:
    """The lines a span goes over, and its share of the area."""

    lines = shares[span.lines]
    indexes = range(span.start, min(span.start + span.count, len(lines)))
    return indexes, sum(lines[i] for i in indexes)


def _fit_score(cells, shares, width, height) -> float:
    # picture_score's, the cells' sizes from the shares
    score = 0.0
    for cell in cells:
        _, cell_width = _span_share(shares, cell.width)
        _, cell_height = _span_share(shares, cell.height)
        picture_width = min(width * cell_width, height * cell_height * cell.shape)
        score += math.log(picture_width * picture_width / cell.shape)
    return score


def _fit_slopes(cells, params, width, height, softness):
    """The rounded score of fit_weights with the lines where these numbers
    put them, and how fast it goes up with each number."""

    shares = {name: _from_params(p) for name, p in params.items()}
    slopes = {name: [0.0] * len(p) for name, p in params.items()}

    value = 0.0
    for cell in cells:
        width_lines, cell_width = _span_share(shares, cell.width)
        height_lines, cell_height = _span_share(shares, cell.height)

        # the logs of the picture's width filling the cell's width, and
        # filling its height: it is the smaller, rounded off
        by_width = math.log(width * cell_width)
        by_height = math.log(height * cell_height * cell.shape)
        over = (by_width - by_height) / softness
        if over > 0:
            power = math.exp(-over)
            value += by_height - softness * math.log1p(power)
            width_part = power / (1 + power)
        else:
            power = math.exp(over)
            value += by_width - softness * math.log1p(power)
            width_part = 1 / (1 + power)

        for index in width_lines:
            slopes[cell.width.lines][index] += width_part / cell_width
        for index in height_lines:
            slopes[cell.height.lines][index] += (1 - width_part) / cell_height

    for name, lines in shares.items():
        value += _FIT_EVENNESS * sum(math.log(share) for share in lines)
        for index, share in enumerate(lines):
            slopes[name][index] += _FIT_EVENNESS / share

    return value, {name: _param_slopes(shares[name], slopes[name]) for name in shares}


def _param_slopes(shares, slopes) -> list[float]:
    # through _from_params: a share's free part goes up with its number,
    # and every other's down
    least = _FIT_LEAST / len(shares)
    free = [share - least for share in shares]
    total = sum(free) or 1.0
    mean = sum(f * s for f, s in zip(free, slopes)) / total
    return [f * (s - mean) for f, s in zip(free, slopes)]


def _shares(edges: Sequence[float]) -> tuple[float, ...]:
    return tuple(high - low for low, high in itertools.pairwise(edges))
