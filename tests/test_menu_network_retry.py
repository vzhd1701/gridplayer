"""The On Network Error submenu: what it shows, and when it shows it."""

from functools import partial
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.params.static import NetworkRetryMode
from gridplayer.player.manager import Commands
from gridplayer.player.managers.actions import ActionsManager

SUBMENU = "On Network Error"

MODE_ITEMS = {
    "On Network Error Show Error": NetworkRetryMode.OFF,
    "On Network Error Retry Times": NetworkRetryMode.TIMES,
    "On Network Error Retry Forever": NetworkRetryMode.INFINITE,
}

ATTEMPTS_ITEM = "On Network Error Attempts: %v"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _action(name, mode=NetworkRetryMode.TIMES, is_local_file=False, times="3"):
    commands = Commands()
    commands.update(
        {
            "active": lambda command, *args: times,
            "is_active_local_file": lambda: is_local_file,
            "is_active_param_set_to": lambda attr, value: mode == value,
        }
    )

    manager = Mock(spec=ActionsManager)
    manager._ctx = Mock()
    manager._ctx.commands = commands
    manager.parent = Mock(return_value=None)
    manager._map_dynamic_functions = partial(
        ActionsManager._map_dynamic_functions, manager
    )

    return ActionsManager._make_action(manager, ACTIONS[name])


def _video_menu_submenus():
    return [item[0] for item in SECTIONS["video_active"] if isinstance(item, tuple)]


def test_the_submenu_sits_with_reload_rather_than_with_the_quality_ladder():
    section = SECTIONS["video_active"]

    assert SUBMENU in _video_menu_submenus()
    assert SUBMENU in SUBMENUS

    names = [item[0] if isinstance(item, tuple) else item for item in section]

    assert names[names.index("Auto Reload: %v") + 1] == SUBMENU


def test_the_submenu_lists_every_mode_and_the_count():
    entry = next(item for item in SECTIONS["video_active"] if item[0] == SUBMENU)

    assert list(entry[1:]) == [*MODE_ITEMS, "---", ATTEMPTS_ITEM]


@pytest.mark.parametrize(("name", "mode"), MODE_ITEMS.items())
def test_the_mode_in_force_is_the_one_ticked(name, mode):
    for candidate in MODE_ITEMS.values():
        action = _action(name, mode=candidate)
        action.adapt()

        assert action.isChecked() is (candidate is mode)


def test_the_count_spells_itself_out():
    action = _action(ATTEMPTS_ITEM, times="7")
    action.adapt()

    assert action.text() == "Attempts: 7"


def test_the_count_is_hidden_unless_the_mode_uses_one():
    assert _action(ATTEMPTS_ITEM, mode=NetworkRetryMode.TIMES).is_skipped is False
    assert _action(ATTEMPTS_ITEM, mode=NetworkRetryMode.OFF).is_skipped is True
    assert _action(ATTEMPTS_ITEM, mode=NetworkRetryMode.INFINITE).is_skipped is True


@pytest.mark.parametrize("name", [*MODE_ITEMS, ATTEMPTS_ITEM])
def test_a_file_on_disk_has_no_network_to_fail(name):
    assert _action(name, is_local_file=True).is_skipped is True


def test_the_divider_goes_when_the_count_below_it_does():
    from PyQt5.QtWidgets import QMenu

    from gridplayer.player.managers.menu import _strip_trailing_separator

    menu = QMenu()
    menu.addAction("Keep Reloading")
    menu.addSeparator()

    _strip_trailing_separator(menu)

    assert [a.isSeparator() for a in menu.actions()] == [False]


def test_a_divider_with_something_under_it_stays():
    from PyQt5.QtWidgets import QMenu

    from gridplayer.player.managers.menu import _strip_trailing_separator

    menu = QMenu()
    menu.addAction("Keep Reloading")
    menu.addSeparator()
    menu.addAction("Attempts: 3")

    _strip_trailing_separator(menu)

    assert [a.isSeparator() for a in menu.actions()] == [False, True, False]
