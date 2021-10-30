import logging

from PyQt5.QtCore import QEvent, pyqtSignal

from gridplayer.utils.misc import dict_swap_items, is_modal_open, qt_connect
from gridplayer.video import Video
from gridplayer.widgets.video_block import VideoBlock

logger = logging.getLogger(__name__)


class PlayerVideoBlocksMixin(object):
    video_count_change = pyqtSignal(int)
    playings_videos_count_change = pyqtSignal(int)

    about_to_close_video = pyqtSignal()
    closed_video = pyqtSignal()
    about_to_close_all = pyqtSignal()
    closed_all = pyqtSignal()

    hide_overlay = pyqtSignal()
    set_pause = pyqtSignal(int)
    seek_shift = pyqtSignal(int)
    seek_random = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.video_blocks = {}
        self.active_video_block = None

    def set_active_block(self, active_block):
        self.active_video_block = active_block

    def event(self, event) -> bool:
        if event.type() in {QEvent.ShortcutOverride, QEvent.NonClientAreaMouseMove}:
            self.cmd_active("show_overlay")

        return super().event(event)

    def pause_all(self):
        self.set_pause.emit(True)

    def cmd_play_pause_all(self):
        unpaused_vbs = (
            v for v in self.video_blocks.values() if not v.video_params.is_paused
        )

        if next(unpaused_vbs, None) is not None:
            self.set_pause.emit(True)
        else:
            self.set_pause.emit(False)

    def cmd_seek_shift_all(self, percent):
        self.seek_shift.emit(percent)

    def cmd_step_forward(self):
        self.pause_all()
        self.step_frame.emit(-1)

    def cmd_step_backward(self):
        self.pause_all()
        self.step_frame.emit(1)

    def cmd_active(self, command, *args):
        if self.active_video_block is None:
            return

        getattr(self.active_video_block, command)(*args)

    @property
    def is_videos(self):
        return bool(self.video_blocks)

    def reload_videos(self):
        videos = [vb.video for vb in self.video_blocks.values()]

        self.close_all()

        self.add_videos(videos)

    def add_videos(self, videos):
        for v in videos:
            self._add_video_block(v)

        self.video_count_change.emit(len(self.video_blocks))

    def _add_video_block(self, video):
        vb = VideoBlock(
            video_driver=self.managers.driver.driver,
            parent=self,
        )
        # vb.installEventFilter(self)

        qt_connect(
            (vb.exit_request, self.close_video_block),
            (vb.is_paused_change, self.playing_count_change),
            (self.set_pause, vb.set_pause),
            (self.seek_shift, vb.seek_shift_percent),
            (self.seek_random, vb.seek_random),
            (self.hide_overlay, vb.hide_overlay),
        )

        vb.set_video(video)

        self.video_blocks[vb.id] = vb

    def remove_video_blocks(self, *videoblocks):
        for vb in videoblocks:
            self._remove_video_block(vb)

        self.video_count_change.emit(len(self.video_blocks))

    def _remove_video_block(self, vb):
        # self.videogrid.takeAt(self.videogrid.indexOf(vb))

        if vb is self.active_video_block:
            self.active_video_block = None

        vb.cleanup()
        self.video_blocks.pop(vb.id)
        # vb.deleteLater()

    def is_active_param_set_to(self, param_name, param_value):
        if self.active_video_block is None:
            return False

        active_video_param = getattr(self.active_video_block.video_params, param_name)

        return active_video_param == param_value

    def close_video_block(self, _id):
        self.remove_video_blocks(self.video_blocks[_id])

        # self.update_active_block(self.get_current_cursor_pos())
        self.cmd_active("show_overlay")

    def close_all(self):
        self.remove_video_blocks(*list(self.video_blocks.values()))

    def playing_count_change(self):
        playing_videos_count = sum(
            True for v in self.video_blocks.values() if not v.video_params.is_paused
        )
        self.playings_videos_count_change.emit(playing_videos_count)
