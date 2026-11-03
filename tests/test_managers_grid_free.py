import contextlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.params.static import GridMode, TileOverlap, TileResize
from gridplayer.player.managers import grid as grid_module
from gridplayer.player.managers.grid import GridManager
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import Box, GridLayout
from gridplayer.utils.layout.free_tiles import Rect


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _settings_get(mocker):
    """Answer with the shipped defaults, never with this machine's settings."""

    mocker.patch.object(Settings(), "get", side_effect=_default_settings.__getitem__)


class _Blocks:
    """Videos by id, of these shapes; None for one not known yet."""

    def __init__(self, shapes):
        self.blocks = {
            video_id: SimpleNamespace(video_id=video_id, picture_shape=shape)
            for video_id, shape in shapes.items()
        }

    @property
    def video_ids(self):
        return list(self.blocks)

    def __bool__(self):
        return bool(self.blocks)

    def __iter__(self):
        return iter(self.blocks.values())

    def by_video_id(self, video_id):
        return self.blocks.get(video_id)

    def blocks_for_ids(self, video_ids):
        return [self.blocks[i] for i in video_ids if i in self.blocks]


def _manager(shapes) -> GridManager:
    # an area of 1000 by 500, as the grid has no place of its own yet
    parent = QWidget()
    parent.resize(1000, 500)
    commands = SimpleNamespace(
        remove_video_blocks=lambda *_a, **_k: None,
        remember_closed=lambda *_a: None,
        add_video_blocks=lambda videos: videos,
    )
    ctx = SimpleNamespace(
        video_blocks=_Blocks(shapes),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=commands,
    )
    manager = GridManager(context=ctx, parent=parent)
    manager._keep_parent = parent
    return manager


def _rects(manager) -> dict[str, Rect]:
    return manager._free.rects(1000, 500)


def _free(manager, **rects):
    """Free Tiles with these tiles, in the area's pixels."""

    manager._mode = GridMode.FREE
    manager._free.page_shape = 2.0
    manager._free.page_height = 500
    manager._free.is_as_placed = True
    for video_id, rect in rects.items():
        manager._free.set_rect(video_id, Rect(*rect), 1000, 500)


def _arranged_when_due(manager):
    """Arranged once the shapes stop coming (see ARRANGE_DELAY)."""

    assert manager._arrange_timer.isActive()
    manager._arrange_timer.stop()
    manager._arrange_due()


def _covered(rects) -> float:
    return sum(r.width * r.height for r in rects.values())


def _overlapping(rects) -> bool:
    found = list(rects.values())
    return any(a.overlaps(b) for i, a in enumerate(found) for b in found[i + 1 :])


def test_free_tiles_keep_each_video_where_its_cell_was():
    manager = _manager({"A": 16 / 9, "B": 16 / 9, "C": 16 / 9})
    manager._flow.ids = ["A", "B", "C"]
    manager._flow.fit_to(1000, 500, {})
    cells = dict(manager._flow.boxes())

    manager.cmd_set_grid_mode(GridMode.FREE)

    assert manager._mode is GridMode.FREE
    assert manager._free.tiles == cells
    assert manager._free.page_shape == 2.0
    # undone, the grid as it was
    manager.cmd_undo_grid()
    assert manager._mode is GridMode.AUTO_ROWS
    assert not manager._free.tiles


def test_free_tiles_from_a_fixed_grid_keep_its_empty_cells_as_room():
    manager = _manager({"A": 16 / 9, "B": 16 / 9})
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(
        max_rows=2,
        max_cols=2,
        cells=[
            GridCell(video_id="A", row=0, col=0),
            GridCell(video_id="B", row=1, col=1),
        ],
    )

    manager.cmd_set_grid_mode(GridMode.FREE)

    assert manager._free.tiles == {
        "A": Box(0, 0, 0.5, 0.5),
        "B": Box(0.5, 0.5, 1, 1),
    }
    assert manager._grid_layout.cells == []


def test_leaving_free_tiles_the_videos_go_in_the_order_the_tiles_are_read():
    manager = _manager({"A": 16 / 9, "B": 16 / 9})
    _free(manager, A=(600, 0, 1000, 250), B=(0, 0, 400, 250))

    manager.cmd_set_grid_mode(GridMode.AUTO_ROWS)

    assert manager._flow.ids == ["B", "A"]
    assert not manager._free.tiles


def test_free_tiles_are_kept_in_the_grid_state(mocker):
    manager = _manager({"A": 16 / 9})
    _free(manager, A=(100, 50, 500, 275))

    state = manager.grid_state()
    loaded = _manager({"A": 16 / 9})
    mocker.patch.object(loaded, "_render_video_grid")
    loaded.set_grid_state(GridState.model_validate(state.model_dump(mode="json")))

    assert loaded._mode is GridMode.FREE
    assert loaded._free.tiles == manager._free.tiles
    assert loaded._free.page_shape == 2.0


def test_a_video_added_to_free_tiles_goes_where_there_is_room():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 500, 250))

    manager._reconcile_layout()

    _approx(_rects(manager)["B"], (500, 0, 1000, 250))
    assert _rects(manager)["A"] == Rect(0, 0, 500, 250)


def test_videos_with_no_room_on_the_page_have_all_tiles_arranged_anew():
    manager = _manager({"A": 2.0, "B": 2.0, "C": 2.0})
    _free(manager, A=(0, 0, 500, 500), B=(500, 0, 1000, 500))

    manager._reconcile_layout()

    rects = _rects(manager)
    assert set(rects) == {"A", "B", "C"}
    assert not _overlapping(rects)
    # as Arrange Tiles does: as much of the page as the crop limit lets them
    # fill, three of this shape cut a fifth
    assert _covered(rects) == pytest.approx(1000 * 500 / (1 - 0.2) * 2 / 3)
    for rect in rects.values():
        assert rect.width / rect.height == pytest.approx(2.0 / (1 - 0.2))


def test_videos_with_no_room_are_arranged_with_the_crop_limit():
    manager = _manager({"A": 2.0, "B": 2.0, "C": 2.0})
    _free(manager, A=(0, 0, 500, 500), B=(500, 0, 1000, 500))
    manager._tile_crop = 0
    manager._free.tiles = {}
    _free(manager, A=(0, 0, 500, 500), B=(500, 0, 1000, 500))

    manager._reconcile_layout()

    for rect in _rects(manager).values():
        assert rect.width / rect.height == pytest.approx(2.0)


