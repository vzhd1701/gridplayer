import logging
import platform

from gridplayer.version import __app_name__

SYSTEM = platform.system()

logger = logging.getLogger(__name__)

if SYSTEM == "Windows":  # noqa: C901
    import ctypes

    SetThreadExecutionState = ctypes.windll.kernel32.SetThreadExecutionState
    SystemParametersInfo = ctypes.windll.user32.SystemParametersInfoW

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    SPI_SETSCREENSAVEACTIVE = 0x0011

    class KeepAwake(object):
        def __init__(self):
            self.is_screensaver_off = False

        def screensaver_off(self):
            if self.is_screensaver_off:
                return

            logger.debug("Inhibiting screensaver")

            flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            SetThreadExecutionState(flags)

            res = SystemParametersInfo(SPI_SETSCREENSAVEACTIVE, 0, None, 0)

            if res != 1:
                logger.warning("ON - SystemParametersInfo failed")

            self.is_screensaver_off = True

        def screensaver_on(self):
            if not self.is_screensaver_off:
                return

            logger.debug("UnInhibiting screensaver")

            SetThreadExecutionState(ES_CONTINUOUS)

            res = SystemParametersInfo(SPI_SETSCREENSAVEACTIVE, 1, None, 0)

            if res != 1:
                logger.warning("OFF - SystemParametersInfo failed")

            self.is_screensaver_off = False


elif SYSTEM == "Linux":
    from PyQt5.QtCore import QMetaType
    from PyQt5.QtDBus import QDBusArgument, QDBusConnection, QDBusInterface

    class KeepAwake(object):
        _services = (
            ("org.freedesktop.ScreenSaver", "/ScreenSaver"),
            (
                "org.freedesktop.PowerManagement.Inhibit",
                "/org/freedesktop/PowerManagement",
            ),
            ("org.mate.SessionManager", "/org/mate/SessionManager"),
            ("org.gnome.SessionManager", "/org/gnome/SessionManager"),
        )

        def __init__(self):
            self.is_screensaver_off = False

            self._dbus_cookie = None

            try:
                self._screensaver_if = self._dbus_get_interface()
            except ValueError:
                self._screensaver_if = None

        def screensaver_off(self):
            if self.is_screensaver_off:
                return

            logger.debug("Inhibiting screensaver")

            if self._screensaver_if is None:
                logger.warning("DBus interface is not initialized")
                return

            reply = self._dbus_call("Inhibit", __app_name__, "Playing media.")

            self._dbus_cookie = reply[0]
            logger.debug(f"New DBus Cookie: {self._dbus_cookie}")

            self.is_screensaver_off = True

        def screensaver_on(self):
            if not self.is_screensaver_off:
                return

            logger.debug("UnInhibiting screensaver")

            if self._screensaver_if is None:
                logger.warning("DBus interface is not initialized")
                return

            if self._dbus_cookie is None:
                logger.warning("DBus Cookie is empty")
                return

            uint_dbus_cookie = QDBusArgument()
            uint_dbus_cookie.add(self._dbus_cookie, QMetaType.UInt)

            self._dbus_call("UnInhibit", uint_dbus_cookie)

            self._dbus_cookie = None

            self.is_screensaver_off = False

        def _dbus_call(self, *args):
            reply = self._screensaver_if.call(*args)

            if reply.errorName():
                logger.debug(f"DBUS Error: {reply.errorName()}")
                logger.debug(f"DBUS Error Message: {reply.errorMessage()}")

            return reply.arguments()

        def _dbus_get_interface(self):
            bus = QDBusConnection.sessionBus()

            if not bus.isConnected():
                logger.warning("DBus failed to connected")

                raise ValueError

            for s_name, s_path in self._services:
                screensaver_if = QDBusInterface(s_name, s_path, s_name, bus)

                if not screensaver_if.isValid():
                    logger.debug(f"DBus interface {s_name} is not valid")
                    continue

                return screensaver_if

            raise ValueError


elif SYSTEM == "Darwin":
    from gridplayer.utils.keepawake_macos import (
        assertNoIdleSleep,
        removeNoIdleSleepAssertion,
    )

    class KeepAwake(object):
        def __init__(self):
            self.is_screensaver_off = False

            self._assertion_id = None

        def screensaver_off(self):
            if self.is_screensaver_off:
                return

            logger.debug("Inhibiting screensaver")

            self._assertion_id = assertNoIdleSleep("Playing media")

            self.is_screensaver_off = True

        def screensaver_on(self):
            if not self.is_screensaver_off:
                return

            logger.debug("UnInhibiting screensaver")

            if self._assertion_id is None:
                logger.warning("Assertion ID is empty")
                return

            removeNoIdleSleepAssertion(self._assertion_id)

            self.is_screensaver_off = False


else:

    class KeepAwake(object):
        def __init__(self):
            self.is_screensaver_off = False

        def keepawake_on(self):
            if self.is_screensaver_off:
                return

            logger.debug("Inhibiting screensaver not supported")

            self.is_screensaver_off = True

        def keepawake_off(self):
            if not self.is_screensaver_off:
                return

            logger.debug("UnInhibiting screensaver not supported")

            self.is_screensaver_off = False
