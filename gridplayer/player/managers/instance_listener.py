from PyQt5.QtCore import pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.single_instance import Listener


class InstanceListenerManager(ManagerBase):
    files_opened = pyqtSignal(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._instance_listener = Listener()
        self._instance_listener.start()

        self._instance_listener.open_files.connect(self.files_opened)
        self.destroyed.connect(self._instance_listener.cleanup)