def test_adding_with_no_room_asks_first_and_cancelled_adds_nothing(mocker):
    manager = _manager({"A": 2.0})
    _free(manager, A=(0, 0, 1000, 500))
    question = mocker.patch(
        "gridplayer.player.managers.grid.QCustomMessageBox.confirm",
        return_value=False,
    )

    assert manager.add_videos_to_layout(["new.mp4"]) == []
    question.assert_called_once()


def test_arranged_without_cropping_tiles_are_laid_out_as_fit_shapes():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 200, 100), B=(700, 300, 900, 400))
    before = dict(manager._free.tiles)
    manager._tile_crop = 0

    manager.cmd_arrange_tiles()

    rects = _rects(manager)
    # side by side, filling the width
    assert rects["A"].width + rects["B"].width == pytest.approx(1000)
    assert not _overlapping(rects)

    manager.cmd_undo_grid()
    assert manager._free.tiles == before


@pytest.mark.parametrize(
    "rects",
    [
        # a tall one beside two wide ones: in columns, read row by row in
        # another order than they went down them
        {"A": (0, 0, 150, 90), "B": (500, 0, 650, 90), "C": (100, 300, 250, 390)},
        {"A": (600, 350, 750, 440), "B": (50, 200, 200, 290), "C": (400, 20, 550, 110)},
        {
            "A": (0, 0, 150, 90),
            "B": (200, 200, 350, 290),
            "C": (400, 0, 550, 90),
            "D": (600, 300, 750, 390),
        },
    ],
)
@pytest.mark.parametrize("crop", [0, 20, 50])
def test_tiles_arranged_again_stay_where_they_are(rects, crop):
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9, "D": 1.0}
    manager = _manager({i: shapes[i] for i in rects})
    _free(manager, **rects)
    manager._tile_crop = crop

    manager.cmd_arrange_tiles()
    arranged = _rects(manager)
    manager.cmd_arrange_tiles()

    assert _rects(manager) == arranged


def test_arranged_tiles_fill_the_page_and_can_be_undone():
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9}
    manager = _manager(shapes)
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90), C=(100, 300, 250, 390))

    manager._tile_crop = 0
    manager.cmd_arrange_tiles()
    exact = _rects(manager)
    manager._tile_crop = 50
    manager.cmd_arrange_tiles()
    filled = _rects(manager)

    # their videos' shapes, with room left around them
    for video_id, rect in exact.items():
        assert rect.width / rect.height == pytest.approx(shapes[video_id])
    assert _covered(exact) < 1000 * 500 * 0.9
    # stretched over it, each the same share off its picture's shape
    assert _covered(filled) == pytest.approx(1000 * 500)
    assert not _overlapping(filled)
    stretch = {i: (r.width / r.height) / shapes[i] for i, r in filled.items()}
    assert len({round(s, 3) for s in stretch.values()}) == 1

    manager.cmd_undo_grid()
    assert _rects(manager) == exact


def test_tiles_arranged_fill_the_page_again_once_shapes_are_known():
    manager = _manager({"A": 16 / 9, "B": None})
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90))
    manager.cmd_arrange_tiles()

    manager._ctx.video_blocks.by_video_id("B").picture_shape = 9 / 16
    manager.fit_to_shapes()
    _arranged_when_due(manager)

    assert _covered(_rects(manager)) == pytest.approx(1000 * 500)


def test_tiles_arranged_before_the_shapes_were_known_are_arranged_again():
    manager = _manager({"A": None, "B": None})
    manager._mode = GridMode.FREE

    manager._reconcile_layout()
    for block in manager._ctx.video_blocks:
        block.picture_shape = 1.0
    manager.fit_to_shapes()
    _arranged_when_due(manager)

    rects = _rects(manager)
    assert all(r.width == pytest.approx(r.height) for r in rects.values())


def test_a_tile_moved_by_hand_is_only_made_its_videos_shape():
    manager = _manager({"A": None, "B": None})
    manager._mode = GridMode.FREE
    manager._reconcile_layout()
    manager.set_free_tiles({"B": Rect(600, 100, 1000, 400)}, 1000, 500)

    manager._ctx.video_blocks.by_video_id("B").picture_shape = 1.0
    manager.fit_to_shapes()

    _approx(_rects(manager)["B"], (650, 100, 950, 400))


def test_a_video_reopened_goes_back_to_its_tile_if_it_is_free():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    place = manager.place_of("B")
    manager._free.remove("B")

    manager._put_back("B", place)

    _approx(_rects(manager)["B"], (500, 0, 900, 200))


def test_a_video_reopened_goes_back_beside_the_others_wherever_they_are(mocker):
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    place = manager.place_of("B")
    manager._free.remove("B")
    # the page made the shape of another window since: A fitted to it
    manager._free.fill(500, 500)

    manager._put_back("B", place)

    # beside A as it was, the two fitted to the window together, as they
    # would have been had B stayed
    rects = _rects(manager)
    _approx(rects["A"], (0, 138.9, 444.4, 361.1))
    _approx(rects["B"], (555.6, 138.9, 1000, 361.1))


def test_tiles_kept_kept_where_they_are_when_one_is_closed_and_reopened():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    manager._free.resize = TileResize.KEEP
    # resized since they were placed: in the middle
    manager._place_free(1000, 500 + 1)
    manager._place_free(1000, 500)
    before = _shown(manager, 1000, 500)
    place = manager.place_of("B")

    del manager._ctx.video_blocks.blocks["B"]
    manager._reconcile_layout()

    # A where it was shown, not fitted alone to the middle
    _approx(_shown(manager, 1000, 500)["A"], before["A"])

    manager._put_back("B", place)
    shown = _shown(manager, 1000, 500)
    for video_id, rect in before.items():
        _approx(shown[video_id], rect)


def test_a_video_closed_leaves_the_others_where_they_are_shown():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    # resized since they were placed: scaled to fit
    manager._place_free(1000, 500 + 1)
    manager._place_free(1000, 500)
    before = _shown(manager, 1000, 500)

    del manager._ctx.video_blocks.blocks["B"]
    manager._reconcile_layout()

    # not made to fill the window alone
    _approx(_shown(manager, 1000, 500)["A"], before["A"])


