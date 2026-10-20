from __future__ import annotations

import functools
import math
from collections.abc import Sequence
from typing import NamedTuple

from gridplayer.utils.layout.boxes import Box

# splits nearly as tall as one kept are dropped, to keep their number down
# for many videos: the pictures come out at most a few percent smaller
SPLIT_HEIGHT_STEP = 0.01


class Split(NamedTuple):
    """Items, in order, split into lines that end flush.

    Each line is as high as its width over the sum of its items' weights
    (their shapes, for rows). For lines one unit wide, height is how high
    they all are, and log_heights the sum, over the items, of the log of
    the height of their line.
    """

    lengths: tuple[int, ...]
    height: float
    log_heights: float


def measure_split(weights: Sequence[float], lengths: Sequence[int]) -> Split:
    height = 0.0
    log_heights = 0.0
    start = 0
    for length in lengths:
        line_weight = sum(weights[start : start + length])
        height += 1 / line_weight
        log_heights -= length * math.log(line_weight)
        start += length
    return Split(tuple(lengths), height, log_heights)


@functools.lru_cache(maxsize=8)
def best_splits(weights: tuple[float, ...]) -> tuple[Split, ...]:
    """The splits of these items into lines that one of them could be best
    for, whatever the area's shape.

    A split scores higher the higher its lines are (log_heights) and lower
    the higher they are all together, once they have to be made smaller to
    fit (height). So the best split for any area is among those no other
    split beats on both, which are found a line at a time.
    """

    prefix = [0.0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)

    # for the first so many items, the splits no other beats, by height
    splits: list[list[Split]] = [[Split((), 0.0, 0.0)]]
    for end in range(1, len(weights) + 1):
        found = []
        for start in range(end):
            line_weight = prefix[end] - prefix[start]
            height = 1 / line_weight
            log_heights = -(end - start) * math.log(line_weight)
            found.extend(
                Split(
                    (*split.lengths, end - start),
                    split.height + height,
                    split.log_heights + log_heights,
                )
                for split in splits[start]
            )
        found.sort(key=lambda split: (split.height, -split.log_heights))

        kept: list[Split] = []
        step_height = 0.0
        for split in found:
            if kept and split.log_heights <= kept[-1].log_heights:
                continue
            if kept and split.height <= step_height:
                kept[-1] = split
                continue
            kept.append(split)
            step_height = split.height * (1 + SPLIT_HEIGHT_STEP)
        splits.append(kept)

    return tuple(splits[-1])


def split_score(split: Split, weights: Sequence[float], width: int, height: int):
    """How well the split shows the items, in an area of this size, by
    picture_score: the sum of the logs of their tiles' areas."""

    count = sum(split.lengths)
    log_width = min(math.log(width), math.log(height) - math.log(split.height))
    log_weights = sum(math.log(weight) for weight in weights)
    return log_weights + 2 * split.log_heights + 2 * count * log_width


def justified_boxes(
    shapes: Sequence[float],
    lines: Sequence[int],
    is_columns: bool,
    width: int,
    height: int,
) -> list[Box]:
    """Tiles of these shapes (width for height), in lines that end flush:
    rows of tiles of one height each, or columns of one width each.

    The lines take the whole width (the whole height, for columns), unless
    that makes them too tall for the area: then they are made smaller to
    fit. The space left over goes evenly around them.
    """

    if is_columns:
        boxes = _justified_rows([1 / shape for shape in shapes], lines, height, width)
        return [Box(box.top, box.left, box.bottom, box.right) for box in boxes]

    return _justified_rows(shapes, lines, width, height)


def _justified_rows(
    shapes: Sequence[float], lines: Sequence[int], width: int, height: int
) -> list[Box]:
    lines_height = measure_split(shapes, lines).height

    lines_width = min(width, height / lines_height)
    left = (width - lines_width) / 2
    top = (height - lines_width * lines_height) / 2

    boxes = []
    start = 0
    for length in lines:
        row = shapes[start : start + length]
        start += length

        row_height = lines_width / sum(row)
        x = left
        for place, shape in enumerate(row, 1):
            # the rows end at the very same number
            right = left + lines_width if place == length else x + row_height * shape
            boxes.append(
                Box(x / width, top / height, right / width, (top + row_height) / height)
            )
            x = right
        top += row_height
    return boxes
