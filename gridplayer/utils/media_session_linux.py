"""MPRIS, the D-Bus interface Linux desktops send media keys through.

https://specifications.freedesktop.org/mpris-spec/latest/

GNOME and KDE take the media keys for themselves and give them only to an
MPRIS player, the window in focus included: without it the keys never
reach the player at all.
"""

import logging
import os

from PyQt5.QtCore import (
    Q_CLASSINFO,
    QMetaType,
    QObject,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusArgument,
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
)

from gridplayer.utils.media_session import (
    KEY_NEXT,
    KEY_PAUSE,
    KEY_PLAY,
    KEY_PLAY_PAUSE,
    KEY_PREVIOUS,
    KEY_STOP,
    MediaState,
    PlaybackStatus,
)
from gridplayer.version import __app_id__, __app_name__

OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_INTERFACE = "org.mpris.MediaPlayer2"
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"

# one name for each player running, as the spec has it
SERVICE_NAME = f"org.mpris.MediaPlayer2.{__app_name__.lower()}.instance{os.getpid()}"

# the one track there is: what the grid plays as a whole
TRACK_ID = "/com/vzhd1701/gridplayer/grid"

_STATUS_TEXT = {
    PlaybackStatus.PLAYING: "Playing",
    PlaybackStatus.PAUSED: "Paused",
    PlaybackStatus.STOPPED: "Stopped",
}

_log = logging.getLogger(__name__)


_ROOT_INTROSPECTION = f"""
  <interface name="{ROOT_INTERFACE}">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
"""


class _RootAdaptor(QDBusAbstractAdaptor):
    Q_CLASSINFO("D-Bus Interface", ROOT_INTERFACE)
    Q_CLASSINFO("D-Bus Introspection", _ROOT_INTROSPECTION)

    def __init__(self, session):
        super().__init__(session)

        self._session = session

    @pyqtSlot()
    def Raise(self):
        self._session.raise_requested.emit()

    @pyqtSlot()
    def Quit(self):
        """Not offered: CanQuit is false."""

    @pyqtProperty(bool)
    def CanQuit(self):
        return False

    @pyqtProperty(bool)
    def CanRaise(self):
        return True

    @pyqtProperty(bool)
    def HasTrackList(self):
        return False

    @pyqtProperty(str)
    def Identity(self):
        return __app_name__

    @pyqtProperty(str)
    def DesktopEntry(self):
        return __app_id__

    @pyqtProperty("QStringList")
    def SupportedUriSchemes(self):
        return []

    @pyqtProperty("QStringList")
    def SupportedMimeTypes(self):
        return []


_PLAYER_INTROSPECTION = f"""
  <interface name="{PLAYER_INTERFACE}">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg direction="in" name="Offset" type="x"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Metadata" type="a{{sv}}" access="read">
      <annotation name="org.qtproject.QtDBus.QtTypeName" value="QVariantMap"/>
    </property>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
"""


