from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.add_urls import QAddURLsDialog
from gridplayer.models.video import VideoURL, filter_video_uris
from gridplayer.params.extensions import (
    SUPPORTED_AUDIO_EXT,
    SUPPORTED_MEDIA_EXT,
    SUPPORTED_VIDEO_EXT,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import translate
from gridplayer.utils.url_resolve.static import PLUGIN_URLS


class AddVideosManager(ManagerBase):
    videos_added = pyqtSignal(list)

    error = pyqtSignal(str)

    @property
    def commands(self):
        return {"add_videos": self.cmd_add_videos, "add_urls": self.cmd_add_urls}

    def cmd_add_videos(self):
        dialog = QFileDialog(
            parent=self.parent(),
            caption=translate("Dialog - Add Files", "Add Files", "Header"),
        )
        dialog.setFileMode(QFileDialog.ExistingFiles)

        dialog.setNameFilters(_get_name_filters())

        if dialog.exec():
            videos = filter_video_uris(dialog.selectedFiles())

            self.videos_added.emit(videos)

    def cmd_add_urls(self):
        urls = QAddURLsDialog.get_urls(
            parent=self.parent(),
            title=translate("Dialog - Add URLs", "Add URL(s)", "Header"),
            supported_schemas=VideoURL.allowed_schemes,
            supported_urls=PLUGIN_URLS,
        )

        valid_urls = filter_video_uris(urls)

        if urls and not valid_urls:
            self.error.emit(translate("Error", "No valid URLs found!"))

        if valid_urls:
            self.videos_added.emit(valid_urls)


def _get_name_filters():
    ext_types = [
        {
            "name": translate("Dialog - Add Files", "Media", "File formats"),
            "extensions": SUPPORTED_MEDIA_EXT,
        },
        {
            "name": translate("Dialog - Add Files", "Video", "File formats"),
            "extensions": SUPPORTED_VIDEO_EXT,
        },
        {
            "name": translate("Dialog - Add Files", "Audio", "File formats"),
            "extensions": SUPPORTED_AUDIO_EXT,
        },
    ]

    name_filers = []

    for ext_type in ext_types:
        ext_with_asterisk = (f"*.{e}" for e in sorted(ext_type["extensions"]))
        ext_list = " ".join(ext_with_asterisk)
        name_filers.append("{0} ({1})".format(ext_type["name"], ext_list))

    return name_filers
