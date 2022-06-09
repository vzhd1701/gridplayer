from types import MappingProxyType
from typing import Dict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction, QMenu

from gridplayer.params.static import GridMode, VideoAspect, VideoRepeat
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import translate

COMMANDS = MappingProxyType(
    {
        "Minimize": {
            "title": translate("Actions", "Minimize"),
            "key": Qt.Key_Escape,
            "icon": "minimize",
            "func": "minimize",
        },
        "Quit": {
            "title": translate("Actions", "Quit"),
            "key": "Q",
            "icon": "quit",
            "func": "close",
        },
        "Close": {
            "title": translate("Actions", "Close"),
            "key": "Ctrl+Q",
            "icon": "close",
            "func": ("active", "exit"),
        },
        "Reload": {
            "title": translate("Actions", "Reload"),
            "icon": "reload",
            "func": ("active", "reload"),
        },
        "Rename": {
            "title": translate("Actions", "Rename"),
            "key": "Ctrl+Shift+R",
            "icon": "rename",
            "func": ("active", "rename"),
        },
        "Add URL(s)": {
            "title": translate("Actions", "Add URL(s)"),
            "key": "Ctrl+U",
            "icon": "add-files",
            "func": "add_urls",
        },
        "Add Files": {
            "title": translate("Actions", "Add Files"),
            "key": "Ctrl+A",
            "icon": "add-files",
            "func": "add_videos",
        },
        "Aspect Fit": {
            "title": translate("Actions", "Aspect Fit"),
            "key": "Ctrl+1",
            "icon": "aspect-fit",
            "func": ("active", "set_aspect", VideoAspect.FIT),
            "check_if": ("is_active_param_set_to", "aspect_mode", VideoAspect.FIT),
        },
        "Aspect Stretch": {
            "title": translate("Actions", "Aspect Stretch"),
            "key": "Ctrl+2",
            "icon": "aspect-stretch",
            "func": ("active", "set_aspect", VideoAspect.STRETCH),
            "check_if": ("is_active_param_set_to", "aspect_mode", VideoAspect.STRETCH),
        },
        "Aspect None": {
            "title": translate("Actions", "Aspect None"),
            "key": "Ctrl+3",
            "icon": "aspect-none",
            "func": ("active", "set_aspect", VideoAspect.NONE),
            "check_if": ("is_active_param_set_to", "aspect_mode", VideoAspect.NONE),
        },
        "Rows First": {
            "title": translate("Actions", "Rows First"),
            "key": "Alt+1",
            "icon": "grid-rows-first",
            "func": ("set_grid_mode", GridMode.AUTO_ROWS),
            "check_if": ("is_grid_mode_set_to", GridMode.AUTO_ROWS),
        },
        "Columns First": {
            "title": translate("Actions", "Columns First"),
            "key": "Alt+2",
            "icon": "grid-columns-first",
            "func": ("set_grid_mode", GridMode.AUTO_COLS),
            "check_if": ("is_grid_mode_set_to", GridMode.AUTO_COLS),
        },
        "Fit Cells": {
            "title": translate("Actions", "Fit Cells"),
            "key": "Alt+F",
            "icon": "grid-fit",
            "func": "switch_is_grid_fit",
            "check_if": "is_grid_fit",
        },
        "Size: %v": {
            "title": translate("Actions", "Size: %v"),
            "key": "Alt+N",
            "icon": "grid-size",
            "func": "ask_grid_size",
            "value_getter": "get_grid_size",
        },
        "Zoom In": {
            "title": translate("Actions", "Zoom In"),
            "key": "+",
            "icon": "zoom-in",
            "func": ("active", "scale_increase"),
        },
        "Zoom Out": {
            "title": translate("Actions", "Zoom Out"),
            "key": "-",
            "icon": "zoom-out",
            "func": ("active", "scale_decrease"),
        },
        "Zoom Reset": {
            "title": translate("Actions", "Zoom Reset"),
            "key": "*",
            "icon": "zoom-reset",
            "func": ("active", "scale_reset"),
        },
        "Faster": {
            "title": translate("Actions", "Faster"),
            "key": "C",
            "icon": "speed-faster",
            "func": ("active", "rate_increase"),
            "show_if": "is_active_seekable",
        },
        "Slower": {
            "title": translate("Actions", "Slower"),
            "key": "X",
            "icon": "speed-slower",
            "func": ("active", "rate_decrease"),
            "show_if": "is_active_seekable",
        },
        "Normal": {
            "title": translate("Actions", "Normal"),
            "key": "Z",
            "icon": "speed-reset",
            "func": ("active", "rate_reset"),
            "show_if": "is_active_seekable",
        },
        "Next frame": {
            "title": translate("Actions", "Next frame"),
            "key": "S",
            "icon": "next-frame",
            "func": ("active", "step_frame", 1),
            "show_if": "is_active_seekable",
        },
        "Previous frame": {
            "title": translate("Actions", "Previous frame"),
            "key": "D",
            "icon": "previous-frame",
            "func": ("active", "step_frame", -1),
            "show_if": "is_active_seekable",
        },
        "Fullscreen": {
            "title": translate("Actions", "Fullscreen"),
            "key": "F",
            "icon": "fullscreen",
            "func": "fullscreen",
            "check_if": "is_fullscreen",
        },
        "Play / Pause": {
            "title": translate("Actions", "Play / Pause"),
            "key": Qt.CTRL + Qt.Key_Space,
            "icon": "play",
            "func": ("active", "play_pause"),
        },
        "Play / Pause [ALL]": {
            "title": translate("Actions", "Play / Pause [ALL]"),
            "key": Qt.Key_Space,
            "icon": "play-all",
            "func": "play_pause_all",
        },
        "Play Previous File": {
            "title": translate("Actions", "Play Previous File"),
            "key": Qt.Key_PageUp,
            "icon": "previous-video-file",
            "func": ("active", "previous_video"),
            "show_if": "is_active_local_file",
        },
        "Play Next File": {
            "title": translate("Actions", "Play Next File"),
            "key": Qt.Key_PageDown,
            "icon": "next-video-file",
            "func": ("active", "next_video"),
            "show_if": "is_active_local_file",
        },
        "Random Loop": {
            "title": translate("Actions", "Random Loop"),
            "key": "Ctrl+R",
            "icon": "loop-random",
            "func": ("active", "toggle_loop_random"),
            "check_if": ("is_active_param_set_to", "is_start_random", True),
            "show_if": "is_active_seekable",
        },
        "Set Loop Start": {
            "title": translate("Actions", "Set Loop Start"),
            "key": ",",
            "icon": "loop-start",
            "func": ("active", "set_loop_start"),
            "show_if": "is_active_seekable",
        },
        "Set Loop End": {
            "title": translate("Actions", "Set Loop End"),
            "key": ".",
            "icon": "loop-end",
            "func": ("active", "set_loop_end"),
            "show_if": "is_active_seekable",
        },
        "Loop Reset": {
            "title": translate("Actions", "Loop Reset"),
            "key": "/",
            "icon": "loop-reset",
            "func": ("active", "reset_loop"),
            "show_if": "is_active_seekable",
        },
        "Repeat Single File": {
            "title": translate("Actions", "Repeat Single File"),
            "icon": "loop-single",
            "func": ("active", "set_repeat_mode", VideoRepeat.SINGLE_FILE),
            "check_if": (
                "is_active_param_set_to",
                "repeat_mode",
                VideoRepeat.SINGLE_FILE,
            ),
            "show_if": "is_active_local_file",
        },
        "Repeat Directory": {
            "title": translate("Actions", "Repeat Directory"),
            "icon": "loop-dir",
            "func": ("active", "set_repeat_mode", VideoRepeat.DIR),
            "check_if": ("is_active_param_set_to", "repeat_mode", VideoRepeat.DIR),
            "show_if": "is_active_local_file",
        },
        "Repeat Directory (Shuffle)": {
            "title": translate("Actions", "Repeat Directory (Shuffle)"),
            "icon": "loop-dir-shuffle",
            "func": ("active", "set_repeat_mode", VideoRepeat.DIR_SHUFFLE),
            "check_if": (
                "is_active_param_set_to",
                "repeat_mode",
                VideoRepeat.DIR_SHUFFLE,
            ),
            "show_if": "is_active_local_file",
        },
        "Random": {
            "title": translate("Actions", "Random"),
            "key": "R",
            "icon": "loop-random",
            "func": "loop_random",
        },
        "Open Playlist": {
            "title": translate("Actions", "Open Playlist"),
            "key": "Ctrl+O",
            "icon": "open-playlist",
            "func": "open_playlist",
        },
        "Save Playlist": {
            "title": translate("Actions", "Save Playlist"),
            "key": "Ctrl+S",
            "icon": "save-playlist",
            "func": "save_playlist",
            "enable_if": "is_videos",
        },
        "Close Playlist": {
            "title": translate("Actions", "Close Playlist"),
            "key": "Ctrl+Shift+Q",
            "icon": "close-playlist",
            "func": "close_playlist",
            "enable_if": "is_videos",
        },
        "Seek Sync": {
            "title": translate("Actions", "Seek Sync"),
            "key": "Shift+S",
            "icon": "seek-sync",
            "func": "switch_seek_synced",
            "check_if": "is_seek_synced",
        },
        "+1%": {
            "title": "+1%",
            "key": Qt.Key_Right,
            "icon": "seek-plus-1",
            "func": ("seek_shift_all", 1),
        },
        "+5%": {
            "title": "+5%",
            "key": Qt.SHIFT + Qt.Key_Right,
            "icon": "seek-plus-5",
            "func": ("seek_shift_all", 5),
        },
        "+10%": {
            "title": "+10%",
            "key": Qt.ALT + Qt.Key_Right,
            "icon": "seek-plus-10",
            "func": ("seek_shift_all", 10),
        },
        "-1%": {
            "title": "-1%",
            "key": Qt.Key_Left,
            "icon": "seek-minus-1",
            "func": ("seek_shift_all", -1),
        },
        "-5%": {
            "title": "-5%",
            "key": Qt.SHIFT + Qt.Key_Left,
            "icon": "seek-minus-5",
            "func": ("seek_shift_all", -5),
        },
        "-10%": {
            "title": "-10%",
            "key": Qt.ALT + Qt.Key_Left,
            "icon": "seek-minus-10",
            "func": ("seek_shift_all", -10),
        },
        "+5s": {
            "title": translate("Actions", "+5s"),
            "key": Qt.CTRL + Qt.Key_Right,
            "icon": "seek-plus-1",
            "func": ("seek_shift_ms_all", 5000),
        },
        "+15s": {
            "title": translate("Actions", "+15s"),
            "key": Qt.CTRL + Qt.SHIFT + Qt.Key_Right,
            "icon": "seek-plus-5",
            "func": ("seek_shift_ms_all", 15000),
        },
        "+30s": {
            "title": translate("Actions", "+30s"),
            "key": Qt.CTRL + Qt.ALT + Qt.Key_Right,
            "icon": "seek-plus-10",
            "func": ("seek_shift_ms_all", 30000),
        },
        "-5s": {
            "title": translate("Actions", "-5s"),
            "key": Qt.CTRL + Qt.Key_Left,
            "icon": "seek-minus-1",
            "func": ("seek_shift_ms_all", -5000),
        },
        "-15s": {
            "title": translate("Actions", "-15s"),
            "key": Qt.CTRL + Qt.SHIFT + Qt.Key_Left,
            "icon": "seek-minus-5",
            "func": ("seek_shift_ms_all", -15000),
        },
        "-30s": {
            "title": translate("Actions", "-30s"),
            "key": Qt.CTRL + Qt.ALT + Qt.Key_Left,
            "icon": "seek-minus-10",
            "func": ("seek_shift_ms_all", -30000),
        },
        "Settings": {
            "title": translate("Actions", "Settings"),
            "key": "F5",
            "icon": "settings",
            "func": "settings",
        },
        "About": {
            "title": translate("Actions", "About"),
            "key": "F1",
            "icon": "about",
            "func": "about",
        },
        "Next Video": {
            "title": translate("Actions", "Next Video"),
            "key": "N",
            "icon": "next-video",
            "func": "next_single_video",
        },
        "Next Active": {
            "title": "Next Active",
            "key": Qt.Key_Tab,
            "func": "next_active",
        },
        "Previous Active": {
            "title": "Previous Active",
            "key": Qt.SHIFT + Qt.Key_Tab,
            "func": "previous_active",
        },
        "Stream Quality": {
            "title": translate("Actions", "Stream Quality"),
            "icon": "stream-quality",
            "show_if": "is_active_multistream",
            "menu_generator": "menu_generator_stream_quality",
        },
    }
)


