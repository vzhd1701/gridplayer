import contextlib
import dataclasses
import random
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from PyQt5 import sip
from PyQt5.QtCore import QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QRegion
from PyQt5.QtWidgets import QMessageBox

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput, QFixedGridSizeDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.grid_state import GridCell, GridState, GridTile
from gridplayer.params.settings_bindings import GRID_STATE_ATTR
from gridplayer.params.static import (
    GRID_TEMPLATES,
    MAX_FIXED_SIZE,
    TILED_MODES,
    GridMode,
    GridTemplate,
    TileOverlap,
    TileResize,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import (
    EVEN,
    FULL_BOX,
    Box,
    CellLayout,
    FlowLayout,
    FlowMode,
    GridLayout,
    Layout,
    Weights,
    grid_box,
)
from gridplayer.utils.layout.arrange import ArrangeCache, arrange_around
from gridplayer.utils.layout.flow_layout import DEFAULT_SHAPE
from gridplayer.utils.layout.free_tiles import FreeTiles, Rect, TilePlace
from gridplayer.utils.layout.lines import (
    MIN_CELL,
    FitCell,
    GridLines,
    MovableLines,
    Span,
    fit_weights,
)
from gridplayer.utils.layout.strip import (
    StripLines,
    StripVideos,
    shape_of_strip,
    strip_layout,
    strip_share,
)
from gridplayer.utils.qt import count_txt, topmost, translate
from gridplayer.widgets.empty_cell import EmptyCell
from gridplayer.widgets.held_place import HeldPlace

# how many changes of the grid can be undone
UNDO_LIMIT = 50

# a video's cell made a step bigger or smaller: rows and columns more
CELL_STEPS = {
    "bigger": (1, 1),
    "smaller": (-1, -1),
    "wider": (0, 1),
    "narrower": (0, -1),
    "taller": (1, 0),
    "shorter": (-1, 0),
}

# in Fit Shapes, where a video's tile is its shape, only bigger and smaller
# (see FlowLayout.size_step)
SHAPES_STEPS = {"bigger": 1, "smaller": -1}


class GridDimensions(NamedTuple):
    cols: int
    rows: int

    @property
    def max_size(self):
        return self.cols * self.rows


class FreePage(NamedTuple):
    """The tiles of Free Tiles, and where their page is on the screen."""

    tiles: FreeTiles
    rect: QRect


def _flow_mode(mode: GridMode) -> FlowMode:
    if mode == GridMode.AUTO_COLS:
        return FlowMode.COLS
    if mode == GridMode.AUTO_SHAPES:
        return FlowMode.SHAPES
    return FlowMode.ROWS


# in ms: shapes that come in, or the window resized, within this of each
# other, arranged for once (Mosaic, or the tiles as Arrange left them)
ARRANGE_DELAY = 200


@dataclasses.dataclass
class _Holding:
    """A tile held in Mosaic, in the change going on: the others arranged
    around it as it goes (see GridManager._arrange_live)."""

    video_id: str
    # the others where they were at its start, read there (see _read_at)
    start: dict[str, Box]
    cache: ArrangeCache = dataclasses.field(default_factory=ArrangeCache)
    # whether the others were arranged around it, the last time
    is_live: bool = False
    # where it was put the last time, in an area of what size, and where
    # it went then (see _arrange_live)
    last: tuple[tuple[Rect, float, float], Rect] | None = None


class GridManager(ManagerBase):
    warning = pyqtSignal(str)
    layout_changed = pyqtSignal()
    # what there is to undo or redo
    undo_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.grid_state = self.grid_state

        mode = Settings().get("playlist/grid_mode")
        self._mode = mode
        self._grid_layout = GridLayout(
            max_rows=Settings().get("playlist/grid_rows"),
            max_cols=Settings().get("playlist/grid_cols"),
            preallocate=Settings().get("playlist/grid_preallocate"),
        )
        self._flow = FlowLayout(
            mode=_flow_mode(mode),
            size=Settings().get("playlist/grid_size"),
            is_fit=Settings().get("playlist/grid_fit"),
            is_match_shapes=Settings().get("playlist/grid_match_shapes"),
            crop=Settings().get("playlist/grid_crop"),
            is_linked=Settings().get("playlist/grid_link"),
            is_reordered=Settings().get("playlist/grid_reorder"),
        )
        # the lines between the cells, moved by hand
        self._weights = EVEN
        # in Single Mode, the strip's share of the window, moved by hand
        self._strip_share: float | None = None

        # in Free Tiles, the tiles placed by hand
        self._free = FreeTiles(resize=Settings().get("playlist/tile_resize"))
        self._free.shape_of = self._shape_of
        # the videos given tiles before their shapes were known, and whether
        # the tiles are still as Arrange left them (see _fit_tiles_to_shapes)
        self._unshaped: set[str] = set()
        self._is_arranged = False
        # how much of each picture Arrange Tiles may cut to fill the room,
        # in percent
        self._tile_crop: int = Settings().get("playlist/tile_crop")
        # in Mosaic, the tile moved or sized by hand in the change going on
        # (see set_free_tiles)
        self._holding: _Holding | None = None
        # the size of the area the tiles were last arranged in
        self._arranged_at: tuple[int, int] | None = None
        self._arrange_timer = QTimer(self)
        self._arrange_timer.setSingleShot(True)
        self._arrange_timer.setInterval(ARRANGE_DELAY)
        self._arrange_timer.timeout.connect(self._arrange_due)

        # the last lines fit_weights found, and for what: asked for each
        # time the menu is made, to say whether fitting would change them
        self._fitted: tuple[tuple, Weights] | None = None

        # the grid as it was before each change made to it, and as it was
        # before each undone, to undo or redo (see _undoable)
        self._undo: list[GridState] = []
        self._redo: list[GridState] = []
        # as it was when a change made over time began (see
        # begin_grid_change), and how many times the changes were
        # forgotten: one going on then is not to be undone either
        self._change_start: tuple[GridState, int] | None = None
        self._forgotten = 0

        self._empty_cells = []
        self._empty_positions = {}
        self._add_anchor = None
        self._reloading = False

        self._grid = CellLayout(self.parent())
        self._grid.laid_out.connect(self._stack_tiles)
        self._grid.laid_out.connect(self._forget_cell_steps)
        # the videos one over another as the tiles were the last time, and
        # those whose overlays were cut where others covered them
        self._stacked: list = []
        self._cut: set = set()

        self._info_label = EmptyCell(
            message=translate("Main Window", "Drag and drop media files or URLs here"),
            parent=self.parent(),
        )
        # in the Fixed Strip, the place of the video shown big
        self._held_place = HeldPlace(parent=self.parent())
        self._held_place.hide()

    def init(self):
        self.layout_changed.emit()

    # --- commands / public queries ---

    @property
    def commands(self):
        return {
            "set_grid_mode": self.cmd_set_grid_mode,
            "strip_held_video_at": self.strip_held_video_at,
            "is_grid_mode_set_to": lambda m: self._mode == m,
            "grid_drop_mode": self.grid_drop_mode,
            "ask_grid_size": self.cmd_ask_grid_size,
            "get_grid_size": self.cmd_get_grid_size,
            "switch_is_grid_fit": self.cmd_switch_is_grid_fit,
            "is_grid_fit": lambda: self._flow.is_fit,
            "switch_is_grid_match_shapes": self.cmd_switch_is_grid_match_shapes,
            "is_grid_match_shapes": lambda: self._flow.is_match_shapes,
            "is_grid_size_auto": lambda: self._flow.size == 0,
            "switch_is_grid_link": self.cmd_switch_is_grid_link,
            "is_grid_link": lambda: self._flow.is_linked,
            "set_grid_crop": self.cmd_set_grid_crop,
            "is_grid_crop_set_to": lambda crop: self._flow.crop == crop,
            "switch_is_grid_reorder": self.cmd_switch_is_grid_reorder,
            "is_grid_reorder": lambda: self._flow.is_reordered,
            "reset_grid_sizes": self.cmd_reset_grid_sizes,
            "is_grid_sized": self.is_grid_sized,
            "reset_grid_cell_size": self.cmd_reset_grid_cell_size,
            "is_grid_cell_sized": self.is_grid_cell_sized,
            "is_grid_preallocate": lambda: self._grid_layout.preallocate,
            "switch_grid_preallocate": self.cmd_switch_grid_preallocate,
            "ask_fixed_grid_size": self.cmd_ask_fixed_grid_size,
            "get_fixed_grid_size": self.cmd_get_fixed_grid_size,
            "add_videos_to_layout": self.add_videos_to_layout,
            "grid_free_capacity": lambda: self._layout.free_capacity(),
            "grid_place_of": self.place_of,
            "put_back_videos": self.put_back_videos,
            "layout_drop": self.cmd_layout_drop,
            "layout_order": lambda: self._layout.order(),
            "shuffle_layout": self.cmd_shuffle_layout,
            "get_cell_at": self.get_cell_at,
            "set_add_anchor": self.set_add_anchor,
            "grid_cell_count": lambda: self.grid_dimensions.max_size,
            "set_grid_state": self.set_grid_state,
            "apply_grid_config": self.apply_grid_config,
            "grid_lines": self.grid_lines,
            "movable_lines": self.movable_lines,
            "grid_area": self.grid_area,
            "set_grid_weights": self.set_grid_weights,
            "fit_grid_lines": self.cmd_fit_grid_lines,
            "reset_grid_lines": self.cmd_reset_grid_lines,
            "is_grid_lines_fittable": self.is_grid_lines_fittable,
            "is_grid_lines_moved": self.is_grid_lines_moved,
            "step_grid_cell": self.cmd_step_grid_cell,
            "is_grid_cell_steppable": self.is_grid_cell_steppable,
            "is_grid_cell_sizable": self.is_grid_cell_sizable,
            "is_grid_cell_shapable": self.is_grid_cell_shapable,
            "grid_cell_span": self.grid_cell_span,
            "grid_cell_room": self.grid_cell_room,
            "set_grid_cell_span": self.cmd_set_grid_cell_span,
            "can_set_grid_cell_span": self.can_set_grid_cell_span,
            "set_grid_template": self.cmd_set_grid_template,
            "is_grid_template": self.is_grid_template,
            "apply_grid_template": self.cmd_apply_grid_template,
            "is_grid_shaped_as": self.is_grid_shaped_as,
            "grid_template_now": self.grid_template_now,
            "undo_grid": self.cmd_undo_grid,
            "redo_grid": self.cmd_redo_grid,
            "is_grid_undoable": lambda: bool(self._undo),
            "is_grid_redoable": lambda: bool(self._redo),
            "begin_grid_change": self.begin_grid_change,
            "cancel_grid_change": self.cancel_grid_change,
            "end_grid_change": self.end_grid_change,
            "is_grid_fixed": lambda: self._is_fixed,
            "make_grid_fixed": self.make_grid_fixed,
            "set_grid_editing": self.set_grid_editing,
            "place_grid_cell": self.cmd_place_grid_cell,
            "can_place_grid_cell": self.can_place_grid_cell,
            "resize_fixed_grid": self.cmd_resize_fixed_grid,
            "can_resize_fixed_grid": self.can_resize_fixed_grid,
            "is_grid_free": lambda: self._is_free,
            "free_page": self.free_page,
            "set_free_tiles": self.set_free_tiles,
            "arrange_tiles": self.cmd_arrange_tiles,
            "tile_crop": lambda: self._tile_crop,
            "set_tile_crop": self.cmd_set_tile_crop,
            "is_tile_crop": lambda crop: self._tile_crop == crop,
            "fit_tiles_to_window": self.cmd_fit_tiles_to_window,
            "tile_resize": lambda: self._free.resize,
            "set_tile_resize": self.cmd_set_tile_resize,
            "is_tile_resize": lambda resize: self._free.resize == resize,
            "tile_overlap": self.tile_overlap,
            "is_tile_overlap": lambda overlap: self.tile_overlap() == overlap,
            "set_tile_overlap": self.set_tile_overlap,
            "is_tiles_stacked": self.is_tiles_stacked,
            "is_tile_stackable": self.is_tile_stackable,
            "stack_tile": self.cmd_stack_tile,
            "stack_free_tile": self.stack_free_tile,
            "is_tile_lockable": self.is_tile_lockable,
            "is_tile_locked": self.is_tile_locked,
            "lock_tile": self.cmd_lock_tile,
            "lock_free_tile": self.lock_free_tile,
            "fill_tile_space": self.cmd_fill_tile_space,
            "is_tile_space_fillable": self.is_tile_space_fillable,
            "fit_tile_to_video": self.cmd_fit_tile_to_video,
            "is_tile_fittable": self.is_tile_fittable,
            "is_tile_room_makeable": self.is_tile_room_makeable,
            "make_room": self.cmd_make_room,
            "bring_free_tile_to_front": self.bring_free_tile_to_front,
        }

    @property
    def _is_fixed(self):
        return self._mode == GridMode.FIXED

    @property
    def _is_free(self):
        # tiles of their own: Free Tiles, or Mosaic
        return self._mode in TILED_MODES

    @property
    def _is_mosaic(self):
        # the tiles arranged after each change, and as it goes
        return self._mode == GridMode.MOSAIC

    @property
    def _is_kept_arranged(self) -> bool:
        # arranged again as shapes come in, the window is resized, or how
        # they are arranged changes: in Mosaic, or as Arrange left them
        return self._is_mosaic or (self._is_free and self._is_arranged)

    @property
    def _layout(self) -> Layout:
        if self._is_free:
            return self._free
        return self._grid_layout if self._is_fixed else self._flow

    @property
    def grid_dimensions(self):
        cols, rows = self._layout.displayed_size()
        return GridDimensions(cols, rows)

    @property
    def _show_empties(self):
        return self._is_fixed and self._grid_layout.shows_every_cell

    @contextlib.contextmanager
    def slow_ui_operation(self):
        self.parent().setUpdatesEnabled(False)
        try:
            yield
        finally:
            self.parent().setUpdatesEnabled(True)

    def grid_state(self):
        return GridState(
            mode=self._mode,
            is_fit=self._flow.is_fit,
            is_match_shapes=self._flow.is_match_shapes,
            crop=self._flow.crop,
            is_reordered=self._flow.is_reordered,
            is_linked=self._flow.is_linked,
            size=self._flow.size,
            video_order=list(self._flow.ids),
            sizes=self._flow.sized(),
            rows=self._grid_layout.max_rows,
            cols=self._grid_layout.max_cols,
            preallocate=self._grid_layout.preallocate,
            cells=list(self._grid_layout.cells),
            col_weights=list(self._weights.cols),
            row_weights=list(self._weights.rows),
            line_weights=[list(weights) for weights in self._weights.lines],
            strip_share=self._strip_share,
            tiles=[
                GridTile(video_id=video_id, box=list(box))
                for video_id, box in self._free.tiles.items()
            ],
            page_shape=self._free.page_shape if self._free.tiles else None,
            page_height=self._free.page_height if self._free.tiles else None,
            locked_tiles=[i for i in self._free.tiles if i in self._free.locked],
            tile_resize=self._free.resize,
            tile_crop=self._tile_crop,
            is_tiles_as_placed=self._free.is_as_placed,
        )

    def set_grid_state(self, state: GridState) -> None:
        """The grid as a playlist or a snapshot has it: nothing done before
        is to be undone in it."""

        self.forget_grid_changes()
        self._load_grid_state(state)

        if self._ctx.video_blocks:
            self._reconcile_layout()

        self._render_video_grid()

    def _load_grid_state(self, state: GridState) -> None:
        self._mode = state.mode
        self._flow.mode = _flow_mode(state.mode)
        self._flow.is_fit = state.is_fit
        self._flow.is_match_shapes = state.is_match_shapes
        self._flow.crop = state.crop
        self._flow.is_reordered = state.is_reordered
        self._flow.is_linked = state.is_linked
        self._flow.size = state.size
        self._flow.ids = list(state.video_order)
        self._flow.sizes = dict(state.sizes)
        self._grid_layout.max_rows = max(1, state.rows)
        self._grid_layout.max_cols = max(1, state.cols)
        self._grid_layout.preallocate = state.preallocate
        self._grid_layout.cells = [cell.model_copy() for cell in state.cells]
        self._weights = Weights(
            tuple(state.col_weights),
            tuple(state.row_weights),
            tuple(tuple(weights) for weights in state.line_weights),
        )
        self._strip_share = state.strip_share
        self._free.tiles = {
            tile.video_id: Box(*tile.box) for tile in state.tiles if len(tile.box) == 4
        }
        self._free.locked = set(state.locked_tiles) & set(self._free.tiles)
        if state.page_shape:
            self._free.page_shape = state.page_shape
        # none in a playlist saved before sizes were kept
        self._free.page_height = state.page_height
        self._free.resize = state.tile_resize
        self._free.is_as_placed = state.is_tiles_as_placed
        self._tile_crop = state.tile_crop
        self._is_arranged = False
        # as arranged on their page: in Mosaic, arranged anew for another
        # size (see _place_free)
        area = self._area_size()
        self._arranged_at = area if self._free.is_page_size(*area) else None

        if self._is_fixed:
            self._grid_layout.resize(
                self._grid_layout.max_rows,
                self._grid_layout.max_cols,
                self._grid_layout.preallocate,
            )
            # one kept while every cell was shown, as Edit Grid does
            self._grid_layout.compact_edges()

    # --- undo ---

    @contextlib.contextmanager
    def _undoable(self):
        """A change of the grid made in it can be undone."""

        start = self._started()
        yield
        self._remember(start)

    def begin_grid_change(self) -> None:
        """A change made over time, a line dragged: undone as one, once it
        ends (see end_grid_change)."""

        self._change_start = self._started()

    def end_grid_change(self) -> None:
        if self._change_start is not None:
            if self._holding is not None:
                self._arrange_after_hand(self._holding)
            self._remember(self._change_start)
            self._change_start = None
        self._holding = None

    def cancel_grid_change(self) -> None:
        """The change made over time put back: the grid as it was at its
        start, with nothing to undo."""

        start, self._change_start = self._change_start, None
        self._holding = None
        if start is None:
            return

        before, forgotten = start
        # a video closed meanwhile, which it would bring back
        if forgotten == self._forgotten:
            self._restore(before, self.grid_state())

    def _started(self) -> tuple[GridState, int]:
        return self.grid_state(), self._forgotten

    def _remember(self, start: tuple[GridState, int]) -> None:
        """The grid was changed from how it was at the start: that can be
        undone, and what was undone can no longer be redone. Not where the
        changes were forgotten meanwhile, a video closed by it."""

        before, forgotten = start
        if forgotten != self._forgotten or before == self.grid_state():
            return

        self._undo.append(before)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self.undo_changed.emit()

    def forget_grid_changes(self) -> None:
        """Nothing to undo or redo: the grid's earlier states had other
        videos in it, which undoing would bring back without their cells,
        or put the new ones where there is no room for them."""

        self._forgotten += 1
        self._undo.clear()
        self._redo.clear()
        self.undo_changed.emit()

    def cmd_undo_grid(self):
        self._go_back(self._undo, self._redo)

    def cmd_redo_grid(self):
        self._go_back(self._redo, self._undo)

    def _go_back(self, states: list[GridState], others: list[GridState]) -> None:
        # to the last of the states, the grid as it is now kept in the others;
        # not while a line is held, which would come back to where it was
        if not states or self._change_start is not None:
            return

        # one that changes nothing in sight, with the one before it: the
        # strip's edge, out of Single Mode, or the grid's lines, in it
        while states:
            now = self.grid_state()
            others.append(now)
            state = states.pop()
            self._restore(state, now)
            if self._in_sight(state) != self._in_sight(now):
                break
        self.undo_changed.emit()

    def _in_sight(self, state: GridState):
        # what of the grid's state is seen now
        if self._strip_videos() is not None:
            return state.strip_share
        if self._ctx.is_single_mode:
            # one video: as the grid is, nothing; each step one
            return state
        return state.model_copy(update={"strip_share": None})

    def _restore(self, state: GridState, now: GridState) -> None:
        # the playlist's own values as they were too, those that differ
        for key, attr in GRID_STATE_ATTR.items():
            if getattr(state, attr) != getattr(now, attr):
                PlaylistSettings().set(key, getattr(state, attr))

        self._load_grid_state(state)
        self.layout_changed.emit()
        if self._ctx.is_single_mode:
            # the strip's share, which the grid is not laid out again for
            self._grid.invalidate()

    def apply_grid_config(self, config: GridState) -> bool:
        """Apply mode/size/fit/match shapes/crop/link/rows/cols/preallocate
        like the Grid menu.

        Restores do not use this — ``set_grid_state`` keeps cell positions.
        Returns False if the user cancelled a confirmation dialog.
        """
        with self._undoable():
            if not self._apply_grid_config(config):
                return False

        # the tiles maybe arranged again, the editor following
        self.layout_changed.emit()
        return True

    def _apply_grid_config(self, config: GridState) -> bool:
        mode = config.mode
        rows = max(1, int(config.rows))
        cols = max(1, int(config.cols))
        preallocate = bool(config.preallocate)

        same_fixed = (
            mode == GridMode.FIXED
            and self._is_fixed
            and self._grid_layout.max_rows == rows
            and self._grid_layout.max_cols == cols
            and self._grid_layout.preallocate == preallocate
        )
        same_flow = (
            mode != GridMode.FIXED
            and not self._is_fixed
            and self._mode == mode
            and self._flow.is_fit == config.is_fit
            and self._flow.is_match_shapes == config.is_match_shapes
            and self._flow.crop == config.crop
            and self._flow.is_reordered == config.is_reordered
            and self._flow.is_linked == config.is_linked
            and self._flow.size == config.size
        )
        if same_fixed or same_flow:
            self._set_flow_options(config)
            return True

        if mode == GridMode.FIXED:
            if not self._apply_fixed(rows, cols, preallocate):
                return False
            self._set_flow_options(config)
            return True

        if mode in TILED_MODES:
            self._make_tiled(mode, config)
            return True

        if self._is_fixed and not self._leave_fixed():
            return False
        if self._is_free:
            self._leave_free()

        self._mode = mode
        self._flow.mode = _flow_mode(mode)
        self._set_flow_options(config)
        return True

    def _set_flow_options(self, config: GridState) -> None:
        self._flow.is_fit = config.is_fit
        self._flow.is_match_shapes = config.is_match_shapes
        self._flow.crop = config.crop
        self._flow.size = config.size
        self._set_linked(config.is_linked)
        self._set_tile_resize(config.tile_resize)
        self._set_arrange_options(config.tile_crop, config.is_reordered)

    def _set_arrange_options(self, crop: int, is_reordered: bool) -> None:
        """Arrange's Crop Limit and Reorder to Fit (Fit Shapes' too): the
        tiles of Mosaic, and as Arrange Tiles left them, arranged again,
        once, by the new ones."""

        if (crop, is_reordered) == (self._tile_crop, self._flow.is_reordered):
            return

        self._tile_crop = crop
        self._flow.is_reordered = is_reordered
        if self._is_kept_arranged:
            self._arrange()
            self._grid.invalidate()

    def _set_tile_resize(self, resize: TileResize) -> None:
        if resize == self._free.resize:
            return

        self._free.set_resize(resize, *self._area_size())
        self._grid.invalidate()

    def _set_linked(self, is_linked: bool) -> None:
        # each row's own lines made one, where they are on average
        if is_linked and not self._flow.is_linked:
            self._weights = self._flow.linked(self._weights)

        self._flow.is_linked = is_linked

    def grid_drop_mode(self) -> GridMode:
        """The mode drops go by: before or after a video along the line it
        is in, a row or a column, or on any side in Fixed Grid."""

        if self._is_free:
            # a tile dropped on, anywhere
            return GridMode.FREE
        if self._mode != GridMode.AUTO_SHAPES:
            return self._mode
        return GridMode.AUTO_COLS if self._flow.is_columns() else GridMode.AUTO_ROWS

    def grid_lines(self) -> GridLines | None:
        """The lines between the cells as they are laid out now, None
        where there are none to move: in Fit Shapes, whose lines go by the
        videos' shapes, in Free Tiles, in Single Mode, or with one cell."""

        if (
            self._ctx.is_single_mode
            or self._is_free
            or self._mode == GridMode.AUTO_SHAPES
        ):
            return None

        if not self._ctx.video_blocks and not self._show_empties:
            return None

        cols, rows = self.grid_dimensions
        area = self._grid.geometry()
        if (cols <= 1 and rows <= 1) or area.isEmpty():
            return None

        cells = [
            (box, getattr(widget, "picture_shape", None))
            for widget, box in self._grid.placed()
        ]
        if not cells:
            return None

        return GridLines(
            cells,
            cols,
            rows,
            self._weights,
            area.width(),
            area.height(),
            own={} if self._is_fixed else self._flow.own_lines(),
            is_columns=not self._is_fixed and self._flow.is_columns(),
        )

    def movable_lines(self) -> MovableLines | None:
        """The lines to move by hand now: the grid's, or in Single Mode the
        strip's edge, if it has one."""

        if self._ctx.is_single_mode:
            return self._strip_lines()
        return self.grid_lines()

    def grid_area(self) -> QRect:
        """Where the cells are laid out, on the screen."""

        # moved lines leave it with no place until it is laid out again
        self._grid.activate()
        area = self._grid.geometry()
        return QRect(self.parent().mapToGlobal(area.topLeft()), area.size())

    def set_grid_weights(self, weights: Weights) -> None:
        """Move the lines between the cells (see Weights); in Single Mode,
        the strip's (see strip_weights)."""

        if self._ctx.is_single_mode:
            self._strip_share = strip_share(weights)
        else:
            self._weights = weights
        self._grid.invalidate()

    def is_grid_lines_moved(self) -> bool:
        if self._ctx.is_single_mode:
            return self._strip_share is not None and self._strip_videos() is not None

        lines = self.grid_lines()
        return lines is not None and not lines.is_even()

    def cmd_fit_grid_lines(self):
        """Move the lines between the cells to where the videos show best,
        the fewest bars left (see fit_weights)."""

        lines = self.grid_lines()
        if lines is None:
            return

        with self._undoable():
            self.set_grid_weights(self._fitted_weights(lines))

    def is_grid_lines_fittable(self) -> bool:
        """Whether Fit Lines to Videos would move any line: not the
        strip's, which snaps where the big video fits instead."""

        lines = self.grid_lines()
        if lines is None:
            return False

        return not lines.is_at(self._fitted_weights(lines))

    def _fitted_weights(self, lines: GridLines) -> Weights:
        cells = tuple(self._fit_cells())
        own = tuple(sorted(lines.own.items()))
        key = (cells, lines.cols, lines.rows, lines.width, lines.height, own)

        if self._fitted is None or self._fitted[0] != key:
            weights = fit_weights(
                cells, lines.cols, lines.rows, lines.width, lines.height, lines.own
            )
            self._fitted = (key, weights)

        return self._fitted[1]

    def cmd_reset_grid_lines(self):
        with self._undoable():
            self.set_grid_weights(EVEN)

    def _shape_of(self, video_id: str) -> float:
        """A video's shape: DEFAULT_SHAPE while it has no picture yet, or
        if it has none at all."""

        block = self._ctx.video_blocks.by_video_id(video_id)
        return (block and block.picture_shape) or DEFAULT_SHAPE

    def _is_shape_known(self, video_id: str) -> bool:
        block = self._ctx.video_blocks.by_video_id(video_id)
        return bool(block and block.picture_shape)

    def _fit_cells(self) -> list[FitCell]:
        """The cells for fit_weights, where they are in the grid. One with
        no picture yet, or with none at all, is taken to be DEFAULT_SHAPE."""

        if not self._is_fixed:
            return self._fit_flow_cells(self._shape_of)

        cells = [
            FitCell.at(
                cell.row,
                cell.col,
                self._shape_of(cell.video_id),
                cell.rowspan,
                cell.colspan,
            )
            for cell in self._grid_layout.cells
            if cell.video_id
        ]
        cells.extend(
            FitCell.at(row, col, DEFAULT_SHAPE)
            for row, col in self._grid_layout.empty_positions()
        )
        return cells

    def _fit_flow_cells(self, shape_of) -> list[FitCell]:
        # those of a line with lines of its own go between them, along it
        own = self._flow.own_lines()
        is_columns = self._flow.is_columns()

        cells = []
        for video_id in self._flow.ids:
            row, col = self._flow.position_of(video_id)
            width, height = Span("cols", col), Span("rows", row)
            if is_columns and col in own:
                height = Span(col, row)
            elif not is_columns and row in own:
                width = Span(row, col)
            cells.append(FitCell(width, height, shape_of(video_id)))
        return cells

    def grid_position_of(self, widget):
        return self._empty_positions.get(widget)

    def get_cell_at(self, global_pos):
        # the one in front, where Free Tiles has one over another
        return topmost(
            widget
            for widget in (
                *self._ctx.video_blocks,
                *self._empty_cells,
                self._info_label,
            )
            if widget.isVisible()
            and widget.rect().contains(widget.mapFromGlobal(global_pos))
        )

    def set_add_anchor(self, widget):
        self._add_anchor = widget

    def add_videos_to_layout(self, videos):
        videos = list(videos)
        if self._ctx.is_shuffle_on_load:
            random.shuffle(videos)

        anchor = self._add_anchor
        self._add_anchor = None
        if anchor is not None and getattr(anchor, "is_empty_cell", False):
            self.cmd_layout_drop(videos, None, anchor, DropZone.CENTER, False)
            return []

        videos = self._clip_videos(videos)
        if not videos or not self._is_room_for(len(videos)):
            return []

        return self._ctx.commands.add_video_blocks(videos)

    def _is_room_for(self, count: int) -> bool:
        """In Free Tiles, whether there is room for so many videos more, or
        all of them are to be arranged anew to make some."""

        if not self._is_free or not self._free.tiles:
            return True

        tiles = self._free.filled(*self._area_size())
        if not tiles.add([f"new {index}" for index in range(count)]):
            return True

        return self._ask_to_arrange(
            translate("Dialog - Free Tiles", "No room for the new videos.")
        )

    def _ask_to_arrange(self, text: str) -> bool:
        return QCustomMessageBox.confirm(
            self.parent(),
            translate("Dialog - Free Tiles", "Free Tiles", "Header"),
            text,
            translate("Dialog - Free Tiles", "Arrange"),
            info=translate("Dialog - Free Tiles", "Arrange all videos to make room?"),
        )

    def _clip_videos(self, videos, is_replace=False):
        cap = self._layout.free_capacity()
        if cap is None:
            return videos

        if is_replace:
            cap += 1

        if len(videos) <= cap:
            return videos

        kept = videos[:cap]
        extra = len(videos) - cap
        self.warning.emit(
            translate(
                "Warning",
                "Grid is full ({COLS}x{ROWS}). {COUNT} files were not added.",
            )
            .replace("{COLS}", str(self._grid_layout.max_cols))
            .replace("{ROWS}", str(self._grid_layout.max_rows))
            .replace("{COUNT}", str(extra))
        )
        return kept

    def _block_at(self, row, col):
        video_id = self._layout.id_at(row, col)
        if not video_id:
            return None
        return self._ctx.video_blocks.by_video_id(video_id)

    # --- Auto vs Fixed ---

    def cmd_set_grid_mode(self, mode):
        if self._mode == mode:
            return

        with self._undoable():
            self._set_grid_mode(mode)

    def _set_grid_mode(self, mode):
        if mode == GridMode.FIXED:
            self._ask_and_apply_fixed(include_preallocate=True)
            return

        if mode in TILED_MODES:
            self._make_tiled(mode)
            PlaylistSettings().set("playlist/grid_mode", mode)
            return

        if self._is_fixed and not self._leave_fixed():
            return
        if self._is_free:
            self._leave_free()

        self._mode = mode
        self._flow.mode = _flow_mode(mode)
        PlaylistSettings().set("playlist/grid_mode", mode)
        self.layout_changed.emit()

    def cmd_ask_grid_size(self):
        if self._flow.mode == FlowMode.COLS:
            title = translate("Grid Size", "Videos per column")
        else:
            title = translate("Grid Size", "Videos per row")

        size = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=title,
            special_text=translate("Grid Size", "Auto"),
            initial_value=self._flow.size,
            _min=0,
            _max=1000,
        )

        if self._flow.size != size:
            self._set_flow_option("playlist/grid_size", size)

    def cmd_get_grid_size(self):
        if self._flow.size == 0:
            return translate("Grid Size", "Auto")

        return str(self._flow.size)

    def cmd_switch_is_grid_fit(self):
        self._set_flow_option("playlist/grid_fit", not self._flow.is_fit)

    def cmd_switch_is_grid_match_shapes(self):
        self._set_flow_option(
            "playlist/grid_match_shapes", not self._flow.is_match_shapes
        )

    def cmd_switch_is_grid_link(self):
        self._set_flow_option("playlist/grid_link", not self._flow.is_linked)

    def cmd_set_tile_resize(self, resize: TileResize):
        if self._free.resize != resize:
            self._set_flow_option("playlist/tile_resize", resize)

    def cmd_set_tile_crop(self, crop: int):
        """How much Arrange Tiles may cut each picture."""

        if self._tile_crop != crop:
            self._set_flow_option("playlist/tile_crop", crop)

    def cmd_set_grid_crop(self, crop: int):
        if self._flow.crop != crop:
            self._set_flow_option("playlist/grid_crop", crop)

    def cmd_switch_is_grid_reorder(self):
        self._set_flow_option("playlist/grid_reorder", not self._flow.is_reordered)

    def _set_flow_option(self, key: str, value) -> None:
        # an option of Auto, by its setting: the playlist's own value
        with self._undoable():
            if key == "playlist/grid_link":
                self._set_linked(value)
            elif key == "playlist/tile_resize":
                self._set_tile_resize(value)
            elif key == "playlist/tile_crop":
                self._set_arrange_options(value, self._flow.is_reordered)
            elif key == "playlist/grid_reorder":
                self._set_arrange_options(self._tile_crop, value)
            else:
                setattr(self._flow, GRID_STATE_ATTR[key], value)
            PlaylistSettings().set(key, value)
            self.layout_changed.emit()

    def is_grid_sized(self) -> bool:
        """Whether any video is made bigger or smaller: in Fit Shapes (see
        FlowLayout.sizes), or in a Fixed Grid, its cell covering more than
        one."""

        if self._mode == GridMode.AUTO_SHAPES:
            return bool(self._flow.sized())
        return self._is_fixed and bool(self._grid_layout.big_cells())

    def cmd_reset_grid_sizes(self):
        """Every video back to its size: in a Fixed Grid, one cell each,
        the others staying where they are."""

        if not self.is_grid_sized():
            return

        with self._undoable():
            if self._mode == GridMode.AUTO_SHAPES:
                self._flow.sizes = {}
            else:
                for cell in self._grid_layout.big_cells():
                    self._grid_layout.set_span(cell.video_id, 1, 1)
            self.layout_changed.emit()

    def is_grid_cell_sized(self, video_id: str | None = None) -> bool:
        """Whether a video, the active one by default, is made bigger or
        smaller (see is_grid_sized)."""

        video_id = video_id or self._active_id()
        if video_id is None:
            return False
        if self._mode == GridMode.AUTO_SHAPES:
            return bool(self._flow.sizes.get(video_id))
        return self._is_fixed and self._grid_layout.span_of(video_id) not in {
            None,
            (1, 1),
        }

    def cmd_reset_grid_cell_size(self, video_id: str | None = None):
        """A video, the active one by default, back to its size."""

        video_id = video_id or self._active_id()
        if not self.is_grid_cell_sized(video_id):
            return
        if self._mode == GridMode.AUTO_SHAPES:
            self._set_shapes_size(video_id, 0)
        else:
            self.cmd_set_grid_cell_span(video_id, 1, 1)

    def cmd_get_fixed_grid_size(self):
        return f"{self._grid_layout.max_cols}x{self._grid_layout.max_rows}"

    def cmd_ask_fixed_grid_size(self):
        with self._undoable():
            self._ask_and_apply_fixed(include_preallocate=not self._is_fixed)

    def cmd_switch_grid_preallocate(self):
        if not self._is_fixed:
            return

        with self._undoable():
            self._grid_layout.preallocate = not self._grid_layout.preallocate
            if not self._grid_layout.preallocate:
                self._grid_layout.compact_edges()
            PlaylistSettings().set(
                "playlist/grid_preallocate", self._grid_layout.preallocate
            )
            self.layout_changed.emit()

    def cmd_shuffle_layout(self):
        with self._undoable():
            self._layout.shuffle()
            if self._is_mosaic:
                # the tiles traded: arranged in the order they now are in
                self._stop_reordering()
                self._arrange()
                self._grid.invalidate()
            self.layout_changed.emit()

    # --- big cells ---

    def _active_id(self) -> str | None:
        block = self._ctx.active_block
        return block.video_id if block is not None else None

    def is_grid_cell_sizable(self) -> bool:
        """Whether the videos' cells can be made bigger and smaller, all of
        them shown: in a Fixed Grid of more than one cell, or in Fit Shapes
        with more than one video (see FlowLayout.sizes)."""

        if self._ctx.is_single_mode:
            return False
        if self._mode == GridMode.AUTO_SHAPES:
            return len(self._flow.ids) > 1
        return (
            self._is_fixed
            and self._grid_layout.max_rows * self._grid_layout.max_cols > 1
        )

    def is_grid_cell_shapable(self) -> bool:
        """Whether they can be made wider, taller and so on, and their size
        picked: in a Fixed Grid (see is_grid_cell_sizable)."""

        return self._is_fixed and self.is_grid_cell_sizable()

    def _step_target(self, video_id: str | None) -> str | None:
        video_id = video_id or self._active_id()
        if video_id is None or not self.is_grid_cell_sizable():
            return None
        return video_id

    def _shapes_size(self, step: str, video_id: str) -> int | None:
        way = SHAPES_STEPS.get(step)
        if way is None:
            return None
        return self._flow.size_step(video_id, way)

    def is_grid_cell_steppable(self, step: str, video_id: str | None = None) -> bool:
        """Whether there is room to make a video's cell, the active one's by
        default, a step bigger or smaller; in Fit Shapes, whether a step
        changes its tile."""

        video_id = self._step_target(video_id)
        if video_id is None:
            return False
        if self._mode == GridMode.AUTO_SHAPES:
            return self._shapes_size(step, video_id) is not None
        rows, cols = CELL_STEPS[step]
        return self._grid_layout.step_span(video_id, rows, cols) is not None

    def cmd_step_grid_cell(self, step: str, video_id: str | None = None):
        """A video's cell, the active one's by default, made a step bigger
        or smaller (see CELL_STEPS), the videos in the way moved to make
        room. Bigger, where there is no room for a row and a column more,
        takes one of them (see GridLayout.steps). In Fit Shapes, its tile
        made bigger or smaller (see FlowLayout.size_step)."""

        video_id = self._step_target(video_id)
        if video_id is None:
            return

        if self._mode == GridMode.AUTO_SHAPES:
            size = self._shapes_size(step, video_id)
            if size is not None:
                self._set_shapes_size(video_id, size)
            return

        rows, cols = CELL_STEPS[step]
        span = self._grid_layout.step_span(video_id, rows, cols)
        if span is not None:
            self._set_span(video_id, *span)
        elif self._grid_layout.steps(video_id, rows, cols):
            self._warn_no_room()

    def _set_shapes_size(self, video_id: str, size: int):
        with self._undoable():
            sizes = self._flow.sized()
            sizes.pop(video_id, None)
            if size:
                sizes[video_id] = size
            self._flow.sizes = sizes
            self.layout_changed.emit()

    def grid_cell_span(self, video_id: str) -> tuple[int, int] | None:
        """How many rows and columns a video's cell covers."""

        return self._grid_layout.span_of(video_id)

    def grid_cell_room(self) -> tuple[int, int]:
        """The rows and columns a cell can cover, at most."""

        return self._grid_layout.max_rows, self._grid_layout.max_cols

    def can_set_grid_cell_span(self, video_id: str, rowspan: int, colspan: int) -> bool:
        return self._grid_layout.copy().set_span(video_id, rowspan, colspan)

    def cmd_set_grid_cell_span(self, video_id: str, rowspan: int, colspan: int):
        if self._grid_layout.span_of(video_id) == (rowspan, colspan):
            return

        if not self._set_span(video_id, rowspan, colspan):
            self._warn_no_room()

    def _warn_no_room(self):
        self.warning.emit(
            translate("Warning", "No room in the grid to make the cell bigger.")
        )

    def _set_span(self, video_id, rowspan, colspan) -> bool:
        with self._undoable():
            if not self._grid_layout.set_span(video_id, rowspan, colspan):
                return False
            self.layout_changed.emit()
            return True

    # --- the cells edited by hand (see GridEditManager) ---

    def make_grid_fixed(self) -> bool:
        """A Fixed Grid of the size the grid is now, the videos in their
        order, to edit its cells."""

        if self._is_fixed:
            return True

        cols, rows = self.grid_dimensions
        with self._undoable():
            if not self._apply_fixed(rows, cols, preallocate=False):
                return False
            self._keep_fixed(rows, cols)
            PlaylistSettings().set("playlist/grid_preallocate", False)
        return True

    def _keep_fixed(self, rows: int, cols: int) -> None:
        # the playlist's own values: a Fixed Grid of this size
        session = PlaylistSettings()
        session.set("playlist/grid_mode", GridMode.FIXED)
        session.set("playlist/grid_rows", rows)
        session.set("playlist/grid_cols", cols)

    def set_grid_editing(self, is_editing: bool) -> None:
        """Every cell of the Fixed Grid shown, as with Show All Cells, the
        empty ones kept, while its cells are edited."""

        if self._grid_layout.is_editing == is_editing:
            return

        self._grid_layout.is_editing = is_editing
        if not is_editing:
            self._grid_layout.compact_edges()
        self.layout_changed.emit()

    def can_place_grid_cell(self, video_id, row, col, rowspan, colspan) -> bool:
        return self._is_fixed and self._grid_layout.can_place(
            video_id, row, col, rowspan, colspan
        )

    def cmd_place_grid_cell(self, video_id, row, col, rowspan, colspan) -> bool:
        """A video's cell moved or resized (see GridLayout.place)."""

        if not self._is_fixed:
            return False

        with self._undoable():
            if not self._grid_layout.place(video_id, row, col, rowspan, colspan):
                return False
            self.layout_changed.emit()
            return True

    def can_resize_fixed_grid(self, rows: int, cols: int) -> bool:
        """Whether the Fixed Grid can have this size with no video closed:
        those it cuts off go into its empty cells."""

        if not self._is_fixed:
            return False
        if not (1 <= rows <= MAX_FIXED_SIZE and 1 <= cols <= MAX_FIXED_SIZE):
            return False
        return not self._grid_layout.copy().resize(rows, cols)

    def cmd_resize_fixed_grid(self, rows: int, cols: int) -> bool:
        if not self.can_resize_fixed_grid(rows, cols):
            return False

        with self._undoable():
            self._grid_layout.resize(rows, cols)

            session = PlaylistSettings()
            session.set("playlist/grid_rows", rows)
            session.set("playlist/grid_cols", cols)
            self.layout_changed.emit()
        return True

    def is_grid_template(self, name: str) -> bool:
        return self.is_grid_shaped_as(GRID_TEMPLATES[name])

    def is_grid_shaped_as(self, template: GridTemplate) -> bool:
        return self._is_fixed and self._grid_layout.is_template(template)

    def grid_template_now(self) -> GridTemplate | None:
        """The Fixed Grid there is as a template: its size and its big
        cells, row by row. None for a grid that is not a Fixed Grid."""

        if not self._is_fixed:
            return None

        big = sorted(
            (c.row, c.col, c.rowspan, c.colspan) for c in self._grid_layout.big_cells()
        )
        return GridTemplate(
            self._grid_layout.max_cols, self._grid_layout.max_rows, tuple(big)
        )

    def cmd_set_grid_template(self, name: str):
        self.cmd_apply_grid_template(GRID_TEMPLATES[name])

    def cmd_apply_grid_template(self, template: GridTemplate):
        """A Fixed Grid with big cells, the videos put in it in their order,
        the first in the first big cell."""

        ordered = self._live_order()
        capacity = len(template.places())
        extra_ids = ordered[capacity:]
        if extra_ids and not self._confirm_overflow(capacity, len(extra_ids)):
            return

        with self._undoable():
            self._free.clear()
            self._mode = GridMode.FIXED
            self._grid_layout.apply_template(template, ordered[:capacity])
            self._weights = EVEN
            self._keep_fixed(template.rows, template.cols)

            if extra_ids:
                self._ctx.commands.remove_video_blocks(extra_ids)
            else:
                self.layout_changed.emit()

    def _live_order(self) -> list[str]:
        """The videos there are, in the order they are laid out in."""

        live_set = set(self._ctx.video_blocks.video_ids)
        ordered = [i for i in self._layout.order() if i in live_set]
        ordered.extend(i for i in self._ctx.video_blocks.video_ids if i not in ordered)
        return ordered

    def _ask_and_apply_fixed(self, include_preallocate=True):
        if self._is_fixed:
            rows, cols = self._grid_layout.max_rows, self._grid_layout.max_cols
            preallocate = self._grid_layout.preallocate
        else:
            dims = self.grid_dimensions
            rows, cols = dims.rows, dims.cols
            preallocate = False

        result = QFixedGridSizeDialog.get_size(
            parent=self.parent(),
            rows=rows,
            cols=cols,
            preallocate=preallocate,
            include_preallocate=include_preallocate,
        )
        if result is None:
            return False

        new_rows, new_cols, new_preallocate = result
        if not self._apply_fixed(new_rows, new_cols, new_preallocate):
            return False

        self._keep_fixed(new_rows, new_cols)
        if include_preallocate:
            PlaylistSettings().set("playlist/grid_preallocate", new_preallocate)
        return True

    def _apply_fixed(self, rows, cols, preallocate) -> bool:
        if self._is_fixed:
            return self._resize_fixed(rows, cols, preallocate)

        ordered = self._live_order()
        extra_ids = ordered[rows * cols :]
        keep_ids = ordered[: rows * cols]
        if extra_ids and not self._confirm_overflow(rows * cols, len(extra_ids)):
            return False

        # where they were, while they are there
        self._ctx.commands.remember_closed(
            self._ctx.video_blocks.blocks_for_ids(extra_ids)
        )

        self._free.clear()
        self._mode = GridMode.FIXED
        self._grid_layout.max_rows = rows
        self._grid_layout.max_cols = cols
        self._grid_layout.preallocate = preallocate
        self._grid_layout.pack_flow(keep_ids)
        if extra_ids:
            self._ctx.commands.remove_video_blocks(extra_ids)
            return True

        self.layout_changed.emit()
        return True

    def _resize_fixed(self, rows, cols, preallocate) -> bool:
        snapshot = self._grid_layout.copy()
        leftover = self._grid_layout.resize(rows, cols, preallocate)

        if leftover:
            if not self._confirm_overflow(rows * cols, len(leftover)):
                self._grid_layout = snapshot
                return False
            self._ctx.commands.remember_closed(
                self._ctx.video_blocks.blocks_for_ids(leftover)
            )
            self._ctx.commands.remove_video_blocks(leftover)
            return True

        self.layout_changed.emit()
        return True

    def _leave_fixed(self):
        holes = self._grid_layout.empty_positions(preallocate=False)
        if holes and self._ctx.video_blocks:
            is_removed = QCustomMessageBox.confirm(
                self.parent(),
                translate("Dialog - Set grid size", "Set grid size", "Header"),
                translate("Dialog - Set grid size", "Remove the empty cells?"),
                translate("Dialog - Set grid size", "Remove"),
                info=translate("Dialog - Set grid size", "Videos keep their order."),
            )
            if not is_removed:
                return False

        self._flow.ids = self._grid_layout.order()
        self._grid_layout.cells = []
        return True

    # --- Free Tiles ---

    def _make_free(self) -> None:
        """Free Tiles, each video's tile where its cell is now, on a page
        the size of the area: nothing moves, until it is moved by hand."""

        width, height = self._area_size()
        cells = self._cells_now(width, height)

        if self._is_fixed:
            # its empty cells kept as room on the page
            self._flow.ids = self._grid_layout.order()
            self._grid_layout.cells = []

        self._mode = GridMode.FREE
        self._free.tiles = dict(cells)
        self._free.set_page(width, height)
        self._is_arranged = False

    def _make_tiled(self, mode: GridMode, config: GridState | None = None) -> None:
        """Free Tiles or Mosaic, the tiles where the cells are, or the
        other's tiles kept; Mosaic arranges them at once, those locked
        staying where they are. config's options set too: the flow's for
        when it is left, and Arrange's, which Mosaic arranges them by."""

        if not self._is_free:
            # where the cells are by the flow's options as they were
            self._make_free()
        is_arranging = mode == GridMode.MOSAIC and not self._is_mosaic
        if is_arranging:
            # arranged once, below, by the new options
            self._is_arranged = False
        if config is not None:
            self._set_flow_options(config)
        self._mode = mode
        if is_arranging:
            self._arrange()
            self._grid.invalidate()
        self.layout_changed.emit()

    def _leave_free(self) -> None:
        """The tiles let go of, the videos in the order they are read in."""

        self._flow.ids = self._free.order()
        self._free.clear()

    def _area_size(self) -> tuple[int, int]:
        area = self._grid.geometry()
        if area.isEmpty():
            area = self.parent().rect()
        return max(area.width(), 1), max(area.height(), 1)

    def _cells_now(self, width: int, height: int) -> list[tuple[str, Box]]:
        """Where the videos' cells are in an area of this size, as the grid
        is out of Single Mode."""

        live = set(self._ctx.video_blocks.video_ids)

        if self._is_fixed:
            cells = [
                (cell.video_id, box)
                for cell, box in self._grid_layout.boxes(self._weights)
            ]
        else:
            shapes = {vb.video_id: vb.picture_shape for vb in self._ctx.video_blocks}
            self._flow.fit_to(width, height, shapes)
            cells = self._flow.boxes(self._weights)

        return [(video_id, box) for video_id, box in cells if video_id in live]

    def cmd_arrange_tiles(self):
        """The tiles not locked laid out anew around those that are, on a
        page the shape of the area (see arrange_around): the videos in the
        order they are read in, row by row for rows and column by column
        for columns, or with Reorder to Fit in the order that shows them
        best; each picture cut by up to the Crop Limit to fill the room,
        and by no more than that does."""

        if not self._is_free:
            return

        with self._undoable():
            self._arrange()
            self.layout_changed.emit()

    def cmd_fit_tiles_to_window(self):
        """The tiles made as big as the window lets them, all together, as
        they are placed among themselves: no room left around them. Those
        locked too, as a window made bigger makes them."""

        if self._mode != GridMode.FREE:
            return

        with self._undoable():
            self._free.fill(*self._area_size())
            self._free.fit_to_page()
            self._is_arranged = False
            self._grid.invalidate()
            self.layout_changed.emit()

    def _arrange(self, is_reordered: bool | None = None) -> None:
        boxes = self._arranged(is_reordered)
        if boxes is None:
            return

        self._free.arrange(boxes.items())
        self._arranged_now()

    def _arranged_now(self) -> None:
        # the tiles as Arrange left them, or Mosaic
        self._unshaped = {i for i in self._free.tiles if not self._is_shape_known(i)}
        self._is_arranged = True
        self._arranged_at = self._area_size()

    def _arranged(self, is_reordered: bool | None = None) -> dict[str, Box] | None:
        """Where Arrange Tiles puts the tiles now, as shares of the area
        (see cmd_arrange_tiles); None if there is no room for them. While
        a tile is held, the others read as if where they were at the start
        (see _Holding). Reordered as Reorder to Fit is, unless told."""

        width, height = self._area_size()
        self._free.fill(width, height)
        if is_reordered is None:
            is_reordered = self._flow.is_reordered
        rects = self._free.rects(width, height)

        # around the locked tiles; with no room left by them, all of them
        for walls in (self._locked_rects(rects), {}):
            boxes = self._arranged_around(walls, rects, width, height, is_reordered)
            if boxes is not None:
                return boxes
        return None

    def _locked_rects(self, rects: Mapping[str, Rect]) -> dict[str, Rect]:
        return {i: rect for i, rect in rects.items() if i in self._free.locked}

    def _arranged_around(
        self,
        walls: Mapping[str, Rect],
        rects: Mapping[str, Rect],
        width: float,
        height: float,
        is_reordered: bool,
        cache: ArrangeCache | None = None,
    ) -> dict[str, Box] | None:
        # the tiles but the walls, arranged around those (see arrange_around)
        ids = [i for i in self._ctx.video_blocks.video_ids if i not in walls]
        return arrange_around(
            width,
            height,
            list(walls.values()),
            ids,
            self._read_at(rects, width, height),
            {i: self._shape_of(i) for i in ids},
            self._tile_crop,
            is_reordered,
            cache,
        )

    def _read_at(
        self, rects: Mapping[str, Rect], width: float, height: float
    ) -> dict[str, Rect]:
        # where the tiles are read in their order: while one is held, the
        # others where they were at the start
        at = dict(rects)
        if self._holding is not None:
            area = Rect(0, 0, width, height)
            at.update(
                (i, Rect.of_box(box, area))
                for i, box in self._holding.start.items()
                if i in at
            )
        return at

    def _arrange_live(self) -> None:
        """Mosaic: the tile held where it is moved or sized to, the
        others arranged around it as around a locked one, as it goes; it
        stretched to the window's edge over room too thin for another, or
        that none of them took (see _stretched_to_edges). With no room
        left for them, the others are left as they were last shown."""

        holding = self._holding
        held = holding.video_id
        width, height = self._area_size()
        self._free.fill(width, height)
        rects = self._free.rects(width, height)
        # put where it was the last time, snapped there again, say: the
        # others are as they were
        put = (rects[held], width, height)
        if holding.last is not None and holding.last[0] == put:
            if holding.is_live:
                self._free.set_rect(held, holding.last[1], width, height)
            return

        rect = self._stretched_to_edges(held, rects[held], width, height)
        locked = self._locked_rects(rects)
        boxes = self._arranged_around(
            {**locked, held: rect},
            rects,
            width,
            height,
            # the order where they are (see _arrange_after_hand)
            False,
            holding.cache,
        )
        holding.is_live = boxes is not None
        holding.last = (put, rect)
        if boxes is None:
            return

        # over room none of the others took
        area = Rect(0, 0, width, height)
        others = [Rect.of_box(box, area) for box in boxes.values()]
        others += locked.values()
        rect = self._stretched_to_edges(held, rect, width, height, others)
        holding.last = (put, rect)
        self._free.set_rect(held, rect, width, height)
        self._free.arrange(boxes.items())

    def _stretched_to_edges(
        self,
        video_id: str,
        rect: Rect,
        width: float,
        height: float,
        others: Sequence[Rect] | None = None,
    ) -> Rect:
        """A tile held stretched to each edge of the window it is nearer
        than MIN_CELL, or, others given, with none of them between, across
        then down: where that cuts its picture no more than the crop limit,
        or than it is cut already; not to all four, which would leave no
        room for the others."""

        shape = self._shape_of(video_id)

        def cut(r: Rect) -> float:
            if r.width <= 0 or r.height <= 0:
                return 1.0
            stretch = r.width / r.height / shape
            return 1 - min(stretch, 1 / stretch)

        limit = max(self._tile_crop / 100, cut(rect)) + 1e-6

        def stretched(r: Rect, side: str) -> Rect:
            strip, edge = {
                "left": (Rect(0, r.top, r.left, r.bottom), 0),
                "right": (Rect(r.right, r.top, width, r.bottom), width),
                "top": (Rect(r.left, 0, r.right, r.top), 0),
                "bottom": (Rect(r.left, r.bottom, r.right, height), height),
            }[side]
            gap = min(strip.width, strip.height)
            is_open = gap < MIN_CELL or (
                others is not None and not any(strip.overlaps(o) for o in others)
            )
            if gap <= 0 or not is_open:
                return r
            longer = r._replace(**{side: edge})
            return longer if cut(longer) <= limit else r

        for side in ("left", "right"):
            rect = stretched(rect, side)
        across = rect
        for side in ("top", "bottom"):
            rect = stretched(rect, side)
        if rect.width >= width - 0.5 and rect.height >= height - 0.5:
            return across
        return rect

    def _hold(self, video_id: str) -> None:
        """The tile held in the change going on, the others where they were
        at its start (see _read_at)."""

        holding = self._holding
        if holding is not None and holding.video_id == video_id:
            return
        if video_id in self._free.tiles:
            start = {i: b for i, b in self._free.tiles.items() if i != video_id}
            self._holding = _Holding(video_id, start)

    def _arrange_after_hand(self, holding: _Holding) -> None:
        """Mosaic: a tile let go of. It stays where it was moved, or
        sized, to, the others where they were shown around it (see
        _arrange_live); with no room left for them, all arranged anew.
        Reorder to Fit is turned off, the others to stay in their order
        around it, as shown. Arranged again later, it is as any other: to
        stay as it is, it is locked."""

        self._stop_reordering()
        # arranged for what came in meanwhile as it went
        self._arrange_timer.stop()
        if holding.is_live:
            self._arranged_now()
        else:
            self._arrange()
        self._grid.invalidate()
        self.layout_changed.emit()

    def _arrange_due(self) -> None:
        """Arranged again for the shapes that came in, or the window
        resized: not while a tile is held. No longer arranged, the tiles of
        those shapes made them (see _fit_tiles_to_shapes)."""

        if not self._is_kept_arranged:
            if self._is_free:
                self._fit_tiles_to_shapes()
            return
        if self._change_start is not None:
            self._arrange_timer.start()
            return

        self._arrange()
        self._grid.invalidate()
        self.layout_changed.emit()

    def _add_tiles(self, video_ids: list[str], is_any_gone: bool = False) -> None:
        """New videos' tiles put where there is room on the window, made
        their videos' shapes once those are known (see _fit_tiles_to_shapes).
        In Mosaic, all of them arranged again, some new or gone."""

        self._unshaped |= {i for i in video_ids if not self._is_shape_known(i)}
        if video_ids:
            # the room beside the tiles' page too
            self._free.fill(*self._area_size())
        # none placed yet, or no room for some: all of them arranged anew
        is_no_room = self._free.add(video_ids)
        if is_no_room or (self._is_mosaic and (video_ids or is_any_gone)):
            self._arrange()

    def _fit_tiles_to_shapes(self) -> None:
        """Tiles made for videos whose shapes were not known then, now that
        they are: arranged anew if none was moved since, else each made its
        video's shape inside it."""

        shaped = {i for i in self._unshaped if self._is_shape_known(i)}
        if not shaped:
            return

        if self._is_kept_arranged:
            # once for those coming in together; fitted then, if no longer
            # arranged (see _arrange_due)
            self._arrange_timer.start()
            return

        self._unshaped -= shaped
        self._keep_tiles_shown()
        for video_id in shaped:
            self._free.fit_shape(video_id, self._shape_of(video_id))
        self._grid.invalidate()

    def _keep_tiles_shown(self) -> None:
        # Free Tiles kept where they are shown, before some of them go or
        # change, which would fit the others anew (see FreeTiles.boxes)
        if self._is_free:
            self._free.fill(*self._area_size())

    def free_page(self) -> FreePage | None:
        """The tiles to move and size by hand now, and where their page is
        on the screen: in Free Tiles, out of Single Mode. The page is all of
        the area, the room beside the tiles' own free to move them to (see
        set_free_tiles)."""

        if not self._is_free or self._ctx.is_single_mode:
            return None

        area = self.grid_area()
        if area.isEmpty():
            return None

        return FreePage(self._free.filled(area.width(), area.height()), area)

    def set_free_tiles(
        self,
        rects: dict[str, Rect],
        page_width: float,
        page_height: float,
        held: str | None = None,
    ) -> None:
        """Tiles moved or sized by hand: one (held), and those it pushed
        aside, on a page of this size (see TileDrag): the area it was,
        which the page now takes the shape of."""

        self._free.fill(page_width, page_height)
        # in Mosaic, the others make room as it goes
        if held is not None and self._is_mosaic:
            self._hold(held)
        for video_id, rect in rects.items():
            self._free.set_rect(video_id, rect, page_width, page_height)
        self._is_arranged = False
        if self._holding is not None:
            self._arrange_live()
        self._grid.invalidate()

    def tile_overlap(self) -> TileOverlap:
        return PlaylistSettings().get("playlist/tile_overlap")

    def is_tile_overlap_on(self) -> bool:
        return self.tile_overlap() == TileOverlap.ON

    def set_tile_overlap(self, overlap: TileOverlap) -> None:
        PlaylistSettings().set("playlist/tile_overlap", overlap)

    def is_tiles_stacked(self) -> bool:
        """In Free Tiles, whether one tile can go over another, or is: to
        be put in front of the others, or behind them."""

        # in Mosaic, never: they are arranged apart
        return self._mode == GridMode.FREE and (
            self.is_tile_overlap_on() or self._free.is_stacked()
        )

    def is_tile_stackable(self, where: str) -> bool:
        """Whether the active video's tile is under another, to be put in
        front ("front"), or over another, to be put behind ("back")."""

        video_id = self._active_tile()
        if video_id is None:
            return False
        if where == "front":
            return self._free.is_under(video_id)
        return self._free.is_over(video_id)

    def _active_tile(self, video_id: str | None = None) -> str | None:
        """A video, the active one by default, with a tile to move or size
        by hand now."""

        video_id = video_id or self._active_id()
        if not self._is_free or self._ctx.is_single_mode:
            return None
        return video_id if video_id in self._free.tiles else None

    def cmd_stack_tile(self, where: str) -> None:
        video_id = self._active_tile()
        if video_id is not None:
            self.stack_free_tile(video_id, where == "front")

    def stack_free_tile(self, video_id: str, is_front: bool) -> None:
        """A tile put in front of the others it is under, or behind those it
        is over (see FreeTiles.stack)."""

        tiles = self._free
        if video_id not in tiles.tiles:
            return
        if not (tiles.is_under(video_id) if is_front else tiles.is_over(video_id)):
            return

        with self._undoable():
            tiles.stack(video_id, is_front)
        self._grid.invalidate()

    def is_tile_lockable(self) -> bool:
        return self._active_tile() is not None

    def is_tile_locked(self, video_id: str | None = None) -> bool:
        return (video_id or self._active_id()) in self._free.locked

    def cmd_lock_tile(self, video_id: str | None = None) -> None:
        """A video's tile, the active one's by default, locked, in front of
        the others, or let go of (see FreeTiles)."""

        video_id = self._active_tile(video_id)
        if video_id is not None:
            self.lock_free_tile(video_id, video_id not in self._free.locked)

    def _sizable_tile(self, video_id: str | None) -> str | None:
        # a video's tile, the active one's by default, to size: not locked,
        # nor arranged after each change, which would undo it
        video_id = self._active_tile(video_id)
        if video_id is None or video_id in self._free.locked or self._is_mosaic:
            return None
        return video_id

    def _room_around(self, video_id: str) -> Rect | None:
        # the most room the tile has, the tiles as they are shown
        return self._free.filled(*self._area_size()).room_around(video_id)

    def is_tile_space_fillable(self, video_id: str | None = None) -> bool:
        """Whether a video's tile, the active one's by default, has room
        around it to fill."""

        video_id = self._sizable_tile(video_id)
        return video_id is not None and self._room_around(video_id) is not None

    def cmd_fill_tile_space(self, video_id: str | None = None) -> None:
        """A video's tile, the active one's by default, made as big as the
        room around it lets it (see FreeTiles.room_around)."""

        video_id = self._sizable_tile(video_id)
        room = None if video_id is None else self._room_around(video_id)
        if room is None:
            return

        with self._undoable():
            self._free.fill(*self._area_size())
            self._free.set_rect(video_id, room, self._free.page_shape, 1)
            self._is_arranged = False
        self._grid.invalidate()

    def is_tile_fittable(self, video_id: str | None = None) -> bool:
        """Whether a video's tile, the active one's by default, is not its
        video's shape, the shape known."""

        video_id = self._sizable_tile(video_id)
        return (
            video_id is not None
            and self._is_shape_known(video_id)
            and not self._free.is_shaped(video_id, self._shape_of(video_id))
        )

    def cmd_fit_tile_to_video(self, video_id: str | None = None) -> None:
        """A video's tile, the active one's by default, made its video's
        shape, as big as it can be inside the tile it had, in the middle of
        it: the bars beside the picture cut off."""

        video_id = self._sizable_tile(video_id)
        if video_id is None or not self.is_tile_fittable(video_id):
            return

        with self._undoable():
            self._free.fill(*self._area_size())
            self._free.fit_shape(video_id, self._shape_of(video_id))
            self._is_arranged = False
        self._grid.invalidate()

    def lock_free_tile(self, video_id: str, is_locked: bool) -> None:
        if video_id not in self._free.tiles:
            return

        # in Mosaic too, nothing moves for it: the others are
        # arranged around it, or it with them, at the next change
        with self._undoable():
            self._free.set_locked(video_id, is_locked)
        self._grid.invalidate()

    def is_tile_room_makeable(self) -> bool:
        """Whether the active video's tile is over another not locked, or
        under, for room to be made for it (see cmd_make_room)."""

        video_id = self._active_tile()
        return (
            video_id is not None
            and not self._is_mosaic
            and self._free.is_crowded(video_id)
        )

    def cmd_make_room(self) -> None:
        """The tiles the active video's is over, or under, set aside: each
        made smaller in its own place, or put where there is room (see
        FreeTiles.make_room). With too little room, asks to arrange them all."""

        if not self.is_tile_room_makeable():
            return

        width, height = self._area_size()
        tiles = self._free.filled(width, height)
        if tiles.make_room(self._active_id()):
            with self._undoable():
                self._free.tiles = tiles.tiles
                self._free.set_page(width, height)
                self._is_arranged = False
            self._grid.invalidate()
            return

        if self._ask_to_arrange(
            translate("Dialog - Free Tiles", "No room for the tiles it covers.")
        ):
            self.cmd_arrange_tiles()

    def bring_free_tile_to_front(self, video_id: str) -> None:
        """A tile in front of the others, as one being moved or sized over
        them is: part of that change (see begin_grid_change)."""

        if video_id in self._free.tiles and self._free.is_under(video_id):
            self._free.stack(video_id, True)
            self._grid.invalidate()

    def _forget_cell_steps(self) -> None:
        # laid out anew, the room each cell or tile has to be made bigger or
        # smaller, or to fill, changed with it or with another: its buttons
        # to be looked at again
        for vb in self._ctx.video_blocks:
            vb.cell_size.forget_steps()

    def _stack_tiles(self) -> None:
        """In Free Tiles, the videos one over another as their tiles are,
        once laid out: the overlays of those behind cut where those in
        front cover them, as an overlay of its own window is over every
        video (see OverlayBlock.set_covered)."""

        stacked = []
        if self._is_free and not self._ctx.is_single_mode:
            for video_id in self._free.tiles:
                vb = self._ctx.video_blocks.by_video_id(video_id)
                if vb is not None and not vb.isHidden():
                    stacked.append(vb)

        if stacked != self._stacked:
            for vb in stacked:
                vb.raise_()
            self._stacked = stacked

        cut = set()
        for at, vb in enumerate(stacked):
            own = vb.geometry()
            covered = QRegion()
            for front in stacked[at + 1 :]:
                over = front.geometry().intersected(own)
                if not over.isEmpty():
                    covered += over.translated(-own.topLeft())
            if not covered.isEmpty():
                cut.add(vb)
            if vb in cut or vb in self._cut:
                vb.overlay.set_covered(covered)

        # out of sight, or out of Free Tiles: whole again
        for vb in self._cut - cut:
            if not sip.isdeleted(vb) and vb not in stacked:
                vb.overlay.set_covered(QRegion())
        self._cut = cut

    def _confirm_overflow(self, capacity, count) -> bool:
        return QCustomMessageBox.confirm(
            self.parent(),
            translate("Dialog - Set grid size", "Set grid size", "Header"),
            translate("Dialog - Set grid size", "Close {COUNT} videos?").format(
                COUNT=count_txt(count)
            ),
            translate("Dialog - Set grid size", "Close Videos"),
            info=translate(
                "Dialog - Set grid size", "This grid holds {CAPACITY} videos."
            ).format(CAPACITY=count_txt(capacity)),
            is_destructive=True,
            icon=QMessageBox.Warning,
        )

    def _reconcile_layout(self):
        live_set = set(self._ctx.video_blocks.video_ids)
        gone = [i for i in self._layout.order() if i not in live_set]
        if gone:
            self._keep_tiles_shown()
        for video_id in gone:
            self._layout.remove(video_id)
        new_ids = [
            i for i in self._ctx.video_blocks.video_ids if not self._layout.contains(i)
        ]

        if self._is_free:
            self._add_tiles(new_ids, is_any_gone=bool(gone))
            return

        leftover = self._layout.add(new_ids)
        if self._is_fixed:
            self._grid_layout.compact_edges()
        if leftover:
            self._ctx.commands.remove_video_blocks(leftover)

    # --- drop / move ---

    def cmd_layout_drop(self, videos, src_block, dst, zone, is_replace):
        dst_id = getattr(dst, "video_id", None) if dst is not None else None
        row, col = None, None
        # Empty cells have no id; only then ask the view for coordinates.
        if dst is not None and dst_id is None:
            pos = self.grid_position_of(dst)
            if pos is not None:
                row, col = pos

        if src_block is not None:
            with self._undoable():
                if dst is not None and dst is not src_block:
                    self._stop_reordering()
                self._drop_move(src_block, dst, row, col, zone, is_replace, dst_id)
            return

        if dst is not None:
            self._stop_reordering()
        self._drop_new(videos, dst, row, col, zone, is_replace, dst_id)

    def _stop_reordering(self):
        """Reorder to Fit turned off for a drop where a video goes, so that
        it stays there: the order shown is taken for the videos' own. In
        Mosaic too: the tiles' order is where they
        are."""

        if not self._flow.is_reordered:
            return
        if self._mode == GridMode.AUTO_SHAPES:
            self._flow.ids = self._flow.order()
        elif not self._is_mosaic:
            return

        self._flow.is_reordered = False
        PlaylistSettings().set("playlist/grid_reorder", False)

    def _drop_move(self, src_block, dst, row, col, zone, is_replace, dst_id):
        src_id = src_block.video_id
        self._keep_tiles_shown()
        leftover = self._layout.drop(
            [],
            row,
            col,
            zone,
            is_replace=is_replace,
            src_id=src_id,
            dst_id=dst_id,
        )
        if leftover:
            self.warning.emit(
                translate("Warning", "Cannot move the video in that direction.")
            )
            return

        if is_replace and dst is not None and dst is not src_block:
            # in Mosaic, arranged as it goes (see _add_tiles)
            self._ctx.commands.remember_closed([dst])
            self._ctx.commands.remove_video_blocks([dst.video_id])
            return

        if self._is_mosaic and dst is not src_block:
            # the tiles traded, or moved: arranged in the order they now
            # are in
            self._stop_reordering()
            self._arrange()
            self._grid.invalidate()
        self.layout_changed.emit()

    def _drop_new(self, videos, dst, row, col, zone, is_replace, dst_id):
        is_replace = is_replace and dst is not None
        videos = self._clip_videos(list(videos), is_replace=is_replace)
        if not videos:
            return

        # the first one in the place of the video replaced
        if not self._is_room_for(len(videos) - (1 if is_replace else 0)):
            return

        if is_replace:
            videos = self._replace_cell_video(dst, videos)
            dst_id = dst.video_id
            zone = DropZone.AFTER
            if not videos:
                self.layout_changed.emit()
                return

        self._place_dropped_ids(videos, row, col, zone, dst_id)

    def _replace_cell_video(self, dst, videos):
        old_id = dst.video_id
        self._ctx.commands.remember_closed([dst])
        dst.set_video(videos[0])
        self._ctx.video_blocks.reindex(dst)
        self._layout.replace_id(old_id, dst.video_id)
        if self._is_mosaic:
            # arranged anew for its shape, once known (see _fit_tiles_to_shapes)
            self._unshaped.add(dst.video_id)
        # the earlier states have the video it had (see forget_grid_changes)
        self.forget_grid_changes()
        return videos[1:]

    def place_of(self, video_id: str) -> GridCell | TilePlace | int | None:
        """Where a video is, to be put back there (see put_back_videos):
        its cell in a Fixed Grid, its tile in Free Tiles, else its place in
        the order."""

        if self._is_free:
            if not self._free.contains(video_id):
                return None
            return self._free.place_of(video_id, *self._area_size())
        if self._is_fixed:
            return next(
                (c for c in self._grid_layout.cells if c.video_id == video_id), None
            )
        if video_id in self._flow.ids:
            return self._flow.ids.index(video_id)
        return None

    def put_back_videos(self, videos, places) -> None:
        """Videos opened again, each where it was if it can be, else where a
        new one goes."""

        with self._ctx.commands.video_count_batch():
            added = self._ctx.commands.add_video_blocks(videos)
            # those earlier in the order first, each put among the others
            # as it was
            pairs = sorted(
                zip(added, places, strict=True),
                key=lambda pair: pair[1] if isinstance(pair[1], int) else -1,
            )
            for block, place in pairs:
                self._put_back(block.video_id, place)

    def _put_back(self, video_id: str, place) -> None:
        if self._is_free:
            if isinstance(place, TilePlace):
                # beside the others, where they are shown; in Mosaic, only
                # locked, the others arranged around it
                self._free.fill(*self._area_size())
                if not self._is_mosaic:
                    is_put = self._free.put_back(
                        video_id, place, self.is_tile_overlap_on()
                    )
                else:
                    is_put = place.is_locked and self._free.put_back(
                        video_id, place, True
                    )
                    if is_put:
                        self._arrange()
                if is_put:
                    return
            self._add_tiles([video_id])
            # elsewhere, still locked
            if isinstance(place, TilePlace) and place.is_locked:
                self._free.set_locked(video_id, True)
            return

        if self._is_fixed:
            if isinstance(place, GridCell) and self._grid_layout.put_back(
                place.model_copy(update={"video_id": video_id})
            ):
                return
            self._grid_layout.add([video_id])
            return

        if isinstance(place, int):
            self._flow.ids.insert(min(place, len(self._flow.ids)), video_id)
            return
        self._flow.add([video_id])

    def _place_dropped_ids(self, videos, row, col, zone, dst_id):
        with self._ctx.commands.video_count_batch():
            added = self._ctx.commands.add_video_blocks(videos)
            ids = [vb.video_id for vb in added]
            if not ids:
                return

            if self._is_free:
                # where there is room, as any new video's
                self._add_tiles(ids)
                return

            leftover = self._layout.drop(
                ids, row, col, zone, is_replace=False, dst_id=dst_id
            )
            if leftover == ids:
                self.warning.emit(
                    translate("Warning", "Cannot add videos in that direction.")
                )
            if leftover:
                self._ctx.commands.remove_video_blocks(leftover)

    # --- render / layout ---

    def on_single_mode_changed(self):
        if not self._ctx.is_single_mode:
            self._held_place.hide()
            self.layout_changed.emit()
            return

        for empty in self._empty_cells:
            empty.hide()

        strip = self._strip_videos()
        if strip is not None:
            self._held_place.set_video(strip.main)

        self._grid.set_widgets([*self._ctx.video_blocks, self._held_place])
        self._grid.set_place(self._place_single)
        self._grid.activate()
        # the big one, and those in the strip
        self._sync_visibility([widget for widget, _box in self._grid.placed()])
        self._sync_cell_sizable()

    def strip_held_video_at(self, global_pos):
        """The video shown big, where its place held in the Fixed Strip is
        at this point on the screen."""

        place = self._held_place
        if not place.isVisible() or place.video_block not in self._ctx.video_blocks:
            return None
        if place.rect().contains(place.mapFromGlobal(global_pos)):
            return place.video_block
        return None

    def _sync_cell_sizable(self):
        # the buttons on the videos that make their cells bigger and smaller,
        # or their tiles fill the room around them, and so on
        is_sizable = self.is_grid_cell_sizable()
        is_shapable = self.is_grid_cell_shapable()
        is_tile = self._is_free and not self._ctx.is_single_mode
        for vb in self._ctx.video_blocks:
            vb.cell_size.set_sizable(
                is_sizable, is_shapable, is_tile, not self._is_mosaic
            )

    def reload_video_grid(self):
        # Count-changed fires before single mode exits. Skip until the grid
        # is rebuilt with every cell visible.
        if self._reloading or self._ctx.is_single_mode:
            return
        self._reloading = True
        try:
            self._reconcile_layout()
            self._render_video_grid()
        finally:
            self._reloading = False

    def fit_to_shapes(self):
        """Lay the grid out again for a video's shape, which Auto goes by;
        in Single Mode, the strip, whose tiles go by every video's."""

        if self._ctx.is_single_mode:
            if self._strip_videos() is not None:
                self._grid.invalidate()
            return

        if self._is_free:
            self._fit_tiles_to_shapes()
            return

        if self._is_fixed:
            return

        is_shapes = self._mode == GridMode.AUTO_SHAPES
        if not is_shapes and (not self._flow.is_match_shapes or self._flow.size):
            return

        self._grid.invalidate()

    def _place_single(self, width, height):
        # The single video fills the area. Going to the next one shows it and
        # hides the other, and showing lays the area out again.
        strip = self._strip_videos()
        if strip is None:
            return [
                (vb, FULL_BOX) for vb in self._ctx.video_blocks if not vb.isHidden()
            ]

        layout = strip_layout(
            len(strip.strip),
            width,
            height,
            self._strip_shape(),
            self._strip_share,
            strip.side,
        )
        tiles = dict(zip(strip.strip, layout.boxes))
        placed = [(strip.main, layout.main)]
        # in the Fixed Strip, the big one's place held
        held = tiles.pop(strip.main, None)
        if held is not None:
            placed.append((self._held_place, held))
        return placed + list(tiles.items())

    def _strip_videos(self) -> StripVideos | None:
        if not self._ctx.is_single_mode:
            return None
        return self._ctx.commands.strip_videos()

    def _strip_shape(self) -> float:
        # of all the videos, the one shown big too: the strip stays as it is
        # whichever is
        return shape_of_strip(
            [vb.picture_shape or DEFAULT_SHAPE for vb in self._ctx.video_blocks]
        )

    def _strip_lines(self) -> StripLines | None:
        strip = self._strip_videos()
        area = self._grid.geometry()
        if strip is None or area.isEmpty():
            return None

        return StripLines(
            len(strip.strip),
            area.width(),
            area.height(),
            self._strip_shape(),
            strip.main.picture_shape,
            self._strip_share,
            strip.side,
        )

    def _place_flow(self, width, height):
        # on Auto, the lines go by the area too, so they are chosen anew
        # each time the area is laid out: as the window is resized among them
        shapes = {vb.video_id: vb.picture_shape for vb in self._ctx.video_blocks}
        self._flow.fit_to(width, height, shapes)
        return self._flow_cells()

    def _render_video_grid(self):
        if self._ctx.is_single_mode:
            return

        with self.slow_ui_operation():
            self._info_label.hide()
            self._discard_empty_cells()

            if not self._ctx.video_blocks and not self._show_empties:
                widgets = self._grid.set_cells([(self._info_label, FULL_BOX)])
            elif self._is_fixed:
                self._add_empty_cells()
                widgets = [widget for widget, _box in self._fixed_cells()]
                self._grid.set_widgets(widgets)
                self._grid.set_place(self._place_fixed)
            elif self._is_free:
                widgets = self._free_blocks()
                self._grid.set_widgets(widgets)
                self._grid.set_place(self._place_free)
            else:
                widgets = [widget for widget, _box in self._flow_cells()]
                self._grid.set_widgets(widgets)
                self._grid.set_place(self._place_flow)

            # Every cell, hidden or not, in place before any comes on screen.
            self._grid.activate()

            self._sync_visibility(widgets)
            self._sync_cell_sizable()

    def _discard_empty_cells(self):
        for empty in self._empty_cells:
            empty.hide()
            empty.deleteLater()
        self._empty_cells = []
        self._empty_positions = {}

    def _sync_visibility(self, placed):
        placed_set = set(placed)
        for vb in [*self._ctx.video_blocks, self._held_place]:
            if vb not in placed_set:
                vb.hide()

        for widget in placed:
            if widget.isHidden():
                widget.show()

    def _place_free(self, width, height):
        # the area laid out at this size: the tiles no longer as placed, if
        # it was resized (see FreeTiles.boxes)
        self._free.resized_to(width, height)
        if self._is_mosaic and self._arranged_at != self._area_size():
            if self._change_start is None:
                # arranged for the window's new shape as it is resized, in
                # the order they are in: Reorder to Fit, which may take
                # long, once it is done (see _arrange_due)
                self._arrange(is_reordered=False)
            self._arrange_timer.start()
        cells = []
        for video_id, box in self._free.boxes(width, height):
            vb = self._ctx.video_blocks.by_video_id(video_id)
            if vb is not None:
                cells.append((vb, box))
        return cells

    def _free_blocks(self):
        by_video_id = self._ctx.video_blocks.by_video_id
        blocks = (by_video_id(video_id) for video_id in self._free.tiles)
        return [vb for vb in blocks if vb is not None]

    def _place_fixed(self, _width, _height):
        # the lines between the cells go where they are moved to, as they are
        return self._fixed_cells()

    def _add_empty_cells(self):
        """An empty cell for each place in the grid no video covers."""

        for position in self._grid_layout.empty_positions():
            empty = EmptyCell(parent=self.parent())
            self._empty_cells.append(empty)
            self._empty_positions[empty] = position

    def _fixed_cells(self):
        cols, rows = self._grid_layout.displayed_size()

        cells = []
        for cell, box in self._grid_layout.boxes(self._weights):
            vb = self._ctx.video_blocks.by_video_id(cell.video_id)
            if vb is not None:
                cells.append((vb, box))

        for empty in self._empty_cells:
            row, col = self._empty_positions[empty]
            cells.append((empty, grid_box(row, col, rows, cols, weights=self._weights)))

        return cells

    def _flow_cells(self):
        cells = []
        for video_id, box in self._flow.boxes(self._weights):
            vb = self._ctx.video_blocks.by_video_id(video_id)
            if vb is not None:
                cells.append((vb, box))
        return cells
