from PyQt5.QtCore import Qt

from gridplayer.settings import Settings


# -noinspection PyUnresolvedReferences
class PlayerSingleModeMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.is_single_mode = False
        self.pre_sm_states = {}

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_single_video()

        super().mouseDoubleClickEvent(event)

    def toggle_single_video(self):
        if len(self.video_blocks) <= 1:
            return

        is_pause_background_videos = Settings().get("player/pause_background_videos")

        if self.is_single_mode:
            self._single_mode_off()
        else:
            self._single_mode_on(is_pause_background_videos)

        self.is_single_mode = not self.is_single_mode

    def next_single_video(self):
        if not self.is_single_mode:
            return

        is_pause_background_videos = Settings().get("player/pause_background_videos")

        current_sv = next(v for v in self.video_blocks.values() if v.isVisible())

        next_sv = self._next_single_video_after(current_sv)

        if is_pause_background_videos:
            self.pre_sm_states[current_sv.id] = current_sv.video_params.is_paused
            current_sv.set_pause(True)
        current_sv.hide()

        pre_sm_state = self.pre_sm_states.pop(next_sv.id, None)
        if pre_sm_state is not None:
            next_sv.set_pause(pre_sm_state)

        next_sv.show()

    def _single_mode_on(self, is_pause_background_videos):
        for vb in self.video_blocks.values():
            if vb == self.active_video_block:
                continue

            if is_pause_background_videos:
                self.pre_sm_states[vb.id] = vb.video_params.is_paused
                vb.set_pause(True)

            vb.hide()

        self.reset_grid_stretch()

    def _single_mode_off(self):
        for vb in self.video_blocks.values():
            if vb == self.active_video_block:
                continue

            pre_sm_state = self.pre_sm_states.pop(vb.id, None)
            if pre_sm_state is not None:
                vb.set_pause(pre_sm_state)

            vb.show()

        self.adjust_grid_stretch()

    def _next_single_video_after(self, current_sv):
        next_sv_idx = list(self.video_blocks).index(current_sv.id) + 1
        if next_sv_idx > len(self.video_blocks) - 1:
            next_sv_idx = 0

        return list(self.video_blocks.values())[next_sv_idx]
