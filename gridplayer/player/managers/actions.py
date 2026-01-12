from collections import Counter

from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction

from gridplayer.params.actions import ACTIONS
from gridplayer.player.managers.base import ManagerBase
from gridplayer.widgets.custom_menu import CustomMenu


class QDynamicAction(QAction):
    def __init__(self, title, icon_id, **kwargs):
        super().__init__(**kwargs)

        self._title = title
        self._icon_id = icon_id

        self.enable_if = None
        self.check_if = None
        self.show_if = None
        self.value_getter = None
        self.toggle = None

        self.menu_generator = None

    @property
    def is_skipped(self) -> bool:
        if self.show_if and not self.show_if():
            return True

        if self.enable_if and self.menu_generator:
            return False

        # skip empty submenus
        return bool(self.menu_generator and not self.menu_generator())

    @property
    def is_enabled(self):
        if self.enable_if is not None:
            return self.enable_if()
        return True

    @property
    def title(self):
        if self.toggle and isinstance(self._title, tuple):
            return self._title[self.toggle()]

        if isinstance(self._title, tuple):
            raise TypeError("Title is tuple with no toggle function")

        return self._title

    @property
    def icon_id(self):
        if self.toggle and isinstance(self._icon_id, tuple):
            return self._icon_id[self.toggle()]

        if isinstance(self._icon_id, tuple):
            raise TypeError("Icon ID is tuple with no toggle function")

        return self._icon_id

    def adapt(self):
        self.setEnabled(self.is_enabled)

        if self.icon_id:
            self.setIcon(QIcon.fromTheme(self.icon_id))

        if self.value_getter is None:
            self.setText(self.title)
        else:
            self.setText(self.title.replace("%v", self.value_getter()))

        if self.is_enabled and self.menu_generator:
            self._generate_submenu()

        elif self.check_if is not None:
            self.setCheckable(True)
            self.setChecked(self.check_if())

    def _generate_submenu(self):
        actions = self.menu_generator()

        generated_menu = CustomMenu()

        for a in actions:
            if a == "---":
                generated_menu.addSeparator()
                continue

            if a.is_skipped:
                continue

            a.adapt()
            generated_menu.addAction(a)

        self.setMenu(generated_menu)


class ActionsManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        _raise_on_duplicate_shortcuts()

        self._ctx.actions = self._make_actions()

    def _make_actions(self) -> dict[str, QDynamicAction]:
        actions: dict[str, QDynamicAction] = {}

        for cmd_name, cmd in ACTIONS.items():
            action = self._make_action(cmd)

            if action.shortcut():
                self.parent().addAction(action)

            actions[cmd_name] = action

        return actions

    def _make_action(self, cmd):
        if cmd == "---":
            return cmd

        action = QDynamicAction(
            title=cmd["title"], icon_id=cmd.get("icon"), parent=self.parent()
        )

        # menus can't have shortcuts
        if cmd.get("menu_generator"):
            action.menu_generator = self._resolve_menu_generator(cmd["menu_generator"])
        else:
            if cmd.get("key"):
                action.setShortcut(QKeySequence(cmd["key"], QKeySequence.PortableText))

            action.triggered.connect(self._ctx.commands.resolve(cmd["func"]))

        self._map_dynamic_functions(action, cmd)

        return action

    def _map_dynamic_functions(self, action, cmd):
        dynamic_functions = [
            "check_if",
            "enable_if",
            "show_if",
            "value_getter",
            "toggle",
        ]

        for dynamic_func_name in dynamic_functions:
            if cmd.get(dynamic_func_name):
                check_func = self._ctx.commands.resolve(cmd[dynamic_func_name])
                setattr(action, dynamic_func_name, check_func)

    def _resolve_menu_generator(self, menu_generator):
        menu_generator_func = self._ctx.commands.resolve(menu_generator)
        return lambda: self._generate_actions(menu_generator_func())

    def _generate_actions(self, templates):
        return [self._make_action(cmd) for cmd in templates]


def _raise_on_duplicate_shortcuts():
    shortcuts = [c["key"] for c in ACTIONS.values() if c.get("key")]

    duplicate_shortcuts = [
        key for key, count in Counter(shortcuts).items() if count > 1
    ]

    if duplicate_shortcuts:
        raise RuntimeError(f"Duplicate shortcuts found: {duplicate_shortcuts}")
