from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.keepawake import KeepAwake, KeepAwakeMode


class ScreensaverManager(ManagerBase):
    """The screen kept on while videos play, and the system awake.

    With the window minimized or in the tray there is nothing to watch, only
    to hear: the screen may go off then, the system is still kept awake.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.keepawake = KeepAwake()

        self._playing_count = 0
        self._is_away = False

    def screensaver_check(self, playing_videos_count):
        self._playing_count = playing_videos_count

        self.refresh()

    def set_away(self, is_away):
        self._is_away = is_away

        self.refresh()

    def refresh(self, *_):
        self.keepawake.set_mode(self._mode())

    def _mode(self):
        if not Settings().get("player/inhibit_screensaver"):
            return KeepAwakeMode.NONE

        if self._playing_count <= 0:
            return KeepAwakeMode.NONE

        if self._is_away:
            return KeepAwakeMode.SLEEP

        return KeepAwakeMode.SCREEN
