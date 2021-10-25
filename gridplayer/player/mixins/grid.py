import math
from typing import NamedTuple

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGridLayout, QLabel

from gridplayer.params_static import GridMode


class GridDimensions(NamedTuple):
    cols: int
    rows: int


class PlayerGridMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._default_minimum_size = QSize(640, 360)

        self._minimum_video_size = QSize(100, 90)
        self._minimum_size = self._default_minimum_size

        self.setMinimumSize(self._minimum_size)

        self.videogrid = QGridLayout(self)
        self.videogrid.setSpacing(0)
        self.videogrid.setContentsMargins(0, 0, 0, 0)

        self.info_label = QLabel("Drag and drop video files here")
        self.info_label.setAlignment(Qt.AlignCenter)
        font = QFont("Hack", 16, QFont.Bold)
        self.info_label.setFont(font)

    @property
    def grid_dimensions(self):
        grid_y = math.ceil(math.sqrt(len(self.video_blocks)))
        grid_x = math.ceil(len(self.video_blocks) / grid_y)

        if self.playlist.grid_mode == GridMode.AUTO_COLS:
            cols, rows = grid_x, grid_y
        else:
            cols, rows = grid_y, grid_x

        return GridDimensions(cols, rows)

    def reset_grid_stretch(self):
        for c in range(self.videogrid.columnCount()):
            self.videogrid.setColumnStretch(c, 0)

        for r in range(self.videogrid.rowCount()):
            self.videogrid.setRowStretch(r, 0)

    def adjust_grid_stretch(self):
        for c in range(self.grid_dimensions.cols):
            self.videogrid.setColumnStretch(c, 1)

        for r in range(self.grid_dimensions.rows):
            self.videogrid.setRowStretch(r, 1)

    def reload_video_grid(self):
        self._reset_video_grid()

        if not self.is_videos:
            return

        self._adjust_window()

        self._populate_grid()

        self.adjust_grid_stretch()

        self.layout().activate()

    def _reset_video_grid(self):
        self.info_label.hide()

        self.videogrid.removeWidget(self.info_label)

        for vb in self.video_blocks.values():
            self.videogrid.removeWidget(vb)

        self.reset_grid_stretch()

        if not self.is_videos:
            self.videogrid.addWidget(self.info_label, 0, 0)
            self.info_label.show()

    def _adjust_window(self):
        width = self.grid_dimensions.cols * self._minimum_video_size.width()
        height = self.grid_dimensions.rows * self._minimum_video_size.height()

        width = max(width, self._default_minimum_size.width())
        height = max(height, self._default_minimum_size.height())

        self._minimum_size = QSize(width, height)
        self.setMinimumSize(self._minimum_size)

    def _populate_grid(self):
        grid = (
            (col, row)
            for row in range(self.grid_dimensions.rows)
            for col in range(self.grid_dimensions.cols)
        )

        for vb in self.video_blocks.values():
            col, row = next(grid)

            vb.setMinimumSize(self._minimum_vb_size())

            self.videogrid.addWidget(vb, row, col, 1, 1)

    def _minimum_vb_size(self):
        return QSize(
            self._minimum_size.width() / self.grid_dimensions.cols,
            self._minimum_size.height() / self.grid_dimensions.rows,
        )