class _PlayerAdaptor(QDBusAbstractAdaptor):
    Q_CLASSINFO("D-Bus Interface", PLAYER_INTERFACE)
    Q_CLASSINFO("D-Bus Introspection", _PLAYER_INTROSPECTION)

    def __init__(self, session):
        super().__init__(session)

        self._session = session

    @pyqtSlot()
    def Next(self):
        self._session.command.emit(KEY_NEXT)

    @pyqtSlot()
    def Previous(self):
        self._session.command.emit(KEY_PREVIOUS)

    @pyqtSlot()
    def Pause(self):
        self._session.command.emit(KEY_PAUSE)

    @pyqtSlot()
    def PlayPause(self):
        self._session.command.emit(KEY_PLAY_PAUSE)

    @pyqtSlot()
    def Stop(self):
        self._session.command.emit(KEY_STOP)

    @pyqtSlot()
    def Play(self):
        self._session.command.emit(KEY_PLAY)

    # no seeking: a grid has no one place in time to seek in, CanSeek is false

    @pyqtSlot("qlonglong")
    def Seek(self, offset):
        """Not offered: CanSeek is false."""

    @pyqtSlot(QDBusObjectPath, "qlonglong")
    def SetPosition(self, track_id, position):
        """Not offered: CanSeek is false."""

    @pyqtProperty(str)
    def PlaybackStatus(self):
        return self._session.properties()["PlaybackStatus"]

    def _get_rate(self):
        return 1.0

    def _set_rate(self, rate):
        """The rate stays as it is: MinimumRate and MaximumRate are both 1."""

    Rate = pyqtProperty(float, fget=_get_rate, fset=_set_rate)

    @pyqtProperty("QVariantMap")
    def Metadata(self):
        return self._session.properties()["Metadata"]

    @pyqtProperty("qlonglong")
    def Position(self):
        return 0

    @pyqtProperty(float)
    def MinimumRate(self):
        return 1.0

    @pyqtProperty(float)
    def MaximumRate(self):
        return 1.0

    @pyqtProperty(bool)
    def CanGoNext(self):
        return self._session.properties()["CanGoNext"]

    @pyqtProperty(bool)
    def CanGoPrevious(self):
        return self._session.properties()["CanGoPrevious"]

    @pyqtProperty(bool)
    def CanPlay(self):
        return self._session.properties()["CanPlay"]

    @pyqtProperty(bool)
    def CanPause(self):
        return self._session.properties()["CanPause"]

    @pyqtProperty(bool)
    def CanSeek(self):
        return False

    @pyqtProperty(bool)
    def CanControl(self):
        return True


class MprisSession(QObject):
    command = pyqtSignal(str)
    raise_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = None
        self._is_named = False

        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            raise RuntimeError("No D-Bus session bus")

        self._root = _RootAdaptor(self)
        self._player = _PlayerAdaptor(self)

        if not self._bus.registerObject(OBJECT_PATH, self):
            raise RuntimeError(f"Cannot register {OBJECT_PATH} on D-Bus")

    def update(self, state: MediaState | None):
        if state is None:
            self._state = None
            self._set_named(False)
            return

        changed = self._changed_properties(self._state, state)
        self._state = state

        # the player turns up once there is something to tell about it
        if not self._is_named:
            self._set_named(True)
        elif changed:
            self._send_properties_changed(changed)

    def close(self):
        self._set_named(False)
        self._bus.unregisterObject(OBJECT_PATH)

    def properties(self) -> dict:
        """The Player interface's properties that change, as D-Bus has them."""

        return self._properties(self._state)

    def _properties(self, state: MediaState | None) -> dict:
        status = PlaybackStatus.STOPPED if state is None else state.status
        keys = frozenset() if state is None else state.keys

        metadata = {"mpris:trackid": QDBusObjectPath(TRACK_ID)}
        if state is not None:
            metadata["xesam:title"] = state.title

        return {
            "PlaybackStatus": _STATUS_TEXT[status],
            "Metadata": metadata,
            "CanGoNext": KEY_NEXT in keys,
            "CanGoPrevious": KEY_PREVIOUS in keys,
            "CanPlay": bool(keys & {KEY_PLAY, KEY_PLAY_PAUSE}),
            "CanPause": bool(keys & {KEY_PAUSE, KEY_PLAY_PAUSE}),
        }

    def _changed_properties(self, old, new) -> dict:
        old_properties = self._properties(old)
        new_properties = self._properties(new)

        changed = {
            name: value
            for name, value in new_properties.items()
            if name != "Metadata" and old_properties[name] != value
        }

        is_new_title = old is None or old.title != new.title
        if is_new_title:
            changed["Metadata"] = new_properties["Metadata"]

        return changed

    def _send_properties_changed(self, changed: dict):
        message = QDBusMessage.createSignal(
            OBJECT_PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged"
        )
        message.setArguments(
            [
                PLAYER_INTERFACE,
                changed,
                # a plain list goes over as av, the spec's is as
                QDBusArgument([], QMetaType.QStringList),
            ]
        )
        self._bus.send(message)

    def _set_named(self, is_named: bool):
        if is_named == self._is_named:
            return

        if is_named:
            is_done = self._bus.registerService(SERVICE_NAME)
        else:
            is_done = self._bus.unregisterService(SERVICE_NAME)

        if not is_done:
            error = self._bus.lastError().message()
            _log.warning(f"D-Bus name {SERVICE_NAME} not changed: {error}")
            return

        self._is_named = is_named
