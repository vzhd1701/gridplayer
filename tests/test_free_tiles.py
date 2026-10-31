import pytest

from gridplayer.models.tile_snaps import TileSnaps
from gridplayer.params.static import TileResize, TileSnap
from gridplayer.utils.layout.boxes import Box
from gridplayer.utils.layout.free_tiles import (
    MOVE,
    FreeTiles,
    Gap,
    Guide,
    GuideKind,
    Rect,
    TileDrag,
    TilePlace,
)
from gridplayer.widgets.grid_line_mark import guides_clear_of

# a page 1000 by 500 on screen, two to one
W, H = 1000, 500


def _tiles(**rects) -> FreeTiles:
    """Tiles given in the page's pixels, as placed on it."""

    tiles = FreeTiles(page_shape=W / H, page_height=H, is_as_placed=True)
    for video_id, rect in rects.items():
        tiles.set_rect(video_id, Rect(*rect), W, H)
    return tiles


# every snap, the gaps too; and all but the gaps, as by default
_ALL = frozenset(TileSnap)
_SNAPS = _ALL - {TileSnap.EQUAL_GAPS}


def _drag(tiles, video_id, handle, at, shape=None, snaps=_SNAPS, **kwargs) -> TileDrag:
    return TileDrag(tiles, video_id, handle, W, H, at, shape, snaps=snaps, **kwargs)


def _approx(rect, expected):
    assert rect == pytest.approx(expected, abs=0.6)


def _kept(**rects) -> FreeTiles:
    """Tiles given in the pixels of a page W by H, their sizes kept."""

    tiles = _resized(**rects)
    tiles.resize = TileResize.KEEP
    return tiles


def _resized(**rects) -> FreeTiles:
    """Tiles given in the pixels of a page W by H, the window resized since
    they were placed."""

    tiles = _tiles(**rects)
    tiles.is_as_placed = False
    return tiles


def _shown(tiles, width, height) -> dict[str, tuple]:
    """The tiles in the pixels of an area of this size."""

    return {
        video_id: (b.left * width, b.top * height, b.right * width, b.bottom * height)
        for video_id, b in tiles.boxes(width, height)
    }


def test_tiles_keep_their_sizes_as_the_window_is_resized_around_them():
    tiles = _kept(a=(0, 0, 300, 200), b=(300, 0, 600, 200))

    # as big, in the middle of the room around them
    for width, height in ((800, 400), (600, 200), (1600, 900)):
        x, y = (width - 600) / 2, (height - 200) / 2
        shown = _shown(tiles, width, height)
        _approx(shown["a"], (x, y, x + 300, y + 200))
        _approx(shown["b"], (x + 300, y, x + 600, y + 200))


def test_tiles_with_one_against_an_edge_stay_in_the_middle():
    # b moved against the right edge, a not
    tiles = _kept(a=(100, 0, 400, 200), b=(700, 0, 1000, 200))

    shown = _shown(tiles, 1200, 500)
    _approx(shown["a"], (150, 150, 450, 350))
    _approx(shown["b"], (750, 150, 1050, 350))


def test_tiles_kept_shrink_only_to_fit_and_grow_back_no_bigger():
    tiles = _kept(a=(0, 0, 500, 250), b=(500, 250, 1000, 500))

    # half as wide: half as big, in the middle of the room above and below
    shown = _shown(tiles, 500, 500)
    _approx(shown["a"], (0, 125, 250, 250))
    _approx(shown["b"], (250, 250, 500, 375))

    # bigger than they were made: as big as that, in the middle
    shown = _shown(tiles, 2000, 1000)
    _approx(shown["a"], (500, 250, 1000, 500))
    _approx(shown["b"], (1000, 500, 1500, 750))

    _approx(_shown(tiles, W, H)["a"], (0, 0, 500, 250))


def test_tiles_scaled_to_fit_fill_the_window_together():
    tiles = _resized(a=(100, 100, 300, 200), b=(300, 200, 500, 300))

    shown = _shown(tiles, W, H)
    _approx(shown["a"], (0, 0, 500, 250))
    _approx(shown["b"], (500, 250, 1000, 500))

    # wider: as high as it, in the middle
    shown = _shown(tiles, 2000, 500)
    _approx(shown["a"], (500, 0, 1000, 250))
    _approx(shown["b"], (1000, 250, 1500, 500))


