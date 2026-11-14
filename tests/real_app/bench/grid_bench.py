"""A grid of the same clip in the real app, measured over a stretch of steady playing.

A scenario for tests.real_app.run, run by run.py. Environment: DRIVER CLIP CELLS, optional
SETTLE MEASURE EXP SPY LOAD_TIMEOUT PLAYERS BENCH_MEDIA AWAY. README.md says what they take.
Writes bench.json to the run's folder. Never fails a run for a number: a run that didn't
load says so in the numbers.
"""

import ctypes
import json
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

from common import clips_for, nested, source_fps
from PyQt5.QtCore import Qt, QTimer

from tests.real_app.composed import is_direct

DRIVER = os.environ["DRIVER"]
CLIP = os.environ["CLIP"]
CELLS = int(os.environ["CELLS"])
SETTLE = float(os.environ.get("SETTLE", "8"))
MEASURE = float(os.environ.get("MEASURE", "20"))
LOAD_TIMEOUT = float(os.environ.get("LOAD_TIMEOUT", "60"))
EXP = dict(
    [*item.split("="), "1"][:2] for item in os.environ.get("EXP", "").split(",") if item
)
SPY = os.environ.get("SPY", "")
BENCH_DIR = Path(os.environ["GP_BENCH_DIR"])
IS_WIN = sys.platform == "win32"
IS_AWAY = IS_WIN and os.environ.get("AWAY") == "1"
# on the user's own screen, never activated: what reaching it costs included
IS_ON_SCREEN = IS_WIN and os.environ.get("ON_SCREEN") == "1"
CLK = 100 if IS_WIN else os.sysconf("SC_CLK_TCK")

SETTINGS = {
    "player/video_driver": DRIVER,
    "player/video_driver_players": int(os.environ.get("PLAYERS", "4")),
    "player/mpv_skip_frames": "skip" in EXP,
    "player/mpv_cpu_decoding": "on" if "cpu" in EXP else "off",
    "player/mpv_output": os.environ.get("MPV_OUTPUT", "readback"),
    "player/mpv_picture_quality": EXP.get("quality", "auto"),
    "playlist/warn_many_cells": False,
}


if IS_AWAY:
    import away

    away.install(Path(os.environ["GP_BENCH_DIR"]))
elif IS_ON_SCREEN:
    import away

    away.install_on_screen()


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * q))]


def summary(values):
    if not values:
        return None
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "p50": round(pct(values, 0.5), 3),
        "p95": round(pct(values, 0.95), 3),
        "p99": round(pct(values, 0.99), 3),
        "max": round(max(values), 3),
    }


# -- what the system says


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def process_tree():
    tree = [os.getpid()]
    for parent in tree:
        try:
            tasks = os.listdir(f"/proc/{parent}/task")
        except OSError:
            continue
        for task in tasks:
            children = read(f"/proc/{parent}/task/{task}/children", "")
            tree.extend(int(c) for c in children.split())
    return tree


def threads_of(pid):
    rows = {}
    try:
        tasks = os.listdir(f"/proc/{pid}/task")
    except OSError:
        return rows
    for tid in tasks:
        stat = read(f"/proc/{pid}/task/{tid}/stat")
        if not stat:
            continue
        comm = stat[stat.index("(") + 1 : stat.rindex(")")]
        fields = stat[stat.rindex(")") + 2 :].split()
        rows[int(tid)] = (comm, int(fields[11]) + int(fields[12]))
    return rows


def mem_of(pid):
    text = read(f"/proc/{pid}/smaps_rollup", "")
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] in {"Rss:", "Pss:", "Private_Dirty:", "Pss_Shmem:"}:
            out[parts[0][:-1]] = int(parts[1])
    return out


def procs_named(*names):
    total = 0
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            stat = read(f"/proc/{entry}/stat")
            if stat:
                comm = stat[stat.index("(") + 1 : stat.rindex(")")]
                if comm in names:
                    fields = stat[stat.rindex(")") + 2 :].split()
                    total += int(fields[11]) + int(fields[12])
    return total


