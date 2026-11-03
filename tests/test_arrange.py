"""Free Tiles' Arrange around the locked tiles (utils/layout/arrange)."""

import math

import pytest

from gridplayer.utils.layout.arrange import (
    ArrangeCache,
    _biggest_room,
    arrange_around,
    open_pieces,
)
from gridplayer.utils.layout.flow_layout import FlowLayout, FlowMode
from gridplayer.utils.layout.free_tiles import Rect

WIDTH, HEIGHT = 1600, 900
AREA = Rect(0, 0, WIDTH, HEIGHT)
SHAPES = [16 / 9, 9 / 16, 4 / 3, 16 / 9, 21 / 9, 1.0, 9 / 16, 16 / 9, 3 / 4]


def _videos(count):
    ids = [f"v{i}" for i in range(count)]
    return ids, dict(zip(ids, SHAPES * 5, strict=False))


def _rects(boxes) -> dict[str, Rect]:
    return {
        video_id: Rect(
            b.left * WIDTH, b.top * HEIGHT, b.right * WIDTH, b.bottom * HEIGHT
        )
        for video_id, b in boxes.items()
    }


def _cut(rect, shape) -> float:
    stretch = (rect.width / rect.height) / shape
    return 1 - min(stretch, 1 / stretch)


def test_the_room_round_a_wall_is_cut_down_first_or_along():
    wall = [Rect(500, 250, 1100, 650)]

    down = open_pieces(AREA, wall, is_down=True)
    along = open_pieces(AREA, wall, is_down=False)

    # read row by row: whole columns at the sides, above and below between
    assert down == [
        Rect(0, 0, 500, 900),
        Rect(500, 0, 1100, 250),
        Rect(1100, 0, 1600, 900),
        Rect(500, 650, 1100, 900),
    ]
    assert along == [
        Rect(0, 0, 1600, 250),
        Rect(0, 250, 500, 650),
        Rect(1100, 250, 1600, 650),
        Rect(0, 650, 1600, 900),
    ]


def test_room_too_small_for_a_tile_is_left_out():
    # 20 pixels left of the wall
    wall = [Rect(20, 0, 1600, 450)]

    assert open_pieces(AREA, wall, is_down=True) == [Rect(20, 450, 1600, 900)]
    # cut along first, the room under the wall is whole
    assert open_pieces(AREA, wall, is_down=False) == [Rect(0, 450, 1600, 900)]


def test_walls_a_fraction_of_a_pixel_into_each_other_are_cut_between():
    # as Free Tiles has it, they only touch
    walls = [Rect(0, 0, 800, 300), Rect(799.7, 0, 1600, 600)]

    assert open_pieces(AREA, walls, is_down=True) == [
        Rect(0, 300, 799.7, 900),
        Rect(799.7, 600, 1600, 900),
    ]


def test_walls_with_no_line_right_across_leave_the_room_between_them():
    pinwheel = [
        Rect(0, 0, 1000, 300),
        Rect(1000, 0, 1600, 600),
        Rect(600, 600, 1600, 900),
        Rect(0, 300, 600, 900),
    ]

    assert open_pieces(AREA, pinwheel, is_down=True) == [Rect(600, 300, 1000, 600)]


def test_a_wall_over_all_of_it_leaves_no_room():
    ids, shapes = _videos(3)
    assert arrange_around(WIDTH, HEIGHT, [AREA], ids, {}, shapes, 20) is None


@pytest.mark.parametrize("crop", [0, 20])
def test_with_no_walls_it_is_fit_shapes(crop):
    ids, shapes = _videos(7)

    boxes = arrange_around(WIDTH, HEIGHT, [], ids, {}, shapes, crop)

    flow = FlowLayout(mode=FlowMode.SHAPES, ids=ids, column_ids=ids, crop=0)
    flow.fit_to(WIDTH, HEIGHT, shapes)
    if crop == 0:
        assert boxes == dict(flow.boxes())
    assert set(boxes) == set(ids)


@pytest.mark.parametrize(
    "walls",
    [
        [Rect(500, 250, 1100, 650)],
        [Rect(0, 0, 700, 400)],
        [Rect(0, 0, 600, 340), Rect(1000, 560, 1600, 900)],
    ],
)
@pytest.mark.parametrize("crop", [0, 10, 20, 50])
@pytest.mark.parametrize("count", [1, 4, 9, 20])
def test_videos_go_round_the_walls_cut_no_more_than_the_limit(walls, crop, count):
    ids, shapes = _videos(count)

    rects = _rects(arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, crop))

    assert set(rects) == set(ids)
    placed = list(rects.values())
    for i, rect in enumerate(placed):
        assert rect.is_inside(Rect(-0.5, -0.5, WIDTH + 0.5, HEIGHT + 0.5))
        assert not any(rect.overlaps(wall) for wall in walls)
        assert not any(rect.overlaps(other) for other in placed[i + 1 :])
    for video_id, rect in rects.items():
        assert _cut(rect, shapes[video_id]) <= crop / 100 + 1e-6


