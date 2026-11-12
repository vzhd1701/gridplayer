"""Running on Wayland natively: no VLC Hardware.

VLC's Hardware drivers hand it an X11 window, so on a Wayland desktop they
need Xwayland. Without it, or on Wayland by the Display setting (on Auto,
whenever the decoder isn't VLC Hardware) or --platform wayland, the player
swaps each Hardware driver for its Software twin, keeping the one picked for
when it runs on X11 again.
"""

import pytest
from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer import settings as settings_module
from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.main.init_app_env import pick_qt_platform
from gridplayer.params import env
from gridplayer.params.static import DisplayServer, MpvOutput, VideoDriver
from gridplayer.player.managers import settings as settings_manager
from gridplayer.player.managers.settings import SettingsManager
from gridplayer.settings import _Settings
from gridplayer.utils import media_libs, video_driver
from gridplayer.utils.cookies import CookieStore
from gridplayer.utils.video_driver import qt_platform_for, session_video_driver
from tests.conftest import FakeSettings


@pytest.fixture(autouse=True)
def _libraries_there(monkeypatch):
    """This is about the platform: see test_media_libs.py for missing libraries."""

    monkeypatch.setattr(media_libs, "lib_problem", lambda _lib: None)
    monkeypatch.setattr(video_driver, "lib_problem", lambda _lib: None)


AUTO, X11, WAYLAND = DisplayServer.AUTO, DisplayServer.X11, DisplayServer.WAYLAND


def _desktop(monkeypatch, wayland_display, display, is_linux=True, frames=True):
    """frames: whether the compositor draws the window frames (not GNOME)."""

    monkeypatch.setattr(env, "IS_LINUX", is_linux)
    monkeypatch.setattr(video_driver, "compositor_draws_frames", lambda: frames)

    for name, value in (("WAYLAND_DISPLAY", wayland_display), ("DISPLAY", display)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("wayland_display", "display", "display_server", "driver", "expected"),
    [
        # Wayland with Xwayland: Auto goes by the decoder
        ("wayland-0", ":0", AUTO, VideoDriver.MPV_HW, "wayland"),
        ("wayland-0", ":0", AUTO, VideoDriver.MPV_SW, "wayland"),
        ("wayland-0", ":0", AUTO, VideoDriver.VLC_SW, "wayland"),
        ("wayland-0", ":0", AUTO, VideoDriver.VLC_SW_SP, "wayland"),
        ("wayland-0", ":0", AUTO, VideoDriver.VLC_HW, "xcb"),
        ("wayland-0", ":0", AUTO, VideoDriver.VLC_HW_SP, "xcb"),
        ("wayland-0", ":0", X11, VideoDriver.MPV_HW, "xcb"),
        ("wayland-0", ":0", WAYLAND, VideoDriver.VLC_HW, "wayland"),
        # only one of them there: that one, whatever is asked
        ("wayland-0", None, X11, VideoDriver.VLC_HW, "wayland"),
        (None, ":0", WAYLAND, VideoDriver.MPV_HW, "xcb"),
        ("", "", AUTO, VideoDriver.MPV_HW, "xcb"),
    ],
)
def test_platform_picked(
    monkeypatch, wayland_display, display, display_server, driver, expected
):
    _desktop(monkeypatch, wayland_display, display)

    assert qt_platform_for(display_server, driver) == expected


@pytest.mark.parametrize(
    ("display_server", "expected"),
    [(AUTO, "xcb"), (WAYLAND, "wayland"), (X11, "xcb")],
)
def test_auto_keeps_x11_where_qt_would_draw_the_frames(
    monkeypatch, display_server, expected
):
    """GNOME: Qt 5's own frame is a thick flat band with no shadow."""

    _desktop(monkeypatch, "wayland-0", ":0", frames=False)

    assert qt_platform_for(display_server, VideoDriver.MPV_HW) == expected


