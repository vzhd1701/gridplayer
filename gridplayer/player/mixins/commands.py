from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.about import AboutDialog
from gridplayer.params_static import SUPPORTED_VIDEO_EXT
from gridplayer.utils.misc import ModalWindow


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

    def cmd_minimize(self):
        self.showMinimized()

    def cmd_step_forward(self):
        self.pause_all()
        self.step_frame.emit(-1)

    def cmd_step_backward(self):
        self.pause_all()
        self.step_frame.emit(1)

    def cmd_fullscreen(self):
        if self.isFullScreen():
            if self.is_maximized_pre_fullscreen:
                self.showMaximized()
            else:
                self.showNormal()

            self.is_maximized_pre_fullscreen = False
        else:
            self.is_maximized_pre_fullscreen = self.windowState() == Qt.WindowMaximized

            self.showFullScreen()

    def cmd_about(self):
        with ModalWindow(self):
            about_dialog = AboutDialog(self)
            about_dialog.exec_()

    def cmd_set_grid_mode(self, mode):
        if self.playlist.grid_mode == mode:
            return

        self.playlist.grid_mode = mode
        self.reload_video_grid()

    def cmd_add_videos(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFiles)

        supported_exts = " ".join((f"*.{e}" for e in SUPPORTED_VIDEO_EXT))
        dialog.setNameFilter(f"Videos ({supported_exts})")

        if dialog.exec():
            files = dialog.selectedFiles()
            self.add_videos(files)
