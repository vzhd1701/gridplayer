from dataclasses import dataclass

from gridplayer.params import env
from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    SettingField,
    SpinField,
    TextField,
    VideoDriverField,
    When,
)
from gridplayer.params.static import MpvOutput, VideoDriver
from gridplayer.utils.media_libs import (
    MPV_DRIVERS,
    VLC_DRIVERS,
    VLC_HW_DRIVERS,
    MediaLib,
    lib_of_driver,
    lib_problem_text,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.video_driver import (
    MULTIPROCESS_DRIVERS,
    is_hw_video_available,
    session_video_driver,
)
from gridplayer.version import __app_url__

MAX_VLC_PROCESSES = 64

DECODER_HELP_URL = f"{__app_url__}#when-a-mode-isnt-available"


def no_hw_video_reason() -> str:
    return translate(
        "SettingsDialog",
        "VLC Hardware needs an X server (Xwayland), which this session doesn't have.",
    )


def no_hw_video() -> str | None:
    # these only ever touch Hardware video
    return None if is_hw_video_available() else no_hw_video_reason()


@dataclass(frozen=True)
class DriverNotice:
    # a pick that can't run; or else only what else isn't available
    is_problem: bool
    title: str
    lines: tuple[str, ...]


def _how_to_fix() -> str:
    text = translate("SettingsDialog", "How to fix")
    return f'<a href="{DECODER_HELP_URL}">{text}</a>'


def _standing_in_title(stored: VideoDriver, running: VideoDriver) -> str:
    if lib_of_driver(stored) == lib_of_driver(running):
        return translate(
            "SettingsDialog",
            "VLC Hardware can't run. Playing with VLC Software for now.",
        )

    if lib_of_driver(stored) == MediaLib.MPV:
        return translate("SettingsDialog", "MPV can't run. Playing with VLC for now.")

    return translate("SettingsDialog", "VLC can't run. Playing with MPV for now.")


def driver_notice(stored: VideoDriver, shown: VideoDriver) -> DriverNotice | None:
    """What isn't available and why; first of all, the pick that can't run,
    until another one is made. None if everything is."""

    running = session_video_driver(stored)
    # it's the stand-in on show, and nobody has picked it
    is_standing_in = shown == running != stored

    lines = []

    for lib in MediaLib:
        said = lib_problem_text(lib)
        if said is None:
            continue

        if lib == MediaLib.MPV and not (
            is_standing_in and lib_of_driver(stored) == lib
        ):
            said = "MPV: " + said

        lines.append(f"{said}. {_how_to_fix()}")

    if not is_hw_video_available():
        said = translate("SettingsDialog", "VLC Hardware: needs X11.")
        lines.append(f"{said} {_how_to_fix()}")

    if not lines:
        return None

    if is_standing_in:
        title = _standing_in_title(stored, running)
    else:
        title = translate("SettingsDialog", "Some modes aren't available")

    return DriverNotice(is_standing_in, title, tuple(lines))


def _is_linux() -> bool:
    return env.IS_LINUX


def _is_not_macos() -> bool:
    return not env.IS_MACOS


def _is_windows() -> bool:
    return env.IS_WINDOWS


ADVANCED_FIELDS: tuple[SettingField, ...] = (
    VideoDriverField(
        settings_key="player/video_driver",
        label=translate("SettingsDialog", "Decoder"),
        choices=choices.video_drivers,
        unavailable_choices=choices.unavailable_video_drivers,
        # what's going to run: a Hardware twin, or the other library's driver
        to_editor=session_video_driver,
        processes_label=translate("SettingsDialog", "Processes"),
        processes=choices.video_driver_processes,
        processes_tooltip=translate(
            "SettingsDialog",
            "Multi-process plays videos in separate processes, so if one crashes"
            " the others keep playing. Single process plays them inside GridPlayer.",
        ),
    ),
    SpinField(
        settings_key="player/video_driver_players",
        label=translate("SettingsDialog", "Videos per process"),
        minimum=1,
        maximum=MAX_VLC_PROCESSES,
        enabled_when=When("player/video_driver", MULTIPROCESS_DRIVERS),
    ),
    ComboField(
        settings_key="player/mpv_output",
        label=translate("SettingsDialog", "Video output"),
        choices=choices.mpv_outputs,
        buttons=True,
        # MPV hasn't been run there yet: Stage 11
        shown_if=_is_not_macos,
        # Software MPV draws on the CPU, always the Steady way
        enabled_when=When("player/video_driver", (VideoDriver.MPV_HW,)),
        tooltip=translate(
            "SettingsDialog",
            "Fast often uses less CPU, mostly with a few videos. Works after you"
            " restart GridPlayer.",
        ),
    ),
    CheckboxField(
        settings_key="player/mpv_skip_frames",
        label=translate("SettingsDialog", "Skip frames to play more videos"),
        enabled_when=When("player/video_driver", MPV_DRIVERS),
        tooltip=translate(
            "SettingsDialog",
            "Plays about half the frames of each video, so more videos can play"
            " at once before they slow down. Doesn't help videos with no frames"
            " it can skip.",
        ),
    ),
    ComboField(
        settings_key="player/mpv_cpu_decoding",
        label=translate("SettingsDialog", "Decode on the CPU"),
        choices=choices.mpv_cpu_decodings,
        enabled_when=When("player/video_driver", (VideoDriver.MPV_HW,)),
        tooltip=translate(
            "SettingsDialog",
            "Decodes videos on the CPU and draws them on the GPU. Plays more videos"
            " on a strong CPU and uses less video memory. Auto does it for new"
            " videos when video memory runs low. Works for videos opened after.",
        ),
    ),
    CheckboxField(
        settings_key="player/mpv_direct_rendering",
        label=translate("SettingsDialog", "Hand frames straight to the GPU"),
        # Software MPV has no GPU to hand them to
        enabled_when=When("player/video_driver", (VideoDriver.MPV_HW,)),
        tooltip=translate(
            "SettingsDialog",
            "When the CPU decodes, this saves copying each frame. Turn it off if"
            " memory keeps growing as you close videos, as it can on NVIDIA. Works"
            " for videos opened after.",
        ),
    ),
    ComboField(
        settings_key="player/mpv_seek_precision",
        label=translate("SettingsDialog", "Seeking"),
        choices=choices.seek_precisions,
        enabled_when=When("player/video_driver", MPV_DRIVERS),
        tooltip=translate(
            "SettingsDialog",
            "Fast seeks land on the nearest key frame, which can be a few seconds"
            " off. Frame steps and synced videos are always exact.",
        ),
    ),
    TextField(
        settings_key="misc/vlc_options",
        # its section, title and all, goes with it
        shown_when=When("player/video_driver", VLC_DRIVERS),
    ),
    CheckboxField(
        settings_key="internal/opaque_hw_overlay",
        label=translate("SettingsDialog", "Opaque overlay (fix black screen)"),
        shown_if=_is_linux,
        unavailable=no_hw_video,
        shown_when=When("player/video_driver", VLC_HW_DRIVERS),
    ),
    CheckboxField(
        settings_key="internal/fake_overlay_invisibility",
        label=translate(
            "SettingsDialog",
            "Fake overlay invisibility (fix overlay on top of other windows)",
        ),
        shown_if=_is_linux,
        unavailable=no_hw_video,
        shown_when=When("player/video_driver", VLC_HW_DRIVERS),
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
        shown_when=When("player/video_driver", VLC_HW_DRIVERS),
        tooltip=translate(
            "SettingsDialog",
            "Crops a few pixels off the edges to hide glitches from hardware video."
            " Auto uses the default for your system.",
        ),
    ),
    ComboField(
        settings_key="internal/gl_line_fix",
        label=translate("SettingsDialog", "Black line fix"),
        choices=choices.gl_line_fixes,
        shown_if=_is_windows,
        # Video output is there only for Hardware MPV, so this is too
        shown_when=When("player/mpv_output", (MpvOutput.GL,)),
        tooltip=translate(
            "SettingsDialog",
            "Fixes a black line at the bottom of the window with Fast video output."
            " Uses more CPU. Auto turns it on for NVIDIA. Works after you restart"
            " GridPlayer.",
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
        tooltip=translate(
            "SettingsDialog",
            "On Windows, VLC with hardware decoding in a single process writes"
            " no log, as it could freeze GridPlayer.",
        ),
    ),
    ComboField(
        settings_key="logging/log_level_mpv",
        label=translate("SettingsDialog", "Log level (MPV)"),
        choices=choices.vlc_log_levels,
    ),
)
