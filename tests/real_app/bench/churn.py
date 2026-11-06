"""Open, close, reload and seek cells as fast as the app takes them while the others play, to catch
what goes wrong when things go away at the wrong moment. A scenario for tests.real_app.run.

Environment: DRIVER, MINUTES, SEED, MAX_CELLS, CLIPS (see common.clips_for).

Every few minutes it closes everything and looks at what's left, which is where a leak shows. Writes
churn.jsonl as it goes. A process that dies leaves its exit code, and a hang (nothing from the GUI
thread for HANG_S) leaves every thread's stack in hang.txt and exits with EXIT_HUNG.
"""

import faulthandler
import json
import os
import random
import threading
import time

from common import clips_for, nested, usage

DRIVER = os.environ["DRIVER"]
MINUTES = float(os.environ.get("MINUTES", "20"))
SEED = int(os.environ.get("SEED", "1"))
MAX_CELLS = int(os.environ.get("MAX_CELLS", "8"))
CLIPS = os.environ.get("CLIPS", "mix")

HANG_S = 45
EXIT_HUNG = 9
CHECKPOINT_EVERY_S = 300
SETTLE_S = 8
WAIT_MS = (5, 60)
# seeks and pauses are the common case, closing the whole lot now and then isn't
OPERATIONS = {
    "open": 14,
    "open_broken": 2,
    "close": 12,
    "reload": 6,
    "reload_all": 1,
    "seek": 25,
    "pause": 15,
    "zoom": 10,
    "resize": 10,
    "skip_frames": 5,
}

SETTINGS = {
    "player/video_driver": DRIVER,
    "playlist/warn_many_cells": False,
}


class Churn:
    def __init__(self, d):
        self.d = d
        self.random = random.Random(SEED)
        self.clips = clips_for(CLIPS, 32)
        self.broken = d.out / "broken.mp4"
        self.broken.write_bytes(b"this is not a video" * 1000)
        self.counts = dict.fromkeys(OPERATIONS, 0)
        self.log = (d.out / "churn.jsonl").open("a")
        self.beat = time.monotonic()
        self.is_skipping = False

        threading.Thread(target=self._watch, daemon=True, name="churn-watch").start()

    def _watch(self):
        while True:
            time.sleep(1)
            if time.monotonic() - self.beat > HANG_S:
                with (self.d.out / "hang.txt").open("w") as f:
                    faulthandler.dump_traceback(file=f, all_threads=True)
                os._exit(EXIT_HUNG)

    def _act(self, block, name):
        self.d.ctx.active_block = block
        self.d.ctx.actions[name].trigger()

    def _some_cell(self):
        cells = self.d.cells
        return self.random.choice(cells) if cells else None

    def open(self):
        if len(self.d.cells) < MAX_CELLS:
            self.d.player.process_arguments([str(self.random.choice(self.clips))])

    def open_broken(self):
        if len(self.d.cells) < MAX_CELLS:
            self.d.player.process_arguments([str(self.broken)])

    def close(self):
        if block := self._some_cell():
            self._act(block, "Close")

    def reload(self):
        if block := self._some_cell():
            self._act(block, "Reload")

    def reload_all(self):
        if block := self._some_cell():
            self._act(block, "Reload [ALL]")

    def seek(self):
        if block := self._some_cell():
            self._act(block, f"{self.random.randrange(1, 10) * 10}%")

    def pause(self):
        if block := self._some_cell():
            self._act(block, "Play / Pause")

    def zoom(self):
        if block := self._some_cell():
            name = self.random.choice(("Zoom In", "Zoom Out", "Zoom Reset"))
            self._act(block, name)

    def resize(self):
        self.d.player.resize(
            self.random.randrange(640, 1920), self.random.randrange(360, 1080)
        )

    def skip_frames(self):
        self.is_skipping = not self.is_skipping
        self.d.change_setting("player/mpv_skip_frames", self.is_skipping)

    def step(self):
        names = list(OPERATIONS)
        name = self.random.choices(names, weights=OPERATIONS.values())[0]
        self.counts[name] += 1
        getattr(self, name)()

    def write(self, kind, started):
        row = {
            "kind": kind,
            "minutes": round((time.monotonic() - started) / 60, 2),
            "cells": len(self.d.cells),
            "ops": sum(self.counts.values()),
            **usage(),
        }
        self.log.write(json.dumps(row) + "\n")
        self.log.flush()

    def checkpoint(self, started):
        """Everything closed and left to settle: what's still in use now is what stays."""

        for block in self.d.cells:
            self._act(block, "Close")
            self.pause_a_moment(0.05)

        deadline = time.monotonic() + 60
        while self.d.cells and time.monotonic() < deadline:
            self.pause_a_moment(0.2)

        self.pause_a_moment(SETTLE_S)
        self.write("empty", started)

    def pause_a_moment(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.beat = time.monotonic()
            nested(min(end - time.monotonic(), 1) + 0.001)


def scenario(d):
    d.player.resize(1280, 720)
    churn = Churn(d)
    started = time.monotonic()

    churn.checkpoint(started)
    next_checkpoint = started + CHECKPOINT_EVERY_S
    end = started + MINUTES * 60

    while time.monotonic() < end:
        churn.beat = time.monotonic()
        try:
            churn.step()
        except LookupError:
            pass
        nested(churn.random.randint(*WAIT_MS) / 1000)

        if time.monotonic() >= next_checkpoint:
            churn.write("busy", started)
            churn.checkpoint(started)
            next_checkpoint = time.monotonic() + CHECKPOINT_EVERY_S

    churn.checkpoint(started)
    d.check("finished", True, churn.counts)
