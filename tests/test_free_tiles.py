import pytest

from gridplayer.utils.layout.boxes import Box
from gridplayer.utils.layout.free_tiles import (
    MOVE,
    FreeTiles,
    Guide,
    GuideKind,
    Rect,
    TileDrag,
    TilePlace,
)

# a page 1000 by 500 on screen, two to one
W, H = 1000, 500


def _tiles(**rects) -> FreeTiles:
    """Tiles given in the page's pixels."""

    tiles = FreeTiles(page_shape=W / H)
    for video_id, rect in rects.items():
        tiles.set_rect(video_id, Rect(*rect), W, H)
    return tiles


def _drag(tiles, video_id, handle, at, shape=None) -> TileDrag:
    return TileDrag(tiles, video_id, handle, W, H, at, shape)


def _approx(rect, expected):
    assert rect == pytest.approx(expected, abs=0.6)


def test_the_page_keeps_its_shape_in_the_middle_of_the_area():
    tiles = FreeTiles({"a": Box(0, 0, 0.5, 1)}, page_shape=2.0)

    # an area taller than the page: bars above and below
    assert tiles.page_rect(800, 600) == (0, 100, 800, 400)

    ((_, box),) = tiles.boxes(800, 600)
    assert box == pytest.approx((0, 1 / 6, 0.5, 5 / 6))


def test_the_tiles_are_read_row_by_row():
    tiles = _tiles(
        c=(10, 260, 400, 480),
        b=(520, 20, 990, 240),
        a=(10, 30, 500, 250),
        d=(420, 270, 990, 490),
    )

    assert tiles.order() == ["a", "b", "c", "d"]


def test_a_video_added_goes_where_there_is_room():
    tiles = _tiles(a=(0, 0, 500, 500))
    tiles.shape_of = lambda _video_id: 1.0

    assert tiles.add(["b"]) == []

    b = tiles.rects(W, H)["b"]
    # the size the other has, on the free half
    _approx(b, (500, 0, 1000, 500))


def test_a_video_added_to_a_full_page_is_left_over():
    tiles = _tiles(a=(0, 0, 500, 500), b=(500, 0, 1000, 500))

    assert tiles.add(["c"]) == ["c"]
    assert "c" not in tiles.tiles


def test_a_video_dropped_on_another_trades_places_or_takes_its_place():
    tiles = _tiles(a=(0, 0, 400, 500), b=(400, 0, 1000, 500))
    a, b = tiles.tiles["a"], tiles.tiles["b"]

    tiles.drop([], None, None, None, src_id="a", dst_id="b")
    assert (tiles.tiles["a"], tiles.tiles["b"]) == (b, a)

    tiles.drop([], None, None, None, is_replace=True, src_id="a", dst_id="b")
    assert tiles.tiles == {"a": a}


def test_a_tile_moved_goes_with_the_pointer():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", MOVE, (150, 150))

    _approx(drag.moved((250, 300), is_snapping=False), (200, 250, 400, 350))


def test_a_tile_moved_stays_on_the_page():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", MOVE, (150, 150))

    _approx(drag.moved((-500, 2000), is_snapping=False), (0, 400, 200, 500))


def test_a_tile_moved_stops_at_one_in_the_way_and_slides_along_it():
    tiles = _tiles(a=(100, 100, 300, 200), b=(500, 0, 700, 500))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    # right into b, and down: flush against it, gone down as far
    _approx(drag.moved((450, 250), is_snapping=False), (300, 200, 500, 300))


def test_a_tile_moved_past_one_in_the_way_jumps_there():
    tiles = _tiles(a=(100, 100, 300, 200), b=(350, 0, 450, 500))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    _approx(drag.moved((700, 150), is_snapping=False), (600, 100, 800, 200))


def test_a_tile_moved_near_an_edge_snaps_to_it_and_shows_it():
    tiles = _tiles(a=(100, 100, 300, 200), b=(600, 300, 800, 450))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    # its right edge 6 px short of b's left, its top 5 below the page's...
    _approx(drag.moved((494, 55)), (400, 0, 600, 100))
    guides = drag.guides()
    # b's left edge, a's right one there with no tile beside it
    assert Guide(True, 600, 0, 450, GuideKind.EDGES) in guides
    assert Guide(False, 0, 0, W, GuideKind.PAGE_EDGE) in guides
    # its middle at the page's
    assert Guide(True, 500, 0, H, GuideKind.CENTERED) in guides

    # ...not with Alt
    _approx(drag.moved((494, 55), is_snapping=False), (394, 5, 594, 105))


def test_a_tile_sized_by_its_side_keeps_its_shape():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", (1, 0), (300, 150), shape=2.0)

    # twice as wide: twice as tall, as much above as below
    _approx(drag.moved((500, 150), is_snapping=False), (100, 50, 500, 250))


