from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.params.static import GridMode
from gridplayer.player.managers.grid import GridManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import GridLayout, Weights
from gridplayer.utils.layout.flow_layout import FlowMode


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

    def blocks_for_ids(self, _video_ids):
        return []


def _make_grid_manager(video_ids):
    parent = QWidget()
    commands = SimpleNamespace(
        remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
    )
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
        self.is_cell_sizable = False
        self.cell_size = SimpleNamespace(
            set_sizable=self._set_cell_sizable, forget_steps=lambda: None
        )
        self.winId()

    def showEvent(self, event):
        self.shown_at.append(self.geometry())

    def _set_cell_sizable(
        self, is_sizable, is_shapable, is_tile=False, is_tile_fillable=True
    ):
        self.is_cell_sizable = is_sizable


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
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
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
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
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

    # their overlays given the buttons to size them
    assert all(c.is_cell_sizable for c in cells)

    window.close()


def test_auto_follows_the_shapes_and_the_window():
    window = QWidget()
    window.resize(1200, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
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
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
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
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
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
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
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


def test_fit_shapes_crops_as_much_as_allowed():
    window = QWidget()
    window.resize(1400, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(3)]
    for cell, shape in zip(cells, (9 / 16, 9 / 16, 1.0)):
        cell.picture_shape = shape
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.layout_changed.connect(grid.reload_video_grid)
    grid.set_grid_state(GridState(mode=GridMode.AUTO_SHAPES))
    window.show()
    QApplication.processEvents()

    def rects():
        return [c.geometry().getRect() for c in cells]

    assert grid.grid_state().crop == 0
    assert rects() == [(62, 0, 338, 600), (400, 0, 338, 600), (738, 0, 600, 600)]

    # the space left at the sides is under 10% of the pictures: all gone
    grid.cmd_set_grid_crop(10)
    QApplication.processEvents()
    assert grid.grid_state().crop == 10
    assert rects() == [(0, 0, 371, 600), (371, 0, 370, 600), (741, 0, 659, 600)]

    grid.set_grid_state(GridState(mode=GridMode.AUTO_SHAPES, crop=5))
    QApplication.processEvents()
    assert grid.grid_state().crop == 5
    assert rects()[0][0] > 0

    window.close()


def _two_cells_grid(shapes, mode=GridMode.AUTO_ROWS, width=1600):
    window = QWidget()
    window.resize(width, 600)
    cells = [_NativeCell(f"v{n}", window) for n in range(len(shapes))]
    for cell, shape in zip(cells, shapes):
        cell.picture_shape = shape
    ctx = SimpleNamespace(
        video_blocks=_Cells(cells),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=SimpleNamespace(
            remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
        ),
    )
    grid = GridManager(context=ctx, parent=window)
    grid.layout_changed.connect(grid.reload_video_grid)
    grid.set_grid_state(GridState(mode=mode, is_match_shapes=False))
    window.show()
    QApplication.processEvents()
    return window, grid, cells


def test_moved_lines_kept_in_the_grid_state():
    window, grid, cells = _two_cells_grid((9 / 16, 16 / 9))

    assert [c.geometry().getRect() for c in cells] == [
        (0, 0, 800, 600),
        (800, 0, 800, 600),
    ]

    lines = grid.grid_lines()
    grid.set_grid_weights(lines.moved(lines.line_at(800, 300, 4), 400))
    QApplication.processEvents()

    assert [c.geometry().getRect() for c in cells] == [
        (0, 0, 400, 600),
        (400, 0, 1200, 600),
    ]
    assert grid.grid_state().col_weights == [0.25, 0.75]
    assert grid.is_grid_lines_moved()

    grid.cmd_reset_grid_lines()
    QApplication.processEvents()
    assert cells[0].geometry().width() == 800
    assert grid.grid_state().col_weights == []

    grid.set_grid_state(GridState(mode=GridMode.AUTO_ROWS, col_weights=[0.25, 0.75]))
    QApplication.processEvents()
    assert cells[0].geometry().width() == 400

    window.close()


def test_fit_lines_to_videos():
    # no room for both whole: the phone video just fits, the wide one has
    # the rest
    window, grid, cells = _two_cells_grid((9 / 16, 16 / 9), width=1400)

    assert grid.is_grid_lines_fittable()

    grid.cmd_fit_grid_lines()
    QApplication.processEvents()

    assert abs(cells[0].geometry().width() - 600 * 9 / 16) <= 1
    assert grid.is_grid_lines_moved()
    # fitted already: nothing more to fit
    assert not grid.is_grid_lines_fittable()

    window.close()


def test_nothing_to_fit_for_videos_the_cells_shape():
    window, grid, _cells = _two_cells_grid((16 / 9, 16 / 9), width=2134)

    assert not grid.is_grid_lines_fittable()

    window.close()


def test_no_lines_to_move_in_fit_shapes():
    window, grid, _cells = _two_cells_grid((9 / 16, 16 / 9), GridMode.AUTO_SHAPES)

    assert grid.grid_lines() is None

    window.close()


def test_unlinked_rows_move_their_lines_alone():
    window, grid, cells = _two_cells_grid((16 / 9,) * 4, width=1000)

    grid.cmd_switch_is_grid_link()
    QApplication.processEvents()
    assert grid.grid_state().is_linked is False

    # the top row's line
    lines = grid.grid_lines()
    grid.set_grid_weights(lines.moved(lines.line_at(500, 150, 4), 300))
    QApplication.processEvents()

    assert [c.geometry().width() for c in cells] == [300, 700, 500, 500]
    assert grid.grid_state().line_weights == [[0.3, 0.7], [0.5, 0.5]]

    # linked again, where the rows are on average
    grid.cmd_switch_is_grid_link()
    QApplication.processEvents()

    assert [c.geometry().width() for c in cells] == [400, 600, 400, 600]
    assert grid.grid_state().line_weights == []
    assert grid.grid_state().col_weights == [0.4, 0.6]

    window.close()


def test_unlinked_fit_fits_each_row():
    # a phone video then a wide one, over a wide one then a phone video:
    # no room for both whole in a row
    window, grid, cells = _two_cells_grid((9 / 16, 16 / 9, 16 / 9, 9 / 16), width=600)
    grid.cmd_switch_is_grid_link()
    QApplication.processEvents()

    grid.cmd_fit_grid_lines()
    QApplication.processEvents()

    assert abs(cells[0].geometry().width() - 300 * 9 / 16) <= 1
    assert abs(cells[3].geometry().width() - 300 * 9 / 16) <= 1
    assert not grid.is_grid_lines_fittable()

    window.close()


def test_fixed_grid_lines_move_at_once():
    window, grid, cells = _two_cells_grid((9 / 16, 16 / 9), width=1500)
    grid.set_grid_state(
        GridState(
            mode=GridMode.FIXED,
            rows=1,
            cols=3,
            preallocate=True,
            cells=[
                GridCell(video_id="v0", row=0, col=0),
                GridCell(video_id="v1", row=0, col=1),
            ],
        )
    )
    QApplication.processEvents()
    (empty,) = grid._empty_cells
    assert empty.geometry().getRect() == (1000, 0, 500, 600)

    # the line between the second video and the empty cell
    lines = grid.grid_lines()
    grid.set_grid_weights(lines.moved(lines.line_at(1000, 300, 4), 1200))
    QApplication.processEvents()

    assert cells[1].geometry().getRect() == (500, 0, 700, 600)
    assert empty.geometry().getRect() == (1200, 0, 300, 600)

    # and found where it is now, on the cells' edges
    lines = grid.grid_lines()
    assert lines.line_at(1200, 300, 4) is not None
    assert lines.line_at(1000, 300, 4) is None

    window.close()


def _cell_spans(manager):
    return sorted(
        (c.video_id, c.row, c.col, c.rowspan, c.colspan)
        for c in manager._grid_layout.cells
    )


def test_template_from_auto_and_undo(mocker):
    manager = _make_grid_manager(list("ABCDEFG"))
    manager._flow.ids = list("ABCDEFG")
    mocker.patch.object(manager, "_confirm_overflow", return_value=True)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    manager.cmd_set_grid_template("1 + 5")

    remove.assert_called_once_with(["G"])
    assert manager._mode is GridMode.FIXED
    assert manager.is_grid_template("1 + 5")
    assert ("A", 0, 0, 2, 2) in _cell_spans(manager)

    manager.cmd_undo_grid()
    assert manager._mode is GridMode.AUTO_ROWS
    manager.cmd_redo_grid()
    assert manager.is_grid_template("1 + 5")


def test_a_change_that_closes_videos_is_not_undone(mocker):
    # closing them forgets the changes, as the player has it, in the middle
    manager = _make_grid_manager(list("ABCDEFG"))
    manager._flow.ids = list("ABCDEFG")
    manager.cmd_shuffle_layout()
    mocker.patch.object(manager, "_confirm_overflow", return_value=True)
    mocker.patch.object(
        manager._ctx.commands,
        "remove_video_blocks",
        side_effect=lambda _ids: manager.forget_grid_changes(),
    )

    manager.cmd_set_grid_template("1 + 5")

    assert manager.is_grid_template("1 + 5")
    assert not manager.commands["is_grid_undoable"]()


def test_a_line_dragged_is_one_change_to_undo():
    manager = _make_grid_manager(["A", "B"])
    _fixed_two_in_three(manager)

    manager.begin_grid_change()
    manager.set_grid_weights(Weights((0.2, 0.3, 0.5), ()))
    manager.set_grid_weights(Weights((0.4, 0.3, 0.3), ()))
    manager.end_grid_change()
    manager.end_grid_change()

    assert len(manager._undo) == 1
    manager.cmd_undo_grid()
    assert manager.grid_state().col_weights == []


def test_template_cancelled_changes_nothing(mocker):
    manager = _make_grid_manager(list("ABCDEFG"))
    manager._flow.ids = list("ABCDEFG")
    mocker.patch.object(manager, "_confirm_overflow", return_value=False)

    manager.cmd_set_grid_template("1 + 5")

    assert manager._mode is GridMode.AUTO_ROWS
    assert not manager.commands["is_grid_undoable"]()


def test_make_the_active_cell_bigger_and_undo(mocker):
    manager = _make_grid_manager(list("ABCDEF"))
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=3, max_cols=3)
    manager._grid_layout.pack_flow(list("ABCDEF"))
    before = _cell_spans(manager)
    manager._ctx.active_block = SimpleNamespace(video_id="B")

    assert manager.is_grid_cell_steppable("bigger")
    assert not manager.is_grid_cell_steppable("smaller")
    manager.cmd_step_grid_cell("bigger")

    assert ("B", 0, 1, 2, 2) in _cell_spans(manager)
    assert manager.is_grid_cell_steppable("smaller")

    manager.cmd_undo_grid()
    assert _cell_spans(manager) == before
    assert not manager.commands["is_grid_undoable"]()
    assert manager.commands["is_grid_redoable"]()

    manager.cmd_redo_grid()
    assert ("B", 0, 1, 2, 2) in _cell_spans(manager)


