from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from gridplayer.params import env
from gridplayer.params.static import (
    MAX_RATE,
    MAX_SCALE,
    MIN_RATE,
    MIN_SCALE,
    AudioChannelMode,
    DropAction,
    DropModifier,
    GridMode,
    SeekSyncMode,
    UnsavedChangesMode,
    VideoAspect,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.utils.qt import translate


class FieldKind(Enum):
    CHECKBOX = auto()
    COMBO = auto()
    SPIN = auto()
    FLOAT_SPIN = auto()
    CROP = auto()
    COLOR = auto()


class GridVisibility(Enum):
    ALWAYS = auto()
    AUTO_ONLY = auto()
    FIXED_ONLY = auto()


@dataclass(frozen=True)
class SettingField:
    settings_key: str
    kind: FieldKind
    section: str
    label: str
    playlist_attr: str | None = None
    video_attr: str | None = None
    is_grid: bool = False
    menu_action: str | None = None
    combo_values: Callable[[], dict] | None = None
    spin_min: float = 0
    spin_max: float = 100
    spin_decimals: int = 0
    spin_step: float = 0.1
    spin_special: str | None = None
    spin_suffix: str | None = None
    enabled_by: str | None = None
    grid_visibility: GridVisibility = GridVisibility.ALWAYS
    tooltip: str | None = None


def _t(text: str) -> str:
    return translate("SettingsDialog", text)


def _grid_modes() -> dict:
    return {
        GridMode.AUTO_ROWS: _t("Auto (Rows First)"),
        GridMode.AUTO_COLS: _t("Auto (Columns First)"),
        GridMode.FIXED: _t("Fixed Grid"),
    }


def _seek_sync_modes() -> dict:
    return {
        SeekSyncMode.DISABLED: _t("Disabled"),
        SeekSyncMode.PERCENT: _t("Percent"),
        SeekSyncMode.TIMECODE: _t("Timecode"),
    }


def _unsaved_changes_modes() -> dict:
    return {
        UnsavedChangesMode.ASK: _t("Ask"),
        UnsavedChangesMode.DISCARD: _t("Discard Changes"),
        UnsavedChangesMode.AUTO_SAVE_DISCARD: _t("Auto Save or Discard"),
        UnsavedChangesMode.AUTO_SAVE_ASK: _t("Auto Save or Ask"),
    }


def _unsaved_changes_tooltip() -> str:
    return _t(
        "Auto save applies only when the playlist has a file location; "
        "otherwise the fallback action is used."
    )


def _drop_internal() -> dict:
    return {
        DropAction.INSERT: _t("Move / Swap"),
        DropAction.REPLACE: _t("Replace"),
    }


def _drop_external() -> dict:
    return {
        DropAction.INSERT: _t("Add"),
        DropAction.REPLACE: _t("Replace"),
    }


def _drop_modifiers() -> dict:
    if env.IS_MACOS:
        return {
            DropModifier.SHIFT: _t("Shift"),
            DropModifier.CTRL: _t("Cmd"),
            DropModifier.ALT: _t("Option"),
            DropModifier.NONE: _t("Disabled"),
        }
    return {
        DropModifier.SHIFT: _t("Shift"),
        DropModifier.CTRL: _t("Ctrl"),
        DropModifier.ALT: _t("Alt"),
        DropModifier.NONE: _t("Disabled"),
    }


def _drop_modifier_tooltip() -> str | None:
    if not env.IS_LINUX:
        return None
    return _t(
        "On GNOME, dropping files from the file manager only honors Shift. "
        "Ctrl and Alt still work when dragging videos inside the player."
    )


def _aspects() -> dict:
    return {
        VideoAspect.FIT: _t("Fit"),
        VideoAspect.STRETCH: _t("Stretch"),
        VideoAspect.NONE: _t("None"),
    }


def _transforms() -> dict:
    return {
        VideoTransform.ROTATE_90: _t("Rotate 90"),
        VideoTransform.ROTATE_180: _t("Rotate 180"),
        VideoTransform.ROTATE_270: _t("Rotate 270"),
        VideoTransform.HFLIP: _t("Flip Horizontally"),
        VideoTransform.VFLIP: _t("Flip Vertically"),
        VideoTransform.TRANSPOSE: _t("Transpose"),
        VideoTransform.ANTITRANSPOSE: _t("Anti-transpose"),
        VideoTransform.NONE: _t("No Transform"),
    }


def _repeat_modes() -> dict:
    return {
        VideoRepeat.SINGLE_FILE: _t("Single File"),
        VideoRepeat.DIR: _t("Directory"),
        VideoRepeat.DIR_SHUFFLE: _t("Directory (Shuffle)"),
    }


def _audio_modes() -> dict:
    return {
        AudioChannelMode.UNSET: translate("Audio Mode", "Original"),
        AudioChannelMode.STEREO: translate("Audio Mode", "Stereo"),
        AudioChannelMode.RSTEREO: translate("Audio Mode", "Reverse Stereo"),
        AudioChannelMode.LEFT: translate("Audio Mode", "Left"),
        AudioChannelMode.RIGHT: translate("Audio Mode", "Right"),
        AudioChannelMode.DOLBYS: translate("Audio Mode", "Dolby Surround"),
        AudioChannelMode.HEADPHONES: translate("Audio Mode", "Headphones"),
        AudioChannelMode.MONO: translate("Audio Mode", "Mono"),
    }


def _stream_qualities() -> dict:
    named = {
        "best": _t("Best"),
        "worst": _t("Worst"),
        "best_audio_only": _t("Best (Audio Only)"),
        "worst_audio_only": _t("Worst (Audio Only)"),
    }
    codes = (
        "2160p",
        "2160p60",
        "1440p",
        "1440p60",
        "1080p",
        "1080p60",
        "720p60",
        "720p",
        "480p",
        "360p",
        "240p",
        "144p",
    )
    return {**named, **{code: code for code in codes}}


def _f(**kwargs) -> SettingField:
    return SettingField(**kwargs)


PLAYLIST_FIELDS: tuple[SettingField, ...] = (
    _f(
        settings_key="playlist/unsaved_changes",
        playlist_attr="unsaved_changes",
        kind=FieldKind.COMBO,
        section=_t("Saving / Restoring"),
        label=_t("Unsaved changes on close"),
        combo_values=_unsaved_changes_modes,
        tooltip=_unsaved_changes_tooltip(),
    ),
    _f(
        settings_key="playlist/save_window",
        playlist_attr="save_window",
        kind=FieldKind.CHECKBOX,
        section=_t("Saving / Restoring"),
        label=_t("Save window position and size"),
    ),
    _f(
        settings_key="playlist/save_position",
        playlist_attr="save_position",
        kind=FieldKind.CHECKBOX,
        section=_t("Saving / Restoring"),
        label=_t("Save videos playback position"),
    ),
    _f(
        settings_key="playlist/save_state",
        playlist_attr="save_state",
        kind=FieldKind.CHECKBOX,
        section=_t("Saving / Restoring"),
        label=_t("Save videos playing / paused status"),
    ),
    _f(
        settings_key="playlist/pause_background_videos",
        playlist_attr="pause_background_videos",
        kind=FieldKind.CHECKBOX,
        section=_t("Playback"),
        label=_t("Pause background videos on single mode"),
        menu_action="Pause Background Videos",
    ),
    _f(
        settings_key="playlist/pause_minimized",
        playlist_attr="pause_minimized",
        kind=FieldKind.CHECKBOX,
        section=_t("Playback"),
        label=_t("Pause videos when minimized"),
        menu_action="Pause When Minimized",
    ),
    _f(
        settings_key="playlist/seek_sync_mode",
        playlist_attr="seek_sync_mode",
        kind=FieldKind.COMBO,
        section=_t("Playback"),
        label=_t("Seek sync mode"),
        combo_values=_seek_sync_modes,
    ),
    _f(
        settings_key="playlist/disable_mouse_click_events",
        playlist_attr="disable_mouse_click_events",
        kind=FieldKind.CHECKBOX,
        section=_t("Input"),
        label=_t("Disable mouse click events"),
        menu_action="Disable Mouse Click Events",
    ),
    _f(
        settings_key="playlist/disable_mouse_wheel_events",
        playlist_attr="disable_mouse_wheel_events",
        kind=FieldKind.CHECKBOX,
        section=_t("Input"),
        label=_t("Disable mouse wheel events"),
        menu_action="Disable Mouse Wheel Events",
    ),
    _f(
        settings_key="playlist/disable_overlay",
        playlist_attr="disable_overlay",
        kind=FieldKind.CHECKBOX,
        section=_t("Overlay"),
        label=_t("Disable overlay"),
        menu_action="Disable Overlay",
    ),
    _f(
        settings_key="playlist/show_overlay_border",
        playlist_attr="show_overlay_border",
        kind=FieldKind.CHECKBOX,
        section=_t("Overlay"),
        label=_t("Show overlay border for active video"),
        menu_action="Show Overlay Border",
    ),
    _f(
        settings_key="playlist/overlay_hide_on_timeout",
        playlist_attr="overlay_hide_on_timeout",
        kind=FieldKind.CHECKBOX,
        section=_t("Overlay"),
        label=_t("Hide overlay after timeout"),
        menu_action="Hide Overlay After Timeout",
    ),
    _f(
        settings_key="playlist/overlay_timeout",
        playlist_attr="overlay_timeout",
        kind=FieldKind.SPIN,
        section=_t("Overlay"),
        label=_t("Overlay timeout"),
        spin_min=1,
        spin_max=60,
        spin_suffix=_t("(sec)"),
        enabled_by="playlist/overlay_hide_on_timeout",
    ),
    _f(
        settings_key="playlist/shuffle_on_load",
        playlist_attr="shuffle_on_load",
        kind=FieldKind.CHECKBOX,
        section=_t("Grid"),
        label=_t("Shuffle on load"),
        menu_action="Shuffle Grid On Load",
    ),
    _f(
        settings_key="playlist/grid_mode",
        kind=FieldKind.COMBO,
        section=_t("Grid"),
        label=_t("Grid mode"),
        is_grid=True,
        combo_values=_grid_modes,
    ),
    _f(
        settings_key="playlist/grid_size",
        kind=FieldKind.SPIN,
        section=_t("Grid"),
        label=_t("Grid size"),
        is_grid=True,
        spin_min=0,
        spin_max=1000,
        spin_special=translate("Grid Size", "Auto"),
        grid_visibility=GridVisibility.AUTO_ONLY,
    ),
    _f(
        settings_key="playlist/grid_fit",
        kind=FieldKind.CHECKBOX,
        section=_t("Grid"),
        label=_t("Fit grid cells"),
        is_grid=True,
        grid_visibility=GridVisibility.AUTO_ONLY,
    ),
    _f(
        settings_key="playlist/grid_rows",
        kind=FieldKind.SPIN,
        section=_t("Grid"),
        label=_t("Rows"),
        is_grid=True,
        spin_min=1,
        spin_max=100,
        grid_visibility=GridVisibility.FIXED_ONLY,
    ),
    _f(
        settings_key="playlist/grid_cols",
        kind=FieldKind.SPIN,
        section=_t("Grid"),
        label=_t("Columns"),
        is_grid=True,
        spin_min=1,
        spin_max=100,
        grid_visibility=GridVisibility.FIXED_ONLY,
    ),
    _f(
        settings_key="playlist/grid_preallocate",
        kind=FieldKind.CHECKBOX,
        section=_t("Grid"),
        label=_t("Show all cells even when empty"),
        is_grid=True,
        grid_visibility=GridVisibility.FIXED_ONLY,
    ),
    _f(
        settings_key="playlist/drop_action_internal",
        playlist_attr="drop_action_internal",
        kind=FieldKind.COMBO,
        section=_t("Drag-n-Drop"),
        label=_t("In-window drag"),
        combo_values=_drop_internal,
    ),
    _f(
        settings_key="playlist/drop_action_external",
        playlist_attr="drop_action_external",
        kind=FieldKind.COMBO,
        section=_t("Drag-n-Drop"),
        label=_t("File drop"),
        combo_values=_drop_external,
    ),
    _f(
        settings_key="playlist/drop_modifier",
        playlist_attr="drop_modifier",
        kind=FieldKind.COMBO,
        section=_t("Drag-n-Drop"),
        label=_t("Hold to switch"),
        combo_values=_drop_modifiers,
        tooltip=_drop_modifier_tooltip(),
    ),
)

VIDEO_FIELDS: tuple[SettingField, ...] = (
    _f(
        settings_key="video_defaults/color",
        video_attr="color",
        kind=FieldKind.COLOR,
        section=_t("Overlay"),
        label=_t("Overlay color"),
    ),
    _f(
        settings_key="video_defaults/audio_mode",
        video_attr="audio_mode",
        kind=FieldKind.COMBO,
        section=_t("Audio"),
        label=_t("Audio mode"),
        combo_values=_audio_modes,
    ),
    _f(
        settings_key="video_defaults/volume",
        video_attr="volume",
        kind=FieldKind.FLOAT_SPIN,
        section=_t("Audio"),
        label=_t("Volume"),
        spin_min=0,
        spin_max=1,
        spin_decimals=2,
        spin_step=0.05,
    ),
    _f(
        settings_key="video_defaults/muted",
        video_attr="muted",
        kind=FieldKind.CHECKBOX,
        section=_t("Audio"),
        label=_t("Muted"),
    ),
    _f(
        settings_key="video_defaults/scale",
        video_attr="scale",
        kind=FieldKind.FLOAT_SPIN,
        section=_t("Video"),
        label=_t("Zoom"),
        spin_min=MIN_SCALE,
        spin_max=MAX_SCALE,
        spin_decimals=1,
        spin_step=0.1,
    ),
    _f(
        settings_key="video_defaults/aspect",
        video_attr="aspect",
        kind=FieldKind.COMBO,
        section=_t("Video"),
        label=_t("Aspect mode"),
        combo_values=_aspects,
    ),
    _f(
        settings_key="video_defaults/crop",
        video_attr="crop",
        kind=FieldKind.CROP,
        section=_t("Video"),
        label=_t("Crop"),
        spin_max=9999,
    ),
    _f(
        settings_key="video_defaults/transform",
        video_attr="transform",
        kind=FieldKind.COMBO,
        section=_t("Video"),
        label=_t("Transform"),
        combo_values=_transforms,
    ),
    _f(
        settings_key="video_defaults/repeat",
        video_attr="repeat",
        kind=FieldKind.COMBO,
        section=_t("Playback"),
        label=_t("Repeat mode"),
        combo_values=_repeat_modes,
    ),
    _f(
        settings_key="video_defaults/random_loop",
        video_attr="random_loop",
        kind=FieldKind.CHECKBOX,
        section=_t("Playback"),
        label=_t("Start at random position"),
    ),
    _f(
        settings_key="video_defaults/paused",
        video_attr="paused",
        kind=FieldKind.CHECKBOX,
        section=_t("Playback"),
        label=_t("Paused"),
    ),
    _f(
        settings_key="video_defaults/rate",
        video_attr="rate",
        kind=FieldKind.FLOAT_SPIN,
        section=_t("Playback"),
        label=_t("Playback speed"),
        spin_min=MIN_RATE,
        spin_max=MAX_RATE,
        spin_decimals=2,
        spin_step=0.1,
    ),
    _f(
        settings_key="video_defaults/stream_quality",
        video_attr="stream_quality",
        kind=FieldKind.COMBO,
        section=_t("Streaming Videos"),
        label=_t("Stream quality"),
        combo_values=_stream_qualities,
    ),
    _f(
        settings_key="video_defaults/auto_reload_timer",
        video_attr="auto_reload_timer",
        kind=FieldKind.SPIN,
        section=_t("Streaming Videos"),
        label=_t("Auto reload time"),
        spin_min=0,
        spin_max=1000,
        spin_special=translate("Auto Reload Timer", "Disabled"),
        spin_suffix=_t("(min)"),
    ),
)

ALL_DEFAULT_FIELDS: tuple[SettingField, ...] = PLAYLIST_FIELDS + VIDEO_FIELDS

GRID_STATE_ATTR = {
    "playlist/grid_mode": "mode",
    "playlist/grid_fit": "is_fit",
    "playlist/grid_size": "size",
    "playlist/grid_rows": "rows",
    "playlist/grid_cols": "cols",
    "playlist/grid_preallocate": "preallocate",
}
