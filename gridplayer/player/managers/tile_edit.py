from gridplayer.params.static import GridMode
from gridplayer.player.managers.layout_edit import LayoutEditManager
from gridplayer.utils.keymap import drop_switch_modifier
from gridplayer.widgets.tile_editor import TileEditor, TileSettings


class TileEditManager(LayoutEditManager):
    """Edit Grid in Free Tiles: its tiles moved and sized by hand in a
    TileEditor over them, until Done, as they are outside it (see
    FreeTilesManager), with the keys too, and swapped. Each drag is one change to undo,
    and so are the arrow keys pressed one after another.

    Another grid is made Free Tiles first, its cells the tiles, which Undo
    takes back.
    """

    is_tiles = True

    @property
    def commands(self):
        return {
            "edit_free_tiles": self.cmd_edit_free_tiles,
            "is_editing_free_tiles": self.is_editing,
        }

    def cmd_edit_free_tiles(self, switched_from=None):
        if self.is_editing():
            self.stop()
            return

        commands = self._ctx.commands
        if not self._ctx.is_single_mode and not commands.is_grid_free():
            # the cells made tiles where they are, which Undo takes back
            commands.set_grid_mode(GridMode.FREE)
        if commands.free_page() is None:
            return

        editor = TileEditor(
            drag_of=commands.tile_drag_of,
            settings=TileSettings(
                overlap=commands.tile_overlap,
                set_overlap=commands.set_tile_overlap,
                resize=commands.tile_resize,
                set_resize=commands.set_tile_resize,
                crop=commands.tile_crop,
                set_crop=commands.set_tile_crop,
                is_reordered=commands.is_grid_reorder,
                set_reordered=self._set_reordered,
                is_mosaic=lambda: commands.is_grid_mode_set_to(GridMode.MOSAIC),
                is_snapping=commands.is_grid_line_snap,
                set_snapping=self._set_snapping,
                snaps=commands.tile_snaps,
                set_snaps=commands.set_tile_snaps,
            ),
            swap_key=drop_switch_modifier,
            can_undo=commands.is_grid_undoable,
            can_redo=commands.is_grid_redoable,
            can_reopen=commands.is_any_video_closed,
            parent=self.parent(),
        )
        editor.tiles_changed.connect(self._refreshing(commands.set_free_tiles))
        editor.front_requested.connect(
            self._refreshing(commands.bring_free_tile_to_front)
        )
        editor.change_started.connect(commands.begin_grid_change)
        editor.change_finished.connect(self._refreshing(commands.end_grid_change))
        # the tiles as they were: nothing to undo
        editor.change_cancelled.connect(self._refreshing(commands.cancel_grid_change))
        editor.stack_requested.connect(self._refreshing(commands.stack_free_tile))
        editor.lock_requested.connect(self._refreshing(commands.lock_free_tile))
        editor.close_requested.connect(self._close_video)
        editor.swap_requested.connect(self._swap)
        editor.arrange_requested.connect(commands.arrange_tiles)
        editor.fit_requested.connect(commands.fit_tiles_to_window)
        self._open(editor, switched_from)

    def refresh(self):
        """The editor where the tiles' page is, with the tiles as they are
        now: the cells' instead once the grid is a Fixed Grid, done with
        once it is neither, or in Single Mode."""

        if self._editor is None:
            return

        page = self._ctx.commands.free_page()
        if page is None:
            self._leave()
            return

        names = {}
        for video_id in page.tiles.tiles:
            name = self._name_of(video_id)
            if name is not None:
                names[video_id] = name

        self._editor.setGeometry(page.rect)
        self._editor.set_tiles(page.tiles, names)

    def _set_snapping(self, is_snapping: bool):
        if self._ctx.commands.is_grid_line_snap() != is_snapping:
            self._ctx.commands.toggle_grid_line_snap()

    def _set_reordered(self, is_reordered: bool):
        if self._ctx.commands.is_grid_reorder() != is_reordered:
            self._ctx.commands.switch_is_grid_reorder()

    def _swap(self, video_id: str, other_id: str):
        # as a video dropped on another: they trade tiles, one change
        blocks = self._ctx.video_blocks
        block, other = blocks.by_video_id(video_id), blocks.by_video_id(other_id)
        if block is not None and other is not None:
            # the editor refreshed with the grid laid out again
            self._ctx.commands.layout_drop(
                [], block, other, zone=None, is_replace=False
            )
