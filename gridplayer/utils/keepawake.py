import logging
import platform

from gridplayer.version import __app_name__

SYSTEM = platform.system()

logger = logging.getLogger(__name__)

if SYSTEM == "Windows":
    import ctypes

    SetThreadExecutionState = ctypes.windll.kernel32.SetThreadExecutionState
    SystemParametersInfo = ctypes.windll.user32.SystemParametersInfoW

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    SPI_SETSCREENSAVEACTIVE = 0x0011

    def keepawake_on():
        logger.debug("Inhibiting screensaver")

        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        SetThreadExecutionState(flags)

        res = SystemParametersInfo(SPI_SETSCREENSAVEACTIVE, 0, None, 0)

        if res != 1:
            logger.warning(f"ON - SystemParametersInfo failed")

    def keepawake_off():
        logger.debug("UnInhibiting screensaver")

        SetThreadExecutionState(ES_CONTINUOUS)

        res = SystemParametersInfo(SPI_SETSCREENSAVEACTIVE, 1, None, 0)

        if res != 1:
            logger.warning(f"OFF - SystemParametersInfo failed")


elif SYSTEM == "Linux":
    from PyQt5.QtDBus import (
        QDBusConnection,
        QDBusInterface,
        QDBusArgument,
    )

    from PyQt5.QtCore import QMetaType

    _dbus_cookie = None

    def dbus_screensaver_set(is_inhibit):
        global _dbus_cookie

        bus = QDBusConnection.sessionBus()

        if not bus.isConnected():
            logger.warning(f"DBus is not connected")
            return

        services = (
            ("org.freedesktop.ScreenSaver", "/ScreenSaver"),
            (
                "org.freedesktop.PowerManagement.Inhibit",
                "/org/freedesktop/PowerManagement",
            ),
            ("org.mate.SessionManager", "/org/mate/SessionManager"),
            ("org.gnome.SessionManager", "/org/gnome/SessionManager"),
        )

        for s_name, s_path in services:
            screensaver_if = QDBusInterface(s_name, s_path, s_name, bus)

            if not screensaver_if.isValid():
                logger.debug(f"DBus interface {s_name} is not valid")
                continue

            if is_inhibit:
                reply = screensaver_if.call("Inhibit", __app_name__, "Playing media.")
            else:
                if _dbus_cookie is None:
                    logger.warning(f"DBus Cookie is empty")
                    break

                uint_dbus_cookie = QDBusArgument()
                uint_dbus_cookie.add(_dbus_cookie, QMetaType.UInt)
                reply = screensaver_if.call("UnInhibit", uint_dbus_cookie)

            error = reply.errorName()

            if not error:
                _dbus_cookie = reply.arguments()[0]
                logger.debug(f"New DBus Cookie: {_dbus_cookie}")
            else:
                logger.debug(f"Error: {error}")
                logger.debug(f"Error: {reply.errorMessage()}")

            break

    def keepawake_on():
        logger.debug("Inhibiting screensaver")
        dbus_screensaver_set(True)

    def keepawake_off():
        logger.debug("UnInhibiting screensaver")
        dbus_screensaver_set(False)


elif SYSTEM == "Darwin":
    from gridplayer.utils.macos import assertNoIdleSleep, removeNoIdleSleepAssertion

    _assertion_id = None

    def keepawake_on():
        logger.debug("Inhibiting screensaver")

        global _assertion_id

        _assertion_id = assertNoIdleSleep("Playing media")

    def keepawake_off():
        logger.debug("UnInhibiting screensaver")

        removeNoIdleSleepAssertion(_assertion_id)


else:

    def keepawake_on():
        logger.debug("Inhibiting screensaver not supported")

    def keepawake_off():
        logger.debug("UnInhibiting screensaver not supported")
