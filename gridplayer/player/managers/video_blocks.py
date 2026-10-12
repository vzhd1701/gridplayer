import contextlib
from functools import partial

from PyQt5.QtCore import Qt, pyqtSignal

from gridplayer.dialogs.audio_delay import SetAudioDelayDialog
from gridplayer.dialogs.input_dialog import QCustomSpinboxInput, QCustomSpinboxTimeInput
from gridplayer.dialogs.subtitle_delay import SetSubtitleDelayDialog
from gridplayer.models.video import Video
from gridplayer.params.static import (
    MAX_LIST_FAIL_WAIT_SEC,
    AudioChannelMode,
    ListEndAction,
    ListFailAction,
    SeekSyncMode,
    VideoAnchor,
    VideoAspect,
    VideoEndAction,
    VideoTransform,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.qt import MILLISECONDS, qt_connect, translate
from gridplayer.utils.step_sizes import seek_step_label, seek_step_ms
from gridplayer.widgets.video_block import SyncedView, VideoBlock

# what [ALL] does to the views, which leaves the one synced to out of date
_VIEW_COMMANDS = frozenset(
    {
        "scale_increase",
        "scale_decrease",
        "scale_reset",
        "set_anchor",
        "shift_by",
        "shift_reset",
    }
)


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


def _start_cleanup(video_blocks) -> None:
    """Start releasing every player before waiting on any of them.

    Closing a block waits for its player to let go of the video output, which
    takes a noticeable moment in hardware mode. Done block by block that wait
    is serial, and closing a full grid reads as the videos going dark one
    after another. Starting them all first makes the waits overlap.
    """
    for video_block in list(video_blocks):
        video_block.cleanup_start()


class VideoBlocksManager(ManagerBase):
    video_count_changed = pyqtSignal(int)
    playings_videos_count_changed = pyqtSignal(int)

    reload_all_closed = pyqtSignal()

    hide_overlay = pyqtSignal()
    show_overlay = pyqtSignal()
    set_drag_ui = pyqtSignal(bool)
    set_pause = pyqtSignal(bool)
    all_stop_playback = pyqtSignal()

    close_all_signal = pyqtSignal()

    all_previous_video = pyqtSignal()
    all_next_video = pyqtSignal()
    all_shuffle_video = pyqtSignal()

    all_seek_shift_percent = pyqtSignal(int)
    all_seek_shift_ms = pyqtSignal(MILLISECONDS)
    all_seek_random = pyqtSignal()
    all_seek_percent = pyqtSignal(float)
    all_seek = pyqtSignal(MILLISECONDS)
    all_next_frame = pyqtSignal()
    all_previous_frame = pyqtSignal()
    all_next_chapter = pyqtSignal()
    all_previous_chapter = pyqtSignal()
    all_next_bookmark = pyqtSignal()
    all_previous_bookmark = pyqtSignal()

    all_set_loop_random = pyqtSignal(bool)
    all_set_loop_start = pyqtSignal()
    all_set_loop_end = pyqtSignal()
    all_loop_chapter = pyqtSignal()
    all_reset_loop = pyqtSignal()
    all_set_end_action = pyqtSignal(VideoEndAction)
    all_set_dir_recursive = pyqtSignal(bool)
    all_set_list_end_action = pyqtSignal(ListEndAction)
    all_set_list_fail_action = pyqtSignal(ListFailAction)
    all_set_list_fail_wait = pyqtSignal(int)

    all_rate_increase = pyqtSignal()
    all_rate_decrease = pyqtSignal()
    all_rate_reset = pyqtSignal()

    all_scale_increase = pyqtSignal()
    all_scale_decrease = pyqtSignal()
    all_scale_reset = pyqtSignal()
    all_set_zoom_to_cursor = pyqtSignal(bool)

    all_crop = pyqtSignal(int, int, int, int)
    all_crop_reset = pyqtSignal()

    all_set_anchor = pyqtSignal(VideoAnchor)
    all_shift_by = pyqtSignal(int, int)
    all_shift_reset = pyqtSignal()
    all_set_shift_past_edges = pyqtSignal(bool)

    all_set_aspect = pyqtSignal(VideoAspect)
    all_set_transform = pyqtSignal(VideoTransform)
    all_take_screenshot = pyqtSignal(bool)
    all_set_auto_reload_timer = pyqtSignal(int)
    all_set_audio_channel_mode = pyqtSignal(AudioChannelMode)

    all_set_audio_delay = pyqtSignal(int)
    all_audio_delay_increase = pyqtSignal()
    all_audio_delay_decrease = pyqtSignal()
    all_audio_delay_reset = pyqtSignal()

    all_set_subtitle_delay = pyqtSignal(int)
    all_subtitle_delay_increase = pyqtSignal()
    all_subtitle_delay_decrease = pyqtSignal()
    all_subtitle_delay_reset = pyqtSignal()

    all_volume_increase = pyqtSignal()
    all_volume_decrease = pyqtSignal()
    all_set_muted = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.seek_sync_mode = Settings().get("playlist/seek_sync_mode")
        self._ctx.is_view_sync = Settings().get("playlist/view_sync")
        self._ctx.is_pause_sync = Settings().get("playlist/pause_sync")
        self._ctx.is_rate_sync = Settings().get("playlist/rate_sync")
        # the view the videos were last synced to, for one that loads after
        # to show as well; None with their views not synced
        self._ctx.synced_view = None
        self._view_leader_id: str | None = None
        self._ctx.is_disable_mouse_click_events = Settings().get(
            "playlist/disable_mouse_click_events"
        )
        self._ctx.is_disable_mouse_wheel_events = Settings().get(
            "playlist/disable_mouse_wheel_events"
        )
        self._ctx.is_disable_overlay = Settings().get("playlist/disable_overlay")
        self._ctx.is_show_overlay_border = Settings().get(
            "playlist/show_overlay_border"
        )
        self._ctx.is_overlay_hide_on_timeout = Settings().get(
            "playlist/overlay_hide_on_timeout"
        )
        self._ctx.overlay_timeout = Settings().get("playlist/overlay_timeout")
        self._ctx.is_drag_ui = False

        self._ctx.video_blocks = VideoBlocks()

        # the picture of every video switched off, the player in the tray
        self._ctx.is_video_decoding_stopped = False

        self._count_batch_depth = 0

    @property
    def commands(self):
        return {
            "all": self.cmd_all,
            "all_play_pause": self.cmd_all_play_pause,
            "all_play": self.cmd_all_play,
            "all_pause": self.cmd_all_pause,
            "set_video_decoding_stopped": self.set_video_decoding_stopped,
            "all_seek_timecode": self.cmd_seek_timecode,
            "all_seek_step": self.cmd_seek_step,
            "seek_step_label": seek_step_label,
            "all_set_auto_reload_timer": self.cmd_set_auto_reload_timer,
            "all_set_audio_delay": self.cmd_set_audio_delay,
            "all_set_list_fail_wait": self.cmd_set_list_fail_wait,
            "all_set_subtitle_delay": self.cmd_set_subtitle_delay,
            "is_videos": lambda: bool(self._ctx.video_blocks),
            "is_any_videos_initialized": self.is_any_videos_initialized,
            "is_any_videos_playable": self.is_any_videos_playable,
            "is_any_videos_stoppable": self.is_any_videos_stoppable,
            "is_any_videos_playable_not_live": self.is_any_videos_playable_not_live,
            "is_any_videos_seekable": self.is_any_videos_seekable,
            "is_any_videos_local_file": self.is_any_videos_local_file,
            "is_any_videos_navigable": self.is_any_videos_navigable,
            "is_any_videos_live": self.is_any_videos_live,
            "is_any_videos_have_audio": self.is_any_videos_have_audio,
            "is_any_videos_have_subtitles": self.is_any_videos_have_subtitles,
            "is_any_videos_have_video": self.is_any_videos_have_video,
            "is_any_videos_have_chapters": self.is_any_videos_have_chapters,
            "is_any_videos_have_bookmarks": self.is_any_videos_have_bookmarks,
            "is_all_videos_param_set_to": self.is_all_videos_param_set_to,
            "is_seek_sync_mode_set_to": self.is_seek_sync_mode_set_to,
            "set_seek_sync_mode": self.set_seek_sync_mode,
            "is_view_sync": lambda: self._ctx.is_view_sync,
            "set_view_sync": self.set_view_sync,
            "toggle_view_sync": self.toggle_view_sync,
            "is_pause_sync": lambda: self._ctx.is_pause_sync,
            "set_pause_sync": self.set_pause_sync,
            "toggle_pause_sync": self.toggle_pause_sync,
            "is_rate_sync": lambda: self._ctx.is_rate_sync,
            "set_rate_sync": self.set_rate_sync,
            "toggle_rate_sync": self.toggle_rate_sync,
            "forget_synced_view": self.forget_synced_view,
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
            "is_show_overlay_border": lambda: self._ctx.is_show_overlay_border,
            "set_show_overlay_border": self.set_show_overlay_border,
            "toggle_show_overlay_border": self.toggle_show_overlay_border,
            "is_overlay_hide_on_timeout": lambda: self._ctx.is_overlay_hide_on_timeout,
            "set_overlay_hide_on_timeout": self.set_overlay_hide_on_timeout,
            "toggle_overlay_hide_on_timeout": self.toggle_overlay_hide_on_timeout,
            "set_overlay_timeout": self.set_overlay_timeout,
            "add_video_blocks": self.add_videos,
            "remove_video_blocks": self.remove_videos,
            "video_count_batch": self.batch,
        }

    def cmd_all(self, command, *args):
        getattr(self, f"all_{command}").emit(*args)

        if command in _VIEW_COMMANDS:
            self._refresh_synced_view()

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

    def set_video_decoding_stopped(self, is_stopped: bool) -> None:
        """The pictures off while the player is in the tray, and back on."""

        self._ctx.is_video_decoding_stopped = is_stopped

        for vb in self._ctx.video_blocks:
            vb.set_video_decoding_stopped(is_stopped)

    def cmd_seek_timecode(self):
        time_ms = QCustomSpinboxTimeInput.get_time_ms_int(
            self.parent(),
            translate("Dialog - Enter timecode", "Enter timecode", "Header"),
        )

        if time_ms is None:
            return

        self.all_seek.emit(time_ms)

    def cmd_seek_step(self, slot, direction):
        """Every video by one of the playlist's seek steps; see
        VideoBlock.seek_step."""

        self.all_seek_shift_ms.emit(direction * seek_step_ms(slot))

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

    def cmd_set_audio_delay(self):
        # nothing to hear it against while it is being set, so this one is
        # typed rather than found by ear the way a single video's is
        delay_ms = SetAudioDelayDialog.get_delay_ms(parent=self.parent())

        if delay_ms is None:
            return

        self.all_set_audio_delay.emit(delay_ms)

    def cmd_set_list_fail_wait(self):
        wait_sec = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate("When Video Fails", "Play next after (sec)"),
            special_text=translate("When Video Fails", "At once"),
            initial_value=PlaylistSettings().get("video_defaults/list_fail_wait"),
            _min=0,
            _max=MAX_LIST_FAIL_WAIT_SEC,
            cancel_value=None,
        )

        if wait_sec is None:
            return

        self.all_set_list_fail_wait.emit(wait_sec)

    def cmd_set_subtitle_delay(self):
        # nothing to see it against while it is being set, so this one is
        # typed rather than found by eye the way a single video's is
        delay_ms = SetSubtitleDelayDialog.get_delay_ms(parent=self.parent())

        if delay_ms is None:
            return

        self.all_set_subtitle_delay.emit(delay_ms)

    def set_disable_mouse_click_events(self, is_disabled):
        self._ctx.is_disable_mouse_click_events = is_disabled

    def toggle_disable_mouse_click_events(self):
        self._ctx.is_disable_mouse_click_events = (
            not self._ctx.is_disable_mouse_click_events
        )
        PlaylistSettings().set(
            "playlist/disable_mouse_click_events",
            self._ctx.is_disable_mouse_click_events,
        )

    def set_disable_mouse_wheel_events(self, is_disabled):
        self._ctx.is_disable_mouse_wheel_events = is_disabled

    def toggle_disable_mouse_wheel_events(self):
        self._ctx.is_disable_mouse_wheel_events = (
            not self._ctx.is_disable_mouse_wheel_events
        )
        PlaylistSettings().set(
            "playlist/disable_mouse_wheel_events",
            self._ctx.is_disable_mouse_wheel_events,
        )

    def set_disable_overlay(self, is_disabled):
        self._ctx.is_disable_overlay = is_disabled
        if is_disabled:
            self.hide_overlay.emit()
            return

        if not self._ctx.is_overlay_hide_on_timeout:
            self.show_overlay.emit()
            return

        # up as long as the List window is open on it, the others once the
        # mouse is over them
        for vb in self._ctx.video_blocks:
            if vb.is_list_window_shown:
                vb.show_overlay()

    def toggle_disable_overlay(self):
        value = not self._ctx.is_disable_overlay
        PlaylistSettings().set("playlist/disable_overlay", value)
        self.set_disable_overlay(value)

    def set_show_overlay_border(self, is_show):
        self._ctx.is_show_overlay_border = is_show
        for vb in self._ctx.video_blocks:
            vb.refresh_overlay_border()

    def toggle_show_overlay_border(self):
        value = not self._ctx.is_show_overlay_border
        PlaylistSettings().set("playlist/show_overlay_border", value)
        self.set_show_overlay_border(value)

    def set_overlay_hide_on_timeout(self, is_hide):
        self._ctx.is_overlay_hide_on_timeout = is_hide
        if is_hide:
            self.hide_overlay.emit()
            return
        self.show_overlay.emit()

    def toggle_overlay_hide_on_timeout(self):
        value = not self._ctx.is_overlay_hide_on_timeout
        PlaylistSettings().set("playlist/overlay_hide_on_timeout", value)
        self.set_overlay_hide_on_timeout(value)

    def set_overlay_timeout(self, timeout):
        self._ctx.overlay_timeout = timeout
        if not self._ctx.is_overlay_hide_on_timeout:
            return
        self.show_overlay.emit()

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
        PlaylistSettings().set("playlist/seek_sync_mode", mode)
        self._ctx.seek_sync_mode = mode

    def set_view_sync(self, is_sync: bool):
        """Have the others show the part of their pictures one is zoomed or
        moved to, or not. From the next zoom or move on: switched on, the
        videos are left as they are until then."""

        if is_sync == self._ctx.is_view_sync:
            return

        self._ctx.is_view_sync = is_sync
        self.forget_synced_view()

    def toggle_view_sync(self):
        value = not self._ctx.is_view_sync
        PlaylistSettings().set("playlist/view_sync", value)
        self.set_view_sync(value)

    def set_pause_sync(self, is_sync: bool):
        self._ctx.is_pause_sync = is_sync

    def toggle_pause_sync(self):
        value = not self._ctx.is_pause_sync
        PlaylistSettings().set("playlist/pause_sync", value)
        self.set_pause_sync(value)

    def set_rate_sync(self, is_sync: bool):
        self._ctx.is_rate_sync = is_sync

    def toggle_rate_sync(self):
        value = not self._ctx.is_rate_sync
        PlaylistSettings().set("playlist/rate_sync", value)
        self.set_rate_sync(value)

    def forget_synced_view(self):
        """Let a video that loads from now on show its own view, as it has
        it, until the next zoom or move is synced. Once a snapshot's views
        are put in place, say."""

        self._ctx.synced_view = None
        self._view_leader_id = None

    def sync_view(self, leader: VideoBlock, synced: SyncedView):
        """The others to show the part of their pictures the leader does,
        zoomed or moved by the viewer, where their views are synced."""

        if not self._ctx.is_view_sync:
            return

        self._ctx.synced_view = synced
        self._view_leader_id = leader.id

        self._follow_view(leader, synced)

    def sync_view_single(self, leader: VideoBlock, synced: SyncedView):
        """The others to show the part of their pictures the leader does,
        this once, synced or not."""

        if self._ctx.is_view_sync:
            self.sync_view(leader, synced)
            return

        self._follow_view(leader, synced)

    def _follow_view(self, leader: VideoBlock, synced: SyncedView):
        for vb in self._ctx.video_blocks:
            if vb is not leader:
                vb.follow_view(synced)

    def _refresh_synced_view(self):
        """The view to sync to as the one it was taken from now has it, all
        of them zoomed or moved alike: else one that loads after would go
        back to the view before."""

        if self._ctx.synced_view is None:
            return

        leader = self._ctx.video_blocks.by_id(self._view_leader_id)
        synced = leader.synced_view() if leader is not None else None

        if synced is not None:
            self._ctx.synced_view = synced

    def sync_pause(self, leader: VideoBlock, is_paused: bool):
        """The others to play or pause as the leader was by the viewer,
        where that is synced.

        Not those single mode keeps paused out of sight: they stay paused,
        to take up where they were once it is left.
        """

        if not self._ctx.is_pause_sync:
            return

        is_kept_paused = getattr(self._ctx, "is_single_mode", False) and getattr(
            self._ctx, "is_pause_background_videos", False
        )

        for vb in self._ctx.video_blocks:
            if vb is leader or (is_kept_paused and vb.isHidden()):
                continue

            vb.set_pause(is_paused)

    def sync_frame_step_pause(self, is_paused: bool):
        """All paused for a step to another frame, where the others follow:
        their play and pause synced, or the seek that comes with the step."""

        if self._ctx.is_pause_sync or self._ctx.seek_sync_mode != SeekSyncMode.DISABLED:
            self.set_pause.emit(is_paused)

    def sync_rate(self, leader: VideoBlock, rate: float):
        """The others to play at the leader's speed, where that is synced."""

        if not self._ctx.is_rate_sync:
            return

        for vb in self._ctx.video_blocks:
            if vb is not leader:
                vb.follow_rate(rate)

    def apply_subtitle_encoding(self, encoding: str):
        """Give the videos already open a subtitle encoding that has changed.

        What a subtitle file is read as is settled when the input opens, so
        a video that is already playing has to be opened again to take a new
        one. Handing it a video that differs is enough -- set_video reopens
        on its own account once it does.
        """

        for vb in self._ctx.video_blocks:
            vb.set_subtitle_encoding(encoding)

    def apply_sponsorblock_settings(self):
        """Mark and skip in the videos already open as the settings now say.

        Switched on, a video looks itself up; switched off, it drops what it
        marked. What was found is kept either way.
        """

        for vb in self._ctx.video_blocks:
            vb.apply_sponsorblock_settings()

    def is_any_videos_initialized(self):
        return bool(self._ctx.video_blocks.initialized)

    def is_any_videos_playable(self):
        return any(vb.is_playable for vb in self._ctx.video_blocks)

    def is_any_videos_stoppable(self):
        return any(vb.is_stoppable for vb in self._ctx.video_blocks)

    def is_any_videos_playable_not_live(self):
        return any(vb.is_playable and not vb.is_live for vb in self._ctx.video_blocks)

    def is_any_videos_seekable(self):
        return any(not vb.is_live for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_live(self):
        return any(vb.is_live for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_have_audio(self):
        return any(vb.audio_tracks for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_have_video(self):
        return any(vb.video_tracks for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_have_subtitles(self):
        return any(vb.has_subtitles for vb in self._ctx.video_blocks.initialized)

    def is_any_videos_have_chapters(self):
        # a live stream never has any; see VideoBlock._update_chapters
        return any(vb.chapters for vb in self._ctx.video_blocks.initialized)

    def is_all_videos_param_set_to(self, param_name, param_value):
        """Whether every video has it so, which ticks the choice for all.

        Every one, stopped and loading too: a choice for all is made for
        them as well. Neither choice is ticked while they differ.
        """

        params = [
            vb.video_params
            for vb in self._ctx.video_blocks
            if vb.video_params is not None
        ]

        return bool(params) and all(
            getattr(p, param_name) == param_value for p in params
        )

    def is_any_videos_have_bookmarks(self):
        return any(
            vb.bookmarks and not vb.is_live for vb in self._ctx.video_blocks.initialized
        )

    def is_any_videos_local_file(self):
        return any(vb.is_local_file and vb.is_playable for vb in self._ctx.video_blocks)

    def is_any_videos_navigable(self):
        return any(
            vb.media_list is not None or (vb.is_local_file and vb.is_playable)
            for vb in self._ctx.video_blocks
        )

    def reload_videos(self):
        """Open every video again, in players started afresh.

        The cells stay on screen while their players let go, each saying it
        loads again, and new ones take their places once the players are
        started again. Closed first, the grid was shown empty, its empty cell
        and all, until the new ones came.
        """
        video_blocks = list(self._ctx.video_blocks)
        videos = self._ctx.video_blocks.videos

        self._log.debug("Reload: letting the players go")

        # said by all of them before any lets go: a hardware video's cell,
        # once its player has, shows what was there before its picture came
        for video_block in video_blocks:
            video_block.show_reloading()

        _start_cleanup(video_blocks)

        for video_block in video_blocks:
            video_block.release_player()

        self._log.debug("Reload: terminating driver")

        self.reload_all_closed.emit()

        if not video_blocks:
            return

        self._log.debug("Reload: adding videos back")

        # the new ones laid out in their places and shown, the old ones gone,
        # all before the window is painted again
        with self.batch():
            self._take_off_screen(video_blocks)
            self.forget_synced_view()

            # before the new ones come: closing one stops its list being read
            # for its video, theirs too
            for video_block in video_blocks:
                video_block.close_silently()

            self.add_videos(videos)

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
        removed = [vb for vb in self._ctx.video_blocks if vb.video_id in leftover_set]

        self._take_off_screen(removed)

        _start_cleanup(removed)
        for vb in removed:
            vb.close_silently()

    def close_single(self, _id):
        closing_block = self._ctx.video_blocks.by_id(_id)
        self._ctx.video_blocks.remove(closing_block)

        if not self._in_count_batch():
            self._emit_video_count()

    def close_all(self):
        """Close every video, off screen all at once before any wait.

        The waits for the players overlap (see _start_cleanup), but the
        window is not painted while they run, and each block was hidden only
        as it closed: hardware videos still on show played on, each going
        black the moment its player let go, in whatever order the players
        did, and the grid's empty cell came up only once the last wait was
        over, the window blank until then. So every block is hidden, and the
        grid laid out without them, and that painted, before the first wait.
        """
        video_blocks = list(self._ctx.video_blocks)

        self._log.debug("Clearing video blocks array")

        self.forget_synced_view()
        self._take_off_screen(video_blocks)

        _start_cleanup(video_blocks)

        self.close_all_signal.emit()

    def _take_off_screen(self, video_blocks):
        """Hidden and out of the grid, and the window painted without them,
        before any of their players is waited on: it is not painted while
        they are, and a hardware video's cell, once its player lets go,
        shows what was painted there before its picture came.

        In a batch, laid out and painted once it is over, along with what
        else it brings.
        """

        is_any_shown = any(vb.isVisible() for vb in video_blocks)

        for vb in video_blocks:
            vb.hide()
            self._ctx.video_blocks.remove(vb)

        if self._in_count_batch():
            return

        self._emit_video_count()

        if is_any_shown:
            self.parent().repaint()

    def playing_count_change(self):
        playing_videos_count = len(self._ctx.video_blocks.unpaused)
        self.playings_videos_count_changed.emit(playing_videos_count)

    def _add_video_block(self, video):
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
            (vb.sync_paused, self.sync_frame_step_pause),
            (vb.sync_pause, partial(self.sync_pause, vb)),
            (vb.sync_view, partial(self.sync_view, vb)),
            (vb.sync_view_single, partial(self.sync_view_single, vb)),
            (vb.sync_rate, partial(self.sync_rate, vb)),
            (self.set_pause, vb.set_pause),
            (self.all_stop_playback, vb.stop_playback),
            (self.all_seek_shift_percent, vb.seek_shift_percent),
            (self.all_seek_shift_ms, vb.seek_shift_ms),
            (self.all_seek_random, vb.seek_random),
            (self.all_seek_percent, vb.seek_percent),
            (self.all_seek, vb.seek),
            (self.all_next_frame, vb.next_frame),
            (self.all_previous_frame, vb.previous_frame),
            (self.all_next_chapter, vb.next_chapter),
            (self.all_previous_chapter, vb.previous_chapter),
            (self.all_next_bookmark, vb.next_bookmark),
            (self.all_previous_bookmark, vb.previous_bookmark),
            (self.all_set_loop_random, vb.set_loop_random),
            (self.all_set_loop_start, vb.set_loop_start),
            (self.all_set_loop_end, vb.set_loop_end),
            (self.all_loop_chapter, vb.loop_chapter),
            (self.all_reset_loop, vb.reset_loop),
            (self.all_set_end_action, vb.set_end_action),
            (self.all_set_dir_recursive, vb.set_dir_recursive),
            (self.all_set_list_end_action, vb.set_list_end_action),
            (self.all_set_list_fail_action, vb.set_list_fail_action),
            (self.all_set_list_fail_wait, vb.set_list_fail_wait),
            (self.all_rate_increase, vb.rate_increase),
            (self.all_rate_decrease, vb.rate_decrease),
            (self.all_rate_reset, vb.rate_reset),
            (self.all_scale_increase, vb.scale_increase),
            (self.all_scale_decrease, vb.scale_decrease),
            (self.all_scale_reset, vb.scale_reset),
            (self.all_set_zoom_to_cursor, vb.set_zoom_to_cursor),
            (self.all_crop, vb.crop),
            (self.all_crop_reset, vb.crop_reset),
            (self.all_set_anchor, vb.set_anchor),
            (self.all_shift_by, vb.shift_by),
            (self.all_shift_reset, vb.shift_reset),
            (self.all_set_shift_past_edges, vb.set_shift_past_edges),
            (self.all_set_aspect, vb.set_aspect),
            (self.all_set_transform, vb.set_transform),
            (self.all_take_screenshot, vb.take_screenshot),
            (self.all_set_auto_reload_timer, vb.set_auto_reload_timer),
            (self.all_set_audio_channel_mode, vb.set_audio_channel_mode),
            (self.all_set_audio_delay, vb.set_audio_delay),
            (self.all_audio_delay_increase, vb.audio_delay_increase),
            (self.all_audio_delay_decrease, vb.audio_delay_decrease),
            (self.all_audio_delay_reset, vb.audio_delay_reset),
            (self.all_set_subtitle_delay, vb.set_subtitle_delay),
            (self.all_subtitle_delay_increase, vb.subtitle_delay_increase),
            (self.all_subtitle_delay_decrease, vb.subtitle_delay_decrease),
            (self.all_subtitle_delay_reset, vb.subtitle_delay_reset),
            (self.all_volume_increase, vb.volume_increase),
            (self.all_volume_decrease, vb.volume_decrease),
            (self.all_set_muted, vb.set_muted),
            (self.all_previous_video, vb.previous_video),
            (self.all_next_video, vb.next_video),
            (self.all_shuffle_video, vb.shuffle_video),
            (self.hide_overlay, vb.hide_overlay),
            (self.show_overlay, vb.show_overlay),
            (self.set_drag_ui, vb.set_drag_ui),
            (self.close_all_signal, vb.close_silently),
        )

        vb.set_video(video)

        self._ctx.video_blocks.append(vb)

        return vb
