from PyQt5.QtGui import QGuiApplication

from gridplayer.params.static import VideoDriver

# The Hardware driver hands mpv an X11 window to draw into, which Qt running
# on Wayland natively doesn't have; its Software twin paints through Qt.
_SOFTWARE_FALLBACK = {
    VideoDriver.MPV_HW: VideoDriver.MPV_SW,
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
