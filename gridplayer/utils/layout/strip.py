"""Single Mode with a strip: the video shown big, and the others small in a
strip beside it, on the side picked; on Auto, along the right of a wide
window or the bottom of a tall one (see strip_layout).

The strip's videos are in lines along it, each tile of the videos' shape,
as many lines as it takes for them all to fit its length, the strip
getting wider for more rather than the videos smaller. The line between
the big video and the strip is moved by hand as the grid's are (see
StripLines), and where it is is kept as the strip's share of the window.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

from gridplayer.params.static import StripSide
from gridplayer.utils.layout.boxes import Box, Weights
from gridplayer.utils.layout.flow_layout import DEFAULT_SHAPE
from gridplayer.utils.layout.lines import Line, SnapKind, Target, merged_targets

# how many videos go along a line of the strip as it is at first: so big
# they are
STRIP_PER_LINE = 4

# the most and the least of the window the strip takes across it: the big
# video keeps the most of it
STRIP_MOST = 0.4
STRIP_LEAST = 0.05


class Strip(NamedTuple):
    """Where the big video goes, and the strip's videos in their order;
    whether the strip is beside the big one, else under or over it, and
    whether before it (on its left, or over it); and its share of the
    window, across."""

    main: Box
    boxes: list[Box]
    is_side: bool
    share: float
    is_before: bool


class StripVideos(NamedTuple):
    """In Single Mode with the strip, the video shown big, the videos in the
    strip in its order, and its side. In the Fixed Strip, the big one is in
    the strip too, its place held there."""

    main: object
    strip: list
    side: StripSide


def strip_place(side: StripSide, width: int, height: int) -> tuple[bool, bool]:
    """Whether the strip is beside the big video (else under or over it),
    and whether before it (on its left, or over it), on this side."""

    if side == StripSide.AUTO:
        return width >= height, False
    return side in {StripSide.RIGHT, StripSide.LEFT}, side in {
        StripSide.LEFT,
        StripSide.TOP,
    }


def strip_share(weights: Weights) -> float | None:
    """The strip's share of the window that the lines' weights keep (see
    StripLines.moved), None where it is not moved by hand."""

    if len(weights.cols) != 2 or min(weights.cols) <= 0:
        return None
    return weights.cols[1] / sum(weights.cols)


def strip_weights(share: float | None) -> Weights:
    """The weights that keep the strip's share of the window (see
    strip_share)."""

    if share is None:
        return Weights()
    return Weights(cols=(1 - share, share))


def shape_of_strip(shapes: Sequence[float]) -> float:
    """The shape the strip's tiles have, width for height: in between the
    videos', each counting as much (their geometric mean)."""

    if not shapes:
        return DEFAULT_SHAPE
    return math.exp(sum(math.log(shape) for shape in shapes) / len(shapes))


def strip_layout(
    count: int,
    width: int,
    height: int,
    shape: float,
    share: float | None = None,
    side: StripSide = StripSide.AUTO,
) -> Strip:
    """The big video and a strip of count others, in an area of this size,
    the strip on this side; the strip's tiles of this shape. The strip
    takes the share of the window given, else as much as its videos take
    at STRIP_PER_LINE to a line, from STRIP_LEAST to STRIP_MOST of it."""

    # an area with no size yet, laid out as one of a pixel
    width, height = max(width, 1), max(height, 1)
    is_side, is_before = strip_place(side, width, height)
    along, across = (height, width) if is_side else (width, height)
    thickness_for_length = _thickness_for_length(shape, is_side)

    share = _share(share, count, along, across, thickness_for_length)
    thickness = share * across

    lines = _line_count(count, thickness, along, thickness_for_length)
    per_line = math.ceil(count / lines) if count else 0
    tile_across = thickness / lines
    tile_along = min(tile_across / thickness_for_length, along / max(per_line, 1))

    boxes = []
    for index in range(count):
        line, place = divmod(index, per_line)
        in_line = min(per_line, count - line * per_line)
        # each line in the middle of the strip's length
        start = (along - in_line * tile_along) / 2 + place * tile_along
        low = across - thickness + line * tile_across
        boxes.append(
            _box(
                is_side,
                is_before,
                start / along,
                (start + tile_along) / along,
                low / across,
                (low + tile_across) / across,
            )
        )

    main = _box(is_side, is_before, 0.0, 1.0, 0.0, 1 - share)
    return Strip(main, boxes, is_side, share, is_before)


def _thickness_for_length(shape: float, is_side: bool) -> float:
    # a tile's size across the strip, for its length along it
    return shape if is_side else 1 / shape