def test_tiles_placed_are_shown_as_placed_until_the_window_is_resized():
    tiles = _resized(a=(100, 100, 300, 200))
    tiles.fill(W, H)
    _approx(_shown(tiles, W, H)["a"], (0, 0, 1000, 500))

    # placed again where it leaves room around it: not fitted under the
    # pointer
    tiles.set_rect("a", Rect(100, 100, 300, 200), W, H)
    _approx(_shown(tiles, W, H)["a"], (100, 100, 300, 200))
    _approx(_shown(tiles, 800, 400)["a"], (0, 0, 800, 400))

    # resized, then back: fitted, with no flicker back as it was placed
    tiles.resized_to(800, 400)
    _approx(_shown(tiles, W, H)["a"], (0, 0, 1000, 500))


def test_tiles_of_unknown_size_fit_or_keep_their_size_on_the_page():
    # as in a playlist saved before the tiles' size was
    tiles = _resized(a=(100, 100, 300, 200))
    tiles.page_height = None

    _approx(_shown(tiles, W, H)["a"], (0, 0, 1000, 500))

    # as big as on a page as big as the area allows, in the middle
    tiles.resize = TileResize.KEEP
    _approx(_shown(tiles, 2000, 1000)["a"], (800, 400, 1200, 600))
    _approx(_shown(tiles, 800, 600)["a"], (320, 260, 480, 340))


def test_tiles_kept_where_they_are_shown_when_the_page_takes_the_area():
    tiles = _kept(a=(300, 100, 500, 200), b=(500, 200, 900, 400))
    before = _shown(tiles, 600, 300)

    tiles.fill(600, 300)

    assert tiles.page_height == 300
    shown = _shown(tiles, 600, 300)
    for video_id, rect in before.items():
        _approx(shown[video_id], rect)


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
    drag = _drag(tiles, "a", (1, 1), (300, 200), 2.0, is_over=True)

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
    assert tile_snap_words([edges], has_gaps=True) == "Same gap, Edges lined up"


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


def test_tiles_closed_together_go_back_beside_those_left_wherever_they_are():
    tiles = _tiles(a=(0, 0, 300, 200), b=(300, 0, 600, 200), c=(600, 0, 900, 200))
    places = {i: tiles.place_of(i, W, H) for i in ("b", "c")}
    tiles.remove("b")
    tiles.remove("c")
    # a fitted to another window, and back to this one
    tiles.fill(500, 500)
    tiles.fill(W, H)
    _approx(_shown(tiles, W, H)["a"], (125, 0, 875, 500))

    for video_id in ("b", "c"):
        assert tiles.put_back(video_id, places[video_id])

    # as they were among themselves, fitted to the window together
    shown = _shown(tiles, W, H)
    _approx(shown["a"], (0, 138.9, 333.3, 361.1))
    _approx(shown["b"], (333.3, 138.9, 666.7, 361.1))
    _approx(shown["c"], (666.7, 138.9, 1000, 361.1))


def test_a_tile_going_over_others_goes_where_the_pointer_takes_it():
    tiles = _tiles(a=(100, 100, 300, 200), b=(350, 0, 450, 500))
    drag = _drag(tiles, "a", MOVE, (200, 150), is_over=True)

    _approx(drag.moved((450, 150), is_snapping=False), (350, 100, 550, 200))

    # sized: over it too
    tiles = _tiles(a=(100, 100, 300, 200), b=(310, 0, 500, 500))
    drag = _drag(tiles, "a", (1, 1), (300, 200), 2.0, is_over=True)
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


def _pushing(tiles, video_id, handle, at, shape=None) -> TileDrag:
    return _drag(tiles, video_id, handle, at, shape, is_pushing=True)


def test_a_tile_pushing_makes_the_one_it_goes_over_smaller_in_its_place():
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 100, 600, 200))
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    _approx(drag.moved((350, 150), is_snapping=False), (250, 100, 450, 200))
    # its shape kept, in what is left of its place, away from a
    _approx(drag.pushed["b"], (450, 112.5, 600, 187.5))


