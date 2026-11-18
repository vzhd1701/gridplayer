"""What a multi-process mpv driver would get, as a prototype, on the app's real renderer and
player classes, with the window a plain grid of widgets painted the way the app paints them.

    mp_bench.py CLIP CELLS PROCS [HWDEC]

PROCS 0: everything in this process, as the driver is now. PROCS k: k worker processes each with
a render thread, reading back straight into shared memory, the GUI process only painting. There
is no copy more than in-process: the readback's buffer is the shared memory.

Prints a JSON line.
"""

import ctypes
import json
import math
import os
import struct
import subprocess
import sys
import threading
import time
from multiprocessing import shared_memory
from types import SimpleNamespace

SLOTS = 3
HEADER = 64
WINDOW = (1920, 1080)


def slot_view(shm, size, index):
    width, height = size
    count = width * height * 4
    return (ctypes.c_ubyte * count).from_buffer(shm.buf, HEADER + index * count)


def fit(cell, source=(16, 9)):
    scale = min(cell[0] / source[0], cell[1] / source[1])
    return max(round(source[0] * scale) & ~1, 2), max(round(source[1] * scale) & ~1, 2)


# -- the render side, in a worker or in this process


def run_renderers(clip, jobs, hwdec):
    """Players and a render thread for these (shared memory name, render size). Qt's event
    loop is the caller's."""

    from PyQt5.QtCore import QObject, Qt, pyqtSlot

    from gridplayer.mpv_player.libmpv import load_mpv
    from gridplayer.mpv_player.player import MpvPlayer
    from gridplayer.mpv_player.renderer import FrameSlot, RenderedVideo, VideoRenderer

    module = load_mpv()

    class Slot(FrameSlot):
        def __init__(self, view, size):
            super().__init__()
            self.view = view
            self.width, self.height = size

        def writable(self, width, height):
            return self.view

    class SharedVideo(RenderedVideo):
        def __init__(self, player, shm, size):
            super().__init__(player)
            self.shm = shm
            self.slots = [Slot(slot_view(shm, size, i), size) for i in range(SLOTS)]
            self.index = 0
            self.seq = 0
            self.back = self.slots[0]

        def publish(self):
            self.seq += 1
            struct.pack_into("<QQ", self.shm.buf, 0, self.index, self.seq)
            self.index = (self.index + 1) % SLOTS
            self.back = self.slots[self.index]

    class Player(MpvPlayer):
        def _read_media(self):
            self._is_media_read = True

    class Starter(QObject):
        def __init__(self, player, box):
            super().__init__()
            self.player = player
            self.box = box

        @pyqtSlot()
        def go(self):
            self.player.start(self.box)

    renderer = VideoRenderer(module)
    renderer._platform = "xcb"

    keep = [renderer]
    for name, size in jobs:
        shm = shared_memory.SharedMemory(name=name, track=False)
        video_options = SimpleNamespace(
            is_paused=False, current_position=0, is_start_random=False
        )
        media = SimpleNamespace(
            video=video_options,
            uri=clip,
            is_audio_only=False,
            is_live=False,
            initial_time=0,
            length=None,
        )
        player = Player(module, media, hwdec, renderer.wake)
        player.set_render_size(size)
        video = SharedVideo(player, shm, size)
        starter = Starter(player, size)
        player.render_context_ready.connect(
            starter.go, Qt.ConnectionType.QueuedConnection
        )
        keep += [shm, player, video, starter]
        renderer.add(video)

    renderer.start()
    return keep


def worker(config):
    from PyQt5.QtCore import QCoreApplication

    app = QCoreApplication(["worker"])
    keep = run_renderers(
        config["clip"], [tuple(j) for j in config["jobs"]], config["hwdec"]
    )
    app.exec()
    del keep


# -- the window


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def tree_cpu_ticks():
    tree = [os.getpid()]
    for pid in tree:
        for task in (
            os.listdir(f"/proc/{pid}/task")
            if os.path.isdir(f"/proc/{pid}/task")
            else []
        ):
            tree.extend(
                int(c) for c in read(f"/proc/{pid}/task/{task}/children").split()
            )
    rows = {}
    for pid in tree:
        stat = read(f"/proc/{pid}/stat")
        if stat:
            fields = stat[stat.rindex(")") + 2 :].split()
            rows[pid] = int(fields[11]) + int(fields[12])
    return rows, tree


def thread_ticks(pid, tid):
    stat = read(f"/proc/{pid}/task/{tid}/stat")
    fields = stat[stat.rindex(")") + 2 :].split()
    return int(fields[11]) + int(fields[12])


