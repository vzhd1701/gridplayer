from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.vlc_player.player_base import VlcPlayerBase


class VlcPlayerThreaded(CommandLoopThreaded, VlcPlayerBase):
    def start(self):
        self.cmd_loop_start_thread(self.init_player)

    def notify_update_status(self, status, percent=0):
        self.cmd_send("update_status_emit", status, percent)

    def notify_error(self, error):
        self.cmd_send("error_state", error)

    def notify_time_changed(self, new_time):
        self.cmd_send("time_changed_emit", new_time)

    def notify_playback_status_changed(self, is_paused):
        self.cmd_send("playback_status_changed_emit", is_paused)

    def notify_end_reached(self):
        self.cmd_send("end_reached_emit")

    def notify_load_video_done(self, media_track):
        self.cmd_send("load_video_done", media_track)

    def notify_snapshot_taken(self, snapshot_path):
        self.cmd_send("snapshot_taken_emit", snapshot_path)

    def loopback_load_video_st2_set_media(self):
        self.cmd_send_self("load_video_st2_set_media")

    def loopback_load_video_st3_extract_media_track(self):
        self.cmd_send_self("load_video_st3_extract_media_track")

    def loopback_load_video_st4_loaded(self):
        self.cmd_send_self("load_video_st4_loaded")
