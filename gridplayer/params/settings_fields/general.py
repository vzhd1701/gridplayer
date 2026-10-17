from PyQt5.QtWidgets import QSystemTrayIcon

from gridplayer.params import env
from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    KeymapField,
    LanguageField,
    PathField,
    SettingField,
    SpinField,
    TextField,
    When,
)
from gridplayer.params.static import CacheMode, ScreenshotFormat
from gridplayer.utils.qt import translate
from gridplayer.utils.screenshots import default_screenshots_dir, screenshots_dir
from gridplayer.utils.taskbar import TaskbarHidingBlocker, taskbar_hiding_blocker

_WITH_TRAY = When("player/tray_icon")


def _no_tray() -> str | None:
    # the page says so under the checkbox, for every option it would take
    return None if QSystemTrayIcon.isSystemTrayAvailable() else ""


def _no_taskbar_hiding() -> str | None:
    blocker = taskbar_hiding_blocker()

    if blocker is None:
        return None

    if blocker == TaskbarHidingBlocker.WAYLAND:
        return translate("SettingsDialog", "Not available on Wayland.")

    if blocker == TaskbarHidingBlocker.GNOME:
        return translate(
            "SettingsDialog",
            "Not available on GNOME. It stops the window from minimizing.",
        )

    return ""


def tray_text(tray: str, menu_bar: str) -> str:
    """What macOS calls the tray is the menu bar."""

    return menu_bar if env.IS_MACOS else tray


