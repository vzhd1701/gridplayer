from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.keepawake import KeepAwake


class ScreensaverManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.keepawake = KeepAwake()

    def screensaver_check(self, playing_videos_count):
        if not Settings().get("player/inhibit_screensaver"):
            self.keepawake.screensaver_on()
            return

        is_something_playing = playing_videos_count > 0

        if is_something_playing:
            self.keepawake.screensaver_off()
        else:
            self.keepawake.screensaver_on()
