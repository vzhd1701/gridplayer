from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.params.static import GridMode
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import Direction, GridLayout


def _occ(cells=None, rows=3, cols=3, preallocate=False):
    return GridLayout(
        max_rows=rows,
        max_cols=cols,
        preallocate=preallocate,
        cells=cells,
    )


def test_pack_flow_rows_first():
    occ = _occ(rows=2, cols=2)
    occ.pack_flow(["A", "B", "C"])
    assert [(c.row, c.col, c.video_id) for c in occ.cells] == [
        (0, 0, "A"),
        (0, 1, "B"),
        (1, 0, "C"),
    ]


def _v1_v2_v3_v4_staggered():
    return _occ(
        [
            GridCell(video_id="V1", row=0, col=0),
            GridCell(video_id="V2", row=0, col=1),
            GridCell(video_id="V3", row=0, col=2),
            GridCell(video_id="V4", row=1, col=2),
        ],
        rows=3,
        cols=3,
    )


def test_resize_grow_keeps_layout():
    occ = _v1_v2_v3_v4_staggered()
    leftover = occ.resize(6, 6)
    assert leftover == []
    assert occ.max_rows == 6
    assert occ.max_cols == 6
    assert occ.id_at(0, 0) == "V1"
    assert occ.id_at(0, 1) == "V2"
    assert occ.id_at(0, 2) == "V3"
    assert occ.id_at(1, 2) == "V4"
    assert occ.id_at(0, 3) is None
    assert occ.displayed_size() == (3, 2)


def test_resize_shrink_relocates_only_clipped_cells():
    occ = _occ(
        [
            GridCell(video_id="V1", row=0, col=0),
            GridCell(video_id="V2", row=0, col=1),
            GridCell(video_id="V3", row=0, col=2),
            GridCell(video_id="V4", row=1, col=2),
            GridCell(video_id="V5", row=2, col=2),
        ],
        rows=3,
        cols=3,
    )
    leftover = occ.resize(2, 3)
    assert leftover == []
    assert occ.id_at(0, 0) == "V1"
    assert occ.id_at(0, 1) == "V2"
    assert occ.id_at(0, 2) == "V3"
    assert occ.id_at(1, 0) == "V5"
    assert occ.id_at(1, 1) is None
    assert occ.id_at(1, 2) == "V4"


def test_resize_overflow_keeps_fitting_cells():
    occ = _occ(rows=2, cols=2)
    occ.pack_flow(["A", "B", "C", "D"])
    leftover = occ.resize(1, 2)
    assert leftover == ["C", "D"]
    assert occ.id_at(0, 0) == "A"
    assert occ.id_at(0, 1) == "B"


def test_displayed_size_compact_vs_preallocate():
    cells = [
        GridCell(video_id="A", row=0, col=0),
        GridCell(video_id="B", row=1, col=1),
    ]
    occ = _occ(cells, rows=3, cols=3, preallocate=False)
    assert occ.displayed_size() == (2, 2)
    occ.preallocate = True
    assert occ.displayed_size() == (3, 3)
    assert _occ(rows=3, cols=3).displayed_size() == (1, 1)


def test_place_in_empties_moves_instead_of_duplicating():
    occ = _occ(
        [
            GridCell(video_id="B", row=0, col=0),
            GridCell(video_id="A", row=1, col=0),
        ],
        rows=2,
        cols=2,
    )
    leftover = occ.place_in_empties(["A"])
    assert leftover == []
    assert occ.id_at(1, 0) is None
    assert occ.id_at(0, 1) == "A"
    assert [c.video_id for c in occ.cells if c.video_id == "A"] == ["A"]


def test_place_in_empties_and_capacity():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=2, cols=2)
    leftover = occ.place_in_empties(["B", "C", "D"])
    assert leftover == []
    assert occ.free_capacity() == 0
    leftover = occ.place_in_empties(["E"])
    assert leftover == ["E"]


def test_remove_leaves_hole():
    occ = _occ(rows=2, cols=2)
    occ.pack_flow(["A", "B", "C"])
    occ.remove_video("B")
    assert occ.id_at(0, 1) is None
    assert occ.id_at(0, 0) == "A"
    assert occ.id_at(1, 0) == "C"


