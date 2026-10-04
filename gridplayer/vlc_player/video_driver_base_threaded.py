from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.multiprocess.process_manager import describe_exit_code
from gridplayer.utils.qt import translate
from gridplayer.vlc_player.static import MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver


class VLCVideoDriverThreaded(CommandLoopThreaded, VLCVideoDriver):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_cleanup_started = False

        self.crash_func = self.crash_thread
        self.cmd_loop_start_thread()

    def crash_thread(self, traceback_txt):
        self.crash.emit(traceback_txt)

    def process_crashed(self, exit_code):
        """The process the player ran in died, and the player with it.

        Called from the process manager's thread.
        """

        self.player_gone()

        # going anyway, and nobody is waiting to hear about it
        if self._is_cleanup_started:
            return

        self._log.error(
            f"Video process died with exit code {describe_exit_code(exit_code)}"
        )

        self.error.emit(translate("Video Error", "Video process crashed"))

    def player_gone(self):
        """Stop waiting on a player that can no longer answer."""

    def cleanup_start(self):
        self._is_cleanup_started = True

        self.cmd_send("cleanup")

    def cleanup_wait(self):
        self.cmd_loop_terminate()

    def load_video(self, media_input: MediaInput):
        self.cmd_send("load_video", media_input)

    def snapshot(self):
        self.cmd_send("snapshot")

    def screenshot(self):
        self.cmd_send("screenshot")

    def play(self):
        self.cmd_send("play")

    def set_pause(self, is_paused):
        self.cmd_send("set_pause", is_paused)

    def set_time(self, seek_ms):
        self.cmd_send("set_time", seek_ms)

    def set_playback_rate(self, rate):
        self.cmd_send("set_playback_rate", rate)

    def audio_set_mute(self, is_muted):
        self.cmd_send("audio_set_mute", is_muted)

    def audio_set_volume(self, volume):
        self.cmd_send("audio_set_volume", volume)

    def set_audio_track(self, track_id):
        self.cmd_send("set_audio_track", track_id)

    def set_audio_device(self, device):
        self.cmd_send("set_audio_device", device)

    def add_audio_slave(self, uri):
        self.cmd_send("add_audio_slave", uri)

    def set_video_track(self, track_id):
        self.cmd_send("set_video_track", track_id)

    def set_subtitle_track(self, track_id):
        self.cmd_send("set_subtitle_track", track_id)

    def add_subtitle_slave(self, uri):
        self.cmd_send("add_subtitle_slave", uri)

    def set_audio_channel_mode(self, mode):
        self.cmd_send("set_audio_channel_mode", mode)

    def set_deinterlace(self, deinterlace, mode):
        self.cmd_send("set_deinterlace", deinterlace, mode)

    def set_audio_delay(self, delay_ms):
        self.cmd_send("set_audio_delay", delay_ms)

    def set_subtitle_delay(self, delay_ms):
        self.cmd_send("set_subtitle_delay", delay_ms)
