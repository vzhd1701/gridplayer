from PyQt5.QtCore import QEvent, Qt, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings


class SingleModeManager(ManagerBase):
    mode_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_single_mode = False

        self._pre_sm_states = {}

    @property
    def event_map(self):
        return {
            QEvent.MouseButtonDblClick: self.mouseDoubleClickEvent,
        }

    @property
    def commands(self):
        return {"next_single_video": self.next_single_video}

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_single_video()

    def set_video_count(self, video_count):
        """Exit single mode when number of videos change"""

        self.single_mode_off()

    def toggle_single_video(self):
        if len(self._ctx.video_blocks) <= 1:
            return

        if self._ctx.is_single_mode:
            self.single_mode_off()
        else:
            self.single_mode_on()

    def next_single_video(self):
        if not self._ctx.is_single_mode:
            return

        is_pause_background_videos = Settings().get("player/pause_background_videos")

        current_sv = next(v for v in self._ctx.video_blocks if v.isVisible())

        next_sv = self._next_single_video_after(current_sv)

        if is_pause_background_videos:
            self._pre_sm_states[current_sv.id] = current_sv.video_params.is_paused
            current_sv.set_pause(True)
        current_sv.hide()

        pre_sm_state = self._pre_sm_states.pop(next_sv.id, None)
        if pre_sm_state is not None:
            next_sv.set_pause(pre_sm_state)

        next_sv.show()

    def single_mode_on(self):
        self._ctx.is_single_mode = True

        is_pause_background_videos = Settings().get("player/pause_background_videos")

        for vb in self._ctx.video_blocks:
            if vb == self._ctx.active_block:
                continue

            if is_pause_background_videos:
                self._pre_sm_states[vb.id] = vb.video_params.is_paused
                vb.set_pause(True)

            vb.hide()

        self.mode_changed.emit()

    def single_mode_off(self):
        self._ctx.is_single_mode = False

        for vb in self._ctx.video_blocks:
            if vb == self._ctx.active_block:
                continue

            pre_sm_state = self._pre_sm_states.pop(vb.id, None)
            if pre_sm_state is not None:
                vb.set_pause(pre_sm_state)

            vb.show()

        self.mode_changed.emit()

    def _next_single_video_after(self, current_sv):
        next_sv_idx = self._ctx.video_blocks.index(current_sv) + 1
        if next_sv_idx > len(self._ctx.video_blocks) - 1:
            next_sv_idx = 0

        return self._ctx.video_blocks[next_sv_idx]
