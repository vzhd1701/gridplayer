from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction

from gridplayer.params.actions import ACTIONS
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.keymap import (
    KeymapOverrides,
    MouseButtonSequence,
    default_keymap,
    find_duplicate_shortcuts,
    merge_keymap,
    qkeysequences_for_shortcut,
    split_shortcuts,
)
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
        # Keep this QAction enabled so shortcuts still fire. enable_if is
        # applied to a menu proxy (grayed out) and checked again on invoke.
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

    def to_menu_action(self, parent) -> QAction:
        """Menu-only stand-in: grayed out when enable_if is false."""
        self.adapt()

        proxy = QAction(self.icon(), self.text(), parent)
        proxy.setShortcuts(self.shortcuts())
        # Display the chord in the menu without registering a second window shortcut.
        proxy.setShortcutContext(Qt.WidgetShortcut)
        proxy.setShortcutVisibleInContextMenu(True)
        proxy.setEnabled(self.is_enabled)

        if self.isCheckable():
            proxy.setCheckable(True)
            proxy.setChecked(self.isChecked())

        submenu = self.menu()
        if submenu is not None:
            self.setMenu(None)
            proxy.setMenu(submenu)
        else:
            proxy.triggered.connect(self.trigger)

        return proxy

    def _generate_submenu(self):
        generated_menu = CustomMenu(parent=self.parent())
        actions = self.menu_generator(generated_menu)

        for a in actions:
            if a == "---":
                generated_menu.addSeparator()
                continue

            if a.is_skipped:
                continue

            if a.parent() is not generated_menu:
                a.setParent(generated_menu)

            generated_menu.addAction(a.to_menu_action(generated_menu))

        self.setMenu(generated_menu)


class ActionsManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._mouse_index: dict[str, str] = {}
        self._bindings: dict[str, list[str]] = {}
        self._invoking = False

        self._ctx.actions = self._make_actions()
        self._ctx.actions_manager = self

        self.apply_bindings()

    @property
    def event_map(self):
        """Mouse chords on the player window itself (empty grid / chrome).

        Events on ``VideoBlock`` children are handled there instead — Qt only
        delivers these filter events for the player widget, not its children,
        so video-area binds are not double-fired.
        """
        return {
            QEvent.MouseButtonRelease: self.handle_mouse_event,
            QEvent.MouseButtonDblClick: self.handle_mouse_event,
            QEvent.Wheel: self.handle_mouse_event,
        }

    def apply_bindings(self, overrides: KeymapOverrides | None = None):
        """Apply effective keymap to QActions and rebuild mouse reverse index.

        ``overrides`` is the sparse ``player/keymap`` setting (as emitted from
        SettingsManager), or a dict of overrides. When omitted, reads Settings.
        """
        if overrides is None:
            overrides = Settings().get("player/keymap")

        bindings = merge_keymap(default_keymap(), overrides)

        duplicates = find_duplicate_shortcuts(bindings)
        if duplicates:
            # Corrupt / hand-edited settings should not crash the player
            self._log.error(
                "Duplicate shortcuts in keymap, falling back to defaults: %s",
                duplicates,
            )
            bindings = default_keymap()

        self._bindings = {k: list(v) for k, v in bindings.items()}
        self._mouse_index = {}

        parent = self.parent()

        # Phase 1: detach and clear every action so no stale chords remain
        for action in self._ctx.actions.values():
            if action in parent.actions():
                parent.removeAction(action)
            action.setShortcuts([])

        # Phase 2: apply normalized keyboard / mouse bindings
        for cmd_name, action in self._ctx.actions.items():
            if action.menu_generator:
                continue

            shortcuts = self._bindings.get(cmd_name, [])
            keyboard_keys, mouse_keys = split_shortcuts(shortcuts)

            for mouse_key in mouse_keys:
                self._mouse_index[mouse_key] = cmd_name

            if not keyboard_keys:
                continue

            # Expand logical Enter → main Return + keypad Enter (both physical keys)
            sequences: list[QKeySequence] = []
            for key in keyboard_keys:
                sequences.extend(qkeysequences_for_shortcut(key))
            if not sequences:
                continue

            action.setEnabled(True)
            action.setShortcuts(sequences)
            parent.addAction(action)

    def trigger(self, action_id: str) -> bool:
        """Invoke an action the same way a menu/shortcut would."""
        action = self._ctx.actions.get(action_id)
        if action is None or action.menu_generator:
            return False

        if not action.is_enabled:
            return False

        action.trigger()
        return True

    def action_for_mouse_sequence(
        self, sequence: str | MouseButtonSequence
    ) -> str | None:
        return self._mouse_index.get(str(sequence))

    def handle_mouse_event(self, event) -> bool:
        """Resolve mouse event via keymap and trigger. Returns True if handled."""

        if self._ctx.commands.handle_fake_drag_click(event):
            return True

        try:
            seq = MouseButtonSequence.from_event(event)
        except ValueError:
            return False

        if seq.is_click and getattr(self._ctx, "is_disable_mouse_click_events", False):
            return False

        if seq.is_wheel and getattr(self._ctx, "is_disable_mouse_wheel_events", False):
            return False

        action_id = self._mouse_index.get(seq.sequence)
        if not action_id:
            return False

        return self.trigger(action_id)

    def is_mouse_event_bound(self, event) -> bool:
        try:
            seq = MouseButtonSequence.from_event(event)
        except ValueError:
            return False
        return seq.sequence in self._mouse_index

    def _make_actions(self) -> dict[str, QDynamicAction]:
        actions: dict[str, QDynamicAction] = {}

        for cmd_name, cmd in ACTIONS.items():
            action = self._make_action(cmd)
            actions[cmd_name] = action

        return actions

    def _make_action(self, cmd, parent=None):
        if cmd == "---":
            return cmd

        action = QDynamicAction(
            title=cmd["title"],
            icon_id=cmd.get("icon"),
            parent=parent if parent is not None else self.parent(),
        )

        # menus can't have shortcuts
        if cmd.get("menu_generator"):
            action.menu_generator = self._resolve_menu_generator(cmd["menu_generator"])
        else:
            command = self._ctx.commands.resolve(cmd["func"])
            action.triggered.connect(
                lambda _checked=False, a=action, c=command: self._run_action(a, c)
            )

        self._map_dynamic_functions(action, cmd)

        return action

    def _run_action(self, action: QDynamicAction, command) -> None:
        if self._invoking or not action.is_enabled:
            return

        self._invoking = True
        try:
            command()
        finally:
            self._invoking = False

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
        return lambda parent=None: self._generate_actions(menu_generator_func(), parent)

    def _generate_actions(self, templates, parent=None):
        return [self._make_action(cmd, parent=parent) for cmd in templates]
