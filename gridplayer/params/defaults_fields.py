from collections.abc import Callable
from dataclasses import dataclass

from PyQt5.QtGui import QFontDatabase

from gridplayer.params import env
from gridplayer.params.static import (
    MANY_CELLS,
    MAX_LIST_FAIL_WAIT_SEC,
    MAX_RATE,
    MAX_SCALE,
    MAX_SEEK_STEP_SECONDS,
    MIN_RATE,
    MIN_SCALE,
    MIN_SEEK_STEP_SECONDS,
    AddMode,
    AudioChannelMode,
    AudioTrackMode,
    DropAction,
    GridMode,
    ListEndAction,
    ListFailAction,
    ListUpdate,
    ListView,
    NetworkRetryMode,
    SeekSyncMode,
    SubtitleOutline,
    SubtitleTrackMode,
    UnsavedChangesMode,
    VideoAnchor,
    VideoAspect,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.params.subtitle_encodings import SUBTITLE_ENCODINGS
from gridplayer.utils.qt import translate


@dataclass(frozen=True)
class When:
    """Met while another field of the same form, named by key, has one of the
    values; by default, while that checkbox is ticked."""

    key: str
    values: tuple = (True,)


@dataclass(frozen=True, kw_only=True)
class SettingField:
    """What every field has; the subclasses say how it is edited."""

    settings_key: str
    section: str
    label: str
    # the name a playlist keeps it under: on the playlist itself for the
    # playlist fields, on its video defaults for the video fields; None when
    # a playlist doesn't keep it there
    attr: str | None = None
    # the name in the playlist's grid state, for the grid fields
    grid_attr: str | None = None
    enabled_when: When | None = None
    # hidden, it is off as well, unless enabled_when already decides that
    shown_when: When | None = None
    tooltip: str | None = None


@dataclass(frozen=True, kw_only=True)
class CheckboxField(SettingField):
    pass


@dataclass(frozen=True, kw_only=True)
class ComboField(SettingField):
    # value -> text, called when the form is built so the texts are translated
    choices: Callable[[], dict]


@dataclass(frozen=True, kw_only=True)
class TextField(SettingField):
    placeholder: str | None = None


@dataclass(frozen=True, kw_only=True)
class _NumberField(SettingField):
    # shown in place of the lowest value, for when that one means something else
    special_text: str | None = None
    suffix: str | None = None


@dataclass(frozen=True, kw_only=True)
class SpinField(_NumberField):
    minimum: int = 0
    maximum: int


@dataclass(frozen=True, kw_only=True)
class FloatSpinField(_NumberField):
    minimum: float = 0
    maximum: float
    decimals: int
    step: float = 0.1


@dataclass(frozen=True, kw_only=True)
class CropField(SettingField):
    pass


@dataclass(frozen=True, kw_only=True)
class ColorField(SettingField):
    pass


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


def _add_modes() -> dict:
    return {
        AddMode.CELL_EACH: translate("Adding", "One per item"),
        AddMode.ONE_CELL: translate("Adding", "One for all"),
        AddMode.CELL_PER_FILE: translate("Adding", "One per video"),
        AddMode.ASK: translate("Adding", "Ask"),
    }


def _list_views() -> dict:
    return {
        ListView.TITLES: translate("SettingsDialog", "Titles"),
        ListView.TITLES_AND_LOCATIONS: translate("SettingsDialog", "Titles and paths"),
        ListView.LOCATIONS: translate("SettingsDialog", "Paths"),
    }


def list_update_txts() -> dict:
    """How often linked lists are read again, as the playlist's setting
    and each list's own choice in its List window say it."""

    return {
        ListUpdate.ON_LOAD: translate("Lists", "On playlist load"),
        ListUpdate.FIVE_MINUTES: translate("Lists", "Every 5 minutes"),
        ListUpdate.FIFTEEN_MINUTES: translate("Lists", "Every 15 minutes"),
        ListUpdate.HOURLY: translate("Lists", "Every hour"),
        ListUpdate.SIX_HOURS: translate("Lists", "Every 6 hours"),
        ListUpdate.DAILY: translate("Lists", "Every day"),
        ListUpdate.MANUAL: translate("Lists", "Manually"),
    }


def _drop_action_tooltip() -> str:
    tooltip = translate(
        "SettingsDialog",
        'Hold the "Hold to switch drop action" key (see Shortcuts) while'
        " dropping to do the other action.",
    )

    if not env.IS_LINUX:
        return tooltip

    gnome_note = translate(
        "SettingsDialog",
        "On GNOME, dropping files from the file manager only honors Shift."
        " Ctrl and Alt still work when dragging videos inside the player.",
    )

    return f"{tooltip}\n\n{gnome_note}"


def _aspects() -> dict:
    return {
        VideoAspect.FIT: translate("Aspect", "Fit"),
        VideoAspect.STRETCH: translate("Aspect", "Stretch"),
        VideoAspect.NONE: translate("Aspect", "None"),
    }


def _anchors() -> dict:
    return {
        VideoAnchor.CENTER: translate("Alignment", "Center"),
        VideoAnchor.TOP: translate("Alignment", "Top"),
        VideoAnchor.BOTTOM: translate("Alignment", "Bottom"),
        VideoAnchor.LEFT: translate("Alignment", "Left"),
        VideoAnchor.RIGHT: translate("Alignment", "Right"),
        VideoAnchor.TOP_LEFT: translate("Alignment", "Top Left"),
        VideoAnchor.TOP_RIGHT: translate("Alignment", "Top Right"),
        VideoAnchor.BOTTOM_LEFT: translate("Alignment", "Bottom Left"),
        VideoAnchor.BOTTOM_RIGHT: translate("Alignment", "Bottom Right"),
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
        VideoEndAction.NEXT_FILE: translate("When Finished", "Play next file"),
        VideoEndAction.PREVIOUS_FILE: translate("When Finished", "Play previous file"),
        VideoEndAction.SHUFFLE_FILE: translate("When Finished", "Play random file"),
        VideoEndAction.PAUSE: translate("When Finished", "Pause at start"),
        VideoEndAction.STOP: translate("When Finished", "Stop"),
        VideoEndAction.CLOSE: translate("When Finished", "Close"),
    }


def _list_end_actions() -> dict:
    return {
        ListEndAction.START_OVER: translate("Lists", "Start over"),
        ListEndAction.PAUSE: translate("Lists", "Pause at start"),
        ListEndAction.STOP: translate("Lists", "Stop"),
        ListEndAction.CLOSE: translate("Lists", "Close"),
    }


def _list_fail_actions() -> dict:
    return {
        ListFailAction.SHOW_ERROR: translate("When Video Fails", "Show error"),
        ListFailAction.PLAY_NEXT: translate("When Video Fails", "Play next"),
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


# the grid options that only mean something in one kind of grid
_GRID_AUTO = (GridMode.AUTO_ROWS, GridMode.AUTO_COLS)
_GRID_FIXED = (GridMode.FIXED,)


# the outline colour is worth nothing without an outline to draw
_OUTLINE_DRAWN = (
    SubtitleOutline.THIN,
    SubtitleOutline.NORMAL,
    SubtitleOutline.THICK,
)


PLAYLIST_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="playlist/unsaved_changes",
        attr="unsaved_changes",
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Unsaved changes on close"),
        choices=_unsaved_changes_modes,
        tooltip=translate(
            "SettingsDialog",
            "Auto save only works for a playlist that's already saved to a file."
            " Otherwise it discards or asks.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/save_window",
        attr="save_window",
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save window position and size"),
    ),
    CheckboxField(
        settings_key="playlist/save_position",
        attr="save_position",
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save videos playback position"),
    ),
    CheckboxField(
        settings_key="playlist/save_state",
        attr="save_state",
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save videos playback status"),
    ),
    CheckboxField(
        settings_key="playlist/save_paths_relative",
        attr="save_paths_relative",
        section=translate("SettingsDialog", "Saving / Restoring"),
        label=translate("SettingsDialog", "Save video paths relative to playlist file"),
        tooltip=translate(
            "SettingsDialog",
            "So you can move the playlist together with its videos. Links and paths"
            " on another drive stay as they are.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/pause_background_videos",
        attr="pause_background_videos",
        section=translate("SettingsDialog", "Playback"),
        label=translate("Playlist Settings", "Pause background videos on single mode"),
    ),
    CheckboxField(
        settings_key="playlist/pause_minimized",
        attr="pause_minimized",
        section=translate("SettingsDialog", "Playback"),
        label=translate("Playlist Settings", "Pause videos when minimized"),
    ),
    CheckboxField(
        settings_key="playlist/bookmarks_shared",
        attr="bookmarks_shared",
        section=translate("SettingsDialog", "Playback"),
        label=translate(
            "Playlist Settings", "Share bookmarks between cells with the same file"
        ),
        tooltip=translate(
            "SettingsDialog",
            "On: cells playing the same file share its bookmarks, and they stay when a"
            " cell closes.\nOff: each cell has its own, removed when the cell closes.",
        ),
    ),
    FloatSpinField(
        settings_key="playlist/seek_step_short",
        attr="seek_step_short",
        section=translate("SettingsDialog", "Step Sizes"),
        label=translate("SettingsDialog", "Short seek"),
        minimum=MIN_SEEK_STEP_SECONDS,
        maximum=MAX_SEEK_STEP_SECONDS,
        decimals=3,
        step=1.0,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    FloatSpinField(
        settings_key="playlist/seek_step_medium",
        attr="seek_step_medium",
        section=translate("SettingsDialog", "Step Sizes"),
        label=translate("SettingsDialog", "Medium seek"),
        minimum=MIN_SEEK_STEP_SECONDS,
        maximum=MAX_SEEK_STEP_SECONDS,
        decimals=3,
        step=1.0,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    FloatSpinField(
        settings_key="playlist/seek_step_long",
        attr="seek_step_long",
        section=translate("SettingsDialog", "Step Sizes"),
        label=translate("SettingsDialog", "Long seek"),
        minimum=MIN_SEEK_STEP_SECONDS,
        maximum=MAX_SEEK_STEP_SECONDS,
        decimals=3,
        step=1.0,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    SpinField(
        settings_key="playlist/zoom_step",
        attr="zoom_step",
        section=translate("SettingsDialog", "Step Sizes"),
        label=translate("SettingsDialog", "Zoom"),
        minimum=1,
        maximum=100,
        suffix="%",
        tooltip=translate(
            "SettingsDialog",
            "How much each zoom in or out step changes the zoom.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/zoom_proportional",
        attr="zoom_proportional",
        section=translate("SettingsDialog", "Step Sizes"),
        label=translate("SettingsDialog", "Proportional zoom"),
        tooltip=translate(
            "SettingsDialog",
            "Each step zooms by the same share of what's on screen, so it feels the same"
            " at 2x and 8x.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/folder_skip_hidden",
        attr="folder_skip_hidden",
        section=translate("SettingsDialog", "Folder Navigation"),
        label=translate("SettingsDialog", "Skip hidden and system files"),
        tooltip=translate(
            "SettingsDialog",
            "Skip hidden files and folders, and system folders like the recycle bin.",
        ),
    ),
    SpinField(
        settings_key="playlist/folder_max_entries",
        attr="folder_max_entries",
        section=translate("SettingsDialog", "Folder Navigation"),
        label=translate("SettingsDialog", "File limit"),
        minimum=0,
        maximum=1000000,
        special_text=translate("SettingsDialog", "No limit"),
        tooltip=translate(
            "SettingsDialog",
            "The most files and folders to scan when subfolders are included.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/shuffle_avoid_open",
        attr="shuffle_avoid_open",
        section=translate("SettingsDialog", "Folder Navigation"),
        label=translate("SettingsDialog", "Skip files open in other cells"),
        tooltip=translate(
            "SettingsDialog",
            "Random play skips files already open in other cells when it can.",
        ),
    ),
    ComboField(
        settings_key="playlist/seek_sync_mode",
        attr="seek_sync_mode",
        section=translate("SettingsDialog", "Sync"),
        label=translate("SettingsDialog", "Seek sync mode"),
        choices=_seek_sync_modes,
    ),
    CheckboxField(
        settings_key="playlist/view_sync",
        attr="view_sync",
        section=translate("SettingsDialog", "Sync"),
        label=translate("Sync", "Sync zoom and position"),
        tooltip=translate(
            "Sync",
            "Zooming or panning one video does the same in the others.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/pause_sync",
        attr="pause_sync",
        section=translate("SettingsDialog", "Sync"),
        label=translate("Sync", "Sync play and pause"),
    ),
    CheckboxField(
        settings_key="playlist/rate_sync",
        attr="rate_sync",
        section=translate("SettingsDialog", "Sync"),
        label=translate("Sync", "Sync speed"),
    ),
    CheckboxField(
        settings_key="playlist/disable_mouse_click_events",
        attr="disable_mouse_click_events",
        section=translate("SettingsDialog", "Input"),
        label=translate("Playlist Settings", "Disable mouse click events"),
    ),
    CheckboxField(
        settings_key="playlist/disable_mouse_wheel_events",
        attr="disable_mouse_wheel_events",
        section=translate("SettingsDialog", "Input"),
        label=translate("Playlist Settings", "Disable mouse wheel events"),
    ),
    CheckboxField(
        settings_key="playlist/disable_overlay",
        attr="disable_overlay",
        section=translate("SettingsDialog", "Overlay"),
        label=translate("Playlist Settings", "Disable overlay"),
    ),
    CheckboxField(
        settings_key="playlist/show_overlay_border",
        attr="show_overlay_border",
        section=translate("SettingsDialog", "Overlay"),
        label=translate("Playlist Settings", "Show overlay border for active video"),
    ),
    CheckboxField(
        settings_key="playlist/overlay_hide_on_timeout",
        attr="overlay_hide_on_timeout",
        section=translate("SettingsDialog", "Overlay"),
        label=translate("Playlist Settings", "Hide overlay after timeout"),
    ),
    SpinField(
        settings_key="playlist/overlay_timeout",
        attr="overlay_timeout",
        section=translate("SettingsDialog", "Overlay"),
        label=translate("SettingsDialog", "Overlay timeout"),
        minimum=1,
        maximum=60,
        suffix=translate("SettingsDialog", "(sec)"),
        enabled_when=When("playlist/overlay_hide_on_timeout"),
    ),
    CheckboxField(
        settings_key="playlist/shuffle_on_load",
        attr="shuffle_on_load",
        section=translate("SettingsDialog", "Grid"),
        label=translate("Playlist Settings", "Shuffle on load"),
    ),
    ComboField(
        settings_key="playlist/grid_mode",
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Grid mode"),
        grid_attr="mode",
        choices=_grid_modes,
    ),
    SpinField(
        settings_key="playlist/grid_size",
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Grid size"),
        grid_attr="size",
        minimum=0,
        maximum=1000,
        special_text=translate("SettingsDialog", "Auto"),
        shown_when=When("playlist/grid_mode", _GRID_AUTO),
    ),
    CheckboxField(
        settings_key="playlist/grid_fit",
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Fit grid cells"),
        grid_attr="is_fit",
        shown_when=When("playlist/grid_mode", _GRID_AUTO),
    ),
    SpinField(
        settings_key="playlist/grid_rows",
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Rows"),
        grid_attr="rows",
        minimum=1,
        maximum=100,
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    SpinField(
        settings_key="playlist/grid_cols",
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Columns"),
        grid_attr="cols",
        minimum=1,
        maximum=100,
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    CheckboxField(
        settings_key="playlist/grid_preallocate",
        section=translate("SettingsDialog", "Grid"),
        label=translate("SettingsDialog", "Show all cells even when empty"),
        grid_attr="preallocate",
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    ComboField(
        settings_key="playlist/drop_action_internal",
        attr="drop_action_internal",
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("SettingsDialog", "In-window drag"),
        choices=_drop_internal,
        tooltip=_drop_action_tooltip(),
    ),
    ComboField(
        settings_key="playlist/drop_action_external",
        attr="drop_action_external",
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("SettingsDialog", "File drop"),
        choices=_drop_external,
        tooltip=_drop_action_tooltip(),
    ),
    ComboField(
        settings_key="playlist/add_mode",
        attr="add_mode",
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("Adding", "Cells"),
        choices=_add_modes,
        tooltip=translate(
            "Adding",
            "How many cells to use for added files, folders and playlists.\n"
            "One per item: each file and folder gets its own cell.\n"
            "One for all: everything in one cell.\n"
            "One per video: every video gets its own cell, even inside folders and"
            " playlists.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/warn_many_cells",
        attr="warn_many_cells",
        section=translate("SettingsDialog", "Drag-n-Drop"),
        label=translate("SettingsDialog", "Warn about too many cells"),
        tooltip=translate(
            "SettingsDialog",
            "Ask before adding more than {COUNT} cells at once. Too many can freeze the"
            " player.",
        ).format(COUNT=MANY_CELLS),
    ),
    ComboField(
        settings_key="playlist/list_view",
        attr="list_view",
        section=translate("SettingsDialog", "Lists"),
        label=translate("SettingsDialog", "List view"),
        choices=_list_views,
        tooltip=translate(
            "SettingsDialog",
            "How items are shown in the List window: titles, titles with paths or links,"
            " or just paths or links.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/list_thumbnails",
        attr="list_thumbnails",
        section=translate("SettingsDialog", "Lists"),
        label=translate("SettingsDialog", "Thumbnails when available"),
        tooltip=translate(
            "SettingsDialog",
            "Show thumbnails, channel, views and upload date for lists from sites like"
            " YouTube.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/list_get_info",
        attr="list_get_info",
        section=translate("SettingsDialog", "Lists"),
        label=translate("SettingsDialog", "Get info automatically"),
        tooltip=translate(
            "SettingsDialog",
            "Look up titles, lengths and thumbnails for files and links you add to a"
            " list. When off, use Get Info in the List window.",
        ),
    ),
    ComboField(
        settings_key="playlist/list_update",
        attr="list_update",
        section=translate("SettingsDialog", "Lists"),
        label=translate("SettingsDialog", "Update linked lists"),
        choices=list_update_txts,
        tooltip=translate(
            "SettingsDialog",
            "How often linked lists update from their source. You can change it for each"
            " list in its List window.",
        ),
    ),
)

VIDEO_FIELDS: tuple[SettingField, ...] = (
    ColorField(
        settings_key="video_defaults/color",
        attr="color",
        section=translate("SettingsDialog", "Overlay"),
        label=translate("SettingsDialog", "Overlay color"),
    ),
    ComboField(
        settings_key="video_defaults/audio_track_mode",
        attr="audio_track_mode",
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Audio track"),
        choices=_audio_track_modes,
        tooltip=translate(
            "SettingsDialog",
            "Which audio track to start with: the file's default, one in your"
            " preferred languages, or none (no audio decoded, which isn't the same as"
            " muted).",
        ),
    ),
    TextField(
        settings_key="video_defaults/audio_languages",
        attr="audio_languages",
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Preferred languages"),
        placeholder=translate("SettingsDialog", "en, ja, fr"),
        enabled_when=When(
            "video_defaults/audio_track_mode", (AudioTrackMode.PREFERRED,)
        ),
        tooltip=translate(
            "SettingsDialog",
            "Language codes or names, best first."
            " Videos that offer none of them keep their own default track.",
        ),
    ),
    CheckboxField(
        settings_key="video_defaults/external_audio_autodiscover",
        attr="external_audio_autodiscover",
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Detect external audio files"),
        tooltip=translate(
            "SettingsDialog",
            "Offer audio files next to the video with the same name. They're opened"
            " only when you pick one.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/audio_mode",
        attr="audio_mode",
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Audio mode"),
        choices=_audio_modes,
    ),
    FloatSpinField(
        settings_key="video_defaults/volume",
        attr="volume",
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Volume"),
        minimum=0,
        maximum=1,
        decimals=2,
        step=0.05,
    ),
    CheckboxField(
        settings_key="video_defaults/muted",
        attr="muted",
        section=translate("SettingsDialog", "Audio"),
        label=translate("SettingsDialog", "Muted"),
    ),
    ComboField(
        settings_key="video_defaults/subtitle_track_mode",
        attr="subtitle_track_mode",
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Subtitles"),
        choices=_subtitle_track_modes,
        tooltip=translate(
            "SettingsDialog",
            "Which subtitles to start with: none, ones in your preferred languages,"
            " or the file's default.",
        ),
    ),
    TextField(
        settings_key="video_defaults/subtitle_languages",
        attr="subtitle_languages",
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Preferred languages"),
        placeholder=translate("SettingsDialog", "en, ja, fr"),
        enabled_when=When(
            "video_defaults/subtitle_track_mode", (SubtitleTrackMode.PREFERRED,)
        ),
        tooltip=translate(
            "SettingsDialog",
            "Language codes or names, best first."
            " Videos that offer none of them are shown without subtitles.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/subtitle_encoding",
        attr="subtitle_encoding",
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Text encoding"),
        choices=_subtitle_encodings,
        tooltip=translate(
            "SettingsDialog",
            "Encoding for subtitle files that aren't UTF-8. UTF-8 is detected"
            " automatically. Doesn't affect ASS and SSA subtitles.",
        ),
    ),
    CheckboxField(
        settings_key="video_defaults/external_subtitle_autodiscover",
        attr="external_subtitle_autodiscover",
        section=translate("SettingsDialog", "Subtitles"),
        label=translate("SettingsDialog", "Detect external subtitle files"),
        tooltip=translate(
            "SettingsDialog",
            "Offer subtitle files next to the video with the same name. They're"
            " opened only when you pick one.",
        ),
    ),
    FloatSpinField(
        settings_key="video_defaults/scale",
        attr="scale",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Zoom"),
        minimum=MIN_SCALE,
        maximum=MAX_SCALE,
        decimals=1,
        step=0.1,
    ),
    CheckboxField(
        settings_key="video_defaults/zoom_to_cursor",
        attr="zoom_to_cursor",
        section=translate("SettingsDialog", "Video"),
        label=translate("Zoom", "Zoom to cursor"),
        tooltip=translate(
            "SettingsDialog",
            "Zoom toward the mouse pointer instead of the alignment point. Resetting"
            " the zoom also recenters the picture.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/aspect",
        attr="aspect",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Aspect mode"),
        choices=_aspects,
    ),
    CropField(
        settings_key="video_defaults/crop",
        attr="crop",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Crop"),
    ),
    ComboField(
        settings_key="video_defaults/anchor",
        attr="anchor",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Alignment"),
        choices=_anchors,
    ),
    CheckboxField(
        settings_key="video_defaults/shift_past_edges",
        attr="shift_past_edges",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Allow moving past the edges"),
    ),
    ComboField(
        settings_key="video_defaults/transform",
        attr="transform",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Transform"),
        choices=_transforms,
    ),
    ComboField(
        settings_key="video_defaults/deinterlace",
        attr="deinterlace",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Deinterlace"),
        choices=_deinterlace_states,
        tooltip=translate(
            "SettingsDialog",
            "Automatic: only videos marked as interlaced.\n"
            "On: always. Use it if you see combing on moving edges.\n"
            "Off: never.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/deinterlace_mode",
        attr="deinterlace_mode",
        section=translate("SettingsDialog", "Video"),
        label=translate("SettingsDialog", "Deinterlace mode"),
        choices=_deinterlace_modes,
        enabled_when=When(
            "video_defaults/deinterlace", (VideoDeinterlace.AUTO, VideoDeinterlace.ON)
        ),
        tooltip=translate(
            "SettingsDialog",
            "Auto: VLC chooses (currently X).\n"
            "Yadif (2x), Bob and Phosphor double the frame rate, which costs more"
            " with many videos.\n"
            "With hardware decoding, the GPU may use another mode it supports.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/end_action",
        attr="end_action",
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "When finished"),
        choices=_end_actions,
    ),
    CheckboxField(
        settings_key="video_defaults/dir_recursive",
        attr="dir_recursive",
        section=translate("SettingsDialog", "Playback"),
        label=translate("Folder Navigation", "Include subfolders"),
        tooltip=translate(
            "Folder Navigation",
            "Next, previous and random files also come from subfolders.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/list_end_action",
        attr="list_end_action",
        section=translate("SettingsDialog", "Playback"),
        label=translate("Lists", "When list ends"),
        choices=_list_end_actions,
        tooltip=translate(
            "Lists",
            "What a cell playing a list does after the last item.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/list_fail_action",
        attr="list_fail_action",
        section=translate("SettingsDialog", "Playback"),
        label=translate("When Video Fails", "When video fails"),
        choices=_list_fail_actions,
        tooltip=translate(
            "When Video Fails",
            "For cells playing a list. Play next doesn't reload a video"
            " that's gone or refused.",
        ),
    ),
    SpinField(
        settings_key="video_defaults/list_fail_wait",
        attr="list_fail_wait",
        section=translate("SettingsDialog", "Playback"),
        label=translate("When Video Fails", "Next after"),
        minimum=0,
        maximum=MAX_LIST_FAIL_WAIT_SEC,
        special_text=translate("When Video Fails", "At once"),
        suffix=translate("SettingsDialog", "(sec)"),
        enabled_when=When(
            "video_defaults/list_fail_action", (ListFailAction.PLAY_NEXT,)
        ),
    ),
    CheckboxField(
        settings_key="video_defaults/random_loop",
        attr="random_loop",
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Start at random position"),
    ),
    ComboField(
        settings_key="video_defaults/initial_state",
        attr="initial_state",
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Initial state"),
        choices=_initial_states,
    ),
    FloatSpinField(
        settings_key="video_defaults/rate",
        attr="rate",
        section=translate("SettingsDialog", "Playback"),
        label=translate("SettingsDialog", "Playback speed"),
        minimum=MIN_RATE,
        maximum=MAX_RATE,
        decimals=2,
        step=0.1,
    ),
    ComboField(
        settings_key="video_defaults/stream_quality",
        attr="stream_quality",
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Stream quality"),
        choices=_stream_qualities,
    ),
    SpinField(
        settings_key="video_defaults/quality_adapt_delay",
        attr="quality_adapt_delay",
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Adapt Auto quality after"),
        minimum=1,
        maximum=3600,
        suffix=translate("SettingsDialog", "(sec)"),
        tooltip=translate(
            "SettingsDialog",
            "How long a video must keep its new size before Auto quality adjusts",
        ),
    ),
    ComboField(
        settings_key="video_defaults/network_retry_mode",
        attr="network_retry_mode",
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "On network error"),
        choices=_network_retry_modes,
    ),
    SpinField(
        settings_key="video_defaults/network_retry_times",
        attr="network_retry_times",
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Reload attempts"),
        minimum=1,
        maximum=1000,
        enabled_when=When(
            "video_defaults/network_retry_mode", (NetworkRetryMode.TIMES,)
        ),
    ),
    SpinField(
        settings_key="video_defaults/auto_reload_timer",
        attr="auto_reload_timer",
        section=translate("SettingsDialog", "Streaming Videos"),
        label=translate("SettingsDialog", "Auto reload time"),
        minimum=0,
        maximum=1000,
        special_text=translate("SettingsDialog", "Disabled"),
        suffix=translate("SettingsDialog", "(min)"),
    ),
)

GRID_STATE_ATTR = {
    spec.settings_key: spec.grid_attr for spec in PLAYLIST_FIELDS if spec.grid_attr
}


SUBTITLE_STYLE_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="subtitles/font",
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Font"),
        choices=_font_families,
    ),
    SpinField(
        settings_key="subtitles/size_scale",
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Size"),
        minimum=10,
        maximum=500,
        suffix="%",
        tooltip=translate(
            "SettingsDialog",
            "Relative to VLC's size, which already scales with the video.",
        ),
    ),
    ColorField(
        settings_key="subtitles/color",
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Color"),
    ),
    CheckboxField(
        settings_key="subtitles/bold",
        section=translate("SettingsDialog", "Text"),
        label=translate("SettingsDialog", "Bold"),
    ),
    ComboField(
        settings_key="subtitles/outline",
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Outline"),
        choices=_subtitle_outlines,
        tooltip=translate(
            "SettingsDialog",
            "Outline around the text. Keeps white text readable on bright pictures.",
        ),
    ),
    ColorField(
        settings_key="subtitles/outline_color",
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Outline color"),
        enabled_when=When("subtitles/outline", _OUTLINE_DRAWN),
    ),
    CheckboxField(
        settings_key="subtitles/shadow",
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Shadow"),
    ),
    ColorField(
        settings_key="subtitles/shadow_color",
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Shadow color"),
        enabled_when=When("subtitles/shadow"),
    ),
    CheckboxField(
        settings_key="subtitles/background",
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Background box"),
        tooltip=translate(
            "SettingsDialog",
            "Draw text on a solid box, readable over any picture.",
        ),
    ),
    ColorField(
        settings_key="subtitles/background_color",
        section=translate("SettingsDialog", "Effects"),
        label=translate("SettingsDialog", "Background color"),
        enabled_when=When("subtitles/background"),
    ),
    SpinField(
        settings_key="subtitles/margin",
        section=translate("SettingsDialog", "Position"),
        label=translate("SettingsDialog", "Raise from bottom"),
        minimum=0,
        maximum=500,
        special_text=translate("SettingsDialog", "Default"),
        suffix=translate("SettingsDialog", "px"),
        tooltip=translate(
            "SettingsDialog",
            "Distance from the bottom of the picture. Also applies to ASS and SSA"
            " subtitles.",
        ),
    ),
)