def test_a_video_reopened_over_another_goes_back_as_deep(mocker):
    manager = _manager({"A": 2.0, "B": 2.0, "C": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(300, 100, 700, 300), C=(600, 200, 1000, 400))
    mocker.patch.object(manager, "tile_overlap", return_value=TileOverlap.ON)
    place = manager.place_of("B")
    manager._free.remove("B")

    manager._put_back("B", place)

    _approx(_rects(manager)["B"], (300, 100, 700, 300))
    assert list(manager._free.tiles) == ["A", "B", "C"]


def test_the_page_is_where_the_tiles_are_moved_on(mocker):
    manager = _manager({"A": 2.0})
    _free(manager, A=(0, 0, 400, 200))
    manager._free.resize = TileResize.KEEP
    mocker.patch.object(manager, "grid_area", return_value=_area(0, 0, 1000, 700))

    page = manager.free_page()

    # all of the area, the tiles where they are shown: as big, in the
    # middle
    assert page.rect == _area(0, 0, 1000, 700)
    _approx(page.tiles.rects(1000, 700)["A"], (300, 250, 700, 450))
    # the layout's own shape kept, until a tile is moved
    assert manager._free.page_shape == 2.0

    manager._ctx.is_single_mode = True
    assert manager.free_page() is None


def test_a_tile_moved_makes_the_page_the_areas_shape(mocker):
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    manager._free.resize = TileResize.KEEP
    mocker.patch.object(manager, "grid_area", return_value=_area(0, 0, 1000, 700))

    # moved into the room below the layout's own page
    manager.set_free_tiles({"A": Rect(0, 500, 400, 700)}, 1000, 700)

    assert manager._free.page_shape == pytest.approx(1000 / 700)
    rects = manager._free.rects(1000, 700)
    _approx(rects["A"], (0, 500, 400, 700))
    # the other where it was shown, in the middle with A as it was
    _approx(rects["B"], (550, 250, 950, 450))


def test_a_video_added_goes_to_the_room_beside_the_page(mocker):
    manager = _manager({"A": 2.0, "B": 2.0})
    manager._keep_parent.resize(1000, 1000)
    _free(manager, A=(0, 0, 1000, 500))

    manager._reconcile_layout()

    rects = manager._free.rects(1000, 1000)
    # A where it was shown, in the middle; B in the room above or below
    _approx(rects["A"], (0, 250, 1000, 750))
    assert not _overlapping(rects)


def _area(x, y, width, height):
    from PyQt5.QtCore import QRect

    return QRect(x, y, width, height)


def _approx(rect, expected):
    assert rect == pytest.approx(expected, abs=0.6)


def test_tiles_keep_their_order_in_the_grid_state(mocker):
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(300, 100, 700, 300))
    manager._free.stack("A", is_front=True)

    state = GridState.model_validate(manager.grid_state().model_dump(mode="json"))
    loaded = _manager({"A": 2.0, "B": 2.0})
    mocker.patch.object(loaded, "_render_video_grid")
    loaded.set_grid_state(state)

    assert list(loaded._free.tiles) == ["B", "A"]


def test_a_tile_put_in_front_can_be_undone():
    manager = _manager({"A": 2.0, "B": 2.0, "C": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(300, 100, 700, 300), C=(800, 0, 1000, 100))
    manager._ctx.active_block = manager._ctx.video_blocks.by_video_id("A")

    assert manager.is_tile_stackable("front")
    assert not manager.is_tile_stackable("back")
    manager.cmd_stack_tile("front")
    assert list(manager._free.tiles) == ["B", "C", "A"]
    assert not manager.is_tile_stackable("front")

    manager.cmd_undo_grid()
    assert list(manager._free.tiles) == ["A", "B", "C"]

    # C is over nothing: it stays where it is
    manager._ctx.active_block = manager._ctx.video_blocks.by_video_id("C")
    assert not manager.is_tile_stackable("front")


def test_tiles_are_stacked_where_they_can_go_over_each_other(mocker):

    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    meet = mocker.patch.object(manager, "tile_overlap", return_value=TileOverlap.OFF)

    assert not manager.is_tiles_stacked()
    meet.return_value = TileOverlap.ON
    assert manager.is_tiles_stacked()


def test_tiles_fitted_to_the_window_leave_no_room_around_them():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(100, 100, 300, 200), B=(300, 200, 500, 300))

    manager.cmd_fit_tiles_to_window()

    _approx(_rects(manager)["A"], (0, 0, 500, 250))
    _approx(_rects(manager)["B"], (500, 250, 1000, 500))
    manager.cmd_undo_grid()
    _approx(_rects(manager)["A"], (100, 100, 300, 200))


def _shown(manager, width, height) -> dict[str, tuple]:
    return {
        video_id: (b.left * width, b.top * height, b.right * width, b.bottom * height)
        for video_id, b in manager._free.boxes(width, height)
    }


def test_tiles_scale_to_fit_by_default():
    manager = _manager({"A": 2.0, "B": 2.0})

    assert manager._free.resize == TileResize.FIT
    assert manager.grid_state().tile_resize == TileResize.FIT


def test_tile_sizes_kept_leave_the_tiles_where_they_are_shown():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    # the window made smaller and taller since they were placed
    manager._keep_parent.resize(800, 800)
    manager._place_free(800, 800)
    before = _shown(manager, 800, 800)

    manager.cmd_set_tile_resize(TileResize.KEEP)

    assert manager._free.resize == TileResize.KEEP
    shown = _shown(manager, 800, 800)
    for video_id, rect in before.items():
        _approx(shown[video_id], rect)

    manager.cmd_undo_grid()
    assert manager._free.resize == TileResize.FIT
    assert manager._free.page_height == 500


def test_tiles_scaled_to_fit_fit_at_once():
    manager = _manager({"A": 2.0})
    _free(manager, A=(100, 100, 300, 200))
    manager._free.resize = TileResize.KEEP

    manager.cmd_set_tile_resize(TileResize.FIT)

    _approx(_shown(manager, 1000, 500)["A"], (0, 0, 1000, 500))


def test_tiles_are_shown_as_placed_until_the_window_is_resized():
    manager = _manager({"A": 2.0})
    _free(manager, A=(100, 100, 300, 200))

    manager._place_free(1000, 500)
    _approx(_shown(manager, 1000, 500)["A"], (100, 100, 300, 200))

    # resized and back: fitted, and so after Undo of a change made since
    manager._place_free(800, 800)
    manager._place_free(1000, 500)
    _approx(_shown(manager, 1000, 500)["A"], (0, 0, 1000, 500))
    manager.begin_grid_change()
    manager.set_free_tiles({"A": Rect(0, 0, 400, 200)}, 1000, 500)
    manager.end_grid_change()
    _approx(_shown(manager, 1000, 500)["A"], (0, 0, 400, 200))
    manager.cmd_undo_grid()
    _approx(_shown(manager, 1000, 500)["A"], (0, 0, 1000, 500))


