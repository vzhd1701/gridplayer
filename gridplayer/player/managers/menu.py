from types import MappingProxyType

from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu

from gridplayer.player.managers.actions import QDynamicAction
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import translate
from gridplayer.widgets.custom_menu import BigMenuIcons, CustomMenu

SUBMENUS = MappingProxyType(
    {
        "Jump (to)": {"title": translate("Actions", "Jump (to)"), "icon": "jump-to"},
        "Loop": {"title": translate("Actions", "Loop"), "icon": "loop"},
        "Speed": {"title": translate("Actions", "Speed"), "icon": "speed"},
        "Zoom": {"title": translate("Actions", "Zoom"), "icon": "zoom"},
        "Aspect": {"title": translate("Actions", "Aspect"), "icon": "aspect"},
        "[ALL]": {"title": translate("Actions", "[ALL]"), "icon": "play-all"},
        "Grid": {"title": translate("Actions", "Grid"), "icon": "grid"},
        "Seek Sync": {"title": translate("Actions", "Seek Sync"), "icon": "seek-sync"},
        "Seek Others": {
            "title": translate("Actions", "Sync Others"),
            "icon": "seek-sync",
        },
        "Percent": {
            "title": translate("Actions", "Percent"),
            "icon": "seek-sync-percent",
        },
        "Playlist Settings": {
            "title": translate("Actions", "Playlist Settings"),
            "icon": "playlist-settings",
        },
        "Snapshots": {"title": translate("Actions", "Snapshots"), "icon": "snapshots"},
        "Save Snapshot": {"title": translate("Actions", "Save Snapshot")},
        "Delete Snapshot": {"title": translate("Actions", "Delete Snapshot")},
    }
)

SECTIONS = MappingProxyType(
    {
        "video_active": [
            "Play / Pause",
            "---",
            "Previous Video",
            "Next Video",
            "---",
            "Play Previous File",
            "Play Next File",
            "---",
            (
                "Jump (to)",
                (
                    "Percent",
                    "0%",
                    "10%",
                    "20%",
                    "30%",
                    "40%",
                    "50%",
                    "60%",
                    "70%",
                    "80%",
                    "90%",
                ),
                "Timecode",
                "Random",
                "---",
                "Next frame",
                "Previous frame",
                "---",
                "+1%",
                "+5%",
                "+10%",
                "-1%",
                "-5%",
                "-10%",
                "---",
                "+5s",
                "+15s",
                "+30s",
                "-5s",
                "-15s",
                "-30s",
            ),
            (
                "Loop",
                "Random Loop",
                "---",
                "Set Loop Start",
                "Set Loop End",
                "Loop Reset",
                "---",
                "Repeat Single File",
                "Repeat Directory",
                "Repeat Directory (Shuffle)",
            ),
            (
                "Speed",
                "Faster",
                "Slower",
                "Normal",
            ),
            (
                "Zoom",
                "Zoom In",
                "Zoom Out",
                "Zoom Reset",
            ),
            (
                "Aspect",
                "Aspect Fit",
                "Aspect Stretch",
                "Aspect None",
            ),
            (
                "Seek Others",
                "Seek Others (Percent)",
                "Seek Others (Timecode)",
            ),
            "Stream Quality",
            "Rename",
            "Reload",
            "Auto Reload: %v",
            "Close",
        ],
        "video_all": [
            (
                "[ALL]",
                "Play / Pause [ALL]",
                "---",
                "Play Previous File [ALL]",
                "Play Next File [ALL]",
                "---",
                (
                    "Jump (to)",
                    (
                        "Percent",
                        "0% [ALL]",
                        "10% [ALL]",
                        "20% [ALL]",
                        "30% [ALL]",
                        "40% [ALL]",
                        "50% [ALL]",
                        "60% [ALL]",
                        "70% [ALL]",
                        "80% [ALL]",
                        "90% [ALL]",
                    ),
                    "Timecode [ALL]",
                    "Random [ALL]",
                    "---",
                    "Next frame [ALL]",
                    "Previous frame [ALL]",
                    "---",
                    "+1% [ALL]",
                    "+5% [ALL]",
                    "+10% [ALL]",
                    "-1% [ALL]",
                    "-5% [ALL]",
                    "-10% [ALL]",
                    "---",
                    "+5s [ALL]",
                    "+15s [ALL]",
                    "+30s [ALL]",
                    "-5s [ALL]",
                    "-15s [ALL]",
                    "-30s [ALL]",
                ),
                (
                    "Loop",
                    "Random Loop [ALL]",
                    "---",
                    "Set Loop Start [ALL]",
                    "Set Loop End [ALL]",
                    "Loop Reset [ALL]",
                    "---",
                    "Repeat Single File [ALL]",
                    "Repeat Directory [ALL]",
                    "Repeat Directory (Shuffle) [ALL]",
                ),
                (
                    "Speed",
                    "Faster [ALL]",
                    "Slower [ALL]",
                    "Normal [ALL]",
                ),
                (
                    "Zoom",
                    "Zoom In [ALL]",
                    "Zoom Out [ALL]",
                    "Zoom Reset [ALL]",
                ),
                (
                    "Aspect",
                    "Aspect Fit [ALL]",
                    "Aspect Stretch [ALL]",
                    "Aspect None [ALL]",
                ),
                "---",
                "Reload [ALL]",
                "Auto Reload [ALL]",
            ),
            (
                "Seek Sync",
                "Seek Sync (Disabled)",
                "Seek Sync (Percent)",
                "Seek Sync (Timecode)",
            ),
            (
                "Grid",
                "Shuffle Grid",
                "Shuffle Grid On Load",
                "---",
                "Rows First",
                "Columns First",
                "---",
                "Fit Cells",
                "Size: %v",
            ),
            (
                "Snapshots",
                (
                    "Save Snapshot",
                    "Save Snapshot (1)",
                    "Save Snapshot (2)",
                    "Save Snapshot (3)",
                    "Save Snapshot (4)",
                    "Save Snapshot (5)",
                    "Save Snapshot (6)",
                    "Save Snapshot (7)",
                    "Save Snapshot (8)",
                    "Save Snapshot (9)",
                    "Save Snapshot (0)",
                ),
                (
                    "Delete Snapshot",
                    "Delete Snapshot (1)",
                    "Delete Snapshot (2)",
                    "Delete Snapshot (3)",
                    "Delete Snapshot (4)",
                    "Delete Snapshot (5)",
                    "Delete Snapshot (6)",
                    "Delete Snapshot (7)",
                    "Delete Snapshot (8)",
                    "Delete Snapshot (9)",
                    "Delete Snapshot (0)",
                ),
                "Load Snapshot (1)",
                "Load Snapshot (2)",
                "Load Snapshot (3)",
                "Load Snapshot (4)",
                "Load Snapshot (5)",
                "Load Snapshot (6)",
                "Load Snapshot (7)",
                "Load Snapshot (8)",
                "Load Snapshot (9)",
                "Load Snapshot (0)",
            ),
            (
                "Playlist Settings",
                "Disable Click Pause",
                "Disable Wheel Seek",
            ),
        ],
        "program": [
            "Fullscreen",
            "Minimize",
            "---",
            "Add Files",
            "Add URL(s)",
            "Open Playlist",
            "Save Playlist",
            "Close Playlist",
            "---",
            "Settings",
            "About",
            "---",
            "Quit",
        ],
    }
)


