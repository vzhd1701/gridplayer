import pytest

from gridplayer.models.grid_state import GridCell
from gridplayer.params.static import GRID_TEMPLATES
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import GridLayout


def _grid(ids, rows=3, cols=3):
    grid = GridLayout(max_rows=rows, max_cols=cols)
    grid.pack_flow(ids)
    return grid


def _cells(grid):
    return sorted((c.video_id, c.row, c.col, c.rowspan, c.colspan) for c in grid.cells)


def test_bigger_moves_only_the_videos_in_its_way():
    grid = _grid(["A", "B", "C", "D"])

    assert grid.stepped("A", 1, 1) == (2, 2)
    assert grid.set_span("A", 2, 2)

    # C is not in the way: it stays
    assert _cells(grid) == [
        ("A", 0, 0, 2, 2),
        ("B", 1, 2, 1, 1),
        ("C", 0, 2, 1, 1),
        ("D", 2, 0, 1, 1),
    ]


def test_bigger_grows_where_it_covers_the_fewest():
    grid = _grid(list("ABCDE"))

    # over B, or over C and F's free cell: there
    assert grid.set_span("C", 2, 1)

    assert ("C", 0, 2, 2, 1) in _cells(grid)
    assert grid.position_of("B") == (0, 1)


def test_smaller_leaves_the_others_where_they_are():
    grid = _grid(["A", "B", "C", "D", "E", "F"])

    grid.set_span("A", 2, 2)
    after = [cell for cell in _cells(grid) if cell[0] != "A"]
    assert grid.stepped("A", -1, -1) == (1, 1)
    assert grid.set_span("A", 1, 1)

    assert ("A", 0, 0, 1, 1) in _cells(grid)
    assert [cell for cell in _cells(grid) if cell[0] != "A"] == after


def test_bigger_with_no_room_both_ways_takes_one():
    # room for one more cell only
    grid = _grid(["A", "B", "C"], rows=2, cols=2)

    assert grid.steps("A", 1, 1) == [(2, 2), (1, 2), (2, 1)]
    assert grid.step_span("A", 1, 1) == (1, 2)
    assert grid.step_span("A", -1, -1) is None

    grid.set_span("A", 1, 2)
    assert grid.position_of("B") == (1, 1)
    assert grid.step_span("A", 1, 1) is None


def test_bigger_tries_the_way_it_is_short_of_first():
    grid = GridLayout(
        max_rows=3,
        max_cols=3,
        cells=[GridCell(video_id="A", row=0, col=0, rowspan=1, colspan=2)],
    )

    assert grid.steps("A", 1, 1) == [(2, 3), (2, 2), (1, 3)]


def test_bigger_refused_with_no_room():
    grid = _grid(list("ABCDEFGHI"))
    before = _cells(grid)

    assert not grid.set_span("E", 2, 2)
    assert _cells(grid) == before


def test_bigger_at_the_edge_grows_back_from_it():
    grid = _grid(["A", "B", "C"])

    assert grid.set_span("C", 2, 2)

    assert ("C", 0, 1, 2, 2) in _cells(grid)
    assert grid.order() == ["A", "C", "B"]


def test_videos_before_it_stay_where_they_are():
    grid = GridLayout(
        max_rows=3,
        max_cols=3,
        cells=[
            GridCell(video_id="A", row=0, col=2),
            GridCell(video_id="B", row=1, col=0),
            GridCell(video_id="C", row=1, col=1),
        ],
    )

    assert grid.set_span("B", 2, 2)

    assert _cells(grid) == [
        ("A", 0, 2, 1, 1),
        ("B", 1, 0, 2, 2),
        ("C", 1, 2, 1, 1),
    ]


def test_bigger_takes_the_free_cells_before_it_too():
    # after A there is one free cell, for two videos: before it, three
    grid = GridLayout(
        max_rows=2,
        max_cols=3,
        preallocate=True,
        cells=[
            GridCell(video_id="A", row=0, col=1),
            GridCell(video_id="B", row=1, col=0),
            GridCell(video_id="C", row=1, col=1),
        ],
    )

    assert grid.set_span("A", 2, 2)

    assert _cells(grid) == [
        ("A", 0, 1, 2, 2),
        ("B", 1, 0, 1, 1),
        ("C", 0, 0, 1, 1),
    ]


def test_bigger_and_smaller_stop_at_the_grid():
    grid = _grid(["A"], rows=2, cols=2)
    grid.set_span("A", 2, 2)

    assert grid.stepped("A", 1, 1) is None
    assert _grid(["A"], rows=1, cols=3).stepped("A", 1, 1) == (1, 2)
    assert _grid(["A"]).stepped("A", -1, -1) is None