def test_a_tile_sized_by_a_corner_follows_the_pointer_further_way():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", (1, 1), (300, 200), shape=2.0)

    _approx(drag.moved((340, 300), is_snapping=False), (100, 100, 500, 300))


def test_a_tile_sized_by_a_corner_into_a_tile_beside_stops_at_it():
    tiles = _tiles(a=(100, 100, 300, 200), b=(310, 0, 500, 500))
    drag = _drag(tiles, "a", (1, 1), (300, 200), shape=2.0)

    # its right edge against b, its top left corner where it was
    _approx(drag.moved((400, 240), is_snapping=False), (100, 100, 310, 205))
    _approx(drag.moved((420, 250), is_snapping=False), (100, 100, 310, 205))
    # back off b: as before
    _approx(drag.moved((280, 180), is_snapping=False), (100, 100, 280, 190))


def test_a_tile_sized_by_a_corner_with_no_room_stays_as_it_is():
    # tight on c, its bottom can go no further
    tiles = _tiles(a=(100, 300, 300, 400), c=(0, 400, 1000, 500))
    drag = _drag(tiles, "a", (1, 1), (300, 400), shape=2.0)

    _approx(drag.moved((400, 450), is_snapping=False), (100, 300, 300, 400))


def test_a_tile_sized_by_a_corner_stops_at_the_pages_edge():
    tiles = _tiles(a=(700, 100, 900, 200))
    drag = _drag(tiles, "a", (1, 1), (900, 200), shape=2.0)

    _approx(drag.moved((1100, 250), is_snapping=False), (700, 100, 1000, 250))
    _approx(drag.moved((1100, 300), is_snapping=False), (700, 100, 1000, 250))


def test_a_tile_sized_by_a_corner_from_the_top_left_holds_the_bottom_right():
    tiles = _tiles(a=(300, 200, 500, 300), b=(0, 0, 150, 500))
    drag = _drag(tiles, "a", (-1, -1), (300, 200), shape=2.0)

    _approx(drag.moved((100, 0), is_snapping=False), (150, 125, 500, 300))


def test_a_tile_going_over_others_sized_by_a_corner_stops_at_the_page():
    tiles = _tiles(a=(100, 100, 300, 200), b=(310, 0, 500, 500))
    drag = TileDrag(tiles, "a", (1, 1), W, H, (300, 200), 2.0, is_over=True)

    _approx(drag.moved((420, 250), is_snapping=False), (100, 100, 420, 260))
    _approx(drag.moved((900, 900), is_snapping=False), (100, 100, 900, 500))


def test_a_tile_sized_by_a_corner_to_any_shape_slides_along_one_in_the_way():
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 0, 600, 150))
    drag = _drag(tiles, "a", (1, 1), (300, 200), shape=2.0)

    # the right edge into b the least: stopped at it, the bottom on
    rect = drag.moved((500, 300), is_snapping=False, keeps_shape=False)
    _approx(rect, (100, 100, 400, 300))


def test_a_tile_sized_with_shift_takes_any_shape():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", (1, 1), (300, 200), shape=2.0)

    rect = drag.moved((340, 300), is_snapping=False, keeps_shape=False)
    _approx(rect, (100, 100, 340, 300))


def test_a_tile_sized_keeps_its_own_shape_with_no_jump():
    # made a grid's cell, wider than its video
    tiles = _tiles(a=(100, 100, 400, 200))
    drag = _drag(tiles, "a", (0, 1), (250, 200), shape=1.0)

    _approx(drag.moved((250, 200)), (100, 100, 400, 200))
    _approx(drag.moved((250, 250), is_snapping=False), (25, 100, 475, 250))


def test_a_tile_sized_with_shift_snaps_to_its_videos_shape():
    tiles = _tiles(a=(100, 100, 400, 200))
    drag = _drag(tiles, "a", (1, 0), (400, 150), shape=2.0)

    # 6 px short of where the picture fits it with no bars
    _approx(drag.moved((306, 150), keeps_shape=False), (100, 100, 300, 200))
    assert drag.fits

    _approx(drag.moved((330, 150), keeps_shape=False), (100, 100, 330, 200))
    assert not drag.fits


def test_a_tile_against_another_sized_by_its_side_grows_away_from_it():
    tiles = _tiles(up=(100, 0, 400, 150), a=(100, 150, 400, 300))
    drag = _drag(tiles, "a", (1, 0), (400, 225))

    # half up and half down would take it into the one above
    _approx(drag.moved((460, 225), is_snapping=False), (100, 150, 460, 330))


def test_a_tile_with_no_room_to_be_sized_stays_as_it_was():
    tiles = _tiles(
        up=(100, 0, 400, 150), a=(100, 150, 400, 300), down=(100, 300, 400, 450)
    )
    drag = _drag(tiles, "a", (1, 0), (400, 225))

    _approx(drag.moved((460, 225), is_snapping=False), (100, 150, 400, 300))


