import os
import sys

import pytest

from gridplayer.main.init_cli import init_cli_args
from gridplayer.params import env
from gridplayer.utils import app_dir


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(app_dir.ENV_USER_DATA_DIR, raising=False)
    monkeypatch.setattr(env, "QT_PLATFORM", env.QT_PLATFORM)


def test_no_options_keeps_argv_and_env(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "a.mp4"])

    init_cli_args()

    assert sys.argv == ["gridplayer", "a.mp4"]
    assert app_dir.ENV_USER_DATA_DIR not in os.environ


def test_user_data_dir_sets_env_and_strips_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--user-data-dir", "data", "a.mp4"])

    init_cli_args()

    assert os.environ[app_dir.ENV_USER_DATA_DIR] == "data"
    assert sys.argv == ["gridplayer", "a.mp4"]


def test_cli_overrides_env_value(monkeypatch):
    monkeypatch.setenv(app_dir.ENV_USER_DATA_DIR, "from_env")
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--user-data-dir=from_cli"])

    init_cli_args()

    assert os.environ[app_dir.ENV_USER_DATA_DIR] == "from_cli"


def test_files_urls_and_playlist_captured_in_order(monkeypatch):
    argv = ["gridplayer", "a.mp4", "https://example.com/stream", "r://x", "list.gpls"]
    monkeypatch.setattr(sys, "argv", argv)

    init_cli_args()

    assert sys.argv == argv


def test_options_interleaved_with_files(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["gridplayer", "a.mp4", "--user-data-dir", "data", "b.mp4"],
    )

    init_cli_args()

    assert os.environ[app_dir.ENV_USER_DATA_DIR] == "data"
    assert sys.argv == ["gridplayer", "a.mp4", "b.mp4"]


def test_dashdash_allows_dash_prefixed_filename(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--", "-weird.mp4"])

    init_cli_args()

    assert sys.argv == ["gridplayer", "-weird.mp4"]


def test_dashdash_keeps_files_on_both_sides_in_order(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["gridplayer", "a.mp4", "--user-data-dir", "data", "--", "-b.mp4", "c.mp4"],
    )

    init_cli_args()

    assert os.environ[app_dir.ENV_USER_DATA_DIR] == "data"
    assert sys.argv == ["gridplayer", "a.mp4", "-b.mp4", "c.mp4"]


def test_dashdash_makes_options_after_it_files(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--", "--version", "--"])

    init_cli_args()

    assert sys.argv == ["gridplayer", "--version", "--"]


def test_unknown_option_exits_two(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "-platform", "xcb"])

    with pytest.raises(SystemExit) as e:
        init_cli_args()

    assert e.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_help_shows_positional_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--help"])

    with pytest.raises(SystemExit) as e:
        init_cli_args()

    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "[FILE|URL ...]" in out
    assert "--user-data-dir" in out


def test_help_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--help"])

    with pytest.raises(SystemExit) as e:
        init_cli_args()

    assert e.value.code == 0
    assert "--user-data-dir" in capsys.readouterr().out


def test_version_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--version"])

    with pytest.raises(SystemExit) as e:
        init_cli_args()

    assert e.value.code == 0
    assert "0.5.5" in capsys.readouterr().out


def test_override_returns_override_dir(monkeypatch, tmp_path):
    target = tmp_path / "custom_data"
    monkeypatch.setenv(app_dir.ENV_USER_DATA_DIR, str(target))

    assert app_dir.get_app_data_dir() == target
    assert target.is_dir()


def test_override_relative_resolves_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(app_dir.ENV_USER_DATA_DIR, "rel_data")

    result = app_dir.get_app_data_dir()

    assert result == tmp_path / "rel_data"
    assert result.is_dir()


def test_empty_env_var_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv(app_dir.ENV_USER_DATA_DIR, "   ")
    monkeypatch.chdir(tmp_path)

    assert app_dir.get_user_data_dir_override() is None


@pytest.mark.parametrize("platform", ["xcb", "wayland"])
def test_platform_replaces_detected(monkeypatch, platform):
    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setattr(env, "QT_PLATFORM", "detected")
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--platform", platform, "a.mp4"])

    init_cli_args()

    assert env.QT_PLATFORM == platform
    assert sys.argv == ["gridplayer", "a.mp4"]


def test_platform_auto_keeps_detected(monkeypatch):
    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setattr(env, "QT_PLATFORM", "detected")
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--platform", "auto"])

    init_cli_args()

    assert env.QT_PLATFORM == "detected"


def test_platform_unknown_rejected(monkeypatch):
    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--platform", "eglfs"])

    with pytest.raises(SystemExit):
        init_cli_args()


def test_platform_linux_only(monkeypatch):
    monkeypatch.setattr(env, "IS_LINUX", False)
    monkeypatch.setattr(sys, "argv", ["gridplayer", "--platform", "xcb"])

    with pytest.raises(SystemExit):
        init_cli_args()
