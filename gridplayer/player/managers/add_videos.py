from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.add_urls import QAddURLsDialog
from gridplayer.params_static import SUPPORTED_VIDEO_EXT
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.misc import tr
from gridplayer.utils.url_resolve.url_resolve import plugin_list_urls
from gridplayer.video import VideoURL, filter_video_uris


class AddVideosManager(ManagerBase):
    videos_added = pyqtSignal(list)

    error = pyqtSignal(str)

    @property
    def commands(self):
        return {"add_videos": self.cmd_add_videos, "add_urls": self.cmd_add_urls}

    def cmd_add_videos(self):
        dialog = QFileDialog(self.parent())
        dialog.setFileMode(QFileDialog.ExistingFiles)

        supported_exts = " ".join((f"*.{e}" for e in sorted(SUPPORTED_VIDEO_EXT)))
        dialog.setNameFilter("{0} ({1})".format(tr("Videos"), supported_exts))

        if dialog.exec():
            videos = filter_video_uris(dialog.selectedFiles())

            self.videos_added.emit(videos)

    def cmd_add_urls(self):
        urls = QAddURLsDialog.get_urls(
            parent=self.parent(),
            title=tr("Add URL(s)"),
            supported_schemas=VideoURL.allowed_schemes,
            supported_urls=plugin_list_urls(),
        )

        valid_urls = filter_video_uris(urls)

        if urls and not valid_urls:
            self.error.emit(tr("No valid URLs found!"))

        if valid_urls:
            self.videos_added.emit(valid_urls)
