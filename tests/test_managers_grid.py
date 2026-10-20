from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.params.static import GridMode
from gridplayer.player.managers.grid import GridManager
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils.layout import GridLayout


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _settings_get(mocker):
    """Answer with the shipped defaults, never with this machine's settings."""

    mocker.patch.object(Settings(), "get", side_effect=_default_settings.__getitem__)


class _Blocks:
    def __init__(self, ids):
        self.video_ids = list(ids)

    def __bool__(self):
        return bool(self.video_ids)

    def __iter__(self):
        return iter(())


def _make_grid_manager(video_ids):
    parent = QWidget()
    commands = SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None)
    ctx = SimpleNamespace(
        video_blocks=_Blocks(video_ids),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=commands,
    )
    manager = GridManager(context=ctx, parent=parent)
    manager._keep_parent = parent
    return manager


def _fixed_two_in_three(manager):
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=3, max_cols=3, preallocate=True)
    manager._grid_layout.pack_flow(["A", "B"])


def test_apply_grid_config_shrink_fixed_closes_overflow(mocker):
    manager = _make_grid_manager(["A", "B"])
    _fixed_two_in_three(manager)
    mocker.patch.object(manager, "_confirm_overflow", return_value=True)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=True)
    )

    assert ok is True
    remove.assert_called_once_with(["B"])
    assert manager._grid_layout.max_rows == 1
    assert manager._grid_layout.max_cols == 1
    assert manager._grid_layout.id_at(0, 0) == "A"
    assert manager._grid_layout.id_at(0, 1) is None


def test_apply_grid_config_shrink_cancel_keeps_videos(mocker):
    manager = _make_grid_manager(["A", "B"])
    _fixed_two_in_three(manager)
    mocker.patch.object(manager, "_confirm_overflow", return_value=False)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=True)
    )

    assert ok is False
    remove.assert_not_called()
    assert manager._grid_layout.max_rows == 3
    assert manager._grid_layout.max_cols == 3
    assert manager._grid_layout.id_at(0, 0) == "A"
    assert manager._grid_layout.id_at(0, 1) == "B"


def test_apply_grid_config_auto_to_fixed_overflow(mocker):
    manager = _make_grid_manager(["A", "B"])
    manager._flow.ids = ["A", "B"]
    mocker.patch.object(manager, "_confirm_overflow", return_value=True)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=False)
    )

    assert ok is True
    remove.assert_called_once_with(["B"])
    assert manager._mode is GridMode.FIXED
    assert manager._grid_layout.id_at(0, 0) == "A"


def test_apply_grid_config_leave_fixed_with_holes(mocker):
    manager = _make_grid_manager(["A", "B"])
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(
        max_rows=3,
        max_cols=3,
        preallocate=False,
        cells=[
            GridCell(video_id="A", row=0, col=0),
            GridCell(video_id="B", row=0, col=2),
        ],
    )
    question = mocker.patch(
        "gridplayer.player.managers.grid.QCustomMessageBox.confirm",
        return_value=True,
    )

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0)
    )

    assert ok is True
    question.assert_called_once()
    assert manager._mode is GridMode.AUTO_ROWS
    assert manager._flow.ids == ["A", "B"]


class _NativeCell(QWidget):
    """A hardware video's cell as the grid sees one: a native window, noting
    where it is each time it comes on screen."""

    def __init__(self, video_id, parent):
        super().__init__(parent)
        self.id = video_id
        self.video_id = video_id
        self.picture_shape = None
        self.shown_at = []
        self.winId()

    def showEvent(self, event):
        self.shown_at.append(self.geometry())


class _Cells:
    def __init__(self, cells):
        self._cells = cells

    @property
    def video_ids(self):
        return [c.video_id for c in self._cells]

    def __bool__(self):
        return bool(self._cells)

    def __iter__(self):
        return iter(self._cells)

    def __len__(self):
        return len(self._cells)

    def by_video_id(self, video_id):
        return next((c for c in self._cells if c.video_id == video_id), None)

    def blocks_for_ids(self, video_ids):
        return [self.by_video_id(i) for i in video_ids if self.by_video_id(i)]


