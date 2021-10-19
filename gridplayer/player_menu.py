from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction, QMenu, QProxyStyle, QStyle

from gridplayer.params_static import GridMode, VideoAspect


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
                "icon": QIcon.fromTheme("minimize"),
            },
            "Quit": {
                "key": "Q",
                "func": self.player.close,
                "icon": QIcon.fromTheme("quit"),
            },
            "Close": {
                "key": "Ctrl+Q",
                "func": lambda: self.player.cmd_active("exit"),
                "icon": QIcon.fromTheme("close"),
            },
            "Add Files": {
                "key": "Ctrl+A",
                "func": self.player.cmd_add_videos,
                "icon": QIcon.fromTheme("add-files"),
            },
            "Aspect Fit": {
                "key": "Ctrl+1",
                "func": lambda: self.player.cmd_active("set_aspect", VideoAspect.FIT),
                "check": lambda: self.player.is_active_aspect_set_to(VideoAspect.FIT),
                "icon": QIcon.fromTheme("aspect-fit"),
            },
            "Aspect Stretch": {
                "key": "Ctrl+2",
                "func": lambda: self.player.cmd_active(
                    "set_aspect", VideoAspect.STRETCH
                ),
                "check": lambda: self.player.is_active_aspect_set_to(
                    VideoAspect.STRETCH
                ),
                "icon": QIcon.fromTheme("aspect-stretch"),
            },
            "Aspect None": {
                "key": "Ctrl+3",
                "func": lambda: self.player.cmd_active("set_aspect", VideoAspect.NONE),
                "check": lambda: self.player.is_active_aspect_set_to(VideoAspect.NONE),
                "icon": QIcon.fromTheme("aspect-none"),
            },
            "Rows First": {
                "key": "Alt+1",
                "func": lambda: self.player.cmd_set_grid_mode(GridMode.AUTO_ROWS),
                "check": lambda: self.player.playlist_params.grid_mode
                == GridMode.AUTO_ROWS,
                "icon": QIcon.fromTheme("grid-rows-first"),
            },
            "Columns First": {
                "key": "Alt+2",
                "func": lambda: self.player.cmd_set_grid_mode(GridMode.AUTO_COLS),
                "check": lambda: self.player.playlist_params.grid_mode
                == GridMode.AUTO_COLS,
                "icon": QIcon.fromTheme("grid-columns-first"),
            },
            "Zoom In": {
                "key": "+",
                "func": lambda: self.player.cmd_active("scale_increase"),
                "icon": QIcon.fromTheme("zoom-in"),
            },
            "Zoom Out": {
                "key": "-",
                "func": lambda: self.player.cmd_active("scale_decrease"),
                "icon": QIcon.fromTheme("zoom-out"),
            },
            "Zoom Reset": {
                "key": "*",
                "func": lambda: self.player.cmd_active("scale_reset"),
                "icon": QIcon.fromTheme("zoom-reset"),
            },
            "Faster": {
                "key": "C",
                "func": lambda: self.player.cmd_active("rate_increase"),
                "icon": QIcon.fromTheme("speed-faster"),
            },
            "Slower": {
                "key": "X",
                "func": lambda: self.player.cmd_active("rate_decrease"),
                "icon": QIcon.fromTheme("speed-slower"),
            },
            "Normal": {
                "key": "Z",
                "func": lambda: self.player.cmd_active("rate_reset"),
                "icon": QIcon.fromTheme("speed-reset"),
            },
            "Next frame": {
                "key": "S",
                "func": lambda: self.player.cmd_active("step_frame", 1),
                "icon": QIcon.fromTheme("next-frame"),
            },
            "Previous frame": {
                "key": "D",
                "func": lambda: self.player.cmd_active("step_frame", -1),
                "icon": QIcon.fromTheme("previous-frame"),
            },
            "Fullscreen": {
                "key": "F",
                "func": self.player.cmd_fullscreen,
                "icon": QIcon.fromTheme("fullscreen"),
                "check": lambda: self.player.isFullScreen(),
            },
            "Play / Pause": {
                "key": Qt.CTRL + Qt.Key_Space,
                "func": lambda: self.player.cmd_active("play_pause"),
                "icon": QIcon.fromTheme("play"),
            },
            "Play / Pause [ALL]": {
                "key": Qt.Key_Space,
                "func": self.player.play_pause_all,
                "icon": QIcon.fromTheme("play-all"),
            },
            "Random Loop": {
                "key": "Ctrl+R",
                "func": lambda: self.player.cmd_active("toggle_loop_random"),
                "check": lambda: self.player.is_active_loop_random(),
                "icon": QIcon.fromTheme("loop-random"),
            },
            "Set Loop Start": {
                "key": ",",
                "func": lambda: self.player.cmd_active("set_loop_start"),
                "icon": QIcon.fromTheme("loop-start"),
            },
            "Set Loop End": {
                "key": ".",
                "func": lambda: self.player.cmd_active("set_loop_end"),
                "icon": QIcon.fromTheme("loop-end"),
            },
            "Loop Reset": {
                "key": "/",
                "func": lambda: self.player.cmd_active("reset_loop"),
                "icon": QIcon.fromTheme("loop-reset"),
            },
            "Random": {
                "key": "R",
                "func": lambda: self.player.seek_random.emit(),
                "icon": QIcon.fromTheme("custom/011-random"),
            },
            "Open Playlist": {
                "key": "Ctrl+O",
                "func": self.player.cmd_open_playlist,
                "icon": QIcon.fromTheme("open-playlist"),
            },
            "Save Playlist": {
                "key": "Ctrl+S",
                "func": self.player.cmd_save_playlist,
                "enabled_if": lambda: len(self.player.video_blocks) > 0,
                "icon": QIcon.fromTheme("save-playlist"),
            },
            "Close Playlist": {
                "key": "Ctrl+Shift+Q",
                "func": self.player.cmd_close_playlist,
                "enabled_if": lambda: len(self.player.video_blocks) > 0,
                "icon": QIcon.fromTheme("close-playlist"),
            },
            "+1%": {
                "key": Qt.Key_Right,
                "func": lambda: self.player.seek_shift_all(1),
                "icon": QIcon.fromTheme("seek-plus-1"),
            },
            "+5%": {
                "key": Qt.SHIFT + Qt.Key_Right,
                "func": lambda: self.player.seek_shift_all(5),
                "icon": QIcon.fromTheme("seek-plus-5"),
            },
            "+10%": {
                "key": Qt.CTRL + Qt.Key_Right,
                "func": lambda: self.player.seek_shift_all(10),
                "icon": QIcon.fromTheme("seek-plus-10"),
            },
            "-1%": {
                "key": Qt.Key_Left,
                "func": lambda: self.player.seek_shift_all(-1),
                "icon": QIcon.fromTheme("seek-minus-1"),
            },
            "-5%": {
                "key": Qt.SHIFT + Qt.Key_Left,
                "func": lambda: self.player.seek_shift_all(-5),
                "icon": QIcon.fromTheme("seek-minus-5"),
            },
            "-10%": {
                "key": Qt.CTRL + Qt.Key_Left,
                "func": lambda: self.player.seek_shift_all(-10),
                "icon": QIcon.fromTheme("seek-minus-10"),
            },
            "Settings": {
                "key": Qt.Key_F5,
                "func": self.player.cmd_settings,
                "icon": QIcon.fromTheme("settings"),
            },
            "About": {
                "key": Qt.Key_F1,
                "func": self.player.cmd_about,
                "icon": QIcon.fromTheme("about"),
            },
            "Next Video": {
                "key": Qt.Key_Tab,
                "func": self.player.next_single_video,
                "icon": QIcon.fromTheme("next-video"),
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
                {"name": "Step", "icon": QIcon.fromTheme("next-frame")},
                (
                    "Next frame",
                    "Previous frame",
                ),
            ),
            (
                {"name": "Loop", "icon": QIcon.fromTheme("loop")},
                (
                    "Random Loop",
                    "---",
                    "Set Loop Start",
                    "Set Loop End",
                    "Loop Reset",
                ),
            ),
            (
                {"name": "Speed", "icon": QIcon.fromTheme("speed")},
                (
                    "Faster",
                    "Slower",
                    "Normal",
                ),
            ),
            (
                {"name": "Zoom", "icon": QIcon.fromTheme("zoom")},
                (
                    "Zoom In",
                    "Zoom Out",
                    "Zoom Reset",
                ),
            ),
            (
                {"name": "Aspect", "icon": QIcon.fromTheme("aspect")},
                (
                    "Aspect Fit",
                    "Aspect Stretch",
                    "Aspect None",
                ),
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
                {"name": "Jump (to) [ALL]", "icon": QIcon.fromTheme("jump-to")},
                (
                    "Random",
                    "---",
                    "+1%",
                    "+5%",
                    "+10%",
                    "-1%",
                    "-5%",
                    "-10%",
                ),
            ),
            (
                {"name": "Grid", "icon": QIcon.fromTheme("grid")},
                (
                    "Rows First",
                    "Columns First",
                ),
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
