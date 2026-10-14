"""A stream in three sizes, switched between; and a link that fails, tried
again, shown with its Details and reloaded."""

from PyQt5.QtWidgets import QLabel

SETTINGS = {
    "video_defaults/network_retry_mode": "times",
    "video_defaults/network_retry_times": 2,
}

# nothing listens on the discard port
DEAD = "http://127.0.0.1:9/dead.mp4"


def scenario(d):
    hls_url = f"{d.serve(d.media.hls)}/master.m3u8"
    d.open(hls_url, DEAD)

    hls = d.wait_for_cell("master.m3u8")
    sizes = d.menu(hls, "menu_generator_stream_quality")
    d.check("three sizes", {"360p", "180p", "90p"} <= set(sizes), sizes)
    d.check("the biggest plays", hls.stream.quality_playing == "360p")

    d.choose(hls, "menu_generator_stream_quality", "180p")
    d.wait_until(
        lambda: hls.stream.quality_playing == "180p" and hls.is_playable,
        "180p plays",
    )

    dead = d.cell("dead.mp4")
    d.wait_until(lambda: dead.is_error, "the dead link gives up", timeout=40)
    d.check(
        "it says why",
        dead.status.last_error.title == "Connection refused",
        dead.status.last_error.title,
    )
    d.shot("dead_link")

    def tries_shown(window):
        texts = [label.text() for label in window.findChildren(QLabel)]
        d.check("Details count the tries", "2 of 2" in texts, texts)

    d.through_modal(dead.status.show_error_details, "details", tries_shown)

    d.act(dead, "Reload")
    d.wait_until(lambda: not dead.is_error, "a reload tries again")
    d.wait_until(lambda: dead.is_error, "and gives up again", timeout=40)

    d.note("end")
