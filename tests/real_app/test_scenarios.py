"""Each scenario of tests/real_app/scenarios against the real app, in a
process of its own (see run.py).

Not part of a plain `pytest` run: they take VLC, ffmpeg and a minute or
two. Run them with

    uv run pytest -m real_app

What a run left behind (report.json, app.log, screenshots) is under the
test's temporary folder, named in a failure.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gridplayer.utils.media_libs import find_libmpv
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

# the scenarios of a driver that isn't there on every machine
NEEDS_LIBMPV = {"mpv_audio", "mpv_basics", "mpv_transport", "mpv_view"}

# the scenarios written for VLC that the MPV drivers are held to as well
ALSO_ON_MPV = (
    "aspect_ratio",
    "crop_ratio",
    "list_shape",
    "pixel_shape",
    "playback",
)
MPV_DRIVERS = ("mpv_hw", "mpv_sw")

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
    if scenario in NEEDS_LIBMPV and find_libmpv() is None:
        pytest.skip("needs libmpv")

    _run_scenario(scenario, tmp_path / scenario)


@pytest.mark.parametrize("driver", MPV_DRIVERS)
@pytest.mark.parametrize("scenario", ALSO_ON_MPV)
def test_scenario_on_mpv(scenario, driver, tmp_path):
    if find_libmpv() is None:
        pytest.skip("needs libmpv")

    _run_scenario(
        scenario,
        tmp_path / scenario,
        env={**os.environ, "REAL_APP_VIDEO_DRIVER": driver},
    )


def _run_scenario(scenario, out, env=None):
    run = subprocess.run(
        [sys.executable, "-m", "tests.real_app.run", scenario, "--out", str(out)],
        cwd=media.REPO,
        env=env,
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
