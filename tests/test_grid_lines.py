import math

import pytest

from gridplayer.utils.layout import EVEN, Box, FlowLayout, FlowMode, GridLayout, Weights
from gridplayer.utils.layout.boxes import grid_box, line_edges, picture_score
from gridplayer.utils.layout.lines import (
    FitCell,
    GridLines,
    Line,
    LineDrag,
    Snap,
    SnapKind,
    Span,
    Target,
    fit_weights,
)

PHONE = 9 / 16
WIDE = 16 / 9


def _score(cells, weights, cols, rows, width, height):
    placed = (
        (
            grid_box(
                c.height.start,
                c.width.start,
                rows,
                cols,
                c.height.count,
                c.width.count,
                weights,
            ),
            c.shape,
        )
        for c in cells
    )
    return picture_score(placed, width, height)


def test_line_edges_even_unless_one_weight_each():
    assert line_edges(3) == (0, 1 / 3, 2 / 3, 1)
    assert line_edges(2, (0.25, 0.75)) == (0, 0.25, 1.0)
    # kept for another count of columns
    assert line_edges(3, (0.25, 0.75)) == (0, 1 / 3, 2 / 3, 1)
    assert line_edges(2, (1, 3)) == (0, 0.25, 1.0)


def test_grid_box_spans_the_weighted_lines():
    weights = Weights(cols=(0.5, 0.25, 0.25), rows=(0.75, 0.25))

    assert grid_box(0, 1, 2, 3, colspan=2, weights=weights) == Box(0.5, 0, 1.0, 0.75)
    assert grid_box(1, 0, 2, 3, weights=weights) == Box(0, 0.75, 0.5, 1.0)


def test_rows_first_lines_where_the_weights_have_them():
    layout = FlowLayout(ids=list("ABCDE"), size=3)
    weights = Weights(cols=(0.5, 0.25, 0.25), rows=(0.6, 0.4))

    assert layout.boxes(weights) == [
        ("A", Box(0, 0, 0.5, 0.6)),
        ("B", Box(0.5, 0, 0.75, 0.6)),
        ("C", Box(0.75, 0, 1.0, 0.6)),
        ("D", Box(0, 0.6, 0.5, 1.0)),
        ("E", Box(0.5, 0.6, 0.75, 1.0)),
    ]


def test_fill_gaps_last_row_has_lines_of_its_own():
    layout = FlowLayout(ids=list("ABCDE"), size=3, is_fit=True)
    assert layout.own_lines() == {1: 2}

    # the columns over it moved: it stays even
    weights = Weights(cols=(0.5, 0.25, 0.25), rows=(0.6, 0.4))
    assert layout.boxes(weights)[3:] == [
        ("D", Box(0, 0.6, 0.5, 1.0)),
        ("E", Box(0.5, 0.6, 1.0, 1.0)),
    ]

    # its own moved
    weights = weights.with_line(1, (0.3, 0.7))
    assert layout.boxes(weights)[3:] == [
        ("D", Box(0, 0.6, 0.3, 1.0)),
        ("E", Box(0.3, 0.6, 1.0, 1.0)),
    ]
    assert layout.boxes(weights)[0] == ("A", Box(0, 0, 0.5, 0.6))


def test_no_short_line_when_full_or_without_fill_gaps():
    assert FlowLayout(ids=list("ABCD"), size=2, is_fit=True).own_lines() == {}
    assert FlowLayout(ids=list("ABCDE"), size=3).own_lines() == {}


def _short_row_lines(weights=EVEN):
    # Rows First, Fill Gaps: A B C over D E
    layout = FlowLayout(ids=list("ABCDE"), size=3, is_fit=True)
    cells = [(box, WIDE) for _id, box in layout.boxes(weights)]
    return GridLines(cells, 3, 2, weights, 900, 400, own=layout.own_lines())


def test_short_row_lines_found_apart_from_the_columns():
    lines = _short_row_lines()

    # a column line, over the short row only
    assert lines.line_at(300, 100, 4) == Line(True, 0)
    assert lines.line_at(300, 300, 4) is None
    # the short row's own, under the columns only
    assert lines.line_at(450, 300, 4) == Line(True, 0, own=1)
    assert lines.line_at(450, 100, 4) is None
    assert lines.span(Line(True, 0, own=1)) == (200, 400)
    # the line between the rows, across all of it
    assert lines.line_at(450, 200, 4) == Line(False, 0)
    assert lines.span(Line(False, 0)) == (0, 900)


