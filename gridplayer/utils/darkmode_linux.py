import logging
import os

from PyQt5.QtCore import QObject, QTimer, pyqtSlot
from PyQt5.QtDBus import QDBusConnection, QDBusInterface, QDBusVariant

logger = logging.getLogger(__name__)

_PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.Settings"
_PORTAL_NS = "org.freedesktop.appearance"
_PORTAL_KEY = "color-scheme"
_PORTAL_PREFER_DARK = 1
_PORTAL_PREFER_LIGHT = 2

_RETRY_MS = 50
_RETRY_MAX = 16


def linux_is_dark() -> bool:
    """Cross-DE dark mode detection, in order of trust.

    1. XDG desktop portal 'color-scheme' (org.freedesktop.appearance).
       This is the only value that's actually part of the portal spec and
       is implemented by both xdg-desktop-portal-gnome and
       xdg-desktop-portal-kde, so it's what we trust when present.
    2. GTK_THEME env var, last resort.
    3. False (assume light) -- we deliberately do NOT fall back to the
       app's own QPalette, since after apply_theme() it only reflects
       whatever scheme we last set, and would trap us in that scheme.
    """
    scheme = _portal_color_scheme()
    if scheme == _PORTAL_PREFER_DARK:
        return True
    if scheme == _PORTAL_PREFER_LIGHT:
        return False
    if scheme is not None:
        # Portal responded but with neither 1 nor 2 (i.e. 0 / "no preference").
        return False

    gtk_theme = os.environ.get("GTK_THEME", "")
    if gtk_theme and "dark" in gtk_theme.lower():
        return True

    return False


def _unwrap_dbus(value):
    while isinstance(value, QDBusVariant):
        value = value.variant()
    return value


def _portal_read(namespace: str, key: str):
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None

    iface = QDBusInterface(_PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE, bus)
    if not iface.isValid():
        return None

    reply = iface.call("Read", namespace, key)
    if reply.errorName():
        logger.debug("Portal Read %s %s: %s", namespace, key, reply.errorMessage())
        return None

    args = reply.arguments()
    if not args:
        return None

    return _unwrap_dbus(args[0])


def _portal_color_scheme() -> "int | None":
    value = _portal_read(_PORTAL_NS, _PORTAL_KEY)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.debug("Portal color-scheme: unexpected value %r", value)
        return None


# Bind slots at runtime so a bad QDBusVariant pyqtSlot cannot
# crash the process at import (see older PyQt SLOT/"QDBusVariant").
class _PortalSink(QObject):
    @pyqtSlot(str, str, QDBusVariant)
    def setting_changed(self, namespace, key, value):
        watcher = self.parent()
        if watcher is None:
            return

        if namespace == _PORTAL_NS and key == _PORTAL_KEY:
            raw = _unwrap_dbus(value)
            try:
                scheme = int(raw)
            except (TypeError, ValueError):
                scheme = None

            # Signal payload is definitive -- no need to poll.
            if scheme == _PORTAL_PREFER_DARK:
                watcher._apply_if_changed(True)
                return
            if scheme == _PORTAL_PREFER_LIGHT:
                watcher._apply_if_changed(False)
                return
            watcher._apply_if_changed(False)
            return

        # Any other appearance/interface-related change:
        # payload doesn't map directly to light/dark, so
        # re-check via is_dark_mode() with brief retries.
        if key in {"color-scheme", "gtk-theme"} or namespace == _PORTAL_NS:
            watcher._on_ambiguous_signal()


class LinuxThemeWatcher(QObject):
    def __init__(self, callback, parent=None):
        super().__init__(parent)

        self._callback = callback
        self._applied_dark = linux_is_dark()
        self._retries_left = 0

        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(_RETRY_MS)
        self._retry.timeout.connect(self._try_apply)

        self._connect_dbus()

    def _apply_if_changed(self, dark: bool) -> None:
        if dark == self._applied_dark:
            return
        self._applied_dark = dark
        self._callback()

    def _on_ambiguous_signal(self):
        # Used only when the signal payload didn't tell us the new
        # scheme directly (e.g. gtk-theme changed) -- poll briefly
        # since the underlying setting may not have committed yet.
        self._retries_left = _RETRY_MAX
        self._try_apply()

    def _try_apply(self):
        dark = linux_is_dark()
        if dark != self._applied_dark:
            self._applied_dark = dark
            self._callback()
            return

        if self._retries_left > 0:
            self._retries_left -= 1
            self._retry.start()

    def _connect_dbus(self):
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return

        self._portal_sink = _PortalSink(self)
        if not bus.connect(
            _PORTAL_SERVICE,
            _PORTAL_PATH,
            _PORTAL_IFACE,
            "SettingChanged",
            self._portal_sink.setting_changed,
        ):
            logger.debug("Could not subscribe to portal SettingChanged")