def _share(share, count, along, across, thickness_for_length) -> float:
    # the share given, else as it is at first, from STRIP_LEAST to STRIP_MOST
    if share is None:
        share = default_share(count, along, across, thickness_for_length)
    return min(max(share, STRIP_LEAST), STRIP_MOST)


def default_share(
    count: int, along: float, across: float, thickness_for_length: float
) -> float:
    """The strip's share of the window, across, as it is at first: its
    videos STRIP_PER_LINE to a line along it, in as many lines as that
    takes, at most STRIP_MOST of it."""

    lines = max(math.ceil(count / STRIP_PER_LINE), 1)
    thickness = lines * along / STRIP_PER_LINE * thickness_for_length
    return min(max(thickness / across, STRIP_LEAST), STRIP_MOST)


def _line_count(count, thickness, along, thickness_for_length) -> int:
    # the fewest lines its videos fit along the strip in, at their shape
    for lines in range(1, max(count, 1) + 1):
        length = math.ceil(count / lines) * thickness / lines / thickness_for_length
        if length <= along * (1 + 1e-9):
            return lines
    return max(count, 1)


def _box(is_side, is_before, along_low, along_high, across_low, across_high):
    # laid out with the strip after the big one, turned round for one before
    if is_before:
        across_low, across_high = 1 - across_high, 1 - across_low
    if is_side:
        return Box(across_low, along_low, across_high, along_high)
    return Box(along_low, across_low, along_high, across_high)


class StripLines:
    """The line between the big video and the strip, to move by hand, as
    GridLines has the grid's (see GridLinesManager): it snaps where the
    big video just fits beside it, and where the strip's videos just fill
    its length in so many lines. Its weights keep the strip's share (see
    strip_weights)."""

    def __init__(
        self,
        count: int,
        width: int,
        height: int,
        shape: float,
        main_shape: float | None,
        share: float | None = None,
        side: StripSide = StripSide.AUTO,
    ):
        self.width = width
        self.height = height
        self._count = count
        self._shape = shape
        self._main_shape = main_shape
        self._side = side
        self._is_moved = share is not None

        self._strip = strip_layout(count, width, height, shape, share, side)
        is_side = self._strip.is_side
        self._line = Line(is_side, 0)
        self._along, self._across = (height, width) if is_side else (width, height)
        self._thickness_for_length = _thickness_for_length(shape, is_side)

    def weights(self) -> Weights:
        """The strip's share, should it be moved by hand; none for one as
        it is at first, which is then put back so."""

        return strip_weights(self._strip.share if self._is_moved else None)

    def is_even(self) -> bool:
        """Whether the strip is as it is at first."""

        return not self._is_moved

    def evened(self, line: Line) -> Weights:
        # as it is at first
        return Weights()

    def position(self, line: Line, weights: Weights | None = None) -> int:
        """Where the line is, in pixels from the area's left (top): the big
        video's size across."""

        share = self._strip.share
        if weights is not None:
            share = _share(
                strip_share(weights),
                self._count,
                self._along,
                self._across,
                self._thickness_for_length,
            )
        return round(self._turned((1 - share) * self._across))

    def _turned(self, position: float) -> float:
        # where the line is with the strip after the big one, for this side
        return self._across - position if self._strip.is_before else position

    def span(self, line: Line) -> tuple[int, int]:
        return 0, self._along

    def line_at(self, x: float, y: float, reach: float) -> Line | None:
        along_line = x if self._line.is_column else y
        if abs(along_line - self.position(self._line)) > reach:
            return None
        return self._line

    def moved(self, line: Line, position: float) -> Weights:
        share = 1 - self._turned(position) / self._across
        return strip_weights(min(max(share, STRIP_LEAST), STRIP_MOST))

    def snaps(self, line: Line) -> list[Target]:
        """Where the big video just fits beside the strip, and where the
        strip's videos just fill its length, in one line or more."""

        low = (1 - STRIP_MOST) * self._across
        high = (1 - STRIP_LEAST) * self._across
        targets = []

        if self._main_shape:
            main_for_along = (
                self._main_shape if self._line.is_column else 1 / self._main_shape
            )
            targets.append(Target(self._along * main_for_along, SnapKind.FITS, -1))

        for lines in range(1, max(self._count, 1) + 1):
            per_line = math.ceil(self._count / lines)
            thickness = self._along * self._thickness_for_length * lines / per_line
            targets.append(Target(self._across - thickness, SnapKind.FITS, 1))

        return sorted(
            self._turned_target(t)
            for t in merged_targets(targets)
            if low <= t.position <= high
        )

    def _turned_target(self, target: Target) -> Target:
        if not self._strip.is_before:
            return target
        return Target(self._across - target.position, target.kind, -target.side)
