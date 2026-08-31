import contextlib

from PyQt5.QtCore import Qt, pyqtSignal

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput, QCustomSpinboxTimeInput
from gridplayer.models.video import Video
from gridplayer.params.static import (
    AudioChannelMode,
    SeekSyncMode,
    VideoAspect,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import qt_connect, translate
from gridplayer.widgets.video_block import VideoBlock


class VideoBlocks:
    """Widget registry. Layout order lives on FlowLayout / GridLayout."""

    def __init__(self):
        self._by_instance: dict[str, VideoBlock] = {}
        self._by_video_id: dict[str, VideoBlock] = {}

    def __iter__(self):
        return iter(self._by_instance.values())

    def __len__(self):
        return len(self._by_instance)

    def append(self, block):
        self._by_instance[block.id] = block
        if block.video_params is not None:
            self._by_video_id[block.video_id] = block

    def remove(self, block):
        self._by_instance.pop(block.id, None)
        if block.video_params is not None:
            vid = block.video_id
            if self._by_video_id.get(vid) is block:
                del self._by_video_id[vid]

    def clear(self):
        self._by_instance.clear()
        self._by_video_id.clear()

    def reindex(self, block):
        """Refresh video_id key after set_video."""
        stale = [vid for vid, vb in self._by_video_id.items() if vb is block]
        for vid in stale:
            del self._by_video_id[vid]
        if block.video_params is not None:
            self._by_video_id[block.video_id] = block

    @property
    def unpaused(self):
        return [v for v in self._by_instance.values() if not v.video_params.is_paused]

    @property
    def initialized(self):
        return [v for v in self._by_instance.values() if v.is_video_initialized]

    @property
    def is_all_initialized(self):
        return all(v.is_video_initialized for v in self._by_instance.values())

    @property
    def videos(self) -> list[Video]:
        return [v.video_params for v in self._by_instance.values()]

    @property
    def video_ids(self) -> list[str]:
        return [vb.video_id for vb in self]

    def by_id(self, _id) -> VideoBlock | None:
        return self._by_instance.get(_id)

    def by_video_id(self, _id) -> VideoBlock | None:
        return self._by_video_id.get(str(_id))

    def blocks_for_ids(self, video_ids: list[str]) -> list[VideoBlock]:
        return [
            block
            for video_id in video_ids
            if (block := self.by_video_id(video_id)) is not None
        ]


class VideoBlocksManager(ManagerBase):
    video_count_changed = pyqtSignal(int)
    playings_videos_count_changed = pyqtSignal(int)

    reload_all_closed = pyqtSignal()

    hide_overlay = pyqtSignal()
    set_drag_ui = pyqtSignal(bool)
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

    all_toggle_loop_random = pyqtSignal()
    all_set_loop_start = pyqtSignal()
    all_set_loop_end = pyqtSignal()
    all_reset_loop = pyqtSignal()
    all_set_repeat_mode = pyqtSignal(VideoRepeat)

    all_rate_increase = pyqtSignal()
    all_rate_decrease = pyqtSignal()
    all_rate_reset = pyqtSignal()

    all_scale_increase = pyqtSignal()
    all_scale_decrease = pyqtSignal()
    all_scale_reset = pyqtSignal()

    all_crop = pyqtSignal(int, int, int, int)
    all_crop_reset = pyqtSignal()

    all_set_aspect = pyqtSignal(VideoAspect)
    all_set_transform = pyqtSignal(VideoTransform)
    all_set_auto_reload_timer = pyqtSignal(int)
    all_set_audio_channel_mode = pyqtSignal(AudioChannelMode)

    all_volume_increase = pyqtSignal()
    all_volume_decrease = pyqtSignal()
    all_set_muted = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.seek_sync_mode = Settings().get("playlist/seek_sync_mode")
        self._ctx.is_disable_mouse_click_events = Settings().get(
            "playlist/disable_mouse_click_events"
        )
        self._ctx.is_disable_mouse_wheel_events = Settings().get(
            "playlist/disable_mouse_wheel_events"
        )
        self._ctx.is_disable_overlay = Settings().get("playlist/disable_overlay")
        self._ctx.is_drag_ui = False

        self._ctx.video_blocks = VideoBlocks()

        self._live_video_blocks = 0
        self._videos_to_reload = []
        self._count_batch_depth = 0

    @property
    def commands(self):
        return {
            "all": self.cmd_all,
            "all_play_pause": self.cmd_all_play_pause,
            "all_play": self.cmd_all_play,
            "all_pause": self.cmd_all_pause,
            "all_seek_timecode": self.cmd_seek_timecode,
            "all_set_auto_reload_timer": self.cmd_set_auto_reload_timer,
            "is_videos": lambda: bool(self._ctx.video_blocks),
            "is_any_videos_initialized": self.is_any_videos_initialized,
            "is_any_videos_seekable": self.is_any_videos_seekable,
            "is_any_videos_local_file": self.is_any_videos_local_file,
            "is_any_videos_live": self.is_any_videos_live,
            "is_any_videos_have_audio": self.is_any_videos_have_audio,
            "is_any_videos_have_video": self.is_any_videos_have_video,
            "is_seek_sync_mode_set_to": self.is_seek_sync_mode_set_to,
            "set_seek_sync_mode": self.set_seek_sync_mode,
            "reload_all": self.reload_videos,
            "is_disable_mouse_click_events": lambda: (
                self._ctx.is_disable_mouse_click_events
            ),
            "set_disable_mouse_click_events": self.set_disable_mouse_click_events,
            "toggle_disable_mouse_click_events": self.toggle_disable_mouse_click_events,
            "is_disable_mouse_wheel_events": lambda: (
                self._ctx.is_disable_mouse_wheel_events
            ),
            "set_disable_mouse_wheel_events": self.set_disable_mouse_wheel_events,
            "toggle_disable_mouse_wheel_events": self.toggle_disable_mouse_wheel_events,
            "is_disable_overlay": lambda: self._ctx.is_disable_overlay,
            "set_disable_overlay": self.set_disable_overlay,
            "toggle_disable_overlay": self.toggle_disable_overlay,
            "add_video_blocks": self.add_videos,
            "remove_video_blocks": self.remove_videos,
            "video_count_batch": self.batch,
        }

    def cmd_all(self, command, *args):
        getattr(self, f"all_{command}").emit(*args)

    def cmd_all_play_pause(self):
        is_at_least_one_unpaused = bool(self._ctx.video_blocks.unpaused)

        if is_at_least_one_unpaused:
            self.set_pause.emit(True)
        else:
            self.set_pause.emit(False)

    def cmd_all_play(self):
        self.set_pause.emit(False)

    def cmd_all_pause(self):
        self.set_pause.emit(True)

    def cmd_seek_timecode(self):
        time_ms = QCustomSpinboxTimeInput.get_time_ms_int(
            self.parent(),
            translate("Dialog - Enter timecode", "Enter timecode", "Header"),
        )

        if time_ms is None:
            return

        self.all_seek.emit(time_ms)

    def cmd_set_auto_reload_timer(self):
        time_minutes = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate(
                "Dialog - Set auto reload timer", "Set auto reload timer", "Header"
            ),
            special_text=translate("Auto Reload Timer", "Disabled"),
            _min=0,
            _max=1000,
        )

        self.all_set_auto_reload_timer.emit(time_minutes)

    def set_disable_mouse_click_events(self, is_disabled):
        self._ctx.is_disable_mouse_click_events = is_disabled

    def toggle_disable_mouse_click_events(self):
        self._ctx.is_disable_mouse_click_events = (
            not self._ctx.is_disable_mouse_click_events
        )

    def set_disable_mouse_wheel_events(self, is_disabled):
        self._ctx.is_disable_mouse_wheel_events = is_disabled

    def toggle_disable_mouse_wheel_events(self):
        self._ctx.is_disable_mouse_wheel_events = (
            not self._ctx.is_disable_mouse_wheel_events
        )

    def set_disable_overlay(self, is_disabled):
        self._ctx.is_disable_overlay = is_disabled
        if is_disabled:
            self.hide_overlay.emit()

    def toggle_disable_overlay(self):
        self.set_disable_overlay(not self._ctx.is_disable_overlay)

    def cmd_set_drag_ui(self, is_drag_ui: bool):
        if self._ctx.is_drag_ui == is_drag_ui:
            return
        self._ctx.is_drag_ui = is_drag_ui
        self.set_drag_ui.emit(is_drag_ui)

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

    def is_any_videos_live(self):
        return any(vb.is_live for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_have_audio(self):
        return any(vb.audio_tracks for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_have_video(self):
        return any(vb.video_tracks for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_local_file(self):
        return any(vb.is_local_file for vb in self._ctx.video_blocks.initialized)

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

    @contextlib.contextmanager
    def batch(self):
        self._count_batch_depth += 1
        try:
            yield
        finally:
            self._count_batch_depth -= 1
            if self._count_batch_depth == 0:
                self._emit_video_count()

    def _in_count_batch(self):
        return self._count_batch_depth > 0

    def _emit_video_count(self):
        self.video_count_changed.emit(len(self._ctx.video_blocks))

    def add_videos(self, videos):
        videos = list(videos)
        added = [self._add_video_block(v) for v in videos]
        if not self._in_count_batch():
            self._emit_video_count()
        return added

    def remove_videos(self, video_ids):
        leftover_set = set(video_ids)
        if not leftover_set:
            return
        for vb in list(self._ctx.video_blocks):
            if vb.video_id in leftover_set:
                self._ctx.video_blocks.remove(vb)
                vb.close_silently()
        if not self._in_count_batch():
            self._emit_video_count()

    def close_single(self, _id):
        closing_block = self._ctx.video_blocks.by_id(_id)
        self._ctx.video_blocks.remove(closing_block)

        if not self._in_count_batch():
            self._emit_video_count()

    def close_all(self):
        self.close_all_signal.emit()

        self._log.debug("Clearing video blocks array")

        self._ctx.video_blocks.clear()

        if not self._in_count_batch():
            self._emit_video_count()

    def playing_count_change(self):
        playing_videos_count = len(self._ctx.video_blocks.unpaused)
        self.playings_videos_count_changed.emit(playing_videos_count)

    def _add_video_block(self, video):
        self._live_video_blocks += 1

        vb = VideoBlock(
            video_driver=self._ctx.video_driver,
            context=self._ctx,
            parent=self.parent(),
        )

        vb.setAttribute(Qt.WA_DeleteOnClose)

        qt_connect(
            (vb.about_to_close, self.close_single),
            (vb.is_paused_change, self.playing_count_change),
            (vb.sync_percent, self.seek_sync_percent),
            (vb.sync_time, self.seek_sync_timecode),
            (vb.sync_percent_single, self.all_seek_percent),
            (vb.sync_time_single, self.all_seek),
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
            (self.all_toggle_loop_random, vb.toggle_loop_random),
            (self.all_set_loop_start, vb.set_loop_start),
            (self.all_set_loop_end, vb.set_loop_end),
            (self.all_reset_loop, vb.reset_loop),
            (self.all_set_repeat_mode, vb.set_repeat_mode),
            (self.all_rate_increase, vb.rate_increase),
            (self.all_rate_decrease, vb.rate_decrease),
            (self.all_rate_reset, vb.rate_reset),
            (self.all_scale_increase, vb.scale_increase),
            (self.all_scale_decrease, vb.scale_decrease),
            (self.all_scale_reset, vb.scale_reset),
            (self.all_crop, vb.crop),
            (self.all_crop_reset, vb.crop_reset),
            (self.all_set_aspect, vb.set_aspect),
            (self.all_set_transform, vb.set_transform),
            (self.all_set_auto_reload_timer, vb.set_auto_reload_timer),
            (self.all_set_audio_channel_mode, vb.set_audio_channel_mode),
            (self.all_volume_increase, vb.volume_increase),
            (self.all_volume_decrease, vb.volume_decrease),
            (self.all_set_muted, vb.set_muted),
            (self.all_previous_video, vb.previous_video),
            (self.all_next_video, vb.next_video),
            (self.hide_overlay, vb.hide_overlay),
            (self.set_drag_ui, vb.set_drag_ui),
            (self.close_all_signal, vb.close_silently),
        )

        vb.set_video(video)

        self._ctx.video_blocks.append(vb)

        return vb

    def _video_block_destroyed(self, _):
        self._live_video_blocks -= 1

        if self._live_video_blocks == 0:
            self._log.debug("No more live video blocks")

            if self._videos_to_reload:
                self.reload_videos_finish()