def test_no_room_to_make_it_bigger_warns():
    manager = _make_grid_manager(list("ABCD"))
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=2, max_cols=2)
    manager._grid_layout.pack_flow(list("ABCD"))
    manager._ctx.active_block = SimpleNamespace(video_id="A")
    warnings = []
    manager.warning.connect(warnings.append)

    manager.cmd_step_grid_cell("bigger")

    assert warnings
    assert manager._grid_layout.span_of("A") == (1, 1)
    assert not manager.commands["is_grid_undoable"]()


def test_a_cell_made_wider_by_its_own_button():
    manager = _make_grid_manager(list("ABC"))
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=2, max_cols=3)
    manager._grid_layout.pack_flow(list("ABC"))

    # not the active one: the one whose button it is
    manager._ctx.active_block = SimpleNamespace(video_id="A")
    manager.cmd_step_grid_cell("wider", "C")

    assert manager.grid_cell_span("C") == (1, 2)
    assert manager.grid_cell_span("A") == (1, 1)

    assert manager.can_set_grid_cell_span("C", 2, 2)
    assert not manager.can_set_grid_cell_span("C", 2, 3)


def test_cells_are_sized_only_in_a_fixed_grid_shown_whole():
    manager = _make_grid_manager(list("AB"))
    manager._grid_layout = GridLayout(max_rows=2, max_cols=2)
    manager._grid_layout.pack_flow(list("AB"))
    manager._ctx.active_block = SimpleNamespace(video_id="A")

    manager._mode = GridMode.AUTO_ROWS
    assert not manager.is_grid_cell_sizable()

    manager._mode = GridMode.FIXED
    assert manager.is_grid_cell_sizable()

    manager._ctx.is_single_mode = True
    assert not manager.is_grid_cell_sizable()
    assert not manager.is_grid_cell_steppable("bigger")