class QDynamicAction(QAction):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.value_template = kwargs.get("text", "")

        self.enable_if = None
        self.check_if = None
        self.show_if = None
        self.value_getter = None

        self.menu_generator = None

    @property
    def is_skipped(self):
        return self.show_if and not self.show_if()

    @property
    def is_enabled(self):
        if self.enable_if is not None:
            return self.enable_if()
        return True

    def adapt(self):
        self.setEnabled(self.is_enabled)

        if self.value_getter is not None:
            self.setText(self.value_template.replace("%v", self.value_getter()))

        if self.menu_generator is not None:
            self._generate_submenu()

        elif self.check_if is not None:
            self.setCheckable(True)
            self.setChecked(self.check_if())

    def _generate_submenu(self):
        actions = self.menu_generator()

        generated_menu = QMenu()

        for a in actions:
            if a.is_skipped:
                continue

            a.adapt()
            generated_menu.addAction(a)

        self.setMenu(generated_menu)


class ActionsManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.actions = self._make_actions()

    def _make_actions(self) -> Dict[str, QDynamicAction]:
        actions: Dict[str, QDynamicAction] = {}

        for cmd_name, cmd in COMMANDS.items():
            action = self._make_action(cmd)

            if action.shortcut():
                self.parent().addAction(action)

            actions[cmd_name] = action

        return actions

    def _make_action(self, cmd):
        action = QDynamicAction(text=cmd["title"], parent=self.parent())

        if cmd.get("icon"):
            action.setIcon(QIcon.fromTheme(cmd["icon"]))

        # menus can't have shortcuts
        if cmd.get("menu_generator"):
            action.menu_generator = self._resolve_menu_generator(cmd["menu_generator"])
        else:
            if cmd.get("key"):
                action.setShortcut(QKeySequence(cmd["key"]))

            action.triggered.connect(self._ctx.commands.resolve(cmd["func"]))

        self._map_dynamic_functions(action, cmd)

        return action

    def _map_dynamic_functions(self, action, cmd):
        dynamic_functions = [
            "check_if",
            "enable_if",
            "show_if",
            "value_getter",
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
