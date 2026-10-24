from __future__ import annotations

import functools
import itertools
import math
from collections.abc import Callable, Sequence
from typing import NamedTuple

from gridplayer.utils.layout.boxes import Box

# splits nearly as tall as one kept are dropped, to keep their number down
# for many videos: the pictures come out at most a few percent smaller
SPLIT_HEIGHT_STEP = 0.01

# how much a tile stretched by cropping counts for what it adds: what is
# cut off its picture is lost, so not all of it. Counted whole, a layout
# that cuts as much as allowed won over one that fills the window as well
# cutting much less
STRETCH_WORTH = 0.5


class Split(NamedTuple):
    """Items, in order, split into lines that end flush.

    Each line is as high as its width over the sum of its items' weights
    (their shapes, for rows). For lines one unit wide, height is how high
    they all are, and log_heights the sum, over the items, of the log of
    the height of their line, each by its worth (see best_splits).
    """

    lengths: tuple[int, ...]
    height: float
    log_heights: float


def measure_split(
    weights: Sequence[float],
    lengths: Sequence[int],
    worth: Sequence[float] | None = None,
) -> Split:
    height = 0.0
    log_heights = 0.0
    start = 0
    for length in lengths:
        line_weight = sum(weights[start : start + length])
        line_worth = length if worth is None else sum(worth[start : start + length])
        height += 1 / line_weight
        log_heights -= line_worth * math.log(line_weight)
        start += length
    return Split(tuple(lengths), height, log_heights)


@functools.lru_cache(maxsize=16)
def best_splits(
    weights: tuple[float, ...], worth: tuple[float, ...] | None = None
) -> tuple[Split, ...]:
    """The splits of these items into lines that one of them could be best
    for, whatever the area's shape.

    A split scores higher the higher its lines are (log_heights) and lower
    the higher they are all together, once they have to be made smaller to
    fit (height). So the best split for any area is among those no other
    split beats on both, which are found a line at a time.

    An item's worth is how much its picture counts, one by default: the
    more, the more a higher line for it scores.
    """

    prefix = [0.0, *itertools.accumulate(weights)]
    worth_prefix = [0.0, *itertools.accumulate(worth or (1.0,) * len(weights))]

    # for the first so many items, the splits no other beats, by height:
    # each its height, its log_heights less than nought, where its last line
    # starts and which of the splits of the items before that it goes on
    # from, so that it sorts by height, the highest lines first
    splits: list[list[tuple[float, float, int, int]]] = [[(0.0, 0.0, 0, 0)]]
    for end in range(1, len(weights) + 1):
        found = []
        for start in range(end):
            line_weight = prefix[end] - prefix[start]
            height = 1 / line_weight
            line_worth = worth_prefix[end] - worth_prefix[start]
            less_log_heights = line_worth * math.log(line_weight)
            found.extend(
                (split[0] + height, split[1] + less_log_heights, start, index)
                for index, split in enumerate(splits[start])
            )
        found.sort()

        kept: list[tuple[float, float, int, int]] = []
        step_height = 0.0
        for split in found:
            if kept and split[1] >= kept[-1][1]:
                continue
            if kept and split[0] <= step_height:
                kept[-1] = split
                continue
            kept.append(split)
            step_height = split[0] * (1 + SPLIT_HEIGHT_STEP)
        splits.append(kept)

    def lengths(end: int, index: int) -> tuple[int, ...]:
        found = []
        while end:
            *_, start, index = splits[end][index]
            found.append(end - start)
            end = start
        return tuple(reversed(found))

    return tuple(
        Split(lengths(len(weights), index), height, -less_log_heights)
        for index, (height, less_log_heights, *_) in enumerate(splits[-1])
    )


def split_score(
    split: Split,
    weights: Sequence[float],
    width: int,
    height: int,
    crop: float = 0.0,
    worth: Sequence[float] | None = None,
) -> float:
    """How well the split shows the items, in an area of this size (see
    split_scorer)."""

    return split_scorer(weights, width, height, crop, worth)(split)


def split_scorer(
    weights: Sequence[float],
    width: int,
    height: int,
    crop: float = 0.0,
    worth: Sequence[float] | None = None,
) -> Callable[[Split], float]:
    """How well a split of these items shows them, in an area of this size,
    by picture_score: the sum of the logs of their tiles' areas, each by its
    worth (see best_splits).

    With crop, the tiles are stretched to take up to that share less of
    their pictures (see justified_boxes), and score by what they show, the
    stretch at STRETCH_WORTH.
    """

    if worth is None:
        worth = (1.0,) * len(weights)
    count = sum(worth)
    log_weights = sum(
        item * math.log(weight) for item, weight in zip(worth, weights, strict=True)
    )
    log_width, log_height = math.log(width), math.log(height)
    most_stretch = -math.log(1 - crop)

    def score(split: Split) -> float:
        log_lines_height = math.log(split.height)
        shown_width = min(log_width, log_height - log_lines_height)
        shown = log_weights + 2 * split.log_heights + 2 * count * shown_width

        # how many times too narrow, or too short, the lines are for the area
        log_leftover = abs(log_height - log_lines_height - log_width)
        return shown + STRETCH_WORTH * count * min(log_leftover, most_stretch)

    return score


def justified_boxes(
    shapes: Sequence[float],
    lines: Sequence[int],
    is_columns: bool,
    width: int,
    height: int,
    crop: float = 0.0,
) -> list[Box]:
    """Tiles of these shapes (width for height), in lines that end flush:
    rows of tiles of one height each, or columns of one width each.

    The lines take the whole width (the whole height, for columns), unless
    that makes them too tall for the area: then they are made smaller to
    fit. With crop, all the tiles are then stretched the same way into the
    space left, as far as a picture filling one would lose that share of
    itself. The space still left goes evenly around them.
    """

    if is_columns:
        boxes = _justified_rows(
            [1 / shape for shape in shapes], lines, height, width, crop
        )
        return [Box(box.top, box.left, box.bottom, box.right) for box in boxes]

    return _justified_rows(shapes, lines, width, height, crop)


def _justified_rows(
    shapes: Sequence[float],
    lines: Sequence[int],
    width: int,
    height: int,
    crop: float,
) -> list[Box]:
    lines_height = measure_split(shapes, lines).height

    lines_width = min(width, height / lines_height)

    # one of the two is not stretched: the lines fill the area that way
    most_stretch = 1 / (1 - crop)
    shown_width = min(width, lines_width * most_stretch)
    shown_height = min(height, lines_width * lines_height * most_stretch)
    stretch_width = shown_width / lines_width
    stretch_height = shown_height / (lines_width * lines_height)

    left = (width - shown_width) / 2
    top = (height - shown_height) / 2

    boxes = []
    start = 0
    for length in lines:
        row = shapes[start : start + length]
        start += length

        # the row's height for each unit of its tiles' shapes, unstretched
        unit = lines_width / sum(row)
        row_height = unit * stretch_height
        x = left
        for place, shape in enumerate(row, 1):
            # the rows end at the very same number
            if place == length:
                right = left + shown_width
            else:
                right = x + unit * shape * stretch_width
            boxes.append(
                Box(x / width, top / height, right / width, (top + row_height) / height)
            )
            x = right
        top += row_height
    return boxes
