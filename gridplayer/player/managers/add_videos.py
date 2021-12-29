from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog

from gridplayer.params_static import SUPPORTED_VIDEO_EXT
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.files import filter_valid_files
from gridplayer.utils.misc import tr
from gridplayer.video import Video


class AddVideosManager(ManagerBase):
    videos_added = pyqtSignal(list)

    @property
    def commands(self):
        return {"add_videos": self.cmd_add_videos}

    def cmd_add_videos(self):
        dialog = QFileDialog(self.parent())
        dialog.setFileMode(QFileDialog.ExistingFiles)

        supported_exts = " ".join((f"*.{e}" for e in sorted(SUPPORTED_VIDEO_EXT)))
        dialog.setNameFilter("{0} ({1})".format(tr("Videos"), supported_exts))

        if dialog.exec():
            videos = [
                Video(file_path=f, title=f.name)
                for f in filter_valid_files(list(map(Path, dialog.selectedFiles())))
            ]

            self.videos_added.emit(videos)
