"""How exact a seek is on MPV, by the setting and by what the seek is for, on a file with
a key frame every 6 s. Fast, a seek lands on the key frame before it: 3 s on from 19 s
was back at 18 s, and pressed again, 18 s again. So one forwards that lands where it was
or behind goes on exactly. Not by so much to the key frame after it: with none after it,
before the end, mpv went back to the start."""

import time

from gridplayer.params.static import SeekPrecision
from gridplayer.settings import Settings

SETTINGS = {"player/video_driver": "mpv_hw"}


def _lands(d, cell, at_s, what):
    """Where mpv is once it has stopped moving, against where it should be. And the
    cell told so, which a frame step goes from: mpv says it a moment before."""

    player = cell.video_driver.video_driver._player
    started = time.monotonic()

    is_there = d.wait_until(
        lambda: (
            # mpv says it's where it's going as soon as it's asked
            not player.mpv.seeking
            and player.mpv.time_pos is not None
            and abs(player.mpv.time_pos - at_s) < 0.05
            and abs(cell.time / 1000 - at_s) < 0.05
        ),
        f"{what}: at {at_s} s",
        timeout=10,
    )
    d.note(
        f"{what}: {player.mpv.time_pos} s, after {time.monotonic() - started:.2f} s",
        cell,
    )

    return is_there


def _start_at(d, cell, at_s):
    cell.seek(int(at_s * 1000))
    _lands(d, cell, at_s, "from")


def scenario(d):
    d.open(d.media.fragmented / "video.mp4")
    cell = d.wait_for_cell("video.mp4")
    cell.set_pause(True)
    d.wait_until(lambda: cell.video_params.is_paused, "paused")

    length_s = cell.video_driver.length / 1000
    one_percent_s = length_s / 100
    d.check("3 s to a press of 1%", abs(one_percent_s - 3) < 0.1, length_s)

    precision = Settings().get("player/mpv_seek_precision")
    d.check(
        "by hand fast, marks exact by default",
        precision == SeekPrecision.EXACT_MARKS,
        precision,
    )

    _start_at(d, cell, 19)
    cell.manual_seek("seek_shift_percent", 1)
    d.check(
        "3 s on with no key frame between is exact",
        _lands(d, cell, 22, "on from 19 s"),
    )

    cell.manual_seek("seek_shift_percent", 1)
    d.check(
        "3 s on past a key frame lands on it, short",
        _lands(d, cell, 24, "on from 22 s"),
    )

    cell.manual_seek("seek_shift_percent", -1)
    d.check(
        "3 s back is the key frame before it", _lands(d, cell, 18, "back from 24 s")
    )

    # 153 s
    cell.manual_seek("seek_percent", 0.51)
    d.check("the bar is fast too", _lands(d, cell, 150, "on the bar"))

    # the last key frame is at 294 s
    _start_at(d, cell, 295)
    cell.manual_seek("seek_shift_percent", 1)
    d.check(
        "on from the last key frame stays on",
        _lands(d, cell, 298, "on from 295 s"),
    )

    cell.manual_seek("seek", 47000)
    d.check("a time typed in is exact", _lands(d, cell, 47, "typed in"))

    # Exact
    d.change_setting("player/mpv_seek_precision", SeekPrecision.EXACT)
    _start_at(d, cell, 19)
    cell.manual_seek("seek_shift_percent", 1)
    d.check(
        "set to exact, by hand is exact", _lands(d, cell, 22, "exact, on from 19 s")
    )

    # Fast
    d.change_setting("player/mpv_seek_precision", SeekPrecision.FAST)
    cell.manual_seek("seek", 40000)
    d.check("set to fast, a mark lands short", _lands(d, cell, 36, "fast, typed in"))

    cell.manual_seek("next_frame")
    d.check("a frame step is exact still", _lands(d, cell, 36.04, "fast, frame step"))

    d.note("end", cell)
