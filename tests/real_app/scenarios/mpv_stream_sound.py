"""A stream whose sound is opened apart, its link refused: MPV plays the picture on,
silent, and says nothing. The cell is loaded again, as for a video failing, and told
once that's no better."""

from tests.real_app.driver import QuietHandler

SETTINGS = {
    "player/video_driver": "mpv_hw",
    # Streamlink takes only the default audio of an HLS stream, in one with the video
    "streaming/resolver_priority": "yt_dlp",
    "video_defaults/network_retry_mode": "times",
    "video_defaults/network_retry_times": 1,
}

SOUND = ("/venglish/", "/vspanish/")


class _NoSound(QuietHandler):
    def do_GET(self):
        if self.path.startswith(SOUND):
            self.send_error(403)
            return

        super().do_GET()


def scenario(d):
    d.open(f"{d.serve(d.media.dubs, _NoSound)}/master.m3u8")
    cell = d.wait_for_cell("master.m3u8")

    player = cell.video_driver.video_driver._player
    d.check("the sound was to be opened apart", player.media_input.stream_audio)

    d.wait_until(lambda: cell.is_error, "the cell is told", timeout=30)

    error = cell.status.last_error
    d.check("of the sound", error.title == "Can't play the sound", error)
    d.check("by what the server said", error.code == "HTTP 403", error)
    tries = cell.status._error_tries
    d.check("loaded again first", tries == 1, tries)
    d.shot("told")
