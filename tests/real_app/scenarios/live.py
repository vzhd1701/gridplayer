"""A live stream, whichever driver: no length, nothing to seek, pausing lets go of it and
Play comes back to where it has got to, and one that goes away is told."""

SETTINGS = {
    "video_defaults/network_retry_mode": "times",
    "video_defaults/network_retry_times": 1,
}


def _picture(cell):
    """What the frame has to show, none of what's over it."""

    image = cell.video_driver.shown_frame_image()

    if image is None:
        return b""

    bits = image.bits()
    bits.setsize(image.byteCount())

    return bytes(bits)


def _is_all_one_colour(picture: bytes) -> bool:
    return picture.count(picture[:4]) * 4 >= len(picture)


def _is_moving(d, cell) -> bool:
    d.wait_until(lambda: _picture(cell), "there's a picture")

    start = _picture(cell)

    return d.wait_until(lambda: _picture(cell) != start, "the picture moves")


def scenario(d):
    live = d.serve_live(d.media.hls / "v0")
    d.open(live.url)
    cell = d.wait_for_cell("live.m3u8")

    d.check("it's live", cell.is_live)
    d.check(
        "it has no length", cell.video_driver.length == -1, cell.video_driver.length
    )
    _is_moving(d, cell)

    d.act(cell, "Play / Pause")
    d.wait_until(lambda: cell.video_params.is_paused, "it's paused")
    # the proxy only finds out at the next thing it has to pass on
    d.wait(3)

    held = _picture(cell)
    asked = live.asked
    d.wait(5)

    d.check("paused, the picture stays", _picture(cell) == held)
    d.check("and isn't blank", not _is_all_one_colour(held))
    d.check("and nothing more is fetched", live.asked == asked, live.asked - asked)
    d.shot("paused")

    d.act(cell, "Play / Pause")
    d.wait_until(lambda: not cell.video_params.is_paused, "it plays")
    _is_moving(d, cell)

    d.act(cell, "Play / Pause")
    d.wait_until(lambda: cell.video_params.is_paused, "it's paused again")
    d.act(cell, "Reload")
    d.wait_until(
        lambda: cell.is_playable and cell.video_params.is_paused,
        "reloaded, it's still paused",
    )
    d.act(cell, "Play / Pause")
    d.wait_until(lambda: not cell.video_params.is_paused, "and plays")
    _is_moving(d, cell)

    live.is_gone = True
    d.wait_until(lambda: cell.is_error, "gone, it gives up", timeout=60)
    d.check(
        "it says why",
        cell.status.last_error.title == "Not found",
        cell.status.last_error.title,
    )
    d.shot("gone")

    live.is_gone = False
    d.act(cell, "Reload")
    d.wait_until(lambda: cell.is_playable, "back, a reload plays it")
    d.check("and isn't paused", not cell.video_params.is_paused)
    _is_moving(d, cell)

    d.note("end", cell)