@pytest.mark.parametrize(
    ("driver", "output", "expected"),
    [
        # mpv's own window in a cell's: X11 only
        (VideoDriver.MPV_HW, MpvOutput.WINDOW, "xcb"),
        (VideoDriver.MPV_HW, MpvOutput.READBACK, "wayland"),
        (VideoDriver.MPV_HW, MpvOutput.GL, "wayland"),
        (VideoDriver.MPV_SW, MpvOutput.WINDOW, "wayland"),
    ],
)
def test_auto_takes_x11_for_mpvs_direct_output(monkeypatch, driver, output, expected):
    _desktop(monkeypatch, "wayland-0", ":0")

    assert qt_platform_for(AUTO, driver, output) == expected


def test_wayland_alone_whatever_the_frames(monkeypatch):
    _desktop(monkeypatch, "wayland-0", None, frames=False)

    assert qt_platform_for(AUTO, VideoDriver.MPV_HW) == "wayland"


def test_left_to_qt_off_linux(monkeypatch):
    _desktop(monkeypatch, "wayland-0", None, is_linux=False)

    assert qt_platform_for(AUTO, VideoDriver.MPV_HW) is None


def test_qt_qpa_platform_not_asked(monkeypatch):
    """Set for the whole desktop, it would take Hardware off by the way."""

    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")

    assert qt_platform_for(AUTO, VideoDriver.VLC_HW) == "xcb"


@pytest.mark.parametrize(
    ("given", "expected", "is_picked"),
    [(None, "wayland", True), ("xcb", "xcb", False), ("offscreen", "offscreen", False)],
)
def test_platform_given_is_kept(monkeypatch, given, expected, is_picked):
    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", given)
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", False)
    monkeypatch.setattr(
        settings_module,
        "Settings",
        lambda: FakeSettings(_platform_values(VideoDriver.MPV_HW)),
    )

    pick_qt_platform()

    assert (env.QT_PLATFORM, env.IS_QT_PLATFORM_PICKED) == (expected, is_picked)


def _platform_values(driver, display_server=AUTO, output=MpvOutput.READBACK):
    return {
        "player/display_server": display_server,
        "player/video_driver": driver,
        "player/mpv_output": output,
    }


@pytest.mark.parametrize(
    ("running", "before", "after", "is_due"),
    [
        # to VLC Hardware, and back off it
        ("wayland", VideoDriver.MPV_HW, VideoDriver.VLC_HW, True),
        ("xcb", VideoDriver.VLC_HW, VideoDriver.MPV_HW, True),
        # no change of platform
        ("wayland", VideoDriver.MPV_HW, VideoDriver.VLC_SW, False),
        # back to how the session started, after a restart put off
        ("xcb", VideoDriver.MPV_HW, VideoDriver.VLC_HW, False),
    ],
)
def test_restart_for_another_platform(monkeypatch, running, before, after, is_due):
    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", running)
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)
    monkeypatch.setattr(
        settings_manager, "Settings", lambda: FakeSettings(_platform_values(after))
    )

    is_seen = SettingsManager._is_qt_platform_due(None, _platform_values(before))

    assert is_seen is is_due


def test_restart_for_mpvs_direct_output(monkeypatch):
    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", "wayland")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)
    after = _platform_values(VideoDriver.MPV_HW, output=MpvOutput.WINDOW)
    monkeypatch.setattr(settings_manager, "Settings", lambda: FakeSettings(after))

    assert SettingsManager._is_qt_platform_due(
        None, _platform_values(VideoDriver.MPV_HW)
    )


def test_restart_for_the_display_setting(monkeypatch):
    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", "wayland")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)
    after = _platform_values(VideoDriver.MPV_HW, X11)
    monkeypatch.setattr(settings_manager, "Settings", lambda: FakeSettings(after))

    assert SettingsManager._is_qt_platform_due(
        None, _platform_values(VideoDriver.MPV_HW)
    )


def test_no_restart_when_platform_given(monkeypatch):
    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", "wayland")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", False)
    after = _platform_values(VideoDriver.VLC_HW)
    monkeypatch.setattr(settings_manager, "Settings", lambda: FakeSettings(after))

    is_due = SettingsManager._is_qt_platform_due(
        None, _platform_values(VideoDriver.MPV_HW)
    )

    assert not is_due


