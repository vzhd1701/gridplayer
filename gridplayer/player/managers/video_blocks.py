import logging

from PyQt5.QtCore import pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.misc import qt_connect
from gridplayer.widgets.video_block import VideoBlock

logger = logging.getLogger(__name__)


class VideoBlocks(object):
    def __init__(self):
        self._blocks = []

    def __iter__(self):
        return iter(self._blocks)

    def __len__(self):
        return len(self._blocks)

    def __getitem__(self, idx):
        return self._blocks[idx]

    def append(self, block):
        self._blocks.append(block)

    def remove(self, block):
        self._blocks.remove(block)

    def index(self, block):
        return self._blocks.index(block)

    @property
    def unpaused(self):
        return [v for v in self._blocks if not v.video_params.is_paused]

    @property
    def videos(self):
        return [v.video_params for v in self._blocks]

    def by_id(self, _id):
        return next((v for v in self._blocks if v.id == _id), None)

    def swap(self, block1, block2):
        idx1 = self._blocks.index(block1)
        idx2 = self._blocks.index(block2)

        old1, old2 = self._blocks[idx1], self._blocks[idx2]

        self._blocks[idx2] = old1
        self._blocks[idx1] = old2


class VideoBlocksManager(ManagerBase):
    video_count_changed = pyqtSignal(int)
    playings_videos_count_changed = pyqtSignal(int)

    hide_overlay = pyqtSignal()
    set_pause = pyqtSignal(int)
    seek_shift = pyqtSignal(int)
    seek_random = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.video_blocks = VideoBlocks()

    @property
    def commands(self):
        return {
            "play_pause_all": self.cmd_play_pause_all,
            "loop_random": lambda: self.seek_random.emit(),
            "seek_shift_all": self.cmd_seek_shift_all,
            "step_forward": self.cmd_step_forward,
            "step_backward": self.cmd_step_backward,
            "is_videos": lambda: bool(self._ctx.video_blocks),
        }

    def cmd_play_pause_all(self):
        is_at_least_one_unpaused = bool(self._ctx.video_blocks.unpaused)

        if is_at_least_one_unpaused:
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

    def pause_all(self):
        self.set_pause.emit(True)

    def reload_videos(self):
        videos = self._ctx.video_blocks.videos

        self.close_all()

        self.add_videos(videos)

    def add_videos(self, videos):
        for v in videos:
            self._add_video_block(v)

        self.video_count_changed.emit(len(self._ctx.video_blocks))

    def remove_video_blocks(self, *videoblocks):
        for vb in videoblocks:
            self._remove_video_block(vb)

        self.video_count_changed.emit(len(self._ctx.video_blocks))

    def close_video_block(self, _id):
        closing_block = self._ctx.video_blocks.by_id(_id)
        self.remove_video_blocks(closing_block)

    def close_all(self):
        self.remove_video_blocks(*self._ctx.video_blocks)

    def playing_count_change(self):
        playing_videos_count = len(self._ctx.video_blocks.unpaused)
        self.playings_videos_count_changed.emit(playing_videos_count)

    def _add_video_block(self, video):
        vb = VideoBlock(
            video_driver=self._ctx.video_driver,
            parent=self.parent(),
        )

        qt_connect(
            (vb.exit_request, self.close_video_block),
            (vb.is_paused_change, self.playing_count_change),
            (self.set_pause, vb.set_pause),
            (self.seek_shift, vb.seek_shift_percent),
            (self.seek_random, vb.seek_random),
            (self.hide_overlay, vb.hide_overlay),
        )

        vb.set_video(video)

        self._ctx.video_blocks.append(vb)

    def _remove_video_block(self, vb):
        vb.cleanup()
        self._ctx.video_blocks.remove(vb)
        vb.deleteLater()
