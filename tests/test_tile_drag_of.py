"""What a tile's drag goes by, as Free Tiles makes it (tile_drag_of): in
Mosaic, of the others only the locked tiles, which stay where they
are while the rest make room for it."""

from types import SimpleNamespace

import pytest

from gridplayer.params.static import GridMode, TileOverlap, TileSnap
from gridplayer.player.managers.free_tiles import FreeTilesManager
from gridplayer.utils.layout.boxes import Box
from gridplayer.utils.layout.free_tiles import MOVE, FreeTiles, Rect

WIDTH, HEIGHT = 1000, 500


def _drag_of(is_mosaic, overlap=TileOverlap.OFF):
    tiles = FreeTiles(
        {
            "A": Box(0.0, 0.0, 0.3, 0.4),
            "B": Box(0.4, 0.0, 0.6, 0.4),
            "C": Box(0.5, 0.6, 0.8, 1.0),
        },
        WIDTH / HEIGHT,
        {"C"},
    )
    manager = SimpleNamespace(
        _ctx=SimpleNamespace(
            commands=SimpleNamespace(
                tile_overlap=lambda: overlap,
                is_grid_mode_set_to=lambda mode: is_mosaic and mode == GridMode.MOSAIC,
            )
        ),
        tile_snaps=lambda: frozenset({TileSnap.TILE_EDGES}),
        _shape_of=lambda _video_id: 16 / 9,
    )
    return FreeTilesManager.tile_drag_of(
        manager, tiles, "A", MOVE, WIDTH, HEIGHT, (150, 100)
    )


def test_in_mosaic_only_the_locked_tiles_are_there():
    drag = _drag_of(is_mosaic=True)

    assert drag.others == [Rect(500, 300, 800, 500)]
    # over the others, which make room for it
    assert drag.is_over


def test_in_free_tiles_all_the_others_are():
    drag = _drag_of(is_mosaic=False)

    assert len(drag.others) == 2
    assert not drag.is_over


def test_in_mosaic_it_snaps_to_a_locked_tile_not_to_the_others():
    # A's right edge 2 px off B's left edge, then off locked C's
    near_b = _drag_of(is_mosaic=True).moved((150 + 102, 100))
    near_c = _drag_of(is_mosaic=True).moved((150 + 202, 100))

    assert near_b.right == pytest.approx(402)
    assert near_c.right == pytest.approx(500)


def test_in_free_tiles_it_snaps_to_any():
    near_b = _drag_of(is_mosaic=False, overlap=TileOverlap.ON).moved((150 + 102, 100))

    assert near_b.right == pytest.approx(400)
