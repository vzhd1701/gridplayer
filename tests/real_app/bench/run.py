"""Grids of one clip in the real app, each driver going up in cells until it can't hold them:
below 40% of the clip's frame rate, or not all of it loaded. Each run is a process of its own.

    uv run --with psutil python tests/real_app/bench/run.py h264_1080p60 \\
        --drivers mpv_hw,vlc_hw_sp --cells 4,9,16 --env EXP=skip --out build/bench/out

Prints a line for each run, and leaves bench.json and the app's own files in a folder for it.
See README.md here.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

RUN_TIMEOUT_S = int(os.environ.get("RUN_TIMEOUT", "200"))
# away.py: the user's desktop changed, so nothing more runs
EXIT_DESKTOP_CHANGED = 77
GAVE_UP_BELOW = 0.4
# sway's headless output starts out smaller than this
SCREEN_MODE = "1920x1080@60Hz"


def _prefix() -> list[str]:
    """What puts a run on the desktop: the test machine's own command, if there is one."""

    return ["session", "xcb"] if shutil.which("session") else []


def _kill_all_of(process: subprocess.Popen) -> None:
    # the VLC drivers leave forked players behind a process that has gone
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        return

    # macOS says EPERM rather than ESRCH for a group that has gone
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_one(driver, clip, cells, out_root, extra_env) -> dict:
    out = out_root / f"{driver}_{clip}_{cells}"
    shutil.rmtree(out, ignore_errors=True)
    (out / "phase_dir").mkdir(parents=True)

    env = {
        **os.environ,
        **extra_env,
        "PYTHONIOENCODING": "utf-8",
        "DRIVER": driver,
        "CLIP": clip,
        "CELLS": str(cells),
        "GP_BENCH_DIR": str(out / "phase_dir"),
        "PYTHONPATH": os.pathsep.join(
            [str(REPO), str(HERE), os.environ.get("PYTHONPATH", "")]
        ),
    }
    if sys.platform == "darwin":
        env["REAL_APP_QT_PLATFORM"] = "cocoa"
    elif sys.platform != "win32":
        env["REAL_APP_QT_PLATFORM"] = "xcb"

    command = [
        *_prefix(),
        sys.executable,
        "-m",
        "tests.real_app.run",
        str(HERE / "grid_bench.py"),
        "--out",
        str(out),
    ]

    with (out / "stdout.txt").open("w") as stdout:
        process = subprocess.Popen(
            command,
            cwd=REPO,
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            start_new_session=sys.platform != "win32",
        )
        try:
            code = process.wait(timeout=RUN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            code = "timeout"
        _kill_all_of(process)

    bench_json = out / "bench.json"
    if bench_json.is_file():
        return json.loads(bench_json.read_text())

    return {"driver": driver, "clip": clip, "cells": cells, "failed": code}


def mean_fps(result: dict) -> float:
    fps = result.get("shown_fps") or [0]
    return sum(fps) / len(fps)


def row(result: dict) -> str:
    head = f"{result['driver']:9} {result['clip']:13} n={result['cells']:<3}"
    if "failed" in result:
        return f"{head} FAILED {result['failed']}"

    gui = result.get("gui_late_ms") or {}
    python_late = result.get("sleep_late_py_us") or {}
    native_late = result.get("sleep_late_c_us") or {}
    numbers = {
        "load": result.get("load_s"),
        "stall": result.get("load_stall_s"),
        "ok": result.get("cells_loaded"),
        "fps": round(mean_fps(result), 1),
        "min": min(result.get("shown_fps") or [0]),
        "clock": result.get("clock_rate"),
        "lost": result.get("lost_fps", result.get("frame_drop_per_s")),
        "cpu": result.get("cpu_app"),
        "sys": result.get("cpu_system"),
        "display": result.get("cpu_display"),
        "gt": result.get("gt_busy"),
        "gpu": result.get("gpu_util"),
        "dec": result.get("dec_util"),
        "vram+": result.get("vram_used_mb"),
        "mem": result.get("pss_mb"),
        "used": result.get("mem_used_mb"),
        "gui_p95": gui.get("p95"),
        "py_p95": python_late.get("p95"),
        "c_p95": native_late.get("p95"),
        "hwdec": result.get("hwdec"),
    }
    said = " ".join(f"{k} {v}" for k, v in numbers.items() if v is not None and v != "")

    return f"{head} {said}"


def has_given_up(result: dict, source_fps: int) -> bool:
    return (
        "failed" in result
        or result.get("cells_loaded") != result.get("cells")
        or mean_fps(result) < source_fps * GAVE_UP_BELOW
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", help="name in the media folder, with no extension")
    parser.add_argument("--drivers", required=True, help="comma-separated")
    parser.add_argument("--cells", required=True, help="comma-separated, going up")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--out", type=Path, default=REPO / "build" / "bench" / "out")
    args = parser.parse_args()

    match = re.search(r"p(\d+)", args.clip)
    source_fps = int(match.group(1)) if match else 0
    extra_env = dict(item.split("=", 1) for item in args.env)

    if _prefix():
        subprocess.run(
            [*_prefix(), "swaymsg", "output", "HEADLESS-1", "mode", SCREEN_MODE],
            capture_output=True,
            check=False,
        )

    for driver in args.drivers.split(","):
        for cells in map(int, args.cells.split(",")):
            result = run_one(driver, args.clip, cells, args.out.resolve(), extra_env)
            print(row(result), flush=True)

            if result.get("failed") == EXIT_DESKTOP_CHANGED:
                sys.exit("The user's desktop changed: stopping")

            if has_given_up(result, source_fps):
                print(f"-- {driver} {args.clip} stops at {cells}", flush=True)
                break


if __name__ == "__main__":
    main()
