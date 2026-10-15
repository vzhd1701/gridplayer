from gridplayer.params import env
from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    SettingField,
    SpinField,
    TextField,
    When,
)
from gridplayer.params.static import VideoDriver
from gridplayer.utils.qt import translate
from gridplayer.utils.video_driver import is_hw_video_available, session_video_driver

# the drivers that run their videos in processes of their own
VIDEO_DRIVERS_MULTIPROCESS = (
    VideoDriver.VLC_SW,
    VideoDriver.VLC_HW,
)

MAX_VLC_PROCESSES = 64


def no_hw_video_reason() -> str:
    return translate(
        "SettingsDialog",
        "Hardware drivers need an X server (Xwayland), which this session doesn't"
        " have.",
    )


def no_hw_video() -> str | None:
    # these only ever touch Hardware video
    return None if is_hw_video_available() else no_hw_video_reason()


def _is_linux() -> bool:
    return env.IS_LINUX


ADVANCED_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="player/video_driver",
        choices=choices.video_drivers,
        # where Hardware can't run, its Software twin stands in for it
        to_editor=session_video_driver,
    ),
    SpinField(
        settings_key="player/video_driver_players",
        label=translate("SettingsDialog", "Videos per process"),
        minimum=1,
        maximum=MAX_VLC_PROCESSES,
        enabled_when=When("player/video_driver", VIDEO_DRIVERS_MULTIPROCESS),
    ),
    TextField(settings_key="misc/vlc_options"),
    CheckboxField(
        settings_key="internal/opaque_hw_overlay",
        label=translate("SettingsDialog", "Opaque overlay (fix black screen)"),
        shown_if=_is_linux,
        unavailable=no_hw_video,
    ),
    CheckboxField(
        settings_key="internal/fake_overlay_invisibility",
        label=translate(
            "SettingsDialog",
            "Fake overlay invisibility (fix overlay on top of other windows)",
        ),
        shown_if=_is_linux,
        unavailable=no_hw_video,
    ),
    CheckboxField(
        settings_key="internal/force_native_drag_events",
        label=translate(
            "SettingsDialog", "Force native drag-n-drop for in-window drag"
        ),
        shown_if=_is_linux,
    ),
    ComboField(
        settings_key="internal/hw_crop_border_offset",
        label=translate("SettingsDialog", "HW video border fix"),
        choices=choices.hw_crop_borders,
        unavailable=no_hw_video,
        tooltip=translate(
            "SettingsDialog",
            "Crops a few pixels off the edges to hide glitches from hardware video."
            " Auto uses the default for your system.",
        ),
    ),
    CheckboxField(
        settings_key="logging/log_limit",
        label=translate("SettingsDialog", "Limit log file size"),
    ),
    SpinField(
        settings_key="logging/log_limit_size",
        label=translate("SettingsDialog", "Log file size"),
        minimum=1,
        maximum=1024 * 1024,
        suffix=translate("SettingsDialog", "MB"),
        enabled_when=When("logging/log_limit"),
    ),
    SpinField(
        settings_key="logging/log_limit_backups",
        label=translate("SettingsDialog", "Log files to keep"),
        minimum=1,
        maximum=1000,
        enabled_when=When("logging/log_limit"),
    ),
    ComboField(
        settings_key="logging/log_level",
        label=translate("SettingsDialog", "Log level"),
        choices=choices.log_levels,
    ),
    ComboField(
        settings_key="logging/log_level_vlc",
        label=translate("SettingsDialog", "Log level (VLC)"),
        choices=choices.vlc_log_levels,
    ),
)
