from PyQt5.QtCore import QEvent, QTimer

from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.keymap import key_sequence_from_event, normalize_key_sequence
from gridplayer.widgets.layout_editor import LayoutEditor, keys_text

# the player's actions its keys still do while the layout is edited, by
# what the editor's buttons for them do
EDITOR_ACTIONS = {
    "undo": "Undo Grid Change",
    "redo": "Redo Grid Change",
    "reopen": "Reopen Closed Video",
}


class LayoutEditManager(ManagerBase):
    """An editor of the layout over the grid (see LayoutEditor), until
    Done: Edit Grid's (GridEditManager) or Edit Tiles' (TileEditManager).

    While it lasts, the videos' overlays are hidden: the editor draws their
    names instead. Each change is one to undo, with the player's own keys
    for it or the editor's buttons. A video closed from it is not: Reopen
    Closed Video, beside them, opens it again.
    """

    # which it edits, of the two: Free Tiles, or a Fixed Grid
    is_tiles = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._editor: LayoutEditor | None = None

        # the player moved or resized: once its grid has been laid out
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.setInterval(0)
        self._follow_timer.timeout.connect(self.refresh)

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

    def _open(self, editor: LayoutEditor, switched_from=None):
        """The editor shown over the grid, the overlays hidden; going on
        from the other kind of editor, if switched from it (see
        LayoutEditor.continue_from)."""

        self._ctx.commands.set_disable_overlay(True)

        actions = self._ctx.actions
        for button, name in EDITOR_ACTIONS.items():
            getattr(editor, f"{button}_requested").connect(actions[name].trigger)
        editor.done.connect(self.stop)
        editor.kind_requested.connect(self._switch)
        editor.key_pressed.connect(self._key_pressed)
        editor.set_action_keys(
            {
                # the first key, if any
                button: keys_text(*actions[name].shortcuts()[:1])
                for button, name in EDITOR_ACTIONS.items()
            }
        )
        self._editor = editor

        self.refresh()
        if switched_from is not None:
            editor.continue_from(switched_from)
        editor.show()
        editor.raise_()
        editor.activateWindow()
        editor.setFocus()

    def stop(self, is_switching: bool = False):
        """The editor gone; for the other kind of editor (is_switching), the
        overlays left hidden, for it."""

        if self._editor is None:
            return

        editor, self._editor = self._editor, None
        editor.finish()
        self._closing(editor)
        editor.hide()
        editor.deleteLater()

        if is_switching:
            return

        self._restore_overlay()
        self.parent().activateWindow()

    def _restore_overlay(self):
        # as the user has it, should it have been changed meanwhile
        self._ctx.commands.set_disable_overlay(
            PlaylistSettings().get("playlist/disable_overlay")
        )

    def _switch(self, is_tiles: bool):
        """The other kind of editor, from the switch on the bar, the layout
        made its kind: Free Tiles or a Fixed Grid. The bar where it was."""

        editor = self._editor
        self.stop(is_switching=True)
        commands = self._ctx.commands
        if is_tiles:
            commands.edit_free_tiles(editor)
        else:
            commands.edit_grid_cells(editor)

        if not commands.is_editing_grid():
            # it could not be made that kind: nothing to edit, the overlays
            # back
            self._restore_overlay()

    def _leave(self):
        """The layout no longer the kind edited, undone or redone, say: the
        other kind's editor, if it is that, else done."""

        commands = self._ctx.commands
        if self._ctx.is_single_mode:
            self.stop()
        elif commands.is_grid_free() and not self.is_tiles:
            self._switch(True)
        elif commands.is_grid_fixed() and self.is_tiles:
            self._switch(False)
        else:
            # an Auto grid again, or the kind edited with nothing of it to
            # edit now, no room for the tiles: done
            self.stop()

    def _closing(self, editor: LayoutEditor):
        """The editor going, before the overlays come back."""

    def refresh(self):
        """The editor where the grid is, with what it edits as it is now;
        done with, once there is nothing of it to edit."""

        raise NotImplementedError

    def _refreshing(self, command):
        """A command of the editor's, the editor shown the grid as it leaves
        it: those changing it by hand only lay it out again, with nothing
        said (see layout_changed)."""

        def run(*args):
            command(*args)
            self.refresh()

        return run

    def update_undo(self):
        # what there is to undo, known once a change has been made
        if self._editor is not None:
            self._editor.update_undo()

    def _close_video(self, video_id: str):
        block = self._ctx.video_blocks.by_video_id(video_id)
        if block is not None:
            block.close()

    def _name_of(self, video_id: str) -> str | None:
        block = self._ctx.video_blocks.by_video_id(video_id)
        if block is None:
            return None
        return block.title or block.video_params.uri_name

    def _key_pressed(self, event):
        sequence = key_sequence_from_event(event)
        if sequence is None:
            return
        for name in EDITOR_ACTIONS.values():
            action = self._ctx.actions[name]
            if sequence in map(normalize_key_sequence, action.shortcuts()):
                action.trigger()
                return