class MenuManager(ManagerBase):
    @property
    def event_map(self):
        return {
            QEvent.ContextMenu: self.contextMenuEvent,
        }

    def contextMenuEvent(self, event):
        event.accept()
        self.make_menu().exec_(event.globalPos())

        return True

    def make_menu(self):
        menu = CustomMenu(parent=self.parent())

        menu_sections = self._menu_sections()

        self._add_menu_items(menu, menu_sections)

        return menu

    def _menu_sections(self):
        sections_added = []

        if self._ctx.active_block is not None:
            sections_added.append(SECTIONS["video_active"])

        if self._ctx.video_blocks:
            sections_added.append(SECTIONS["video_all"])

        sections_added.append(SECTIONS["program"])

        return _join_menu_sections(sections_added)

    def _add_menu_items(self, menu, menu_items):
        for m_idx, m_item in enumerate(menu_items):
            if isinstance(m_item, tuple):
                self._add_submenu(m_item, menu)

                if not menu.actions()[-1].menu().actions():
                    menu.removeAction(menu.actions()[-1])
            elif m_item == "---":
                is_last_element = m_idx == len(menu_items) - 1
                _add_separator(menu, is_last_element)
            else:
                action = self._ctx.actions[m_item]
                _add_action(action, menu)

    def _add_submenu(self, submenu, menu):
        sub = SUBMENUS[submenu[0]]
        sub_items = submenu[1:]

        if sub.get("icon"):
            sub_menu = menu.addMenu(QIcon.fromTheme(sub["icon"]), sub["title"])
        else:
            sub_menu = menu.addMenu(sub["title"])

        sub_menu.setStyle(BigMenuIcons())

        self._add_menu_items(sub_menu, sub_items)


def _join_menu_sections(menu_sections):
    menu = []
    for m_block in menu_sections:
        menu.extend(m_block)
        if m_block != menu_sections[-1]:
            menu.append("---")
    return menu


def _add_separator(menu, is_last_element):
    is_empty_menu = not menu.actions()
    is_trailing = not is_empty_menu and menu.actions()[-1].isSeparator()

    if any([is_empty_menu, is_trailing, is_last_element]):
        return

    menu.addSeparator()


def _add_action(action: QDynamicAction, menu: QMenu):
    if action.is_skipped:
        return

    action.adapt()

    menu.addAction(action)