def system():
    cpu = [int(v) for v in read("/proc/stat").splitlines()[0].split()[1:]]
    meminfo = {
        line.split(":")[0]: int(line.split()[1])
        for line in read("/proc/meminfo").splitlines()
    }
    freq = read("/sys/class/drm/card0/gt_act_freq_mhz") or read(
        "/sys/class/drm/card0/gt_cur_freq_mhz", "0"
    )
    return {
        "cpu_total": sum(cpu[:8]),
        "cpu_idle": cpu[3] + cpu[4],
        "rc6_ms": int(read("/sys/class/drm/card0/power/rc6_residency_ms", "0")),
        "gt_mhz": int(freq),
        "mem_available_kb": meminfo["MemAvailable"],
        "shmem_kb": meminfo["Shmem"],
        "display_ticks": procs_named("sway", "Xwayland"),
    }


def cpu_temp():
    best = 0
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        if (read(hw / "name", "") or "").strip() == "coretemp":
            for sensor in hw.glob("temp*_input"):
                best = max(best, int(read(sensor, "0")))
    return best / 1000


# -- what the app says


class Counters:
    def __init__(self):
        self.published = {}
        self.paints = 0
        self.paint_s = 0.0
        self.shown = 0
        self.rounds = []
        self.reads = []
        self.time_events = 0
        self.render_tid = None
        self.gate = False
        self.keep = []


COUNT = Counters()


def instrument():
    from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface

    paint = SoftwareVideoSurface.paintEvent

    if "nopaint" in EXP:
        # the frame gets here and goes no further: what's left is everything but showing it
        def paint(self, event):
            pass

    if "nofill" in EXP or "nosmooth" in EXP:
        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QPainter

        smooth = "nosmooth" not in EXP
        fill = "nofill" not in EXP

        def paint(self, event):
            painter = QPainter(self)
            if smooth:
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            placement = self.placement() if self.has_frame() else None
            covers = placement is not None and (
                placement.target[0] <= 0
                and placement.target[1] <= 0
                and placement.target[2] >= self.width()
                and placement.target[3] >= self.height()
            )
            if fill or not covers:
                painter.fillRect(self.rect(), Qt.black)
            if placement is not None:
                painter.drawImage(
                    QRectF(*placement.target), self._image, QRectF(*placement.source)
                )

    def timed(paint):
        def timed_paint(*args):
            start = time.perf_counter()
            paint(*args)
            if COUNT.gate:
                COUNT.paints += 1
                COUNT.paint_s += time.perf_counter() - start

        return timed_paint

    SoftwareVideoSurface.paintEvent = timed(paint)

    # GL output: all of a window's pictures in one paint, where software
    # output paints a cell at a time: paints and their time aren't alike
    from gridplayer.widgets.video_surface_gl import GLGridSurface

    GLGridSurface.paintGL = timed(GLGridSurface.paintGL)

    present = SoftwareVideoSurface.present_rgb32

    def counted_present(self, *args, **kwargs):
        if COUNT.gate:
            COUNT.shown += 1
        present(self, *args, **kwargs)

    SoftwareVideoSurface.present_rgb32 = counted_present

    if "switch" in EXP:
        sys.setswitchinterval(float(EXP["switch"]))

    if DRIVER.startswith("mpv"):
        instrument_mpv()


def instrument_mpv():
    from gridplayer.mpv_player import player as player_module
    from gridplayer.mpv_player import renderer

    if "hwdec" in EXP:
        # a decoder of mpv's by name, whatever the app would have picked
        made = player_module.MpvPlayer.__init__

        def forced_decoder(self, *args, **kwargs):
            kwargs["hwdec"] = EXP["hwdec"]
            made(self, *args, **kwargs)

        player_module.MpvPlayer.__init__ = forced_decoder

    run = renderer.VideoRenderer.run

    def named_run(self):
        COUNT.render_tid = threading.get_native_id()
        run(self)

    renderer.VideoRenderer.run = named_run

    publish = renderer.RenderedVideo.publish

    def counted_publish(self):
        COUNT.published[id(self)] = COUNT.published.get(id(self), 0) + 1
        publish(self)

    renderer.RenderedVideo.publish = counted_publish

    render_round = renderer.VideoRenderer._render_round

    def timed_round(self):
        start = time.perf_counter()
        before = sum(COUNT.published.values())
        render_round(self)
        if COUNT.gate and sum(COUNT.published.values()) != before:
            COUNT.rounds.append((time.perf_counter() - start) * 1000)

    renderer.VideoRenderer._render_round = timed_round

    gl_init = renderer._GLFunctions.__init__

    def timed_gl_init(self, context):
        gl_init(self, context)
        read_pixels = self.glReadPixels

        def timed_read(*args):
            start = time.perf_counter()
            read_pixels(*args)
            if COUNT.gate:
                COUNT.reads.append((time.perf_counter() - start) * 1000)

        self.glReadPixels = timed_read

    renderer._GLFunctions.__init__ = timed_gl_init

    on_time = player_module.MpvPlayer._on_time

    def counted_time(self, name, seconds):
        if COUNT.gate:
            COUNT.time_events += 1
        on_time(self, name, seconds)

    player_module.MpvPlayer._on_time = counted_time

    apply_experiments(renderer, player_module)