GENERAL_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="player/color_scheme",
        label=translate("SettingsDialog", "Color scheme"),
        choices=choices.color_schemes,
        buttons=True,
    ),
    CheckboxField(
        settings_key="player/one_instance",
        label=translate("SettingsDialog", "Allow only one instance"),
    ),
    CheckboxField(
        settings_key="player/stay_on_top",
        label=translate("SettingsDialog", "Stay on top"),
        # the window managers there keep it on top whatever is asked
        shown_if=lambda: not env.IS_LINUX,
    ),
    CheckboxField(
        settings_key="player/start_maximized",
        label=translate("SettingsDialog", "Start with maximized window"),
    ),
    CheckboxField(
        settings_key="player/start_fullscreen",
        label=translate("SettingsDialog", "Start in fullscreen mode"),
    ),
    CheckboxField(
        settings_key="player/inhibit_screensaver",
        label=translate("SettingsDialog", "Disable screensaver while playing"),
    ),
    CheckboxField(
        settings_key="player/media_keys_background",
        label=translate("SettingsDialog", "Control playback with media keys globally"),
    ),
    CheckboxField(
        settings_key="player/tray_icon",
        label=tray_text(
            translate("SettingsDialog", "Show icon in the tray"),
            translate("SettingsDialog", "Show icon in the menu bar"),
        ),
        unavailable=_no_tray,
    ),
    CheckboxField(
        settings_key="player/minimize_to_tray",
        label=tray_text(
            translate("SettingsDialog", "Minimize to the tray"),
            translate("SettingsDialog", "Minimize to the menu bar"),
        ),
        enabled_when=_WITH_TRAY,
    ),
    CheckboxField(
        settings_key="player/close_to_tray",
        label=tray_text(
            translate("SettingsDialog", "Close to the tray"),
            translate("SettingsDialog", "Close to the menu bar"),
        ),
        enabled_when=_WITH_TRAY,
    ),
    CheckboxField(
        settings_key="player/hide_taskbar",
        label=tray_text(
            translate("SettingsDialog", "Hide from the taskbar"),
            translate("SettingsDialog", "Hide from the Dock"),
        ),
        enabled_when=_WITH_TRAY,
        unavailable=_no_taskbar_hiding,
    ),
    CheckboxField(
        settings_key="player/tray_stop_video",
        label=tray_text(
            translate("SettingsDialog", "Stop video decoding while in the tray"),
            translate("SettingsDialog", "Stop video decoding while in the menu bar"),
        ),
        enabled_when=_WITH_TRAY,
        tooltip=translate(
            "SettingsDialog",
            "Audio keeps playing. The picture may be black for a moment when you"
            " show the window.",
        ),
    ),
    CheckboxField(
        settings_key="player/recent_list_enabled",
        label=translate("SettingsDialog", "Enable recent list"),
    ),
    SpinField(
        settings_key="player/recent_list_max_size",
        label=translate("SettingsDialog", "Maximum size"),
        minimum=1,
        maximum=100,
        suffix=translate("SettingsDialog", "(items)"),
        enabled_when=When("player/recent_list_enabled"),
    ),
    CheckboxField(
        settings_key="player/reopen_last_playlist",
        label=translate("SettingsDialog", "Reopen last playlist on startup"),
    ),
    SpinField(
        settings_key="player/video_init_timeout",
        label=translate("SettingsDialog", "Video initialization timeout"),
        minimum=1,
        maximum=1000,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    CheckboxField(
        settings_key="misc/mouse_hide",
        label=translate("SettingsDialog", "Hide mouse after timeout"),
    ),
    SpinField(
        settings_key="misc/mouse_hide_timeout",
        label=translate("SettingsDialog", "Timeout"),
        minimum=1,
        maximum=60,
        suffix=translate("SettingsDialog", "(sec)"),
        enabled_when=When("misc/mouse_hide"),
    ),
    SpinField(
        settings_key="player/list_max_mb",
        label=translate("SettingsDialog", "M3U size limit"),
        minimum=1,
        maximum=8192,
        suffix=translate("SettingsDialog", "(MB)"),
        tooltip=translate(
            "SettingsDialog",
            "Larger M3U, PLS and XSPF playlists won't be loaded. IPTV lists can be"
            " hundreds of MB and take about 2.5 times their size in memory."
            " GridPlayer's own playlists have no limit.",
        ),
    ),
    ComboField(
        settings_key="cache/mode",
        label=translate("SettingsDialog", "Keep"),
        choices=choices.cache_modes,
        buttons=True,
        tooltip=translate(
            "SettingsDialog",
            "Where downloaded thumbnails and lists are kept.\n"
            "On disk: kept after GridPlayer closes, up to the limit.\n"
            "In memory: cleared when GridPlayer closes.",
        ),
    ),
    SpinField(
        settings_key="cache/max_mb",
        label=translate("SettingsDialog", "Limit"),
        minimum=1,
        maximum=8192,
        suffix=translate("SettingsDialog", "(MB)"),
        enabled_when=When("cache/mode", (CacheMode.DISK,)),
        tooltip=translate(
            "SettingsDialog",
            "Maximum cache size on disk. The oldest files are deleted first.",
        ),
    ),
    PathField(
        settings_key="screenshots/dir",
        label=translate("SettingsDialog", "Folder"),
        placeholder=translate("SettingsDialog", "In the data folder"),
        browse_title=translate("SettingsDialog", "Screenshots folder"),
        start_dir=screenshots_dir,
        # the placeholder is short enough to fit, this is where it is
        tooltip=lambda: str(default_screenshots_dir()),
    ),
    TextField(
        settings_key="screenshots/filename_template",
        label=translate("SettingsDialog", "File name"),
        # a file name has to come from somewhere
        blank_is_default=True,
    ),
    ComboField(
        settings_key="screenshots/format",
        label=translate("SettingsDialog", "Format"),
        choices=choices.screenshot_formats,
        buttons=True,
    ),
    SpinField(
        settings_key="screenshots/jpg_quality",
        label=translate("SettingsDialog", "Quality"),
        minimum=1,
        maximum=100,
        enabled_when=When("screenshots/format", (ScreenshotFormat.JPG,)),
    ),
    LanguageField(settings_key="player/language"),
    KeymapField(settings_key="player/keymap"),
)
