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
from tests.real_app.run import HANG_FILE

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
NEEDS_LIBMPV = {
    "mpv_audio",
    "mpv_basics",
    "mpv_deinterlace",
    "mpv_hidden_cells",
    "mpv_low_video_memory",
    "mpv_seeking",
    "mpv_stream_sound",
    "mpv_streams",
    "mpv_subtitles",
    "mpv_transport",
    "mpv_view",
}

# the scenarios written for VLC that the MPV drivers are held to as well
ALSO_ON_MPV = (
    "aspect_ratio",
    "cookies",
    "crop_ratio",
    "dubs",
    "external_audio_jump",
    "list_shape",
    "live",
    "live_dash",
    "marks",
    "navigation",
    "pixel_shape",
    "playback",
    "stream_errors",
    "stream_stalls",
    "streams",
    "tracks",
)
MPV_DRIVERS = ("mpv_hw", "mpv_sw")

# The MPV drivers to run, REAL_APP_MPV_DRIVERS=mpv_sw for Software only: a
# Windows runner has no OpenGL Hardware MPV can draw with
MPV_DRIVERS_RUN = os.environ.get("REAL_APP_MPV_DRIVERS", ",".join(MPV_DRIVERS)).split(
    ","
)

# The MPV scenarios written for Hardware MPV that Software MPV is held to too:
# with libmpv's software renderer it turns, flips and deinterlaces by filters.
ALSO_ON_SOFTWARE_MPV = ("mpv_basics", "mpv_deinterlace", "mpv_subtitles", "mpv_view")

RUN_TIMEOUT_SEC = 300
# a run gone this long says where each thread was stuck, before it's killed
HANG_SEC = RUN_TIMEOUT_SEC - 20

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

    # Hardware MPV's own, which Software MPV is held to apart, as far as it can be
    if scenario in NEEDS_LIBMPV and "mpv_hw" not in MPV_DRIVERS_RUN:
        pytest.skip("Hardware MPV not run here")

    _run_scenario(scenario, tmp_path / scenario)


@pytest.mark.parametrize("driver", MPV_DRIVERS)
@pytest.mark.parametrize("scenario", ALSO_ON_MPV)
def test_scenario_on_mpv(scenario, driver, tmp_path):
    if find_libmpv() is None:
        pytest.skip("needs libmpv")

    if driver not in MPV_DRIVERS_RUN:
        pytest.skip(f"{driver} not run here")

    _run_scenario(
        scenario,
        tmp_path / scenario,
        env={**os.environ, "REAL_APP_VIDEO_DRIVER": driver},
    )


@pytest.mark.parametrize("scenario", ALSO_ON_SOFTWARE_MPV)
def test_mpv_scenario_on_software(scenario, tmp_path):
    if find_libmpv() is None:
        pytest.skip("needs libmpv")

    if "mpv_sw" not in MPV_DRIVERS_RUN:
        pytest.skip("mpv_sw not run here")

    _run_scenario(
        scenario,
        tmp_path / scenario,
        env={**os.environ, "REAL_APP_VIDEO_DRIVER": "mpv_sw"},
    )


def _run_scenario(scenario, out, env=None):
    run = subprocess.run(
        [sys.executable, "-m", "tests.real_app.run", scenario, "--out", str(out)],
        cwd=media.REPO,
        env={**(env or os.environ), "REAL_APP_HANG_S": str(HANG_SEC)},
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SEC,
        check=False,
    )

    report_file = out / "report.json"
    hang_file = out / HANG_FILE
    if not report_file.exists() and hang_file.exists() and hang_file.stat().st_size:
        pytest.fail(
            f"hung, still going after {HANG_SEC} s; where each thread was:\n"
            f"{hang_file.read_text(encoding='utf-8', errors='replace')[-6000:]}"
        )
    if not report_file.exists():
        pytest.fail(
            f"the run ended without a report:\n{run.stdout[-3000:]}{run.stderr[-3000:]}"
        )

    report = json.loads(report_file.read_text())

    assert report["ok"], "\n".join(
        [f"see {out}", *report["failures"], *report["errors"]]
    )