def test_short_row_line_moved_alone():
    lines = _short_row_lines()

    weights = lines.moved(Line(True, 0, own=1), 300)
    assert weights.lines[1] == pytest.approx((1 / 3, 2 / 3))
    assert weights.cols == pytest.approx((1 / 3, 1 / 3, 1 / 3))

    moved = _short_row_lines(weights)
    assert moved.position(Line(True, 0, own=1)) == 300
    assert moved.evened(Line(True, 0, own=1)).lines[1] == pytest.approx((0.5, 0.5))
    assert moved.evened(Line(True, 0)).lines[1] == weights.lines[1]


def test_fit_takes_the_short_row_lines():
    # a wide video and a phone video under three wide ones
    cells = [FitCell.at(0, n, WIDE) for n in range(3)] + [
        FitCell(Span(1, 0), Span("rows", 1), PHONE),
        FitCell(Span(1, 1), Span("rows", 1), WIDE),
    ]

    weights = fit_weights(cells, 3, 2, 1800, 800, own={1: 2})

    assert len(weights.lines[1]) == 2
    assert weights.lines[1][0] < 0.5


def test_unlinked_every_row_has_lines_of_its_own():
    layout = FlowLayout(ids=list("ABCDE"), size=3, is_linked=False)
    # the short row, not spread, has as many places as the others
    assert layout.own_lines() == {0: 3, 1: 3}

    layout.is_fit = True
    assert layout.own_lines() == {0: 3, 1: 2}


def test_unlinked_rows_take_their_own_else_the_columns():
    layout = FlowLayout(ids=list("ABCDEF"), size=3, is_linked=False)
    weights = Weights(cols=(0.5, 0.25, 0.25), rows=(0.5, 0.5)).with_line(
        1, (0.25, 0.25, 0.5)
    )

    boxes = dict(layout.boxes(weights))
    assert boxes["B"] == Box(0.5, 0, 0.75, 0.5)
    assert boxes["E"] == Box(0.25, 0.5, 0.5, 1.0)


def test_columns_first_unlinked_columns_have_their_own():
    layout = FlowLayout(mode=FlowMode.COLS, ids=list("ABCD"), size=2, is_linked=False)
    weights = Weights().with_line(1, (0.25, 0.75))

    assert dict(layout.boxes(weights))["C"] == Box(0.5, 0, 1.0, 0.25)
    assert dict(layout.boxes(weights))["A"] == Box(0, 0, 0.5, 0.5)


def test_linked_again_where_the_rows_are_on_average():
    layout = FlowLayout(ids=list("ABCDEFG"), size=3, is_fit=True, is_linked=False)
    weights = (
        Weights(rows=(0.4, 0.3, 0.3))
        .with_line(0, (0.5, 0.25, 0.25))
        .with_line(1, (0.3, 0.35, 0.35))
        .with_line(2, (1.0,))
    )

    linked = layout.linked(weights)

    assert linked.cols == pytest.approx((0.4, 0.3, 0.3))
    assert linked.rows == weights.rows
    # the short row Fill Gaps spreads keeps its own
    assert linked.lines == ((), (), (1.0,))


def test_linked_again_where_no_row_is_moved_is_as_it_was():
    layout = FlowLayout(ids=list("ABCD"), size=2, is_linked=False)
    weights = Weights(cols=(0.3, 0.7))

    assert layout.linked(weights).cols == pytest.approx((0.3, 0.7))


def _unlinked_lines(weights=EVEN, shapes=(WIDE,) * 6):
    # Rows First, Link Rows off: A B C over D E F
    layout = FlowLayout(ids=list("ABCDEF"), size=3, is_linked=False)
    cells = [(box, shape) for (_id, box), shape in zip(layout.boxes(weights), shapes)]
    return GridLines(cells, 3, 2, weights, 900, 400, own=layout.own_lines())


def test_unlinked_row_line_found_and_moved_alone():
    lines = _unlinked_lines()

    assert lines.line_at(300, 100, 4) == Line(True, 0, own=0)
    assert lines.line_at(300, 300, 4) == Line(True, 0, own=1)
    assert lines.span(Line(True, 0, own=0)) == (0, 200)
    assert lines.line_at(450, 200, 4) == Line(False, 0)

    weights = lines.moved(Line(True, 0, own=0), 200)
    moved = _unlinked_lines(weights)
    assert moved.position(Line(True, 0, own=0)) == 200
    assert moved.position(Line(True, 0, own=1)) == 300

    assert not moved.is_even()
    assert moved.evened(Line(True, 0, own=0)).lines[0] == pytest.approx((1 / 3,) * 3)