def test_a_tile_pushed_comes_back_as_the_one_pushing_goes_away():
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 100, 600, 200))
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    drag.moved((350, 150), is_snapping=False)
    drag.moved((200, 150), is_snapping=False)

    _approx(drag.pushed["b"], (400, 100, 600, 200))


def test_a_tile_pushed_over_a_corner_shrinks_toward_the_corner_across():
    tiles = _tiles(a=(100, 300, 300, 400), b=(400, 100, 600, 200))
    drag = _pushing(tiles, "a", MOVE, (200, 350))

    # over its bottom right corner: as big beside a as above it
    _approx(drag.moved((640, 220), is_snapping=False), (540, 170, 740, 270))
    _approx(drag.pushed["b"], (400, 100, 540, 170))

    # less of it down: bigger above a, still in its top left corner
    drag.moved((640, 230), is_snapping=False)
    _approx(drag.pushed["b"], (400, 100, 560, 180))

    # less of it across: bigger beside a, the same
    drag.moved((660, 220), is_snapping=False)
    _approx(drag.pushed["b"], (400, 100, 560, 180))


def test_a_tile_pushed_with_too_little_left_goes_where_there_is_room():
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 100, 600, 200))
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    a = drag.moved((450, 150), is_snapping=False)
    b = drag.pushed["b"]

    # as big as it was, clear of a, out of its place
    assert b.width == pytest.approx(200)
    assert b.height == pytest.approx(100)
    assert not b.overlaps(a)
    assert b.right <= 400 or b.left >= 600 or b.bottom <= 100 or b.top >= 200


def test_a_tile_pushed_where_there_was_little_room_grows_back_as_room_is_made():
    tiles = _tiles(
        a=(0, 0, 300, 250),
        b=(350, 0, 650, 250),
        c=(0, 260, 1000, 500),
        d=(700, 0, 1000, 250),
    )
    drag = _pushing(tiles, "a", MOVE, (150, 125))

    # out of its place, into what a leaves of its own: smaller
    drag.moved((375, 125), is_snapping=False)
    _approx(drag.pushed["b"], (0, 31.25, 225, 218.75))

    # a going on: b as big as it was again, in the place a left
    drag.moved((400, 125), is_snapping=False)
    _approx(drag.pushed["b"], (0, 20.8, 250, 229.2))
    drag.moved((500, 125), is_snapping=False)
    _approx(drag.pushed["b"], (0, 0, 300, 250))


def test_two_tiles_stacked_swap_places_pushing():
    tiles = _tiles(big=(300, 0, 700, 225), small=(400, 280, 600, 392))
    drag = _pushing(tiles, "small", MOVE, (500, 336))

    # pushed up into big: big smaller in its place, above it
    drag.moved((500, 236), is_snapping=False)
    _approx(drag.pushed["big"], (340, 0, 660, 180))

    # through it: big in the place small left, as big as it was, and kept
    # there with room for it in its own place again
    drag.moved((500, 156), is_snapping=False)
    _approx(drag.pushed["big"], (300, 224, 700, 448))
    _approx(drag.moved((500, 36), is_snapping=False), (400, 0, 600, 112))
    _approx(drag.pushed["big"], (300, 224, 700, 448))

    # back down again: big back where it was
    drag.moved((500, 336), is_snapping=False)
    _approx(drag.pushed["big"], (300, 0, 700, 225))


