"""A command may name a method of a part of the video block, "part.method",
as well as one of the block itself."""

import ast
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

import gridplayer
from gridplayer.player.managers.active_block import (
    LOADING_COMMANDS,
    QUIETLY_DROPPED_COMMANDS,
    ActiveBlockManager,
)
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.widgets.video_block import VideoBlock
from tests.conftest import is_block_command

PACKAGE = Path(gridplayer.__file__).parent

# these run another command of the block, named in their first argument
FORWARDING = frozenset({"manual_seek", "manual_view", "manual_rate"})


def _sources():
    for path in sorted(PACKAGE.rglob("*.py")):
        # compiled resources, nothing in them names a command
        if "resources" in path.relative_to(PACKAGE).parts:
            continue

        yield path.relative_to(PACKAGE), ast.parse(path.read_text("utf-8"))


def _literal_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    return None


def _named_commands():
    """Each command a menu, a key or a dialog names for a video block, as
    ("active", name), ("all", name) or block.manual_seek(name), with where
    it was named.

    A misspelt one is no error until it is chosen, and then it is only a
    menu item doing nothing.
    """

    active, everyone = defaultdict(list), defaultdict(list)

    for path, tree in _sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple) and len(node.elts) >= 2:
                kind, name = map(_literal_str, node.elts[:2])

                if name is None:
                    continue

                if kind == "active":
                    active[name].append(f"{path}:{node.lineno}")

                    forwarded = node.elts[2:3]
                    target = _literal_str(forwarded[0]) if forwarded else None
                    if name in FORWARDING and target is not None:
                        active[target].append(f"{path}:{node.lineno}")

                elif kind == "all":
                    everyone[name].append(f"{path}:{node.lineno}")

            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FORWARDING
                and node.args
            ):
                target = _literal_str(node.args[0])
                if target is not None:
                    active[target].append(f"{path}:{node.lineno}")

    return dict(sorted(active.items())), dict(sorted(everyone.items()))


def _all_signal_wiring():
    """(signal, block command) as VideoBlocksManager connects each new block
    to the commands it sends to all of them: (self.all_x, vb.part.method)."""

    source = PACKAGE / "player" / "managers" / "video_blocks.py"
    tree = ast.parse(source.read_text("utf-8"))

    wiring = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Tuple) and len(node.elts) == 2):
            continue

        signal, slot = map(ast.unparse, node.elts)
        if signal.startswith("self.all_") and slot.startswith("vb."):
            wiring.append((signal.removeprefix("self."), slot.removeprefix("vb.")))

    return wiring


ACTIVE_COMMANDS, ALL_COMMANDS = _named_commands()
ALL_SIGNAL_WIRING = _all_signal_wiring()


def test_the_named_commands_are_found_at_all():
    # a walk that finds nothing passes every test below
    assert len(ACTIVE_COMMANDS) > 50
    assert len(ALL_COMMANDS) > 30
    assert len(ALL_SIGNAL_WIRING) > 30


@pytest.mark.parametrize("command", ACTIVE_COMMANDS)
def test_a_command_named_for_the_active_block_is_there(command):
    assert is_block_command(command), f"named at {ACTIVE_COMMANDS[command]}"


@pytest.mark.parametrize("command", sorted(LOADING_COMMANDS | QUIETLY_DROPPED_COMMANDS))
def test_a_command_let_through_while_loading_is_there(command):
    # one that is not would leave its menu item dropped while loading
    assert is_block_command(command)


@pytest.mark.parametrize("command", ALL_COMMANDS)
def test_a_command_named_for_all_blocks_has_a_signal(command):
    assert hasattr(VideoBlocksManager, f"all_{command}"), (
        f"named at {ALL_COMMANDS[command]}"
    )


@pytest.mark.parametrize(
    ("signal", "command"), ALL_SIGNAL_WIRING, ids=[s for s, _ in ALL_SIGNAL_WIRING]
)
def test_a_signal_to_all_blocks_reaches_a_block_command(signal, command):
    assert is_block_command(command)


def _active_manager(block):
    manager = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    manager._ctx.active_block = block
    return manager


def _playing_block(mocker):
    block = mocker.Mock()
    block.is_video_initialized = True
    block.is_playable = True
    block.is_live = False
    block.position = 0.5
    block.video_driver.length = 10_000
    block.video_params.rate = 1.5
    return block


def test_cmd_active_reaches_a_part_of_the_block(mocker):
    block = _playing_block(mocker)
    block.bookmarker.seek.return_value = "sought"

    result = _active_manager(block).cmd_active("bookmarker.seek", 3)

    block.bookmarker.seek.assert_called_once_with(3)
    assert result == "sought"


def test_cmd_active_still_takes_a_plain_name(mocker):
    block = _playing_block(mocker)

    _active_manager(block).cmd_active("reload")

    block.reload.assert_called_once_with()


def test_cmd_active_drops_a_dotted_command_while_loading(mocker):
    block = _playing_block(mocker)
    block.is_playable = False

    _active_manager(block).cmd_active("bookmarker.next")

    block.bookmarker.next.assert_not_called()


def test_runtime_param_reaches_a_part_of_the_block(mocker):
    block = _playing_block(mocker)
    block.bookmarker.count = 2
    manager = _active_manager(block)

    assert manager.is_active_runtime_param_set_to("bookmarker.count", 2)
    assert not manager.is_active_runtime_param_set_to("bookmarker.count", 3)


def test_manual_seek_reaches_a_part_and_syncs_the_others(mocker):
    block = _playing_block(mocker)

    VideoBlock.manual_seek(block, "bookmarker.seek", 3)

    block.bookmarker.seek.assert_called_once_with(3)
    block.sync_percent.emit.assert_called_once_with(0.5)
    block.sync_time.emit.assert_called_once_with(5000)


def test_manual_seek_of_a_part_that_went_nowhere_syncs_nothing(mocker):
    block = _playing_block(mocker)
    block.bookmarker.seek.return_value = False

    VideoBlock.manual_seek(block, "bookmarker.seek", 3)

    block.sync_percent.emit.assert_not_called()
    block.sync_time.emit.assert_not_called()


def test_manual_view_reaches_a_part_and_gives_back_its_result(mocker):
    block = _playing_block(mocker)
    block.view.pan_by.return_value = (1.0, 2.0)
    block.view.synced.return_value = "synced"

    result = VideoBlock.manual_view(block, "view.pan_by", 3, 4)

    block.view.pan_by.assert_called_once_with(3, 4)
    block.sync_view.emit.assert_called_once_with("synced")
    assert result == (1.0, 2.0)


def test_manual_rate_reaches_a_part_and_syncs_the_others(mocker):
    block = _playing_block(mocker)

    VideoBlock.manual_rate(block, "rate.increase")

    block.rate.increase.assert_called_once_with()
    block.sync_rate.emit.assert_called_once_with(1.5)