def test_unlinked_row_line_snaps_in_line_with_the_next_row():
    weights = Weights().with_line(1, (0.2, 0.4, 0.4))
    lines = _unlinked_lines(weights, shapes=(None,) * 6)

    snaps = [(round(t.position), t.kind) for t in lines.snaps(Line(True, 0, own=0))]

    # the next row's lines at 180 and 540; even between 0 and 600 is 300
    assert snaps == [
        (180, SnapKind.ALIGNED),
        (300, SnapKind.EVEN),
        (540, SnapKind.ALIGNED),
    ]


def test_linked_lines_do_not_snap_in_line():
    lines = _two_by_two(shapes=(None,) * 4)

    assert [t.kind for t in lines.snaps(Line(True, 0))] == [SnapKind.EVEN]


def test_unlinked_fit_fits_each_row():
    # a phone video then a wide one, over a wide one then a phone video
    cells = [
        FitCell(Span(0, 0), Span("rows", 0), PHONE),
        FitCell(Span(0, 1), Span("rows", 0), WIDE),
        FitCell(Span(1, 0), Span("rows", 1), WIDE),
        FitCell(Span(1, 1), Span("rows", 1), PHONE),
    ]

    weights = fit_weights(cells, 2, 2, 1000, 1080, own={0: 2, 1: 2})

    assert weights.cols == ()
    assert weights.lines[0][0] * 1000 == pytest.approx(540 * PHONE, abs=2)
    assert weights.lines[1][1] * 1000 == pytest.approx(540 * PHONE, abs=2)


def test_columns_first_takes_the_columns_across():
    layout = FlowLayout(mode=FlowMode.COLS, ids=list("ABCD"), size=2)
    weights = Weights(cols=(0.7, 0.3), rows=(0.4, 0.6))

    assert layout.boxes(weights) == [
        ("A", Box(0, 0, 0.7, 0.4)),
        ("B", Box(0, 0.4, 0.7, 1.0)),
        ("C", Box(0.7, 0, 1.0, 0.4)),
        ("D", Box(0.7, 0.4, 1.0, 1.0)),
    ]


def test_fixed_grid_lines_where_the_weights_have_them():
    grid = GridLayout(max_rows=1, max_cols=2, preallocate=True)
    grid.pack_flow(["A", "B"])

    boxes = [(cell.video_id, box) for cell, box in grid.boxes(Weights((0.3, 0.7)))]
    assert boxes == [("A", Box(0, 0, 0.3, 1.0)), ("B", Box(0.3, 0, 1.0, 1.0))]