def test_a_tile_pushed_out_grows_into_room_one_set_aside_after_it_left():
    # a full 16:9 page, three tiles high in columns; "one" dragged into
    # "two"'s place, "two" going to one's, k above it set aside by one too,
    # but after two has gone
    width, height = 1920, 1080
    tiles = FreeTiles(page_shape=width / height)
    for video_id, rect in {
        "a": (0, 0, 276, 359),
        "b": (0, 359, 276, 721),
        "c": (0, 721, 276, 1080),
        "d": (276, 0, 719, 248),
        "e": (276, 248, 719, 503),
        "f": (276, 503, 719, 1080),
        "g": (720, 0, 1062, 447),
        "two": (720, 447, 1062, 885),
        "i": (719, 885, 1063, 1080),
        "j": (1063, 0, 1477, 232),
        "k": (1063, 232, 1477, 779),
        "one": (1063, 779, 1477, 1080),
        "m": (1478, 0, 1920, 578),
        "n": (1477, 578, 1920, 832),
        "o": (1477, 832, 1920, 1080),
    }.items():
        tiles.set_rect(video_id, Rect(*rect), width, height)
    drag = TileDrag(
        tiles, "one", MOVE, width, height, (1270, 930), snaps=_SNAPS, is_pushing=True
    )

    for step in range(1, 41):
        one = drag.moved(
            (1270 - 374 * step / 40, 930 - 369 * step / 40), is_snapping=False
        )
    two, k = drag.pushed["two"], drag.pushed["k"]

    # up against k as k ends up, not where k was, the outline's top
    assert k.bottom < 779 - 30
    assert two.top == pytest.approx(k.bottom)
    assert not two.overlaps(one)
    assert not two.overlaps(k)


def test_a_small_tile_pushed_goes_elsewhere_before_it_is_too_small():
    # b too low to be made half as big: 48 high at most, with 80
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 100, 542, 180))
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    # a follows the pointer all the way through b, never held up
    for x in range(200, 460, 2):
        _approx(drag.moved((x, 150), is_snapping=False), (x - 100, 100, x + 100, 200))
        b = drag.pushed.get("b")
        assert b is None or min(b.width, b.height) >= 48 - 1e-6


def test_a_tile_pushing_stops_where_one_would_be_too_small():
    tiles = _tiles(a=(0, 0, 500, 500), b=(500, 0, 1000, 500))
    drag = _pushing(tiles, "a", (1, 0), (500, 250))

    _approx(
        drag.moved((980, 250), is_snapping=False, keeps_shape=False), (0, 0, 952, 500)
    )
    _approx(drag.pushed["b"], (952, 226, 1000, 274))


def test_a_tile_pushing_goes_over_those_it_was_over_at_the_press():
    tiles = _tiles(a=(100, 100, 300, 200), b=(250, 100, 450, 200))
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    _approx(drag.moved((250, 150), is_snapping=False), (150, 100, 350, 200))
    assert drag.pushed == {}


def test_room_made_for_a_tile_sets_aside_those_it_is_over():
    tiles = _tiles(a=(250, 100, 450, 200), b=(400, 100, 600, 200), c=(0, 300, 200, 400))
    assert tiles.make_room("a")

    rects = tiles.rects(W, H)
    _approx(rects["b"], (450, 112.5, 600, 187.5))
    _approx(rects["c"], (0, 300, 200, 400))


def test_room_not_made_where_one_would_be_too_small():
    tiles = _tiles(a=(0, 0, 1000, 500), b=(400, 100, 600, 200))
    before = dict(tiles.tiles)

    assert not tiles.make_room("a")
    assert tiles.tiles == before


def _locked(tiles, *video_ids) -> FreeTiles:
    for video_id in video_ids:
        tiles.set_locked(video_id, True)
    return tiles


def test_a_locked_tile_has_nothing_to_move_or_size_it_by():
    tiles = _locked(_tiles(a=(100, 100, 300, 200), b=(300, 100, 500, 200)), "b")

    assert tiles.handle_at(400, 150, W, H) is None
    assert tiles.handle_at(498, 150, W, H) is None
    # where the two meet, the other's edge
    assert tiles.handle_at(302, 150, W, H) == ("a", (1, 0))


def test_a_tile_under_a_locked_one_has_nothing_there():
    tiles = _locked(_tiles(a=(0, 0, 300, 200), b=(200, 100, 500, 300)), "a")

    # a in front once locked
    assert list(tiles.tiles) == ["b", "a"]
    assert tiles.handle_at(250, 150, W, H) is None
    assert tiles.handle_at(400, 250, W, H) == ("b", MOVE)


