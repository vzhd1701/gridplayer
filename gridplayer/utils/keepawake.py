import logging
from enum import Enum, auto

from gridplayer.params import env
from gridplayer.version import __app_name__

logger = logging.getLogger(__name__)

INHIBIT_REASON = "Playing media."


class KeepAwakeMode(Enum):
    # the system may sleep and the screen go off as they like
    NONE = auto()
    # the system kept awake, for sound playing with nothing to watch
    SLEEP = auto()
    # the screen kept on as well, and with it the system
    SCREEN = auto()


if env.IS_WINDOWS:
    import ctypes

    SetThreadExecutionState = ctypes.windll.kernel32.SetThreadExecutionState
    SystemParametersInfo = ctypes.windll.user32.SystemParametersInfoW

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    SPI_SETSCREENSAVEACTIVE = 0x0011

    _FLAGS = {
        KeepAwakeMode.NONE: ES_CONTINUOUS,
        KeepAwakeMode.SLEEP: ES_CONTINUOUS | ES_SYSTEM_REQUIRED,
        KeepAwakeMode.SCREEN: ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED,
    }

    class KeepAwake:
        def __init__(self):
            self.mode = KeepAwakeMode.NONE

        def set_mode(self, mode: KeepAwakeMode):
            if mode == self.mode:
                return

            logger.debug(f"Keep awake: {mode.name}")

            SetThreadExecutionState(_FLAGS[mode])

            is_screen = mode == KeepAwakeMode.SCREEN
            if is_screen != (self.mode == KeepAwakeMode.SCREEN):
                self._set_screensaver_active(not is_screen)

            self.mode = mode

        def _set_screensaver_active(self, is_active):
            res = SystemParametersInfo(SPI_SETSCREENSAVEACTIVE, int(is_active), None, 0)

            if res != 1:
                logger.warning(f"SystemParametersInfo({is_active}) failed")


