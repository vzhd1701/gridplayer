"""Finding the video libraries without loading them, and what the player does
when one is missing or won't load."""

import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

from gridplayer.mpv_player import libmpv
from gridplayer.params import env
from gridplayer.params.static import VideoDriver
from gridplayer.player.managers import video_driver as manager_module
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.settings import Settings
from gridplayer.utils import libvlc, media_libs, video_driver
from gridplayer.utils.media_libs import LibProblem, MediaLib
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy

ALL_VLC = (
    VideoDriver.VLC_HW,
    VideoDriver.VLC_HW_SP,
    VideoDriver.VLC_SW,
    VideoDriver.VLC_SW_SP,
)


@pytest.fixture(autouse=True)
def _nothing_known(monkeypatch):
    media_libs.forget_libs()

    for name in ("GP_LIBMPV_PATH", "PYTHON_VLC_LIB_PATH", "LD_LIBRARY_PATH"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(video_driver, "is_hw_video_available", lambda: True)

    yield

    # with the real ones back, which are what can be told to forget
    monkeypatch.undo()
    media_libs.forget_libs()


@pytest.fixture
def libs(monkeypatch):
    """Says what is there and what happens on loading it, and counts both."""

    state = SimpleNamespace(
        vlc="libvlc",
        mpv="libmpv",
        vlc_loads=True,
        mpv_problem=None,
        looked=[],
        loaded=[],
    )

    def find_vlc():
        state.looked.append(MediaLib.VLC)
        return state.vlc

    def find_mpv():
        state.looked.append(MediaLib.MPV)
        return state.mpv

    def load_vlc():
        state.loaded.append(MediaLib.VLC)
        return None if state.vlc_loads else LibProblem.WONT_LOAD

    def load_mpv():
        state.loaded.append(MediaLib.MPV)
        return state.mpv_problem

    monkeypatch.setattr(media_libs, "find_libvlc", find_vlc)
    monkeypatch.setattr(media_libs, "find_libmpv", find_mpv)
    monkeypatch.setattr(media_libs, "_load_vlc", load_vlc)
    monkeypatch.setattr(media_libs, "_load_mpv", load_mpv)

    return state


def _no_library_call(_name):
    raise AssertionError("Should have been found before asking the linker")


# -- finding libmpv


def test_libmpv_from_the_environment(monkeypatch, tmp_path):
    library = tmp_path / "libmpv.dll"
    library.touch()

    monkeypatch.setenv("GP_LIBMPV_PATH", str(library))

    assert media_libs.find_libmpv() == str(library)


def test_libmpv_from_the_environment_that_isnt_there_stops_the_search(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GP_LIBMPV_PATH", str(tmp_path / "nothing"))
    monkeypatch.setattr(media_libs.ctypes.util, "find_library", _no_library_call)

    assert media_libs.find_libmpv() is None


def test_libmpv_is_looked_for_once(monkeypatch):
    calls = []

    monkeypatch.setattr(media_libs, "_find_libmpv_windows", lambda: calls.append(1))
    monkeypatch.setattr(media_libs, "_find_libmpv_macos", lambda: calls.append(1))
    monkeypatch.setattr(media_libs, "_find_linux", lambda *_: calls.append(1))
    monkeypatch.setattr(media_libs, "_first_file", lambda *_: None)

    media_libs.find_libmpv()
    media_libs.find_libmpv()

    assert calls == [1]


def test_libmpv_bundled_with_pyinstaller(monkeypatch, tmp_path):
    (tmp_path / "libmpv").mkdir()
    library = tmp_path / "libmpv" / "libmpv-2.dll"
    library.touch()

    monkeypatch.setattr(env, "IS_PYINSTALLER", True)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "gridplayer.exe"))
    monkeypatch.setattr(media_libs.ctypes.util, "find_library", _no_library_call)

    assert media_libs._find_libmpv_windows() == str(library)


@pytest.mark.parametrize(
    "folder",
    [
        "next_to_the_app",
        "next_to_mpv_exe",
        "program_files",
        "local_app_data",
        "scoop",
    ],
)
def test_libmpv_in_the_windows_folders(monkeypatch, tmp_path, folder):
    places = {
        "next_to_the_app": tmp_path / "app",
        "next_to_mpv_exe": tmp_path / "exe",
        "program_files": tmp_path / "pf" / "mpv",
        "local_app_data": tmp_path / "lad" / "Programs" / "mpv",
        "scoop": tmp_path / "scoop" / "apps" / "mpv" / "current",
    }
    places[folder].mkdir(parents=True)
    library = places[folder] / "libmpv-2.dll"
    library.touch()

    monkeypatch.setattr(env, "IS_PYINSTALLER", False)
    monkeypatch.setattr(media_libs, "get_embed_vlc_root", lambda: None)
    monkeypatch.setattr(media_libs.ctypes.util, "find_library", lambda _name: None)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "python.exe"))
    monkeypatch.setattr(
        media_libs.shutil, "which", lambda _name: str(tmp_path / "exe" / "mpv.exe")
    )
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    monkeypatch.setenv("SCOOP", str(tmp_path / "scoop"))

    assert media_libs._find_libmpv_windows() == str(library)