@pytest.mark.parametrize(
    "grid_state",
    [
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
        GridState(mode=GridMode.FIXED, rows=3, cols=3, preallocate=True),
    ],
    ids=["auto", "fixed_with_empty_cells"],
)
def test_new_cells_come_on_screen_in_place(grid_state):
    """A cell is shown where it ends up, not moved there once shown.

    A native window takes the pixels it covers along when it moves, so a
    hardware video's cell shown at the top left and moved into place after
    carried a piece of the window's corner into its cell.
    """
    window = QWidget()
    window.resize(1200, 700)
    ctx = SimpleNamespace(
        video_blocks=_Cells([]),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.set_grid_state(grid_state)
    window.show()
    QApplication.processEvents()

    cells = [_NativeCell(f"v{n}", window) for n in range(5)]
    ctx.video_blocks = _Cells(cells)
    grid.reload_video_grid()

    placed = [c.geometry() for c in cells]
    assert len({r.getRect() for r in placed}) == len(cells)
    assert all(r.width() > 100 for r in placed)
    assert [c.shown_at for c in cells] == [[r] for r in placed]

    window.close()


def test_fixed_cell_spans_its_cells():
    window = QWidget()
    window.resize(900, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.set_grid_state(
        GridState(
            mode=GridMode.FIXED,
            rows=3,
            cols=3,
            preallocate=True,
            cells=[
                GridCell(video_id="v0", row=0, col=0, rowspan=2, colspan=2),
                GridCell(video_id="v1", row=0, col=2),
                GridCell(video_id="v2", row=2, col=2),
            ],
        )
    )

    assert [c.geometry().getRect() for c in cells] == [
        (0, 0, 600, 400),
        (600, 0, 300, 200),
        (600, 400, 300, 200),
    ]
    empties = [grid.grid_position_of(e) for e in grid._empty_cells]
    assert empties == [(1, 2), (2, 0), (2, 1)]

    window.close()


def test_auto_follows_the_shapes_and_the_window():
    window = QWidget()
    window.resize(1200, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.set_grid_state(GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0))
    window.show()
    QApplication.processEvents()

    def rects():
        return [c.geometry().getRect() for c in cells]

    # none known yet: taken as wide
    assert rects() == [(0, 0, 600, 300), (600, 0, 600, 300), (0, 300, 1200, 300)]

    for cell in cells:
        cell.picture_shape = 9 / 16
    grid.fit_to_shapes()
    QApplication.processEvents()
    assert rects() == [(0, 0, 400, 600), (400, 0, 400, 600), (800, 0, 400, 600)]

    for cell in cells:
        cell.picture_shape = 16 / 9
    grid.fit_to_shapes()
    window.resize(600, 1200)
    QApplication.processEvents()
    assert rects() == [(0, 0, 600, 400), (0, 400, 600, 400), (0, 800, 600, 400)]

    window.close()


def test_size_set_by_hand_ignores_the_shapes():
    window = QWidget()
    window.resize(1200, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    for cell in cells:
        cell.picture_shape = 9 / 16
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.set_grid_state(GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=2))

    assert grid.grid_dimensions == (2, 2)
    assert cells[2].geometry().getRect() == (0, 300, 1200, 300)

    window.close()


def test_match_shapes_off_keeps_the_square_grid():
    window = QWidget()
    window.resize(1200, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    for cell in cells:
        cell.picture_shape = 9 / 16
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.layout_changed.connect(grid.reload_video_grid)
    grid.set_grid_state(
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, is_match_shapes=False)
    )
    assert grid.grid_dimensions == (2, 2)
    assert grid.grid_state().is_match_shapes is False

    grid.cmd_switch_is_grid_match_shapes()

    assert grid.grid_dimensions == (3, 1)
    assert cells[2].geometry().getRect() == (800, 0, 400, 600)

    window.close()


def test_fit_shapes_gives_each_video_a_tile_of_its_shape():
    window = QWidget()
    window.resize(1400, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.layout_changed.connect(grid.reload_video_grid)
    # the options of Rows and Columns First make no difference
    grid.set_grid_state(
        GridState(mode=GridMode.AUTO_ROWS, size=1, is_match_shapes=False)
    )
    window.show()
    QApplication.processEvents()

    def rects():
        return [c.geometry().getRect() for c in cells]

    grid.cmd_set_grid_mode(GridMode.AUTO_SHAPES)
    QApplication.processEvents()
    assert grid.grid_state().mode == GridMode.AUTO_SHAPES

    # none known yet: taken as wide, the first big and two beside it, in a
    # column: drops go above and below them
    assert rects() == [(0, 38, 933, 524), (933, 38, 467, 262), (933, 300, 467, 262)]
    assert grid.grid_drop_mode() == GridMode.AUTO_COLS

    cells[0].picture_shape = 9 / 16
    cells[1].picture_shape = 9 / 16
    cells[2].picture_shape = 1.0
    grid.fit_to_shapes()
    QApplication.processEvents()
    # side by side, as high as the window, the space left over at the sides
    assert rects() == [(62, 0, 338, 600), (400, 0, 338, 600), (738, 0, 600, 600)]
    assert grid.grid_drop_mode() == GridMode.AUTO_ROWS

    # in a tall window, the square below
    window.resize(600, 1400)
    QApplication.processEvents()
    assert rects() == [(0, 133, 300, 534), (300, 133, 300, 534), (0, 667, 600, 600)]

    window.close()