def _big_a(rows=3, cols=4):
    return GridLayout(
        max_rows=rows,
        max_cols=cols,
        cells=[
            GridCell(video_id="A", row=0, col=0, rowspan=2, colspan=2),
            GridCell(video_id="B", row=0, col=2),
            GridCell(video_id="C", row=1, col=2),
        ],
    )


def test_a_big_cell_dropped_on_a_video_trades_places_with_it():
    grid = _big_a()
    grid.preallocate = True

    assert grid.drop([], None, None, DropZone.CENTER, src_id="A", dst_id="B") == []

    # back from the edge, as far as it has to: B and C to where it was
    assert _cells(grid) == [
        ("A", 0, 2, 2, 2),
        ("B", 0, 1, 1, 1),
        ("C", 1, 1, 1, 1),
    ]


def test_a_video_dropped_on_a_big_cell_trades_places_with_it():
    grid = _big_a()
    grid.preallocate = True

    # as the big cell dropped on it: it goes where C was
    grid.drop([], None, None, DropZone.CENTER, src_id="C", dst_id="A")

    assert _cells(grid) == [
        ("A", 1, 2, 2, 2),
        ("B", 0, 2, 1, 1),
        ("C", 1, 1, 1, 1),
    ]


def test_videos_of_a_size_dropped_on_each_other_swap():
    grid = _big_a()

    grid.drop([], None, None, DropZone.CENTER, src_id="C", dst_id="B")

    assert grid.position_of("C") == (0, 2)
    assert grid.position_of("B") == (1, 2)


def test_dropped_beside_a_big_cell_goes_beside_the_whole_of_it():
    grid = _big_a()

    assert grid.drop(["N"], None, None, DropZone.BELOW, dst_id="A") == []

    assert ("N", 2, 0, 1, 1) in _cells(grid)
    assert ("A", 0, 0, 2, 2) in _cells(grid)


def test_a_column_put_in_through_a_big_cell_widens_it():
    grid = _big_a()

    # before C, a column put in where none of the grid is free
    assert grid.drop(["N"], None, None, DropZone.BEFORE, dst_id="B") == []

    assert _cells(grid) == [
        ("A", 0, 0, 2, 2),
        ("B", 0, 3, 1, 1),
        ("C", 1, 3, 1, 1),
        ("N", 0, 2, 1, 1),
    ]


def test_a_big_cell_is_pushed_as_one():
    grid = GridLayout(
        max_rows=3,
        max_cols=4,
        cells=[
            GridCell(video_id="X", row=0, col=0),
            GridCell(video_id="A", row=0, col=1, rowspan=2, colspan=2),
            GridCell(video_id="Y", row=1, col=0),
            GridCell(video_id="W", row=2, col=3),
        ],
    )

    # the grid is as wide as it can be: X and A are pushed along, Y not
    assert grid.drop(["N"], None, None, DropZone.BEFORE, dst_id="X") == []

    assert _cells(grid) == [
        ("A", 0, 2, 2, 2),
        ("N", 0, 0, 1, 1),
        ("W", 2, 3, 1, 1),
        ("X", 0, 1, 1, 1),
        ("Y", 1, 0, 1, 1),
    ]


def test_a_push_past_the_grid_is_refused():
    grid = GridLayout(
        max_rows=2,
        max_cols=3,
        cells=[
            GridCell(video_id="X", row=0, col=0),
            GridCell(video_id="A", row=0, col=1, rowspan=2, colspan=2),
            GridCell(video_id="Y", row=1, col=0),
        ],
    )
    before = _cells(grid)

    assert grid.drop(["N"], None, None, DropZone.BEFORE, dst_id="X") == ["N"]
    assert _cells(grid) == before


def test_a_video_put_in_a_big_cell_takes_its_size():
    grid = _big_a()

    grid.occupy(1, 1, "N")
    assert ("N", 0, 0, 2, 2) in _cells(grid)
    assert not grid.contains("A")


def test_a_tall_cell_trades_places_with_the_two_beside_it():
    grid = GridLayout(
        max_rows=2,
        max_cols=2,
        cells=[
            GridCell(video_id="A", row=0, col=0, rowspan=2, colspan=1),
            GridCell(video_id="B", row=0, col=1),
            GridCell(video_id="C", row=1, col=1),
        ],
    )

    grid.drop([], None, None, DropZone.CENTER, src_id="A", dst_id="B")

    assert _cells(grid) == [
        ("A", 0, 1, 2, 1),
        ("B", 0, 0, 1, 1),
        ("C", 1, 0, 1, 1),
    ]


def _big_on_top():
    return GridLayout(
        max_rows=3,
        max_cols=3,
        cells=[
            GridCell(video_id="A", row=0, col=0, rowspan=2, colspan=2),
            GridCell(video_id="B", row=0, col=2),
            GridCell(video_id="C", row=1, col=2),
            GridCell(video_id="D", row=2, col=0),
            GridCell(video_id="E", row=2, col=1),
        ],
    )


