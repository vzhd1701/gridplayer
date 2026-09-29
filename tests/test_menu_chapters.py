"""Where the chapter actions live: the menu, the keymap, and every video at once."""

from types import SimpleNamespace

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtWidgets import QAction

from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS
from gridplayer.player.managers.actions import QDynamicAction
from gridplayer.player.managers.menu import MenuManager, _add_inline_actions
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.widgets.custom_menu import CustomMenu
from gridplayer.widgets.keymap_tree_view import DATA_ACTION_ID, fill_keymap_model
from gridplayer.widgets.video_block import VideoBlock

CHAPTER_ACTIONS = (
    "Previous Chapter",
    "Next Chapter",
    "Loop Chapter",
    "Previous Chapter [ALL]",
    "Next Chapter [ALL]",
    "Loop Chapter [ALL]",
)


def _submenu(items, *path):
    for name in path:
        items = next(i for i in items if isinstance(i, tuple) and i[0] == name)[1:]

    return list(items)


class TestWhereTheyAre:
    def test_chapters_sit_in_playback_with_the_list_under_the_jumps(self):
        chapters = _submenu(SECTIONS["video_active"], "Playback", "Chapters")

        assert chapters == ["Previous Chapter", "Next Chapter", "---", "Chapter List"]

    def test_chapters_come_right_after_the_other_jumps(self):
        playback = _submenu(SECTIONS["video_active"], "Playback")
        names = [item[0] for item in playback if isinstance(item, tuple)]

        assert names.index("Chapters") == names.index("Jump (to)") + 1

    def test_loop_chapter_is_with_the_rest_of_the_loop(self):
        loop = _submenu(SECTIONS["video_active"], "Playback", "Loop")

        assert loop.index("Loop Chapter") == loop.index("Loop Reset") - 1

    def test_every_video_at_once_can_jump_and_loop_but_has_no_list(self):
        playback = _submenu(SECTIONS["video_all"], "[ALL]", "Playback")

        assert _submenu(playback, "Chapters") == [
            "Previous Chapter [ALL]",
            "Next Chapter [ALL]",
        ]
        assert "Loop Chapter [ALL]" in _submenu(playback, "Loop")


class TestTheirKeys:
    def test_none_come_with_a_key(self):
        """Whoever hops chapters picks the keys for it."""

        for name in CHAPTER_ACTIONS:
            assert "key" not in ACTIONS[name], name
            assert "keys" not in ACTIONS[name], name

    def test_all_can_be_given_one_in_the_keymap(self):
        model = QStandardItemModel()
        fill_keymap_model(model)

        action_ids = set()
        pending = [model.item(row) for row in range(model.rowCount())]

        while pending:
            item = pending.pop()
            action_ids.add(item.data(DATA_ACTION_ID))
            pending += [item.child(row) for row in range(item.rowCount())]

        assert set(CHAPTER_ACTIONS) <= action_ids
        # a list of the chapters of one file is nothing to bind a key to
        assert "Chapter List" not in action_ids


class TestWhatTheyCall:
    def test_the_active_video_has_what_they_call(self):
        for name in ("Previous Chapter", "Next Chapter", "Loop Chapter"):
            func = ACTIONS[name]["func"]
            method = func[2] if func[1] == "manual_seek" else func[1]

            assert hasattr(VideoBlock, method), name

    def test_every_video_is_wired_up_for_them(self):
        for name in (
            "Previous Chapter [ALL]",
            "Next Chapter [ALL]",
            "Loop Chapter [ALL]",
        ):
            command = ACTIONS[name]["func"][1]

            assert hasattr(VideoBlocksManager, f"all_{command}"), name
            assert hasattr(VideoBlock, command), name

    def test_jumps_on_the_active_video_are_seeks_the_others_follow(self):
        for name in ("Previous Chapter", "Next Chapter"):
            assert ACTIONS[name]["func"][1] == "manual_seek", name


def _action(title, parent=None):
    return QDynamicAction(title=title, icon_id="empty", parent=parent)


def _inline_list(*titles, is_shown=True):
    action = _action("Chapters")
    action.is_menu_inline = True
    action.show_if = lambda: is_shown
    action.menu_generator = lambda parent=None: [_action(t, parent) for t in titles]

    return action


class TestTheListGoesStraightIntoTheMenu:
    def test_the_rows_follow_the_actions_before_them(self):
        menu = CustomMenu()
        menu.addAction(QAction("Previous Chapter", menu))

        _add_inline_actions(_inline_list("Opening\t00:00", "Heist\t00:25"), menu)

        assert [a.text() for a in menu.actions()] == [
            "Previous Chapter",
            "Opening\t00:00",
            "Heist\t00:25",
        ]
        assert all(a.menu() is None for a in menu.actions())

    def test_a_list_not_shown_adds_nothing(self):
        menu = CustomMenu()

        _add_inline_actions(_inline_list("Opening\t00:00", is_shown=False), menu)

        assert menu.actions() == []

    def test_the_submenu_holds_the_actions_and_the_rows_together(self):
        manager = MenuManager(
            context=SimpleNamespace(
                actions={
                    "Previous Chapter": _action("Previous Chapter"),
                    "Next Chapter": _action("Next Chapter"),
                    "Chapter List": _inline_list("Opening\t00:00", "Heist\t00:25"),
                }
            ),
            parent=None,
        )

        menu = CustomMenu()
        manager._add_menu_items(
            menu,
            [("Chapters", "Previous Chapter", "Next Chapter", "---", "Chapter List")],
        )

        submenu = menu.actions()[0].menu()

        assert [a.text() for a in submenu.actions()] == [
            "Previous Chapter",
            "Next Chapter",
            "",
            "Opening\t00:00",
            "Heist\t00:25",
        ]

    def test_a_video_without_chapters_has_no_submenu_at_all(self):
        hidden = _action("Previous Chapter")
        hidden.show_if = lambda: False

        manager = MenuManager(
            context=SimpleNamespace(
                actions={
                    "Previous Chapter": hidden,
                    "Chapter List": _inline_list("Opening\t00:00", is_shown=False),
                }
            ),
            parent=None,
        )

        menu = CustomMenu()
        manager._add_menu_items(
            menu, [("Chapters", "Previous Chapter", "---", "Chapter List")]
        )

        assert menu.actions() == []
