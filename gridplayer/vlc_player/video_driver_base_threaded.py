from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.vlc_player.static import MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver


class VLCVideoDriverThreaded(CommandLoopThreaded, VLCVideoDriver):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.crash_func = self.crash_thread
        self.cmd_loop_start_thread()

    def crash_thread(self, traceback_txt):
        self.crash.emit(traceback_txt)

    def cleanup(self):
        self.cmd_send("cleanup")
        self.cmd_loop_terminate()

    def load_video(self, media_input: MediaInput):
        self.cmd_send("load_video", media_input)

    def snapshot(self):
        self.cmd_send("snapshot")

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