def test_undo_takes_back_the_grid_options_too():
    manager = _make_grid_manager(list("AB"))
    manager._flow.ids = list("AB")

    manager.cmd_switch_is_grid_fit()
    manager.cmd_set_grid_mode(GridMode.AUTO_COLS)
    assert manager.grid_state().is_fit is not GridState().is_fit

    manager.cmd_undo_grid()
    manager.cmd_undo_grid()

    state = manager.grid_state()
    assert state.mode is GridMode.AUTO_ROWS
    assert state.is_fit is GridState().is_fit
    assert PlaylistSettings().get("playlist/grid_fit") is state.is_fit
    assert PlaylistSettings().get("playlist/grid_mode") is GridMode.AUTO_ROWS


def test_a_new_grid_state_or_other_videos_forget_the_changes(mocker):
    manager = _make_grid_manager(list("AB"))
    mocker.patch.object(manager, "_render_video_grid")
    manager._flow.ids = list("AB")

    manager.cmd_switch_is_grid_fit()
    manager.cmd_undo_grid()
    assert manager.commands["is_grid_redoable"]()

    manager.set_grid_state(GridState(video_order=list("AB")))
    assert not manager.commands["is_grid_redoable"]()

    manager.cmd_switch_is_grid_fit()
    manager.forget_grid_changes()
    assert not manager.commands["is_grid_undoable"]()