def test_drop_center_on_empty():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=2, cols=2)
    leftover = occ.drop_on_center(0, 1, ["B"])
    assert leftover == []
    assert occ.id_at(0, 1) == "B"


def test_drop_center_swap():
    occ = _occ(rows=1, cols=2)
    occ.pack_flow(["A", "B"])
    leftover = occ.drop_on_center(0, 1, ["A"], is_internal=True)
    assert leftover == []
    assert occ.id_at(0, 0) == "B"
    assert occ.id_at(0, 1) == "A"


def test_drop_resolves_position_from_dst_id():
    occ = _occ(rows=1, cols=2)
    occ.pack_flow(["A", "B"])
    leftover = occ.drop(
        ["A"],
        None,
        None,
        DropZone.CENTER,
        src_id="A",
        dst_id="B",
    )
    assert leftover == []
    assert occ.id_at(0, 0) == "B"
    assert occ.id_at(0, 1) == "A"


def _v1_v2_v3_l_shape():
    return _occ(
        [
            GridCell(video_id="V1", row=0, col=0),
            GridCell(video_id="V2", row=0, col=1),
            GridCell(video_id="V3", row=1, col=1),
        ],
        rows=3,
        cols=3,
    )


def test_insert_left_of_v1_grows_column_when_space():
    occ = _v1_v2_v3_l_shape()
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.LEFT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "NEW"
    assert occ.id_at(0, 1) == "V1"
    assert occ.id_at(0, 2) == "V2"
    assert occ.id_at(1, 0) is None
    assert occ.id_at(1, 1) is None
    assert occ.id_at(1, 2) == "V3"
    assert occ.displayed_size() == (3, 2)


def test_insert_center_on_v1_same_as_left():
    occ = _v1_v2_v3_l_shape()
    leftover = occ.drop_on_center(0, 0, ["NEW"])
    assert leftover == []
    assert occ.id_at(0, 0) == "NEW"
    assert occ.id_at(0, 1) == "V1"
    assert occ.id_at(0, 2) == "V2"
    assert occ.id_at(1, 2) == "V3"
    assert occ.displayed_size() == (3, 2)


def test_insert_right_of_v1_grows_column_when_space():
    occ = _v1_v2_v3_l_shape()
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.RIGHT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "V1"
    assert occ.id_at(0, 1) == "NEW"
    assert occ.id_at(0, 2) == "V2"
    assert occ.id_at(1, 0) is None
    assert occ.id_at(1, 1) is None
    assert occ.id_at(1, 2) == "V3"
    assert occ.displayed_size() == (3, 2)


