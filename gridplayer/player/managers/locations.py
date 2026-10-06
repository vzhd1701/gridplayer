"""Where the videos are: copied out, shown in their folder, opened elsewhere.

None of it asks for a video that plays. A file that is gone or a stream
that fails is when its name is wanted most, so these go by the address
the video was given and never through the active video's own commands,
which a video that cannot play drops.
"""

from pathlib import Path

from PyQt5.QtCore import QProcess, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication

from gridplayer.params import env
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.show_in_folder import FolderRevealer
from gridplayer.utils.url_at_time import url_at_time


class LocationsManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._revealer = FolderRevealer(parent=self)

    @property
    def commands(self):
        return {
            "is_active_file": self.is_active_file,
            "is_active_url": self.is_active_url,
            "is_active_web_url": self.is_active_web_url,
            "is_active_url_at_time": self.is_active_url_at_time,
            "copy_active_file_name": self.cmd_copy_active_file_name,
            "copy_active_file_path": self.cmd_copy_active_file_path,
            "show_active_in_folder": self.cmd_show_active_in_folder,
            "copy_active_url": self.cmd_copy_active_url,
            "copy_active_url_at_time": self.cmd_copy_active_url_at_time,
            "open_active_url": self.cmd_open_active_url,
            "copy_all_locations": self.cmd_copy_all_locations,
        }

    @property
    def _active_uri(self) -> Path | str | None:
        block = self._ctx.active_block

        if block is None or block.video_params is None:
            return None

        return block.video_params.uri

    def is_active_file(self) -> bool:
        return isinstance(self._active_uri, Path)

    def is_active_url(self) -> bool:
        return isinstance(self._active_uri, str)

    def is_active_web_url(self) -> bool:
        return self.is_active_url() and self._active_uri.startswith(
            ("http://", "https://")
        )

    def is_active_url_at_time(self) -> bool:
        return self._active_url_at_time() is not None

    def cmd_copy_active_file_name(self):
        if self.is_active_file():
            _copy(self._active_uri.name)

    def cmd_copy_active_file_path(self):
        if self.is_active_file():
            _copy(str(self._active_uri))

    def cmd_show_active_in_folder(self):
        if self.is_active_file():
            self._revealer.show(self._active_uri)

    def cmd_copy_active_url(self):
        if self.is_active_url():
            _copy(self._active_uri)

    def cmd_copy_active_url_at_time(self):
        url = self._active_url_at_time()

        if url is not None:
            _copy(url)

    def cmd_open_active_url(self):
        if not self.is_active_web_url():
            return

        if env.IS_SNAP:
            # https://forum.snapcraft.io/t/xdg-open-or-gvfs-open-qdesktopservices-openurl-file-somelocation-file-txt-wont-open-the-file/16824
            QProcess.startDetached("xdg-open", [self._active_uri])
        else:
            QDesktopServices.openUrl(QUrl(self._active_uri))

    def cmd_copy_all_locations(self):
        """Every video's file or address, a line each, as the grid has them.

        Which is what Add from Clipboard takes, to put them all back.
        """

        blocks = self._ctx.video_blocks.blocks_for_ids(
            self._ctx.commands.layout_order()
        )

        locations = [
            str(block.video_params.uri)
            for block in blocks
            if block.video_params is not None
        ]

        if locations:
            _copy("\n".join(locations))

    def _active_url_at_time(self) -> str | None:
        """Where the active video is playing now, as its site would have it.

        Only for one that has a now to give: one that has started, and
        not a live one, whose now is the only place it can be opened at.
        """

        if not self.is_active_url():
            return None

        block = self._ctx.active_block

        if not block.is_video_initialized or block.is_live:
            return None

        return url_at_time(self._active_uri, block.time, block.youtube_id)


def _copy(text: str) -> None:
    QApplication.clipboard().setText(text)
