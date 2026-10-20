import itertools
import math
import random

import pytest

from gridplayer.utils.layout.boxes import box_rect, picture_score
from gridplayer.utils.layout.justified import (
    best_splits,
    justified_boxes,
    measure_split,
    split_score,
)

WIDE, TALL, SQUARE = 16 / 9, 9 / 16, 1.0


def _all_splits(count):
    for cuts in itertools.product((False, True), repeat=count - 1):
        lengths = [1]
        for is_cut in cuts:
            if is_cut:
                lengths.append(1)
            else:
                lengths[-1] += 1
        yield tuple(lengths)


def _score(shapes, lengths, is_columns, width, height):
    boxes = justified_boxes(shapes, lengths, is_columns, width, height)
    return picture_score(zip(boxes, shapes), width, height)


def _shown_score(shapes, lengths, is_columns, width, height, crop):
    # by the tiles' areas: what shows of pictures that fill them
    boxes = justified_boxes(shapes, lengths, is_columns, width, height, crop)
    return sum(
        math.log((box.right - box.left) * width * (box.bottom - box.top) * height)
        for box in boxes
    )


def _cut(box, shape, width, height):
    # the share of a picture of this shape cut off to fill the box
    box_shape = (box.right - box.left) * width / ((box.bottom - box.top) * height)
    return 1 - min(box_shape / shape, shape / box_shape)


def test_rows_end_flush_and_keep_the_shapes():
    shapes = [WIDE, TALL, SQUARE, WIDE]
    boxes = justified_boxes(shapes, (2, 2), False, 1920, 1080)

    rects = [box_rect(box, 1920, 1080) for box in boxes]
    # each tile as wide as its picture for its height
    for (_x, _y, width, height), shape in zip(rects, shapes):
        assert width / height == pytest.approx(shape, abs=0.01)

    # a row's tiles meet, at one height, and the rows meet
    assert boxes[0].right == boxes[1].left
    assert (boxes[0].top, boxes[0].bottom) == (boxes[1].top, boxes[1].bottom)
    assert boxes[1].bottom == boxes[2].top
    assert boxes[1].right == boxes[3].right


def test_the_space_left_over_goes_around():
    # three tall pictures in a wide area: too tall for the whole width
    boxes = justified_boxes([TALL] * 3, (3,), False, 1920, 1080)
    assert (boxes[0].top, boxes[0].bottom) == (0, 1)
    assert boxes[0].left == pytest.approx(1 - boxes[2].right)

    # one wide picture in a tall area: too wide for the whole height
    (box,) = justified_boxes([WIDE], (1,), False, 1080, 1920)
    assert (box.left, box.right) == (0, 1)
    assert box.top == pytest.approx(1 - box.bottom)


def test_columns_are_rows_turned():
    shapes = [WIDE, TALL, SQUARE]
    boxes = justified_boxes(shapes, (1, 2), True, 1080, 1920)

    assert boxes[1].left == boxes[2].left
    assert boxes[1].bottom == boxes[2].top
    assert boxes[0].right == boxes[1].left
    for box, shape in zip(boxes, shapes):
        width = (box.right - box.left) * 1080
        height = (box.bottom - box.top) * 1920
        assert width / height == pytest.approx(shape)


@pytest.mark.parametrize("is_columns", [False, True])
@pytest.mark.parametrize("area", [(1920, 1080), (1080, 1920)])
def test_split_score_is_the_picture_score(is_columns, area):
    shapes = [WIDE, TALL, SQUARE, WIDE, TALL]
    weights = [1 / shape for shape in shapes] if is_columns else shapes
    width, height = area
    for lengths in _all_splits(len(shapes)):
        split = measure_split(weights, lengths)
        along = (height, width) if is_columns else (width, height)
        assert split_score(split, weights, *along) == pytest.approx(
            _score(shapes, lengths, is_columns, width, height)
        )


@pytest.mark.parametrize("crop", [0.0, 0.1])
def test_the_best_split_is_among_those_found(crop):
    shapes_to_pick = [WIDE, WIDE, TALL, SQUARE, 4 / 3, 21 / 9]
    areas = [(1920, 1080), (1080, 1920), (2560, 1080), (1600, 1200)]

    rng = random.Random(1)
    for _ in range(60):
        shapes = tuple(rng.choice(shapes_to_pick) for _ in range(rng.randint(2, 9)))
        width, height = rng.choice(areas)

        best = max(
            _shown_score(shapes, lengths, is_columns, width, height, crop)
            for lengths in _all_splits(len(shapes))
            for is_columns in (False, True)
        )
        found = max(
            _shown_score(shapes, split.lengths, is_columns, width, height, crop)
            for is_columns, weights in (
                (False, shapes),
                (True, tuple(1 / shape for shape in shapes)),
            )
            for split in best_splits(weights)
        )
        # splits found nearly as tall as others are dropped
        assert math.exp((best - found) / len(shapes)) < 1.02


def test_cropping_stretches_the_tiles_into_the_space_left():
    # three tall pictures in a wide area leave about 5% of it at the sides
    shapes = [TALL] * 3

    boxes = justified_boxes(shapes, (3,), False, 1920, 1080, 0.1)
    assert (boxes[0].left, boxes[2].right) == (0, 1)
    assert [(box.top, box.bottom) for box in boxes] == [(0, 1)] * 3
    for box, shape in zip(boxes, shapes):
        assert _cut(box, shape, 1920, 1080) < 0.1

    # cut no more than allowed, the rest of the space left at the sides
    boxes = justified_boxes(shapes, (3,), False, 1920, 1080, 0.05)
    assert boxes[0].left == pytest.approx(1 - boxes[2].right)
    assert 0 < boxes[0].left < 0.001
    for box, shape in zip(boxes, shapes):
        assert _cut(box, shape, 1920, 1080) == pytest.approx(0.05)

    # one wide picture in a tall area gets taller
    (box,) = justified_boxes([WIDE], (1,), False, 1080, 1920, 0.2)
    assert (box.left, box.right) == (0, 1)
    assert box.top == pytest.approx(1 - box.bottom)
    assert (box.bottom - box.top) * 1920 == pytest.approx(1080 / WIDE * 1.25)


def test_cropped_columns_are_rows_turned():
    shapes = [WIDE] * 3

    boxes = justified_boxes(shapes, (3,), True, 1080, 1920, 0.1)
    assert (boxes[0].top, boxes[2].bottom) == (0, 1)
    assert [(box.left, box.right) for box in boxes] == [(0, 1)] * 3
    assert boxes[0].bottom == boxes[1].top


@pytest.mark.parametrize("crop", [0.05, 0.2])
@pytest.mark.parametrize("is_columns", [False, True])
@pytest.mark.parametrize("area", [(1920, 1080), (1080, 1920)])
def test_split_score_counts_what_cropped_tiles_show(crop, is_columns, area):
    shapes = [WIDE, TALL, SQUARE, WIDE, TALL]
    weights = [1 / shape for shape in shapes] if is_columns else shapes
    width, height = area
    for lengths in _all_splits(len(shapes)):
        split = measure_split(weights, lengths)
        along = (height, width) if is_columns else (width, height)
        assert split_score(split, weights, *along, crop) == pytest.approx(
            _shown_score(shapes, lengths, is_columns, width, height, crop)
        )
