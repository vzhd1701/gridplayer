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
    VideoDriver.MPV_SW,
    VideoDriver.MPV_HW,
)

MAX_PLAYER_PROCESSES = 64


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


def _is_windows() -> bool:
    return env.IS_WINDOWS


ADVANCED_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="player/video_driver",
        label=translate("SettingsDialog", "Decoder"),
        choices=choices.video_drivers,
        # where Hardware can't run, its Software twin stands in for it
        to_editor=session_video_driver,
        tooltip=no_hw_video,
    ),
    SpinField(
        settings_key="player/video_driver_players",
        label=translate("SettingsDialog", "Videos per process"),
        minimum=1,
        maximum=MAX_PLAYER_PROCESSES,
        enabled_when=When("player/video_driver", VIDEO_DRIVERS_MULTIPROCESS),
    ),
    TextField(settings_key="misc/mpv_options"),
    ComboField(
        settings_key="player/video_quality",
        label=translate("SettingsDialog", "Video quality"),
        choices=choices.video_qualities,
        enabled_when=When("player/video_driver", (VideoDriver.MPV_HW,)),
        tooltip=translate(
            "SettingsDialog",
            "How much of the graphics card goes on scaling the picture."
            " Auto goes by how big each video is shown and drops a step for"
            " a video that can't keep up. Fast gets the most videos playing"
            " smoothly, Maximum is meant for a few videos on a strong card.",
        ),
    ),
    ComboField(
        settings_key="player/gpu_adapter",
        label=translate("SettingsDialog", "Graphics card"),
        choices=choices.gpu_choices,
        enabled_when=When("player/video_driver", (VideoDriver.MPV_HW,)),
        shown_if=_is_windows,
        tooltip=translate(
            "SettingsDialog",
            "On a laptop with two graphics cards, Windows often starts video"
            " on the weaker one. High performance plays more videos, and uses"
            " more power and memory.",
        ),
    ),
    ComboField(
        settings_key="player/hardware_decoding",
        label=translate("SettingsDialog", "Hardware decoding"),
        choices=choices.hardware_decoding_modes,
        tooltip=translate(
            "SettingsDialog",
            "Auto uses the graphics card with the Hardware decoder and the"
            " CPU with the Software one. Copied to memory also speeds up the"
            " Software decoder, on a computer whose graphics card can decode.",
        ),
    ),
    CheckboxField(
        settings_key="player/fast_scrubbing",
        label=translate("SettingsDialog", "Fast seeking while dragging the timeline"),
        tooltip=translate(
            "SettingsDialog",
            "Jumps between keyframes during the drag, then goes to the exact"
            " spot when the mouse is let go.",
        ),
    ),
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
)
