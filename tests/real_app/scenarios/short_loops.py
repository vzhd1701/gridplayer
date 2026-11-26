"""Short files going round on their own: a clip of 45 frames reaches its
last one (#129), and, on MPV, a sound of 1 s plays to its end every time.

The frames are seen by grabbing the cell over and over, and a grab can miss
a frame: a slow machine misses frames of 40 ms now and then. #129 cut the
same frames off every pass, so one pass reaching the end is enough. On MPV,
which shows the last frame whole, that is the last one. VLC shows it for 10
to 20 ms of its 40 before the clip starts again, which a grab misses on half
the passes or so: there it is the frame before it.

Not the sound on VLC: on Windows it is cut to about 100 ms of each pass,
left as it is (docs/findings/KNOWN_ISSUES.md).
"""

import time
from itertools import pairwise

from PyQt6.QtGui import QColor

from gridplayer.settings import Settings
from tests.real_app.media import frame_shown
from tests.real_app.scenarios.pixel_shape import _grab

CLIP_FRAMES = 45

WATCH_S = 8

# the sound's time going back this much: round again
WRAP_MS = 150


def scenario(d):
    _clip(d)

    if _is_mpv():
        _sound(d)


def _clip(d):
    d.open(d.media.short_clip)
    b = d.wait_for_cell("clip.mp4")

    passes, seen, last = [], [], None
    end = time.perf_counter() + WATCH_S
    while time.perf_counter() < end:
        d.pump(0.005)
        frame = _shown(b)
        if not 0 <= frame < CLIP_FRAMES or frame == last:
            continue
        if last is not None and frame < last - CLIP_FRAMES // 2:
            passes.append(seen)
            seen = []
        seen.append(frame)
        last = frame

    # the first starts late, and the run ends in the middle of one
    whole = passes[1:]
    d.check("the clip goes round", len(whole) >= 2, len(passes))
    end = CLIP_FRAMES - 1 if _is_mpv() else CLIP_FRAMES - 2
    d.check(
        f"the clip reaches frame {end + 1} of {CLIP_FRAMES}",
        any(max(seen) >= end for seen in whole),
        [max(seen) for seen in passes],
    )

    d.act(b, "Close")
    d.wait_until(lambda: not d.cells, "the clip is closed")


def _sound(d):
    d.open(d.media.short_sound)
    b = d.wait_for_cell("sound.wav")
    b.audio.set_muted(True)

    # How long each pass takes: MPV says the time of a sound only every 200 ms
    # or so, which can leave the last word on a pass 400 ms short of its end.
    # libmpv 0.37 counts the sound still queued from a pass as before the
    # next: its time goes from below 0, said as 0, to half a second or so,
    # then round. Only the time going back says it went round.
    length = b.video_driver.length
    wraps, last = [], 0
    end = time.perf_counter() + WATCH_S
    while time.perf_counter() < end:
        d.pump(0.01)
        now = b.time
        if now < last - WRAP_MS:
            wraps.append(time.perf_counter())
        last = now

    passes_ms = [round((later - sooner) * 1000) for sooner, later in pairwise(wraps)]
    d.check("the sound goes round", len(passes_ms) >= 2, passes_ms)
    d.check(
        "every pass of the sound plays to its end",
        all(ms >= length * 0.9 for ms in passes_ms),
        (length, passes_ms),
    )


def _is_mpv() -> bool:
    driver = Settings().get("player/video_driver")
    return str(getattr(driver, "value", driver)).startswith("mpv")


def _shown(b) -> int:
    image = _grab(b)
    return frame_shown(QColor(image.pixel(image.width() // 2, image.height() // 2)))
