"""Scrubbing with seek sync on (#164): two H.264 clips playing, and the bar of
one dragged back and forth, a seek for each move of the mouse. Neither stops:
both end up where the last seek went and play on from there, the picture
moving. On MPV the two play on together; VLC can leave them up to a second
apart now and then, which is only written down.

Bursts as a drag makes them: quick (a move every 10 ms), all at once (moves
coming faster than the app takes them) and slow (a move every 150 ms); by
timecode and by percent, from either cell.
"""

import math
import os

from gridplayer.settings import Settings
from tests.real_app.scenarios.pixel_shape import _grab

# how far apart the two may be once both have landed, and from the aim
CLOSE_MS = 700

ROUNDS = int(os.environ.get("SCRUB_ROUNDS", "3"))

PLAY_ON_S = 5


def scenario(d):
    a_clip, b_clip = d.media.clips[0], d.media.clips[1]
    d.open(a_clip, b_clip)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")

    for mode in ("Seek Sync (Timecode)", "Seek Sync (Percent)"):
        d.act(a, mode)

        for n in range(ROUNDS):
            for burst in (_quick, _at_once, _slow):
                dragged, other = (a, b) if n % 2 == 0 else (b, a)
                aim = burst(d, dragged, phase=n)
                _both_play_on(d, dragged, other, aim, f"{mode}, {burst.__name__} {n}")

    d.act(a, "Seek Sync (Disabled)")


def _positions(count, phase):
    """Back and forth across most of the bar, as a hand drags it."""

    return [0.5 + 0.4 * math.sin(phase + 3 * math.pi * i / count) for i in range(count)]


def _quick(d, block, phase):
    positions = _positions(60, phase)
    for position in positions:
        block.manual_seek("seek_percent", position)
        d.pump(0.01)
    return positions[-1]


def _at_once(d, block, phase):
    positions = _positions(40, phase)
    for position in positions:
        block.manual_seek("seek_percent", position)
    return positions[-1]


def _slow(d, block, phase):
    positions = _positions(10, phase)
    for position in positions:
        block.manual_seek("seek_percent", position)
        d.pump(0.15)
    return positions[-1]


def _both_play_on(d, dragged, other, aim, what):
    aim_ms = int(aim * dragged.video_driver.length)
    cells = (dragged, other)

    # A cell can sit where it landed for a second or two while it decodes its
    # way there, a stale seek of the burst landing on the way now and then.
    # Stopped is still sitting there after this long.
    def played_on(block):
        return aim_ms + 500 <= block.time <= aim_ms + PLAY_ON_S * 1000 + CLOSE_MS

    d.wait_until(
        lambda: all(played_on(block) for block in cells),
        f"{what}: both play on from where the last seek went ({aim_ms})",
        timeout=PLAY_ON_S,
    )

    before = {block: (block.time, _picture(block)) for block in cells}
    d.wait(1)

    for block in cells:
        name = block.title
        time_before, picture_before = before[block]
        # round the end, maybe
        played = (block.time - time_before) % block.video_driver.length

        d.check(
            f"{what}: {name} plays",
            not block.video_params.is_paused and not block.is_error,
            d.state(block),
        )
        d.check(
            f"{what}: {name}'s time goes on",
            500 <= played <= 1500,
            (time_before, block.time),
        )
        d.check(
            f"{what}: {name}'s picture moves",
            _picture(block) != picture_before,
        )

    # VLC can come out of a quick drag up to a second later in one cell than
    # in the other (docs/findings/KNOWN_ISSUES.md), so they play on apart
    gap = abs(dragged.time - other.time)
    if _is_mpv():
        d.check(f"{what}: the two together", gap <= CLOSE_MS, gap)
    else:
        d._step(f"{what}: the two apart by", gap_ms=gap)


def _is_mpv() -> bool:
    driver = Settings().get("player/video_driver")
    return str(getattr(driver, "value", driver)).startswith("mpv")


def _picture(block):
    return _grab(block)
