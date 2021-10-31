from types import MappingProxyType

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction

from gridplayer.params_static import GridMode, VideoAspect
from gridplayer.player.managers.base import ManagerBase

COMMANDS = MappingProxyType(
    {
        "Minimize": {
            "key": Qt.Key_Escape,
            "icon": "minimize",
            "func": "minimize",
        },
        "Quit": {
            "key": "Q",
            "icon": "quit",
            "func": "close",
        },
        "Close": {
            "key": "Ctrl+Q",
            "icon": "close",
            "func": ("active", "exit"),
        },
        "Add Files": {
            "key": "Ctrl+A",
            "icon": "add-files",
            "func": "add_videos",
        },
        "Aspect Fit": {
            "key": "Ctrl+1",
            "icon": "aspect-fit",
            "func": ("active", "set_aspect", VideoAspect.FIT),
            "check": ("is_active_param_set_to", "aspect_mode", VideoAspect.FIT),
        },
        "Aspect Stretch": {
            "key": "Ctrl+2",
            "icon": "aspect-stretch",
            "func": ("active", "set_aspect", VideoAspect.STRETCH),
            "check": ("is_active_param_set_to", "aspect_mode", VideoAspect.STRETCH),
        },
        "Aspect None": {
            "key": "Ctrl+3",
            "icon": "aspect-none",
            "func": ("active", "set_aspect", VideoAspect.NONE),
            "check": ("is_active_param_set_to", "aspect_mode", VideoAspect.NONE),
        },
        "Rows First": {
            "key": "Alt+1",
            "icon": "grid-rows-first",
            "func": ("set_grid_mode", GridMode.AUTO_ROWS),
            "check": ("is_grid_mode_set_to", GridMode.AUTO_ROWS),
        },
        "Columns First": {
            "key": "Alt+2",
            "icon": "grid-columns-first",
            "func": ("set_grid_mode", GridMode.AUTO_COLS),
            "check": ("is_grid_mode_set_to", GridMode.AUTO_COLS),
        },
        "Zoom In": {
            "key": "+",
            "icon": "zoom-in",
            "func": ("active", "scale_increase"),
        },
        "Zoom Out": {
            "key": "-",
            "icon": "zoom-out",
            "func": ("active", "scale_decrease"),
        },
        "Zoom Reset": {
            "key": "*",
            "icon": "zoom-reset",
            "func": ("active", "scale_reset"),
        },
        "Faster": {
            "key": "C",
            "icon": "speed-faster",
            "func": ("active", "rate_increase"),
        },
        "Slower": {
            "key": "X",
            "icon": "speed-slower",
            "func": ("active", "rate_decrease"),
        },
        "Normal": {
            "key": "Z",
            "icon": "speed-reset",
            "func": ("active", "rate_reset"),
        },
        "Next frame": {
            "key": "S",
            "icon": "next-frame",
            "func": ("active", "step_frame", 1),
        },
        "Previous frame": {
            "key": "D",
            "icon": "previous-frame",
            "func": ("active", "step_frame", -1),
        },
        "Fullscreen": {
            "key": "F",
            "icon": "fullscreen",
            "func": "fullscreen",
            "check": "is_fullscreen",
        },
        "Play / Pause": {
            "key": Qt.CTRL + Qt.Key_Space,
            "icon": "play",
            "func": ("active", "play_pause"),
        },
        "Play / Pause [ALL]": {
            "key": Qt.Key_Space,
            "icon": "play-all",
            "func": "play_pause_all",
        },
        "Random Loop": {
            "key": "Ctrl+R",
            "icon": "loop-random",
            "func": ("active", "toggle_loop_random"),
            "check": ("is_active_param_set_to", "is_start_random", True),
        },
        "Set Loop Start": {
            "key": ",",
            "icon": "loop-start",
            "func": ("active", "set_loop_start"),
        },
        "Set Loop End": {
            "key": ".",
            "icon": "loop-end",
            "func": ("active", "set_loop_end"),
        },
        "Loop Reset": {
            "key": "/",
            "icon": "loop-reset",
            "func": ("active", "reset_loop"),
        },
        "Random": {
            "key": "R",
            "icon": "loop-random",
            "func": "loop_random",
        },
        "Open Playlist": {
            "key": "Ctrl+O",
            "icon": "open-playlist",
            "func": "open_playlist",
        },
        "Save Playlist": {
            "key": "Ctrl+S",
            "icon": "save-playlist",
            "func": "save_playlist",
            "enabled_if": "is_videos",
        },
        "Close Playlist": {
            "key": "Ctrl+Shift+Q",
            "icon": "close-playlist",
            "func": "close_playlist",
            "enabled_if": "is_videos",
        },
        "+1%": {
            "key": Qt.Key_Right,
            "icon": "seek-plus-1",
            "func": ("seek_shift_all", 1),
        },
        "+5%": {
            "key": Qt.SHIFT + Qt.Key_Right,
            "icon": "seek-plus-5",
            "func": ("seek_shift_all", 5),
        },
        "+10%": {
            "key": Qt.CTRL + Qt.Key_Right,
            "icon": "seek-plus-10",
            "func": ("seek_shift_all", 10),
        },
        "-1%": {
            "key": Qt.Key_Left,
            "icon": "seek-minus-1",
            "func": ("seek_shift_all", -1),
        },
        "-5%": {
            "key": Qt.SHIFT + Qt.Key_Left,
            "icon": "seek-minus-5",
            "func": ("seek_shift_all", -5),
        },
        "-10%": {
            "key": Qt.CTRL + Qt.Key_Left,
            "icon": "seek-minus-10",
            "func": ("seek_shift_all", -10),
        },
        "Settings": {
            "key": "F5",
            "icon": "settings",
            "func": "settings",
        },
        "About": {
            "key": "F1",
            "icon": "about",
            "func": "about",
        },
        "Next Video": {
            "key": Qt.Key_Tab,
            "icon": "next-video",
            "func": "next_single_video",
        },
    }
)


class ActionsManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.actions = self._make_actions()

    def _make_actions(self):
        actions = {}
        for cmd_name, cmd in COMMANDS.items():
            action = self._make_action(cmd, cmd_name)

            self.parent().addAction(action)

            actions[cmd_name] = action

        return actions

    def _make_action(self, cmd, cmd_name):
        action = QAction(cmd_name, self.parent())

        action.setShortcut(QKeySequence(cmd["key"]))

        action.triggered.connect(self._ctx.commands.resolve(cmd["func"]))

        icon = cmd.get("icon")
        if icon is not None:
            action.setIcon(QIcon.fromTheme(icon))

        is_checked_test = cmd.get("check")
        action.setCheckable(is_checked_test is not None)
        if is_checked_test is not None:
            action.is_checked_test = self._ctx.commands.resolve(is_checked_test)

        is_enabled_test = cmd.get("enabled_if")
        action.is_switchable = is_enabled_test is not None
        if is_enabled_test is not None:
            action.is_enabled_test = self._ctx.commands.resolve(is_enabled_test)

        return action