def test_libmpv_nowhere_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "IS_PYINSTALLER", False)
    monkeypatch.setattr(media_libs, "get_embed_vlc_root", lambda: None)
    monkeypatch.setattr(media_libs.ctypes.util, "find_library", lambda _name: None)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(media_libs.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("SCOOP", str(tmp_path))

    assert media_libs._find_libmpv_windows() is None


def test_libmpv_from_homebrew(monkeypatch, tmp_path):
    library = tmp_path / "libmpv.2.dylib"
    library.touch()

    monkeypatch.setattr(env, "IS_PYINSTALLER", False)
    monkeypatch.setattr(media_libs, "get_embed_vlc_root", lambda: None)
    monkeypatch.setattr(media_libs, "LIBMPV_MACOS_DIRS", (str(tmp_path),))
    monkeypatch.setattr(media_libs.ctypes.util, "find_library", _no_library_call)

    assert media_libs._find_libmpv_macos() == str(library)


# -- Linux


def test_linux_finds_the_file_without_asking_the_linker(monkeypatch, tmp_path):
    """If it's missing from the linker's list, that goes on to run gcc and ld."""

    library = tmp_path / "libmpv.so.2"
    library.touch()

    monkeypatch.setenv("LD_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setattr(media_libs.ctypes.util, "find_library", _no_library_call)

    assert media_libs._find_linux("libmpv.so.2", "mpv") == str(library)


def test_linux_asks_the_linker_last(monkeypatch):
    monkeypatch.setattr(media_libs, "_linux_lib_dirs", list)
    monkeypatch.setattr(
        media_libs.ctypes.util, "find_library", lambda name: f"lib{name}.so.1"
    )

    assert media_libs._find_linux("libmpv.so.2", "mpv") == "libmpv.so.1"


def test_linux_folders_put_the_ones_set_first(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/here")

    dirs = media_libs._linux_lib_dirs()

    assert str(dirs[0]).replace("\\", "/") == "/here"
    assert any(str(d).replace("\\", "/") == "/usr/lib" for d in dirs)


# -- finding libVLC


def test_libvlc_embedded_comes_first(monkeypatch, tmp_path):
    library = tmp_path / "libvlc.dll"
    library.touch()

    monkeypatch.setattr(
        media_libs, "get_embed_vlc_paths", lambda: (tmp_path / "plugins", library)
    )

    assert media_libs.find_libvlc() == str(library)


def test_libvlc_embedded_that_isnt_there_goes_on_to_the_system(monkeypatch, tmp_path):
    library = tmp_path / "libvlc.dll"
    library.touch()

    monkeypatch.setattr(
        media_libs, "get_embed_vlc_paths", lambda: (None, tmp_path / "nothing")
    )
    monkeypatch.setenv("PYTHON_VLC_LIB_PATH", str(library))

    assert media_libs.find_libvlc() == str(library)


@pytest.mark.parametrize("folder", ["registry", "videolan", "vlc", "cwd"])
def test_libvlc_in_the_windows_folders(monkeypatch, tmp_path, folder):
    places = {
        "registry": tmp_path / "reg",
        "videolan": tmp_path / "pf" / "VideoLAN" / "VLC",
        "vlc": tmp_path / "pf" / "VLC",
        "cwd": tmp_path / "cwd",
    }
    for place in places.values():
        place.mkdir(parents=True, exist_ok=True)

    library = places[folder] / "libvlc.dll"
    library.touch()

    monkeypatch.setattr(media_libs.ctypes.util, "find_library", lambda _name: None)
    monkeypatch.setattr(media_libs, "_vlc_registry_dir", lambda: tmp_path / "reg")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.chdir(places["cwd"])

    assert media_libs._find_libvlc_windows() == str(library)


def test_nothing_is_loaded_by_finding_or_by_making_the_player():
    """Run apart, with both python modules made to fail if anything imports them."""

    code = textwrap.dedent(
        """
        import sys

        class Blocked:
            def find_spec(self, name, path=None, target=None):
                if name in {"gridplayer.vlc_player.vlc", "gridplayer.mpv_player.mpv"}:
                    raise AssertionError(name + " was imported")

        sys.meta_path.insert(0, Blocked())

        from gridplayer.player import Player
        from gridplayer.utils.media_libs import find_libmpv, find_libvlc

        find_libmpv()
        find_libvlc()
        """
    )

    subprocess.run([sys.executable, "-c", code], check=True, timeout=120)


# -- what is known of a library


def test_a_library_found_is_fine_until_it_wont_load(libs):
    assert media_libs.lib_problem(MediaLib.MPV) is None

    libs.mpv_problem = LibProblem.TOO_OLD

    assert media_libs.load_lib(MediaLib.MPV) is False
    assert media_libs.lib_problem(MediaLib.MPV) is LibProblem.TOO_OLD


def test_a_library_is_only_tried_once(libs):
    libs.mpv_problem = LibProblem.WONT_LOAD

    media_libs.load_lib(MediaLib.MPV)
    media_libs.load_lib(MediaLib.MPV)

    assert libs.loaded == [MediaLib.MPV]


def test_a_library_is_only_loaded_once(libs):
    media_libs.load_lib(MediaLib.VLC)
    media_libs.load_lib(MediaLib.VLC)

    assert libs.loaded == [MediaLib.VLC]


def test_a_library_loaded_isnt_looked_for(libs):
    media_libs.load_lib(MediaLib.VLC)

    assert media_libs.lib_problem(MediaLib.VLC) is None
    assert libs.looked == []


def test_a_library_not_there(libs):
    libs.mpv = None

    assert media_libs.lib_problem(MediaLib.MPV) is LibProblem.MISSING


def test_no_library_is_needed_for_the_dummy(libs):
    assert media_libs.load_lib(media_libs.lib_of_driver(VideoDriver.DUMMY)) is True


@pytest.mark.parametrize(
    ("error", "found", "problem"),
    [
        (libmpv.LibmpvTooOldError("old"), "libmpv", LibProblem.TOO_OLD),
        (OSError("bad"), "libmpv", LibProblem.WONT_LOAD),
        (OSError("gone"), None, LibProblem.MISSING),
    ],
)
def test_what_loading_libmpv_finds(monkeypatch, error, found, problem):
    def load_mpv():
        raise error

    monkeypatch.setattr(libmpv, "load_mpv", load_mpv)
    monkeypatch.setattr(media_libs, "find_libmpv", lambda: found)

    assert media_libs.load_lib(MediaLib.MPV) is False
    assert media_libs.lib_problem(MediaLib.MPV) is problem


@pytest.mark.parametrize(
    ("found", "problem"),
    [("libvlc", LibProblem.WONT_LOAD), (None, LibProblem.MISSING)],
)
def test_what_loading_libvlc_finds(monkeypatch, found, problem):
    def init_vlc():
        raise FileNotFoundError

    monkeypatch.setattr(media_libs, "init_vlc", init_vlc)
    monkeypatch.setattr(media_libs, "find_libvlc", lambda: found)

    assert media_libs.load_lib(MediaLib.VLC) is False
    assert media_libs.lib_problem(MediaLib.VLC) is problem


def test_loading_libvlc_says_its_version(monkeypatch):
    monkeypatch.setattr(media_libs, "init_vlc", lambda: ("3.0.21", "3.0.20"))
    monkeypatch.setattr(env, "VLC_VERSION", None)
    monkeypatch.setattr(env, "VLC_PYTHON_VERSION", None)

    media_libs.load_lib(MediaLib.VLC)

    assert (env.VLC_VERSION, env.VLC_PYTHON_VERSION) == ("3.0.21", "3.0.20")


def test_python_vlc_exiting_is_only_a_library_that_wont_load(monkeypatch):
    """What it does by itself when the library it's pointed at won't load."""

    def importing():
        raise SystemExit(1)

    monkeypatch.setattr(libvlc, "importing_embed_vlc", importing)

    with pytest.raises(FileNotFoundError):
        libvlc._get_vlc_version()


def test_a_file_that_isnt_a_library(monkeypatch, tmp_path):
    junk = tmp_path / "libmpv-2.dll"
    junk.write_bytes(b"not a library")

    monkeypatch.setenv("GP_LIBMPV_PATH", str(junk))
    monkeypatch.delitem(sys.modules, "gridplayer.mpv_player.mpv", raising=False)
    libmpv.load_mpv.cache_clear()

    assert media_libs.load_lib(MediaLib.MPV) is False
    assert media_libs.lib_problem(MediaLib.MPV) is LibProblem.WONT_LOAD


def test_libmpv_under_the_oldest_tried_is_too_old():
    with pytest.raises(libmpv.LibmpvTooOldError):
        libmpv.check_client_api((1, 109))

    # 0.35, 0.36: no video-scale-x, no `fast` profile
    for version in ((2, 0), (2, 1)):
        with pytest.raises(libmpv.LibmpvTooOldError):
            libmpv.check_client_api(version)

    # 0.37, 0.40
    libmpv.check_client_api((2, 2))
    libmpv.check_client_api((2, 5))


@pytest.mark.parametrize(
    ("lib", "problem"),
    [
        *((MediaLib.MPV, problem) for problem in LibProblem),
        (MediaLib.VLC, LibProblem.MISSING),
        (MediaLib.VLC, LibProblem.WONT_LOAD),
    ],
)
def test_each_problem_has_words(monkeypatch, lib, problem):
    monkeypatch.setitem(media_libs._load_results, lib, problem)

    assert media_libs.lib_problem_text(lib)


# -- the driver to run with


@pytest.mark.parametrize(
    ("picked", "stand_in"),
    [
        (VideoDriver.VLC_HW, VideoDriver.MPV_HW),
        (VideoDriver.VLC_HW_SP, VideoDriver.MPV_HW),
        (VideoDriver.VLC_SW, VideoDriver.MPV_SW),
        (VideoDriver.VLC_SW_SP, VideoDriver.MPV_SW),
    ],
)
def test_vlc_missing_runs_on_mpv_of_the_same_kind(libs, picked, stand_in):
    libs.vlc = None

    assert video_driver.session_video_driver(picked) == stand_in


def test_mpv_software_missing_runs_on_vlc_software(libs):
    libs.mpv = None

    assert video_driver.session_video_driver(VideoDriver.MPV_SW) == VideoDriver.VLC_SW


@pytest.mark.parametrize(
    "driver", [VideoDriver.MPV_HW, VideoDriver.MPV_SW], ids=["hardware", "software"]
)
def test_both_mpv_drivers_need_libmpv(driver):
    assert media_libs.lib_of_driver(driver) == MediaLib.MPV


def test_mpv_missing_runs_on_vlc(libs):
    libs.mpv = None

    assert video_driver.session_video_driver(VideoDriver.MPV_HW) == VideoDriver.VLC_HW


def test_mpv_missing_on_macos_runs_on_what_it_has(libs, monkeypatch):
    libs.mpv = None
    monkeypatch.setattr(env, "IS_MACOS", True)

    assert (
        video_driver.session_video_driver(VideoDriver.MPV_HW) == VideoDriver.VLC_HW_SP
    )


def test_mpv_missing_on_native_wayland_runs_on_software(libs, monkeypatch):
    libs.mpv = None
    monkeypatch.setattr(video_driver, "is_hw_video_available", lambda: False)

    assert video_driver.session_video_driver(VideoDriver.MPV_HW) == VideoDriver.VLC_SW


def test_vlc_missing_on_native_wayland_runs_on_mpv(libs, monkeypatch):
    libs.vlc = None
    monkeypatch.setattr(video_driver, "is_hw_video_available", lambda: False)

    assert video_driver.session_video_driver(VideoDriver.VLC_HW) == VideoDriver.MPV_HW


@pytest.mark.parametrize("picked", [*ALL_VLC, VideoDriver.MPV_HW])
def test_both_missing_keeps_the_pick(libs, picked):
    libs.vlc = libs.mpv = None

    assert video_driver.session_video_driver(picked) == picked


def test_the_dummy_needs_nothing(libs):
    libs.vlc = libs.mpv = None

    assert video_driver.session_video_driver(VideoDriver.DUMMY) == VideoDriver.DUMMY


def test_the_setting_stays_as_it_is(libs, mocker):
    libs.mpv = None
    settings_set = mocker.patch.object(Settings(), "set")

    video_driver.session_video_driver(VideoDriver.MPV_HW)

    settings_set.assert_not_called()


def test_loading_goes_to_the_other_when_the_first_wont_load(libs):
    libs.mpv_problem = LibProblem.WONT_LOAD

    driver = video_driver.load_session_driver(VideoDriver.MPV_HW)

    assert driver == VideoDriver.VLC_HW
    assert libs.loaded == [MediaLib.MPV, MediaLib.VLC]


def test_loading_with_neither_working(libs):
    libs.mpv_problem = LibProblem.WONT_LOAD
    libs.vlc_loads = False

    assert video_driver.load_session_driver(VideoDriver.MPV_HW) is None


def test_loading_with_the_other_not_there(libs):
    libs.mpv_problem = LibProblem.TOO_OLD
    libs.vlc = None

    assert video_driver.load_session_driver(VideoDriver.MPV_HW) is None


# -- starting the player


def test_start_on_vlc_only_loads_it(libs):
    assert video_driver.prepare_video_libs(VideoDriver.VLC_HW) is True

    assert libs.loaded == [MediaLib.VLC]
    assert libs.looked == []


def test_start_on_mpv_loads_nothing(libs):
    assert video_driver.prepare_video_libs(VideoDriver.MPV_HW) is True

    assert libs.loaded == []
    assert set(libs.looked) == {MediaLib.MPV}


def test_start_on_the_dummy_needs_nothing(libs):
    libs.vlc = libs.mpv = None

    assert video_driver.prepare_video_libs(VideoDriver.DUMMY) is True

    assert libs.loaded == []


def test_start_on_vlc_not_loading_goes_on_with_mpv_not_loaded(libs):
    libs.vlc_loads = False

    assert video_driver.prepare_video_libs(VideoDriver.VLC_HW) is True

    assert libs.loaded == [MediaLib.VLC]


def test_start_on_mpv_missing_loads_vlc(libs):
    libs.mpv = None

    assert video_driver.prepare_video_libs(VideoDriver.MPV_HW) is True

    assert libs.loaded == [MediaLib.VLC]


@pytest.mark.parametrize("picked", [VideoDriver.VLC_HW, VideoDriver.MPV_HW])
def test_start_with_neither(libs, picked):
    libs.vlc = libs.mpv = None
    libs.vlc_loads = False

    assert video_driver.prepare_video_libs(picked) is False


# -- what the player says


@pytest.fixture
def told(mocker):
    mocker.patch.object(
        manager_module.QTimer, "singleShot", side_effect=lambda _ms, call: call()
    )

    return mocker.patch.object(manager_module.QCustomMessageBox, "warning")


@pytest.fixture
def manager(mocker):
    frame = mocker.patch.object(VideoDriverManager, "_vlc_video_frame")
    mpv_frame = mocker.patch.object(VideoDriverManager, "_mpv_video_frame")

    made = VideoDriverManager(context=SimpleNamespace())
    made.vlc_frame, made.mpv_frame = frame, mpv_frame

    return made


def test_the_player_says_nothing_with_the_library_there(libs, told, manager, mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.MPV_HW)

    assert manager.video_driver() is manager.mpv_frame.return_value

    told.assert_not_called()


def test_the_player_says_nothing_about_software_on_wayland(
    libs, told, manager, mocker, monkeypatch
):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_HW)
    monkeypatch.setattr(video_driver, "is_hw_video_available", lambda: False)

    manager.video_driver()

    manager.vlc_frame.assert_called_once_with(VideoDriver.VLC_SW)
    told.assert_not_called()


def test_the_player_says_once_it_stood_in_with_vlc(libs, told, manager, mocker):
    libs.mpv = None
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.MPV_HW)

    assert manager.video_driver() is manager.vlc_frame.return_value
    manager.video_driver()

    told.assert_called_once()
    assert told.call_args.args[2] == "libmpv not found"
    assert told.call_args.kwargs["info"] == "Playing with VLC for now."


def test_the_player_says_once_it_stood_in_with_mpv(libs, told, manager, mocker):
    libs.vlc = None
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)

    assert manager.video_driver() is manager.mpv_frame.return_value

    told.assert_called_once()
    assert told.call_args.args[2] == "VLC not found"
    assert told.call_args.kwargs["info"] == "Playing with MPV for now."


def test_the_player_says_when_a_library_wont_load_when_first_used(
    libs, told, manager, mocker
):
    libs.mpv_problem = LibProblem.TOO_OLD
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.MPV_HW)

    manager.video_driver()

    manager.vlc_frame.assert_called_once_with(VideoDriver.VLC_HW)
    assert told.call_args.args[2] == "libmpv is too old"


def test_with_nothing_to_play_with_the_cell_stays_empty(libs, told, manager, mocker):
    libs.mpv_problem = LibProblem.WONT_LOAD
    libs.vlc = None
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.MPV_HW)

    assert manager.video_driver() is VideoFrameDummy

    told.assert_called_once()
    assert told.call_args.args[2] == "libmpv won't load"
    assert told.call_args.kwargs["info"] == "Videos can't play without VLC or MPV."