def test_insert_left_of_v3_occupies_empty_neighbor():
    occ = _v1_v2_v3_l_shape()
    leftover, rejected = occ.drop_on_edge(1, 1, Direction.LEFT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "V1"
    assert occ.id_at(0, 1) == "V2"
    assert occ.id_at(0, 2) is None
    assert occ.id_at(1, 0) == "NEW"
    assert occ.id_at(1, 1) == "V3"
    assert occ.displayed_size() == (2, 2)


def test_place_in_empties_fills_displayed_hole_before_growing():
    occ = _v1_v2_v3_l_shape()
    leftover = occ.place_in_empties(["NEW"])
    assert leftover == []
    assert occ.id_at(1, 0) == "NEW"
    assert occ.id_at(0, 2) is None
    assert occ.displayed_size() == (2, 2)


def test_insert_left_of_v1_after_video_was_parked_in_first_empty():
    occ = _v1_v2_v3_l_shape()
    occ.occupy(0, 2, "NEW")
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.LEFT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "NEW"
    assert occ.id_at(0, 1) == "V1"
    assert occ.id_at(0, 2) == "V2"
    assert occ.id_at(1, 2) == "V3"
    assert occ.displayed_size() == (3, 2)


def _v1_to_v5_with_row_hole():
    return _occ(
        [
            GridCell(video_id="V1", row=0, col=0),
            GridCell(video_id="V2", row=0, col=1),
            GridCell(video_id="V3", row=0, col=2),
            GridCell(video_id="V4", row=1, col=0),
            GridCell(video_id="V5", row=1, col=1),
        ],
        rows=3,
        cols=3,
    )


def _v1_v2_over_v3():
    return _occ(
        [
            GridCell(video_id="V1", row=0, col=0),
            GridCell(video_id="V2", row=0, col=1),
            GridCell(video_id="V3", row=1, col=0),
        ],
        rows=3,
        cols=3,
    )


def test_insert_left_of_v1_grows_column_keeps_rows_aligned():
    occ = _v1_v2_over_v3()
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.LEFT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "NEW"
    assert occ.id_at(0, 1) == "V1"
    assert occ.id_at(0, 2) == "V2"
    assert occ.id_at(1, 0) is None
    assert occ.id_at(1, 1) == "V3"
    assert occ.id_at(1, 2) is None
    assert occ.displayed_size() == (3, 2)


def test_insert_center_of_v1_grows_column_keeps_rows_aligned():
    occ = _v1_v2_over_v3()
    leftover = occ.drop_on_center(0, 0, ["NEW"])
    assert leftover == []
    assert occ.id_at(0, 0) == "NEW"
    assert occ.id_at(0, 1) == "V1"
    assert occ.id_at(0, 2) == "V2"
    assert occ.id_at(1, 1) == "V3"
    assert occ.displayed_size() == (3, 2)


def test_insert_left_of_v4_pushes_that_row():
    occ = _v1_to_v5_with_row_hole()
    leftover, rejected = occ.drop_on_edge(1, 0, Direction.LEFT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "V1"
    assert occ.id_at(0, 1) == "V2"
    assert occ.id_at(0, 2) == "V3"
    assert occ.id_at(1, 0) == "NEW"
    assert occ.id_at(1, 1) == "V4"
    assert occ.id_at(1, 2) == "V5"
    assert occ.displayed_size() == (3, 2)


def test_insert_center_of_v4_same_as_left():
    occ = _v1_to_v5_with_row_hole()
    leftover = occ.drop_on_center(1, 0, ["NEW"])
    assert leftover == []
    assert occ.id_at(1, 0) == "NEW"
    assert occ.id_at(1, 1) == "V4"
    assert occ.id_at(1, 2) == "V5"
    assert occ.id_at(0, 0) == "V1"


def test_insert_left_of_v5_inserts_between():
    occ = _v1_to_v5_with_row_hole()
    leftover, rejected = occ.drop_on_edge(1, 1, Direction.LEFT, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(1, 0) == "V4"
    assert occ.id_at(1, 1) == "NEW"
    assert occ.id_at(1, 2) == "V5"


def test_insert_below_v4_grows_that_column():
    occ = _v1_to_v5_with_row_hole()
    leftover, rejected = occ.drop_on_edge(1, 0, Direction.DOWN, ["NEW"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(1, 0) == "V4"
    assert occ.id_at(2, 0) == "NEW"
    assert occ.id_at(1, 1) == "V5"
    assert occ.displayed_size() == (3, 3)


def test_drop_left_of_left_edge_inserts_column():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=2, cols=3)
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.LEFT, ["B"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "B"
    assert occ.id_at(0, 1) == "A"


def test_drop_below_grows_row():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=3, cols=3)
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.DOWN, ["B"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 0) == "A"
    assert occ.id_at(1, 0) == "B"
    assert occ.displayed_size() == (1, 2)


def test_drop_right_into_empty_neighbor():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=2, cols=2)
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.RIGHT, ["B"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 1) == "B"


def test_drop_when_full_rejects():
    occ = _occ(rows=2, cols=2)
    occ.pack_flow(["A", "B", "C", "D"])
    before = [c.model_copy() for c in occ.cells]
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.LEFT, ["E"])
    assert rejected
    assert leftover == ["E"]
    assert occ.cells == before


def test_drop_multiple_along_edge_then_empties():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=2, cols=3)
    leftover, rejected = occ.drop_on_edge(0, 0, Direction.RIGHT, ["B", "C"])
    assert not rejected
    assert leftover == []
    assert occ.id_at(0, 1) == "B"
    assert occ.id_at(0, 2) == "C"


def test_place_in_empties_along_down_fills_column_first():
    occ = _occ([GridCell(video_id="A", row=0, col=0)], rows=3, cols=3)
    leftover = occ.place_in_empties(["B", "C"], along=Direction.DOWN, compact=False)
    assert leftover == []
    assert occ.id_at(1, 0) == "B"
    assert occ.id_at(2, 0) == "C"
    assert occ.id_at(0, 1) is None


def test_place_in_empties_default_fills_row_first():
    occ = _occ(
        [GridCell(video_id="A", row=0, col=0)],
        rows=3,
        cols=3,
    )
    leftover = occ.place_in_empties(["B", "C"], compact=False)
    assert leftover == []
    assert occ.id_at(0, 1) == "B"
    assert occ.id_at(0, 2) == "C"


def test_shuffle_keeps_holes():
    occ = _occ(
        [
            GridCell(video_id="A", row=0, col=0),
            GridCell(video_id="B", row=0, col=2),
        ],
        rows=1,
        cols=3,
    )
    occ.shuffle_occupied(["B", "A"])
    assert occ.id_at(0, 0) == "B"
    assert occ.id_at(0, 1) is None
    assert occ.id_at(0, 2) == "A"


def test_swap_videos():
    occ = _occ(rows=1, cols=3)
    occ.pack_flow(["A", "B", "C"])
    occ.swap_videos("A", "C")
    assert [c.video_id for c in occ.cells] == ["C", "B", "A"]


def test_grid_state_cells_json_roundtrip():
    state = GridState(
        mode=GridMode.FIXED,
        is_fit=False,
        size=0,
        rows=2,
        cols=3,
        preallocate=True,
        cells=[GridCell(video_id="abc", row=1, col=2)],
        video_order=["abc"],
    )
    restored = GridState.model_validate_json(state.model_dump_json())
    assert restored.mode is GridMode.FIXED
    assert restored.rows == 2
    assert restored.cols == 3
    assert restored.preallocate is True
    assert restored.cells[0].video_id == "abc"
    assert restored.cells[0].row == 1
    assert restored.cells[0].col == 2
    assert restored.video_order == ["abc"]


def test_grid_state_video_order_default_when_missing():
    restored = GridState.model_validate(
        {
            "mode": GridMode.AUTO_ROWS,
            "is_fit": True,
            "size": 0,
            "rows": 1,
            "cols": 1,
            "preallocate": False,
            "cells": [],
        }
    )
    assert restored.video_order == []
    assert restored.cells == []


def test_compact_edges_trims_leading_empty_column():
    occ = _occ(
        [
            GridCell(video_id="V1", row=0, col=1),
            GridCell(video_id="V2", row=1, col=0),
            GridCell(video_id="V3", row=1, col=1),
        ],
        rows=3,
        cols=3,
        preallocate=False,
    )
    occ.remove_video("V2")
    occ.compact_edges()
    assert occ.id_at(0, 0) == "V1"
    assert occ.id_at(1, 0) == "V3"
    assert occ.id_at(0, 1) is None
    assert occ.displayed_size() == (1, 2)


def test_compact_edges_keeps_interior_holes():
    occ = _occ(
        [
            GridCell(video_id="A", row=0, col=0),
            GridCell(video_id="B", row=0, col=2),
        ],
        rows=3,
        cols=3,
        preallocate=False,
    )
    occ.compact_edges()
    assert occ.id_at(0, 0) == "A"
    assert occ.id_at(0, 1) is None
    assert occ.id_at(0, 2) == "B"
    assert occ.displayed_size() == (3, 1)


def test_compact_edges_noop_when_preallocate():
    occ = _occ(
        [GridCell(video_id="V1", row=0, col=1)],
        rows=3,
        cols=3,
        preallocate=True,
    )
    occ.compact_edges()
    assert occ.id_at(0, 1) == "V1"
    assert occ.displayed_size() == (3, 3)


def test_occupy_moves_existing_id():
    occ = _occ(rows=1, cols=2)
    occ.pack_flow(["A", "B"])
    occ.occupy(0, 1, "A")
    assert occ.id_at(0, 0) is None
    assert occ.id_at(0, 1) == "A"