class SemWake:
    """In place of the render thread's Event, a semaphore libmpv itself posts to, with no
    Python and no GIL on its side. The wait comes back at most once per COALESCE, and every
    video is asked whether it has a frame."""

    COALESCE_US = 4000

    def __init__(self, renderer):
        import ctypes

        self.renderer = renderer
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.sem = ctypes.create_string_buffer(64)
        self.libc.sem_init(self.sem, 0, 0)
        self.post_address = ctypes.cast(self.libc.sem_post, ctypes.c_void_p).value

    def set(self):
        self.libc.sem_post(self.sem)

    def clear(self):
        pass

    def wait(self):
        libc = self.libc
        libc.sem_wait(self.sem)
        libc.usleep(self.COALESCE_US)
        while libc.sem_trywait(self.sem) == 0:
            pass
        for video in self.renderer._videos:
            video.needs_update = True


def apply_experiments(renderer, player_module):
    from gridplayer.mpv_player.libmpv import load_mpv

    module = load_mpv()

    extra = {k[4:].replace("-", "_"): v for k, v in EXP.items() if k.startswith("opt.")}
    if extra:
        options = player_module.MpvPlayer._options

        def more_options(self):
            return {**options(self), **extra}

        player_module.MpvPlayer._options = more_options

    if "notime" in EXP:
        observe = module.MPV.observe_property
        players = COUNT.players = []

        def no_time(self, name, handler=None):
            if name != "time-pos":
                observe(self, name, handler)

        module.MPV.observe_property = no_time

        player_init = player_module.MpvPlayer.__init__

        def remembered(self, *args, **kwargs):
            player_init(self, *args, **kwargs)
            players.append(self)

        player_module.MpvPlayer.__init__ = remembered

        def poll():
            while True:
                time.sleep(0.2)
                for player in list(players):
                    try:
                        player._on_time("time-pos", player.mpv.time_pos)
                    except Exception:
                        pass

        threading.Thread(target=poll, daemon=True, name="time-poll").start()

    if "fastrender" in EXP:
        cache = {}
        call = module._mpv_render_context_render
        make = module.kwargs_to_render_param_array

        def render(self, **kwargs):
            fbo = kwargs["opengl_fbo"]
            key = (fbo["w"], fbo["h"], fbo["fbo"])
            params = cache.get(key)
            if params is None:
                params = cache[key] = make(kwargs)
            call(self._handle, params)

        module.MpvRenderContext.render = render

    if "semwake" in EXP:
        renderer_init = renderer.VideoRenderer.__init__

        def with_sem(self, *args, **kwargs):
            renderer_init(self, *args, **kwargs)
            self._wake = SemWake(self)

        renderer.VideoRenderer.__init__ = with_sem

        init_video = renderer.VideoRenderer._init_video

        def no_gil_callback(self, video):
            init_video(self, video)
            if video.render_context is not None:
                function = module.RenderUpdateFn(self._wake.post_address)
                COUNT.keep.append(function)
                module._mpv_render_context_set_update_callback(
                    video.render_context._handle,
                    function,
                    ctypes.cast(self._wake.sem, ctypes.c_void_p),
                )

        renderer.VideoRenderer._init_video = no_gil_callback


def mpv_of(block):
    driver = getattr(block.video_driver, "video_driver", None)
    player = getattr(driver, "_player", None)
    return getattr(player, "mpv", None)


MPV_COUNTERS = {
    "frame_drop": "frame-drop-count",
    "decoder_drop": "decoder-frame-drop-count",
    "vo_delayed": "vo-delayed-frame-count",
    "mistimed": "mistimed-frame-count",
}


