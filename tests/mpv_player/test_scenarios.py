"""Each scenario of tests/mpv_player/scenarios.py against the real libmpv.

Not part of a plain `pytest` run: they need libmpv and a desktop to open
windows on, and take a few minutes. Run them with

    uv run pytest -m mpv

Windows only for now, the one place the mpv drivers have been made to work.
A run's report.json and pictures are under the test's temporary folder.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.mpv_player.media import REPO

SCENARIOS_FILE = Path(__file__).parent / "scenarios.py"
SCENARIOS = sorted(
    node.name
    for node in ast.parse(SCENARIOS_FILE.read_text(encoding="utf-8")).body
    if isinstance(node, ast.FunctionDef) and node.name.startswith("scenario_")
)

NO_LIBMPV_EXIT_CODE = 3
RUN_TIMEOUT_SEC = 900

pytestmark = [
    pytest.mark.mpv,
    pytest.mark.skipif(sys.platform != "win32", reason="needs Windows, for now"),
]


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    out = tmp_path_factory.mktemp("mpv")

    process_env = {
        key: value for key, value in os.environ.items() if key != "QT_QPA_PLATFORM"
    }

    run = subprocess.run(
        [sys.executable, "-m", "tests.mpv_player.run", "--out", str(out)],
        cwd=REPO,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SEC,
        check=False,
    )

    if run.returncode == NO_LIBMPV_EXIT_CODE:
        pytest.skip("needs libmpv")

    report_file = out / "report.json"

    if not report_file.exists():
        pytest.fail(
            f"the run ended without a report:\n{run.stdout[-3000:]}{run.stderr[-3000:]}"
        )

    return json.loads(report_file.read_text(encoding="utf-8"))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario(report, scenario):
    checks = report[scenario]

    assert checks, "it checked nothing"

    failed = [f"{c['name']}: {c['detail']}" for c in checks if not c["ok"]]

    assert not failed, "\n".join(failed)