def test_a_locked_tile_stays_in_front_of_the_others():
    tiles = _locked(
        _tiles(a=(0, 0, 300, 200), b=(200, 100, 500, 300), c=(250, 150, 450, 250)),
        "a",
    )

    tiles.stack("b", is_front=True)
    assert list(tiles.tiles) == ["c", "b", "a"]
    # nor is a tile under it to be put in front of it, nor it behind
    assert not tiles.is_under("b")
    assert not tiles.is_over("a")

    tiles.set_locked("a", False)
    tiles.stack("c", is_front=True)
    assert list(tiles.tiles) == ["b", "a", "c"]


@pytest.mark.parametrize(
    ("is_over", "is_pushing"), [(False, False), (True, False), (False, True)]
)
def test_a_tile_moved_stops_at_a_locked_one(is_over, is_pushing):
    tiles = _locked(_tiles(a=(100, 100, 300, 200), b=(350, 0, 450, 500)), "b")
    drag = _drag(tiles, "a", MOVE, (200, 150), is_over=is_over, is_pushing=is_pushing)

    _approx(drag.moved((450, 150), is_snapping=False), (150, 100, 350, 200))
    assert "b" not in drag.pushed


def test_a_tile_sized_over_others_stops_at_a_locked_one():
    tiles = _locked(_tiles(a=(100, 100, 300, 200), b=(310, 0, 500, 500)), "b")
    drag = _drag(tiles, "a", (1, 1), (300, 200), 2.0, is_over=True)

    _approx(drag.moved((400, 250), is_snapping=False), (100, 100, 310, 205))


def test_a_tile_pushing_sets_aside_others_but_not_a_locked_one():
    tiles = _locked(
        _tiles(a=(100, 100, 300, 200), b=(400, 100, 600, 200), c=(700, 100, 900, 200)),
        "c",
    )
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    # b pushed, a stopped at c
    _approx(drag.moved((700, 150), is_snapping=False), (500, 100, 700, 200))
    assert not drag.pushed["b"].overlaps(Rect(500, 100, 700, 200))
    assert "c" not in drag.pushed


def test_room_made_for_a_tile_leaves_a_locked_one():
    tiles = _locked(
        _tiles(a=(250, 100, 450, 200), b=(400, 100, 600, 200), c=(150, 50, 300, 150)),
        "c",
    )

    assert tiles.is_crowded("a")
    assert tiles.make_room("a")
    rects = tiles.rects(W, H)
    _approx(rects["b"], (450, 112.5, 600, 187.5))
    _approx(rects["c"], (150, 50, 300, 150))
    # with only the locked one over it, no room to make
    assert not tiles.is_crowded("a")


def test_videos_shuffled_leave_those_in_locked_tiles():
    tiles = _locked(
        _tiles(a=(0, 0, 100, 100), b=(200, 0, 300, 100), c=(400, 0, 500, 100)), "b"
    )
    before = tiles.rects(W, H)

    tiles.shuffle()

    rects = tiles.rects(W, H)
    assert rects["b"] == before["b"]
    assert rects["a"] == before["c"]
    assert rects["c"] == before["a"]


def test_a_lock_stays_with_the_tile_a_video_is_dropped_on():
    tiles = _locked(_tiles(a=(0, 0, 100, 100), b=(200, 0, 300, 100)), "b")

    tiles.drop([], None, None, None, src_id="a", dst_id="b")
    assert tiles.locked == {"a"}
    assert list(tiles.tiles) == ["b", "a"]

    tiles.drop([], None, None, None, is_replace=True, src_id="b", dst_id="a")
    assert tiles.locked == {"b"}
    _approx(tiles.rects(W, H)["b"], (200, 0, 300, 100))


def test_a_locked_tile_put_back_is_locked_again():
    tiles = _locked(_tiles(a=(0, 0, 300, 200), b=(400, 0, 600, 200)), "a")
    place = tiles.place_of("a", W, H)
    tiles.remove("a")
    assert tiles.locked == set()

    assert tiles.put_back("a", place)
    assert tiles.locked == {"a"}
    assert list(tiles.tiles) == ["b", "a"]


