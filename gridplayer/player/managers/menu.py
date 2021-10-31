from types import MappingProxyType

from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QProxyStyle, QStyle

from gridplayer.player.managers.base import ManagerBase

MENU_STYLE = """
QMenu::item { height:24px; padding: 2px; margin: 0 5px;}
QMenu::item:selected { background-color: #53aedf; }
QMenu::item:checked { background-color: #7b888f; }
QMenu::separator { height: 2px; margin: 0; }
"""

SUBMENUS = MappingProxyType(
    {
        "Step": {"icon": "next-frame"},
        "Loop": {"icon": "loop"},
        "Speed": {"icon": "speed"},
        "Zoom": {"icon": "zoom"},
        "Aspect": {"icon": "aspect"},
        "Jump (to) [ALL]": {"icon": "jump-to"},
        "Grid": {"icon": "grid"},
    }
)

SECTIONS = MappingProxyType(
    {
        "video_active": [
            "Play / Pause",
            ("Step", "Next frame", "Previous frame"),
            (
                "Loop",
                "Random Loop",
                "---",
                "Set Loop Start",
                "Set Loop End",
                "Loop Reset",
            ),
            ("Speed", "Faster", "Slower", "Normal"),
            ("Zoom", "Zoom In", "Zoom Out", "Zoom Reset"),
            ("Aspect", "Aspect Fit", "Aspect Stretch", "Aspect None"),
        ],
        "video_block": ["Close"],
        "video_single": ["Next Video"],
        "video_all": [
            "Play / Pause [ALL]",
            (
                "Jump (to) [ALL]",
                "Random",
                "---",
                "+1%",
                "+5%",
                "+10%",
                "-1%",
                "-5%",
                "-10%",
            ),
            ("Grid", "Rows First", "Columns First"),
        ],
        "player": ["Fullscreen", "Minimize"],
        "program": [
            "Add Files",
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


class BigMenuIcons(QProxyStyle):
    def pixelMetric(self, metric, option, widget):
        if metric == QStyle.PM_SmallIconSize:
            return 24
        return super().pixelMetric(metric, option, widget)


def _join_menu_sections(menu_sections):
    menu = []
    for m_block in menu_sections:
        menu.extend(m_block)
        if m_block != menu_sections[-1]:
            menu.append("---")
    return menu


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
        menu = QMenu(self.parent())
        menu.setStyle(BigMenuIcons())
        menu.setStyleSheet(MENU_STYLE)

        menu_sections = self._menu_sections()

        self._add_menu_items(menu, menu_sections)

        return menu

    def _menu_sections(self):
        sections_added = []

        if self._ctx.active_block is not None:
            if self._ctx.active_block.video_driver.is_video_initialized:
                menu_video = SECTIONS["video_active"] + SECTIONS["video_block"]
            else:
                menu_video = SECTIONS["video_block"]

            sections_added.append(menu_video)

            if self._ctx.is_single_mode:
                sections_added.append(SECTIONS["video_single"])

        if self._ctx.video_blocks:
            sections_added.append(SECTIONS["video_all"])

        sections_added.append(SECTIONS["player"])
        sections_added.append(SECTIONS["program"])

        return _join_menu_sections(sections_added)

    def _add_menu_items(self, menu, menu_items):
        for m_item in menu_items:
            if isinstance(m_item, tuple):
                self._add_submenu(m_item, menu)
            elif m_item == "---":
                menu.addSeparator()
            else:
                self._add_action(m_item, menu)

    def _add_submenu(self, submenu, menu):
        sub_name = submenu[0]
        sub_items = submenu[1:]
        sub = SUBMENUS[sub_name]

        sub_icon = sub.get("icon")

        if sub_icon is not None:
            sub_menu = menu.addMenu(QIcon.fromTheme(sub_icon), sub_name)
        else:
            sub_menu = menu.addMenu(sub_name)

        sub_menu.setStyle(BigMenuIcons())

        self._add_menu_items(sub_menu, sub_items)

    def _add_action(self, menu_item, menu):
        action = self._ctx.actions[menu_item]

        if action.isCheckable():
            action.setChecked(action.is_checked_test())
        if action.is_switchable:
            action.setEnabled(action.is_enabled_test())

        menu.addAction(action)
