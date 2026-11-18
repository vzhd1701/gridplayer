"""Scenario: how heavy a window resize is with many videos playing, as a drag
makes it, a step a mouse move. Each step is the window made a size and every
event that brings until the app is idle again, timed; then the frame's wait,
the next mouse move 16 ms on. A drag is smooth when a step fits in that.

DRIVER, CLIP (a name of common.clips_for), CELLS, STEPS, STEP_MS (0: the
next step at once), PROFILE=1 for the heaviest calls of the drag,
RESIZE_INTERVAL=MS for how often VLC's hardware cells follow, SHOTS=10,30 for
the window as shown after those steps, AWAY=1 / ON_SCREEN=1 (see away.py).
Leaves resize.json in the run's folder.

What it can't show: a drag by hand. The window resized here doesn't go
through Windows' own sizing loop, and what a drag felt like with Hardware VLC
wasn't in these numbers (docs/findings/VLC.md, 10.36).

    PYTHONPATH=.;tests/real_app/bench DRIVER=vlc_hw CELLS=12 AWAY=1 \\
        REAL_APP_QT_PLATFORM=windows uv run --with psutil python -m tests.real_app.run \\
        tests/real_app/bench/resize.py --out build/bench/resize
"""

import cProfile
import io
import json
import os
import pstats
import statistics
import time
from pathlib import Path

from common import clips_for
from PyQt5.QtWidgets import QApplication

DRIVER = os.environ.get("DRIVER", "vlc_hw")
CLIP = os.environ.get("CLIP", "h264_1080p30")
CELLS = int(os.environ.get("CELLS", "12"))
STEPS = int(os.environ.get("STEPS", "120"))
# a mouse move a frame of a 60 Hz screen
STEP_MS = int(os.environ.get("STEP_MS", "16"))
# SHOTS=10,30: the window right after those steps, and settled
SHOTS = {int(n) for n in os.environ.get("SHOTS", "").split(",") if n}

SETTINGS = {
    "player/video_driver": DRIVER,
    "player/mpv_output": os.environ.get("MPV_OUTPUT", "readback"),
    "playlist/warn_many_cells": False,
    "video_defaults/initial_state": "playing",
}

if os.environ.get("AWAY") == "1":
    import away

    away.install(Path(os.environ["GP_BENCH_DIR"]))
elif os.environ.get("ON_SCREEN") == "1":
    import away

    away.install_on_screen()


def _try_interval():
    """RESIZE_INTERVAL=MS: VLC's hardware cells following a resize that often."""

    interval = os.environ.get("RESIZE_INTERVAL")
    if interval is None:
        return

    from gridplayer.widgets import video_frame_vlc_hw, video_frame_vlc_hw_sp

    video_frame_vlc_hw.VideoFrameVLCHW.resize_view_interval_ms = int(interval)
    video_frame_vlc_hw_sp.VideoFrameVLCHWSP.resize_view_interval_ms = int(interval)


_try_interval()


def _capturer():
    """Windows: how the window is taken a picture of, for SHOTS. On screen,
    as shown there, mid-resize too."""

    import away

    return away.capture_screen if os.environ.get("ON_SCREEN") == "1" else away.capture


def _sizes():
    """A corner dragged in and out: 1920x1080 down to 1280x720 and back."""

    half = STEPS // 2
    for i in range(STEPS):
        k = i / half if i < half else (STEPS - i) / half
        yield round(1920 - 640 * k), round(1080 - 360 * k)


def _settle(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def scenario(d):
    app = QApplication.instance()
    d.player.resize(1920, 1080)
    d.open(*clips_for(CLIP, CELLS))
    d.wait_until(lambda: len(d.cells) == CELLS, "all cells", 60)
    d.wait_until(lambda: all(c.is_video_initialized for c in d.cells), "all loaded", 90)
    _settle(app, 3)

    profile = cProfile.Profile() if os.environ.get("PROFILE") == "1" else None
    capture = _capturer() if SHOTS else None
    steps_ms = []
    late_ms = []
    started = time.monotonic()
    if profile:
        profile.enable()
    for size in _sizes():
        step_start = time.monotonic()
        d.player.resize(*size)
        app.processEvents()
        steps_ms.append((time.monotonic() - step_start) * 1000)
        if SHOTS and len(steps_ms) in SHOTS:
            capture(d.player, d.out / f"step_{len(steps_ms):03d}.png")

        # the rest of the frame, the app left to its own events
        due = step_start + STEP_MS / 1000
        while time.monotonic() < due:
            app.processEvents()
            time.sleep(0.001)
        late_ms.append(max(0.0, (time.monotonic() - due) * 1000))
    if profile:
        profile.disable()
    drag_s = time.monotonic() - started

    _settle(app, 1)
    if SHOTS:
        capture(d.player, d.out / "settled.png")

    def summary(values):
        ordered = sorted(values)
        return {
            "mean": round(statistics.fmean(values), 1),
            "p50": round(ordered[len(ordered) // 2], 1),
            "p95": round(ordered[int(len(ordered) * 0.95)], 1),
            "max": round(ordered[-1], 1),
        }

    result = {
        "driver": DRIVER,
        "clip": CLIP,
        "cells": CELLS,
        "steps": STEPS,
        "drag_s": round(drag_s, 2),
        # as long as the drag would take at a frame a step
        "ideal_s": round(STEPS * STEP_MS / 1000, 2),
        "step_ms": summary(steps_ms),
        "late_ms": summary(late_ms),
    }
    if profile:
        out = io.StringIO()
        pstats.Stats(profile, stream=out).sort_stats("cumulative").print_stats(45)
        (d.out / "profile.txt").write_text(out.getvalue(), encoding="utf-8")
        out = io.StringIO()
        pstats.Stats(profile, stream=out).sort_stats("tottime").print_stats(30)
        (d.out / "profile_self.txt").write_text(out.getvalue(), encoding="utf-8")

    (d.out / "resize.json").write_text(json.dumps(result, indent=1))
    d._step("resize", info=result)
