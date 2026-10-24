import math

import pytest

from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import Box, FlowLayout, FlowMode


def _flow(count, size=0, mode=FlowMode.ROWS):
    return FlowLayout(mode=mode, size=size, ids=[str(i) for i in range(count)])


def test_displayed_size_auto_square():
    assert _flow(1).displayed_size() == (1, 1)
    assert _flow(4).displayed_size() == (2, 2)
    assert _flow(5).displayed_size() == (3, 2)
    assert _flow(5, mode=FlowMode.COLS).displayed_size() == (2, 3)


def test_displayed_size_fixed_axis():
    assert _flow(5, size=3).displayed_size() == (3, 2)
    assert _flow(5, size=3, mode=FlowMode.COLS).displayed_size() == (2, 3)


def test_id_at_rows_first():
    layout = FlowLayout(mode=FlowMode.ROWS, size=3, ids=["A", "B", "C", "D", "E"])
    assert layout.displayed_size() == (3, 2)
    assert layout.id_at(0, 0) == "A"
    assert layout.id_at(0, 2) == "C"
    assert layout.id_at(1, 0) == "D"
    assert layout.id_at(1, 1) == "E"
    assert layout.id_at(1, 2) is None


def test_id_at_cols_first():
    layout = FlowLayout(mode=FlowMode.COLS, size=3, ids=["A", "B", "C", "D", "E"])
    assert layout.displayed_size() == (2, 3)
    assert layout.id_at(0, 0) == "A"
    assert layout.id_at(2, 0) == "C"
    assert layout.id_at(0, 1) == "D"
    assert layout.id_at(1, 1) == "E"


def test_position_of_roundtrip():
    rows = FlowLayout(mode=FlowMode.ROWS, size=3, ids=["A", "B", "C", "D", "E"])
    assert rows.position_of("C") == (0, 2)
    assert rows.position_of("D") == (1, 0)
    assert rows.id_at(*rows.position_of("E")) == "E"

    cols = FlowLayout(mode=FlowMode.COLS, size=3, ids=["A", "B", "C", "D", "E"])
    assert cols.position_of("C") == (2, 0)
    assert cols.position_of("D") == (0, 1)
    assert cols.id_at(*cols.position_of("E")) == "E"


def test_drop_insert_before_and_after():
    layout = FlowLayout(ids=["A", "B", "C"])
    layout.drop(["N"], 0, 0, DropZone.BEFORE, dst_id="B")
    assert layout.order() == ["A", "N", "B", "C"]

    layout = FlowLayout(ids=["A", "B", "C"])
    layout.drop(["N"], 0, 0, DropZone.AFTER, dst_id="B")
    assert layout.order() == ["A", "B", "N", "C"]


def test_drop_internal_swap_and_move():
    layout = FlowLayout(ids=["A", "B", "C", "D"])
    layout.drop([], 0, 0, DropZone.CENTER, src_id="A", dst_id="C")
    assert layout.order() == ["C", "B", "A", "D"]

    layout = FlowLayout(ids=["A", "B", "C", "D"])
    layout.drop([], 0, 0, DropZone.BEFORE, src_id="D", dst_id="A")
    assert layout.order() == ["D", "A", "B", "C"]


def test_drop_internal_replace():
    layout = FlowLayout(ids=["A", "B", "C", "D"])
    layout.drop([], 0, 0, DropZone.CENTER, is_replace=True, src_id="D", dst_id="B")
    assert layout.order() == ["A", "D", "C"]


def test_add_remove():
    layout = FlowLayout()
    assert layout.add(["A", "B"]) == []
    layout.remove("A")
    assert layout.order() == ["B"]
    assert layout.free_capacity() is None