def test_a_tile_over_another_is_kept_apart_once_moved_clear_of_it():
    tiles = _tiles(a=(100, 100, 300, 200), b=(250, 150, 450, 250))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    # over b to start with: moved as it likes
    _approx(drag.moved((190, 150), is_snapping=False), (90, 100, 290, 200))
    # clear of it, and from then on not over it again
    _approx(drag.moved((100, 50), is_snapping=False), (0, 0, 200, 100))
    _approx(drag.moved((200, 200), is_snapping=False), (100, 50, 300, 150))


def test_a_tile_sized_stops_at_one_in_the_way():
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 0, 600, 500))
    drag = _drag(tiles, "a", (1, 1), (300, 200), shape=2.0)

    # against b
    _approx(drag.moved((700, 400), is_snapping=False), (100, 100, 400, 250))


def test_a_tile_sized_stops_at_the_page_edge():
    tiles = _tiles(a=(100, 300, 300, 400))
    drag = _drag(tiles, "a", (1, 1), (300, 400), shape=2.0)

    # on the page's bottom, as wide as that makes it
    _approx(drag.moved((900, 900), is_snapping=False), (100, 300, 500, 500))


def test_a_tile_is_never_made_too_small():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", (1, 0), (300, 150), shape=2.0)

    rect = drag.moved((0, 150), is_snapping=False)
    assert rect.width == pytest.approx(96)
    assert rect.height == pytest.approx(48)


def test_an_edge_stretched_goes_to_the_next_tile_or_the_page_edge():
    tiles = _tiles(a=(100, 100, 300, 200), b=(500, 0, 700, 500))

    _approx(_drag(tiles, "a", (1, 0), (300, 150)).stretched(), (100, 100, 500, 200))
    _approx(_drag(tiles, "a", (0, -1), (200, 100)).stretched(), (100, 0, 300, 200))


def test_what_is_at_a_point_of_a_tile():
    tiles = _tiles(a=(100, 100, 300, 200), b=(300, 100, 500, 200))

    assert tiles.handle_at(200, 150, W, H) == ("a", MOVE)
    assert tiles.handle_at(102, 150, W, H) == ("a", (-1, 0))
    assert tiles.handle_at(298, 198, W, H) == ("a", (1, 1))
    # just outside a tile's edge still takes it
    assert tiles.handle_at(200, 97, W, H) == ("a", (0, -1))
    # where two meet, the one the pointer is in
    assert tiles.handle_at(302, 150, W, H) == ("b", (-1, 0))
    assert tiles.handle_at(700, 400, W, H) is None


def test_what_a_tile_is_in_line_with_in_words():
    from gridplayer.widgets.grid_line_mark import tile_snap_words

    def guide(kind):
        return Guide(True, 0, 0, 1, kind)

    assert tile_snap_words([]) == ""
    edges = guide(GuideKind.EDGES)
    assert tile_snap_words([edges, edges]) == "Edges lined up"
    assert (
        tile_snap_words([guide(GuideKind.TOUCHING), guide(GuideKind.PAGE_EDGE)])
        == "Page edge, Touching"
    )
    assert tile_snap_words([guide(GuideKind.MIDDLES)]) == "Middles lined up"
    assert tile_snap_words([guide(GuideKind.CENTERED)]) == "Centered"
    assert tile_snap_words([edges], fits=True) == "Fits, Edges lined up"
    assert tile_snap_words([guide(GuideKind.START)]) == "Old edge"
    assert tile_snap_words([guide(GuideKind.PAGE_MIDDLE)]) == "Page middle"


def test_a_tile_beside_another_is_touching_it_else_lined_up():
    tiles = _tiles(a=(100, 100, 300, 200), b=(300, 150, 500, 250), c=(0, 300, 100, 400))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    drag.moved((200, 150))
    guides = drag.guides()

    # its right edge on b's left, b beside it
    assert Guide(True, 300, 100, 250, GuideKind.TOUCHING) in guides
    # its left edge on c's right, c below it, and its top on b's middle
    assert Guide(True, 100, 100, 400, GuideKind.EDGES) in guides
    assert not any(guide.position == 200 for guide in guides if not guide.is_column)


def test_tiles_with_their_middles_in_line_are_shown_so():
    tiles = _tiles(a=(100, 100, 300, 200), b=(150, 300, 250, 400))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    drag.moved((200, 150))

    assert Guide(True, 200, 100, 400, GuideKind.MIDDLES) in drag.guides()