def main():
    clip, cells, procs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    hwdec = sys.argv[4] if len(sys.argv) > 4 else "auto"
    settle = float(os.environ.get("SETTLE", "8"))
    measure = float(os.environ.get("MEASURE", "20"))

    from PyQt5.QtCore import QEventLoop, QRectF, Qt, QTimer
    from PyQt5.QtGui import QImage, QPainter
    from PyQt5.QtWidgets import QApplication, QGridLayout, QWidget

    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
    _app = QApplication(["bench", "-platform", "xcb"])

    columns = math.ceil(math.sqrt(cells))
    rows = math.ceil(cells / columns)
    cell_size = (WINDOW[0] // columns, WINDOW[1] // rows)
    size = fit(cell_size)

    frame_bytes = size[0] * size[1] * 4
    memories = [
        shared_memory.SharedMemory(
            create=True, size=HEADER + SLOTS * frame_bytes, track=False
        )
        for _ in range(cells)
    ]
    jobs = [(m.name, size) for m in memories]

    class Surface(QWidget):
        def __init__(self, shm):
            super().__init__()
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
            self.shm = shm
            self.seq = 0
            self.index = 0
            self.images = [
                QImage(
                    slot_view(shm, size, i),
                    size[0],
                    size[1],
                    size[0] * 4,
                    QImage.Format.Format_RGB32,
                )
                for i in range(SLOTS)
            ]
            self.source = QRectF(0, 0, size[0], size[1])

        def poll(self):
            index, seq = struct.unpack_from("<QQ", self.shm.buf, 0)
            if seq != self.seq:
                self.seq = seq
                self.index = index
                self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
            painter.drawImage(
                QRectF(0, 0, self.width(), self.height()),
                self.images[self.index],
                self.source,
            )
            painter.end()

    window = QWidget()
    grid = QGridLayout(window)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(0)
    surfaces = []
    for i, shm in enumerate(memories):
        surface = Surface(shm)
        surfaces.append(surface)
        grid.addWidget(surface, i // columns, i % columns)
    window.resize(*WINDOW)
    window.show()

    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(16)
    timer.timeout.connect(lambda: [s.poll() for s in surfaces])
    timer.start()

    children = []
    _keep = None
    if procs <= 0:
        # below zero: this process, with that many render threads
        threads = max(1, -procs)
        _keep = [run_renderers(clip, jobs[k::threads], hwdec) for k in range(threads)]
    else:
        for k in range(procs):
            config = {"clip": clip, "jobs": jobs[k::procs], "hwdec": hwdec}
            children.append(
                subprocess.Popen(
                    [sys.executable, __file__, "--worker", json.dumps(config)],
                    stdout=subprocess.DEVNULL,
                )
            )

    def nested(seconds):
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    nested(settle)

    late = []
    last = [None]

    def tick():
        now = time.perf_counter()
        if last[0] is not None:
            late.append((now - last[0]) * 1000 - 10)
        last[0] = now

    probe = QTimer()
    probe.setTimerType(Qt.TimerType.PreciseTimer)
    probe.setInterval(10)
    probe.timeout.connect(tick)
    probe.start()

    py_late = []
    running = [True]

    def sleeper():
        while running[0]:
            start = time.perf_counter()
            time.sleep(0.005)
            py_late.append((time.perf_counter() - start - 0.005) * 1e6)

    threading.Thread(target=sleeper, daemon=True).start()

    available = lambda: int(read("/proc/meminfo").split("MemAvailable:")[1].split()[0])  # noqa: E731
    rc6 = lambda: int(read("/sys/class/drm/card0/power/rc6_residency_ms", "0"))  # noqa: E731
    clk = os.sysconf("SC_CLK_TCK")

    nested(0.3)
    late.clear()
    py_late.clear()

    t0 = time.monotonic()
    seq0 = [struct.unpack_from("<QQ", m.buf, 0)[1] for m in memories]
    ticks0, _ = tree_cpu_ticks()
    gui0 = thread_ticks(os.getpid(), os.getpid())
    rc0 = rc6()

    nested(measure)

    span = time.monotonic() - t0
    seq1 = [struct.unpack_from("<QQ", m.buf, 0)[1] for m in memories]
    ticks1, tree = tree_cpu_ticks()
    gui1 = thread_ticks(os.getpid(), os.getpid())
    rc1 = rc6()
    running[0] = False

    fps = [(b - a) / span for a, b in zip(seq0, seq1)]
    late.sort()
    py_late.sort()
    pss = 0
    for pid in tree:
        for line in read(f"/proc/{pid}/smaps_rollup").splitlines():
            if line.startswith("Pss:"):
                pss += int(line.split()[1])

    per_process = {
        pid: round(
            (ticks1.get(pid, 0) - ticks0.get(pid, ticks1.get(pid, 0)))
            / clk
            / span
            * 100,
            1,
        )
        for pid in tree
    }

    print(
        json.dumps(
            {
                "clip": os.path.basename(clip),
                "cells": cells,
                "procs": procs,
                "render_size": size,
                "fps_mean": round(sum(fps) / len(fps), 1),
                "fps_min": round(min(fps), 1),
                "cpu_total": round(sum(per_process.values()), 1),
                "cpu_parent": per_process[os.getpid()],
                "cpu_gui_thread": round((gui1 - gui0) / clk / span * 100, 1),
                "cpu_workers": [v for k, v in per_process.items() if k != os.getpid()],
                "gt_busy": round(100 - (rc1 - rc0) / (span * 1000) * 100, 1),
                "pss_mb": round(pss / 1024, 1),
                "avail_mb": round(available() / 1024),
                "gui_late_p95": round(late[int(len(late) * 0.95)], 2) if late else None,
                "gui_late_max": round(late[-1], 2) if late else None,
                "py_late_p95_us": round(py_late[int(len(py_late) * 0.95)])
                if py_late
                else None,
            }
        ),
        flush=True,
    )

    for child in children:
        child.kill()
    for memory in memories:
        memory.unlink()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        worker(json.loads(sys.argv[2]))
    else:
        main()