def test_tile_sizes_are_kept_in_the_grid_state(mocker):
    manager = _manager({"A": 2.0})
    _free(manager, A=(0, 0, 400, 200))
    manager._free.resize = TileResize.KEEP

    dumped = manager.grid_state().model_dump(mode="json")
    state = GridState.model_validate(dumped)
    loaded = _manager({"A": 2.0})
    mocker.patch.object(loaded, "_render_video_grid")
    loaded.set_grid_state(state)

    assert loaded._free.page_height == 500
    assert loaded._free.resize == TileResize.KEEP
    # whether shown as placed is for undo, not written: a playlist's are as
    # it was saved, until the window is resized
    assert "is_tiles_as_placed" not in dumped
    assert loaded._free.is_as_placed
    loaded._place_free(1000, 500)
    _approx(_shown(loaded, 1000, 500)["A"], (0, 0, 400, 200))


def test_settings_applied_in_free_tiles_keep_the_tiles():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(100, 100, 300, 200), B=(600, 200, 800, 300))
    before = dict(manager._free.tiles)
    config = manager.grid_state().model_copy(update={"is_fit": False})

    assert manager.apply_grid_config(config)

    assert manager._free.tiles == before
    # for when Free Tiles is left
    assert manager._flow.is_fit is False


def _adding(manager):
    """Videos added as the video blocks manager adds them, those of the
    blocks there are."""

    blocks = manager._ctx.video_blocks
    manager._ctx.commands.video_count_batch = contextlib.nullcontext
    manager._ctx.commands.add_video_blocks = blocks.blocks_for_ids
    return blocks


def test_a_video_dropped_is_made_its_videos_shape_once_known():
    manager = _manager({"A": 2.0, "B": None})
    _free(manager, A=(0, 0, 400, 200))
    blocks = _adding(manager)

    manager._place_dropped_ids(["B"], None, None, DropZone.CENTER, None)
    blocks.by_video_id("B").picture_shape = 1.0
    manager.fit_to_shapes()

    rect = _rects(manager)["B"]
    assert rect.width == pytest.approx(rect.height)


def test_a_video_reopened_with_no_tile_is_made_its_videos_shape_once_known():
    manager = _manager({"A": 2.0, "B": None})
    _free(manager, A=(0, 0, 400, 200))

    manager._put_back("B", None)
    manager._ctx.video_blocks.by_video_id("B").picture_shape = 1.0
    manager.fit_to_shapes()

    rect = _rects(manager)["B"]
    assert rect.width == pytest.approx(rect.height)


def test_a_drop_with_no_room_asks_first_and_cancelled_adds_nothing(mocker):
    manager = _manager({"A": 2.0})
    _free(manager, A=(0, 0, 1000, 500))
    manager._ctx.commands.add_video_blocks = Mock()
    question = mocker.patch(
        "gridplayer.player.managers.grid.QCustomMessageBox.confirm",
        return_value=False,
    )

    manager.cmd_layout_drop(["new.mp4"], None, None, DropZone.CENTER, False)

    question.assert_called_once()
    manager._ctx.commands.add_video_blocks.assert_not_called()


def test_a_tile_put_back_on_esc_leaves_nothing_to_undo():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    before = manager.grid_state()

    manager.begin_grid_change()
    # on a window taller than the page: its shape made the window's
    manager.set_free_tiles({"A": Rect(0, 500, 400, 700)}, 1000, 700)
    manager.cancel_grid_change()
    manager.end_grid_change()

    assert manager.grid_state() == before
    assert not manager._undo


def test_room_made_for_a_tile_sets_aside_those_it_covers_and_can_be_undone():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(250, 100, 450, 200), B=(400, 100, 600, 200))
    manager._ctx.active_block = manager._ctx.video_blocks.by_video_id("A")
    before = dict(manager._free.tiles)

    assert manager.is_tile_room_makeable()
    manager.cmd_make_room()

    rects = _rects(manager)
    assert not _overlapping(rects)
    assert rects["A"] == pytest.approx(Rect(250, 100, 450, 200))
    assert not manager.is_tile_room_makeable()

    manager.cmd_undo_grid()
    assert manager._free.tiles == before


def test_room_made_with_too_little_asks_to_arrange(mocker):
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 1000, 500), B=(400, 100, 600, 200))
    manager._ctx.active_block = manager._ctx.video_blocks.by_video_id("A")
    question = mocker.patch(
        "gridplayer.player.managers.grid.QCustomMessageBox.confirm",
        return_value=True,
    )

    manager.cmd_make_room()

    question.assert_called_once()
    assert not _overlapping(_rects(manager))


def test_a_tile_locked_is_kept_in_the_grid_state_and_can_be_undone(mocker):
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 300, 200), B=(200, 100, 500, 300))
    manager._ctx.active_block = manager._ctx.video_blocks.by_video_id("A")
    assert manager.is_tile_lockable()

    manager.cmd_lock_tile()

    assert manager.is_tile_locked()
    assert list(manager._free.tiles) == ["B", "A"]

    loaded = _manager({"A": 2.0, "B": 2.0})
    mocker.patch.object(loaded, "_render_video_grid")
    state = manager.grid_state()
    loaded.set_grid_state(GridState.model_validate(state.model_dump(mode="json")))
    assert loaded._free.locked == {"A"}

    manager.cmd_undo_grid()
    assert not manager.is_tile_locked()
    assert list(manager._free.tiles) == ["A", "B"]


def test_tiles_arranged_leave_a_locked_one_where_it_is():
    manager = _manager({"A": 2.0, "B": 2.0, "C": 2.0})
    _free(manager, A=(600, 0, 1000, 500), B=(0, 0, 200, 100), C=(700, 300, 900, 400))
    manager._free.set_locked("A", True)
    manager._tile_crop = 0

    manager.cmd_arrange_tiles()

    rects = _rects(manager)
    _approx(rects["A"], (600, 0, 1000, 500))
    assert not _overlapping(rects)
    # the others in the room left of it, one above the other
    _approx(rects["B"], (50, 0, 550, 250))
    _approx(rects["C"], (50, 250, 550, 500))
    assert list(manager._free.tiles)[-1] == "A"


