"""The Subtitle Delay submenu: where it sits, what it is bound to, where it leads."""

from functools import partial
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.player.manager import Commands
from gridplayer.player.managers.actions import ActionsManager
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.widgets.video_block import VideoBlock

SUBMENU = "Subtitle Delay"

ACTIVE_ROWS = [
    "Subtitle Delay: %v",
    "---",
    "Subtitle Delay Later",
    "Subtitle Delay Earlier",
    "Subtitle Delay Reset",
]

ALL_ROWS = [
    "Subtitle Delay Set [ALL]",
    "---",
    "Subtitle Delay Later [ALL]",
    "Subtitle Delay Earlier [ALL]",
    "Subtitle Delay Reset [ALL]",
]


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _submenu(section, *path):
    """The submenu at the end of a path of submenu names."""

    branch = SECTIONS[section]

    for name in path:
        branch = next(
            item for item in branch if isinstance(item, tuple) and item[0] == name
        )

    return branch


def _action(name, has_subtitles=True, delay="+150 ms"):
    commands = Commands()
    commands.update(
        {
            "active": lambda command, *args: delay,
            "is_active_has_subtitles": lambda: has_subtitles,
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


class TestWhereItSits:
    def test_it_is_a_submenu_of_its_own_with_an_icon(self):
        assert SUBMENUS[SUBMENU]["icon"]

    def test_it_follows_the_track_list_rather_than_joining_it(self):
        subtitles = _submenu("video_active", "Subtitles")
        names = [item[0] if isinstance(item, tuple) else item for item in subtitles]

        assert names[names.index("Subtitle Track") + 1] == SUBMENU

    def test_it_lists_the_readout_then_the_three_moves(self):
        assert list(_submenu("video_active", "Subtitles", SUBMENU)[1:]) == ACTIVE_ROWS

    def test_every_video_at_once_gets_the_same_submenu(self):
        all_subtitles = _submenu("video_all", "[ALL]", "Subtitles")
        delay = next(
            item
            for item in all_subtitles
            if isinstance(item, tuple) and item[0] == SUBMENU
        )

        assert list(delay[1:]) == ALL_ROWS


class TestWhatItIsBoundTo:
    """G and H, which is what VLC moves subtitles with.

    They sit immediately left of the J and K the sound is moved with, in
    the same order, so the two pairs read across the home row as
    subtitle-earlier, subtitle-later, audio-earlier, audio-later.
    """

    @pytest.mark.parametrize(
        ("name", "key"),
        [
            ("Subtitle Delay Earlier", "G"),
            ("Subtitle Delay Later", "H"),
            ("Subtitle Delay Earlier [ALL]", "Shift+G"),
            ("Subtitle Delay Later [ALL]", "Shift+H"),
        ],
    )
    def test_the_key_it_answers_to(self, name, key):
        assert ACTIONS[name]["key"] == key

    def test_earlier_and_later_sit_the_same_way_round_as_the_sound(self):
        """Left is earlier and right is later, for both pairs."""

        pairs = [
            ("Audio Delay Earlier", "Audio Delay Later"),
            ("Subtitle Delay Earlier", "Subtitle Delay Later"),
        ]

        for earlier, later in pairs:
            assert ACTIONS[earlier]["func"][1].endswith("decrease")
            assert ACTIONS[later]["func"][1].endswith("increase")
            assert ACTIONS[earlier]["key"] < ACTIONS[later]["key"]


class TestWhereTheRowsLead:
    """A row pointing at nothing fails silently at the click."""

    @pytest.mark.parametrize("name", [row for row in ACTIVE_ROWS if row != "---"])
    def test_an_active_row_names_something_a_video_can_do(self, name):
        action = ACTIONS[name]

        assert action["func"][0] == "active"
        assert hasattr(VideoBlock, action["func"][1])
        assert hasattr(ActiveBlockManager, action["show_if"])

        if action.get("value_getter"):
            assert hasattr(VideoBlock, action["value_getter"][1])

    @pytest.mark.parametrize("name", [row for row in ALL_ROWS if row != "---"])
    def test_an_all_row_names_something_every_video_can_do(self, name):
        action = ACTIONS[name]
        func = action["func"]

        assert hasattr(VideoBlocksManager, action["show_if"])

        if isinstance(func, tuple):
            assert func[0] == "all"
            # cmd_all emits all_<command> at every block's method of that name
            assert hasattr(VideoBlocksManager, f"all_{func[1]}")
            assert hasattr(VideoBlock, func[1])
        else:
            assert hasattr(VideoBlocksManager, func)
            assert hasattr(VideoBlocksManager, "cmd_set_subtitle_delay")


class TestWhatTheRowsSay:
    def test_the_readout_carries_the_delay_in_force(self):
        action = _action("Subtitle Delay: %v", delay="+150 ms")
        action.adapt()

        assert action.text() == "Delay: +150 ms"

    @pytest.mark.parametrize("name", [row for row in ACTIVE_ROWS if row != "---"])
    def test_a_video_with_no_subtitles_has_nothing_to_move(self, name):
        assert _action(name, has_subtitles=False).is_skipped is True
        assert _action(name, has_subtitles=True).is_skipped is False