def test_editing_cells_from_auto(mocker):
    manager = _make_grid_manager(list("ABCD"))
    manager._flow.ids = list("ABCD")
    layout_changed = mocker.Mock()
    manager.layout_changed.connect(layout_changed)

    assert manager.make_grid_fixed()
    assert manager._mode is GridMode.FIXED
    assert (manager._grid_layout.max_rows, manager._grid_layout.max_cols) == (2, 2)

    manager.set_grid_editing(True)
    assert not manager.can_resize_fixed_grid(1, 2)
    assert manager.cmd_resize_fixed_grid(2, 3)
    assert manager.cmd_place_grid_cell("A", 0, 0, 1, 2)
    assert manager._grid_layout.position_of("B") == (0, 2)
    assert not manager.cmd_place_grid_cell("A", 0, 0, 2, 2)
    manager.set_grid_editing(False)

    # each a change of its own, back to the Auto grid
    for _ in range(3):
        manager.cmd_undo_grid()
    assert manager._mode is GridMode.AUTO_ROWS
    assert not manager.commands["is_grid_undoable"]()


def test_sizes_reset_at_once_and_undone():
    manager = _make_grid_manager(list("ABCD"))
    manager._mode = GridMode.AUTO_SHAPES
    manager._flow.mode = FlowMode.SHAPES
    manager._flow.ids = list("ABCD")
    manager._flow.sizes = {"A": 2, "C": -1}

    assert manager.is_grid_sized()
    manager.cmd_reset_grid_sizes()

    assert not manager.is_grid_sized()
    assert manager.grid_state().sizes == {}

    manager.cmd_undo_grid()
    assert manager.grid_state().sizes == {"A": 2, "C": -1}


def test_reset_size_of_a_cell_and_of_the_grid_in_a_fixed_grid():
    manager = _make_grid_manager(list("ABC"))
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=3, max_cols=3)
    manager._grid_layout.pack_flow(list("ABC"))
    manager._grid_layout.set_span("A", 2, 2)
    manager._grid_layout.set_span("C", 1, 2)
    c_at = manager._grid_layout.position_of("C")

    assert manager.is_grid_sized()
    assert manager.is_grid_cell_sized("A")
    assert not manager.is_grid_cell_sized("B")

    manager.cmd_reset_grid_cell_size("A")
    assert manager.grid_cell_span("A") == (1, 1)
    assert manager.grid_cell_span("C") == (1, 2)

    manager.cmd_reset_grid_sizes()
    assert not manager.is_grid_sized()
    assert manager._grid_layout.position_of("C") == c_at

    manager.cmd_undo_grid()
    assert manager.grid_cell_span("C") == (1, 2)


def test_reset_size_of_a_video_in_fit_shapes():
    manager = _make_grid_manager(list("ABCD"))
    manager._mode = GridMode.AUTO_SHAPES
    manager._flow.mode = FlowMode.SHAPES
    manager._flow.ids = list("ABCD")
    manager._flow.sizes = {"A": 2, "C": -1}

    manager.cmd_reset_grid_cell_size("A")

    assert manager.grid_state().sizes == {"C": -1}
    assert not manager.is_grid_cell_sized("A")


def test_undo_told_once_it_can_be_undone():
    # the editor's bar looks then, not when the grid is laid out, which is
    # before the change is kept
    manager = _make_grid_manager(list("ABCD"))
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=3, max_cols=3)
    manager._grid_layout.pack_flow(list("ABCD"))

    seen = []
    manager.undo_changed.connect(
        lambda: seen.append(manager.commands["is_grid_undoable"]())
    )

    manager.cmd_step_grid_cell("bigger", "A")
    assert seen == [True]

    manager.forget_grid_changes()
    assert seen == [True, False]


