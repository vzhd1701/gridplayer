"""A grid left playing, sampled once a minute. A scenario for tests.real_app.run.

Environment: DRIVER, CELLS, MINUTES, CLIPS (see common.clips_for). Writes soak.jsonl as it goes,
and soak.json at the end with how much memory grew per hour, leaving out the first minutes.
"""

import json
import os
import time

from common import clips_for, nested, usage
from PyQt6.QtCore import QElapsedTimer, QTimer

DRIVER = os.environ["DRIVER"]
CELLS = int(os.environ.get("CELLS", "9"))
MINUTES = float(os.environ.get("MINUTES", "60"))
CLIPS = os.environ.get("CLIPS", "mix")

# not a whole number of the clips' 60 s, or a video that's looping looks stopped
SAMPLE_S = 67
SETTLED_AFTER_MIN = 5
GUI_TICK_MS = 20

SETTINGS = {
    "player/video_driver": DRIVER,
    "playlist/warn_many_cells": False,
}


class GuiLateness:
    def __init__(self):
        self.worst_ms = 0.0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer()
        self._timer.setInterval(GUI_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        late = self._clock.restart() - GUI_TICK_MS
        self.worst_ms = max(self.worst_ms, late)

    def take(self) -> float:
        worst, self.worst_ms = self.worst_ms, 0.0
        return worst


def _slope_per_hour(rows, key) -> float | None:
    points = [
        (r["minutes"], r[key])
        for r in rows
        if r["minutes"] >= SETTLED_AFTER_MIN and r.get(key) is not None
    ]
    if len(points) < 2:
        return None

    mean_x = sum(p[0] for p in points) / len(points)
    mean_y = sum(p[1] for p in points) / len(points)
    over = sum((x - mean_x) * (y - mean_y) for x, y in points)
    under = sum((x - mean_x) ** 2 for x, _y in points)

    return round(over / under * 60, 1)


def _count_frames() -> list[int]:
    """Frames finished so far, for MPV; stays at 0 for VLC, which has no such place."""

    frames = [0]

    if not DRIVER.startswith("mpv"):
        return frames

    from gridplayer.mpv_player import renderer

    publish = renderer.RenderedVideo.publish

    def counted(self):
        frames[0] += 1
        publish(self)

    renderer.RenderedVideo.publish = counted

    return frames


def scenario(d):
    d.player.resize(1920, 1080)
    d.open(*clips_for(CLIPS, CELLS))
    d.wait_until(
        lambda: len(d.cells) == CELLS and all(b.is_playable for b in d.cells),
        "all of them play",
        120,
    )

    frames = _count_frames()
    gui = GuiLateness()
    rows = []
    started = time.monotonic()

    with (d.out / "soak.jsonl").open("w") as log:
        while time.monotonic() - started < MINUTES * 60:
            times = [b.time for b in d.cells]
            frames_before = frames[0]
            sampled_at = time.monotonic()
            nested(SAMPLE_S)
            span = time.monotonic() - sampled_at
            row = {
                "minutes": round((time.monotonic() - started) / 60, 2),
                "cells": len(d.cells),
                "fps_per_cell": round((frames[0] - frames_before) / span / CELLS, 1),
                "still": sum(a == b.time for a, b in zip(times, d.cells, strict=False)),
                "errors": sum(b.is_error for b in d.cells),
                "gui_worst_ms": gui.take(),
                **usage(),
            }
            rows.append(row)
            log.write(json.dumps(row) + "\n")
            log.flush()

    summary = {
        "driver": DRIVER,
        "cells": CELLS,
        "minutes": MINUTES,
        "first": rows[0],
        "last": rows[-1],
        "uss_mb_per_hour": _slope_per_hour(rows, "uss_mb"),
        "vram_mb_per_hour": _slope_per_hour(rows, "vram_mb"),
        "available_mb_per_hour": _slope_per_hour(rows, "available_mb"),
        "threads_per_hour": _slope_per_hour(rows, "threads"),
        "handles_per_hour": _slope_per_hour(rows, "handles"),
        "gui_worst_ms": max(r["gui_worst_ms"] for r in rows),
        "most_still": max(r["still"] for r in rows),
        "most_errors": max(r["errors"] for r in rows),
    }
    (d.out / "soak.json").write_text(json.dumps(summary, indent=1))
    d.check("finished", True, summary)