@pytest.mark.parametrize(
    ("picked", "expected"),
    [
        (VideoDriver.VLC_HW, VideoDriver.VLC_SW),
        (VideoDriver.VLC_HW_SP, VideoDriver.VLC_SW_SP),
        (VideoDriver.VLC_SW, VideoDriver.VLC_SW),
        (VideoDriver.VLC_SW_SP, VideoDriver.VLC_SW_SP),
        (VideoDriver.DUMMY, VideoDriver.DUMMY),
    ],
)
def test_hardware_falls_back_to_software(monkeypatch, picked, expected):
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "wayland")

    assert session_video_driver(picked) is expected


@pytest.mark.parametrize("platform", ["xcb", "windows", "cocoa"])
@pytest.mark.parametrize("picked", list(VideoDriver))
def test_driver_kept_off_wayland(monkeypatch, platform, picked):
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: platform)

    assert session_video_driver(picked) is picked


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)
    monkeypatch.setattr(
        settings_dialog, "cookie_store", lambda: CookieStore(tmp_path / "cookies.txt")
    )

    return store


@pytest.fixture
def make_dialog(settings):
    made = []

    def _make():
        dialog = SettingsDialog(None)
        made.append(dialog)

        return dialog

    yield _make

    for dialog in made:
        dialog.close()
        dialog.deleteLater()

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _driver_items(dialog):
    combo = dialog.widget("player/video_driver")
    return [combo.itemData(i) for i in range(combo.count())]


@pytest.fixture
def pure_wayland(monkeypatch):
    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "wayland")
    monkeypatch.delenv("DISPLAY", raising=False)


@pytest.fixture
def wayland_with_xwayland(monkeypatch):
    """On Wayland by the Display setting: X11 is a restart away."""

    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_greys_vlc_hardware(make_dialog):
    dialog = make_dialog()

    combo = dialog.widget("player/video_driver")
    available = [
        combo.itemData(i)
        for i in range(combo.count())
        if combo.model().item(i).isEnabled()
    ]

    assert available == [
        VideoDriver.VLC_SW,
        VideoDriver.MPV_HW,
        VideoDriver.MPV_SW,
        VideoDriver.DUMMY,
    ]
    assert combo.reason_of(VideoDriver.VLC_HW) == "Needs X11"
    assert VideoDriver.VLC_HW in _driver_items(dialog)


@pytest.mark.usefixtures("pure_wayland")
@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        (VideoDriver.VLC_HW, VideoDriver.VLC_SW),
        (VideoDriver.VLC_HW_SP, VideoDriver.VLC_SW_SP),
    ],
)
def test_dialog_keeps_hardware_pick(settings, make_dialog, stored, shown):
    settings.set("player/video_driver", stored)

    dialog = make_dialog()

    assert dialog.value("player/video_driver") is shown

    dialog.save_settings()

    assert settings.get("player/video_driver") is stored


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_saves_another_driver(settings, make_dialog):
    settings.set("player/video_driver", VideoDriver.VLC_HW)

    dialog = make_dialog()
    combo = dialog.widget("player/video_driver")
    combo.setCurrentIndex(combo.findData(VideoDriver.VLC_SW))
    dialog.forms["decoder"]._editors["player/video_driver"].processes.setCurrentIndex(1)

    dialog.save_settings()

    assert settings.get("player/video_driver") is VideoDriver.VLC_SW_SP


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_leaves_hardware_options_alone(make_dialog):
    dialog = make_dialog()

    assert not dialog.widget("internal/opaque_hw_overlay").isEnabled()
    assert not dialog.widget("internal/fake_overlay_invisibility").isEnabled()
    assert not dialog.widget("internal/hw_crop_border_offset").isEnabled()
    # shown as Software VLC, which they're not for: a search still finds them
    assert dialog.forms["decoder"]._rows["internal/hw_crop_border_offset"].isHidden()