def mpv_counters(blocks):
    rows = []
    for block in blocks:
        handle = mpv_of(block)
        row = {}
        if handle is not None:
            for key, name in (
                *MPV_COUNTERS.items(),
                ("hwdec", "hwdec-current"),
                ("vf_fps", "estimated-vf-fps"),
            ):
                try:
                    row[key] = handle._get_property(name)
                except Exception:
                    row[key] = None
        rows.append(row)
    return rows


class OwnWindowFrames:
    """MPV drawing into its own windows, with no render thread to count frames: how
    far each video's clock went, read every half second on a thread of its own, its
    frame rate times that less what mpv dropped is what it showed."""

    def __init__(self, blocks):
        self.handles = [mpv_of(b) for b in blocks]
        self.progress = [0.0] * len(self.handles)
        # from the first snapshot's moment: made right after it
        self._prev = self._read()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="frames")
        self._thread.start()

    def _read(self):
        rows = []
        for handle in self.handles:
            try:
                rows.append(
                    (handle._get_property("time-pos"), handle._get_property("duration"))
                )
            except Exception:
                rows.append((None, None))
        return rows

    def _run(self):
        while not self._stop.wait(0.5):
            now = self._read()
            self._add(self._prev, now)
            self._prev = now

    def stop(self):
        """Up to now: what went since the last half-second read too."""

        self._stop.set()
        self._thread.join()
        self._add(self._prev, self._read())

    def _add(self, prev, now):
        for i, ((a, _), (b, length)) in enumerate(zip(prev, now)):
            if a is None or b is None:
                continue
            step = b - a
            if step < 0 and length:
                step += length
            self.progress[i] += max(step, 0)


def autoskip(blocks, result):
    """While mpv is dropping frames past what's allowed, have a few more cells decode only the
    frames others depend on. Once a second, on a thread of its own, as reading can wait."""

    handles = [h for h in (mpv_of(b) for b in blocks) if h is not None]
    step = max(1, len(handles) // 8)
    fps = float(CLIP.split("p")[1].split("_")[0]) if "p" in CLIP else 30
    allowed = 0.02 * fps * len(handles)
    on = 0
    log = result["autoskip_log"] = []
    last = None
    started = time.monotonic()

    while True:
        time.sleep(1)
        try:
            drops = sum(h._get_property("frame-drop-count") or 0 for h in handles)
        except Exception:
            continue
        if last is not None:
            rate = drops - last
            if rate > allowed and on < len(handles):
                for handle in handles[on : on + step]:
                    handle.command_async("set", "vd-lavc-skipframe", "nonref")
                on = min(on + step, len(handles))
                log.append((round(time.monotonic() - started, 1), rate, on))
                result["autoskip_cells"] = on
                # give it a moment to show
                time.sleep(1)
                last = None
                continue
        last = drops


def set_phase(phase):
    (BENCH_DIR / "phase.tmp").write_text(phase)
    os.replace(BENCH_DIR / "phase.tmp", BENCH_DIR / "phase")


def vlc_rows(phase):
    rows = {}
    for path in BENCH_DIR.glob(f"vlc_{phase}_*.json"):
        data = json.loads(path.read_text())
        for row in data["rows"]:
            rows[(path.name.split("_")[-1], row["player"])] = (data["t"], row)
    return rows


def vlc_rates():
    start, end = vlc_rows("t0"), vlc_rows("t1")
    out = []
    for key, (t1, last) in end.items():
        if key not in start:
            continue
        t0, first = start[key]
        span = t1 - t0
        if span > 0:
            out.append(
                {
                    "shown_fps": (last["displayed"] - first["displayed"]) / span,
                    "lost_fps": (last["lost"] - first["lost"]) / span,
                    "decoded_fps": (last["decoded"] - first["decoded"]) / span,
                }
            )
    return out


# -- the probes


class SleepProbe:
    """How late a sleeping thread gets going again. With the GIL: time.sleep, whose thread
    needs it back to go on, as every Python thread woken by anything does. Without: the same
    sleep in C. The gap between them is the GIL."""

    def __init__(self):
        self.running = True
        self.python_us = []
        self.native_us = []
        self.lib = None
        library = Path("build/bench/probe.so")
        if library.exists():
            self.lib = ctypes.CDLL(str(library))
        self._threads = [
            threading.Thread(target=self._python, daemon=True, name="bench-py")
        ]
        if self.lib:
            self._threads.append(
                threading.Thread(target=self._native, daemon=True, name="bench-c")
            )
        for thread in self._threads:
            thread.start()

    def _python(self):
        want = 0.005
        clock = time.perf_counter
        sleep = time.sleep
        while self.running:
            start = clock()
            sleep(want)
            self.python_us.append((clock() - start - want) * 1e6)

    def _native(self):
        count = 100
        buf = (ctypes.c_double * count)()
        while self.running:
            self.lib.sleep_overshoots(count, 5000, buf)
            self.native_us.extend(buf)

    def stop(self):
        self.running = False


class GuiProbe:
    """How late a timer on the GUI thread fires: what a click or a drag would feel."""

    INTERVAL_MS = 10

    def __init__(self):
        self.late_ms = []
        self._last = None
        self.timer = QTimer()
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.INTERVAL_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        now = time.perf_counter()
        if self._last is not None:
            self.late_ms.append((now - self._last) * 1000 - self.INTERVAL_MS)
        self._last = now

    def stop(self):
        self.timer.stop()


def start_spy(out, duration):
    if not SPY:
        return None
    args = [
        shutil.which("py-spy") or str(Path(sys.executable).with_name("py-spy")),
        "record",
        "--pid",
        str(os.getpid()),
        "--rate",
        "200",
        "--duration",
        str(int(duration)),
        "--format",
        "raw",
        "--threads",
        "--output",
        str(out / f"spy_{SPY}.txt"),
    ]
    if SPY == "gil":
        args.extend(["--gil", "--nonblocking"])
    if SPY == "idle":
        args.extend(["--idle", "--nonblocking"])
    if SPY == "native":
        args.extend(["--native", "--idle"])
    return subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=open(out / "spy.err", "w")
    )


