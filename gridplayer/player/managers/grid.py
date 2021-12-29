import math
from typing import NamedTuple

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput
from gridplayer.params import GridState
from gridplayer.params_static import (
    PLAYER_INFO_TEXT_SIZE,
    PLAYER_INITIAL_SIZE,
    PLAYER_MIN_VIDEO_SIZE,
    GridMode,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.misc import tr


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


class GridManager(ManagerBase):
    minimum_size_changed = pyqtSignal(QSize)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.grid_state = self.grid_state

        self._grid_mode = Settings().get("playlist/grid_mode")
        self._is_grid_fit = Settings().get("playlist/grid_fit")
        self._grid_size = Settings().get("playlist/grid_size")

        self._default_minimum_size = QSize(*PLAYER_INITIAL_SIZE)
        self._minimum_video_size = QSize(*PLAYER_MIN_VIDEO_SIZE)
        self._minimum_size = self._default_minimum_size

        self._grid = QGridLayout(self.parent())
        self._grid.setSpacing(0)
        self._grid.setContentsMargins(0, 0, 0, 0)

        self._info_label = QLabel(
            tr("Drag and drop video files here"), parent=self.parent()
        )
        self._info_label.setAlignment(Qt.AlignCenter)
        font = QFont("Hack", PLAYER_INFO_TEXT_SIZE, QFont.Bold)
        self._info_label.setFont(font)

    def init(self):
        self.minimum_size_changed.emit(self._minimum_size)
        self.reload_video_grid()

    @property
    def commands(self):
        return {
            "set_grid_mode": self.cmd_set_grid_mode,
            "is_grid_mode_set_to": lambda m: self._grid_mode == m,
            "ask_grid_size": self.cmd_ask_grid_size,
            "get_grid_size": self.cmd_get_grid_size,
            "switch_is_grid_fit": self.cmd_switch_is_grid_fit,
            "is_grid_fit": lambda: self._is_grid_fit,
        }

    @property
    def visible_count(self):
        # Visible (already present) or not explicitly hidden
        # to exclude hidden (e.g. during single mode)
        # and include new blocks that are not yet visible
        return sum(
            w.isVisible() or not w.testAttribute(Qt.WA_WState_ExplicitShowHide)
            for w in self._ctx.video_blocks
        )

    @property
    def grid_dimensions(self):
        if self.visible_count <= 1:
            return GridDimensions(1, 1)

        if self._grid_size == 0:
            grid_size = math.ceil(math.sqrt(self.visible_count))
        else:
            grid_size = self._grid_size

        grid_slices = math.ceil(self.visible_count / grid_size)

        if self._grid_mode == GridMode.AUTO_COLS:
            cols, rows = grid_slices, grid_size
        else:
            cols, rows = grid_size, grid_slices

        return GridDimensions(cols, rows)

    def grid_state(self):
        return GridState(
            mode=self._grid_mode,
            is_fit=self._is_grid_fit,
            size=self._grid_size,
        )

    def set_grid_state(self, state: GridState) -> None:
        self._grid_mode = state.mode
        self._is_grid_fit = state.is_fit
        self._grid_size = state.size

        self.reload_video_grid()

    def cmd_set_grid_mode(self, mode):
        if self._grid_mode == mode:
            return

        self._grid_mode = mode
        self.reload_video_grid()

    def cmd_ask_grid_size(self):
        size = QCustomSpinboxInput.get_int(
            self.parent(), tr("Set grid size"), tr("Auto"), self._grid_size, 0, 1000
        )

        if self._grid_size == size:
            return

        self._grid_size = size
        self.reload_video_grid()

    def cmd_get_grid_size(self):
        if self._grid_size == 0:
            return tr("Auto")

        return str(self._grid_size)

    def cmd_switch_is_grid_fit(self):
        self._is_grid_fit = not self._is_grid_fit
        self.reload_video_grid()

    def adapt_grid(self):
        self._reset_grid_stretch()

        if self.visible_count > 1:
            self._adjust_grid_stretch()

    def reload_video_grid(self):
        self._reset_video_grid()

        if not self._ctx.video_blocks:
            return

        self._adjust_window()
        self._adjust_cells()

        self._populate_grid()

        self.adapt_grid()

        self.parent().layout().activate()

    def _reset_grid_stretch(self):
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)

        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)

    def _adjust_grid_stretch(self):
        for c in range(self.grid_dimensions.cols):
            self._grid.setColumnStretch(c, 1)

        for r in range(self.grid_dimensions.rows):
            self._grid.setRowStretch(r, 1)

    def _reset_video_grid(self):
        self._info_label.hide()

        _clear_layout(self._grid)

        if not self._ctx.video_blocks:
            self._grid.addWidget(self._info_label, 0, 0)
            self._info_label.show()

            self.adapt_grid()

    def _adjust_window(self):
        width = self.grid_dimensions.cols * self._minimum_video_size.width()
        height = self.grid_dimensions.rows * self._minimum_video_size.height()

        width = max(width, self._default_minimum_size.width())
        height = max(height, self._default_minimum_size.height())

        self._minimum_size = QSize(width, height)
        self.minimum_size_changed.emit(self._minimum_size)

    def _adjust_cells(self):
        for vb in self._ctx.video_blocks:
            vb.setMinimumSize(self._minimum_vb_size())

    def _populate_grid(self):
        odd_cells = self.grid_dimensions.max_size - len(self._ctx.video_blocks)

        if odd_cells == 0 or not self._is_grid_fit:
            self._fill_grid(self._ctx.video_blocks)
        else:
            if self._grid_mode == GridMode.AUTO_COLS:
                straight_cells = self.grid_dimensions.rows * (
                    self.grid_dimensions.cols - 1
                )

                self._fill_grid(self._ctx.video_blocks[:straight_cells])
                self._fill_last_col(self._ctx.video_blocks[straight_cells:])
            else:
                straight_cells = self.grid_dimensions.cols * (
                    self.grid_dimensions.rows - 1
                )

                self._fill_grid(self._ctx.video_blocks[:straight_cells])
                self._fill_last_row(self._ctx.video_blocks[straight_cells:])

    def _fill_grid(self, widgets):
        if self._grid_mode == GridMode.AUTO_COLS:
            grid = (
                (col, row)
                for col in range(self.grid_dimensions.cols)
                for row in range(self.grid_dimensions.rows)
            )
        else:
            grid = (
                (col, row)
                for row in range(self.grid_dimensions.rows)
                for col in range(self.grid_dimensions.cols)
            )

        for (col, row), w in zip(grid, widgets):
            self._grid.addWidget(w, row, col, 1, 1)

    def _fill_last_row(self, widgets):
        last_row = QHBoxLayout()

        for w in widgets:
            last_row.addWidget(w, 1)

        last_row_num = self.grid_dimensions.rows - 1

        self._grid.addLayout(last_row, last_row_num, 0, 1, -1)

    def _fill_last_col(self, widgets):
        last_row = QVBoxLayout()

        for w in widgets:
            last_row.addWidget(w, 1)

        last_col_num = self.grid_dimensions.cols - 1

        self._grid.addLayout(last_row, 0, last_col_num, -1, 1)

    def _minimum_vb_size(self):
        return QSize(
            self._minimum_size.width() / self.grid_dimensions.cols,
            self._minimum_size.height() / self.grid_dimensions.rows,
        )