def test_leaving_free_tiles_lets_go_of_the_locks():
    manager = _manager({"A": 2.0})
    _free(manager, A=(0, 0, 300, 200))
    manager._free.set_locked("A", True)

    manager._leave_free()

    assert manager._free.locked == set()


def test_tiles_arranged_with_no_room_left_by_the_locked_ones_are_all_arranged():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 1000, 500), B=(100, 100, 300, 200))
    manager._free.set_locked("A", True)

    manager.cmd_arrange_tiles()

    rects = _rects(manager)
    assert not _overlapping(rects)
    assert rects["B"].width > 300


def test_a_locked_video_reopened_elsewhere_is_still_locked():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 400, 200), B=(500, 0, 900, 200))
    manager._free.set_locked("B", True)
    place = manager.place_of("B")
    manager._free.remove("B")
    manager._free.set_rect("A", Rect(400, 0, 800, 200), 1000, 500)

    manager._put_back("B", place)

    assert manager._free.locked == {"B"}
    assert not _overlapping(_rects(manager))


# --- Fill Space, Fit Tile to Video ---


def test_fill_space_makes_a_tile_as_big_as_the_room_around_it_once():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 500, 500), B=(600, 100, 800, 300))

    assert manager.is_tile_space_fillable("B")

    manager.cmd_fill_tile_space("B")

    _approx(_rects(manager)["B"], (500, 0, 1000, 500))
    _approx(_rects(manager)["A"], (0, 0, 500, 500))
    # no room left: again, nothing changes
    assert not manager.is_tile_space_fillable("B")
    manager.cmd_fill_tile_space("B")
    _approx(_rects(manager)["B"], (500, 0, 1000, 500))


def test_fill_space_can_be_undone():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 500, 500), B=(600, 100, 800, 300))
    manager.cmd_fill_tile_space("B")

    manager.cmd_undo_grid()

    _approx(_rects(manager)["B"], (600, 100, 800, 300))


def test_a_tile_with_no_room_around_it_or_locked_cannot_be_filled():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 500, 500), B=(500, 0, 1000, 500))

    assert not manager.is_tile_space_fillable("A")

    _free(manager, A=(0, 0, 500, 500), B=(600, 100, 800, 300))
    manager.lock_free_tile("B", True)

    assert not manager.is_tile_space_fillable("B")
    manager.cmd_fill_tile_space("B")
    _approx(_rects(manager)["B"], (600, 100, 800, 300))


def test_a_tile_fit_to_its_video_loses_the_bars_beside_the_picture():
    manager = _manager({"A": 16 / 9, "B": None})
    _free(manager, A=(0, 0, 500, 500), B=(600, 100, 800, 300))

    assert manager.is_tile_fittable("A")
    # its video's shape not known yet
    assert not manager.is_tile_fittable("B")

    manager.cmd_fit_tile_to_video("A")

    _approx(_rects(manager)["A"], (0, 109.4, 500, 390.6))
    assert not manager.is_tile_fittable("A")

    manager.cmd_undo_grid()

    _approx(_rects(manager)["A"], (0, 0, 500, 500))


def test_tiles_arranged_go_all_round_a_locked_one():
    shapes = {"A": 2.0, "B": 16 / 9, "C": 16 / 9, "D": 16 / 9, "E": 16 / 9}
    manager = _manager(shapes)
    _free(
        manager,
        A=(350, 150, 650, 350),
        B=(0, 0, 160, 90),
        C=(800, 0, 960, 90),
        D=(0, 400, 160, 490),
        E=(800, 400, 960, 490),
    )
    manager._free.set_locked("A", True)

    manager.cmd_arrange_tiles()

    rects = _rects(manager)
    _approx(rects["A"], (350, 150, 650, 350))
    assert not _overlapping(rects)
    # not all in the biggest room on one side of it: some on its left, and
    # some on its right
    others = [rects[i] for i in "BCDE"]
    assert any(r.right <= 350 + 0.5 for r in others)
    assert any(r.left >= 650 - 0.5 for r in others)
    # each picture cut by no more than the limit
    for video_id in "BCDE":
        r = rects[video_id]
        stretch = (r.width / r.height) / shapes[video_id]
        assert 1 - min(stretch, 1 / stretch) <= 0.2 + 1e-6


def test_crop_limit_is_20_by_default_and_kept_in_the_grid_state(mocker):
    manager = _manager({"A": 2.0})
    _free(manager, A=(0, 0, 400, 200))
    assert manager._tile_crop == 20
    manager._tile_crop = 5

    state = GridState.model_validate(manager.grid_state().model_dump(mode="json"))
    loaded = _manager({"A": 2.0})
    mocker.patch.object(loaded, "_render_video_grid")
    loaded.set_grid_state(state)

    assert loaded._tile_crop == 5
    assert loaded.commands["is_tile_crop"](5)


def test_crop_limit_set_arranges_again_tiles_as_arrange_left_them():
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9}
    manager = _manager(shapes)
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90), C=(100, 300, 250, 390))
    manager._tile_crop = 0
    manager.cmd_arrange_tiles()
    exact = _rects(manager)

    manager.cmd_set_tile_crop(50)

    assert manager._tile_crop == 50
    assert _covered(_rects(manager)) > _covered(exact)

    manager.cmd_undo_grid()
    assert manager._tile_crop == 0
    assert _rects(manager) == exact


def test_crop_limit_set_leaves_tiles_moved_since_where_they_are():
    manager = _manager({"A": 2.0, "B": 2.0})
    _free(manager, A=(0, 0, 200, 100), B=(700, 300, 900, 400))
    before = dict(manager._free.tiles)

    manager.cmd_set_tile_crop(0)

    assert manager._free.tiles == before


def test_tiles_arranged_round_a_locked_one_again_stay_where_they_are():
    shapes = {"A": 2.0, "B": 16 / 9, "C": 9 / 16, "D": 4 / 3, "E": 16 / 9, "F": 1.0}
    manager = _manager(shapes)
    _free(
        manager,
        A=(300, 150, 700, 350),
        B=(0, 0, 140, 80),
        C=(800, 20, 940, 100),
        D=(100, 400, 240, 480),
        E=(750, 380, 890, 460),
        F=(400, 0, 540, 80),
    )
    manager._free.set_locked("A", True)

    manager.cmd_arrange_tiles()
    arranged = _rects(manager)
    manager.cmd_arrange_tiles()

    assert _rects(manager) == arranged


