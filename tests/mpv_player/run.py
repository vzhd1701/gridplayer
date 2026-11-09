"""Run the mpv scenarios and write down what they found.

    uv run python -m tests.mpv_player.run --out DIR [SCENARIO ...]

In a process of its own: mpv's hardware driver needs a real window, and the
tests proper draw offscreen. Writes DIR/report.json. Exits 3 without one's
scenarios run where there is no libmpv to run them against.
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

NO_LIBMPV_EXIT_CODE = 3


class Context:
    """What a scenario is handed: the media, a folder, and somewhere to report."""

    def __init__(self, media: Path, out: Path):
        self.media = media
        self.out = out
        self.checks = []

    def check(self, name, is_ok, detail=""):
        self.checks.append(
            {"name": name, "ok": bool(is_ok), "detail": str(detail)[:400]}
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("scenarios", nargs="*")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    # settings of its own, whatever the person running it has set
    os.environ["GP_USER_DATA_DIR"] = str(args.out / "data")

    from PyQt5.QtWidgets import QApplication

    from gridplayer.main.init_app_env import init_app_env_id
    from gridplayer.utils.libmpv import init_mpv

    application = QApplication([])
    init_app_env_id()

    try:
        init_mpv()
    except FileNotFoundError:
        return NO_LIBMPV_EXIT_CODE

    from gridplayer.params import env

    if env.IS_WINDOWS:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)

    from tests.mpv_player import harness, media, scenarios

    media_dir = media.ensure()
    report = {}

    names = args.scenarios or [n for n in dir(scenarios) if n.startswith("scenario_")]

    for name in names:
        context = Context(media_dir, args.out)

        try:
            getattr(scenarios, name)(context)
        except Exception:
            context.check("ran to the end", False, traceback.format_exc())

        for session in list(harness.open_sessions):
            session.close()

        report[name] = context.checks

        print(name, sum(c["ok"] for c in context.checks), "/", len(context.checks))
        sys.stdout.flush()

    (args.out / "report.json").write_text(json.dumps(report, indent=1))

    del application

    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # nothing a run would want from Qt and libmpv tearing themselves down
    os._exit(code)