def test_bigger_in_fit_shapes_is_kept_in_the_grid_state_and_undone():
    manager = _make_grid_manager(list("ABCDEFGH"))
    manager._mode = GridMode.AUTO_SHAPES
    manager._flow.mode = FlowMode.SHAPES
    manager._flow.ids = list("ABCDEFGH")
    manager._flow.fit_to(1600, 900, {})
    manager._ctx.active_block = SimpleNamespace(video_id="B")

    assert manager.is_grid_cell_sizable()
    assert not manager.is_grid_cell_shapable()
    assert manager.is_grid_cell_steppable("bigger")
    assert not manager.is_grid_cell_steppable("wider")

    manager.cmd_step_grid_cell("bigger")
    assert manager.grid_state().sizes["B"] > 0

    manager.cmd_undo_grid()
    assert manager.grid_state().sizes == {}


def test_a_drop_turns_reorder_to_fit_off_and_stays():
    ids = list("ABCDEF")
    manager = _make_grid_manager(ids)
    manager._mode = GridMode.AUTO_SHAPES
    manager._flow.mode = FlowMode.SHAPES
    manager._flow.ids = list(ids)
    manager._flow.is_reordered = True
    manager._flow.fit_to(1920, 1080, dict(zip(ids, [16 / 9, 9 / 16] * 3)))
    shown = [video_id for video_id, _box in manager._flow.boxes()]
    assert shown != ids

    manager.cmd_layout_drop(
        [],
        SimpleNamespace(video_id="A"),
        SimpleNamespace(video_id="F"),
        DropZone.AFTER,
        False,
    )

    assert not manager.grid_state().is_reordered
    assert not PlaylistSettings().get("playlist/grid_reorder")
    moved = [i for i in shown if i != "A"]
    moved.insert(moved.index("F") + 1, "A")
    assert manager._flow.ids == moved


def _reordered(ids):
    manager = _make_grid_manager(ids)
    manager._mode = GridMode.AUTO_SHAPES
    manager._flow.mode = FlowMode.SHAPES
    manager._flow.ids = list(ids)
    manager._flow.is_reordered = True
    manager._flow.fit_to(1920, 1080, dict(zip(ids, [16 / 9, 9 / 16] * 3)))
    return manager


def test_a_video_dropped_back_on_itself_keeps_reorder_to_fit():
    manager = _reordered(list("ABCDEF"))
    block = SimpleNamespace(video_id="A")

    manager.cmd_layout_drop([], block, block, DropZone.CENTER, False)

    assert manager.grid_state().is_reordered
    assert not manager.commands["is_grid_undoable"]()


def test_edited_as_a_fixed_grid_the_videos_stay_where_they_are_shown():
    manager = _reordered(list("ABCDEF"))
    shown = manager._flow.order()
    assert shown != list("ABCDEF")
    PlaylistSettings().set("playlist/grid_preallocate", True)

    assert manager.make_grid_fixed()

    assert manager._grid_layout.order() == shown
    # Show All Cells as the grid has it
    assert not PlaylistSettings().get("playlist/grid_preallocate")


def test_no_undo_while_a_line_is_held():
    manager = _make_grid_manager(["A", "B"])
    _fixed_two_in_three(manager)
    manager.cmd_reset_grid_lines()
    manager.cmd_set_grid_cell_span("A", 2, 2)

    manager.begin_grid_change()
    manager.set_grid_weights(Weights((0.2, 0.3, 0.5), ()))
    manager.cmd_undo_grid()
    manager.end_grid_change()

    assert manager._grid_layout.span_of("A") == (2, 2)
    manager.cmd_undo_grid()
    assert manager.grid_state().col_weights == []
    manager.cmd_undo_grid()
    assert manager._grid_layout.span_of("A") == (1, 1)


def test_undone_after_editing_the_grid_has_no_empty_band():
    manager = _make_grid_manager(["A"])
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=3, max_cols=3)
    manager._grid_layout.pack_flow(["A"])
    manager.set_grid_editing(True)
    manager.cmd_place_grid_cell("A", 1, 1, 1, 1)
    manager.cmd_place_grid_cell("A", 2, 2, 1, 1)
    manager.set_grid_editing(False)

    # to A where the first move left it, a row and a column from the top
    manager.cmd_undo_grid()

    assert manager._grid_layout.position_of("A") == (0, 0)
    assert manager._grid_layout.displayed_size() == (1, 1)


def test_reorder_to_fit_is_a_grid_option():
    manager = _make_grid_manager(list("AB"))
    manager._mode = GridMode.AUTO_SHAPES

    manager.cmd_switch_is_grid_reorder()

    assert manager.grid_state().is_reordered
    assert PlaylistSettings().get("playlist/grid_reorder")

    manager.cmd_undo_grid()
    assert not manager.grid_state().is_reordered
