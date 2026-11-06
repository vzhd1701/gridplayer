"""Does switching frame skipping show? A scenario for tests.real_app.run, MPV drivers only.

Environment: DRIVER, CLIPS (see common.clips_for), CELLS, RESIZING.

Plays, then turns skipping on and off through the setting, again and again. For each switch: the longest
gap between finished frames in the following seconds, against the same state with no switch near it, and
how far a video's clock jumps. Saves a cell's picture right after each one, to look at. RESIZING=1 does
all this with the window changing size meanwhile. Writes hitch.json.
"""

import itertools
import json
import os
import statistics
import time

from common import clips_for, nested

DRIVER = os.environ.get("DRIVER", "mpv_hw")
CELLS = int(os.environ.get("CELLS", "4"))
CLIPS = os.environ.get("CLIPS", "h264_1080p60")
IS_RESIZING = os.environ.get("RESIZING") == "1"

SETTLE_S = 8
SWITCHES = 12
AFTER_SWITCH_S = 2
QUIET_S = 4
SHOT_DELAYS_S = (0.05, 0.25)
RESIZE_EVERY_S = 0.05
RESIZE_SIZES = ((1920, 1080), (1700, 960), (1500, 840))

SETTINGS = {
    "player/video_driver": DRIVER,
    "playlist/warn_many_cells": False,
}


def _gaps_ms(stamps, since, until) -> list[float]:
    inside = [t for t in stamps if since <= t <= until]
    return [(b - a) * 1000 for a, b in itertools.pairwise(inside)]


def _wait(d, seconds):
    """Runs the app, and changes the window's size as it goes when asked to."""

    end = time.perf_counter() + seconds
    index = 0
    while time.perf_counter() < end:
        if IS_RESIZING:
            index += 1
            d.player.resize(*RESIZE_SIZES[index % len(RESIZE_SIZES)])
        nested(min(RESIZE_EVERY_S, max(end - time.perf_counter(), 0.001)))


def _window(stamps_by_cell, since, until):
    gaps = [_gaps_ms(s, since, until) for s in stamps_by_cell.values()]
    span = until - since
    return {
        "worst_gap_ms": round(max((max(g) for g in gaps if g), default=0), 1),
        "fps": round(statistics.fmean(len(g) / span for g in gaps), 1),
    }


def _clock_jump_ms(block, wall_since, time_since) -> float:
    return abs((block.time - time_since) - (time.perf_counter() - wall_since) * 1000)


def scenario(d):
    from gridplayer.mpv_player import renderer

    stamps = {}
    publish = renderer.RenderedVideo.publish

    def counted(self):
        stamps.setdefault(id(self), []).append(time.perf_counter())
        publish(self)

    renderer.RenderedVideo.publish = counted

    d.player.resize(*RESIZE_SIZES[0])
    d.open(*clips_for(CLIPS, CELLS))
    d.wait_until(
        lambda: len(d.cells) == CELLS and all(b.is_playable for b in d.cells),
        "all of them play",
        60,
    )
    nested(SETTLE_S)

    block = d.cells[0]
    results = []
    is_skipping = False

    for index in range(SWITCHES):
        # the stretch before it, in the state it's leaving, with no switch near it
        quiet_start = time.perf_counter()
        _wait(d, QUIET_S)
        quiet = _window(stamps, quiet_start, time.perf_counter())

        time_before, wall_before = block.time, time.perf_counter()
        is_skipping = not is_skipping
        d.change_setting("player/mpv_skip_frames", is_skipping)
        at = time.perf_counter()

        for shot, delay in enumerate(SHOT_DELAYS_S):
            _wait(d, delay)
            picture = block.video_driver.grab()
            picture.save(str(d.out / f"switch{index:02}_{shot}.png"))

        _wait(d, AFTER_SWITCH_S)
        results.append(
            {
                "to": "on" if is_skipping else "off",
                "before": quiet,
                "after": _window(stamps, at, time.perf_counter()),
                "clock_off_ms": round(_clock_jump_ms(block, wall_before, time_before)),
            }
        )

    summary = {
        "driver": DRIVER,
        "cells": CELLS,
        "resizing": IS_RESIZING,
        "quiet_worst_gap_ms": max(r["before"]["worst_gap_ms"] for r in results),
        "after_switch_worst_gap_ms": max(r["after"]["worst_gap_ms"] for r in results),
        "switches": results,
    }
    (d.out / "hitch.json").write_text(json.dumps(summary, indent=1))
    d.check("finished", True, {k: v for k, v in summary.items() if k != "switches"})