def test_reorder_to_fit_arranges_again_tiles_as_arrange_left_them():
    shapes = {"A": 2.0, "B": 9 / 16, "C": 16 / 9, "D": 9 / 16, "E": 16 / 9}
    manager = _manager(shapes)
    _free(
        manager,
        A=(300, 0, 700, 500),
        B=(0, 0, 140, 80),
        C=(800, 20, 940, 100),
        D=(100, 400, 240, 480),
        E=(750, 380, 890, 460),
    )
    manager._free.set_locked("A", True)
    manager.cmd_arrange_tiles()
    kept = _rects(manager)

    manager.cmd_switch_is_grid_reorder()

    assert manager._flow.is_reordered
    reordered = _rects(manager)
    assert reordered != kept
    _approx(reordered["A"], (300, 0, 700, 500))
    assert not _overlapping(reordered)
    # arranged again: the same
    manager.cmd_arrange_tiles()
    assert _rects(manager) == reordered

    manager.cmd_undo_grid()
    assert not manager._flow.is_reordered
    assert _rects(manager) == kept


def test_crop_limit_from_the_settings_arranges_again_as_from_the_menu():
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9}
    manager = _manager(shapes)
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90), C=(100, 300, 250, 390))
    manager.cmd_arrange_tiles()
    from_menu = _manager(shapes)
    _free(from_menu, A=(0, 0, 150, 90), B=(500, 0, 650, 90), C=(100, 300, 250, 390))
    from_menu.cmd_arrange_tiles()

    assert manager.apply_grid_config(
        manager.grid_state().model_copy(update={"tile_crop": 0})
    )
    from_menu.cmd_set_tile_crop(0)

    assert manager._tile_crop == 0
    assert _rects(manager) == _rects(from_menu)
    for video_id, rect in _rects(manager).items():
        assert rect.width / rect.height == pytest.approx(shapes[video_id])


def test_both_arrange_settings_from_the_settings_arrange_again_once(mocker):
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9}
    manager = _manager(shapes)
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90), C=(100, 300, 250, 390))
    manager.cmd_arrange_tiles()
    arrange = mocker.spy(manager, "_arrange")
    changed = mocker.Mock()
    manager.layout_changed.connect(changed)

    assert manager.apply_grid_config(
        manager.grid_state().model_copy(update={"tile_crop": 0, "is_reordered": True})
    )

    assert (manager._tile_crop, manager._flow.is_reordered) == (0, True)
    arrange.assert_called_once()
    # the editor shown where the tiles went
    changed.assert_called()


def _mosaic(shapes, **rects):
    """Mosaic, from Free Tiles with these tiles: arranged."""

    manager = _manager(shapes)
    _free(manager, **rects)
    manager.cmd_set_grid_mode(GridMode.MOSAIC)
    return manager


def _by_hand(manager, video_id, rect):
    """A tile moved, or sized, by hand and let go, as Edit Tiles or a drag
    does it."""

    manager.begin_grid_change()
    _held_at(manager, video_id, rect)
    manager.end_grid_change()


def _held_at(manager, video_id, rect):
    """A tile moved, or sized, there by hand: not let go."""

    manager.set_free_tiles({video_id: Rect(*rect)}, 1000, 500, video_id)


ROW = {"A": 16 / 9, "B": 16 / 9, "C": 16 / 9}
SMALL = {
    "A": (0, 0, 150, 90),
    "B": (300, 0, 450, 90),
    "C": (600, 0, 750, 90),
}


