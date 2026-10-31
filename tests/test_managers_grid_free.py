import contextlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.params.static import GridMode, TileOverlap, TileResize
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
    # as Arrange Tiles does: filling the page
    assert _covered(rects) == pytest.approx(1000 * 500)


def test_videos_with_no_room_are_arranged_as_the_tiles_were_last():
    manager = _manager({"A": 2.0, "B": 2.0, "C": 2.0})
    _free(manager, A=(0, 0, 500, 500), B=(500, 0, 1000, 500))
    manager.cmd_arrange_tiles_uncropped()
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

    manager.cmd_arrange_tiles_uncropped()

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
@pytest.mark.parametrize(
    "arrange", ["cmd_arrange_tiles", "cmd_arrange_tiles_uncropped"]
)
def test_tiles_arranged_again_stay_where_they_are(rects, arrange):
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9, "D": 1.0}
    manager = _manager({i: shapes[i] for i in rects})
    _free(manager, **rects)

    getattr(manager, arrange)()
    arranged = _rects(manager)
    getattr(manager, arrange)()

    assert _rects(manager) == arranged


def test_arranged_tiles_fill_the_page_and_can_be_undone():
    shapes = {"A": 16 / 9, "B": 3 / 4, "C": 16 / 9}
    manager = _manager(shapes)
    _free(manager, A=(0, 0, 150, 90), B=(500, 0, 650, 90), C=(100, 300, 250, 390))

    manager.cmd_arrange_tiles_uncropped()
    exact = _rects(manager)
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

    assert _covered(_rects(manager)) == pytest.approx(1000 * 500)


def test_tiles_arranged_before_the_shapes_were_known_are_arranged_again():
    manager = _manager({"A": None, "B": None})
    manager._mode = GridMode.FREE

    manager._reconcile_layout()
    for block in manager._ctx.video_blocks:
        block.picture_shape = 1.0
    manager.fit_to_shapes()

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

    manager.cmd_arrange_tiles_uncropped()

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