def test_boxes_rows_first():
    layout = FlowLayout(mode=FlowMode.ROWS, ids=["A", "B", "C", "D", "E"])

    assert layout.boxes() == [
        ("A", Box(0, 0, 1 / 3, 1 / 2)),
        ("B", Box(1 / 3, 0, 2 / 3, 1 / 2)),
        ("C", Box(2 / 3, 0, 1, 1 / 2)),
        ("D", Box(0, 1 / 2, 1 / 3, 1)),
        ("E", Box(1 / 3, 1 / 2, 2 / 3, 1)),
    ]


def test_boxes_fit_cells_share_the_last_row():
    layout = FlowLayout(mode=FlowMode.ROWS, is_fit=True, ids=["A", "B", "C", "D", "E"])

    assert layout.boxes()[3:] == [
        ("D", Box(0, 1 / 2, 1 / 2, 1)),
        ("E", Box(1 / 2, 1 / 2, 1, 1)),
    ]


def test_boxes_fit_cells_share_the_last_column():
    layout = FlowLayout(mode=FlowMode.COLS, is_fit=True, ids=["A", "B", "C", "D", "E"])

    assert layout.boxes() == [
        ("A", Box(0, 0, 1 / 2, 1 / 3)),
        ("B", Box(0, 1 / 3, 1 / 2, 2 / 3)),
        ("C", Box(0, 2 / 3, 1 / 2, 1)),
        ("D", Box(1 / 2, 0, 1, 1 / 2)),
        ("E", Box(1 / 2, 1 / 2, 1, 1)),
    ]


def test_boxes_one_video_fills():
    assert FlowLayout(ids=["A"], is_fit=True).boxes() == [("A", Box(0, 0, 1, 1))]


WIDE, TALL, SQUARE = 16 / 9, 9 / 16, 1.0


def _fitted(shapes, width, height, mode=FlowMode.ROWS, is_fit=True):
    layout = FlowLayout(
        is_match_shapes=True,
        mode=mode,
        is_fit=is_fit,
        ids=[str(i) for i in range(len(shapes))],
    )
    layout.fit_to(width, height, {str(i): s for i, s in enumerate(shapes)})
    return layout.displayed_size()


@pytest.mark.parametrize("is_fit", [True, False])
@pytest.mark.parametrize("count", range(1, 26))
def test_auto_keeps_the_square_grid_for_wide_videos_in_a_wide_window(count, is_fit):
    layout = _flow(count)
    assert _fitted([WIDE] * count, 1920, 1080, is_fit=is_fit) == layout.displayed_size()


@pytest.mark.parametrize("mode", [FlowMode.ROWS, FlowMode.COLS])
def test_auto_puts_tall_videos_side_by_side(mode):
    assert _fitted([TALL] * 3, 1920, 1080, mode) == (3, 1)


@pytest.mark.parametrize("mode", [FlowMode.ROWS, FlowMode.COLS])
def test_auto_stacks_wide_videos_in_a_tall_window(mode):
    assert _fitted([WIDE] * 3, 1080, 1920, mode) == (1, 3)


def test_auto_takes_a_video_of_unknown_shape_as_wide():
    layout = FlowLayout(is_match_shapes=True, ids=["A", "B", "C"], is_fit=True)
    layout.fit_to(1920, 1080, {"A": None})
    assert layout.displayed_size() == (2, 2)

    layout.fit_to(1920, 1080, {"A": TALL, "B": TALL, "C": TALL})
    assert layout.displayed_size() == (3, 1)


def test_auto_holds_until_another_size_is_clearly_better():
    """Two wide videos show as big side by side as stacked in a 1920 pixel
    wide window: narrower, stacked is better, and wider, side by side, but
    it changes only once the other is 8% better."""

    layout = FlowLayout(is_match_shapes=True, ids=["A", "B"])
    shapes = {"A": WIDE, "B": WIDE}

    sizes = []
    for width in (1920, 1880, 1800, 1900, 1990, 2000):
        layout.fit_to(width, 1080, shapes)
        sizes.append(layout.displayed_size())

    assert sizes == [(2, 1), (2, 1), (1, 2), (1, 2), (1, 2), (2, 1)]