def test_in_mosaic_a_tile_held_put_where_it_was_arranges_nothing_anew(monkeypatch):
    manager = _mosaic(ROW, **SMALL)
    manager.begin_grid_change()
    _held_at(manager, "A", (400, 200, 600, 312))
    shown = _rects(manager)

    calls = []
    real = manager._arranged_around
    monkeypatch.setattr(
        manager, "_arranged_around", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    # snapped there again, say
    _held_at(manager, "A", (400, 200, 600, 312))

    assert not calls
    assert _rects(manager) == shown
    manager.end_grid_change()
    assert _rects(manager) == shown


def test_mosaic_from_free_tiles_arranges_them_and_is_undone():
    manager = _manager(ROW)
    _free(manager, **SMALL)

    manager.cmd_set_grid_mode(GridMode.MOSAIC)

    assert manager.grid_state().mode == GridMode.MOSAIC
    assert manager._is_free
    assert _covered(_rects(manager)) > 0.9 * 1000 * 500
    manager.cmd_undo_grid()
    assert manager.grid_state().mode == GridMode.FREE
    assert _rects(manager)["A"] == pytest.approx(Rect(*SMALL["A"]))


def test_free_tiles_from_mosaic_leaves_them_where_they_are():
    manager = _mosaic(ROW, **SMALL)
    arranged = _rects(manager)

    manager.cmd_set_grid_mode(GridMode.FREE)

    assert _rects(manager) == arranged
    # by hand again: moved, the others stay
    _by_hand(manager, "A", (500, 250, 900, 475))
    assert _rects(manager)["B"] == arranged["B"]


def test_mosaic_from_rows_arranges_the_cells_made_tiles():
    manager = _manager(ROW)
    manager._flow.ids = ["A", "B", "C"]

    manager.cmd_set_grid_mode(GridMode.MOSAIC)

    assert manager._is_mosaic
    assert sorted(manager._free.tiles) == ["A", "B", "C"]
    assert not _overlapping(_rects(manager))


def test_in_mosaic_a_tile_moved_stays_where_it_is_let_go():
    manager = _mosaic(ROW, **SMALL)
    before = _rects(manager)

    _by_hand(manager, "A", (500, 250, 900, 475))

    rects = _rects(manager)
    # stretched to the window's edge over the room under it, too thin for
    # another, and that right of it, which none took: cut less than the
    # crop limit
    _approx(rects["A"], (500, 250, 1000, 500))
    assert not _overlapping(rects)
    assert _covered(rects) > 0.8 * 1000 * 500
    # one change, the arranging with it
    manager.cmd_undo_grid()
    assert _rects(manager) == before


def test_in_mosaic_a_tile_moved_turns_reorder_to_fit_off():
    manager = _mosaic(ROW, **SMALL)
    manager.cmd_switch_is_grid_reorder()

    _by_hand(manager, "A", (500, 250, 900, 475))

    assert not manager._flow.is_reordered


def test_in_mosaic_a_tile_sized_stays_as_made_till_the_next_change():
    shapes = {"A": 16 / 9, "B": 16 / 9, "C": 16 / 9, "D": 16 / 9}
    manager = _mosaic(
        shapes,
        A=(0, 0, 150, 90),
        B=(300, 0, 450, 90),
        C=(0, 300, 150, 390),
        D=(300, 300, 450, 390),
    )
    even = _rects(manager)
    a = even["A"]
    big = Rect(a.left, a.top, a.left + a.width * 1.6, a.top + a.height * 1.6)

    _by_hand(manager, "A", big)

    rects = _rects(manager)
    # where it was made, over the room under it none took
    _approx(rects["A"], (big.left, big.top, big.right, 500))
    assert not _overlapping(rects)
    # no size kept for it: arranged again, as any other
    manager.cmd_arrange_tiles()
    areas = [r.width * r.height for r in _rects(manager).values()]
    assert areas == pytest.approx([areas[0]] * 4)


def test_in_mosaic_a_video_closed_leaves_no_gap():
    manager = _mosaic(ROW, **SMALL)

    del manager._ctx.video_blocks.blocks["B"]
    manager._reconcile_layout()

    rects = _rects(manager)
    assert set(rects) == {"A", "C"}
    # side by side, as wide as the window
    assert rects["A"].width + rects["C"].width == pytest.approx(1000)


def test_in_mosaic_a_tile_locked_or_let_go_moves_nothing():
    manager = _mosaic(ROW, **SMALL)
    before = _rects(manager)

    manager.lock_free_tile("B", True)
    assert _rects(manager) == before
    manager.lock_free_tile("B", False)
    assert _rects(manager) == before


def test_in_mosaic_hand_sizing_actions_are_off():
    manager = _mosaic(ROW, **SMALL)
    manager._active_id = lambda: "A"

    assert not manager.is_tile_space_fillable()
    assert not manager.is_tile_fittable()
    assert not manager.is_tile_room_makeable()


def test_in_mosaic_shapes_coming_in_together_are_arranged_for_once():
    manager = _mosaic({"A": 16 / 9, "B": None, "C": None}, **SMALL)
    manager._unshaped = {"B", "C"}
    arrange = Mock(wraps=manager._arrange)
    manager._arrange = arrange

    for video_id in ("B", "C"):
        manager._ctx.video_blocks.by_video_id(video_id).picture_shape = 1.0
        manager.fit_to_shapes()
    _arranged_when_due(manager)

    arrange.assert_called_once()


def test_in_mosaic_the_window_resized_arranges_them_as_it_goes():
    manager = _mosaic(ROW, **SMALL)

    for width in (900, 800):
        manager._keep_parent.resize(width, 500)
        manager._place_free(width, 500)

        # at once, each size, as Arrange would
        rects = manager._free.rects(width, 500)
        assert not _overlapping(rects)
        assert all(r.right <= width + 0.5 for r in rects.values())
        manager.cmd_arrange_tiles()
        assert manager._free.rects(width, 500) == pytest.approx(rects)

    # and once more when done, for Reorder to Fit
    _arranged_when_due(manager)
    assert manager._free.rects(800, 500) == pytest.approx(rects)
    # the same size: not again
    manager._place_free(800, 500)
    assert not manager._arrange_timer.isActive()


def test_in_mosaic_with_reorder_to_fit_the_window_resized_is_reordered_once_done():
    manager = _mosaic({"A": 16 / 9, "B": 9 / 16, "C": 16 / 9}, **SMALL)
    manager.cmd_switch_is_grid_reorder()
    arrange = Mock(wraps=manager._arrange)
    manager._arrange = arrange

    manager._keep_parent.resize(800, 500)
    manager._place_free(800, 500)
    # as it goes, in the order they are in, which may be quick
    arrange.assert_called_once_with(is_reordered=False)

    _arranged_when_due(manager)
    # once done, reordered
    assert arrange.call_args == ()


def test_in_mosaic_the_others_make_room_as_a_tile_is_moved():
    manager = _mosaic(ROW, **SMALL)
    start = _rects(manager)

    manager.begin_grid_change()
    for left in (300, 400, 500):
        _held_at(manager, "A", (left, 250, left + 400, 475))
        shown = _rects(manager)
        # each time: A where it is moved to, the others round it
        assert shown["A"].left == pytest.approx(left)
        assert not _overlapping(shown)

    manager.end_grid_change()
    assert _rects(manager) == shown
    manager.cmd_undo_grid()
    assert _rects(manager) == start


def test_a_tile_moved_and_put_back_with_esc_leaves_them_all_as_they_were():
    manager = _mosaic(ROW, **SMALL)
    start = _rects(manager)

    manager.begin_grid_change()
    _held_at(manager, "A", (500, 250, 900, 475))
    manager.cancel_grid_change()

    assert _rects(manager) == start


def test_in_mosaic_the_others_make_room_as_a_tile_is_sized():
    manager = _mosaic(ROW, **SMALL)
    start = _rects(manager)
    a = start["A"]

    manager.begin_grid_change()
    _held_at(manager, "A", (a.left, a.top, a.right - 200, a.bottom - 112.5))

    shown = _rects(manager)
    assert shown["B"] != start["B"]
    assert not _overlapping(shown)
    manager.cancel_grid_change()


def test_with_no_room_left_the_others_stay_as_last_shown():
    manager = _mosaic(ROW, **SMALL)

    manager.begin_grid_change()
    _held_at(manager, "A", (0, 0, 700, 400))
    shown = _rects(manager)
    # as big as the window: none for the others
    _held_at(manager, "A", (0, 0, 1000, 500))

    for video_id in ("B", "C"):
        assert _rects(manager)[video_id] == shown[video_id]
    manager.end_grid_change()
    # let go, arranged anew
    assert not _overlapping(_rects(manager))


def test_in_mosaic_there_are_no_size_steps():
    manager = _mosaic(ROW, **SMALL)
    # made bigger in Fit Shapes, say
    manager._flow.sizes = {"A": 2}

    assert not manager.is_grid_cell_sizable()
    assert not manager.is_grid_sized()
    assert not manager.is_grid_cell_sized("A")


def _cut(rect, shape) -> float:
    # how much of a picture of this shape its tile cuts
    stretch = rect.width / rect.height / shape
    return 1 - min(stretch, 1 / stretch)


def test_tiles_from_the_settings_are_where_the_cells_were_by_the_old_options():
    shapes = {"A": 16 / 9, "B": 9 / 16, "C": 16 / 9, "D": 9 / 16}
    manager = _manager(shapes)
    manager.cmd_set_grid_mode(GridMode.AUTO_SHAPES)
    manager._flow.ids = list(shapes)
    cells = dict(manager._cells_now(1000, 500))
    # which would lay them out in another order
    config = manager.grid_state().model_copy(
        update={"mode": GridMode.FREE, "is_reordered": True}
    )

    assert manager.apply_grid_config(config)

    assert manager._free.tiles == cells
    # for when Free Tiles is left
    assert manager._flow.is_reordered


def test_mosaic_from_the_settings_with_a_new_crop_limit_arranges_once(mocker):
    manager = _manager(ROW)
    _free(manager, **SMALL)
    manager.cmd_arrange_tiles()
    arrange = mocker.spy(manager, "_arrange")

    assert manager.apply_grid_config(
        manager.grid_state().model_copy(
            update={"mode": GridMode.MOSAIC, "tile_crop": 0}
        )
    )

    assert manager._tile_crop == 0
    arrange.assert_called_once()


def test_mosaic_from_rows_tells_of_the_new_layout_once():
    manager = _manager(ROW)
    manager._flow.ids = ["A", "B", "C"]
    changed = Mock()
    manager.layout_changed.connect(changed)

    manager.cmd_set_grid_mode(GridMode.MOSAIC)

    changed.assert_called_once()


def test_in_mosaic_a_video_reopened_is_arranged_with_the_others(mocker):
    manager = _mosaic(ROW, **SMALL)
    # left on from Free Tiles
    mocker.patch.object(manager, "tile_overlap", return_value=TileOverlap.ON)
    place = manager.place_of("B")
    manager._free.remove("B")
    manager._arrange()

    manager._put_back("B", place)

    rects = _rects(manager)
    assert set(rects) == {"A", "B", "C"}
    assert not _overlapping(rects)


def test_in_mosaic_a_locked_video_reopened_goes_back_the_others_around_it():
    manager = _mosaic(ROW, **SMALL)
    manager.lock_free_tile("B", True)
    locked = _rects(manager)["B"]
    place = manager.place_of("B")
    manager._free.remove("B")
    manager._arrange()

    manager._put_back("B", place)

    rects = _rects(manager)
    assert rects["B"] == locked
    assert "B" in manager._free.locked
    assert not _overlapping(rects)


def test_in_mosaic_shuffled_they_are_arranged_in_the_new_order(mocker):
    shapes = {"A": 16 / 9, "B": 9 / 16, "C": 16 / 9}
    manager = _mosaic(shapes, **SMALL)
    manager._flow.is_reordered = True
    mocker.patch(
        "gridplayer.utils.layout.free_tiles.random.shuffle",
        side_effect=lambda ids: ids.reverse(),
    )

    manager.cmd_shuffle_layout()

    rects = _rects(manager)
    assert not _overlapping(rects)
    # each tile its own video's shape, within the crop limit
    for video_id, rect in rects.items():
        assert _cut(rect, shapes[video_id]) <= 0.2 + 1e-6
    # kept in the order shuffled
    assert not manager._flow.is_reordered


def test_in_mosaic_a_video_put_in_anothers_tile_is_arranged_for_its_shape():
    manager = _mosaic(ROW, **SMALL)
    blocks = manager._ctx.video_blocks
    block = blocks.by_video_id("B")

    def set_video(_video):
        block.video_id, block.picture_shape = "D", None

    def reindex(_block):
        blocks.blocks = {b.video_id: b for b in blocks.blocks.values()}

    block.set_video = set_video
    blocks.reindex = reindex
    manager.forget_grid_changes = lambda: None

    manager._replace_cell_video(block, ["d.mp4"])
    block.picture_shape = 9 / 16
    manager.fit_to_shapes()
    _arranged_when_due(manager)

    rect = _rects(manager)["D"]
    assert _cut(rect, 9 / 16) <= 0.2 + 1e-6


def test_in_mosaic_tiles_loaded_from_another_size_are_arranged_again():
    manager = _mosaic(ROW, **SMALL)
    state = manager.grid_state()
    manager._keep_parent.resize(800, 500)
    manager._place_free(800, 500)

    # as undo or a playlist puts it back
    manager._load_grid_state(state)
    manager._place_free(800, 500)

    assert manager._arranged_at == (800, 500)
    assert manager._free.is_page_size(800, 500)


def test_a_shape_come_in_after_arrange_is_fitted_if_a_tile_is_moved_first():
    manager = _manager({"A": 16 / 9, "B": None})
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90))
    manager.cmd_arrange_tiles()

    manager._ctx.video_blocks.by_video_id("B").picture_shape = 9 / 16
    manager.fit_to_shapes()
    # no longer as Arrange left them, before it is due
    manager.set_free_tiles({"A": Rect(0, 0, 200, 112.5)}, 1000, 500)
    _arranged_when_due(manager)

    rect = _rects(manager)["B"]
    assert rect.width / rect.height == pytest.approx(9 / 16)


def test_in_mosaic_a_tile_let_go_of_is_not_arranged_again_after():
    manager = _mosaic(ROW, **SMALL)
    manager.begin_grid_change()
    _held_at(manager, "A", (400, 200, 600, 312))
    # a shape came in, or the window was resized, as it went
    manager._arrange_timer.start()

    manager.end_grid_change()

    assert not manager._arrange_timer.isActive()


def test_in_mosaic_a_tile_sized_keeps_the_others_order_and_reorder_goes_off(mocker):
    manager = _mosaic(ROW, **SMALL)
    manager._flow.is_reordered = True
    arrange = mocker.spy(grid_module, "arrange_around")
    a = _rects(manager)["A"]

    manager.begin_grid_change()
    _held_at(manager, "A", (a.left, a.top, a.right + 100, a.bottom + 56.25))

    # as it goes, in the order they are in
    assert arrange.call_args.args[7] is False
    manager.end_grid_change()
    # and so after: as moved
    assert not manager._flow.is_reordered
