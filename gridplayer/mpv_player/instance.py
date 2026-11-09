"""The processes mpv players run in.

libmpv has no instance to share between players the way libVLC does, each
player is a whole mpv, so all a process has to look after is its players.
"""

import ctypes
import logging

from gridplayer.multiprocess.instance_process import InstanceProcess
from gridplayer.multiprocess.process_manager import ProcessManager
from gridplayer.params import env

_PROCESS_PER_MONITOR_DPI_AWARE = 2


def _make_process_dpi_aware() -> None:
    """Have every window mpv makes here measured the way Qt measures them.

    mpv makes the process DPI aware itself, but only as its first window
    goes up: that one comes out in scaled coordinates and the rest do not.
    """

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(_PROCESS_PER_MONITOR_DPI_AWARE)
    except OSError:
        logging.getLogger(__name__).debug("Could not set DPI awareness", exc_info=True)


class InstanceProcessMPV(InstanceProcess):
    def init_instance(self):
        if env.IS_WINDOWS:
            _make_process_dpi_aware()

    def cleanup_instance(self): ...

    def init_player_shared_data(self, player_id): ...

    def release_player_shared_data(self, player_id): ...


class ProcessManagerMPV(ProcessManager):
    def set_log_level_vlc(self, log_level):
        """Asked of whichever manager there is; there is no VLC here to tell."""
