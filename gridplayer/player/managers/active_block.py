from PyQt5.QtCore import QEvent, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.misc import is_modal_open
from gridplayer.widgets.video_block import VideoBlock


class ActiveBlockManager(ManagerBase):
    active_block_change = pyqtSignal(VideoBlock)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._context["active_block"] = None

        self._event_map = {
            QEvent.MouseMove: lambda x: self.update_active_under_mouse(),
            QEvent.MouseButtonPress: lambda x: self.update_active_under_mouse(),
            QEvent.MouseButtonRelease: lambda x: self.update_active_under_mouse(),
            QEvent.NonClientAreaMouseMove: lambda x: self.update_active_reset(),
            QEvent.NonClientAreaMouseButtonPress: lambda x: self.update_active_reset(),
            QEvent.Drop: lambda x: self.update_active_under_mouse(),
            QEvent.DragMove: lambda x: self.update_active_under_mouse(),
        }

    @property
    def commands(self):
        return {
            "active": self.cmd_active,
            "is_active_param_set_to": self.is_active_param_set_to,
        }

    def cmd_active(self, command, *args):
        if self._context["active_block"] is None:
            return

        getattr(self._context["active_block"], command)(*args)

    def is_active_param_set_to(self, param_name, param_value):
        if self._context["active_block"] is None:
            return False

        active_video_param = getattr(
            self._context["active_block"].video_params, param_name
        )

        return active_video_param == param_value

    def update_active_under_mouse(self):
        self._update_active_block(self._get_current_cursor_pos())
        self.cmd_active("show_overlay")

    def update_active_reset(self):
        self._update_active_block(None)

    def _update_active_block(self, pos):
        if is_modal_open():
            return

        old_active_block = self._context["active_block"]

        if pos is None:
            self._context["active_block"] = None

        else:
            self._context["active_block"] = self._get_hover_video_block()

            if self._context["active_block"] is not None:
                self._context["active_block"].is_active = True

        if self._context["active_block"] != old_active_block:
            if old_active_block is not None:
                old_active_block.is_active = False

            self.active_block_change.emit(self._context["active_block"])

    def _get_hover_video_block(self):
        visible_blocks_under_cursor = (
            v
            for v in self._context["video_blocks"]
            if v.isVisible() and v.is_under_cursor()
        )

        return next(visible_blocks_under_cursor, None)

    def _get_current_cursor_pos(self):
        parent = self.parent()
        return parent.mapFromGlobal(parent.cursor().pos())