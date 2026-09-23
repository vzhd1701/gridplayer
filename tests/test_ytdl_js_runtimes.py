"""Which JavaScript engines yt-dlp is allowed to reach for.

Left to itself yt-dlp looks for Deno and nothing else, so a machine with
Node on it is told there is no runtime at all. Naming every engine it
knows how to drive is what makes an installed one count.
"""

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.globals import supported_js_runtimes

from gridplayer.params import env
from gridplayer.utils import js_runtime
from gridplayer.utils.js_runtime import ytdl_js_runtimes
from tests.conftest import FakeSettings


@pytest.fixture
def settings(monkeypatch):
    """The page as it comes out of the box, for a test to edit."""

    values = {"streaming/js_runtime_path": ""}

    monkeypatch.setattr(js_runtime, "Settings", lambda: FakeSettings(values))

    return values


@pytest.fixture
def no_setting(settings):
    """Nobody has named a folder, which is how it ships."""

    return settings


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    """The folder GridPlayer keeps its own files in, emptied."""

    app_data = tmp_path / "data"
    app_data.mkdir()

    monkeypatch.setattr(js_runtime, "get_app_data_dir", lambda: app_data)

    return app_data


def test_every_engine_yt_dlp_can_drive_is_offered():
    """Not a vote for one of them: yt-dlp ranks them and picks."""

    assert set(ytdl_js_runtimes()) == set(supported_js_runtimes.value)


def test_more_than_the_one_yt_dlp_settles_for_by_itself():
    """The whole point of naming them, so guard against it collapsing."""

    with YoutubeDL({"logger": _Quiet()}) as ydl:
        left_alone = set(ydl.params.get("js_runtimes") or ())

    assert set(ytdl_js_runtimes()) > left_alone


def test_a_fresh_dict_every_time():
    """yt-dlp prunes the dict it is handed, so a shared one would erode.

    _clean_js_runtimes pops the names it does not recognise straight out
    of the caller's dict. Handing the same one over twice would mean the
    second resolve inheriting whatever the first one had taken from it.
    """

    first = ytdl_js_runtimes()
    first.pop(next(iter(first)))

    assert len(ytdl_js_runtimes()) == len(first) + 1


def test_every_name_is_one_yt_dlp_recognises():
    """A name it does not know is dropped with a warning on every resolve."""

    logger = _Collecting()

    with YoutubeDL({"logger": logger, "js_runtimes": ytdl_js_runtimes()}) as ydl:
        kept = set(ydl.params["js_runtimes"])

    assert kept == set(ytdl_js_runtimes())
    assert not [line for line in logger.lines if "runtime" in line.lower()]


@pytest.mark.parametrize("engine", ["deno", "node", "quickjs", "bun"])
def test_the_engines_the_readme_names_are_all_offered(engine):
    """The list somebody is told to install from has to be the live one."""

    assert engine in ytdl_js_runtimes()


class _Quiet:
    def debug(self, message):
        """Nothing here is worth a line of its own."""

    info = warning = error = debug


class _Collecting:
    def __init__(self):
        self.lines = []

    def debug(self, message):
        """Only what yt-dlp complains about is of interest here."""

    info = debug

    def warning(self, message):
        self.lines.append(message)

    def error(self, message):
        self.lines.append(message)


class TestWhereItLooks:
    """The folders yt-dlp does not search by itself.

    A snap cannot see the host's /usr/bin at all, a flatpak has the
    runtime's own PATH, and a macOS app started from Finder inherits
    launchd's. In all three the engine is reachable and simply never
    looked for, so the folder GridPlayer already writes to is searched
    as well.
    """

    def test_an_engine_in_the_data_folder_is_found(self, data_dir, no_setting):
        _fake_binary(data_dir, "deno")

        assert ytdl_js_runtimes()["deno"] == {"path": str(data_dir / _exe("deno"))}

    def test_quickjs_is_looked_for_under_the_name_it_ships_as(
        self, data_dir, no_setting
    ):
        """yt-dlp calls the engine quickjs; the binary is called qjs."""

        _fake_binary(data_dir, "qjs")

        assert ytdl_js_runtimes()["quickjs"] == {"path": str(data_dir / _exe("qjs"))}

    def test_an_engine_that_is_nowhere_is_left_to_PATH(self, data_dir, no_setting):
        """A path yt-dlp is given replaces PATH rather than adding to it.

        So naming a folder for an engine that is not in it would stop
        the one on PATH from being found at all.
        """

        assert ytdl_js_runtimes()["deno"] == {}

    def test_the_settings_folder_is_tried_before_the_data_folder(
        self, data_dir, settings, tmp_path
    ):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()

        _fake_binary(data_dir, "deno")
        _fake_binary(elsewhere, "deno")

        settings["streaming/js_runtime_path"] = str(elsewhere)

        assert ytdl_js_runtimes()["deno"] == {"path": str(elsewhere / _exe("deno"))}

    def test_naming_the_engine_itself_works_like_naming_its_folder(
        self, data_dir, settings, tmp_path
    ):
        """Somebody pointed at a binary means the folder it sits in."""

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        binary = _fake_binary(elsewhere, "deno")

        settings["streaming/js_runtime_path"] = str(binary)

        assert ytdl_js_runtimes()["deno"] == {"path": str(binary)}

    def test_a_folder_that_is_not_there_is_not_an_error(
        self, data_dir, settings, tmp_path
    ):
        settings["streaming/js_runtime_path"] = str(tmp_path / "gone")

        assert ytdl_js_runtimes()["deno"] == {}

    def test_a_flatpak_is_shown_the_host_folders(self, monkeypatch, data_dir, settings):
        """The host's own binaries, which a flatpak reaches only here."""

        monkeypatch.setattr(js_runtime.Path, "is_dir", lambda self: True)

        searched = [str(d) for d in js_runtime.js_runtime_dirs()]

        assert "/run/host/usr/local/bin" in [d.replace("\\", "/") for d in searched]
        assert "/run/host/usr/bin" in [d.replace("\\", "/") for d in searched]

    def test_nothing_else_is_shown_them(self, data_dir, no_setting):
        host = js_runtime.FLATPAK_HOST_ROOT

        assert not [d for d in js_runtime.js_runtime_dirs() if d.is_relative_to(host)]


