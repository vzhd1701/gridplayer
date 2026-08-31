from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import FlowLayout, FlowMode


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
