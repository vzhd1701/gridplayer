from gridplayer.params.static import GridMode
from gridplayer.player.managers.video_blocks import VideoBlocks
from gridplayer.utils.drop_zone import (
    DropIndicator,
    DropZone,
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


def test_video_blocks_move_reorders_and_is_noop_on_self():
    blocks = VideoBlocks()
    a, b, c, d = "A", "B", "C", "D"
    for item in (a, b, c, d):
        blocks.append(item)

    blocks.move(c, 0)
    assert list(blocks) == [c, a, b, d]

    blocks.move(c, 1)
    assert list(blocks) == [c, a, b, d]

    blocks.move(c, 4)
    assert list(blocks) == [a, b, d, c]

    blocks.move(c, 4)
    assert list(blocks) == [a, b, d, c]

    blocks.move(a, 2)
    assert list(blocks) == [b, a, d, c]
