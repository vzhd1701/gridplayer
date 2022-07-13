from collections import Counter
from types import MappingProxyType
from typing import Dict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction

from gridplayer.params.static import GridMode, SeekSyncMode, VideoAspect, VideoRepeat
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import translate
from gridplayer.widgets.custom_menu import CustomMenu

COMMANDS = MappingProxyType(
    {
        # Single Video
        "Play / Pause": {
            "title": translate("Actions", "Play / Pause"),
            "key": Qt.CTRL + Qt.Key_Space,
            "icon": "play",
            "func": ("active", "play_pause"),
            "show_if": "is_active_initialized",
        },
        "Previous Video": {
            "title": translate("Actions", "Previous Video"),
            "key": "B",
            "icon": "previous-video",
            "func": "previous_single_video",
            "show_if": "is_single_mode",
        },
        "Next Video": {
            "title": translate("Actions", "Next Video"),
            "key": "N",
            "icon": "next-video",
            "func": "next_single_video",
            "show_if": "is_single_mode",
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
        "0%": {
            "title": "0%",
            "key": "0",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0),
            "show_if": "is_active_seekable",
        },
        "10%": {
            "title": "10%",
            "key": "1",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.1),
            "show_if": "is_active_seekable",
        },
        "20%": {
            "title": "20%",
            "key": "2",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.2),
            "show_if": "is_active_seekable",
        },
        "30%": {
            "title": "30%",
            "key": "3",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.3),
            "show_if": "is_active_seekable",
        },
        "40%": {
            "title": "40%",
            "key": "4",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.4),
            "show_if": "is_active_seekable",
        },
        "50%": {
            "title": "50%",
            "key": "5",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.5),
            "show_if": "is_active_seekable",
        },
        "60%": {
            "title": "60%",
            "key": "6",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.6),
            "show_if": "is_active_seekable",
        },
        "70%": {
            "title": "70%",
            "key": "7",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.7),
            "show_if": "is_active_seekable",
        },
        "80%": {
            "title": "80%",
            "key": "8",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.8),
            "show_if": "is_active_seekable",
        },
        "90%": {
            "title": "90%",
            "key": "9",
            "icon": "empty",
            "func": ("active", "manual_seek", "seek_percent", 0.9),
            "show_if": "is_active_seekable",
        },
        "Timecode": {
            "title": translate("Actions", "Timecode"),
            "key": "T",
            "icon": "seek-sync-time",
            "func": ("active", "seek_timecode"),
            "show_if": "is_active_seekable",
        },
        "Random": {
            "title": translate("Actions", "Random"),
            "key": "R",
            "icon": "loop-random",
            "func": ("active", "manual_seek", "seek_random"),
            "show_if": "is_active_seekable",
        },
        "Next frame": {
            "title": translate("Actions", "Next frame"),
            "key": "S",
            "icon": "next-frame",
            "func": ("active", "manual_seek", "next_frame"),
            "show_if": "is_active_seekable",
        },
        "Previous frame": {
            "title": translate("Actions", "Previous frame"),
            "key": "D",
            "icon": "previous-frame",
            "func": ("active", "manual_seek", "previous_frame"),
            "show_if": "is_active_seekable",
        },
        "+1%": {
            "title": "+1%",
            "key": "Right",
            "icon": "seek-plus-1",
            "func": ("active", "manual_seek", "seek_shift_percent", 1),
            "show_if": "is_active_seekable",
        },
        "+5%": {
            "title": "+5%",
            "key": "]",
            "icon": "seek-plus-5",
            "func": ("active", "manual_seek", "seek_shift_percent", 5),
            "show_if": "is_active_seekable",
        },
        "+10%": {
            "title": "+10%",
            "key": "'",
            "icon": "seek-plus-10",
            "func": ("active", "manual_seek", "seek_shift_percent", 10),
            "show_if": "is_active_seekable",
        },
        "-1%": {
            "title": "-1%",
            "key": "Left",
            "icon": "seek-minus-1",
            "func": ("active", "manual_seek", "seek_shift_percent", -1),
            "show_if": "is_active_seekable",
        },
        "-5%": {
            "title": "-5%",
            "key": "[",
            "icon": "seek-minus-5",
            "func": ("active", "manual_seek", "seek_shift_percent", -5),
            "show_if": "is_active_seekable",
        },
        "-10%": {
            "title": "-10%",
            "key": ";",
            "icon": "seek-minus-10",
            "func": ("active", "manual_seek", "seek_shift_percent", -10),
            "show_if": "is_active_seekable",
        },
        "+5s": {
            "title": translate("Actions", "+5s"),
            "key": "Ctrl+Right",
            "icon": "seek-plus-1",
            "func": ("active", "manual_seek", "seek_shift_ms", 5000),
            "show_if": "is_active_seekable",
        },
        "+15s": {
            "title": translate("Actions", "+15s"),
            "key": "Ctrl+]",
            "icon": "seek-plus-5",
            "func": ("active", "manual_seek", "seek_shift_ms", 15000),
            "show_if": "is_active_seekable",
        },
        "+30s": {
            "title": translate("Actions", "+30s"),
            "key": "Ctrl+'",
            "icon": "seek-plus-10",
            "func": ("active", "manual_seek", "seek_shift_ms", 30000),
            "show_if": "is_active_seekable",
        },
        "-5s": {
            "title": translate("Actions", "-5s"),
            "key": "Ctrl+Left",
            "icon": "seek-minus-1",
            "func": ("active", "manual_seek", "seek_shift_ms", -5000),
            "show_if": "is_active_seekable",
        },
        "-15s": {
            "title": translate("Actions", "-15s"),
            "key": "Ctrl+[",
            "icon": "seek-minus-5",
            "func": ("active", "manual_seek", "seek_shift_ms", -15000),
            "show_if": "is_active_seekable",
        },
        "-30s": {
            "title": translate("Actions", "-30s"),
            "key": "Ctrl+;",
            "icon": "seek-minus-10",
            "func": ("active", "manual_seek", "seek_shift_ms", -30000),
            "show_if": "is_active_seekable",
        },
        "Random Loop": {
            "title": translate("Actions", "Random Loop"),
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
        "Zoom In": {
            "title": translate("Actions", "Zoom In"),
            "key": "+",
            "icon": "zoom-in",
            "func": ("active", "scale_increase"),
            "show_if": "is_active_initialized",
        },
        "Zoom Out": {
            "title": translate("Actions", "Zoom Out"),
            "key": "-",
            "icon": "zoom-out",
            "func": ("active", "scale_decrease"),
            "show_if": "is_active_initialized",
        },
        "Zoom Reset": {
            "title": translate("Actions", "Zoom Reset"),
            "key": "*",
            "icon": "zoom-reset",
            "func": ("active", "scale_reset"),
            "show_if": "is_active_initialized",
        },
        "Aspect Fit": {
            "title": translate("Actions", "Aspect Fit"),
            "icon": "aspect-fit",
            "func": ("active", "set_aspect", VideoAspect.FIT),
            "check_if": ("is_active_param_set_to", "aspect_mode", VideoAspect.FIT),
            "show_if": "is_active_initialized",
        },
        "Aspect Stretch": {
            "title": translate("Actions", "Aspect Stretch"),
            "icon": "aspect-stretch",
            "func": ("active", "set_aspect", VideoAspect.STRETCH),
            "check_if": ("is_active_param_set_to", "aspect_mode", VideoAspect.STRETCH),
            "show_if": "is_active_initialized",
        },
        "Aspect None": {
            "title": translate("Actions", "Aspect None"),
            "icon": "aspect-none",
            "func": ("active", "set_aspect", VideoAspect.NONE),
            "check_if": ("is_active_param_set_to", "aspect_mode", VideoAspect.NONE),
            "show_if": "is_active_initialized",
        },
        "Seek Others (Percent)": {
            "title": translate("Actions", "Sync By Percent"),
            "icon": "seek-sync-percent",
            "func": ("active", "sync_others_percent"),
            "show_if": "is_active_seekable",
        },
        "Seek Others (Timecode)": {
            "title": translate("Actions", "Sync By Timecode"),
            "icon": "seek-sync-time",
            "func": ("active", "sync_others_time"),
            "show_if": "is_active_seekable",
        },
        "Stream Quality": {
            "title": translate("Actions", "Stream Quality"),
            "icon": "stream-quality",
            "show_if": "is_active_multistream",
            "menu_generator": "menu_generator_stream_quality",
        },
        "Rename": {
            "title": translate("Actions", "Rename"),
            "key": "F4",
            "icon": "rename",
            "func": ("active", "rename"),
            "show_if": "is_active_initialized",
        },
        "Reload": {
            "title": translate("Actions", "Reload"),
            "icon": "reload",
            "key": "F5",
            "func": ("active", "reload"),
        },
        "Auto Reload: %v": {
            "title": "{0}: %v".format(translate("Actions", "Auto Reload")),
            "icon": "reload",
            "func": ("active", "auto_reload_timer"),
            "value_getter": ("active", "get_auto_reload_timer"),
            "show_if": "is_active_live",
        },
        "Close": {
            "title": translate("Actions", "Close"),
            "key": "Ctrl+F4",
            "icon": "close",
            "func": ("active", "close"),
        },
        # All Videos
        "Play / Pause [ALL]": {
            "title": translate("Actions", "Play / Pause"),
            "key": "Space",
            "icon": "play",
            "func": "all_play_pause",
            "show_if": "is_any_videos_initialized",
        },
        "Play Previous File [ALL]": {
            "title": translate("Actions", "Play Previous File"),
            "key": Qt.SHIFT + Qt.Key_PageUp,
            "icon": "previous-video-file",
            "func": ("all", "previous_video"),
            "show_if": "is_any_videos_local_file",
        },
        "Play Next File [ALL]": {
            "title": translate("Actions", "Play Next File"),
            "key": Qt.SHIFT + Qt.Key_PageDown,
            "icon": "next-video-file",
            "func": ("all", "next_video"),
            "show_if": "is_any_videos_local_file",
        },
        "0% [ALL]": {
            "title": "0%",
            "key": "Alt+0",
            "icon": "empty",
            "func": ("all", "seek_percent", 0),
            "show_if": "is_any_videos_seekable",
        },
        "10% [ALL]": {
            "title": "10%",
            "key": "Alt+1",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.1),
            "show_if": "is_any_videos_seekable",
        },
        "20% [ALL]": {
            "title": "20%",
            "key": "Alt+2",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.2),
            "show_if": "is_any_videos_seekable",
        },
        "30% [ALL]": {
            "title": "30%",
            "key": "Alt+3",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.3),
            "show_if": "is_any_videos_seekable",
        },
        "40% [ALL]": {
            "title": "40%",
            "key": "Alt+4",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.4),
            "show_if": "is_any_videos_seekable",
        },
        "50% [ALL]": {
            "title": "50%",
            "key": "Alt+5",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.5),
            "show_if": "is_any_videos_seekable",
        },
        "60% [ALL]": {
            "title": "60%",
            "key": "Alt+6",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.6),
            "show_if": "is_any_videos_seekable",
        },
        "70% [ALL]": {
            "title": "70%",
            "key": "Alt+7",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.7),
            "show_if": "is_any_videos_seekable",
        },
        "80% [ALL]": {
            "title": "80%",
            "key": "Alt+8",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.8),
            "show_if": "is_any_videos_seekable",
        },
        "90% [ALL]": {
            "title": "90%",
            "key": "Alt+9",
            "icon": "empty",
            "func": ("all", "seek_percent", 0.9),
            "show_if": "is_any_videos_seekable",
        },
        "Timecode [ALL]": {
            "title": translate("Actions", "Timecode"),
            "key": "Shift+T",
            "icon": "seek-sync-time",
            "func": "all_seek_timecode",
            "show_if": "is_any_videos_seekable",
        },
        "Random [ALL]": {
            "title": translate("Actions", "Random"),
            "key": "Shift+R",
            "icon": "loop-random",
            "func": ("all", "seek_random"),
            "show_if": "is_any_videos_seekable",
        },
        "Next frame [ALL]": {
            "title": translate("Actions", "Next frame"),
            "key": "Shift+S",
            "icon": "next-frame",
            "func": ("all", "next_frame"),
            "show_if": "is_any_videos_seekable",
        },
        "Previous frame [ALL]": {
            "title": translate("Actions", "Previous frame"),
            "key": "Shift+D",
            "icon": "previous-frame",
            "func": ("all", "previous_frame"),
            "show_if": "is_any_videos_seekable",
        },
        "+1% [ALL]": {
            "title": "+1%",
            "key": "Shift+Right",
            "icon": "seek-plus-1",
            "func": ("all", "seek_shift_percent", 1),
            "show_if": "is_any_videos_seekable",
        },
        "+5% [ALL]": {
            "title": "+5%",
            "key": "Shift+]",
            "icon": "seek-plus-5",
            "func": ("all", "seek_shift_percent", 5),
            "show_if": "is_any_videos_seekable",
        },
        "+10% [ALL]": {
            "title": "+10%",
            "key": "Shift+'",
            "icon": "seek-plus-10",
            "func": ("all", "seek_shift_percent", 10),
            "show_if": "is_any_videos_seekable",
        },
        "-1% [ALL]": {
            "title": "-1%",
            "key": "Shift+Left",
            "icon": "seek-minus-1",
            "func": ("all", "seek_shift_percent", -1),
            "show_if": "is_any_videos_seekable",
        },
        "-5% [ALL]": {
            "title": "-5%",
            "key": "Shift+[",
            "icon": "seek-minus-5",
            "func": ("all", "seek_shift_percent", -5),
            "show_if": "is_any_videos_seekable",
        },
        "-10% [ALL]": {
            "title": "-10%",
            "key": "Shift+;",
            "icon": "seek-minus-10",
            "func": ("all", "seek_shift_percent", -10),
            "show_if": "is_any_videos_seekable",
        },
        "+5s [ALL]": {
            "title": translate("Actions", "+5s"),
            "key": "Ctrl+Shift+Right",
            "icon": "seek-plus-1",
            "func": ("all", "seek_shift_ms", 5000),
            "show_if": "is_any_videos_seekable",
        },
        "+15s [ALL]": {
            "title": translate("Actions", "+15s"),
            "key": "Ctrl+Shift+]",
            "icon": "seek-plus-5",
            "func": ("all", "seek_shift_ms", 15000),
            "show_if": "is_any_videos_seekable",
        },
        "+30s [ALL]": {
            "title": translate("Actions", "+30s"),
            "key": "Ctrl+Shift+'",
            "icon": "seek-plus-10",
            "func": ("all", "seek_shift_ms", 30000),
            "show_if": "is_any_videos_seekable",
        },
        "-5s [ALL]": {
            "title": translate("Actions", "-5s"),
            "key": "Ctrl+Shift+Left",
            "icon": "seek-minus-1",
            "func": ("all", "seek_shift_ms", -5000),
            "show_if": "is_any_videos_seekable",
        },
        "-15s [ALL]": {
            "title": translate("Actions", "-15s"),
            "key": "Ctrl+Shift+[",
            "icon": "seek-minus-5",
            "func": ("all", "seek_shift_ms", -15000),
            "show_if": "is_any_videos_seekable",
        },
        "-30s [ALL]": {
            "title": translate("Actions", "-30s"),
            "key": "Ctrl+Shift+;",
            "icon": "seek-minus-10",
            "func": ("all", "seek_shift_ms", -30000),
            "show_if": "is_any_videos_seekable",
        },
        "Random Loop [ALL]": {
            "title": translate("Actions", "Random Loop"),
            "icon": "loop-random",
            "func": ("all", "toggle_loop_random"),
            "show_if": "is_any_videos_seekable",
        },
        "Set Loop Start [ALL]": {
            "title": translate("Actions", "Set Loop Start"),
            "key": "Shift+,",
            "icon": "loop-start",
            "func": ("all", "set_loop_start"),
            "show_if": "is_any_videos_seekable",
        },
        "Set Loop End [ALL]": {
            "title": translate("Actions", "Set Loop End"),
            "key": "Shift+.",
            "icon": "loop-end",
            "func": ("all", "set_loop_end"),
            "show_if": "is_any_videos_seekable",
        },
        "Loop Reset [ALL]": {
            "title": translate("Actions", "Loop Reset"),
            "key": "Shift+/",
            "icon": "loop-reset",
            "func": ("all", "reset_loop"),
            "show_if": "is_any_videos_seekable",
        },
        "Repeat Single File [ALL]": {
            "title": translate("Actions", "Repeat Single File"),
            "icon": "loop-single",
            "func": ("all", "set_repeat_mode", VideoRepeat.SINGLE_FILE),
            "show_if": "is_any_videos_local_file",
        },
        "Repeat Directory [ALL]": {
            "title": translate("Actions", "Repeat Directory"),
            "icon": "loop-dir",
            "func": ("all", "set_repeat_mode", VideoRepeat.DIR),
            "show_if": "is_any_videos_local_file",
        },
        "Repeat Directory (Shuffle) [ALL]": {
            "title": translate("Actions", "Repeat Directory (Shuffle)"),
            "icon": "loop-dir-shuffle",
            "func": ("all", "set_repeat_mode", VideoRepeat.DIR_SHUFFLE),
            "show_if": "is_any_videos_local_file",
        },
        "Faster [ALL]": {
            "title": translate("Actions", "Faster"),
            "key": "Shift+C",
            "icon": "speed-faster",
            "func": ("all", "rate_increase"),
            "show_if": "is_any_videos_seekable",
        },
        "Slower [ALL]": {
            "title": translate("Actions", "Slower"),
            "key": "Shift+X",
            "icon": "speed-slower",
            "func": ("all", "rate_decrease"),
            "show_if": "is_any_videos_seekable",
        },
        "Normal [ALL]": {
            "title": translate("Actions", "Normal"),
            "key": "Shift+Z",
            "icon": "speed-reset",
            "func": ("all", "rate_reset"),
            "show_if": "is_any_videos_seekable",
        },
        "Zoom In [ALL]": {
            "title": translate("Actions", "Zoom In"),
            "key": "Shift++",
            "icon": "zoom-in",
            "func": ("all", "scale_increase"),
            "show_if": "is_any_videos_initialized",
        },
        "Zoom Out [ALL]": {
            "title": translate("Actions", "Zoom Out"),
            "key": "Shift+-",
            "icon": "zoom-out",
            "func": ("all", "scale_decrease"),
            "show_if": "is_any_videos_initialized",
        },
        "Zoom Reset [ALL]": {
            "title": translate("Actions", "Zoom Reset"),
            "key": "Shift+*",
            "icon": "zoom-reset",
            "func": ("all", "scale_reset"),
            "show_if": "is_any_videos_initialized",
        },
        "Aspect Fit [ALL]": {
            "title": translate("Actions", "Aspect Fit"),
            "icon": "aspect-fit",
            "func": ("all", "set_aspect", VideoAspect.FIT),
            "show_if": "is_any_videos_initialized",
        },
        "Aspect Stretch [ALL]": {
            "title": translate("Actions", "Aspect Stretch"),
            "icon": "aspect-stretch",
            "func": ("all", "set_aspect", VideoAspect.STRETCH),
            "show_if": "is_any_videos_initialized",
        },
        "Aspect None [ALL]": {
            "title": translate("Actions", "Aspect None"),
            "icon": "aspect-none",
            "func": ("all", "set_aspect", VideoAspect.NONE),
            "show_if": "is_any_videos_initialized",
        },
        "Reload [ALL]": {
            "title": translate("Actions", "Reload"),
            "icon": "reload",
            "key": "Shift+F5",
            "func": "reload_all",
        },
        "Auto Reload [ALL]": {
            "title": translate("Actions", "Auto Reload"),
            "icon": "reload",
            "func": "all_set_auto_reload_timer",
            "show_if": "is_any_videos_live",
        },
        # Playlist
        "Seek Sync (Disabled)": {
            "title": translate("Actions", "Disabled"),
            "icon": "empty",
            "func": ("set_seek_sync_mode", SeekSyncMode.DISABLED),
            "check_if": ("is_seek_sync_mode_set_to", SeekSyncMode.DISABLED),
        },
        "Seek Sync (Percent)": {
            "title": translate("Actions", "Sync By Percent"),
            "icon": "seek-sync-percent",
            "func": ("set_seek_sync_mode", SeekSyncMode.PERCENT),
            "check_if": ("is_seek_sync_mode_set_to", SeekSyncMode.PERCENT),
        },
        "Seek Sync (Timecode)": {
            "title": translate("Actions", "Sync By Timecode"),
            "icon": "seek-sync-time",
            "func": ("set_seek_sync_mode", SeekSyncMode.TIMECODE),
            "check_if": ("is_seek_sync_mode_set_to", SeekSyncMode.TIMECODE),
        },
        "Shuffle Grid": {
            "title": translate("Actions", "Shuffle"),
            "key": "Alt+R",
            "icon": "loop-random",
            "func": "shuffle_video_blocks",
        },
        "Shuffle Grid On Load": {
            "title": translate("Actions", "Shuffle On Load"),
            "icon": "loop-random",
            "func": "toggle_shuffle_on_load",
            "check_if": "is_shuffle_on_load",
        },
        "Rows First": {
            "title": translate("Actions", "Rows First"),
            "icon": "grid-rows-first",
            "func": ("set_grid_mode", GridMode.AUTO_ROWS),
            "check_if": ("is_grid_mode_set_to", GridMode.AUTO_ROWS),
        },
        "Columns First": {
            "title": translate("Actions", "Columns First"),
            "icon": "grid-columns-first",
            "func": ("set_grid_mode", GridMode.AUTO_COLS),
            "check_if": ("is_grid_mode_set_to", GridMode.AUTO_COLS),
        },
        "Fit Cells": {
            "title": translate("Actions", "Fit Cells"),
            "icon": "grid-fit",
            "func": "switch_is_grid_fit",
            "check_if": "is_grid_fit",
        },
        "Size: %v": {
            "title": translate("Actions", "Size: %v"),
            "icon": "grid-size",
            "func": "ask_grid_size",
            "value_getter": "get_grid_size",
        },
        "Save Snapshot (0)": {
            "title": translate("Actions", "Save Snapshot") + " (0)",
            "key": "Ctrl+Alt+0",
            "func": ("save_snapshot", 0),
        },
        "Save Snapshot (1)": {
            "title": translate("Actions", "Save Snapshot") + " (1)",
            "key": "Ctrl+Alt+1",
            "func": ("save_snapshot", 1),
        },
        "Save Snapshot (2)": {
            "title": translate("Actions", "Save Snapshot") + " (2)",
            "key": "Ctrl+Alt+2",
            "func": ("save_snapshot", 2),
        },
        "Save Snapshot (3)": {
            "title": translate("Actions", "Save Snapshot") + " (3)",
            "key": "Ctrl+Alt+3",
            "func": ("save_snapshot", 3),
        },
        "Save Snapshot (4)": {
            "title": translate("Actions", "Save Snapshot") + " (4)",
            "key": "Ctrl+Alt+4",
            "func": ("save_snapshot", 4),
        },
        "Save Snapshot (5)": {
            "title": translate("Actions", "Save Snapshot") + " (5)",
            "key": "Ctrl+Alt+5",
            "func": ("save_snapshot", 5),
        },
        "Save Snapshot (6)": {
            "title": translate("Actions", "Save Snapshot") + " (6)",
            "key": "Ctrl+Alt+6",
            "func": ("save_snapshot", 6),
        },
        "Save Snapshot (7)": {
            "title": translate("Actions", "Save Snapshot") + " (7)",
            "key": "Ctrl+Alt+7",
            "func": ("save_snapshot", 7),
        },
        "Save Snapshot (8)": {
            "title": translate("Actions", "Save Snapshot") + " (8)",
            "key": "Ctrl+Alt+8",
            "func": ("save_snapshot", 8),
        },
        "Save Snapshot (9)": {
            "title": translate("Actions", "Save Snapshot") + " (9)",
            "key": "Ctrl+Alt+9",
            "func": ("save_snapshot", 9),
        },
        "Delete Snapshot (0)": {
            "title": translate("Actions", "Delete Snapshot") + " (0)",
            "func": ("delete_snapshot", 0),
            "show_if": ("is_snapshot_exists", 0),
        },
        "Delete Snapshot (1)": {
            "title": translate("Actions", "Delete Snapshot") + " (1)",
            "func": ("delete_snapshot", 1),
            "show_if": ("is_snapshot_exists", 1),
        },
        "Delete Snapshot (2)": {
            "title": translate("Actions", "Delete Snapshot") + " (2)",
            "func": ("delete_snapshot", 2),
            "show_if": ("is_snapshot_exists", 2),
        },
        "Delete Snapshot (3)": {
            "title": translate("Actions", "Delete Snapshot") + " (3)",
            "func": ("delete_snapshot", 3),
            "show_if": ("is_snapshot_exists", 3),
        },
        "Delete Snapshot (4)": {
            "title": translate("Actions", "Delete Snapshot") + " (4)",
            "func": ("delete_snapshot", 4),
            "show_if": ("is_snapshot_exists", 4),
        },
        "Delete Snapshot (5)": {
            "title": translate("Actions", "Delete Snapshot") + " (5)",
            "func": ("delete_snapshot", 5),
            "show_if": ("is_snapshot_exists", 5),
        },
        "Delete Snapshot (6)": {
            "title": translate("Actions", "Delete Snapshot") + " (6)",
            "func": ("delete_snapshot", 6),
            "show_if": ("is_snapshot_exists", 6),
        },
        "Delete Snapshot (7)": {
            "title": translate("Actions", "Delete Snapshot") + " (7)",
            "func": ("delete_snapshot", 7),
            "show_if": ("is_snapshot_exists", 7),
        },
        "Delete Snapshot (8)": {
            "title": translate("Actions", "Delete Snapshot") + " (8)",
            "func": ("delete_snapshot", 8),
            "show_if": ("is_snapshot_exists", 8),
        },
        "Delete Snapshot (9)": {
            "title": translate("Actions", "Delete Snapshot") + " (9)",
            "func": ("delete_snapshot", 9),
            "show_if": ("is_snapshot_exists", 9),
        },
        "Load Snapshot (0)": {
            "title": translate("Actions", "Load Snapshot") + " (0)",
            "key": "Ctrl+0",
            "func": ("load_snapshot", 0),
            "show_if": ("is_snapshot_exists", 0),
        },
        "Load Snapshot (1)": {
            "title": translate("Actions", "Load Snapshot") + " (1)",
            "key": "Ctrl+1",
            "func": ("load_snapshot", 1),
            "show_if": ("is_snapshot_exists", 1),
        },
        "Load Snapshot (2)": {
            "title": translate("Actions", "Load Snapshot") + " (2)",
            "key": "Ctrl+2",
            "func": ("load_snapshot", 2),
            "show_if": ("is_snapshot_exists", 2),
        },
        "Load Snapshot (3)": {
            "title": translate("Actions", "Load Snapshot") + " (3)",
            "key": "Ctrl+3",
            "func": ("load_snapshot", 3),
            "show_if": ("is_snapshot_exists", 3),
        },
        "Load Snapshot (4)": {
            "title": translate("Actions", "Load Snapshot") + " (4)",
            "key": "Ctrl+4",
            "func": ("load_snapshot", 4),
            "show_if": ("is_snapshot_exists", 4),
        },
        "Load Snapshot (5)": {
            "title": translate("Actions", "Load Snapshot") + " (5)",
            "key": "Ctrl+5",
            "func": ("load_snapshot", 5),
            "show_if": ("is_snapshot_exists", 5),
        },
        "Load Snapshot (6)": {
            "title": translate("Actions", "Load Snapshot") + " (6)",
            "key": "Ctrl+6",
            "func": ("load_snapshot", 6),
            "show_if": ("is_snapshot_exists", 6),
        },
        "Load Snapshot (7)": {
            "title": translate("Actions", "Load Snapshot") + " (7)",
            "key": "Ctrl+7",
            "func": ("load_snapshot", 7),
            "show_if": ("is_snapshot_exists", 7),
        },
        "Load Snapshot (8)": {
            "title": translate("Actions", "Load Snapshot") + " (8)",
            "key": "Ctrl+8",
            "func": ("load_snapshot", 8),
            "show_if": ("is_snapshot_exists", 8),
        },
        "Load Snapshot (9)": {
            "title": translate("Actions", "Load Snapshot") + " (9)",
            "key": "Ctrl+9",
            "func": ("load_snapshot", 9),
            "show_if": ("is_snapshot_exists", 9),
        },
        "Disable Click Pause": {
            "title": translate("Actions", "Disable Click Pause"),
            "icon": "empty",
            "func": "toggle_disable_click_pause",
            "check_if": "is_disable_click_pause",
        },
        "Disable Wheel Seek": {
            "title": translate("Actions", "Disable Wheel Seek"),
            "icon": "empty",
            "func": "toggle_disable_wheel_seek",
            "check_if": "is_disable_wheel_seek",
        },
        # Program
        "Fullscreen": {
            "title": translate("Actions", "Fullscreen"),
            "key": "F",
            "icon": "fullscreen",
            "func": "fullscreen",
            "check_if": "is_fullscreen",
        },
        "Minimize": {
            "title": translate("Actions", "Minimize"),
            "key": Qt.Key_Escape,
            "icon": "minimize",
            "func": "minimize",
        },
        "Add Files": {
            "title": translate("Actions", "Add Files"),
            "key": "Ctrl+A",
            "icon": "add-files",
            "func": "add_videos",
        },
        "Add URL(s)": {
            "title": translate("Actions", "Add URL(s)"),
            "key": "Ctrl+U",
            "icon": "add-files",
            "func": "add_urls",
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
        "Settings": {
            "title": translate("Actions", "Settings"),
            "key": "F6",
            "icon": "settings",
            "func": "settings",
        },
        "About": {
            "title": translate("Actions", "About"),
            "key": "F1",
            "icon": "about",
            "func": "about",
        },
        "Quit": {
            "title": translate("Actions", "Quit"),
            "key": "Q",
            "icon": "quit",
            "func": "close",
        },
        # Invisible
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

        generated_menu = CustomMenu()

        for a in actions:
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


def _raise_on_duplicate_shortcuts():
    shortcuts = [c["key"] for c in COMMANDS.values() if c.get("key")]

    duplicate_shortcuts = [
        key for key, count in Counter(shortcuts).items() if count > 1
    ]

    if duplicate_shortcuts:
        raise RuntimeError(f"Duplicate shortcuts found: {duplicate_shortcuts}")
