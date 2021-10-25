from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction, QMenu, QProxyStyle, QStyle

from gridplayer.params_static import GridMode, VideoAspect
from gridplayer.utils.misc import ModalWindow

MENU_STYLE = """
QMenu::item { height:24px; padding: 2px; margin: 0 5px;}
QMenu::item:selected { background-color: #53aedf; }
QMenu::item:checked { background-color: #7b888f; }
QMenu::separator { height: 2px; margin: 0; }
"""


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


class PlayerMenuMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.actions = self._make_actions()

    def contextMenuEvent(self, event):
        with ModalWindow(self):
            self.make_menu().exec_(event.globalPos())

        super().contextMenuEvent(event)

    def make_menu(self):
        menu = QMenu()
        menu.installEventFilter(self)
        menu.setStyle(BigMenuIcons())
        menu.setStyleSheet(MENU_STYLE)

        menu_sections = self._menu_sections()

        self._add_menu_items(menu, menu_sections)

        return menu

    def _make_actions(self):
        commands = {
            "Minimize": {
                "key": Qt.Key_Escape,
                "func": self.cmd_minimize,
                "icon": "minimize",
            },
            "Quit": {
                "key": "Q",
                "func": self.close,
                "icon": "quit",
            },
            "Close": {
                "key": "Ctrl+Q",
                "func": lambda: self.cmd_active("exit"),
                "icon": "close",
            },
            "Add Files": {
                "key": "Ctrl+A",
                "func": self.cmd_add_videos,
                "icon": "add-files",
            },
            "Aspect Fit": {
                "key": "Ctrl+1",
                "func": lambda: self.cmd_active("set_aspect", VideoAspect.FIT),
                "check": lambda: self.is_active_param_set_to(
                    "aspect_mode", VideoAspect.FIT
                ),
                "icon": "aspect-fit",
            },
            "Aspect Stretch": {
                "key": "Ctrl+2",
                "func": lambda: self.cmd_active("set_aspect", VideoAspect.STRETCH),
                "check": lambda: self.is_active_param_set_to(
                    "aspect_mode", VideoAspect.STRETCH
                ),
                "icon": "aspect-stretch",
            },
            "Aspect None": {
                "key": "Ctrl+3",
                "func": lambda: self.cmd_active("set_aspect", VideoAspect.NONE),
                "check": lambda: self.is_active_param_set_to(
                    "aspect_mode", VideoAspect.NONE
                ),
                "icon": "aspect-none",
            },
            "Rows First": {
                "key": "Alt+1",
                "func": lambda: self.cmd_set_grid_mode(GridMode.AUTO_ROWS),
                "check": lambda: self.playlist.grid_mode == GridMode.AUTO_ROWS,
                "icon": "grid-rows-first",
            },
            "Columns First": {
                "key": "Alt+2",
                "func": lambda: self.cmd_set_grid_mode(GridMode.AUTO_COLS),
                "check": lambda: self.playlist.grid_mode == GridMode.AUTO_COLS,
                "icon": "grid-columns-first",
            },
            "Zoom In": {
                "key": "+",
                "func": lambda: self.cmd_active("scale_increase"),
                "icon": "zoom-in",
            },
            "Zoom Out": {
                "key": "-",
                "func": lambda: self.cmd_active("scale_decrease"),
                "icon": "zoom-out",
            },
            "Zoom Reset": {
                "key": "*",
                "func": lambda: self.cmd_active("scale_reset"),
                "icon": "zoom-reset",
            },
            "Faster": {
                "key": "C",
                "func": lambda: self.cmd_active("rate_increase"),
                "icon": "speed-faster",
            },
            "Slower": {
                "key": "X",
                "func": lambda: self.cmd_active("rate_decrease"),
                "icon": "speed-slower",
            },
            "Normal": {
                "key": "Z",
                "func": lambda: self.cmd_active("rate_reset"),
                "icon": "speed-reset",
            },
            "Next frame": {
                "key": "S",
                "func": lambda: self.cmd_active("step_frame", 1),
                "icon": "next-frame",
            },
            "Previous frame": {
                "key": "D",
                "func": lambda: self.cmd_active("step_frame", -1),
                "icon": "previous-frame",
            },
            "Fullscreen": {
                "key": "F",
                "func": self.cmd_fullscreen,
                "icon": "fullscreen",
                "check": lambda: self.isFullScreen(),
            },
            "Play / Pause": {
                "key": Qt.CTRL + Qt.Key_Space,
                "func": lambda: self.cmd_active("play_pause"),
                "icon": "play",
            },
            "Play / Pause [ALL]": {
                "key": Qt.Key_Space,
                "func": self.cmd_play_pause_all,
                "icon": "play-all",
            },
            "Random Loop": {
                "key": "Ctrl+R",
                "func": lambda: self.cmd_active("toggle_loop_random"),
                "check": lambda: self.is_active_param_set_to("is_start_random", True),
                "icon": "loop-random",
            },
            "Set Loop Start": {
                "key": ",",
                "func": lambda: self.cmd_active("set_loop_start"),
                "icon": "loop-start",
            },
            "Set Loop End": {
                "key": ".",
                "func": lambda: self.cmd_active("set_loop_end"),
                "icon": "loop-end",
            },
            "Loop Reset": {
                "key": "/",
                "func": lambda: self.cmd_active("reset_loop"),
                "icon": "loop-reset",
            },
            "Random": {
                "key": "R",
                "func": lambda: self.seek_random.emit(),
                "icon": "loop-random",
            },
            "Open Playlist": {
                "key": "Ctrl+O",
                "func": self.cmd_open_playlist,
                "icon": "open-playlist",
            },
            "Save Playlist": {
                "key": "Ctrl+S",
                "func": self.cmd_save_playlist,
                "enabled_if": lambda: bool(self.video_blocks),
                "icon": "save-playlist",
            },
            "Close Playlist": {
                "key": "Ctrl+Shift+Q",
                "func": self.cmd_close_playlist,
                "enabled_if": lambda: bool(self.video_blocks),
                "icon": "close-playlist",
            },
            "+1%": {
                "key": Qt.Key_Right,
                "func": lambda: self.cmd_seek_shift_all(1),
                "icon": "seek-plus-1",
            },
            "+5%": {
                "key": Qt.SHIFT + Qt.Key_Right,
                "func": lambda: self.cmd_seek_shift_all(5),
                "icon": "seek-plus-5",
            },
            "+10%": {
                "key": Qt.CTRL + Qt.Key_Right,
                "func": lambda: self.cmd_seek_shift_all(10),
                "icon": "seek-plus-10",
            },
            "-1%": {
                "key": Qt.Key_Left,
                "func": lambda: self.cmd_seek_shift_all(-1),
                "icon": "seek-minus-1",
            },
            "-5%": {
                "key": Qt.SHIFT + Qt.Key_Left,
                "func": lambda: self.cmd_seek_shift_all(-5),
                "icon": "seek-minus-5",
            },
            "-10%": {
                "key": Qt.CTRL + Qt.Key_Left,
                "func": lambda: self.cmd_seek_shift_all(-10),
                "icon": "seek-minus-10",
            },
            "Settings": {
                "key": Qt.Key_F5,
                "func": self.cmd_settings,
                "icon": "settings",
            },
            "About": {
                "key": Qt.Key_F1,
                "func": self.cmd_about,
                "icon": "about",
            },
            "Next Video": {
                "key": Qt.Key_Tab,
                "func": self.next_single_video,
                "icon": "next-video",
            },
        }

        actions = {}
        for cmd_name, cmd in commands.items():
            action = self._make_action(cmd, cmd_name)

            self.addAction(action)

            actions[cmd_name] = action

        return actions

    def _make_action(self, cmd, cmd_name):
        action = QAction(cmd_name, self)

        action.triggered.connect(cmd["func"])
        action.setShortcut(QKeySequence(cmd["key"]))

        icon = cmd.get("icon")
        if icon is not None:
            action.setIcon(QIcon.fromTheme(icon))

        action.is_checked_test = cmd.get("check")
        action.setCheckable(action.is_checked_test is not None)

        action.is_enabled_test = cmd.get("enabled_if")
        action.is_switchable = action.is_enabled_test is not None

        return action

    def _menu_sections(self):
        sections = {
            "video_active": [
                "Play / Pause",
                (
                    {"name": "Step", "icon": "next-frame"},
                    ("Next frame", "Previous frame"),
                ),
                (
                    {"name": "Loop", "icon": "loop"},
                    (
                        "Random Loop",
                        "---",
                        "Set Loop Start",
                        "Set Loop End",
                        "Loop Reset",
                    ),
                ),
                (
                    {"name": "Speed", "icon": "speed"},
                    ("Faster", "Slower", "Normal"),
                ),
                (
                    {"name": "Zoom", "icon": "zoom"},
                    ("Zoom In", "Zoom Out", "Zoom Reset"),
                ),
                (
                    {"name": "Aspect", "icon": "aspect"},
                    ("Aspect Fit", "Aspect Stretch", "Aspect None"),
                ),
            ],
            "video_block": ["Close"],
            "video_single": ["Next Video"],
            "video_all": [
                "Play / Pause [ALL]",
                (
                    {"name": "Jump (to) [ALL]", "icon": "jump-to"},
                    ("Random", "---", "+1%", "+5%", "+10%", "-1%", "-5%", "-10%"),
                ),
                (
                    {"name": "Grid", "icon": "grid"},
                    ("Rows First", "Columns First"),
                ),
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

        sections_added = []

        if self.active_video_block is not None:
            if self.active_video_block.video_driver.is_video_initialized:
                menu_video = sections["video_active"] + sections["video_block"]
            else:
                menu_video = sections["video_block"]

            sections_added.append(menu_video)

            if self.is_single_mode:
                sections_added.append(sections["video_single"])

        if self.video_blocks:
            sections_added.append(sections["video_all"])

        sections_added.append(sections["player"])
        sections_added.append(sections["program"])

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
        sub, sub_items = submenu
        sub_icon = sub.get("icon")

        if sub_icon is not None:
            sub_menu = menu.addMenu(QIcon.fromTheme(sub_icon), sub["name"])
        else:
            sub_menu = menu.addMenu(sub["name"])

        sub_menu.setStyle(BigMenuIcons())

        self._add_menu_items(sub_menu, sub_items)

    def _add_action(self, menu_item, menu):
        action = self.actions[menu_item]

        if action.isCheckable():
            action.setChecked(action.is_checked_test())
        if action.is_switchable:
            action.setEnabled(action.is_enabled_test())

        menu.addAction(action)
