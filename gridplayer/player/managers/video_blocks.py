from typing import List

from PyQt5.QtCore import Qt, pyqtSignal

from gridplayer.dialogs.input_dialog import QCustomSpinboxTimeInput
from gridplayer.models.video import Video
from gridplayer.params.static import SeekSyncMode, VideoAspect
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import qt_connect
from gridplayer.widgets.video_block import VideoBlock


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

    def clear(self):
        self._blocks.clear()

    def index(self, block):
        return self._blocks.index(block)

    @property
    def unpaused(self):
        return [v for v in self._blocks if not v.video_params.is_paused]

    @property
    def initialized(self):
        return [v for v in self._blocks if v.is_video_initialized]

    @property
    def videos(self) -> List[Video]:
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

    reload_all_closed = pyqtSignal()

    hide_overlay = pyqtSignal()
    set_pause = pyqtSignal(bool)

    close_all_signal = pyqtSignal()

    all_previous_video = pyqtSignal()
    all_next_video = pyqtSignal()

    all_seek_shift_percent = pyqtSignal(int)
    all_seek_shift_ms = pyqtSignal(int)
    all_seek_random = pyqtSignal()
    all_seek_percent = pyqtSignal(float)
    all_seek = pyqtSignal(int)
    all_next_frame = pyqtSignal()
    all_previous_frame = pyqtSignal()

    all_rate_increase = pyqtSignal()
    all_rate_decrease = pyqtSignal()
    all_rate_reset = pyqtSignal()

    all_scale_increase = pyqtSignal()
    all_scale_decrease = pyqtSignal()
    all_scale_reset = pyqtSignal()

    all_set_aspect = pyqtSignal(VideoAspect)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.seek_sync_mode = Settings().get("playlist/seek_sync_mode")

        self._ctx.video_blocks = VideoBlocks()

        self._live_video_blocks = 0
        self._videos_to_reload = []

    @property
    def commands(self):
        return {
            "all": self.cmd_all,
            "all_play_pause": self.cmd_all_play_pause,
            "all_seek_timecode": self.cmd_seek_timecode,
            "is_videos": lambda: bool(self._ctx.video_blocks),
            "is_any_videos_initialized": self.is_any_videos_initialized,
            "is_any_videos_seekable": self.is_any_videos_seekable,
            "is_any_videos_local_file": self.is_any_videos_local_file,
            "is_seek_sync_mode_set_to": self.is_seek_sync_mode_set_to,
            "set_seek_sync_mode": self.set_seek_sync_mode,
            "reload_all": self.reload_videos,
        }

    def cmd_all(self, command, *args):
        getattr(self, f"all_{command}").emit(*args)

    def cmd_all_play_pause(self):
        is_at_least_one_unpaused = bool(self._ctx.video_blocks.unpaused)

        if is_at_least_one_unpaused:
            self.set_pause.emit(True)
        else:
            self.set_pause.emit(False)

    def cmd_seek_timecode(self):
        time_ms = QCustomSpinboxTimeInput.get_time_ms_int(
            self.parent(), self.tr("Enter timecode")
        )

        if time_ms is None:
            return

        self.all_seek.emit(time_ms)

    def seek_sync_percent(self, percent):
        if self._ctx.seek_sync_mode == SeekSyncMode.PERCENT:
            self.all_seek_percent.emit(percent)

    def seek_sync_timecode(self, timecode):
        if self._ctx.seek_sync_mode == SeekSyncMode.TIMECODE:
            self.all_seek.emit(timecode)

    def is_seek_sync_mode_set_to(self, mode):
        return self._ctx.seek_sync_mode == mode

    def set_seek_sync_mode(self, mode):
        self._ctx.seek_sync_mode = mode

    def is_any_videos_initialized(self):
        return bool(self._ctx.video_blocks.initialized)

    def is_any_videos_seekable(self):
        return any(not vb.is_live for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_local_file(self):
        return any(vb.is_local_file for vb in self._ctx.video_blocks.initialized)

    def pause_all(self):
        self.set_pause.emit(True)

    def reload_videos(self):
        if self._videos_to_reload:
            self._log.warning("Reload: operation in progress")
            return

        self._videos_to_reload = self._ctx.video_blocks.videos

        self._log.debug("Reload: closing all")

        if self._live_video_blocks == 0:
            self.reload_all_closed.emit()
        else:
            self.close_all()

    def reload_videos_finish(self):
        self._log.debug("Reload: terminating driver")

        self.reload_all_closed.emit()

        self._log.debug("Reload: adding videos back")

        self.add_videos(self._videos_to_reload)
        self._videos_to_reload = []

    def add_videos(self, videos):
        for v in videos:
            self._add_video_block(v)

        self.video_count_changed.emit(len(self._ctx.video_blocks))

    def close_single(self, _id):
        closing_block = self._ctx.video_blocks.by_id(_id)
        self._ctx.video_blocks.remove(closing_block)

        self.video_count_changed.emit(len(self._ctx.video_blocks))

    def close_all(self):
        self.close_all_signal.emit()

        self._log.debug("Clearing video blocks array")

        self._ctx.video_blocks.clear()

        self.video_count_changed.emit(len(self._ctx.video_blocks))

    def playing_count_change(self):
        playing_videos_count = len(self._ctx.video_blocks.unpaused)
        self.playings_videos_count_changed.emit(playing_videos_count)

    def _add_video_block(self, video):
        self._live_video_blocks += 1

        vb = VideoBlock(
            video_driver=self._ctx.video_driver,
            parent=self.parent(),
        )

        vb.setAttribute(Qt.WA_DeleteOnClose)

        qt_connect(
            (vb.about_to_close, self.close_single),
            (vb.is_paused_change, self.playing_count_change),
            (vb.sync_percent, self.seek_sync_percent),
            (vb.sync_time, self.seek_sync_timecode),
            (vb.sync_paused, self.set_pause),
            (vb.destroyed, self._video_block_destroyed),
            (self.set_pause, vb.set_pause),
            (self.all_seek_shift_percent, vb.seek_shift_percent),
            (self.all_seek_shift_ms, vb.seek_shift_ms),
            (self.all_seek_random, vb.seek_random),
            (self.all_seek_percent, vb.seek_percent),
            (self.all_seek, vb.seek),
            (self.all_next_frame, vb.next_frame),
            (self.all_previous_frame, vb.previous_frame),
            (self.all_rate_increase, vb.rate_increase),
            (self.all_rate_decrease, vb.rate_decrease),
            (self.all_rate_reset, vb.rate_reset),
            (self.all_scale_increase, vb.scale_increase),
            (self.all_scale_decrease, vb.scale_decrease),
            (self.all_scale_reset, vb.scale_reset),
            (self.all_set_aspect, vb.set_aspect),
            (self.all_previous_video, vb.previous_video),
            (self.all_next_video, vb.next_video),
            (self.hide_overlay, vb.hide_overlay),
            (self.close_all_signal, vb.close_silently),
        )

        vb.set_video(video)

        self._ctx.video_blocks.append(vb)

    def _video_block_destroyed(self, _):
        self._live_video_blocks -= 1

        if self._live_video_blocks == 0:
            self._log.debug("No more live video blocks")

            if self._videos_to_reload:
                self.reload_videos_finish()
