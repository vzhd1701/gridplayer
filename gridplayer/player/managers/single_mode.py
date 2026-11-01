from PyQt5.QtCore import pyqtSignal

from gridplayer.params.static import NO_FILL_LIMIT, StripMode, StripSide
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.layout.strip import StripVideos


class SingleModeManager(ManagerBase):
    """One video shown big, the others out of sight; or, with the strip on,
    small in a strip beside it, still playing (see strip_layout). Show Big
    on one in the strip, a double click by default, shows it big instead: in
    the Strip, it trades places with the big one; in the Fixed Strip, every
    video keeps its place, the big one's held (see HeldPlace).

    The one shown big, in Fill, fills the window only where that cuts no
    more of it than the playlist allows, and is shown whole otherwise (see
    apply_crop)."""

    mode_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_single_mode = False
        self._ctx.is_pause_background_videos = Settings().get(
            "playlist/pause_background_videos"
        )

        # the video shown big, and the others in the strip's order: one shown
        # big trades places with the one it takes the place of, the rest of
        # the strip staying as it is
        self._main = None
        self._strip = []

        self._pre_sm_states = {}

        # the video given Single Mode's fill limit, the one shown big
        self._cropped = None

    @property
    def commands(self):
        return {
            "next_single_video": self.next_single_video,
            "previous_single_video": self.previous_single_video,
            "toggle_single_video": self.toggle_single_video,
            "is_single_mode": lambda: self._ctx.is_single_mode,
            "single_mode_video": self.single_mode_video,
            "strip_videos": self.strip_videos,
            "is_active_in_strip": self.is_active_in_strip,
            "show_big": self.show_big,
            "is_more_than_one_video": lambda: len(self._ctx.video_blocks) > 1,
            "is_single_mode_available": self.is_single_mode_available,
            "is_pause_background_videos": lambda: self._ctx.is_pause_background_videos,
            "set_pause_background_videos": self.set_pause_background_videos,
            "toggle_pause_background_videos": self.toggle_pause_background_videos,
            "is_single_mode_strip_set_to": lambda mode: self.strip_mode() == mode,
            "set_single_mode_strip": self.choose_strip,
            "is_single_mode_strip_side_set_to": lambda side: self.strip_side() == side,
            "set_single_mode_strip_side": self.choose_strip_side,
            "is_single_mode_crop_set_to": lambda crop: self.crop() == crop,
            "set_single_mode_crop": self.choose_crop,
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

    def single_mode_video(self):
        """The video shown big, in Single Mode."""

        return self._main if self._ctx.is_single_mode else None

    def strip_videos(self) -> StripVideos | None:
        """The strip as the grid lays it out (see StripVideos), None with
        no strip shown."""

        mode = self.strip_mode()
        if (
            not self._ctx.is_single_mode
            or mode == StripMode.OFF
            or len(self._ctx.video_blocks) < 2
            # closed, Single Mode about to be left
            or self._main not in self._ctx.video_blocks
        ):
            return None

        if mode == StripMode.FIXED:
            strip = self._ordered_blocks()
        else:
            # in the strip's order, any not in it yet after
            others = [vb for vb in self._ctx.video_blocks if vb is not self._main]
            kept = [vb for vb in self._strip if vb in set(others)]
            strip = kept + [vb for vb in others if vb not in set(kept)]

        return StripVideos(self._main, strip, self.strip_side())

    def is_active_in_strip(self) -> bool:
        """Whether the active video is one of the strip's, not the one shown
        big."""

        active = self._ctx.active_block
        return (
            self._ctx.is_single_mode
            and self.is_strip()
            and active not in {None, self._main}
        )

    def show_big(self):
        if self.is_active_in_strip():
            self._show_big(self._ctx.active_block)

    def strip_mode(self) -> StripMode:
        return PlaylistSettings().get("playlist/single_mode_strip")

    def is_strip(self) -> bool:
        return self.strip_mode() != StripMode.OFF

    def choose_strip(self, mode: StripMode):
        PlaylistSettings().set("playlist/single_mode_strip", mode)
        self.set_strip(mode)

    def set_strip(self, mode: StripMode):
        """The others shown in the strip, playing, or out of sight."""

        if not self._ctx.is_single_mode:
            return

        for vb in self._others():
            if mode != StripMode.OFF:
                self._restore_playing(vb)
            else:
                self._pause_playing(vb)
                vb.hide()

        # the grid shows those in the strip as it lays them out
        self.mode_changed.emit()

    def strip_side(self) -> StripSide:
        return PlaylistSettings().get("playlist/single_mode_strip_side")

    def choose_strip_side(self, side: StripSide):
        PlaylistSettings().set("playlist/single_mode_strip_side", side)
        self.relayout()

    def relayout(self, *_):
        # the grid lays the strip out again, on its side as it is now
        if self._ctx.is_single_mode:
            self.mode_changed.emit()

    def crop(self) -> int:
        """How much of the video shown big may be cut to fill the window,
        in percent (see ViewParams.fill_limit)."""

        return PlaylistSettings().get("playlist/single_mode_crop")

    def choose_crop(self, crop: int):
        PlaylistSettings().set("playlist/single_mode_crop", crop)
        self.apply_crop()

    def apply_crop(self, *_):
        """The video shown big filling the window as far as the playlist
        allows it to be cut, the one shown big till now as it was."""

        main = self._main if self._ctx.is_single_mode else None
        if main is not None and main not in self._ctx.video_blocks:
            main = None

        if self._cropped is not None and self._cropped is not main:
            if self._cropped in self._ctx.video_blocks:
                self._cropped.view.set_fill_limit(NO_FILL_LIMIT)
            self._cropped = None

        if main is not None:
            main.view.set_fill_limit(self.crop())
            self._cropped = main

    def set_pause_background_videos(self, is_pause):
        was_pause = self._ctx.is_pause_background_videos
        self._ctx.is_pause_background_videos = is_pause
        if not self._ctx.is_single_mode or was_pause == is_pause:
            return

        if is_pause:
            self._pause_hidden_videos()
        else:
            self._restore_hidden_videos()

    def toggle_pause_background_videos(self):
        value = not self._ctx.is_pause_background_videos
        PlaylistSettings().set("playlist/pause_background_videos", value)
        self.set_pause_background_videos(value)

    def _others(self):
        return [vb for vb in self._ctx.video_blocks if vb is not self._main]

    def _hidden(self):
        # those out of sight: none, with the strip
        return [] if self.is_strip() else self._others()

    def _pause_hidden_videos(self):
        for vb in self._hidden():
            self._pause_playing(vb)

    def _restore_hidden_videos(self):
        for vb in self._hidden():
            self._restore_playing(vb)

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

        self._main = self._ctx.active_block
        self._strip = [vb for vb in self._ordered_blocks() if vb is not self._main]
        self._ctx.is_single_mode = True

        for vb in self._hidden():
            self._pause_playing(vb)
            vb.hide()

        self.mode_changed.emit()
        self.apply_crop()

    def single_mode_off(self):
        self._ctx.is_single_mode = False

        for vb in self._others():
            self._restore_playing(vb)

        # The grid shows the hidden videos as it lays them out again, all at
        # once. Shown here one by one, each would lay the grid out on the spot.
        self.mode_changed.emit()
        self.apply_crop()

    def _switch_single_video(self, is_before):
        if not self._ctx.is_single_mode or self._main is None:
            return

        next_sv = self._find_next_single_video(self._main, is_before)
        if next_sv is self._main:
            return

        if self.is_strip():
            self._show_big(next_sv)
            return

        current_sv = self._main
        self._set_main(next_sv)

        self._pause_playing(current_sv)
        current_sv.hide()

        self._restore_playing(next_sv)
        next_sv.show()

    def _show_big(self, vb):
        # one of the strip's, in the big one's place
        if vb is None or vb is self._main:
            return

        self._set_main(vb)
        self.mode_changed.emit()
        # another video under the pointer now, the one shown big till now;
        # with a button held, once it is let go of
        self._ctx.commands.update_active_under_mouse()

    def _set_main(self, vb):
        # the one shown big till now in the place it leaves in the strip
        if vb in self._strip:
            self._strip[self._strip.index(vb)] = self._main
        self._main = vb
        self.apply_crop()

    def _ordered_blocks(self):
        return self._ctx.video_blocks.blocks_for_ids(self._ctx.commands.layout_order())

    def _find_next_single_video(self, current_sv, is_before):
        blocks = self._ordered_blocks()
        if not blocks or current_sv not in blocks:
            return current_sv
        idx = blocks.index(current_sv)
        if is_before:
            return blocks[idx - 1]
        return blocks[(idx + 1) % len(blocks)]

    def _pause_playing(self, vb):
        if not self._ctx.is_pause_background_videos:
            return
        if vb.video_params.is_paused:
            return
        self._pre_sm_states[vb.id] = False
        vb.set_pause(True)

    def _restore_playing(self, vb):
        pre_sm_state = self._pre_sm_states.pop(vb.id, None)
        if pre_sm_state is not None:
            vb.set_pause(pre_sm_state)