def test_auto_starts_from_the_square_grid_for_a_new_count():
    layout = FlowLayout(is_match_shapes=True, ids=["A", "B"])
    layout.fit_to(1800, 1080, {})
    assert layout.displayed_size() == (1, 2)

    layout.add(["C"])
    assert layout.displayed_size() == (2, 2)


def test_size_set_by_hand_holds():
    layout = FlowLayout(is_match_shapes=True, size=2, ids=["A", "B", "C"])
    layout.fit_to(1920, 1080, {"A": TALL, "B": TALL, "C": TALL})
    assert layout.displayed_size() == (2, 2)


def test_auto_keeps_the_square_grid_unless_matching_shapes():
    layout = FlowLayout(ids=["A", "B", "C"])
    layout.fit_to(1920, 1080, {"A": TALL, "B": TALL, "C": TALL})
    assert layout.displayed_size() == (2, 2)

    layout.is_match_shapes = True
    layout.fit_to(1920, 1080, {"A": TALL, "B": TALL, "C": TALL})
    assert layout.displayed_size() == (3, 1)

    layout.is_match_shapes = False
    assert layout.displayed_size() == (2, 2)


def _shapes_layout(shapes, width, height):
    ids = [str(i) for i in range(len(shapes))]
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=ids)
    layout.fit_to(width, height, dict(zip(ids, shapes)))
    return layout


def test_fit_shapes_puts_tall_videos_side_by_side():
    layout = _shapes_layout([TALL] * 3, 1920, 1080)
    assert layout.displayed_size() == (3, 1)

    # each as big as the height allows, the space left over at the sides
    boxes = [box for _id, box in layout.boxes()]
    assert [(box.top, box.bottom) for box in boxes] == [(0, 1)] * 3
    assert boxes[0].left == pytest.approx(1 - boxes[2].right)


def test_fit_shapes_keeps_the_order():
    shapes = [WIDE, TALL, WIDE, SQUARE, TALL, WIDE]
    layout = _shapes_layout(shapes, 1920, 1080)

    assert [video_id for video_id, _box in layout.boxes()] == list("012345")
    assert layout.order() == list("012345")


def test_fit_shapes_lays_out_in_columns_when_they_show_more():
    # wide videos in a tall window: in rows, one above the other
    layout = _shapes_layout([WIDE] * 3, 1080, 1920)
    assert layout.is_columns() is False
    assert layout.displayed_size() == (1, 3)

    # mixed videos in a wide window: some fit better in columns
    layout = _shapes_layout(
        [TALL, WIDE, TALL, WIDE, WIDE, TALL, WIDE, TALL], 1920, 1080
    )
    assert layout.is_columns() is True
    cols, rows = layout.displayed_size()
    assert layout.id_at(0, 0) == "0"
    assert layout.id_at(1, 0) == "1"
    assert layout.position_of("1") == (1, 0)
    for video_id in layout.order():
        assert layout.id_at(*layout.position_of(video_id)) == video_id
    assert layout.id_at(rows, 0) is None
    assert layout.id_at(0, cols) is None


def test_fit_shapes_holds_until_other_lines_are_clearly_better():
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=["A", "B"])
    shapes = {"A": WIDE, "B": WIDE}

    lines = []
    for width in (1920, 1880, 1800, 1900, 1990, 2000):
        layout.fit_to(width, 1080, shapes)
        lines.append(layout.displayed_size())

    assert lines == [(2, 1), (2, 1), (1, 2), (1, 2), (1, 2), (2, 1)]


def test_fit_shapes_starts_anew_for_other_videos():
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=["A", "B"])
    layout.fit_to(1800, 1080, {})
    assert layout.displayed_size() == (1, 2)

    # side by side shows them a little bigger, not enough to change...
    layout.fit_to(1990, 1080, {})
    assert layout.displayed_size() == (1, 2)

    # ...unless the videos are others, or in another order
    layout.drop([], None, None, DropZone.CENTER, src_id="A", dst_id="B")
    layout.fit_to(1990, 1080, {})
    assert layout.displayed_size() == (2, 1)

    layout.add(["C"])
    # until fit_to has chosen, as the square grid
    assert layout.displayed_size() == (2, 2)


