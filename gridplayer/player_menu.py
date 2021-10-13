from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction, QMenu, QProxyStyle, QStyle

from gridplayer.params_static import GridMode, VideoAspect
from gridplayer.resources import ICONS


class BigMenuIcons(QProxyStyle):
    def pixelMetric(self, metric, option, widget):
        if metric == QStyle.PM_SmallIconSize:
            return 24
        return super().pixelMetric(metric, option, widget)


class PlayerMenu:
    def __init__(self, player):
        self.player = player

        self.actions = {}

        commands = {
            "Minimize": {
                "key": Qt.Key_Escape,
                "func": self.player.cmd_minimize,
                "icon": ICONS["custom/001-minimize window"],
            },
            "Quit": {
                "key": "Q",
                "func": self.player.close,
                "icon": ICONS["basic/136-log out"],
            },
            "Close": {
                "key": "Ctrl+Q",
                "func": lambda: self.player.cmd_active("exit"),
                "icon": ICONS["basic/031-cancel"],
            },
            "Add Files": {
                "key": "Ctrl+A",
                "func": self.player.cmd_add_videos,
                "icon": ICONS["basic/003-add"],
            },
            "Aspect Fit": {
                "key": "Ctrl+1",
                "func": lambda: self.player.cmd_active("set_aspect", VideoAspect.FIT),
                "check": lambda: self.player.is_active_aspect_set_to(VideoAspect.FIT),
                "icon": ICONS["custom/003-aspect fit"],
            },
            "Aspect Stretch": {
                "key": "Ctrl+2",
                "func": lambda: self.player.cmd_active(
                    "set_aspect", VideoAspect.STRETCH
                ),
                "check": lambda: self.player.is_active_aspect_set_to(
                    VideoAspect.STRETCH
                ),
                "icon": ICONS["custom/004-aspect stretch"],
            },
            "Aspect None": {
                "key": "Ctrl+3",
                "func": lambda: self.player.cmd_active("set_aspect", VideoAspect.NONE),
                "check": lambda: self.player.is_active_aspect_set_to(VideoAspect.NONE),
                "icon": ICONS["custom/005-aspect none"],
            },
            "Rows First": {
                "key": "Alt+1",
                "func": lambda: self.player.cmd_set_grid_mode(GridMode.AUTO_ROWS),
                "check": lambda: self.player.playlist_params.grid_mode
                == GridMode.AUTO_ROWS,
                "icon": ICONS["custom/007-rows first"],
            },
            "Columns First": {
                "key": "Alt+2",
                "func": lambda: self.player.cmd_set_grid_mode(GridMode.AUTO_COLS),
                "check": lambda: self.player.playlist_params.grid_mode
                == GridMode.AUTO_COLS,
                "icon": ICONS["custom/008-columns first"],
            },
            "Zoom In": {
                "key": "+",
                "func": lambda: self.player.cmd_active("scale_increase"),
                "icon": ICONS["basic/235-zoom in"],
            },
            "Zoom Out": {
                "key": "-",
                "func": lambda: self.player.cmd_active("scale_decrease"),
                "icon": ICONS["basic/236-zoom out"],
            },
            "Zoom Reset": {
                "key": "*",
                "func": lambda: self.player.cmd_active("scale_reset"),
                "icon": ICONS["basic/234-zoom"],
            },
            "Faster": {
                "key": "C",
                "func": lambda: self.player.cmd_active("rate_increase"),
                "icon": ICONS["custom/027-speed faster"],
            },
            "Slower": {
                "key": "X",
                "func": lambda: self.player.cmd_active("rate_decrease"),
                "icon": ICONS["custom/028-speed slower"],
            },
            "Normal": {
                "key": "Z",
                "func": lambda: self.player.cmd_active("rate_reset"),
                "icon": ICONS["custom/029-speed reset"],
            },
            "Next frame": {
                "key": "S",
                "func": lambda: self.player.cmd_active("step_frame", 1),
                "icon": ICONS["basic/084-forward"],
            },
            "Previous frame": {
                "key": "D",
                "func": lambda: self.player.cmd_active("step_frame", -1),
                "icon": ICONS["basic/083-backward"],
            },
            "Fullscreen": {
                "key": "F",
                "func": self.player.cmd_fullscreen,
                "icon": ICONS["custom/015-fullscreen"],
                "check": lambda: self.player.isFullScreen(),
            },
            "Play / Pause": {
                "key": Qt.CTRL + Qt.Key_Space,
                "func": lambda: self.player.cmd_active("play_pause"),
                "icon": ICONS["basic/145-play"],
            },
            "Play / Pause [ALL]": {
                "key": Qt.Key_Space,
                "func": self.player.play_pause_all,
                "icon": ICONS["custom/009-play all"],
            },
            "Random Loop": {
                "key": "Ctrl+R",
                "func": lambda: self.player.cmd_active("toggle_loop_random"),
                "check": lambda: self.player.is_active_loop_random(),
                "icon": ICONS["custom/011-random"],
            },
            "Set Loop Start": {
                "key": ",",
                "func": lambda: self.player.cmd_active("set_loop_start"),
                "icon": ICONS["custom/013-loop start"],
            },
            "Set Loop End": {
                "key": ".",
                "func": lambda: self.player.cmd_active("set_loop_end"),
                "icon": ICONS["custom/014-loop end"],
            },
            "Loop Reset": {
                "key": "/",
                "func": lambda: self.player.cmd_active("reset_loop"),
                "icon": ICONS["custom/012-loop reset"],
            },
            "Random": {
                "key": "R",
                "func": lambda: self.player.seek_random.emit(),
                "icon": ICONS["custom/011-random"],
            },
            "Open Playlist": {
                "key": "Ctrl+O",
                "func": self.player.cmd_open_playlist,
                "icon": ICONS["basic/093-folder"],
            },
            "Save Playlist": {
                "key": "Ctrl+S",
                "func": self.player.cmd_save_playlist,
                "enabled_if": lambda: len(self.player.video_blocks) > 0,
                "icon": ICONS["basic/067-down arrow"],
            },
            "Close Playlist": {
                "key": "Ctrl+Shift+Q",
                "func": self.player.cmd_close_playlist,
                "enabled_if": lambda: len(self.player.video_blocks) > 0,
                "icon": ICONS["custom/002-close all"],
            },
            "+1%": {
                "key": Qt.Key_Right,
                "func": lambda: self.player.seek_shift_all(1),
                "icon": ICONS["custom/020-plus-1"],
            },
            "+5%": {
                "key": Qt.SHIFT + Qt.Key_Right,
                "func": lambda: self.player.seek_shift_all(5),
                "icon": ICONS["custom/021-plus-5"],
            },
            "+10%": {
                "key": Qt.CTRL + Qt.Key_Right,
                "func": lambda: self.player.seek_shift_all(10),
                "icon": ICONS["custom/022-plus-10"],
            },
            "-1%": {
                "key": Qt.Key_Left,
                "func": lambda: self.player.seek_shift_all(-1),
                "icon": ICONS["custom/023-minus-1"],
            },
            "-5%": {
                "key": Qt.SHIFT + Qt.Key_Left,
                "func": lambda: self.player.seek_shift_all(-5),
                "icon": ICONS["custom/024-minus-5"],
            },
            "-10%": {
                "key": Qt.CTRL + Qt.Key_Left,
                "func": lambda: self.player.seek_shift_all(-10),
                "icon": ICONS["custom/025-minus-10"],
            },
            "Settings": {
                "key": Qt.Key_F5,
                "func": self.player.cmd_settings,
                "icon": ICONS["basic/166-gear"],
            },
            "About": {
                "key": Qt.Key_F1,
                "func": self.player.cmd_about,
                "icon": ICONS["basic/155-ribbon"],
            },
            "Next Video": {
                "key": Qt.Key_Tab,
                "func": self.player.next_single_video,
                "icon": ICONS["basic/157-right"],
            },
        }

        for cmd_name, cmd in commands.items():
            act = QAction(cmd_name, self.player)
            act.triggered.connect(cmd["func"])
            act.setShortcut(QKeySequence(cmd["key"]))

            if "icon" in cmd:
                act.setIcon(cmd["icon"])

            if "check" in cmd:
                act.setCheckable(True)
                act.is_checked_test = cmd["check"]

            if "enabled_if" in cmd:
                act.is_enabled_test = cmd["enabled_if"]

            self.player.addAction(act)

            self.actions[cmd_name] = act

    def make_menu(self):
        menu = QMenu()
        menu.installEventFilter(self.player)
        menu.setStyle(BigMenuIcons())
        menu.setStyleSheet(
            """
            QMenu::item { height:24px; padding: 2px; margin: 0 5px;}
            QMenu::item:selected { background-color: #53aedf; }
            QMenu::item:checked { background-color: #7b888f; }
            QMenu::separator { height: 2px; margin: 0; }
            """
        )

        menu_video_active = [
            "Play / Pause",
            (
                {"name": "Step", "icon": ICONS["basic/084-forward"]},
                ("Next frame", "Previous frame",),
            ),
            (
                {"name": "Loop", "icon": ICONS["basic/153-refresh"]},
                ("Random Loop", "---", "Set Loop Start", "Set Loop End", "Loop Reset",),
            ),
            (
                {"name": "Speed", "icon": ICONS["custom/026-speed"]},
                ("Faster", "Slower", "Normal",),
            ),
            (
                {"name": "Zoom", "icon": ICONS["basic/163-search"]},
                ("Zoom In", "Zoom Out", "Zoom Reset",),
            ),
            (
                {"name": "Aspect", "icon": ICONS["custom/006-aspect"]},
                ("Aspect Fit", "Aspect Stretch", "Aspect None",),
            ),
        ]

        menu_video_block = [
            "Close",
        ]

        menu_video_single = [
            "Next Video",
        ]

        menu_video_all = (
            "Play / Pause [ALL]",
            (
                {"name": "Jump (to) [ALL]", "icon": ICONS["custom/010-jump"]},
                ("Random", "---", "+1%", "+5%", "+10%", "-1%", "-5%", "-10%",),
            ),
            (
                {"name": "Grid", "icon": ICONS["basic/099-squares"]},
                ("Rows First", "Columns First",),
            ),
        )

        menu_player = (
            "Fullscreen",
            "Minimize",
        )

        menu_program = (
            "Add Files",
            "Open Playlist",
            "Save Playlist",
            "Close Playlist",
            "---",
            "Settings",
            "About",
            "---",
            "Quit",
        )

        menu_blocks = []
        if self.player.active_video_block is not None:
            if self.player.active_video_block.video.is_video_initialized:
                menu_video = menu_video_active + menu_video_block
            else:
                menu_video = menu_video_block

            menu_blocks.append(menu_video)

            if self.player.is_single_mode:
                menu_blocks.append(menu_video_single)
        if self.player.video_blocks:
            menu_blocks.append(menu_video_all)
        menu_blocks.append(menu_player)
        menu_blocks.append(menu_program)

        menu_template = []
        for m_block in menu_blocks:
            menu_template.extend(m_block)
            if m_block != menu_blocks[-1]:
                menu_template.append("---")

        self._add_menu_items(menu, menu_template)

        return menu

    def _add_menu_items(self, menu, items):
        for item in items:
            if isinstance(item, tuple):
                sub, sub_items = item

                if "icon" in sub:
                    sub_menu = menu.addMenu(sub["icon"], sub["name"])
                else:
                    sub_menu = menu.addMenu(sub["name"])

                sub_menu.setStyle(BigMenuIcons())

                self._add_menu_items(sub_menu, sub_items)
            elif item == "---":
                menu.addSeparator()
            else:
                if self.actions[item].isCheckable():
                    self.actions[item].setChecked(self.actions[item].is_checked_test())
                if getattr(self.actions[item], "is_enabled_test", None):
                    self.actions[item].setEnabled(self.actions[item].is_enabled_test())
                menu.addAction(self.actions[item])
