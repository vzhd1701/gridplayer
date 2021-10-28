from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.about import AboutDialog
from gridplayer.params_static import SUPPORTED_VIDEO_EXT
from gridplayer.video import Video


class PlayerCommandsMixin(object):
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

    def cmd_about(self):
        AboutDialog(self).exec_()

    def cmd_set_grid_mode(self, mode):
        if self.grid_mode == mode:
            return

        self.grid_mode = mode
        self.reload_video_grid()

    def cmd_add_videos(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFiles)

        supported_exts = " ".join((f"*.{e}" for e in SUPPORTED_VIDEO_EXT))
        dialog.setNameFilter(f"Videos ({supported_exts})")

        if dialog.exec():
            files = dialog.selectedFiles()
            self.add_videos(Video(file_path=f) for f in files)
