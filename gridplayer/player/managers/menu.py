from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu

from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.player.managers.actions import QDynamicAction
from gridplayer.player.managers.base import ManagerBase
from gridplayer.widgets.custom_menu import BigMenuIcons, CustomMenu


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

        sub_menu.setStyle(BigMenuIcons("Fusion"))

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
