from PyQt5.QtCore import pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings


class SingleModeManager(ManagerBase):
    mode_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_single_mode = False

        self._pre_sm_states = {}

    @property
    def commands(self):
        return {
            "next_single_video": self.next_single_video,
            "previous_single_video": self.previous_single_video,
            "toggle_single_video": self.toggle_single_video,
            "is_single_mode": lambda: self._ctx.is_single_mode,
            "is_more_than_one_video": lambda: len(self._ctx.video_blocks) > 1,
            "is_single_mode_available": self.is_single_mode_available,
        }

    def set_video_count(self, video_count):
        """Exit single mode when number of videos change"""

        if self._ctx.is_single_mode:
            self.single_mode_off()

    def is_single_mode_available(self):
        return (
            len(self._ctx.video_blocks) >= 1
            and self._ctx.commands.grid_cell_count() > 1
        )

    def toggle_single_video(self):
        if self._ctx.is_single_mode:
            self.single_mode_off()
            return

        if not self.is_single_mode_available():
            return

        self.single_mode_on()

    def next_single_video(self):
        self._switch_single_video(is_before=False)

    def previous_single_video(self):
        self._switch_single_video(is_before=True)

    def single_mode_on(self):
        if self._ctx.active_block is None:
            return

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

    def _switch_single_video(self, is_before):
        if not self._ctx.is_single_mode:
            return

        is_pause_background_videos = Settings().get("player/pause_background_videos")

        current_sv = next(v for v in self._ctx.video_blocks if v.isVisible())

        next_sv = self._find_next_single_video(current_sv, is_before)

        if next_sv is current_sv:
            return

        if is_pause_background_videos:
            self._pre_sm_states[current_sv.id] = current_sv.video_params.is_paused
            current_sv.set_pause(True)
        current_sv.hide()

        pre_sm_state = self._pre_sm_states.pop(next_sv.id, None)
        if pre_sm_state is not None:
            next_sv.set_pause(pre_sm_state)

        next_sv.show()

    def _find_next_single_video(self, current_sv, is_before):
        blocks = self._ctx.video_blocks.blocks_for_ids(
            self._ctx.commands.layout_order()
        )
        if not blocks:
            return current_sv
        idx = blocks.index(current_sv)
        if is_before:
            return blocks[idx - 1]
        return blocks[(idx + 1) % len(blocks)]
