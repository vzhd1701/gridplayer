import logging

from PyQt5.QtCore import QEvent, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.misc import qt_connect
from gridplayer.widgets.video_block import VideoBlock

logger = logging.getLogger(__name__)


class VideoBlocksManager(ManagerBase):
    video_count_changed = pyqtSignal(int)
    playings_videos_count_changed = pyqtSignal(int)

    hide_overlay = pyqtSignal()
    set_pause = pyqtSignal(int)
    seek_shift = pyqtSignal(int)
    seek_random = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._context["video_blocks"] = []

    # def event(self, event) -> bool:
    #     if event.type() in {QEvent.ShortcutOverride}:
    #         self.cmd_active("show_overlay")
    #
    #     return super().event(event)

    @property
    def commands(self):
        return {
            "play_pause_all": self.cmd_play_pause_all,
            "loop_random": lambda: self.seek_random.emit(),
            "seek_shift_all": self.cmd_seek_shift_all,
            "step_forward": self.cmd_step_forward,
            "step_backward": self.cmd_step_backward,
            "is_videos": lambda: bool(self._context["video_blocks"]),
        }

    def cmd_play_pause_all(self):
        unpaused_vbs = (
            v for v in self._context["video_blocks"] if not v.video_params.is_paused
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

    def pause_all(self):
        self.set_pause.emit(True)

    def reload_videos(self):
        videos = [vb.video_params for vb in self._context["video_blocks"]]

        self.close_all()

        self.add_videos(videos)

    def add_videos(self, videos):
        for v in videos:
            self._add_video_block(v)

        self.video_count_changed.emit(len(self._context["video_blocks"]))

    def _add_video_block(self, video):
        driver = self._context["commands"]["state_video_driver"]()

        vb = VideoBlock(
            video_driver=driver,
            parent=self.parent(),
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

        self._context["video_blocks"].append(vb)

    def remove_video_blocks(self, *videoblocks):
        for vb in videoblocks:
            self._remove_video_block(vb)

        self.video_count_changed.emit(len(self._context["video_blocks"]))

    def _remove_video_block(self, vb):
        vb.cleanup()
        self._context["video_blocks"].remove(vb)
        vb.deleteLater()

    def close_video_block(self, _id):
        closing_block = next(v for v in self._context["video_blocks"] if v.id == _id)
        self.remove_video_blocks(closing_block)

    def close_all(self):
        self.remove_video_blocks(*self._context["video_blocks"])

    def playing_count_change(self):
        playing_videos_count = sum(
            True for v in self._context["video_blocks"] if not v.video_params.is_paused
        )
        self.playings_videos_count_changed.emit(playing_videos_count)
