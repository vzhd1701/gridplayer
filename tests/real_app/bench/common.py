"""What the bench's scenarios share: the clips of a run, the app's route to a setting, what a
process is using. grid_bench.py keeps its own, finer numbers."""

import os
import random
import re
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QEventLoop, QTimer

MEDIA = Path(os.environ.get("BENCH_MEDIA", "build/bench-media")).resolve()

# Keeps every run on the same clips, and any number of cells a mix of them
_MIX_ORDER_SEED = 7


def nested(seconds: float) -> None:
    """The app's real event loop, not the driver's pump, which sleeps."""

    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec_()


def media_path(name: str) -> Path:
    return MEDIA / (name if Path(name).suffix else f"{name}.mp4")


# the sets of make_media.sh, by the start of their names
CLIP_SETS = ("mix", "small")


def set_clips(name: str = "mix") -> list[Path]:
    """A set of make_media.sh, in an order that doesn't depend on the name."""

    clips = sorted(MEDIA.glob(f"{name}[0-9]*"))
    random.Random(_MIX_ORDER_SEED).shuffle(clips)

    return clips


def clips_for(spec: str, cells: int) -> list[Path]:
    """As many clips as cells, going round: a set ("mix", "small"), or names with commas between
    them."""

    if spec in CLIP_SETS:
        clips = set_clips(spec)
        if not clips:
            raise FileNotFoundError(f"No {spec} clips in {MEDIA}. See make_media.sh")
    else:
        clips = [media_path(n) for n in spec.split(",")]

    # The app would ask about it in a dialog, and the run sit there until its timeout
    missing = [str(clip) for clip in clips if not clip.is_file()]
    if missing:
        raise FileNotFoundError(f"No such clip: {missing}. See make_media.sh")

    return [clips[i % len(clips)] for i in range(cells)]


def source_fps(clip: Path) -> int:
    return int(re.search(r"p(\d+)", clip.name).group(1))


def vram_used_mb() -> int | None:
    if sys.platform != "win32":
        return None

    try:
        said = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return int(said.stdout.split()[0])


def usage() -> dict:
    """The whole run: this process and any players it has started."""

    import psutil

    me = psutil.Process()
    processes = [me, *me.children(recursive=True)]

    total = {"uss_mb": 0.0, "threads": 0, "handles": 0}
    for process in processes:
        try:
            total["uss_mb"] += process.memory_full_info().uss / 1048576
            total["threads"] += process.num_threads()
            total["handles"] += (
                process.num_handles() if sys.platform == "win32" else process.num_fds()
            )
        except psutil.Error:
            continue

    return {
        **total,
        "uss_mb": round(total["uss_mb"], 1),
        "processes": len(processes),
        "available_mb": round(psutil.virtual_memory().available / 1048576),
        "vram_mb": vram_used_mb(),
    }