def snapshot(blocks):
    tree = process_tree()
    return {
        "t": time.monotonic(),
        "threads": {pid: threads_of(pid) for pid in tree},
        "system": system(),
        "times": [b.time for b in blocks],
        "published": dict(COUNT.published),
        "mpv": mpv_counters(blocks),
    }


def classify(pid, tid, comm, py_names):
    me = os.getpid()
    if pid != me:
        return "child:" + comm[:12]
    if tid == threading.main_thread().native_id:
        return "gui"
    if tid == COUNT.render_tid:
        return "render"
    if tid in py_names:
        return "py:" + py_names[tid]
    return comm


if IS_WIN:
    import psutil

    def process_tree():
        me = psutil.Process()
        return [me.pid] + [c.pid for c in me.children(recursive=True)]

    def threads_of(pid):
        try:
            return {
                t.id: ("thread", int((t.user_time + t.system_time) * CLK))
                for t in psutil.Process(pid).threads()
            }
        except psutil.Error:
            return {}

    def mem_of(pid):
        try:
            info = psutil.Process(pid).memory_full_info()
        except psutil.Error:
            return {}
        return {"Rss": info.rss // 1024, "Pss": info.uss // 1024}

    def system():
        cpu = psutil.cpu_times()
        return {
            "cpu_total": int((cpu.user + cpu.system + cpu.idle) * CLK),
            "cpu_idle": int(cpu.idle * CLK),
            "rc6_ms": 0,
            "gt_mhz": 0,
            "mem_available_kb": psutil.virtual_memory().available // 1024,
            "shmem_kb": 0,
            "display_ticks": 0,
        }

    def cpu_temp():
        return 0


class GpuLog:
    """nvidia-smi once a second, where there is one."""

    QUERY = "utilization.gpu,utilization.decoder,memory.used"

    def __init__(self, out):
        self.path = out / "gpu.csv"
        self.proc = None
        try:
            self.proc = subprocess.Popen(
                [
                    "nvidia-smi",
                    f"--query-gpu={self.QUERY}",
                    "--format=csv,noheader,nounits",
                    "-l",
                    "1",
                ],
                stdout=open(self.path, "w"),
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def finish(self):
        if self.proc is None:
            return {}
        self.proc.terminate()
        self.proc.wait()
        rows = []
        for line in self.path.read_text().splitlines():
            try:
                rows.append([float(v) for v in line.split(",")])
            except ValueError:
                pass
        if not rows:
            return {}
        return {
            "gpu_util": round(statistics.fmean(r[0] for r in rows), 1),
            "dec_util": round(statistics.fmean(r[1] for r in rows), 1),
            "vram_mb": round(max(r[2] for r in rows)),
        }


def vram_now():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
        )
        return int(out.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def scenario(d):
    instrument()

    out = d.out
    set_phase("")
    result = {
        "driver": DRIVER,
        "clip": CLIP,
        "cells": CELLS,
        "settle": SETTLE,
        "measure": MEASURE,
        "exp": EXP,
        "spy": SPY,
    }

    base_system = system()
    base_vram = vram_now()
    clips = clips_for(CLIP, CELLS)

    # the whole screen, tiled by sway or not
    if not IS_AWAY:
        d.player.showMaximized()
        d.player.resize(1920, 1080)
    nested(0.5)

    started = time.monotonic()
    d.open(*clips)

    deadline = started + LOAD_TIMEOUT
    loaded = 0
    load_stall = 0.0
    while time.monotonic() < deadline:
        tick = time.monotonic()
        nested(0.1)
        load_stall = max(load_stall, time.monotonic() - tick - 0.1)
        blocks = d.cells
        loaded = sum(1 for b in blocks if b.is_playable)
        if len(blocks) == CELLS and loaded == CELLS:
            break

    from PyQt5.QtGui import QGuiApplication

    result["load_s"] = round(time.monotonic() - started, 2)
    result["load_stall_s"] = round(load_stall, 2)
    result["source_fps"] = sum(source_fps(clip) for clip in clips)
    result["cells_made"] = len(d.cells)
    result["cells_loaded"] = loaded
    result["refresh_hz"] = QGuiApplication.primaryScreen().refreshRate()
    result["platform"] = QGuiApplication.platformName()

    if "autoskip" in EXP:
        threading.Thread(
            target=autoskip, args=(d.cells, result), daemon=True, name="autoskip"
        ).start()

    if "liveskip" in EXP:
        nested(3)
        for block in d.cells:
            handle = mpv_of(block)
            if handle is not None:
                handle.command_async("set", "vd-lavc-skipframe", EXP["liveskip"])

    if "single" in EXP and d.cells:
        # one cell over the window, the others hidden
        d.act(d.cells[0], "Single Mode ON / OFF")
        result["single_mode"] = bool(d.ctx.is_single_mode)

    nested(SETTLE)
    result["window"] = (d.player.width(), d.player.height())
    block0 = d.cells[0] if d.cells else None
    result["cell_size"] = (block0.width(), block0.height()) if block0 else None
    set_phase("find")
    nested(1)

    blocks = d.cells
    sleep_probe = SleepProbe()
    gui_probe = GuiProbe()
    nested(0.3)
    sleep_probe.python_us.clear()
    sleep_probe.native_us.clear()
    gui_probe.late_ms.clear()

    set_phase("t0")
    nested(0.6)
    spy = start_spy(out, MEASURE)
    gpu_log = GpuLog(out)
    first = snapshot(blocks)
    own_window = OwnWindowFrames(blocks) if blocks and is_direct(blocks[0]) else None
    COUNT.gate = True

    nested(MEASURE)

    COUNT.gate = False
    if own_window is not None:
        own_window.stop()
    last = snapshot(blocks)
    result.update(gpu_log.finish())
    if base_vram is not None and "vram_mb" in result:
        result["vram_used_mb"] = result["vram_mb"] - base_vram
    set_phase("t1")
    gui_probe.stop()
    sleep_probe.stop()
    temp = cpu_temp()
    py_names = {t.native_id: t.name for t in threading.enumerate() if t.native_id}

    tree = process_tree()
    memory = {pid: mem_of(pid) for pid in tree}
    nested(0.7)

    span = last["t"] - first["t"]
    result["span"] = round(span, 2)

    if spy is not None:
        try:
            spy.wait(timeout=15)
        except subprocess.TimeoutExpired:
            spy.kill()

    # thread CPU, percent of one core
    groups = {}
    for pid, threads in last["threads"].items():
        before = first["threads"].get(pid, {})
        for tid, (comm, ticks) in threads.items():
            old = before.get(tid, (comm, ticks))[1]
            used = (ticks - old) / CLK / span * 100
            name = classify(pid, tid, comm, py_names)
            groups[name] = groups.get(name, 0) + used
    result["cpu_groups"] = {
        k: round(v, 1)
        for k, v in sorted(groups.items(), key=lambda kv: -kv[1])
        if v >= 0.1
    }
    result["cpu_app"] = round(sum(groups.values()), 1)

    a, b = first["system"], last["system"]
    busy = (b["cpu_total"] - a["cpu_total"]) - (b["cpu_idle"] - a["cpu_idle"])
    result["cpu_system"] = round(busy / CLK / span * 100, 1)
    result["cpu_display"] = round(
        (b["display_ticks"] - a["display_ticks"]) / CLK / span * 100, 1
    )
    result["gt_busy"] = round(
        100 - (b["rc6_ms"] - a["rc6_ms"]) / (span * 1000) * 100, 1
    )
    result["gt_mhz"] = b["gt_mhz"]
    result["cpu_temp_c"] = temp

    result["pss_mb"] = round(sum(m.get("Pss", 0) for m in memory.values()) / 1024, 1)
    result["rss_main_mb"] = round(memory.get(os.getpid(), {}).get("Rss", 0) / 1024, 1)
    result["processes"] = len(tree)
    result["mem_used_mb"] = round(
        (base_system["mem_available_kb"] - b["mem_available_kb"]) / 1024, 1
    )
    result["shmem_mb"] = round((b["shmem_kb"] - base_system["shmem_kb"]) / 1024, 1)

    # how fast the clock runs; a wrap around the clip's end makes one negative
    rates = [
        (y - x) / 1000 / span
        for x, y in zip(first["times"], last["times"])
        if x is not None and y is not None
    ]
    rates = [r for r in rates if r >= 0]
    result["clock_rate"] = round(statistics.fmean(rates), 3) if rates else None

    # frames
    if DRIVER.startswith("mpv"):
        rows_a, rows_b = first["mpv"], last["mpv"]
        if own_window is not None:
            per_video = []
            for went, x, y in zip(own_window.progress, rows_a, rows_b):
                dropped = sum(
                    (y.get(key) or 0) - (x.get(key) or 0)
                    for key in ("frame_drop", "decoder_drop")
                )
                per_video.append((went * (y.get("vf_fps") or 0) - dropped) / span)
        else:
            per_video = [
                (last["published"].get(k, 0) - v) / span
                for k, v in first["published"].items()
            ]
        result["shown_fps"] = [round(v, 1) for v in per_video]
        for key in MPV_COUNTERS:
            total = 0
            for x, y in zip(rows_a, rows_b):
                if x.get(key) is not None and y.get(key) is not None:
                    total += y[key] - x[key]
            result[f"{key}_per_s"] = round(total / span, 2)
        result["hwdec"] = sorted({str(r.get("hwdec")) for r in rows_b})
        result["vf_fps"] = [round(r["vf_fps"], 1) for r in rows_b if r.get("vf_fps")]
    else:
        rows = vlc_rates()
        result["shown_fps"] = [round(r["shown_fps"], 1) for r in rows]
        result["lost_fps"] = round(sum(r["lost_fps"] for r in rows), 1)
        result["decoded_fps"] = round(sum(r["decoded_fps"] for r in rows), 1)
        result["vlc_players_seen"] = len(rows)

    result["paints_per_s"] = round(COUNT.paints / span, 1)
    result["presents_per_s"] = round(COUNT.shown / span, 1)
    result["paint_ms_mean"] = (
        round(COUNT.paint_s / COUNT.paints * 1000, 3) if COUNT.paints else None
    )
    result["paint_share"] = round(COUNT.paint_s / span * 100, 1)
    result["round_ms"] = summary(COUNT.rounds)
    result["readback_ms"] = summary(COUNT.reads)
    result["time_events_per_s"] = round(COUNT.time_events / span, 1)
    result["gui_late_ms"] = summary(gui_probe.late_ms)
    result["gui_stalls_over_50ms"] = sum(1 for v in gui_probe.late_ms if v > 50)
    result["sleep_late_py_us"] = summary(sleep_probe.python_us)
    result["sleep_late_c_us"] = summary(sleep_probe.native_us)

    d.shot("end")
    if IS_AWAY or IS_ON_SCREEN:
        away.capture(d.player, out / "window.png")
    (out / "bench.json").write_text(json.dumps(result, indent=1, default=str))