elif env.IS_LINUX:
    from PyQt5.QtCore import QMetaType
    from PyQt5.QtDBus import (
        QDBusArgument,
        QDBusConnection,
        QDBusInterface,
        QDBusObjectPath,
    )

    # Inhibit's flag for suspending, see org.freedesktop.portal.Inhibit and
    # org.gnome.SessionManager
    _INHIBIT_SUSPEND = 4

    def _uint(value):
        argument = QDBusArgument()
        argument.add(value, QMetaType.UInt)
        return argument

    def _dbus_call(interface, *args):
        reply = interface.call(*args)

        if reply.errorName():
            logger.debug(f"DBus Error: {reply.errorName()}")
            logger.debug(f"DBus Error Message: {reply.errorMessage()}")
            return None

        arguments = reply.arguments()

        return arguments[0] if arguments else None

    def _session_bus():
        bus = QDBusConnection.sessionBus()

        if not bus.isConnected():
            logger.warning("DBus failed to connected")
            return None

        return bus

    class _ScreenInhibitor:
        """The screen saver held off, and with it the system's sleep."""

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
            self._interface = None
            self._cookie = None

            bus = _session_bus()
            if bus is None:
                return

            for s_name, s_path in self._services:
                interface = QDBusInterface(s_name, s_path, s_name, bus)

                if not interface.isValid():
                    logger.debug(f"DBus interface {s_name} is not valid")
                    continue

                self._interface = interface
                return

        def acquire(self):
            if self._interface is None:
                logger.warning("DBus interface is not initialized")
                return

            self._cookie = _dbus_call(
                self._interface, "Inhibit", __app_name__, INHIBIT_REASON
            )
            logger.debug(f"New DBus Cookie: {self._cookie}")

        def release(self):
            if self._interface is None or self._cookie is None:
                return

            _dbus_call(self._interface, "UnInhibit", _uint(self._cookie))

            self._cookie = None

    class _SleepInhibitor:
        """The system's sleep held off, the screen left to go off.

        KDE and GNOME first, by their own: GNOME's portal takes the request
        and answers, and no inhibitor turns up for it. The portal for the
        rest, and in a Flatpak, which has no way to the other two.
        """

        def __init__(self):
            self._release = None

        def acquire(self):
            bus = _session_bus()
            if bus is None:
                return

            for acquire in (self._kde, self._gnome, self._portal):
                self._release = acquire(bus)
                if self._release is not None:
                    return

            logger.warning("Nothing to keep the system awake with")

        def release(self):
            if self._release is not None:
                self._release()
                self._release = None

        def _portal(self, bus):
            interface = QDBusInterface(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Inhibit",
                bus,
            )
            if not interface.isValid():
                return None

            handle = _dbus_call(
                interface,
                "Inhibit",
                "",
                _uint(_INHIBIT_SUSPEND),
                {"reason": INHIBIT_REASON},
            )
            if handle is None:
                return None

            if isinstance(handle, QDBusObjectPath):
                handle = handle.path()

            def release():
                request = QDBusInterface(
                    "org.freedesktop.portal.Desktop",
                    handle,
                    "org.freedesktop.portal.Request",
                    bus,
                )
                _dbus_call(request, "Close")

            return release

        def _kde(self, bus):
            interface = QDBusInterface(
                "org.freedesktop.PowerManagement.Inhibit",
                "/org/freedesktop/PowerManagement/Inhibit",
                "org.freedesktop.PowerManagement.Inhibit",
                bus,
            )
            if not interface.isValid():
                return None

            cookie = _dbus_call(interface, "Inhibit", __app_name__, INHIBIT_REASON)
            if cookie is None:
                return None

            return lambda: _dbus_call(interface, "UnInhibit", _uint(cookie))

        def _gnome(self, bus):
            interface = QDBusInterface(
                "org.gnome.SessionManager",
                "/org/gnome/SessionManager",
                "org.gnome.SessionManager",
                bus,
            )
            if not interface.isValid():
                return None

            cookie = _dbus_call(
                interface,
                "Inhibit",
                __app_name__,
                _uint(0),
                INHIBIT_REASON,
                _uint(_INHIBIT_SUSPEND),
            )
            if cookie is None:
                return None

            return lambda: _dbus_call(interface, "Uninhibit", _uint(cookie))

    class KeepAwake:
        def __init__(self):
            self.mode = KeepAwakeMode.NONE

            self._inhibitors = {
                KeepAwakeMode.SLEEP: _SleepInhibitor(),
                KeepAwakeMode.SCREEN: _ScreenInhibitor(),
            }

        def set_mode(self, mode: KeepAwakeMode):
            if mode == self.mode:
                return

            logger.debug(f"Keep awake: {mode.name}")

            # the new one held before the old one is let go, leaving no gap
            if mode != KeepAwakeMode.NONE:
                self._inhibitors[mode].acquire()

            if self.mode != KeepAwakeMode.NONE:
                self._inhibitors[self.mode].release()

            self.mode = mode


elif env.IS_MACOS:
    from gridplayer.utils.keepawake_macos import (
        ASSERTION_NO_DISPLAY_SLEEP,
        ASSERTION_NO_IDLE_SLEEP,
        assertNoIdleSleep,
        removeNoIdleSleepAssertion,
    )

    _ASSERTIONS = {
        KeepAwakeMode.SLEEP: ASSERTION_NO_IDLE_SLEEP,
        KeepAwakeMode.SCREEN: ASSERTION_NO_DISPLAY_SLEEP,
    }

    class KeepAwake:
        def __init__(self):
            self.mode = KeepAwakeMode.NONE

            self._assertion_id = None

        def set_mode(self, mode: KeepAwakeMode):
            if mode == self.mode:
                return

            logger.debug(f"Keep awake: {mode.name}")

            old_assertion_id = self._assertion_id
            self._assertion_id = None

            # the new one held before the old one is let go, leaving no gap
            if mode != KeepAwakeMode.NONE:
                self._assertion_id = assertNoIdleSleep(
                    INHIBIT_REASON, _ASSERTIONS[mode]
                )

            removeNoIdleSleepAssertion(old_assertion_id)

            self.mode = mode


else:

    class KeepAwake:
        def __init__(self):
            self.mode = KeepAwakeMode.NONE

        def set_mode(self, mode: KeepAwakeMode):
            if mode != self.mode:
                logger.debug("Keeping awake not supported")

            self.mode = mode
