from types import SimpleNamespace

from gridplayer.models.media_list import ListSource, MediaList
from gridplayer.params.static import GridMode, ListSourceKind
from gridplayer.utils.drop_zone import (
    DropIndicator,
    DropZone,
    adds_to_list,
    indicator_for,
    insert_index,
    zone_at,
)


def test_zone_at_rows_first_splits_by_x():
    w, h = 300, 90
    assert zone_at(0, 45, w, h, GridMode.AUTO_ROWS) == DropZone.BEFORE
    assert zone_at(99, 45, w, h, GridMode.AUTO_ROWS) == DropZone.BEFORE
    assert zone_at(150, 45, w, h, GridMode.AUTO_ROWS) == DropZone.CENTER
    assert zone_at(201, 45, w, h, GridMode.AUTO_ROWS) == DropZone.AFTER
    assert zone_at(299, 0, w, h, GridMode.AUTO_ROWS) == DropZone.AFTER


def test_zone_at_columns_first_splits_by_y():
    w, h = 90, 300
    assert zone_at(45, 0, w, h, GridMode.AUTO_COLS) == DropZone.BEFORE
    assert zone_at(45, 99, w, h, GridMode.AUTO_COLS) == DropZone.BEFORE
    assert zone_at(45, 150, w, h, GridMode.AUTO_COLS) == DropZone.CENTER
    assert zone_at(45, 201, w, h, GridMode.AUTO_COLS) == DropZone.AFTER


def test_zone_at_outside_and_invalid_size():
    assert zone_at(-1, 10, 100, 100, GridMode.AUTO_ROWS) is None
    assert zone_at(10, 101, 100, 100, GridMode.AUTO_ROWS) is None
    assert zone_at(10, 10, 0, 100, GridMode.AUTO_ROWS) is None


def test_insert_index():
    assert insert_index(2, DropZone.BEFORE) == 2
    assert insert_index(2, DropZone.CENTER) == 2
    assert insert_index(2, DropZone.AFTER) == 3


def test_zone_at_fixed_five_region():
    w, h = 200, 200
    assert zone_at(100, 100, w, h, GridMode.FIXED) == DropZone.CENTER
    assert zone_at(10, 100, w, h, GridMode.FIXED) == DropZone.BEFORE
    assert zone_at(190, 100, w, h, GridMode.FIXED) == DropZone.AFTER
    assert zone_at(100, 10, w, h, GridMode.FIXED) == DropZone.ABOVE
    assert zone_at(100, 190, w, h, GridMode.FIXED) == DropZone.BELOW


def test_indicator_for_fixed_uses_cardinal_arrows():
    assert (
        indicator_for(DropZone.BEFORE, False, GridMode.FIXED)
        is DropIndicator.ARROW_LEFT
    )
    assert (
        indicator_for(DropZone.AFTER, False, GridMode.FIXED)
        is DropIndicator.ARROW_RIGHT
    )
    assert (
        indicator_for(DropZone.ABOVE, False, GridMode.FIXED) is DropIndicator.ARROW_UP
    )
    assert (
        indicator_for(DropZone.BELOW, False, GridMode.FIXED) is DropIndicator.ARROW_DOWN
    )


def test_indicator_for():
    rows = GridMode.AUTO_ROWS
    cols = GridMode.AUTO_COLS
    assert indicator_for(None, True, rows) is DropIndicator.NONE
    assert indicator_for(DropZone.BEFORE, False, rows) is DropIndicator.ARROW_LEFT
    assert indicator_for(DropZone.AFTER, False, rows) is DropIndicator.ARROW_RIGHT
    assert indicator_for(DropZone.BEFORE, False, cols) is DropIndicator.ARROW_UP
    assert indicator_for(DropZone.AFTER, False, cols) is DropIndicator.ARROW_DOWN
    assert indicator_for(DropZone.CENTER, True, rows) is DropIndicator.SWAP
    assert indicator_for(DropZone.CENTER, False, rows) is DropIndicator.DOT
    assert (
        indicator_for(DropZone.BEFORE, False, rows, is_replace=True)
        is DropIndicator.REPLACE
    )
    assert (
        indicator_for(DropZone.CENTER, True, rows, is_replace=True)
        is DropIndicator.REPLACE
    )


def _list_cell(**fields):
    return SimpleNamespace(media_list=MediaList(**fields))


def test_adds_to_list_only_in_the_middle_of_a_cell_playing_one():
    cell = _list_cell()

    assert adds_to_list(cell, DropZone.CENTER, False)
    for zone in (DropZone.BEFORE, DropZone.AFTER, DropZone.ABOVE, DropZone.BELOW):
        assert not adds_to_list(cell, zone, False)
    assert not adds_to_list(cell, None, False)


def test_adds_to_list_not_to_replace_its_video():
    assert not adds_to_list(_list_cell(), DropZone.CENTER, True)


def test_adds_to_list_not_to_a_cell_with_no_list_or_none():
    assert not adds_to_list(SimpleNamespace(media_list=None), DropZone.CENTER, False)
    assert not adds_to_list(SimpleNamespace(), DropZone.CENTER, False)
    assert not adds_to_list(None, DropZone.CENTER, False)


def test_adds_to_list_not_to_a_linked_list_or_a_closing_cell():
    linked = _list_cell(
        source=ListSource(kind=ListSourceKind.URL, location="http://tv/l"),
        is_linked=True,
    )
    closing = SimpleNamespace(media_list=MediaList(), is_closing=True)

    assert not adds_to_list(linked, DropZone.CENTER, False)
    assert not adds_to_list(closing, DropZone.CENTER, False)


def test_indicator_for_adding_to_a_list():
    mode = GridMode.AUTO_ROWS

    assert (
        indicator_for(DropZone.CENTER, False, mode, is_add_to_list=True)
        == DropIndicator.ADD_TO_LIST
    )
    # replacing wins, and an edge stays an edge
    assert (
        indicator_for(DropZone.CENTER, False, mode, True, is_add_to_list=True)
        == DropIndicator.REPLACE
    )
    assert (
        indicator_for(DropZone.AFTER, False, mode, is_add_to_list=True)
        == DropIndicator.ARROW_RIGHT
    )
