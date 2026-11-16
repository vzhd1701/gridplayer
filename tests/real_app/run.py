"""Run a scenario against the real app.

    uv run python -m tests.real_app.run SCENARIO [--out DIR]

SCENARIO is one of tests/real_app/scenarios by name ("playback"), or the
path of a .py file anywhere, such as one written for a single debug run.
It defines

    SETTINGS = {"video_defaults/network_retry_times": 2}   (optional)

    def scenario(d):    # d is a tests.real_app.driver.Driver
        d.open(d.media.feature)
        block = d.wait_for_cell("feature.mkv")
        d.act(block, "Next Chapter")
        d.wait_until(lambda: block.chapters.playing == 1, "in Part One")

and gets the app offscreen, with settings and data of its own, and the
media of tests/real_app/media.py made if they are not yet. Every step is
printed as a line of JSON as it happens.

What it leaves in DIR (a new temporary folder by default): report.json,
app.log, the screenshots the scenario took and, in screenshots/, those the
app saved. Exits 0 when every check passed and nothing raised, 1 when not,
2 when the run could not start.

With REAL_APP_HANG_S set, a run still going after that many seconds is taken
for hung: every thread's stack goes into hung.txt and the process ends.
"""

import argparse
import faulthandler
import importlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

from tests.real_app import media

HANG_FILE = "hung.txt"

# open for the run, for faulthandler to write to
_hang_file = None


def _load(scenario: str):
    if scenario.endswith(".py"):
        spec = importlib.util.spec_from_file_location("scenario", scenario)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return importlib.import_module(f"tests.real_app.scenarios.{scenario}")


def _watch_for_a_hang(out: Path) -> None:
    """Where every thread was, should the run not end in time: from a thread
    of faulthandler's own, which needs nothing of a Python thread stuck in
    VLC or mpv."""

    global _hang_file

    hang_s = os.environ.get("REAL_APP_HANG_S")

    if not hang_s:
        return

    _hang_file = (out / HANG_FILE).open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(float(hang_s), exit=True, file=_hang_file)


def _stop_watching(out: Path) -> None:
    """A run that ended leaves no hung.txt."""

    if _hang_file is None:
        return

    faulthandler.cancel_dump_traceback_later()
    # closed first: Windows deletes no open file
    _hang_file.close()

    hang_file = out / HANG_FILE

    if not hang_file.stat().st_size:
        hang_file.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenario")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    out = args.out or Path(tempfile.mkdtemp(prefix="gridplayer-run-"))
    out.mkdir(parents=True, exist_ok=True)

    _watch_for_a_hang(out)

    if not media.is_ffmpeg_installed():
        print("ffmpeg is needed to make the media", file=sys.stderr)
        return 2

    module = _load(args.scenario)

    from tests.real_app.driver import start

    driver = start(media.ensure(), out, getattr(module, "SETTINGS", {}))

    # An exception in a Qt slot goes here; with Python's own hook PyQt
    # aborts the process instead
    sys.excepthook = driver.error

    try:
        module.scenario(driver)
    except Exception:
        driver.error(*sys.exc_info())

    _stop_watching(out)

    report = driver.report()
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))

    print(f"\n{'PASSED' if report['ok'] else 'FAILED'}: {out}")
    for line in report["failures"]:
        print(f"  failed: {line}")
    for text in report["errors"]:
        print(f"  error: {text}")

    driver.close()

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # The player tears down VLC and its threads as it quits, which a run
    # has no use for and can hang on; it ends itself this way too
    os._exit(code)