def test_the_open_area_is_the_biggest_part_no_locked_tile_is_on():
    tiles = _tiles(a=(600, 0, 1000, 500), b=(0, 0, 100, 100))
    assert tiles.open_area() == Box(0, 0, 1, 1)

    _locked(tiles, "a")
    assert tiles.open_area() == pytest.approx((0, 0, 0.6, 1))


def test_a_locked_tile_over_another_is_stacked():
    tiles = _locked(_tiles(a=(0, 0, 300, 200), b=(200, 100, 500, 300)), "a")

    assert tiles.is_stacked()
    assert tiles.is_crowded("a")


def test_an_edge_under_a_locked_tile_has_nothing_there():
    tiles = _locked(_tiles(a=(0, 0, 300, 200), b=(100, 50, 250, 150)), "a")

    # inside a, just right of b's edge under it
    assert tiles.handle_at(253, 100, W, H) is None


def test_a_tile_put_back_never_goes_under_a_locked_one():
    tiles = _locked(_tiles(a=(0, 0, 300, 200), b=(290, 0, 600, 200)), "b")
    place = tiles.place_of("a", W, H)
    tiles.remove("a")

    assert not tiles.put_back("a", place, is_over=True)


def test_a_video_added_goes_behind_the_locked_tiles():
    tiles = _locked(_tiles(a=(0, 0, 500, 500)), "a")
    tiles.shape_of = lambda _video_id: 1.0

    assert tiles.add(["b"]) == []
    assert list(tiles.tiles) == ["b", "a"]


def test_a_tile_pushing_does_not_snap_to_where_one_pushed_was():
    tiles = _tiles(a=(100, 100, 300, 200), b=(400, 100, 600, 200))
    drag = _pushing(tiles, "a", MOVE, (200, 150))

    drag.moved((350, 150))
    # its right edge near b's old left one, which b has left
    _approx(drag.moved((305, 150)), (205, 100, 405, 200))


def test_a_stretch_that_cannot_go_puts_back_those_pushed():
    # d locked off a's corner: its two edges stretched each way meet it
    tiles = _locked(
        _tiles(a=(100, 100, 300, 200), b=(310, 120, 500, 180), d=(305, 210, 400, 300)),
        "d",
    )
    drag = _pushing(tiles, "a", (1, 1), (300, 200))

    drag.moved((330, 215), is_snapping=False)
    assert drag.pushed["b"] != tiles.rects(W, H)["b"]

    _approx(drag.stretched(), (100, 100, 300, 200))
    _approx(drag.pushed["b"], (310, 120, 500, 180))


def test_a_tile_moved_snaps_to_the_gap_others_have():
    tiles = _tiles(
        a=(100, 200, 300, 300), b=(340, 200, 540, 300), c=(600, 380, 800, 480)
    )
    drag = _drag(tiles, "c", MOVE, (700, 430), snaps=_ALL)

    # 43 from b, as a and b are 40 apart
    rect = drag.moved((683, 253))

    _approx(rect, (580, 200, 780, 300))
    # its gap and theirs, not the page's margins above and below, the same
    # for all three only as their edges are lined up
    assert set(drag.gaps()) == {
        Gap(True, 540, 580, 200, 300, False),
        Gap(True, 300, 340, 200, 300, False),
    }

    # the line along their middles would hide the marks: not drawn, the
    # lines along their edges are
    guides = drag.guides()
    assert Guide(False, 250, 100, 780, GuideKind.MIDDLES) in guides
    drawn = guides_clear_of(guides, drag.gaps())
    assert not [g for g in drawn if not g.is_column and g.position == 250]
    assert Guide(False, 200, 100, 780, GuideKind.EDGES) in drawn


def test_a_tile_moved_snaps_to_the_middle_between_two():
    tiles = _tiles(
        a=(60, 200, 260, 300), b=(640, 200, 840, 300), x=(400, 350, 560, 430)
    )
    drag = _drag(tiles, "x", MOVE, (480, 390), snaps=_ALL)

    rect = drag.moved((454, 250))

    # as far from a as from b, not in the middle of the page
    _approx(rect, (370, 210, 530, 290))
    assert set(drag.gaps()) == {
        Gap(True, 260, 370, 210, 290, False),
        Gap(True, 530, 640, 210, 290, False),
    }


