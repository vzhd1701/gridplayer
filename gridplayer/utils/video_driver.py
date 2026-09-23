from PyQt5.QtGui import QGuiApplication

from gridplayer.params.static import VideoDriver

# Hardware drivers hand VLC an X11 window to draw into, which Qt running on
# Wayland natively doesn't have; each has a Software twin that paints
# through Qt.
_SOFTWARE_FALLBACK = {
    VideoDriver.VLC_HW: VideoDriver.VLC_SW,
    VideoDriver.VLC_HW_SP: VideoDriver.VLC_SW_SP,
}


def is_hw_video_available() -> bool:
    # the platform Qt ended up on, however it was picked
    return _qt_platform_name() != "wayland"


def session_video_driver(driver: VideoDriver) -> VideoDriver:
    """The driver to run with in this session in place of the one picked.

    Leaves the setting itself alone, so a Hardware pick still applies
    the next time the player starts on X11 or Xwayland.
    """

    if is_hw_video_available():
        return driver

    return _SOFTWARE_FALLBACK.get(driver, driver)


def _qt_platform_name() -> str:
    return QGuiApplication.platformName()
