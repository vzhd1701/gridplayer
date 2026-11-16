"""--self-check, which CI runs on each package built. What it finds needs the
libraries, and is seen there; here, how a run comes out."""

import pytest

from gridplayer.main import self_check
from gridplayer.utils.checkup import CheckResult, CheckStatus


@pytest.fixture
def checks(monkeypatch):
    """Each check passing unless a test says otherwise."""

    def passing(*_args):
        return CheckResult(CheckStatus.PASSED, "fine")

    for name in ("_check_qt", "_check_vlc", "_check_mpv", "_vlc_plays", "_mpv_plays"):
        monkeypatch.setattr(self_check, name, passing)

    return monkeypatch


def test_all_found_and_played_is_a_pass(checks, capsys):
    assert self_check.run_self_check(["clip.mp4"]) == 0

    report = capsys.readouterr().out
    assert "[ ok ] VLC plays clip.mp4: fine" in report
    assert "[ ok ] MPV plays clip.mp4: fine" in report


def test_one_failing_fails_the_run_and_the_rest_still_run(checks, capsys):
    def missing():
        return CheckResult(CheckStatus.FAILED, "libmpv not found")

    checks.setattr(self_check, "_check_mpv", missing)

    assert self_check.run_self_check(["clip.mp4"]) == 1

    report = capsys.readouterr().out
    assert "[fail] MPV: libmpv not found" in report
    assert "[ ok ] VLC plays clip.mp4: fine" in report


def test_a_check_that_raises_is_a_failure_not_a_crash(checks, capsys):
    def exits(_file):
        # as python-vlc does when the library it found won't load
        raise SystemExit("no VLC")

    checks.setattr(self_check, "_vlc_plays", exits)

    assert self_check.run_self_check(["clip.mp4"]) == 1
    assert "[fail] VLC plays clip.mp4: SystemExit: no VLC" in capsys.readouterr().out


def test_with_no_console_the_report_goes_into_the_data_folder(
    checks, monkeypatch, tmp_path
):
    monkeypatch.setattr(self_check.sys, "stdout", None)
    monkeypatch.setattr("gridplayer.utils.app_dir.get_app_data_dir", lambda: tmp_path)

    self_check.run_self_check([])

    assert "[ ok ] Qt: fine" in (tmp_path / self_check.REPORT_FILE).read_text("utf-8")