def test_a_tile_sized_snaps_to_the_gap_others_have():
    tiles = _tiles(
        a=(800, 20, 960, 120), b=(800, 150, 960, 250), c=(800, 300, 960, 400)
    )
    drag = _drag(tiles, "c", (0, -1), (880, 300), snaps=_ALL)

    rect = drag.moved((880, 283), keeps_shape=False)

    # its top 30 below b, as b is below a
    _approx(rect, (800, 280, 960, 400))
    assert set(drag.gaps()) == {
        Gap(False, 250, 280, 800, 960, False),
        Gap(False, 120, 150, 800, 960, False),
    }


def test_a_tile_sized_snaps_to_the_gap_on_its_other_side():
    tiles = _tiles(
        a=(100, 200, 300, 300), b=(700, 200, 900, 300), c=(350, 200, 550, 300)
    )
    drag = _drag(tiles, "c", (1, 0), (550, 250), snaps=_ALL)

    rect = drag.moved((645, 250), keeps_shape=False)

    # 50 from b, as it is from a
    _approx(rect, (350, 200, 650, 300))
    assert set(drag.gaps()) == {
        Gap(True, 300, 350, 200, 300, False),
        Gap(True, 650, 700, 200, 300, False),
    }


def test_a_tile_over_another_snaps_to_the_margin_another_has():
    tiles = _tiles(main=(0, 0, 1000, 500), a=(20, 20, 220, 120), b=(500, 200, 700, 300))
    drag = _drag(tiles, "b", MOVE, (600, 250), is_over=True, snaps=_ALL)

    rect = drag.moved((883, 427))

    # in the corner across from a's, as far in; not marked as far from
    # the other edges, as a is
    _approx(rect, (780, 380, 980, 480))
    assert set(drag.gaps()) == {
        Gap(True, 980, 1000, 380, 480, True),
        Gap(True, 0, 20, 20, 120, True),
        Gap(False, 480, 500, 780, 980, True),
        Gap(False, 0, 20, 20, 220, True),
    }


def test_a_tile_moved_without_snapping_keeps_its_gap():
    tiles = _tiles(
        a=(100, 200, 300, 300), b=(340, 200, 540, 300), c=(600, 380, 800, 480)
    )
    drag = _drag(tiles, "c", MOVE, (700, 430), snaps=_ALL)

    rect = drag.moved((683, 253), is_snapping=False)

    _approx(rect, (583, 203, 783, 303))


def test_gaps_are_not_snapped_to_by_default():
    tiles = _tiles(
        a=(100, 200, 300, 300), b=(340, 200, 540, 300), c=(600, 380, 800, 480)
    )
    drag = _drag(tiles, "c", MOVE, (700, 430))

    rect = drag.moved((683, 253))

    # its top on theirs, but not 40 from b
    _approx(rect, (583, 200, 783, 300))
    assert drag.gaps() == []


def test_a_snap_turned_off_is_neither_snapped_to_nor_shown():
    tiles = _tiles(a=(100, 100, 250, 200), b=(600, 300, 800, 400))
    drag = _drag(tiles, "a", MOVE, (175, 150), snaps=_ALL - {TileSnap.TILE_EDGES})

    # its right edge 4 short of b's left
    rect = drag.moved((521, 150))

    _approx(rect, (446, 100, 596, 200))
    assert not [g for g in drag.guides() if g.kind is GuideKind.EDGES]


def test_a_tile_sized_to_any_shape_snaps_to_its_videos_only_if_told():
    tiles = _tiles(a=(100, 100, 300, 200))
    snaps = _SNAPS - {TileSnap.VIDEO_SHAPE}
    drag = _drag(tiles, "a", (1, 0), (300, 150), shape=2.0, snaps=snaps)

    # 4 short of its video's shape
    rect = drag.moved((296, 150), keeps_shape=False)

    _approx(rect, (100, 100, 296, 200))
    assert not drag.fits


