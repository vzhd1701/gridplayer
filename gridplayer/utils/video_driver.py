from PyQt5.QtGui import QGuiApplication

from gridplayer.params import env
from gridplayer.params.static import MpvOutput, VideoDriver
from gridplayer.utils.media_libs import MediaLib, lib_of_driver, lib_problem, load_lib

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
    not VLC standing in for it. Software MPV has no GL. Not on macOS, where MPV
    hasn't been run yet."""

    return (
        not env.IS_MACOS
        and output == MpvOutput.GL
        and session_video_driver(picked) == VideoDriver.MPV_HW
    )


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
