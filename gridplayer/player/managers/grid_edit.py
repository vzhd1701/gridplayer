from functools import partial

from PyQt5.QtCore import QRect

from gridplayer.params.static import GridMode
from gridplayer.player.managers.layout_edit import LayoutEditManager
from gridplayer.widgets.grid_editor import EditCell, GridEditor
from gridplayer.widgets.grid_span_picker import GridSpanPicker


class GridEditManager(LayoutEditManager):
    """Edit Grid (see cmd_edit_grid): the cells of a Fixed Grid resized and
    moved by hand, in a GridEditor over the grid, until Done.

    An Auto grid is made a Fixed Grid of the size it is first, which Undo
    takes back. While it lasts, every cell of the grid is shown, as with
    Show All Cells, so a video can take the empty ones. A line moved is one
    change to undo, however far.
    """

    @property
    def commands(self):
        return {
            "edit_grid": self.cmd_edit_grid,
            "is_editing_grid": self.is_editing_grid,
            "edit_grid_cells": self.cmd_edit_grid_cells,
            "pick_grid_cell_span": self.cmd_pick_grid_cell_span,
        }

    def is_editing_grid(self) -> bool:
        """Whether the cells or the tiles are edited."""

        return self.is_editing() or self._ctx.commands.is_editing_free_tiles()

    def cmd_edit_grid(self):
        """Edit Grid: the editor of what is shown, as it is: a Fixed Grid's
        or Free Tiles'; an Auto grid made a Fixed Grid of its cells, but Fit
        Shapes made Free Tiles, its videos' sizes only there as they are.
        Done, if either is up."""

        commands = self._ctx.commands
        if self.is_editing():
            self.stop()
        elif commands.is_editing_free_tiles():
            commands.edit_free_tiles()
        elif self._ctx.is_single_mode:
            return
        elif commands.is_grid_free() or commands.is_grid_mode_set_to(
            GridMode.AUTO_SHAPES
        ):
            commands.edit_free_tiles()
        else:
            self.cmd_edit_grid_cells()

    def cmd_edit_grid_cells(self, switched_from=None):
        if self.is_editing():
            self.stop()
            return

        if self._ctx.is_single_mode or not self._ctx.commands.make_grid_fixed():
            return

        self._ctx.commands.set_grid_editing(True)

        commands = self._ctx.commands
        editor = GridEditor(
            can_place=commands.can_place_grid_cell,
            can_resize=commands.can_resize_fixed_grid,
            lines=commands.grid_lines,
            is_snapping=commands.is_grid_line_snap,
            can_fit_lines=commands.is_grid_lines_fittable,
            can_reset_lines=commands.is_grid_lines_moved,
            can_undo=commands.is_grid_undoable,
            can_redo=commands.is_grid_redoable,
            can_reopen=commands.is_any_video_closed,
            parent=self.parent(),
        )
        editor.place_requested.connect(commands.place_grid_cell)
        editor.size_requested.connect(commands.resize_fixed_grid)
        editor.close_requested.connect(self._close_video)
        editor.line_started.connect(commands.begin_grid_change)
        editor.weights_changed.connect(commands.set_grid_weights)
        # one change to undo, however far it was moved
        editor.line_finished.connect(self._refreshing(commands.end_grid_change))
        editor.snapping_toggled.connect(commands.toggle_grid_line_snap)
        editor.fit_lines_requested.connect(self._refreshing(commands.fit_grid_lines))
        editor.reset_lines_requested.connect(
            self._refreshing(commands.reset_grid_lines)
        )
        self._open(editor, switched_from)

    def _closing(self, editor):
        self._ctx.commands.set_grid_editing(False)

    def refresh(self):
        """The editor where the grid is, with its cells as they are now: the
        tiles' instead once the grid is Free Tiles, done with once it is
        neither, or one video fills the window."""

        if self._editor is None:
            return

        if self._ctx.is_single_mode or not self._ctx.commands.is_grid_fixed():
            self._leave()
            return

        state = self._ctx.grid_state
        cells = []
        for cell in state.cells:
            name = self._name_of(cell.video_id)
            if name is None:
                continue
            cells.append(
                EditCell(
                    cell.video_id,
                    name,
                    cell.row,
                    cell.col,
                    cell.rowspan,
                    cell.colspan,
                )
            )

        self._editor.setGeometry(self._ctx.commands.grid_area())
        self._editor.set_grid(
            state.rows, state.cols, state.col_weights, state.row_weights, cells
        )

    def update_snapping(self):
        if self._editor is not None:
            self._editor.update_snapping()

    def cmd_pick_grid_cell_span(self, video_id: str, under: QRect):
        """A video's cell's size picked, from the button for it on the
        video, under it on the screen. Returns the picker shown."""

        commands = self._ctx.commands
        span = commands.grid_cell_span(video_id)
        if span is None or not commands.is_grid_cell_shapable():
            return None

        picker = GridSpanPicker(
            *commands.grid_cell_room(),
            span,
            partial(commands.can_set_grid_cell_span, video_id),
            parent=self.parent(),
        )
        picker.picked.connect(partial(commands.set_grid_cell_span, video_id))
        picker.popup_under(under)
        return picker