def test_dialog_offers_hardware_on_xcb(monkeypatch, make_dialog):
    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "xcb")

    dialog = make_dialog()

    assert VideoDriver.VLC_HW in _driver_items(dialog)
    assert dialog.widget("internal/hw_crop_border_offset").isEnabled()


@pytest.mark.usefixtures("pure_wayland")
def test_a_saved_software_driver_is_not_taken_for_the_default(settings, make_dialog):
    # the default is Hardware, shown here as Software too
    settings.set("player/video_driver", VideoDriver.VLC_SW)

    dialog = make_dialog()
    dialog.show_page("decoder")

    assert dialog.forms["decoder"].is_modified("player/video_driver")
    assert not dialog.resetPage.isHidden()


@pytest.mark.usefixtures("pure_wayland")
def test_a_saved_software_driver_reset_is_forgotten(settings, make_dialog):
    settings.set("player/video_driver", VideoDriver.VLC_SW)

    dialog = make_dialog()
    dialog.forms["decoder"].reset("player/video_driver")

    assert not dialog.forms["decoder"].is_modified("player/video_driver")

    dialog.save_settings()

    assert not settings.settings.contains("player/video_driver")


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_says_why_the_hardware_options_are_off(make_dialog):
    dialog = make_dialog()

    assert "X server" in dialog.widget("internal/hw_crop_border_offset").toolTip()


def test_dialog_says_nothing_of_hardware_on_xcb(monkeypatch, make_dialog):
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "xcb")

    dialog = make_dialog()

    assert not dialog.widget("player/video_driver").parentWidget().toolTip()


@pytest.mark.usefixtures("wayland_with_xwayland")
def test_hardware_can_be_picked_for_after_a_restart(make_dialog):
    dialog = make_dialog()

    combo = dialog.widget("player/video_driver")

    assert combo.model().item(combo.findData(VideoDriver.VLC_HW)).isEnabled()


@pytest.mark.usefixtures("wayland_with_xwayland")
def test_dialog_says_a_restart_brings_hardware(make_dialog):
    dialog = make_dialog()

    tip = dialog.widget("internal/hw_crop_border_offset").toolTip()

    assert "running on Wayland" in tip


def test_restart_asked_again_once_put_off(monkeypatch):
    """On Wayland, VLC Hardware picked and no restart; then Window system to
    X11, which wants the same X11 as before: still not what runs."""

    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", "wayland")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)
    after = _platform_values(VideoDriver.VLC_HW, X11)
    monkeypatch.setattr(settings_manager, "Settings", lambda: FakeSettings(after))

    is_due = SettingsManager._is_qt_platform_due(
        None, _platform_values(VideoDriver.VLC_HW)
    )

    assert is_due


def test_no_restart_for_another_change_on_the_platform_running(monkeypatch):
    _desktop(monkeypatch, "wayland-0", ":0")
    monkeypatch.setattr(env, "QT_PLATFORM", "xcb")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)
    after = _platform_values(VideoDriver.VLC_HW_SP)
    monkeypatch.setattr(settings_manager, "Settings", lambda: FakeSettings(after))

    is_due = SettingsManager._is_qt_platform_due(
        None, _platform_values(VideoDriver.VLC_HW)
    )

    assert not is_due


@pytest.mark.parametrize(
    ("wayland_display", "display", "is_shown"),
    [("wayland-0", ":0", True), ("wayland-0", None, False), (None, ":0", False)],
)
def test_window_system_shown_only_with_a_choice(
    monkeypatch, wayland_display, display, is_shown
):
    _desktop(monkeypatch, wayland_display, display)

    assert video_driver.is_window_system_choice() is is_shown


@pytest.mark.usefixtures("wayland_with_xwayland")
def test_hardware_isnt_offered_after_a_restart_with_platform_given(
    monkeypatch, make_dialog
):
    """--platform wayland: the same command line starts on Wayland again."""

    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", False)

    dialog = make_dialog()
    combo = dialog.widget("player/video_driver")

    assert not combo.model().item(combo.findData(VideoDriver.VLC_HW)).isEnabled()
