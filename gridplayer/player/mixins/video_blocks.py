from PyQt5.QtCore import QEvent, pyqtSignal

from gridplayer.widgets.video_block import VideoBlock


class PlayerVideoBlocksMixin(object):
    video_count_change = pyqtSignal(int)
    playings_videos_count_change = pyqtSignal(int)

    hide_overlay = pyqtSignal()
    set_pause = pyqtSignal(int)
    seek_shift = pyqtSignal(int)
    seek_random = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.video_blocks = {}
        self.active_video_block = None

    def mouseMoveEvent(self, event):
        self.update_active_block(event.pos())

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self.update_active_block(event.pos())

        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self.update_active_block(None)

        super().leaveEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.NonClientAreaMouseMove:
            self.update_active_block(None)

        if event.type() in {QEvent.ShortcutOverride, QEvent.NonClientAreaMouseMove}:
            self.cmd_active("show_overlay")

        return super().event(event)

    @property
    def is_videos(self):
        return bool(self.video_blocks)

    def update_active_block(self, pos):
        if self.is_modal_open:
            return

        old_active_block = self.active_video_block

        if pos is None:
            self.active_video_block = None
        else:
            self.active_video_block = self.get_hover_video_block()

            if self.active_video_block is not None:
                self.active_video_block.is_active = True

        if old_active_block is not None and self.active_video_block != old_active_block:
            old_active_block.is_active = False

    def add_new_video_block(self, video):
        vb = VideoBlock(
            video_driver=self.driver_manager.driver,
            parent=self,
        )
        vb.installEventFilter(self)

        con_list = [
            (vb.exit_request, self.close_video_block),
            (vb.is_paused_change, self.is_paused_change),
            (self.set_pause, vb.set_pause),
            (self.seek_shift, vb.seek_shift_percent),
            (self.seek_random, vb.seek_random),
            (self.hide_overlay, vb.hide_overlay),
        ]

        for c_sig, c_slot in con_list:
            c_sig.connect(c_slot)

        vb.set_video(video)

        self.video_blocks[vb.id] = vb

        self.video_count_change.emit(len(self.video_blocks))

    def remove_video_blocks(self, *videoblocks):
        for vb in videoblocks:
            self.videogrid.takeAt(self.videogrid.indexOf(vb))

            if vb is self.active_video_block:
                self.active_video_block = None

            vb.cleanup()
            self.video_blocks.pop(vb.id)

            vb.deleteLater()

        self.video_count_change.emit(len(self.video_blocks))

    def get_hover_video_block(self):
        visible_blocks_under_cursor = (
            v
            for v in self.video_blocks.values()
            if v.isVisible() and v.is_under_cursor()
        )

        return next(visible_blocks_under_cursor, None)

    def cmd_active(self, command, *args):
        if self.active_video_block is None:
            return

        getattr(self.active_video_block, command)(*args)

    def is_active_param_set_to(self, param_name, param_value):
        if self.active_video_block is None:
            return False

        active_video_param = getattr(self.active_video_block.video_params, param_name)

        return active_video_param == param_value

    def close_video_block(self, _id):
        if self.is_single_mode:
            self.toggle_single_video()

        self.remove_video_blocks(self.video_blocks[_id])
        self.reload_video_grid()

        self.update_active_block(self.get_current_cursor_pos())
        self.cmd_active("show_overlay")

    def close_all(self):
        self.remove_video_blocks(*list(self.video_blocks.values()))
        self.reload_video_grid()

        self.is_paused_change()

        self.driver_manager.cleanup()

    def is_paused_change(self):
        playing_videos_count = sum(
            True for v in self.video_blocks.values() if not v.video_params.is_paused
        )
        self.playings_videos_count_change.emit(playing_videos_count)
