from gridplayer.settings import Settings
from gridplayer.utils.keepawake import KeepAwake


class PlayerScreensaverMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.keepawake = KeepAwake()

    def screensaver_check(self):
        if not Settings().get("player/inhibit_screensaver"):
            return

        playing_videos = (
            True for v in self.video_blocks.values() if not v.video_params.is_paused
        )
        is_something_playing = next(playing_videos, False)

        if is_something_playing:
            if not self.keepawake.is_screensaver_off:
                self.keepawake.screensaver_off()
        elif self.keepawake.is_screensaver_off:
            self.keepawake.screensaver_on()
