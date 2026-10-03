"""Where the bookmark actions live: the menu, the keymap, and every video at once."""

from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtWidgets import QWidget

from gridplayer.params.actions import ACTIONS
from gridplayer.params.defaults_fields import PLAYLIST_FIELDS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.bookmarks import BookmarksManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.widgets.keymap_tree_view import DATA_ACTION_ID, fill_keymap_model
from gridplayer.widgets.video_block import VideoBlock

BOOKMARK_ACTIONS = (
    "Add Bookmark",
    "Previous Bookmark",
    "Next Bookmark",
    "Manage Bookmarks",
    "Previous Bookmark [ALL]",
    "Next Bookmark [ALL]",
)

ICONS = Path(__file__).parent.parent / "gridplayer" / "resources" / "icons"


def _submenu(items, *path):
    for name in path:
        items = next(i for i in items if isinstance(i, tuple) and i[0] == name)[1:]

    return list(items)


class TestWhereTheyAre:
    def test_bookmarks_sit_in_playback_right_after_the_chapters(self):
        playback = _submenu(SECTIONS["video_active"], "Playback")
        names = [item[0] for item in playback if isinstance(item, tuple)]

        assert names.index("Bookmarks") == names.index("Chapters") + 1

    def test_adding_jumping_and_the_manager_come_first_then_the_list(self):
        bookmarks = _submenu(SECTIONS["video_active"], "Playback", "Bookmarks")

        assert bookmarks == [
            "Add Bookmark",
            "Previous Bookmark",
            "Next Bookmark",
            "Manage Bookmarks",
            "---",
            "Bookmark List",
        ]

    def test_the_manager_is_there_whenever_one_can_be_added(self):
        assert (
            ACTIONS["Manage Bookmarks"]["show_if"] == ACTIONS["Add Bookmark"]["show_if"]
        )

    def test_every_video_at_once_can_only_jump(self):
        playback = _submenu(SECTIONS["video_all"], "[ALL]", "Playback")

        assert _submenu(playback, "Bookmarks") == [
            "Previous Bookmark [ALL]",
            "Next Bookmark [ALL]",
        ]


class TestTheirKeys:
    def test_none_come_with_a_key(self):
        for name in BOOKMARK_ACTIONS:
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

        assert set(BOOKMARK_ACTIONS) <= action_ids
        # the bookmarks of one video are nothing to bind a key to
        assert "Bookmark List" not in action_ids


class TestWhatTheyCall:
    def test_the_active_video_has_what_they_call(self):
        for name in BOOKMARK_ACTIONS:
            if "[ALL]" in name:
                continue

            func = ACTIONS[name]["func"]
            method = func[2] if func[1] == "manual_seek" else func[1]

            assert hasattr(VideoBlock, method), name

    def test_jumps_on_the_active_video_are_seeks_the_others_follow(self):
        for name in ("Previous Bookmark", "Next Bookmark"):
            assert ACTIONS[name]["func"][1] == "manual_seek", name

    def test_every_video_is_wired_up_for_them(self):
        for name in ("Previous Bookmark [ALL]", "Next Bookmark [ALL]"):
            command = ACTIONS[name]["func"][1]

            assert hasattr(VideoBlocksManager, f"all_{command}"), name
            assert hasattr(VideoBlock, command), name

    def test_what_decides_when_they_show_is_there(self):
        commands = {
            *vars(ActiveBlockManager),
            *vars(VideoBlocksManager),
        }

        for name in (*BOOKMARK_ACTIONS, "Bookmark List"):
            for key in ("show_if", "enable_if", "menu_generator"):
                command = ACTIONS[name].get(key)

                if isinstance(command, str):
                    assert command in commands, (name, key)


class TestTheirIcons:
    def test_every_one_has_its_icon_in_both_themes(self):
        icon_ids = {ACTIONS[name]["icon"] for name in BOOKMARK_ACTIONS}
        icon_ids.add(SUBMENUS["Bookmarks"]["icon"])
        # Rename's, in a marker's menu and the manager's
        icon_ids.add("bookmark-rename")

        for icon_id in icon_ids:
            for theme in ("light", "dark"):
                assert (ICONS / theme / "scalable" / f"{icon_id}.svg").is_file(), (
                    icon_id,
                    theme,
                )


class TestThePlaylists:
    def test_they_sit_in_playlist_settings_after_editing_them(self):
        settings = _submenu(SECTIONS["playlist"], "Playlist Settings")

        assert settings[:5] == [
            "Edit Playlist Settings",
            "---",
            "Bookmarks in Playlist",
            "Share Bookmarks",
            "---",
        ]

    def test_they_are_there_with_no_video_open(self):
        for name in ("Bookmarks in Playlist", "Share Bookmarks"):
            assert "show_if" not in ACTIONS[name], name
            assert "enable_if" not in ACTIONS[name], name

    def test_what_they_call_is_there(self):
        parent = QWidget()
        commands = BookmarksManager(context=SimpleNamespace(), parent=parent).commands

        assert ACTIONS["Bookmarks in Playlist"]["func"] in commands
        assert ACTIONS["Share Bookmarks"]["func"] in commands
        assert ACTIONS["Share Bookmarks"]["check_if"] in commands

    def test_sharing_reads_as_it_does_in_the_settings(self):
        field = next(
            spec
            for spec in PLAYLIST_FIELDS
            if spec.settings_key == "playlist/bookmarks_shared"
        )

        assert field.menu_action == "Share Bookmarks"
        assert field.label == ACTIONS["Share Bookmarks"]["title"]
