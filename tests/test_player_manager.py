from gridplayer.player.manager import Commands, Context


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

    try:
        ctx.missing
    except AttributeError:
        pass
    else:
        raise AssertionError("AttributeError not raised")


def test_commands_unknown_command_raises_key_error():
    commands = Commands()

    try:
        commands.unknown
    except KeyError:
        pass
    else:
        raise AssertionError("KeyError not raised")
