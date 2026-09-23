"""Running on Wayland natively: Software video only.

Hardware drivers hand VLC an X11 window, so on a Wayland session they need
Xwayland. Without it (or with --platform wayland) the player runs on
Wayland and swaps each Hardware driver for its Software twin, keeping the
one picked for when it runs on X11 again.
"""

import pytest
from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params import env
from gridplayer.params.static import VideoDriver
from gridplayer.settings import _Settings
from gridplayer.utils import video_driver
from gridplayer.utils.cookies import CookieStore
from gridplayer.utils.video_driver import session_video_driver


@pytest.mark.parametrize(
    ("is_linux", "wayland_display", "display", "expected"),
    [
        (True, "wayland-0", None, "wayland"),
        (True, "wayland-0", ":0", "xcb"),
        (True, None, ":0", "xcb"),
        (True, "", "", "xcb"),
        (False, "wayland-0", None, None),
    ],
)
def test_platform_detection(monkeypatch, is_linux, wayland_display, display, expected):
    monkeypatch.setattr(env, "IS_LINUX", is_linux)

    for name, value in (("WAYLAND_DISPLAY", wayland_display), ("DISPLAY", display)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    assert env._detect_qt_platform() == expected


def test_qt_qpa_platform_not_asked(monkeypatch):
    """Set for the whole desktop, it would take Hardware off by the way."""

    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")

    assert env._detect_qt_platform() == "xcb"


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
    combo = dialog.playerVideoDriver
    return [combo.itemData(i) for i in range(combo.count())]


@pytest.fixture
def pure_wayland(monkeypatch):
    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "wayland")


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_offers_software_only(make_dialog):
    dialog = make_dialog()

    assert _driver_items(dialog) == [
        VideoDriver.VLC_SW,
        VideoDriver.VLC_SW_SP,
        VideoDriver.DUMMY,
    ]


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

    assert dialog.playerVideoDriver.currentData() is shown

    dialog.save_settings()

    assert settings.get("player/video_driver") is stored


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_saves_another_driver(settings, make_dialog):
    settings.set("player/video_driver", VideoDriver.VLC_HW)

    dialog = make_dialog()
    combo = dialog.playerVideoDriver
    combo.setCurrentIndex(combo.findData(VideoDriver.VLC_SW_SP))

    dialog.save_settings()

    assert settings.get("player/video_driver") is VideoDriver.VLC_SW_SP


@pytest.mark.usefixtures("pure_wayland")
def test_dialog_leaves_hardware_options_alone(make_dialog):
    dialog = make_dialog()

    assert not dialog.miscOpaqueHWOverlay.isEnabled()
    assert not dialog.miscFakeOverlayInvisibility.isEnabled()
    assert not dialog.miscHWCropBorder.isEnabled()


def test_dialog_offers_hardware_on_xcb(monkeypatch, make_dialog):
    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "xcb")

    dialog = make_dialog()

    assert VideoDriver.VLC_HW in _driver_items(dialog)
    assert dialog.miscHWCropBorder.isEnabled()
