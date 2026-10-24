from functools import partial

from PyQt5.QtCore import QEvent, QRect, QTimer

from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.keymap import key_sequence_from_event, normalize_key_sequence
from gridplayer.widgets.grid_editor import EditCell, GridEditor
from gridplayer.widgets.grid_span_picker import GridSpanPicker

# the player's actions its keys still do while the cells are edited
EDITOR_ACTIONS = ("Undo Grid Change", "Redo Grid Change")


class GridEditManager(ManagerBase):
    """Edit Grid: the cells of a Fixed Grid resized and moved by hand,
    in a GridEditor over the grid, until Done.

    An Auto grid is made a Fixed Grid of the size it is first, which Undo
    takes back. While it lasts, every cell of the grid is shown, as with
    Show All Cells, so a video can take the empty ones, and the videos'
    overlays are hidden: the editor draws their names instead. Each change
    is one to undo, with the player's own keys for it or the editor's
    buttons: a line moved too, however far. A video closed from it is not.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._editor: GridEditor | None = None

        # the player moved or resized: once its grid has been laid out
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.setInterval(0)
        self._follow_timer.timeout.connect(self.refresh)

    @property
    def commands(self):
        return {
            "edit_grid_cells": self.cmd_edit_grid_cells,
            "is_editing_grid_cells": self.is_editing,
            "pick_grid_cell_span": self.cmd_pick_grid_cell_span,
        }

    @property
    def event_map(self):
        return {
            QEvent.Move: self._follow,
            QEvent.Resize: self._follow,
        }

    def _follow(self):
        if self._editor is not None:
            self._follow_timer.start()

    def is_editing(self) -> bool:
        return self._editor is not None

    def cmd_edit_grid_cells(self):
        if self.is_editing():
            self.stop()
            return

        if self._ctx.is_single_mode or not self._ctx.commands.make_grid_fixed():
            return

        self._ctx.commands.set_grid_editing(True)
        self._ctx.commands.set_disable_overlay(True)

        commands = self._ctx.commands
        editor = GridEditor(
            can_place=commands.can_place_grid_cell,
            can_resize=commands.can_resize_fixed_grid,
            lines=commands.grid_lines,
            is_snapping=commands.is_grid_line_snap,
            can_undo=commands.is_grid_undoable,
            can_redo=commands.is_grid_redoable,
            parent=self.parent(),
        )
        editor.place_requested.connect(commands.place_grid_cell)
        editor.size_requested.connect(commands.resize_fixed_grid)
        editor.close_requested.connect(self._close_video)
        editor.line_started.connect(commands.begin_grid_change)
        editor.weights_changed.connect(commands.set_grid_weights)
        editor.line_finished.connect(self._line_finished)
        editor.undo_requested.connect(self._ctx.actions["Undo Grid Change"].trigger)
        editor.redo_requested.connect(self._ctx.actions["Redo Grid Change"].trigger)
        editor.done.connect(self.stop)
        editor.key_pressed.connect(self._key_pressed)
        self._editor = editor

        self.refresh()
        editor.show()
        editor.raise_()
        editor.activateWindow()
        editor.setFocus()

    def stop(self):
        if self._editor is None:
            return

        editor, self._editor = self._editor, None
        editor.hide()
        editor.deleteLater()

        self._ctx.commands.set_grid_editing(False)
        # as the user has it, should it have been changed meanwhile
        self._ctx.commands.set_disable_overlay(
            PlaylistSettings().get("playlist/disable_overlay")
        )
        self.parent().activateWindow()

    def refresh(self):
        """The editor where the grid is, with its cells as they are now: done
        with, once the grid is no Fixed Grid, or one video fills the
        window."""

        if self._editor is None:
            return

        if self._ctx.is_single_mode or not self._ctx.commands.is_grid_fixed():
            self.stop()
            return

        state = self._ctx.grid_state
        cells = []
        for cell in state.cells:
            block = self._ctx.video_blocks.by_video_id(cell.video_id)
            if block is None:
                continue
            cells.append(
                EditCell(
                    cell.video_id,
                    block.title or block.video_params.uri_name,
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

    def update_undo(self):
        # what there is to undo, known once a change has been made
        if self._editor is not None:
            self._editor.update_undo()

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

    def _close_video(self, video_id: str):
        block = self._ctx.video_blocks.by_video_id(video_id)
        if block is not None:
            block.close()

    def _line_finished(self):
        # one change to undo, however far it was moved
        self._ctx.commands.end_grid_change()
        self.refresh()

    def _key_pressed(self, event):
        sequence = key_sequence_from_event(event)
        if sequence is None:
            return
        for name in EDITOR_ACTIONS:
            action = self._ctx.actions[name]
            if sequence in map(normalize_key_sequence, action.shortcuts()):
                action.trigger()
                return
