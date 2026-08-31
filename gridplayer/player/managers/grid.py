import contextlib
import random
from typing import NamedTuple

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput, QFixedGridSizeDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.grid_state import GridState
from gridplayer.params.static import (
    FONT_SIZE_BIG_INFO,
    PLAYER_INITIAL_SIZE,
    PLAYER_MIN_VIDEO_SIZE,
    GridMode,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout import FlowLayout, FlowMode, GridLayout, Layout
from gridplayer.utils.qt import translate
from gridplayer.widgets.empty_cell import EmptyCell


class GridDimensions(NamedTuple):
    cols: int
    rows: int

    @property
    def max_size(self):
        return self.cols * self.rows


def _clear_layout(layout):
    for _ in range(layout.count()):
        l_item = layout.takeAt(0)

        sublay = l_item.layout()

        if sublay is not None:
            _clear_layout(sublay)
            sublay.deleteLater()


def _flow_mode(mode: GridMode) -> FlowMode:
    return FlowMode.COLS if mode == GridMode.AUTO_COLS else FlowMode.ROWS


class GridManager(ManagerBase):
    minimum_size_changed = pyqtSignal(QSize)
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
        )
        self._empty_cells = []
        self._reloading = False

        self._default_minimum_size = QSize(*PLAYER_INITIAL_SIZE)
        self._minimum_video_size = QSize(*PLAYER_MIN_VIDEO_SIZE)
        self._minimum_size = self._default_minimum_size

        self._grid = QGridLayout(self.parent())
        self._grid.setSpacing(0)
        self._grid.setContentsMargins(0, 0, 0, 0)

        self._info_label = QLabel(
            translate("Main Window", "Drag and drop media files or URLs here"),
            parent=self.parent(),
        )
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setWordWrap(True)
        self._info_label.setMargin(20)
        font = QFont("Hack", FONT_SIZE_BIG_INFO, QFont.Bold)
        self._info_label.setFont(font)

    def init(self):
        self.minimum_size_changed.emit(self._minimum_size)
        self.layout_changed.emit()

    # --- commands / public queries ---

    @property
    def commands(self):
        return {
            "set_grid_mode": self.cmd_set_grid_mode,
            "is_grid_mode_set_to": lambda m: self._mode == m,
            "ask_grid_size": self.cmd_ask_grid_size,
            "get_grid_size": self.cmd_get_grid_size,
            "switch_is_grid_fit": self.cmd_switch_is_grid_fit,
            "is_grid_fit": lambda: self._flow.is_fit,
            "is_grid_preallocate": lambda: self._grid_layout.preallocate,
            "switch_grid_preallocate": self.cmd_switch_grid_preallocate,
            "ask_fixed_grid_size": self.cmd_ask_fixed_grid_size,
            "get_fixed_grid_size": self.cmd_get_fixed_grid_size,
            "add_videos_to_layout": self.add_videos_to_layout,
            "layout_drop": self.cmd_layout_drop,
            "layout_order": lambda: self._layout.order(),
            "shuffle_layout": self.cmd_shuffle_layout,
            "get_cell_at": self.get_cell_at,
            "grid_cell_count": lambda: self.grid_dimensions.max_size,
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
        self._flow.size = state.size
        self._flow.ids = list(state.video_order)
        self._grid_layout.max_rows = max(1, state.rows)
        self._grid_layout.max_cols = max(1, state.cols)
        self._grid_layout.preallocate = state.preallocate
        self._grid_layout.cells = [cell.model_copy() for cell in state.cells]

        if self._ctx.video_blocks:
            self._reconcile_layout()

        self._render_video_grid()

    def grid_position_of(self, widget):
        index = self._grid.indexOf(widget)
        if index < 0:
            return None
        row, col, _rowspan, _colspan = self._grid.getItemPosition(index)
        return row, col

    def get_cell_at(self, global_pos):
        for widget in (*self._ctx.video_blocks, *self._empty_cells):
            if widget.isVisible() and widget.rect().contains(
                widget.mapFromGlobal(global_pos)
            ):
                return widget
        return None

    def add_videos_to_layout(self, videos):
        videos = list(videos)
        if self._ctx.is_shuffle_on_load:
            random.shuffle(videos)
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
        self.layout_changed.emit()

    def cmd_ask_grid_size(self):
        size = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate("Dialog - Set grid size", "Set grid size", "Header"),
            special_text=translate("Grid Size", "Auto"),
            initial_value=self._flow.size,
            _min=0,
            _max=1000,
        )

        if self._flow.size == size:
            return

        self._flow.size = size
        self.layout_changed.emit()

    def cmd_get_grid_size(self):
        if self._flow.size == 0:
            return translate("Grid Size", "Auto")

        return str(self._flow.size)

    def cmd_switch_is_grid_fit(self):
        self._flow.is_fit = not self._flow.is_fit
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
            return

        new_rows, new_cols, new_preallocate = result
        self._apply_fixed(new_rows, new_cols, new_preallocate)

    def _apply_fixed(self, rows, cols, preallocate):
        if self._is_fixed:
            self._resize_fixed(rows, cols, preallocate)
            return

        live_set = set(self._ctx.video_blocks.video_ids)
        ordered = [i for i in self._flow.order() if i in live_set]
        ordered.extend(i for i in self._ctx.video_blocks.video_ids if i not in ordered)
        extra_ids = ordered[rows * cols :]
        keep_ids = ordered[: rows * cols]
        if extra_ids and not self._confirm_overflow(rows * cols, len(extra_ids)):
            return

        self._mode = GridMode.FIXED
        self._grid_layout.max_rows = rows
        self._grid_layout.max_cols = cols
        self._grid_layout.preallocate = preallocate
        self._grid_layout.pack_flow(keep_ids)
        if extra_ids:
            self._ctx.commands.remove_video_blocks(extra_ids)
            return

        self.layout_changed.emit()

    def _resize_fixed(self, rows, cols, preallocate):
        snapshot = self._grid_layout.copy()
        leftover = self._grid_layout.resize(rows, cols, preallocate)

        if leftover:
            if not self._confirm_overflow(rows * cols, len(leftover)):
                self._grid_layout = snapshot
                return
            self._ctx.commands.remove_video_blocks(leftover)
            return

        self.layout_changed.emit()

    def _leave_fixed(self):
        holes = self._grid_layout.empty_positions(preallocate=False)
        if holes:
            ret = QCustomMessageBox.question(
                self.parent(),
                translate("Dialog - Set grid size", "Set grid size", "Header"),
                translate(
                    "Warning",
                    "Empty cells will be removed. Videos keep their current order.",
                ),
            )
            if ret != QMessageBox.Yes:
                return False

        self._flow.ids = self._grid_layout.order()
        self._grid_layout.cells = []
        return True

    def _confirm_overflow(self, capacity, count) -> bool:
        msg = (
            translate(
                "Warning",
                "This grid can hold {CAPACITY} videos. {COUNT} videos will be closed.",
            )
            .replace("{CAPACITY}", str(capacity))
            .replace("{COUNT}", str(count))
        )
        ret = QCustomMessageBox.cancellable_question(
            self.parent(),
            translate("Dialog - Set grid size", "Set grid size", "Header"),
            msg,
        )
        return ret == QMessageBox.Yes

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
            # Hidden empties stay in the layout at size 0; un-hiding does not
            # restore them. Take them out so the active video can fill, then
            # rebuild on the way out.
            self.adapt_grid()
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

    def adapt_grid(self, dims=None):
        self._reset_grid_stretch()

        if dims is None:
            dims = self.grid_dimensions

        show_stretch = not self._ctx.is_single_mode and dims.max_size > 1
        if show_stretch:
            self._adjust_grid_stretch(dims)

        for empty in self._empty_cells:
            empty.setVisible(not self._ctx.is_single_mode)

    def _render_video_grid(self):
        if self._ctx.is_single_mode:
            return

        dims = self.grid_dimensions

        with self.slow_ui_operation():
            self._reset_video_grid()

            if not self._ctx.video_blocks and not self._show_empties:
                self._grid.activate()
                return

            for vb in self._ctx.video_blocks:
                vb.show()

            self._adjust_window(dims)
            if self._is_fixed:
                self._populate_fixed(dims)
            else:
                self._adjust_cells(dims)
                self._populate_flow(dims)

            self.adapt_grid(dims)

            self._grid.activate()

    def _reset_grid_stretch(self):
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)

        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)

    def _adjust_grid_stretch(self, dims):
        for c in range(dims.cols):
            self._grid.setColumnStretch(c, 1)

        for r in range(dims.rows):
            self._grid.setRowStretch(r, 1)

    def _discard_empty_cells(self):
        for empty in self._empty_cells:
            self._grid.removeWidget(empty)
            empty.hide()
            empty.deleteLater()
        self._empty_cells = []

    def _reset_video_grid(self):
        self._info_label.hide()
        self._discard_empty_cells()

        _clear_layout(self._grid)

        if not self._ctx.video_blocks and not self._show_empties:
            self._grid.addWidget(self._info_label, 0, 0)
            self._info_label.show()

            self.adapt_grid()

    def _adjust_window(self, dims):
        width = dims.cols * self._minimum_video_size.width()
        height = dims.rows * self._minimum_video_size.height()

        width = max(width, self._default_minimum_size.width())
        height = max(height, self._default_minimum_size.height())

        self._minimum_size = QSize(width, height)
        self.minimum_size_changed.emit(self._minimum_size)

    def _adjust_cells(self, dims):
        min_size = self._minimum_vb_size(dims)
        for vb in self._ctx.video_blocks:
            vb.setMinimumSize(min_size)

    def _populate_fixed(self, dims):
        min_size = self._minimum_vb_size(dims)
        placed = set()

        for row in range(dims.rows):
            for col in range(dims.cols):
                vb = self._block_at(row, col)
                if vb is not None and vb not in placed:
                    vb.setMinimumSize(min_size)
                    self._grid.addWidget(vb, row, col, 1, 1)
                    placed.add(vb)
                    continue

                empty = EmptyCell(parent=self.parent())
                empty.setMinimumSize(min_size)
                self._empty_cells.append(empty)
                self._grid.addWidget(empty, row, col, 1, 1)

    def _minimum_vb_size(self, dims):
        return QSize(
            self._minimum_size.width() // dims.cols,
            self._minimum_size.height() // dims.rows,
        )

    def _populate_flow(self, dims):
        widgets = self._ctx.video_blocks.blocks_for_ids(self._flow.order())
        odd_cells = dims.max_size - len(widgets)

        if odd_cells == 0 or not self._flow.is_fit:
            self._fill_grid(widgets, dims)
        elif self._flow.mode == FlowMode.COLS:
            straight_cells = dims.rows * (dims.cols - 1)
            self._fill_grid(widgets[:straight_cells], dims)
            self._fill_last_col(widgets[straight_cells:], dims)
        else:
            straight_cells = dims.cols * (dims.rows - 1)
            self._fill_grid(widgets[:straight_cells], dims)
            self._fill_last_row(widgets[straight_cells:], dims)

    def _fill_grid(self, widgets, dims):
        if self._flow.mode == FlowMode.COLS:
            grid = ((col, row) for col in range(dims.cols) for row in range(dims.rows))
        else:
            grid = ((col, row) for row in range(dims.rows) for col in range(dims.cols))

        for (col, row), w in zip(grid, widgets):
            self._grid.addWidget(w, row, col, 1, 1)

    def _fill_last_row(self, widgets, dims):
        last_row = QHBoxLayout()

        for w in widgets:
            last_row.addWidget(w, 1)

        self._grid.addLayout(last_row, dims.rows - 1, 0, 1, -1)

    def _fill_last_col(self, widgets, dims):
        last_col = QVBoxLayout()

        for w in widgets:
            last_col.addWidget(w, 1)

        self._grid.addLayout(last_col, 0, dims.cols - 1, -1, 1)