def test_an_edge_at_the_pages_middle_is_not_the_tile_centered():
    tiles = _tiles(a=(100, 300, 300, 400))
    drag = _drag(tiles, "a", MOVE, (200, 350))

    drag.moved((200, 303))

    assert Guide(False, 250, 0, W, GuideKind.PAGE_MIDDLE) in drag.guides()


def test_tiles_are_kept_back_to_front_and_put_in_front_or_behind():
    tiles = _tiles(a=(0, 0, 300, 200), b=(200, 100, 500, 300), c=(700, 0, 900, 100))

    assert tiles.is_under("a")
    assert not tiles.is_under("b")
    assert tiles.is_over("b")
    # c is over nothing, nor under anything
    assert not tiles.is_under("c")
    assert not tiles.is_over("c")
    assert tiles.is_stacked()

    tiles.stack("a", is_front=True)
    assert list(tiles.tiles) == ["b", "c", "a"]
    tiles.stack("a", is_front=False)
    assert list(tiles.tiles) == ["a", "b", "c"]


def test_tiles_side_by_side_are_not_one_over_another():
    tiles = _tiles(a=(0, 0, 300, 200), b=(300, 0, 600, 200))

    assert not tiles.is_stacked()


def test_the_tile_in_front_is_the_one_pointed_at():
    tiles = _tiles(a=(0, 0, 300, 200), b=(200, 100, 500, 300))

    assert tiles.handle_at(250, 150, W, H) == ("b", MOVE)
    tiles.stack("a", is_front=True)
    assert tiles.handle_at(250, 150, W, H) == ("a", MOVE)
    # b's edge, under a: a's to move
    assert tiles.handle_at(201, 150, W, H) == ("a", MOVE)


def test_a_tile_put_back_where_another_is_now_is_not():
    tiles = _tiles(a=(0, 0, 300, 200), b=(290, 0, 600, 200))
    place = TilePlace(tiles.tiles.pop("a"), 0)

    tiles.tiles["b"] = Box(0.25, 0, 0.6, 0.4)
    assert not tiles.put_back("a", place)
    # unless tiles go over each other
    assert tiles.put_back("a", place, is_over=True)
    assert list(tiles.tiles) == ["a", "b"]


def test_a_tile_going_over_others_goes_where_the_pointer_takes_it():
    tiles = _tiles(a=(100, 100, 300, 200), b=(350, 0, 450, 500))
    drag = TileDrag(tiles, "a", MOVE, W, H, (200, 150), is_over=True)

    _approx(drag.moved((450, 150), is_snapping=False), (350, 100, 550, 200))

    # sized: over it too
    tiles = _tiles(a=(100, 100, 300, 200), b=(310, 0, 500, 500))
    drag = TileDrag(tiles, "a", (1, 1), W, H, (300, 200), 2.0, is_over=True)
    _approx(drag.moved((400, 250), is_snapping=False), (100, 100, 400, 250))


def test_tiles_fitted_to_the_page_grow_together_in_the_middle():
    tiles = _tiles(a=(100, 100, 300, 200), b=(300, 100, 500, 200))

    tiles.fit_to_page()

    # 400 by 100 together: 2.5 times as big, as wide as the page
    rects = tiles.rects(W, H)
    _approx(rects["a"], (0, 125, 500, 375))
    _approx(rects["b"], (500, 125, 1000, 375))


def test_a_tile_sized_by_its_side_stops_at_the_page_rather_than_move():
    tiles = _tiles(a=(100, 20, 300, 120))
    drag = _drag(tiles, "a", (1, 0), (300, 70), shape=2.0)

    # half up and half down, until its top is on the page's
    _approx(drag.moved((500, 70), is_snapping=False), (100, 0, 380, 140))


def test_an_edge_sized_snaps_back_to_where_it_started():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", (1, 0), (300, 150))

    # not before it has been away from there
    _approx(drag.moved((305, 150), keeps_shape=False), (100, 100, 305, 200))
    assert not [g for g in drag.guides() if g.kind is GuideKind.START]

    drag.moved((400, 150), keeps_shape=False)
    _approx(drag.moved((305, 150), keeps_shape=False), (100, 100, 300, 200))
    assert Guide(True, 300, 100, 200, GuideKind.START) in drag.guides()


def test_a_tile_moved_stays_in_line_with_where_it_started():
    tiles = _tiles(a=(100, 100, 300, 200))
    drag = _drag(tiles, "a", MOVE, (200, 150))

    def said():
        guides = [g for g in drag.guides() if g.kind is GuideKind.START]
        return {(g.is_column, g.position) for g in guides}

    # down, a little to the side: kept in its column, said only once it
    # has been out of it
    _approx(drag.moved((205, 350)), (100, 300, 300, 400))
    assert said() == set()
    drag.moved((400, 350))
    _approx(drag.moved((205, 350)), (100, 300, 300, 400))
    assert said() == {(True, 100), (True, 300)}