def test_a_big_cell_dropped_above_the_one_below_it_stays():
    grid = _big_on_top()
    before = _cells(grid)

    assert grid.drop([], None, None, DropZone.ABOVE, src_id="A", dst_id="D") == []
    assert _cells(grid) == before


def test_a_big_cell_dropped_beside_another_keeps_its_size():
    grid = _big_on_top()
    grid.max_cols = 4

    assert grid.drop([], None, None, DropZone.AFTER, src_id="A", dst_id="B") == []

    assert _cells(grid) == [
        ("A", 0, 2, 2, 2),
        ("B", 0, 1, 1, 1),
        ("C", 1, 1, 1, 1),
        ("D", 2, 0, 1, 1),
        ("E", 2, 1, 1, 1),
    ]


def test_a_big_cell_at_the_grid_edge_still_goes_beside_it():
    # below E is one row of the grid, A is two high: E goes up into what A
    # left, A below it
    grid = _big_on_top()
    grid.max_rows = 4

    assert grid.drop([], None, None, DropZone.BELOW, src_id="A", dst_id="E") == []

    assert ("A", 2, 1, 2, 2) in _cells(grid)
    assert ("E", 1, 1, 1, 1) in _cells(grid)


def test_a_smaller_grid_makes_a_big_cell_fit():
    grid = _big_a()

    assert grid.resize(1, 3) == ["C"]
    assert ("A", 0, 0, 1, 2) in _cells(grid)


@pytest.mark.parametrize(
    ("name", "count"),
    [
        ("1 + 2", 3),
        ("1 + 3", 4),
        ("1 + 5", 6),
        ("1 + 7", 8),
        ("1 + 12", 13),
        ("2 + 8", 10),
    ],
)
def test_templates_hold_what_they_are_named_for(name, count):
    assert len(GRID_TEMPLATES[name].places()) == count


def test_template_puts_the_first_videos_in_its_big_cells():
    grid = GridLayout(max_rows=1, max_cols=1, preallocate=True)

    grid.apply_template(GRID_TEMPLATES["1 + 12"], list("ABCDEFGHIJKLMNO"))

    assert grid.order()[-1] == "M"
    assert ("A", 1, 1, 2, 2) in _cells(grid)
    assert grid.id_at(0, 0) == "B"
    assert grid.free_capacity() == 0
    assert grid.is_template(GRID_TEMPLATES["1 + 12"])
    assert not grid.is_template(GRID_TEMPLATES["1 + 7"])

    grid.set_span("A", 1, 1)
    assert not grid.is_template(GRID_TEMPLATES["1 + 12"])


def _editing(ids, rows, cols):
    grid = _grid(ids, rows=rows, cols=cols)
    grid.is_editing = True
    return grid


def test_place_moves_the_covered_videos_nearest():
    grid = _editing(["A", "B", "C", "D"], rows=2, cols=3)

    assert grid.place("A", 0, 0, 1, 2)

    # B to the free cell under it, not the one further on
    assert _cells(grid) == [
        ("A", 0, 0, 1, 2),
        ("B", 1, 1, 1, 1),
        ("C", 0, 2, 1, 1),
        ("D", 1, 0, 1, 1),
    ]


def test_place_onto_a_video_of_its_size_swaps():
    grid = _editing(["A", "B", "C"], rows=2, cols=3)

    assert grid.place("A", 1, 2, 1, 1)

    assert grid.id_at(1, 2) == "A"
    assert grid.id_at(0, 0) is None
    assert grid.place("B", 1, 2, 1, 1)
    assert grid.id_at(1, 2) == "B"
    assert grid.id_at(0, 1) == "A"


def test_place_refused_where_the_covered_do_not_fit():
    grid = _editing(["A", "B", "C", "D"], rows=2, cols=3)
    before = _cells(grid)

    assert not grid.can_place("A", 0, 0, 2, 2)
    assert not grid.place("A", 0, 0, 2, 2)
    assert _cells(grid) == before
    assert not grid.place("A", 1, 2, 1, 2)


def test_editing_shows_every_cell_and_keeps_the_empty_ones():
    grid = _grid(["A", "B"], rows=3, cols=3)
    grid.is_editing = True

    assert grid.displayed_size() == (3, 3)
    assert grid.place("A", 2, 2, 1, 1)
    assert grid.id_at(2, 2) == "A"

    grid.is_editing = False
    assert grid.displayed_size() == (3, 3)
    grid.remove_video("B")
    grid.compact_edges()
    assert grid.id_at(0, 0) == "A"
