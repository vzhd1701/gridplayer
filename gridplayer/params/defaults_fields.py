from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from PyQt5.QtGui import QFontDatabase

from gridplayer.params import env
from gridplayer.params.static import (
    MAX_RATE,
    MAX_SCALE,
    MIN_RATE,
    MIN_SCALE,
    AudioChannelMode,
    AudioTrackMode,
    DropAction,
    DropModifier,
    GridMode,
    NetworkRetryMode,
    SeekSyncMode,
    SubtitleOutline,
    SubtitleTrackMode,
    UnsavedChangesMode,
    VideoAspect,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.params.subtitle_encodings import SUBTITLE_ENCODINGS
from gridplayer.utils.qt import translate


class FieldKind(Enum):
    CHECKBOX = auto()
    COMBO = auto()
    TEXT = auto()
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
    text_placeholder: str | None = None
    # what a checkbox stands for, where the setting behind it is not a
    # plain bool; ticking it stores one value and clearing it the other
    checked_value: object | None = None
    unchecked_value: object | None = None
    enabled_by: str | None = None
    # what the driving field has to be set to; None means any value that
    # counts as on, which is what a plain checkbox gives, and a tuple
    # means any one of several, which is what a combo with more than one
    # setting worth having gives
    enabled_by_value: object | None = None
    grid_visibility: GridVisibility = GridVisibility.ALWAYS
    tooltip: str | None = None


def _grid_modes() -> dict:
    return {
        GridMode.AUTO_ROWS: translate("Grid Mode", "Auto (Rows First)"),
        GridMode.AUTO_COLS: translate("Grid Mode", "Auto (Columns First)"),
        GridMode.FIXED: translate("Grid Mode", "Fixed Grid"),
    }


def _seek_sync_modes() -> dict:
    return {
        SeekSyncMode.DISABLED: translate("Seek Sync", "Disabled"),
        SeekSyncMode.PERCENT: translate("Seek Sync", "Percent"),
        SeekSyncMode.TIMECODE: translate("Seek Sync", "Timecode"),
    }


def _unsaved_changes_modes() -> dict:
    return {
        UnsavedChangesMode.ASK: translate("SettingsDialog", "Ask"),
        UnsavedChangesMode.DISCARD: translate("SettingsDialog", "Discard Changes"),
        UnsavedChangesMode.AUTO_SAVE_DISCARD: translate(
            "SettingsDialog", "Auto Save or Discard"
        ),
        UnsavedChangesMode.AUTO_SAVE_ASK: translate(
            "SettingsDialog", "Auto Save or Ask"
        ),
    }


def _unsaved_changes_tooltip() -> str:
    return translate(
        "SettingsDialog",
        "Auto save applies only when the playlist has a file location; "
        "otherwise the fallback action is used.",
    )


def _save_paths_relative_tooltip() -> str:
    return translate(
        "SettingsDialog",
        "Store local video paths relative to the playlist file location so the "
        "playlist stays portable when moved together with its videos. URLs and "
        "paths that cannot be made relative (e.g. another drive) are kept as-is.",
    )


def _drop_internal() -> dict:
    return {
        DropAction.INSERT: translate("SettingsDialog", "Move / Swap"),
        DropAction.REPLACE: translate("SettingsDialog", "Replace"),
    }


def _drop_external() -> dict:
    return {
        DropAction.INSERT: translate("SettingsDialog", "Add"),
        DropAction.REPLACE: translate("SettingsDialog", "Replace"),
    }


def _drop_modifiers() -> dict:
    if env.IS_MACOS:
        return {
            DropModifier.SHIFT: translate("SettingsDialog", "Shift"),
            DropModifier.CTRL: translate("SettingsDialog", "Cmd"),
            DropModifier.ALT: translate("SettingsDialog", "Option"),
            DropModifier.NONE: translate("SettingsDialog", "Disabled"),
        }
    return {
        DropModifier.SHIFT: translate("SettingsDialog", "Shift"),
        DropModifier.CTRL: translate("SettingsDialog", "Ctrl"),
        DropModifier.ALT: translate("SettingsDialog", "Alt"),
        DropModifier.NONE: translate("SettingsDialog", "Disabled"),
    }


def _drop_modifier_tooltip() -> str | None:
    if not env.IS_LINUX:
        return None
    return translate(
        "SettingsDialog",
        "On GNOME, dropping files from the file manager only honors Shift. "
        "Ctrl and Alt still work when dragging videos inside the player.",
    )


def _aspects() -> dict:
    return {
        VideoAspect.FIT: translate("Aspect", "Fit"),
        VideoAspect.STRETCH: translate("Aspect", "Stretch"),
        VideoAspect.NONE: translate("Aspect", "None"),
    }


def _transforms() -> dict:
    return {
        VideoTransform.ROTATE_90: translate("Transform", "Rotate 90"),
        VideoTransform.ROTATE_180: translate("Transform", "Rotate 180"),
        VideoTransform.ROTATE_270: translate("Transform", "Rotate 270"),
        VideoTransform.HFLIP: translate("Transform", "Flip Horizontally"),
        VideoTransform.VFLIP: translate("Transform", "Flip Vertically"),
        VideoTransform.TRANSPOSE: translate("Transform", "Transpose"),
        VideoTransform.ANTITRANSPOSE: translate("Transform", "Anti-transpose"),
        VideoTransform.NONE: translate("Transform", "No Transform"),
    }


def _deinterlace_states() -> dict:
    # in the menu's own contexts, so each string is translated once for both
    return {
        VideoDeinterlace.AUTO: translate("Deinterlace", "Automatic"),
        VideoDeinterlace.ON: translate("Deinterlace", "On"),
        VideoDeinterlace.OFF: translate("Deinterlace", "Off"),
    }


def _deinterlace_modes() -> dict:
    return {
        VideoDeinterlaceMode.AUTO: translate("Deinterlace Mode", "Auto"),
        VideoDeinterlaceMode.DISCARD: translate("Deinterlace Mode", "Discard"),
        VideoDeinterlaceMode.BLEND: translate("Deinterlace Mode", "Blend"),
        VideoDeinterlaceMode.MEAN: translate("Deinterlace Mode", "Mean"),
        VideoDeinterlaceMode.BOB: translate("Deinterlace Mode", "Bob"),
        VideoDeinterlaceMode.LINEAR: translate("Deinterlace Mode", "Linear"),
        VideoDeinterlaceMode.X: translate("Deinterlace Mode", "X"),
        VideoDeinterlaceMode.YADIF: translate("Deinterlace Mode", "Yadif"),
        VideoDeinterlaceMode.YADIF2X: translate("Deinterlace Mode", "Yadif (2x)"),
        VideoDeinterlaceMode.PHOSPHOR: translate("Deinterlace Mode", "Phosphor"),
        VideoDeinterlaceMode.IVTC: translate("Deinterlace Mode", "Film NTSC (IVTC)"),
    }


def _end_actions() -> dict:
    return {
        VideoEndAction.LOOP_FILE: translate("When Finished", "Loop this file"),
        VideoEndAction.NEXT_FILE: translate("When Finished", "Next in folder"),
        VideoEndAction.PREVIOUS_FILE: translate("When Finished", "Previous in folder"),
        VideoEndAction.SHUFFLE_FILE: translate("When Finished", "Random in folder"),
        VideoEndAction.PAUSE: translate("When Finished", "Pause at start"),
        VideoEndAction.STOP: translate("When Finished", "Stop"),
        VideoEndAction.CLOSE: translate("When Finished", "Close"),
    }


def _initial_states() -> dict:
    return {
        VideoInitialState.PLAYING: translate("SettingsDialog", "Playing"),
        VideoInitialState.PAUSED: translate("SettingsDialog", "Paused"),
        VideoInitialState.STOPPED: translate("SettingsDialog", "Stopped"),
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


def _subtitle_track_modes() -> dict:
    return {
        SubtitleTrackMode.DISABLED: translate("Subtitle Track", "Off"),
        SubtitleTrackMode.PREFERRED: translate("Subtitle Track", "Preferred Language"),
        SubtitleTrackMode.DEFAULT: translate("Subtitle Track", "Default"),
    }


def _subtitle_encodings() -> dict:
    return {"": translate("Subtitle Encoding", "Default"), **SUBTITLE_ENCODINGS}


def _audio_track_modes() -> dict:
    return {
        AudioTrackMode.DEFAULT: translate("Audio Track", "Default"),
        AudioTrackMode.PREFERRED: translate("Audio Track", "Preferred Language"),
        AudioTrackMode.DISABLED: translate("Audio Track", "Disable Audio"),
    }


def _network_retry_modes() -> dict:
    return {
        NetworkRetryMode.OFF: translate("On Network Error", "Show error"),
        NetworkRetryMode.TIMES: translate("On Network Error", "Reload a few times"),
        NetworkRetryMode.INFINITE: translate("On Network Error", "Keep reloading"),
    }


def _stream_qualities() -> dict:
    named = {
        "auto": translate("Stream Quality", "Auto (fit to pane)"),
        "best": translate("Stream Quality", "Best"),
        "best_audio_only": translate("Stream Quality", "Audio Only"),
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


def _font_families() -> dict:
    """Every font on this machine, with VLC's own pick at the top.

    Default is an empty name rather than a font, so that nothing is
    passed and VLC goes on choosing for itself.
    """

    families = QFontDatabase().families()

    return {
        "": translate("SettingsDialog", "Default"),
        **{family: family for family in families},
    }


def _subtitle_outlines() -> dict:
    return {
        SubtitleOutline.NONE: translate("SettingsDialog", "None"),
        SubtitleOutline.THIN: translate("SettingsDialog", "Thin"),
        SubtitleOutline.NORMAL: translate("SettingsDialog", "Normal"),
        SubtitleOutline.THICK: translate("SettingsDialog", "Thick"),
    }


# the outline colour is worth nothing without an outline to draw
_OUTLINE_DRAWN = (
    SubtitleOutline.THIN,
    SubtitleOutline.NORMAL,
    SubtitleOutline.THICK,
)


def _f(**kwargs) -> SettingField:
    return SettingField(**kwargs)


PLAYLIST_FIELDS: tuple[SettingField, ...] = (
    _f(
        settings_key="playlist/unsaved_changes",
        playlist_attr="unsaved_changes",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Unsaved changes on close"),
        combo_values=_unsaved_changes_modes,
        tooltip=_unsaved_changes_tooltip(),
    ),
    _f(
        settings_key="playlist/save_window",
        playlist_attr="save_window",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save window position and size"),
    ),
    _f(
        settings_key="playlist/save_position",
        playlist_attr="save_position",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save videos playback position"),
    ),
    _f(
        settings_key="playlist/save_state",
        playlist_attr="save_state",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save videos playback status"),
    ),
    _f(
        settings_key="playlist/save_paths_relative",
        playlist_attr="save_paths_relative",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save video paths relative to playlist file"),
        tooltip=_save_paths_relative_tooltip(),
    ),
    _f(
        settings_key="playlist/pause_background_videos",
        playlist_attr="pause_background_videos",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Playback"),
        label=translate("Playlist Settings", "Pause background videos on single mode"),
        menu_action="Pause Background Videos",
    ),
    _f(
        settings_key="playlist/pause_minimized",
        playlist_attr="pause_minimized",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Playback"),
        label=translate("Playlist Settings", "Pause videos when minimized"),
        menu_action="Pause When Minimized",
    ),
    _f(
        settings_key="playlist/seek_sync_mode",
        playlist_attr="seek_sync_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Seek sync mode"),
        combo_values=_seek_sync_modes,
    ),
    _f(
        settings_key="playlist/disable_mouse_click_events",
        playlist_attr="disable_mouse_click_events",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Input"),
        label=translate("Playlist Settings", "Disable mouse click events"),
        menu_action="Disable Mouse Click Events",
    ),
    _f(
        settings_key="playlist/disable_mouse_wheel_events",
        playlist_attr="disable_mouse_wheel_events",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Input"),
        label=translate("Playlist Settings", "Disable mouse wheel events"),
        menu_action="Disable Mouse Wheel Events",
    ),
    _f(
        settings_key="playlist/disable_overlay",
        playlist_attr="disable_overlay",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Overlay"),
        label=translate("Playlist Settings", "Disable overlay"),
        menu_action="Disable Overlay",
    ),
    _f(
        settings_key="playlist/show_overlay_border",
        playlist_attr="show_overlay_border",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Overlay"),
        label=translate("Playlist Settings", "Show overlay border for active video"),
        menu_action="Show Overlay Border",
    ),
    _f(
        settings_key="playlist/overlay_hide_on_timeout",
        playlist_attr="overlay_hide_on_timeout",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Overlay"),
        label=translate("Playlist Settings", "Hide overlay after timeout"),
        menu_action="Hide Overlay After Timeout",
    ),
    _f(
        settings_key="playlist/overlay_timeout",
        playlist_attr="overlay_timeout",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Overlay"),
        label=translate("SettingsDialog", "Overlay timeout"),
        spin_min=1,
        spin_max=60,
        spin_suffix=translate("SettingsDialog", "(sec)"),
        enabled_by="playlist/overlay_hide_on_timeout",
    ),
    _f(
        settings_key="playlist/shuffle_on_load",
        playlist_attr="shuffle_on_load",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Grid"),
        label=translate("Playlist Settings", "Shuffle on load"),
        menu_action="Shuffle Grid On Load",
    ),
    _f(
        settings_key="playlist/grid_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Grid mode"),
        is_grid=True,
        combo_values=_grid_modes,
    ),
    _f(
        settings_key="playlist/grid_size",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Grid size"),
        is_grid=True,
        spin_min=0,
        spin_max=1000,
        spin_special=translate("SettingsDialog", "Auto"),
        grid_visibility=GridVisibility.AUTO_ONLY,
    ),
    _f(
        settings_key="playlist/grid_fit",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Fit grid cells"),
        is_grid=True,
        grid_visibility=GridVisibility.AUTO_ONLY,
    ),
    _f(
        settings_key="playlist/grid_rows",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Rows"),
        is_grid=True,
        spin_min=1,
        spin_max=100,
        grid_visibility=GridVisibility.FIXED_ONLY,
    ),
    _f(
        settings_key="playlist/grid_cols",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Columns"),
        is_grid=True,
        spin_min=1,
        spin_max=100,
        grid_visibility=GridVisibility.FIXED_ONLY,
    ),
    _f(
        settings_key="playlist/grid_preallocate",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Show all cells even when empty"),
        is_grid=True,
        grid_visibility=GridVisibility.FIXED_ONLY,
    ),
    _f(
        settings_key="playlist/drop_action_internal",
        playlist_attr="drop_action_internal",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("SettingsDialog", "In-window drag"),
        combo_values=_drop_internal,
    ),
    _f(
        settings_key="playlist/drop_action_external",
        playlist_attr="drop_action_external",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("SettingsDialog", "File drop"),
        combo_values=_drop_external,
    ),
    _f(
        settings_key="playlist/drop_modifier",
        playlist_attr="drop_modifier",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("SettingsDialog", "Hold to switch"),
        combo_values=_drop_modifiers,
        tooltip=_drop_modifier_tooltip(),
    ),
)

VIDEO_FIELDS: tuple[SettingField, ...] = (
    _f(
        settings_key="video_defaults/color",
        video_attr="color",
        kind=FieldKind.COLOR,
        section=translate("SettingsDialog", "Overlay"),
        label=translate("SettingsDialog", "Overlay color"),
    ),
    _f(
        settings_key="video_defaults/audio_track_mode",
        video_attr="audio_track_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Audio track"),
        combo_values=_audio_track_modes,
        tooltip=translate(
            "SettingsDialog",
            "Which track a video opens on: the one its own file marks as the"
            " default, the one answering the preferred languages below, or"
            " none decoded at all, which is not the same as starting muted.",
        ),
    ),
    _f(
        settings_key="video_defaults/audio_languages",
        video_attr="audio_languages",
        kind=FieldKind.TEXT,
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Preferred languages"),
        text_placeholder=translate("SettingsDialog", "en, ja, fr"),
        enabled_by="video_defaults/audio_track_mode",
        enabled_by_value=AudioTrackMode.PREFERRED,
        tooltip=translate(
            "SettingsDialog",
            "Language codes or names, best first."
            " Videos that offer none of them keep their own default track.",
        ),
    ),
    _f(
        settings_key="video_defaults/external_audio_autodiscover",
        video_attr="external_audio_autodiscover",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Detect external audio files"),
        tooltip=translate(
            "SettingsDialog",
            "Offer audio files named after the video and kept beside it,"
            " so they can be played in place of its own sound."
            " Nothing is opened until one of them is picked.",
        ),
    ),
    _f(
        settings_key="video_defaults/audio_mode",
        video_attr="audio_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Audio mode"),
        combo_values=_audio_modes,
    ),
    _f(
        settings_key="video_defaults/subtitle_track_mode",
        video_attr="subtitle_track_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Subtitles"),
        combo_values=_subtitle_track_modes,
        tooltip=translate(
            "SettingsDialog",
            "Which subtitle a video opens on: none, the one answering the"
            " preferred languages below, or the one its container marks as"
            " the default. Videos are opened with none unless told otherwise.",
        ),
    ),
    _f(
        settings_key="video_defaults/subtitle_languages",
        video_attr="subtitle_languages",
        kind=FieldKind.TEXT,
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Preferred languages"),
        text_placeholder=translate("SettingsDialog", "en, ja, fr"),
        enabled_by="video_defaults/subtitle_track_mode",
        enabled_by_value=SubtitleTrackMode.PREFERRED,
        tooltip=translate(
            "SettingsDialog",
            "Language codes or names, best first."
            " Videos that offer none of them are shown without subtitles.",
        ),
    ),
    _f(
        settings_key="video_defaults/subtitle_encoding",
        video_attr="subtitle_encoding",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Text encoding"),
        combo_values=_subtitle_encodings,
        tooltip=translate(
            "SettingsDialog",
            "What a subtitle file is read as where it is not UTF-8."
            " UTF-8 files are recognised on their own and are left alone by"
            " this; anything else is read as Western European unless another"
            " set is picked here. ASS and SSA subtitles are not affected.",
        ),
    ),
    _f(
        settings_key="video_defaults/external_subtitle_autodiscover",
        video_attr="external_subtitle_autodiscover",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Detect external subtitle files"),
        tooltip=translate(
            "SettingsDialog",
            "Offer subtitle files named after the video and kept beside it,"
            " so they can be shown over it."
            " Nothing is opened until one of them is picked.",
        ),
    ),
    _f(
        settings_key="video_defaults/volume",
        video_attr="volume",
        kind=FieldKind.FLOAT_SPIN,
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Volume"),
        spin_min=0,
        spin_max=1,
        spin_decimals=2,
        spin_step=0.05,
    ),
    _f(
        settings_key="video_defaults/muted",
        video_attr="muted",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Muted"),
    ),
    _f(
        settings_key="video_defaults/scale",
        video_attr="scale",
        kind=FieldKind.FLOAT_SPIN,
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Zoom"),
        spin_min=MIN_SCALE,
        spin_max=MAX_SCALE,
        spin_decimals=1,
        spin_step=0.1,
    ),
    _f(
        settings_key="video_defaults/aspect",
        video_attr="aspect",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Aspect mode"),
        combo_values=_aspects,
    ),
    _f(
        settings_key="video_defaults/crop",
        video_attr="crop",
        kind=FieldKind.CROP,
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Crop"),
        spin_max=9999,
    ),
    _f(
        settings_key="video_defaults/transform",
        video_attr="transform",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Transform"),
        combo_values=_transforms,
    ),
    _f(
        settings_key="video_defaults/deinterlace",
        video_attr="deinterlace",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Deinterlace"),
        combo_values=_deinterlace_states,
        tooltip=translate(
            "SettingsDialog",
            "Automatic deinterlaces only the videos marked as interlaced."
            " Some are marked wrongly and show combing on moving edges;"
            " turn it on for those.",
        ),
    ),
    _f(
        settings_key="video_defaults/deinterlace_mode",
        video_attr="deinterlace_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Deinterlace mode"),
        combo_values=_deinterlace_modes,
        enabled_by="video_defaults/deinterlace",
        enabled_by_value=(VideoDeinterlace.AUTO, VideoDeinterlace.ON),
        tooltip=translate(
            "SettingsDialog",
            "Auto leaves it to VLC, which currently picks X. Yadif (2x), Bob"
            " and Phosphor double the frame rate, which costs more with many"
            " videos playing. With hardware decoding the GPU does the work and"
            " has fewer modes of its own; a mode it lacks falls back to one"
            " it has.",
        ),
    ),
    _f(
        settings_key="video_defaults/end_action",
        video_attr="end_action",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "When finished"),
        combo_values=_end_actions,
    ),
    _f(
        settings_key="video_defaults/random_loop",
        video_attr="random_loop",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Start at random position"),
    ),
    _f(
        settings_key="video_defaults/initial_state",
        video_attr="initial_state",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Initial state"),
        combo_values=_initial_states,
    ),
    _f(
        settings_key="video_defaults/rate",
        video_attr="rate",
        kind=FieldKind.FLOAT_SPIN,
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Playback speed"),
        spin_min=MIN_RATE,
        spin_max=MAX_RATE,
        spin_decimals=2,
        spin_step=0.1,
    ),
    _f(
        settings_key="video_defaults/stream_quality",
        video_attr="stream_quality",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Stream quality"),
        combo_values=_stream_qualities,
    ),
    _f(
        settings_key="video_defaults/quality_adapt_delay",
        video_attr="quality_adapt_delay",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Adapt Auto quality after"),
        spin_min=1,
        spin_max=3600,
        spin_suffix=translate("SettingsDialog", "(sec)"),
        tooltip=translate(
            "SettingsDialog",
            "How long a video has to keep its new size before Auto quality follows it",
        ),
    ),
    _f(
        settings_key="video_defaults/network_retry_mode",
        video_attr="network_retry_mode",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "On network error"),
        combo_values=_network_retry_modes,
    ),
    _f(
        settings_key="video_defaults/network_retry_times",
        video_attr="network_retry_times",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Reload attempts"),
        spin_min=1,
        spin_max=1000,
        enabled_by="video_defaults/network_retry_mode",
        enabled_by_value=NetworkRetryMode.TIMES,
    ),
    _f(
        settings_key="video_defaults/auto_reload_timer",
        video_attr="auto_reload_timer",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Auto reload time"),
        spin_min=0,
        spin_max=1000,
        spin_special=translate("SettingsDialog", "Disabled"),
        spin_suffix=translate("SettingsDialog", "(min)"),
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


SUBTITLE_STYLE_FIELDS: tuple[SettingField, ...] = (
    _f(
        settings_key="subtitles/font",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Font"),
        combo_values=_font_families,
    ),
    _f(
        settings_key="subtitles/size_scale",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Size"),
        spin_min=10,
        spin_max=500,
        spin_suffix="%",
        tooltip=translate(
            "SettingsDialog",
            "Size against the one VLC picks, which already follows the"
            " height of the video, so a small pane gets small subtitles"
            " without this being touched.",
        ),
    ),
    _f(
        settings_key="subtitles/color",
        kind=FieldKind.COLOR,
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Color"),
    ),
    _f(
        settings_key="subtitles/bold",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Bold"),
    ),
    _f(
        settings_key="subtitles/outline",
        kind=FieldKind.COMBO,
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Outline"),
        combo_values=_subtitle_outlines,
        tooltip=translate(
            "SettingsDialog",
            "The rim drawn around every glyph, which is what keeps white"
            " text readable over a light picture.",
        ),
    ),
    _f(
        settings_key="subtitles/outline_color",
        kind=FieldKind.COLOR,
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Outline color"),
        enabled_by="subtitles/outline",
        enabled_by_value=_OUTLINE_DRAWN,
    ),
    _f(
        settings_key="subtitles/shadow",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Shadow"),
    ),
    _f(
        settings_key="subtitles/shadow_color",
        kind=FieldKind.COLOR,
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Shadow color"),
        enabled_by="subtitles/shadow",
    ),
    _f(
        settings_key="subtitles/background",
        kind=FieldKind.CHECKBOX,
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Background box"),
        tooltip=translate(
            "SettingsDialog",
            "Draw the text on a filled box, which is the one thing that"
            " stays readable over any picture at all.",
        ),
    ),
    _f(
        settings_key="subtitles/background_color",
        kind=FieldKind.COLOR,
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Background color"),
        enabled_by="subtitles/background",
    ),
    _f(
        settings_key="subtitles/margin",
        kind=FieldKind.SPIN,
        section=translate("SettingsDialog", "Position"),
        label=translate("SettingsDialog", "Raise from bottom"),
        spin_min=0,
        spin_max=500,
        spin_special=translate("SettingsDialog", "Default"),
        spin_suffix=translate("SettingsDialog", "px"),
        tooltip=translate(
            "SettingsDialog",
            "How far up from the bottom of the picture subtitles are drawn."
            " This is the one setting here that ASS and SSA subtitles follow"
            " as well.",
        ),
    ),
)
