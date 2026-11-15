from PyQt5.QtGui import QGuiApplication

from gridplayer.params import env
from gridplayer.params.static import DisplayServer, MpvOutput, VideoDriver
from gridplayer.utils.media_libs import (
    VLC_HW_DRIVERS,
    MediaLib,
    lib_of_driver,
    lib_problem,
    load_lib,
)
from gridplayer.utils.wayland_frames import compositor_draws_frames

# Hardware drivers hand VLC an X11 window to draw into, which Qt running on
# Wayland natively doesn't have; each has a Software twin that paints
# through Qt.
_SOFTWARE_FALLBACK = {
    VideoDriver.VLC_HW: VideoDriver.VLC_SW,
    VideoDriver.VLC_HW_SP: VideoDriver.VLC_SW_SP,
}


# The drivers that can run in processes of their own, and each one's
# single-process twin. Settings show these as two choices.
_SINGLE_PROCESS_TWIN = {
    VideoDriver.VLC_HW: VideoDriver.VLC_HW_SP,
    VideoDriver.VLC_SW: VideoDriver.VLC_SW_SP,
}

MULTIPROCESS_DRIVERS = tuple(_SINGLE_PROCESS_TWIN)


def driver_parts(driver: VideoDriver) -> tuple[VideoDriver, bool]:
    """A driver as the decoder and whether it's a single process."""

    for decoder, twin in _SINGLE_PROCESS_TWIN.items():
        if driver == twin:
            return decoder, True

    return driver, driver not in _SINGLE_PROCESS_TWIN


def driver_of_parts(decoder: VideoDriver, is_single: bool) -> VideoDriver:
    return _SINGLE_PROCESS_TWIN.get(decoder, decoder) if is_single else decoder


def is_single_process_only(decoder: VideoDriver) -> bool:
    if decoder == VideoDriver.VLC_HW and env.IS_MACOS:
        return True

    return decoder not in _SINGLE_PROCESS_TWIN


def is_hw_video_available() -> bool:
    # the platform Qt ended up on, however it was picked
    return _qt_platform_name() != "wayland"


def is_hw_video_possible() -> bool:
    """Whether VLC Hardware can run here, if not now then after a restart on
    X11: there is an X server, Xwayland on a Wayland desktop, and --platform
    didn't say Wayland."""

    if is_hw_video_available():
        return True

    return env.has_x_server() and env.IS_QT_PLATFORM_PICKED


def is_window_system_choice() -> bool:
    """Whether there's a choice of X11 or Wayland: a Wayland desktop with
    Xwayland."""

    return env.IS_LINUX and env.has_wayland() and env.has_x_server()


def qt_platform_for(
    display: DisplayServer,
    driver: VideoDriver,
    mpv_output: MpvOutput = MpvOutput.READBACK,
) -> str | None:
    """The Qt platform to run on, None to leave it to Qt (not Linux).

    QT_QPA_PLATFORM is not asked: it is often set to wayland for the whole
    desktop, which would take VLC Hardware off by the way.
    """

    if not env.IS_LINUX:
        return None

    if not env.has_wayland():
        return "xcb"

    if not env.has_x_server():
        return "wayland"

    if display == DisplayServer.X11:
        return "xcb"

    if display == DisplayServer.WAYLAND:
        return "wayland"

    # VLC Hardware draws into an X11 window, as MPV's Direct does
    if driver in VLC_HW_DRIVERS:
        return "xcb"

    if driver == VideoDriver.MPV_HW and mpv_output == MpvOutput.WINDOW:
        return "xcb"

    # Without a frame from the desktop, Qt 5's own is a thick flat band with
    # no shadow, around dialogs too: Xwayland looks like every other app
    return "wayland" if compositor_draws_frames() else "xcb"


def session_video_driver(driver: VideoDriver) -> VideoDriver:
    """The driver to run with in this session in place of the one picked.

    Leaves the setting itself alone, so a Hardware pick still applies the next
    time the player starts on X11 or Xwayland, and an mpv or VLC pick the next
    time its library is there. If neither library can be used it's the one picked.
    """

    picked = driver
    driver = driver_for_platform(picked)
    lib = lib_of_driver(driver)

    if lib is None or lib_problem(lib) is None:
        return driver

    stand_in = _stand_in_driver(picked)

    return driver if lib_problem(lib_of_driver(stand_in)) else stand_in


def is_mpv_gl_output(output: MpvOutput, picked: VideoDriver) -> bool:
    """Whether MPV's frames are drawn by GL: picked, with Hardware MPV playing,
    not VLC standing in for it. Software MPV has no GL."""

    return output == MpvOutput.GL and session_video_driver(picked) == VideoDriver.MPV_HW


def is_mpv_window_output(output: MpvOutput) -> bool:
    """Whether Hardware MPV draws into a native window a cell itself: on Windows,
    and on Linux with an X11 window to give mpv. On Wayland a surface is only its
    own client's to draw into, and offscreen there are no windows: Copy there
    instead."""

    if output != MpvOutput.WINDOW:
        return False

    if env.IS_WINDOWS:
        return _qt_platform_name() == "windows"

    return env.IS_LINUX and _qt_platform_name() == "xcb"


def load_session_driver(driver: VideoDriver) -> VideoDriver | None:
    """The driver to run with, its library loaded. None if nothing can play."""

    session_driver = session_video_driver(driver)

    while not load_lib(lib_of_driver(session_driver)):
        # now that it's known it won't load, this comes out different if it can
        stand_in = session_video_driver(driver)

        if stand_in == session_driver:
            return None

        session_driver = stand_in

    return session_driver


def prepare_video_libs(driver: VideoDriver) -> bool:
    """What starting the player takes, False if nothing can play.

    VLC loads here, since it is what's going to play and its version is on show.
    libmpv loads with the first video, so with mpv nothing is loaded at all. If
    VLC is there, this doesn't even look for it: loading it is the looking.
    """

    if lib_of_driver(driver) == MediaLib.VLC and load_lib(MediaLib.VLC):
        return True

    session_driver = session_video_driver(driver)
    lib = lib_of_driver(session_driver)

    if lib == MediaLib.VLC:
        return load_lib(lib)

    return lib is None or lib_problem(lib) is None


def driver_for_platform(driver: VideoDriver) -> VideoDriver:
    if is_hw_video_available():
        return driver

    return _SOFTWARE_FALLBACK.get(driver, driver)


def _stand_in_driver(picked: VideoDriver) -> VideoDriver:
    """The other library's driver for a pick, of the same kind: someone on
    Software may well be there because Hardware doesn't work for them."""

    if lib_of_driver(picked) == MediaLib.VLC:
        is_software = picked in _SOFTWARE_FALLBACK.values()
        return VideoDriver.MPV_SW if is_software else VideoDriver.MPV_HW

    if picked == VideoDriver.MPV_SW:
        return VideoDriver.VLC_SW

    return _default_vlc_driver()


def _default_vlc_driver() -> VideoDriver:
    # the same as in the default settings
    driver = VideoDriver.VLC_HW_SP if env.IS_MACOS else VideoDriver.VLC_HW

    return driver_for_platform(driver)


def _qt_platform_name() -> str:
    return QGuiApplication.platformName()
