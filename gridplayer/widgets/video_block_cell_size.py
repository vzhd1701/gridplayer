"""The size of a video block's cell in the grid: its overlay's buttons that
make it a step bigger or smaller, and pick its size, on where there is room.

Whether there is room is looked at for the cell under the pointer only, and
for another once the pointer comes to it: in Fit Shapes, finding a step
that changes a tile lays the grid out again a few times over.

Where the cell goes is the grid's (see GridManager); here is only how the
viewer asks for it.
"""

from functools import partial

from gridplayer.widgets.video_block_guards import VideoBlockPart


class CellSizeControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # whether the buttons are known to be had, for the grid as it is
        self._are_steps_known = True
        # its own button made its cell bigger or smaller
        self._is_stepped = False

    def set_sizable(self, is_sizable: bool, is_shapable: bool):
        """Its overlay's buttons that make its cell bigger and smaller, and
        pick its size where it can be shaped too, the grid just laid out:
        off where there is no room, as looked at once they are seen, the
        pointer on them (see sync_steps)."""

        overlay = self._block.overlay
        overlay.set_cell_size_controls(is_sizable, is_shapable)
        self._are_steps_known = False
        if not overlay.isVisible():
            return
        # the one whose button was just clicked, wherever it went, or under
        # the pointer, at once; the others once the pointer comes to them
        if self._is_stepped or self._block.is_under_cursor():
            self._is_stepped = False
            self.sync_steps()

    def sync_steps(self):
        """Whether there is room for its cell a step bigger, and smaller, on
        its buttons, unless known already: as its overlay is shown, which
        the pointer moving over the cell does."""

        block = self._block
        if self._are_steps_known or not block.overlay.has_cell_size_buttons():
            return
        self._are_steps_known = True

        commands = block._ctx.commands
        block.overlay.set_cell_steps(
            commands.is_grid_cell_steppable("bigger", block.video_id),
            commands.is_grid_cell_steppable("smaller", block.video_id),
        )

    def step(self, step: str):
        self._is_stepped = True
        self._block._ctx.commands.step_grid_cell(step, self._block.video_id)
        # nothing changed, no room: nothing laid out to tell it
        self._is_stepped = False

    def pick(self, under):
        block = self._block
        picker = block._ctx.commands.pick_grid_cell_span(block.video_id, under)
        if picker is None:
            return
        block.overlay.set_cell_size_picking(True)
        picker.closed.connect(partial(block.overlay.set_cell_size_picking, False))
