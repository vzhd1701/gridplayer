from PyQt5.QtCore import QEvent, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.misc import is_modal_open
from gridplayer.widgets.video_block import VideoBlock


class ActiveBlockManager(ManagerBase):
    active_block_change = pyqtSignal(VideoBlock)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.active_block = None

    @property
    def event_map(self):
        return {
            QEvent.MouseMove: self.update_active_under_mouse,
            QEvent.MouseButtonPress: self.update_active_under_mouse,
            QEvent.MouseButtonRelease: self.update_active_under_mouse,
            QEvent.NonClientAreaMouseMove: self.update_active_reset,
            QEvent.NonClientAreaMouseButtonPress: self.update_active_reset,
            QEvent.Drop: self.update_active_under_mouse,
            QEvent.DragMove: self.update_active_under_mouse,
        }

    @property
    def commands(self):
        return {
            "active": self.cmd_active,
            "is_active_param_set_to": self.is_active_param_set_to,
        }

    def cmd_active(self, command, *args):
        if self._ctx.active_block is None:
            return

        if not self._ctx.active_block.is_video_initialized:
            return

        getattr(self._ctx.active_block, command)(*args)

    def is_active_param_set_to(self, param_name, param_value):
        if self._ctx.active_block is None:
            return False

        active_video_param = getattr(self._ctx.active_block.video_params, param_name)

        return active_video_param == param_value

    def update_active_under_mouse(self):
        self._update_active_block(self._get_current_cursor_pos())
        self.cmd_active("show_overlay")

    def update_active_reset(self):
        self._update_active_block(None)

    def _update_active_block(self, pos):
        if is_modal_open():
            return

        old_active_block = self._ctx.active_block

        if pos is None:
            self._ctx.active_block = None

        else:
            self._ctx.active_block = self._get_hover_video_block()

            if self._ctx.active_block is not None:
                self._ctx.active_block.is_active = True

        if self._ctx.active_block != old_active_block:
            if old_active_block is not None:
                old_active_block.is_active = False

            self.active_block_change.emit(self._ctx.active_block)

    def _get_hover_video_block(self):
        visible_blocks_under_cursor = (
            v for v in self._ctx.video_blocks if v.isVisible() and v.is_under_cursor()
        )

        return next(visible_blocks_under_cursor, None)

    def _get_current_cursor_pos(self):
        parent = self.parent()
        return parent.mapFromGlobal(parent.cursor().pos())