def _exe(basename: str) -> str:
    return f"{basename}.exe" if env.IS_WINDOWS else basename


def _fake_binary(directory, basename: str):
    """Only its presence is asked about, so it need not run."""

    binary = directory / _exe(basename)
    binary.write_bytes(b"")

    return binary


class TestMacOSHomebrew:
    """An app started from Finder cannot see where Homebrew installs.

    launchd hands it /usr/bin:/bin:/usr/sbin:/sbin and nothing else, so
    a runtime installed the ordinary way is there and never looked at.
    """

    def test_the_homebrew_folders_are_searched(self, monkeypatch, data_dir, settings):
        monkeypatch.setattr(js_runtime.env, "IS_MACOS", True)

        searched = _posix(js_runtime.js_runtime_dirs())

        assert "/opt/homebrew/bin" in searched
        assert "/usr/local/bin" in searched

    def test_apple_silicon_comes_before_intel(self, monkeypatch, data_dir, settings):
        """Both can exist on one machine; the native one is the one meant."""

        monkeypatch.setattr(js_runtime.env, "IS_MACOS", True)

        searched = _posix(js_runtime.js_runtime_dirs())

        assert searched.index("/opt/homebrew/bin") < searched.index("/usr/local/bin")

    def test_what_the_person_named_still_wins(self, monkeypatch, data_dir, settings):
        monkeypatch.setattr(js_runtime.env, "IS_MACOS", True)
        settings["streaming/js_runtime_path"] = "/somewhere/else"

        assert _posix(js_runtime.js_runtime_dirs())[0].endswith("/somewhere/else")

    def test_nowhere_else_is_shown_them(self, monkeypatch, data_dir, settings):
        monkeypatch.setattr(js_runtime.env, "IS_MACOS", False)

        assert "/opt/homebrew/bin" not in _posix(js_runtime.js_runtime_dirs())


def _posix(dirs) -> list[str]:
    """Paths as the platform being described spells them, not this one."""

    return [str(d).replace("\\", "/") for d in dirs]


class TestTheInstallersOwnFolders:
    """Where Deno and Bun put themselves when installed their own way.

    Each adds its folder to the shell profile, which a terminal reads
    and a windowed app never does. The folder is dotted, so it is also
    the one place a snap is refused outright.
    """

    def test_they_are_searched(self, data_dir, no_setting):
        searched = _posix(js_runtime.js_runtime_dirs())

        assert any(d.endswith("/.deno/bin") for d in searched)
        assert any(d.endswith("/.bun/bin") for d in searched)

    def test_an_engine_installed_that_way_is_found(
        self, monkeypatch, data_dir, no_setting, tmp_path
    ):
        home = tmp_path / "home"
        deno_bin = home / ".deno" / "bin"
        deno_bin.mkdir(parents=True)
        _fake_binary(deno_bin, "deno")

        monkeypatch.setattr(js_runtime.Path, "home", classmethod(lambda cls: home))

        assert ytdl_js_runtimes()["deno"] == {"path": str(deno_bin / _exe("deno"))}

    def test_the_data_folder_still_comes_first(
        self, monkeypatch, data_dir, no_setting, tmp_path
    ):
        """It is the one a person put there on purpose."""

        home = tmp_path / "home"
        deno_bin = home / ".deno" / "bin"
        deno_bin.mkdir(parents=True)
        _fake_binary(deno_bin, "deno")
        _fake_binary(data_dir, "deno")

        monkeypatch.setattr(js_runtime.Path, "home", classmethod(lambda cls: home))

        assert ytdl_js_runtimes()["deno"] == {"path": str(data_dir / _exe("deno"))}

    def test_node_is_not_among_them(self, data_dir, no_setting):
        """nvm keeps a folder per version, so there is none to name."""

        searched = _posix(js_runtime.js_runtime_dirs())

        assert not [d for d in searched if ".nvm" in d]
