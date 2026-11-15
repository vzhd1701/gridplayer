"""A live DASH stream, whichever driver: played on as it goes, back to it after a
pause, and nothing asked for before it's out. VLC follows the manifest itself; mpv,
whose DASH reader can't, is served it by the proxy as live HLS."""

from tests.real_app.scenarios.live import _is_moving, _picture

SETTINGS = {
    "video_defaults/network_retry_mode": "times",
    "video_defaults/network_retry_times": 1,
}


def scenario(d):
    live = d.serve_live_dash(d.media.dash)
    d.open(live.url)
    cell = d.wait_for_cell("live.mpd")

    d.check("it's live", cell.is_live)
    _is_moving(d, cell)
    d.check("with its sound", cell.video_driver.media.cur_audio_track is not None)

    d.act(cell, "Play / Pause")
    d.wait_until(lambda: cell.video_params.is_paused, "it's paused")
    d.wait(3)
    d.act(cell, "Play / Pause")
    d.wait_until(lambda: cell.is_playable and not cell.video_params.is_paused, "again")

    # past what was out when it was opened: it's followed, not read once
    d.wait(15)
    held = _picture(cell)
    d.wait(1)
    d.check("still moving", _picture(cell) != held)
    d.check("nothing asked for too early", not live.too_early, live.too_early[:5])
    d.shot("later")