def test_fit_shapes_ignores_the_line_options():
    layout = FlowLayout(
        mode=FlowMode.SHAPES,
        size=1,
        is_fit=False,
        is_match_shapes=False,
        ids=["A", "B"],
    )
    layout.fit_to(1920, 1080, {"A": TALL, "B": TALL})
    assert layout.displayed_size() == (2, 1)


def test_fit_shapes_crops_to_fill_the_window():
    ids = ["A", "B", "C"]
    shapes = dict.fromkeys(ids, TALL)

    layout = FlowLayout(mode=FlowMode.SHAPES, ids=ids, crop=10)
    layout.fit_to(1920, 1080, shapes)
    boxes = [box for _id, box in layout.boxes()]
    assert (boxes[0].left, boxes[2].right) == (0, 1)

    layout.crop = 0
    boxes = [box for _id, box in layout.boxes()]
    assert boxes[0].left > 0.02


def test_cropping_takes_the_layout_that_cuts_less():
    # ten wide videos: three rows fill the window cutting a little, where
    # one row stretched down would cut nine tenths of each
    ids = [str(i) for i in range(10)]
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=ids, crop=50)
    layout.fit_to(1920, 1080, dict.fromkeys(ids, WIDE))

    assert layout.displayed_size()[1] > 1


def _log_areas(layout, width, height):
    return sum(
        math.log((box.right - box.left) * width * (box.bottom - box.top) * height)
        for _id, box in layout.boxes()
    )


def _tile(layout, video_id):
    box = dict(layout.boxes())[video_id]
    return (box.right - box.left) * (box.bottom - box.top)


def test_a_video_made_bigger_gets_a_bigger_tile():
    ids = ["A", "B", "C", "D", "E", "F", "G", "H"]
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=ids)
    layout.fit_to(1600, 900, {})
    before = _tile(layout, "A")

    size = layout.size_step("A", 1)
    assert size is not None
    assert size > 0
    layout.sizes["A"] = size
    layout.fit_to(1600, 900, {})

    assert _tile(layout, "A") > before
    assert layout.order() == ids


def test_a_step_back_down_comes_back_to_nought():
    ids = ["A", "B", "C", "D", "E", "F", "G", "H"]
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=ids)
    layout.fit_to(1600, 900, {})

    layout.sizes["A"] = layout.size_step("A", 1)
    layout.fit_to(1600, 900, {})

    assert layout.size_step("A", -1) == 0


def test_no_step_where_the_tile_cannot_change():
    # one video fills the area whatever it counts for
    layout = FlowLayout(mode=FlowMode.SHAPES, ids=["A"])
    layout.fit_to(1600, 900, {"A": 16 / 9})

    assert layout.size_step("A", 1) is None
    assert layout.size_step("A", -1) is None
    assert FlowLayout(ids=["A", "B"]).size_step("A", 1) is None


def test_reordered_the_pictures_show_bigger():
    ids = ["A", "B", "C", "D", "E", "F"]
    shapes = dict(zip(ids, [WIDE, TALL] * 3))

    given = FlowLayout(mode=FlowMode.SHAPES, ids=ids)
    given.fit_to(1920, 1080, shapes)

    reordered = FlowLayout(mode=FlowMode.SHAPES, ids=ids, is_reordered=True)
    reordered.fit_to(1920, 1080, shapes)

    assert _log_areas(reordered, 1920, 1080) > _log_areas(given, 1920, 1080)
    shown = [i for i, _box in reordered.boxes()]
    assert shown != ids
    # in the order shown, their own kept
    assert reordered.order() == shown
    assert reordered.ids == ids
    assert [reordered.id_at(*reordered.position_of(i)) for i in ids] == ids
    assert reordered.id_at(0, 0) == shown[0]
