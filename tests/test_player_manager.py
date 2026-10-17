import pytest
from PyQt5.QtCore import QEvent, QObject

from gridplayer.player.manager import Commands, Context, ManagersManager
from gridplayer.player.managers.base import ManagerBase


def test_context_returns_stored_value():
    ctx = Context()

    ctx.answer = 42

    assert ctx.answer == 42


def test_context_calls_callable_hooks():
    ctx = Context()
    calls = []

    def hook():
        calls.append(True)
        return "live"

    ctx.grid_state = hook

    assert ctx.grid_state == "live"
    assert calls == [True]


def test_context_missing_attribute_raises_attribute_error():
    ctx = Context()

    assert getattr(ctx, "missing", None) is None
    assert not hasattr(ctx, "missing")

    with pytest.raises(AttributeError):
        _ = ctx.missing


def test_commands_unknown_command_raises_key_error():
    commands = Commands()

    with pytest.raises(KeyError):
        _ = commands.unknown


class _Listener(ManagerBase):
    seen: list

    @property
    def event_map(self):
        return {QEvent.MouseMove: lambda: self.seen.append("move")}

    def eventFilter(self, event_object, event):
        self.seen.append(event.type())
        return super().eventFilter(event_object, event)


def _app_wide_listener():
    class Manager(ManagersManager):
        def __init__(self):
            super().__init__()
            self.managers = {"listener": _Listener}
            self.global_event_filters = ["listener"]
            self.init()

    manager = Manager()
    listener = manager._managers_inst["listener"]
    listener.seen = []
    return manager, listener


def test_a_global_filter_hears_what_it_answers_to():
    manager, listener = _app_wide_listener()

    manager.eventFilter(QObject(), QEvent(QEvent.MouseMove))

    assert listener.seen == [QEvent.MouseMove, "move"]


def test_a_global_filter_is_not_asked_about_anything_else():
    """Every event of the application comes by: a dialog being made sends
    tens of thousands, and asking each filter took half its opening time."""

    manager, listener = _app_wide_listener()

    for kind in (QEvent.ChildAdded, QEvent.Polish, QEvent.LayoutRequest):
        assert manager.eventFilter(QObject(), QEvent(kind)) is False

    assert listener.seen == []
