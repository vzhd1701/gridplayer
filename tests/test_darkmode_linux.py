"""Asking the desktop portal, which can be there and still never answer."""

from types import SimpleNamespace

import pytest
from PyQt5.QtDBus import QDBusMessage, QDBusVariant

from gridplayer.utils import darkmode_linux

NO_REPLY = "org.freedesktop.DBus.Error.NoReply"
SERVICE_UNKNOWN = "org.freedesktop.DBus.Error.ServiceUnknown"


class _FakeReply:
    def __init__(self, arguments=(), error=None):
        self._arguments = list(arguments)
        self._error = error

    def type(self):
        if self._error:
            return QDBusMessage.ErrorMessage
        return QDBusMessage.ReplyMessage

    def errorName(self):
        return self._error or ""

    def errorMessage(self):
        return f"{self._error} happened" if self._error else ""

    def arguments(self):
        return self._arguments


class _FakeBus:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def isConnected(self):
        return True

    def call(self, message, mode, timeout):
        self.calls.append((message, timeout))
        return self.reply


@pytest.fixture(autouse=True)
def _portal_not_given_up_on(monkeypatch):
    monkeypatch.setattr(darkmode_linux, "_portal_is_silent", False)
    # the fallback when the portal says nothing, set on some desktops
    monkeypatch.delenv("GTK_THEME", raising=False)


def _bus(monkeypatch, reply):
    bus = _FakeBus(reply)
    monkeypatch.setattr(
        darkmode_linux, "QDBusConnection", SimpleNamespace(sessionBus=lambda: bus)
    )
    return bus


def test_an_answer_is_unwrapped(monkeypatch):
    _bus(monkeypatch, _FakeReply([QDBusVariant(QDBusVariant(1))]))

    assert darkmode_linux.portal_read("org.freedesktop.appearance", "color-scheme") == 1


def test_the_portal_is_asked_once_with_a_bounded_wait(monkeypatch):
    bus = _bus(monkeypatch, _FakeReply([QDBusVariant(1)]))

    darkmode_linux.portal_read("org.freedesktop.appearance", "color-scheme")

    [(message, timeout)] = bus.calls
    assert message.member() == "Read"
    assert message.arguments() == ["org.freedesktop.appearance", "color-scheme"]
    assert timeout == darkmode_linux._PORTAL_TIMEOUT_MS


def test_a_portal_that_does_not_answer_is_not_waited_on_again(monkeypatch):
    bus = _bus(monkeypatch, _FakeReply(error=NO_REPLY))

    assert darkmode_linux.linux_is_dark() is False
    assert darkmode_linux.linux_is_dark() is False

    assert len(bus.calls) == 1


def test_a_portal_that_is_not_there_is_asked_each_time(monkeypatch):
    """Being told there is none is as quick as an answer, nothing to save."""

    bus = _bus(monkeypatch, _FakeReply(error=SERVICE_UNKNOWN))

    darkmode_linux.portal_read("org.freedesktop.appearance", "color-scheme")
    darkmode_linux.portal_read("org.freedesktop.appearance", "color-scheme")

    assert len(bus.calls) == 2


def test_a_signal_from_the_portal_has_it_asked_again(monkeypatch):
    bus = _bus(monkeypatch, _FakeReply(error=NO_REPLY))
    darkmode_linux.portal_read("org.freedesktop.appearance", "color-scheme")

    darkmode_linux._PortalSink().setting_changed(
        "org.freedesktop.appearance", "color-scheme", QDBusVariant(1)
    )
    bus.reply = _FakeReply([QDBusVariant(1)])

    assert darkmode_linux.linux_is_dark() is True
    assert len(bus.calls) == 2
