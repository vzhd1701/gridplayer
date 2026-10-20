import contextlib
import random
from typing import NamedTuple

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput, QFixedGridSizeDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.grid_state import GridState
from gridplayer.params.static import GridMode
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import (
    FULL_BOX,
    CellLayout,
    FlowLayout,
    FlowMode,
    GridLayout,
    Layout,
    grid_box,
)
from gridplayer.utils.qt import count_txt, translate
from gridplayer.widgets.empty_cell import EmptyCell


class GridDimensions(NamedTuple):
    cols: int
    rows: int

    @property
    def max_size(self):
        return self.cols * self.rows


def _flow_mode(mode: GridMode) -> FlowMode:
    if mode == GridMode.AUTO_COLS:
        return FlowMode.COLS
    if mode == GridMode.AUTO_SHAPES:
        return FlowMode.SHAPES
    return FlowMode.ROWS


class GridManager(ManagerBase):
    warning = pyqtSignal(str)
    layout_changed = pyqtSignal()

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
        )
        self._empty_cells = []
        self._empty_positions = {}
        self._add_anchor = None
        self._reloading = False

        self._grid = CellLayout(self.parent())

        self._info_label = EmptyCell(
            message=translate("Main Window", "Drag and drop media files or URLs here"),
            parent=self.parent(),
        )

    def init(self):
        self.layout_changed.emit()

    # --- commands / public queries ---

    @property
    def commands(self):
        return {
            "set_grid_mode": self.cmd_set_grid_mode,
            "is_grid_mode_set_to": lambda m: self._mode == m,
            "grid_drop_mode": self.grid_drop_mode,
            "ask_grid_size": self.cmd_ask_grid_size,
            "get_grid_size": self.cmd_get_grid_size,
            "switch_is_grid_fit": self.cmd_switch_is_grid_fit,
            "is_grid_fit": lambda: self._flow.is_fit,
            "switch_is_grid_match_shapes": self.cmd_switch_is_grid_match_shapes,
            "is_grid_match_shapes": lambda: self._flow.is_match_shapes,
            "is_grid_size_auto": lambda: self._flow.size == 0,
            "is_grid_preallocate": lambda: self._grid_layout.preallocate,
            "switch_grid_preallocate": self.cmd_switch_grid_preallocate,
            "ask_fixed_grid_size": self.cmd_ask_fixed_grid_size,
            "get_fixed_grid_size": self.cmd_get_fixed_grid_size,
            "add_videos_to_layout": self.add_videos_to_layout,
            "grid_free_capacity": lambda: self._layout.free_capacity(),
            "layout_drop": self.cmd_layout_drop,
            "layout_order": lambda: self._layout.order(),
            "shuffle_layout": self.cmd_shuffle_layout,
            "get_cell_at": self.get_cell_at,
            "set_add_anchor": self.set_add_anchor,
            "grid_cell_count": lambda: self.grid_dimensions.max_size,
            "set_grid_state": self.set_grid_state,
            "apply_grid_config": self.apply_grid_config,
        }

    @property
    def _is_fixed(self):
        return self._mode == GridMode.FIXED

    @property
    def _layout(self) -> Layout:
        return self._grid_layout if self._is_fixed else self._flow

    @property
    def grid_dimensions(self):
        cols, rows = self._layout.displayed_size()
        return GridDimensions(cols, rows)

    @property
    def _show_empties(self):
        return self._is_fixed and self._grid_layout.preallocate

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
            size=self._flow.size,
            video_order=list(self._flow.ids),
            rows=self._grid_layout.max_rows,
            cols=self._grid_layout.max_cols,
            preallocate=self._grid_layout.preallocate,
            cells=list(self._grid_layout.cells),
        )

    def set_grid_state(self, state: GridState) -> None:
        self._mode = state.mode
        self._flow.mode = _flow_mode(state.mode)
        self._flow.is_fit = state.is_fit
        self._flow.is_match_shapes = state.is_match_shapes
        self._flow.size = state.size
        self._flow.ids = list(state.video_order)
        self._grid_layout.max_rows = max(1, state.rows)
        self._grid_layout.max_cols = max(1, state.cols)
        self._grid_layout.preallocate = state.preallocate
        self._grid_layout.cells = [cell.model_copy() for cell in state.cells]

        if self._is_fixed:
            self._grid_layout.resize(
                self._grid_layout.max_rows,
                self._grid_layout.max_cols,
                self._grid_layout.preallocate,
            )

        if self._ctx.video_blocks:
            self._reconcile_layout()

        self._render_video_grid()

    def apply_grid_config(self, config: GridState) -> bool:
        """Apply mode/size/fit/match shapes/rows/cols/preallocate like the Grid menu.

        Restores do not use this — ``set_grid_state`` keeps cell positions.
        Returns False if the user cancelled a confirmation dialog.
        """
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
            and self._flow.size == config.size
        )
        if same_fixed or same_flow:
            self._flow.is_fit = config.is_fit
            self._flow.is_match_shapes = config.is_match_shapes
            self._flow.size = config.size
            return True

        if mode == GridMode.FIXED:
            if not self._apply_fixed(rows, cols, preallocate):
                return False
            self._flow.is_fit = config.is_fit
            self._flow.is_match_shapes = config.is_match_shapes
            self._flow.size = config.size
            return True

        if self._is_fixed and not self._leave_fixed():
            return False

        self._mode = mode
        self._flow.mode = _flow_mode(mode)
        self._flow.is_fit = config.is_fit
        self._flow.is_match_shapes = config.is_match_shapes
        self._flow.size = config.size
        self.layout_changed.emit()
        return True

    def grid_drop_mode(self) -> GridMode:
        """The mode drops go by: before or after a video along the line it
        is in, a row or a column, or on any side in Fixed Grid."""

        if self._mode != GridMode.AUTO_SHAPES:
            return self._mode
        return GridMode.AUTO_COLS if self._flow.is_columns() else GridMode.AUTO_ROWS

    def grid_position_of(self, widget):
        return self._empty_positions.get(widget)

    def get_cell_at(self, global_pos):
        for widget in (
            *self._ctx.video_blocks,
            *self._empty_cells,
            self._info_label,
        ):
            if widget.isVisible() and widget.rect().contains(
                widget.mapFromGlobal(global_pos)
            ):
                return widget
        return None

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
        if not videos:
            return []

        return self._ctx.commands.add_video_blocks(videos)

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

        if mode == GridMode.FIXED:
            self._ask_and_apply_fixed(include_preallocate=True)
            return

        if self._is_fixed and not self._leave_fixed():
            return

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

        if self._flow.size == size:
            return

        self._flow.size = size
        PlaylistSettings().set("playlist/grid_size", size)
        self.layout_changed.emit()

    def cmd_get_grid_size(self):
        if self._flow.size == 0:
            return translate("Grid Size", "Auto")

        return str(self._flow.size)

    def cmd_switch_is_grid_fit(self):
        self._flow.is_fit = not self._flow.is_fit
        PlaylistSettings().set("playlist/grid_fit", self._flow.is_fit)
        self.layout_changed.emit()

    def cmd_switch_is_grid_match_shapes(self):
        self._flow.is_match_shapes = not self._flow.is_match_shapes
        PlaylistSettings().set("playlist/grid_match_shapes", self._flow.is_match_shapes)
        self.layout_changed.emit()

    def cmd_get_fixed_grid_size(self):
        return f"{self._grid_layout.max_cols}x{self._grid_layout.max_rows}"

    def cmd_ask_fixed_grid_size(self):
        self._ask_and_apply_fixed(include_preallocate=not self._is_fixed)

    def cmd_switch_grid_preallocate(self):
        if not self._is_fixed:
            return
        self._grid_layout.preallocate = not self._grid_layout.preallocate
        if not self._grid_layout.preallocate:
            self._grid_layout.compact_edges()
        PlaylistSettings().set(
            "playlist/grid_preallocate", self._grid_layout.preallocate
        )
        self.layout_changed.emit()

    def cmd_shuffle_layout(self):
        self._layout.shuffle()
        self.layout_changed.emit()

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

        session = PlaylistSettings()
        session.set("playlist/grid_mode", GridMode.FIXED)
        session.set("playlist/grid_rows", new_rows)
        session.set("playlist/grid_cols", new_cols)
        if include_preallocate:
            session.set("playlist/grid_preallocate", new_preallocate)
        return True

    def _apply_fixed(self, rows, cols, preallocate) -> bool:
        if self._is_fixed:
            return self._resize_fixed(rows, cols, preallocate)

        live_set = set(self._ctx.video_blocks.video_ids)
        ordered = [i for i in self._flow.order() if i in live_set]
        ordered.extend(i for i in self._ctx.video_blocks.video_ids if i not in ordered)
        extra_ids = ordered[rows * cols :]
        keep_ids = ordered[: rows * cols]
        if extra_ids and not self._confirm_overflow(rows * cols, len(extra_ids)):
            return False

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
        for video_id in list(self._layout.order()):
            if video_id not in live_set:
                self._layout.remove(video_id)
        new_ids = [
            i for i in self._ctx.video_blocks.video_ids if not self._layout.contains(i)
        ]
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
            self._drop_move(src_block, dst, row, col, zone, is_replace, dst_id)
            return

        self._drop_new(videos, dst, row, col, zone, is_replace, dst_id)

    def _drop_move(self, src_block, dst, row, col, zone, is_replace, dst_id):
        src_id = src_block.video_id
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
            self._ctx.commands.remove_video_blocks([dst.video_id])
            return

        self.layout_changed.emit()

    def _drop_new(self, videos, dst, row, col, zone, is_replace, dst_id):
        videos = self._clip_videos(
            list(videos), is_replace=is_replace and dst is not None
        )
        if not videos:
            return

        if is_replace and dst is not None:
            videos = self._replace_cell_video(dst, videos)
            dst_id = dst.video_id
            zone = DropZone.AFTER
            if not videos:
                self.layout_changed.emit()
                return

        self._place_dropped_ids(videos, row, col, zone, dst_id)

    def _replace_cell_video(self, dst, videos):
        old_id = dst.video_id
        dst.set_video(videos[0])
        self._ctx.video_blocks.reindex(dst)
        self._layout.replace_id(old_id, dst.video_id)
        return videos[1:]

    def _place_dropped_ids(self, videos, row, col, zone, dst_id):
        with self._ctx.commands.video_count_batch():
            added = self._ctx.commands.add_video_blocks(videos)
            ids = [vb.video_id for vb in added]
            if not ids:
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
        if self._ctx.is_single_mode:
            for empty in self._empty_cells:
                empty.hide()

            self._grid.set_place(self._place_single)
            self._grid.activate()
            return
        self.layout_changed.emit()

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
        """Lay the grid out again for a video's shape, which Auto goes by."""

        if self._is_fixed:
            return

        is_shapes = self._mode == GridMode.AUTO_SHAPES
        if not is_shapes and (not self._flow.is_match_shapes or self._flow.size):
            return

        if self._ctx.is_single_mode:
            return

        self._grid.invalidate()

    def _place_single(self, _width, _height):
        # The single video fills the area. Going to the next one shows it and
        # hides the other, and showing lays the area out again.
        return [(vb, FULL_BOX) for vb in self._ctx.video_blocks if not vb.isHidden()]

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
                widgets = self._grid.set_cells(self._fixed_cells())
            else:
                widgets = [widget for widget, _box in self._flow_cells()]
                self._grid.set_widgets(widgets)
                self._grid.set_place(self._place_flow)

            # Every cell, hidden or not, in place before any comes on screen.
            self._grid.activate()

            self._sync_visibility(widgets)

    def _discard_empty_cells(self):
        for empty in self._empty_cells:
            empty.hide()
            empty.deleteLater()
        self._empty_cells = []
        self._empty_positions = {}

    def _sync_visibility(self, placed):
        placed_set = set(placed)
        for vb in self._ctx.video_blocks:
            if vb not in placed_set:
                vb.hide()

        for widget in placed:
            if widget.isHidden():
                widget.show()

    def _fixed_cells(self):
        cols, rows = self._grid_layout.displayed_size()

        cells = []
        covered = set()
        for cell, box in self._grid_layout.boxes():
            vb = self._ctx.video_blocks.by_video_id(cell.video_id)
            if vb is None:
                continue
            cells.append((vb, box))
            covered.update(
                (row, col)
                for row in range(cell.row, cell.row + cell.rowspan)
                for col in range(cell.col, cell.col + cell.colspan)
            )

        for row in range(rows):
            for col in range(cols):
                if (row, col) in covered:
                    continue
                empty = EmptyCell(parent=self.parent())
                self._empty_cells.append(empty)
                self._empty_positions[empty] = (row, col)
                cells.append((empty, grid_box(row, col, rows, cols)))

        return cells

    def _flow_cells(self):
        cells = []
        for video_id, box in self._flow.boxes():
            vb = self._ctx.video_blocks.by_video_id(video_id)
            if vb is not None:
                cells.append((vb, box))
        return cells