def _two_by_two(weights=EVEN, shapes=(PHONE, WIDE, WIDE, WIDE)):
    cells = [
        (grid_box(n // 2, n % 2, 2, 2, weights=weights), shape)
        for n, shape in enumerate(shapes)
    ]
    return GridLines(cells, 2, 2, weights, 1000, 600)


def test_line_found_near_it_on_its_cells():
    lines = _two_by_two()

    assert lines.line_at(497, 100, 4) == Line(True, 0)
    assert lines.line_at(500, 302, 4) == Line(True, 0)
    assert lines.line_at(200, 303, 4) == Line(False, 0)
    assert lines.line_at(490, 100, 4) is None
    # the area's own edges are no lines
    assert lines.line_at(2, 100, 4) is None


def test_no_line_where_no_cell_edge_is():
    # Fill Gaps: the last row's one video is as wide as the whole row
    layout = FlowLayout(ids=list("ABC"), size=2, is_fit=True)
    cells = [(box, WIDE) for _id, box in layout.boxes()]
    lines = GridLines(cells, 2, 2, EVEN, 1000, 600)

    assert lines.line_at(500, 100, 4) == Line(True, 0)
    assert lines.line_at(500, 500, 4) is None
    assert lines.span(Line(True, 0)) == (0, 300)


def test_moved_line_resizes_only_the_cells_either_side():
    lines = GridLines(
        [(grid_box(0, n, 1, 3), WIDE) for n in range(3)], 3, 1, EVEN, 900, 300
    )

    weights = lines.moved(Line(True, 0), 200)
    assert weights.cols == pytest.approx((2 / 9, 4 / 9, 1 / 3))
    assert lines.position(Line(True, 0), weights) == 200
    assert lines.position(Line(True, 1), weights) == 600


def test_moved_line_leaves_the_cells_some_room():
    lines = GridLines(
        [(grid_box(0, n, 1, 2), WIDE) for n in range(2)], 2, 1, EVEN, 1000, 300
    )

    assert lines.moved(Line(True, 0), -50).cols[0] == pytest.approx(0.048)
    assert lines.moved(Line(True, 0), 2000).cols[1] == pytest.approx(0.048)


def test_line_snaps_where_a_video_beside_it_fits_or_cells_are_even():
    lines = _two_by_two()

    snaps = [(round(t.position, 2), t.kind, t.side) for t in lines.snaps(Line(True, 0))]

    # the phone, top left, fits 300 * 9 / 16 wide; a wide one on the left
    # fits 300 * 16 / 9 wide, and those on the right from the right edge
    assert snaps == [
        (168.75, SnapKind.FITS, -1),
        (466.67, SnapKind.FITS, 1),
        (500.0, SnapKind.EVEN, 0),
        (533.33, SnapKind.FITS, -1),
    ]


def test_snaps_where_fitting_is_even_too_say_it_fits():
    # two wide videos in a window two of them wide: they fit at even
    cells = [(grid_box(0, n, 1, 2), WIDE) for n in range(2)]
    lines = GridLines(cells, 2, 1, EVEN, 1000, 281.25)

    snaps = lines.snaps(Line(True, 0))
    assert [(t.kind, t.side) for t in snaps] == [(SnapKind.FITS, 0)]


def test_snap_holds_until_far_enough():
    snap = Snap(reach=8, hold=12)
    targets = [Target(100, SnapKind.EVEN)]

    assert snap(120, targets) == 120
    assert snap.target is None
    assert snap(107, targets) == 100
    assert snap.target == targets[0]
    assert snap(111, targets) == 100
    assert snap(113, targets) == 113
    assert snap(109, targets) == 109


def test_fit_puts_the_line_where_the_tall_video_fits():
    # #329: a phone video and a wide one side by side
    cells = [FitCell.at(0, 0, PHONE), FitCell.at(0, 1, WIDE)]

    weights = fit_weights(cells, 2, 1, 1920, 1080)

    assert weights.cols[0] * 1920 == pytest.approx(1080 * PHONE, abs=2)


def test_fit_does_not_move_lines_for_nothing():
    cells = [FitCell.at(0, n, WIDE) for n in range(2)]

    assert fit_weights(cells, 2, 1, 1920, 1080) == EVEN


@pytest.mark.parametrize("seed", range(6))
def test_fit_is_no_worse_than_any_line_nearby(seed):
    import random

    rng = random.Random(seed)
    cols, rows = rng.randint(1, 3), rng.randint(2, 3)
    cells = [
        FitCell.at(n // cols, n % cols, rng.choice([PHONE, WIDE, 1.0, 4 / 3]))
        for n in range(cols * rows)
    ]
    width, height = rng.choice([(1920, 1080), (1080, 1920), (1600, 1200)])

    weights = fit_weights(cells, cols, rows, width, height)
    if weights == EVEN:
        weights = Weights(
            tuple(1 / cols for _ in range(cols)), tuple(1 / rows for _ in range(rows))
        )
    best = _score(cells, weights, cols, rows, width, height)

    assert best >= _score(cells, EVEN, cols, rows, width, height) - 1e-9

    for _ in range(300):
        nudged = [
            tuple(w * math.exp(rng.gauss(0, 0.03)) for w in side) for side in weights
        ]
        nudged = Weights(*(tuple(w / sum(side) for w in side) for side in nudged))
        assert _score(cells, nudged, cols, rows, width, height) <= best + 1e-3 * len(
            cells
        )


def test_fit_takes_spans():
    cells = [
        FitCell.at(0, 0, WIDE, 1, 2),
        FitCell.at(1, 0, PHONE),
        FitCell.at(1, 1, WIDE),
        FitCell.at(0, 2, PHONE, 2, 1),
    ]

    weights = fit_weights(cells, 3, 2, 1920, 1080)

    assert _score(cells, weights, 3, 2, 1920, 1080) > _score(
        cells, EVEN, 3, 2, 1920, 1080
    )


def test_a_line_dragged_snaps_unless_told_not_to():
    lines = _two_by_two(shapes=(None,) * 4)
    drag = LineDrag(Line(True, 0), lines)

    # even is at 500
    snapped = drag.moved(504, is_snapping=True)
    assert drag.position(snapped) == 500
    assert drag.target.kind is SnapKind.EVEN

    free = drag.moved(504, is_snapping=False)
    assert drag.position(free) == 504
    assert drag.target is None
    assert drag.before == lines.weights()