def test_more_cut_allowed_fills_more_of_the_room():
    ids, shapes = _videos(7)
    walls = [Rect(0, 0, 700, 400)]

    def covered(crop):
        rects = _rects(arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, crop))
        return sum(r.width * r.height for r in rects.values())

    assert covered(0) < covered(20) <= covered(50)


def test_videos_are_shared_out_in_the_order_they_are_read():
    ids, shapes = _videos(8)
    # a wall down the middle: the first videos left of it
    walls = [Rect(700, 0, 900, 900)]

    rects = _rects(arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 20))

    sides = ["left" if rects[i].right <= 700.5 else "right" for i in ids]
    assert sides == sorted(sides)
    assert set(sides) == {"left", "right"}


@pytest.mark.parametrize("count", [3, 6, 9, 14, 20, 30])
def test_arranged_again_from_where_they_went_they_stay(count):
    ids, shapes = _videos(count)
    # in the middle: the pieces round it would be mixed up read row by row
    # across the whole area
    walls = [Rect(500, 250, 1100, 650)]

    boxes = arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 20)
    again = arrange_around(WIDTH, HEIGHT, walls, ids, _rects(boxes), shapes, 20)

    assert again == pytest.approx(boxes)


def _mean_area(rects) -> float:
    areas = [r.width * r.height for r in rects.values()]
    return math.exp(sum(math.log(a) for a in areas) / len(areas))


@pytest.mark.parametrize(
    "walls",
    [
        [],
        [Rect(500, 250, 1100, 650)],
        [Rect(0, 0, 600, 340), Rect(1000, 560, 1600, 900)],
    ],
)
def test_reordered_they_show_no_smaller_and_the_same_wherever_they_were(walls):
    ids, shapes = _videos(9)
    kept = _rects(arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 20))

    reordered = arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 20, True)
    again = arrange_around(WIDTH, HEIGHT, walls, ids, kept, shapes, 20, True)

    assert again == reordered
    assert _mean_area(_rects(reordered)) >= _mean_area(kept) * 0.99


def test_reordered_round_a_wall_tall_videos_go_where_tall_room_is():
    # tall room on the left, read first, and wide room at the bottom right
    walls = [Rect(400, 0, 1600, 600)]
    ids = ["wide1", "wide2", "tall1", "tall2"]
    shapes = {"wide1": 16 / 9, "tall1": 9 / 16, "wide2": 16 / 9, "tall2": 9 / 16}

    kept = _rects(arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 0))
    reordered = _rects(arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 0, True))

    assert _mean_area(reordered) > _mean_area(kept) * 1.1


def test_with_no_walls_a_small_area_still_has_them_all():
    ids, shapes = _videos(3)

    boxes = arrange_around(40, 30, [], ids, {}, shapes, 20)

    assert set(boxes) == set(ids)


def test_a_crop_limit_below_nought_cuts_none():
    ids, shapes = _videos(4)

    boxes = arrange_around(WIDTH, HEIGHT, [], ids, {}, shapes, -5)

    assert boxes == arrange_around(WIDTH, HEIGHT, [], ids, {}, shapes, 0)


def test_the_biggest_room_is_one_a_tile_fits_in():
    area = Rect(0, 0, 1600, 1000)
    # a strip 40 wide down the left, the biggest; under the walls, a room
    # 190 by 200
    walls = [Rect(40, 0, 1600, 800), Rect(190, 800, 1600, 1000)]

    assert _biggest_room(area, walls) == Rect(0, 800, 190, 1000)


def test_with_what_was_worked_out_kept_it_comes_to_the_same():
    ids, shapes = _videos(9)
    cache = ArrangeCache()

    def arranged(left, cache=None):
        # a wall moved about, as a tile held is
        walls = [Rect(left, 250, left + 600, 650)]
        return arrange_around(WIDTH, HEIGHT, walls, ids, {}, shapes, 20, cache=cache)

    for left in (300, 500):
        assert arranged(left, cache) == arranged(left)
    found = cache.find_splits.cache_info().misses

    # back where it was: no splits to find anew
    assert arranged(300, cache) == arranged(300)
    assert cache.find_splits.cache_info().misses == found
