"""Each scenario of tests/real_app/scenarios against the real app, in a
process of its own (see run.py).

Not part of a plain `pytest` run: they take VLC, ffmpeg and a minute or
two. Run them with

    uv run pytest -m real_app

What a run left behind (report.json, app.log, screenshots) is under the
test's temporary folder, named in a failure.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.real_app import media

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
SCENARIOS = sorted(
    path.stem for path in SCENARIOS_DIR.glob("*.py") if not path.stem.startswith("_")
)

# bugs a scenario shows, until they are fixed: a fix makes the run pass,
# which fails the test, so that it is taken off this list
KNOWN_BUGS = {
    "external_audio_jump": "VLC moves the video back on a track change while "
    "an audio file plays beside it",
}

RUN_TIMEOUT_SEC = 300

pytestmark = [
    pytest.mark.real_app,
    pytest.mark.skipif(not media.is_ffmpeg_installed(), reason="needs ffmpeg"),
]


@pytest.fixture(scope="module", autouse=True)
def _media():
    # made once up front, so that no one scenario's run pays for it
    return media.ensure()


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            name,
            marks=pytest.mark.xfail(reason=KNOWN_BUGS[name], strict=True)
            if name in KNOWN_BUGS
            else (),
        )
        for name in SCENARIOS
    ],
)
def test_scenario(scenario, tmp_path):
    out = tmp_path / scenario

    run = subprocess.run(
        [sys.executable, "-m", "tests.real_app.run", scenario, "--out", str(out)],
        cwd=media.REPO,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SEC,
        check=False,
    )

    report_file = out / "report.json"
    if not report_file.exists():
        pytest.fail(
            f"the run ended without a report:\n{run.stdout[-3000:]}{run.stderr[-3000:]}"
        )

    report = json.loads(report_file.read_text())

    assert report["ok"], "\n".join(
        [f"see {out}", *report["failures"], *report["errors"]]
    )
