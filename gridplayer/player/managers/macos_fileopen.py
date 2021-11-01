import subprocess

from PyQt5.QtCore import QEvent, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.single_instance import is_the_only_instance
from gridplayer.version import __app_name__


class MacOSFileOpenManager(ManagerBase):
    file_opened = pyqtSignal(list)

    @property
    def event_map(self):
        return {QEvent.FileOpen: self.handle_macos_fileopen}

    def handle_macos_fileopen(self, event):
        input_file = event.file()

        if not input_file:
            return

        Settings().sync()

        is_empty = not self._ctx.video_blocks
        is_only_empty = is_the_only_instance() and is_empty

        if Settings().get("player/one_instance") or is_only_empty:
            self.file_opened.emit([input_file])
        else:
            subprocess.run(  # noqa: S603, S607
                [
                    "open",
                    "-n",
                    f"/Applications/{__app_name__}.app",
                    "--args",
                    input_file,
                ]
            )