def test_snapping_to_all_but_equal_gaps_by_default():
    from gridplayer.settings import _default_settings

    assert _default_settings["playlist/tile_snaps"].root == _SNAPS


def test_snaps_saved_by_name_in_the_menu_order():
    snaps = TileSnaps(frozenset({TileSnap.EQUAL_GAPS, TileSnap.TILE_EDGES}))

    assert snaps.model_dump_json() == '["tile_edges","equal_gaps"]'
    assert TileSnaps.model_validate_json(snaps.model_dump_json()) == snaps
    assert TileSnap.EQUAL_GAPS not in snaps.toggled(TileSnap.EQUAL_GAPS)


def test_the_room_beside_a_tile_is_to_one_it_pushed_where_it_is_now():
    tiles = _tiles(
        a=(100, 200, 300, 300),
        b=(600, 200, 800, 300),
        c=(350, 400, 450, 480),
        t=(350, 200, 550, 300),
    )
    drag = _drag(tiles, "t", MOVE, (450, 250), snaps=_ALL, is_pushing=True)

    # onto b, made smaller in its place, against t
    drag.moved((550, 250), is_snapping=False)

    places = [drag.pushed.get(i, r) for i, r in tiles.rects(W, H).items() if i != "t"]
    assert drag.pushed["b"].left == pytest.approx(650)
    # no gap across b to the page's edge, as far as c is from the other
    assert not [g for g in drag.gaps() if any(g.area.overlaps(r) for r in places)]


def test_a_tile_does_not_snap_to_a_margin_by_the_same_edge():
    tiles = _tiles(a=(16, 100, 216, 200), t=(300, 300, 460, 400))
    snaps = _ALL - {TileSnap.TILE_EDGES}
    drag = _drag(tiles, "t", MOVE, (380, 350), snaps=snaps)

    # 20 from the page's left, as a is 16: that would only be their edges
    # lined up, which it is told not to snap to
    rect = drag.moved((100, 350))

    _approx(rect, (20, 300, 180, 400))


def test_a_tile_sized_by_a_corner_snaps_to_a_gap_beside_it_as_sized():
    tiles = _tiles(
        a=(0, 0, 100, 100),
        b=(130, 0, 230, 100),
        t=(300, 150, 400, 250),
        c=(500, 300, 600, 400),
    )
    drag = _drag(tiles, "t", (1, 1), (400, 250), snaps=_ALL)

    # as tall as it is now, beside c, 28 from it: 30, as a is from b
    rect = drag.moved((472, 350), keeps_shape=False)

    _approx(rect, (300, 150, 470, 350))


def test_between_the_page_edges_only_the_less_margin_snaps_to_a_gap():
    tiles = _tiles(a=(0, 0, 100, 100), b=(130, 0, 230, 100), t=(40, 200, 982, 300))
    drag = _drag(tiles, "t", MOVE, (500, 250), snaps={TileSnap.EQUAL_GAPS})

    # 30 on the left would leave 28 on the right, the margin it has
    rect = drag.moved((493, 250))

    _approx(rect, (33, 200, 975, 300))
    assert drag.gaps() == []


def test_between_the_page_edges_the_less_margin_snaps_and_is_marked():
    tiles = _tiles(a=(0, 0, 100, 100), b=(130, 0, 230, 100), t=(37, 200, 927, 300))
    drag = _drag(tiles, "t", MOVE, (480, 250), snaps={TileSnap.EQUAL_GAPS})

    rect = drag.moved((477, 250))

    _approx(rect, (30, 200, 920, 300))
    assert set(drag.gaps()) == {
        Gap(True, 0, 30, 200, 300, True),
        Gap(True, 100, 130, 0, 100, False),
    }


def test_snaps_turned_on_while_held_are_snapped_to():
    tiles = _tiles(
        a=(100, 200, 300, 300), b=(340, 200, 540, 300), c=(600, 380, 800, 480)
    )
    drag = _drag(tiles, "c", MOVE, (700, 430))
    _approx(drag.moved((683, 253)), (583, 200, 783, 300))

    drag.snap_to(_ALL)

    _approx(drag.moved((683, 253)), (580, 200, 780, 300))
