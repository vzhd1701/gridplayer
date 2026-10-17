from gridplayer.params import env
from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    FloatSpinField,
    SettingField,
    SpinField,
    When,
)
from gridplayer.params.static import (
    MANY_CELLS,
    MAX_SEEK_STEP_SECONDS,
    MIN_SEEK_STEP_SECONDS,
    GridMode,
)
from gridplayer.utils.qt import translate

# the grid options that only mean something in one kind of grid
_GRID_AUTO = (GridMode.AUTO_ROWS, GridMode.AUTO_COLS)
_GRID_FIXED = (GridMode.FIXED,)


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


PLAYLIST_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="playlist/unsaved_changes",
        label=translate("SettingsDialog", "Unsaved changes on close"),
        choices=choices.unsaved_changes_modes,
        tooltip=translate(
            "SettingsDialog",
            "Auto save only works for a playlist that's already saved to a file."
            " Otherwise it discards or asks.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/save_window",
        label=translate("SettingsDialog", "Save window position and size"),
    ),
    CheckboxField(
        settings_key="playlist/save_position",
        label=translate("SettingsDialog", "Save videos playback position"),
    ),
    CheckboxField(
        settings_key="playlist/save_state",
        label=translate("SettingsDialog", "Save videos playback status"),
    ),
    CheckboxField(
        settings_key="playlist/save_paths_relative",
        label=translate("SettingsDialog", "Save video paths relative to playlist file"),
        tooltip=translate(
            "SettingsDialog",
            "So you can move the playlist together with its videos. Links and paths"
            " on another drive stay as they are.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/pause_background_videos",
        label=translate("Playlist Settings", "Pause background videos on single mode"),
    ),
    CheckboxField(
        settings_key="playlist/pause_minimized",
        label=translate("Playlist Settings", "Pause videos when minimized"),
    ),
    CheckboxField(
        settings_key="playlist/bookmarks_shared",
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
        label=translate("SettingsDialog", "Short seek"),
        minimum=MIN_SEEK_STEP_SECONDS,
        maximum=MAX_SEEK_STEP_SECONDS,
        decimals=3,
        step=1.0,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    FloatSpinField(
        settings_key="playlist/seek_step_medium",
        label=translate("SettingsDialog", "Medium seek"),
        minimum=MIN_SEEK_STEP_SECONDS,
        maximum=MAX_SEEK_STEP_SECONDS,
        decimals=3,
        step=1.0,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    FloatSpinField(
        settings_key="playlist/seek_step_long",
        label=translate("SettingsDialog", "Long seek"),
        minimum=MIN_SEEK_STEP_SECONDS,
        maximum=MAX_SEEK_STEP_SECONDS,
        decimals=3,
        step=1.0,
        suffix=translate("SettingsDialog", "(sec)"),
    ),
    SpinField(
        settings_key="playlist/zoom_step",
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
        label=translate("SettingsDialog", "Proportional zoom"),
        tooltip=translate(
            "SettingsDialog",
            "Each step zooms by the same share of what's on screen, so it feels the same"
            " at 2x and 8x.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/folder_skip_hidden",
        label=translate("SettingsDialog", "Skip hidden and system files"),
        tooltip=translate(
            "SettingsDialog",
            "Skip hidden files and folders, and system folders like the recycle bin.",
        ),
    ),
    SpinField(
        settings_key="playlist/folder_max_entries",
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
        label=translate("SettingsDialog", "Skip files open in other cells"),
        tooltip=translate(
            "SettingsDialog",
            "Random play skips files already open in other cells when it can.",
        ),
    ),
    ComboField(
        settings_key="playlist/seek_sync_mode",
        label=translate("SettingsDialog", "Seek sync mode"),
        choices=choices.seek_sync_modes,
        buttons=True,
    ),
    CheckboxField(
        settings_key="playlist/view_sync",
        label=translate("Sync", "Sync zoom and position"),
        tooltip=translate(
            "Sync",
            "Zooming or panning one video does the same in the others.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/pause_sync",
        label=translate("Sync", "Sync play and pause"),
    ),
    CheckboxField(
        settings_key="playlist/rate_sync",
        label=translate("Sync", "Sync speed"),
    ),
    CheckboxField(
        settings_key="playlist/disable_mouse_click_events",
        label=translate("Playlist Settings", "Disable mouse click events"),
    ),
    CheckboxField(
        settings_key="playlist/disable_mouse_wheel_events",
        label=translate("Playlist Settings", "Disable mouse wheel events"),
    ),
    CheckboxField(
        settings_key="playlist/disable_overlay",
        label=translate("Playlist Settings", "Disable overlay"),
    ),
    CheckboxField(
        settings_key="playlist/show_overlay_border",
        label=translate("Playlist Settings", "Show overlay border for active video"),
    ),
    CheckboxField(
        settings_key="playlist/overlay_hide_on_timeout",
        label=translate("Playlist Settings", "Hide overlay after timeout"),
    ),
    SpinField(
        settings_key="playlist/overlay_timeout",
        label=translate("SettingsDialog", "Overlay timeout"),
        minimum=1,
        maximum=60,
        suffix=translate("SettingsDialog", "(sec)"),
        enabled_when=When("playlist/overlay_hide_on_timeout"),
    ),
    CheckboxField(
        settings_key="playlist/shuffle_on_load",
        label=translate("Playlist Settings", "Shuffle on load"),
    ),
    ComboField(
        settings_key="playlist/grid_mode",
        label=translate("SettingsDialog", "Grid mode"),
        choices=choices.grid_modes,
    ),
    SpinField(
        settings_key="playlist/grid_size",
        label=translate("SettingsDialog", "Grid size"),
        minimum=0,
        maximum=1000,
        special_text=translate("SettingsDialog", "Auto"),
        shown_when=When("playlist/grid_mode", _GRID_AUTO),
    ),
    CheckboxField(
        settings_key="playlist/grid_fit",
        label=translate("SettingsDialog", "Fit grid cells"),
        shown_when=When("playlist/grid_mode", _GRID_AUTO),
    ),
    SpinField(
        settings_key="playlist/grid_rows",
        label=translate("SettingsDialog", "Rows"),
        minimum=1,
        maximum=100,
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    SpinField(
        settings_key="playlist/grid_cols",
        label=translate("SettingsDialog", "Columns"),
        minimum=1,
        maximum=100,
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    CheckboxField(
        settings_key="playlist/grid_preallocate",
        label=translate("SettingsDialog", "Show all cells even when empty"),
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    ComboField(
        settings_key="playlist/drop_action_internal",
        label=translate("SettingsDialog", "In-window drag"),
        choices=choices.drop_internal,
        buttons=True,
        tooltip=_drop_action_tooltip(),
    ),
    ComboField(
        settings_key="playlist/drop_action_external",
        label=translate("SettingsDialog", "File drop"),
        choices=choices.drop_external,
        buttons=True,
        tooltip=_drop_action_tooltip(),
    ),
    ComboField(
        settings_key="playlist/add_mode",
        label=translate("Adding", "Cells"),
        choices=choices.add_modes,
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
        label=translate("SettingsDialog", "Warn about too many cells"),
        tooltip=translate(
            "SettingsDialog",
            "Ask before adding more than {COUNT} cells at once. Too many can freeze the"
            " player.",
        ).format(COUNT=MANY_CELLS),
    ),
    ComboField(
        settings_key="playlist/list_view",
        label=translate("SettingsDialog", "List view"),
        choices=choices.list_views,
        tooltip=translate(
            "SettingsDialog",
            "How items are shown in the List window: titles, titles with paths or links,"
            " or just paths or links.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/list_thumbnails",
        label=translate("SettingsDialog", "Thumbnails when available"),
        tooltip=translate(
            "SettingsDialog",
            "Show thumbnails, channel, views and upload date for lists from sites like"
            " YouTube.",
        ),
    ),
    CheckboxField(
        settings_key="playlist/list_get_info",
        label=translate("SettingsDialog", "Get info automatically"),
        tooltip=translate(
            "SettingsDialog",
            "Look up titles, lengths and thumbnails for files and links you add to a"
            " list. When off, use Get Info in the List window.",
        ),
    ),
    ComboField(
        settings_key="playlist/list_update",
        label=translate("SettingsDialog", "Update linked lists"),
        choices=choices.list_update_txts,
        tooltip=translate(
            "SettingsDialog",
            "How often linked lists update from their source. You can change it for each"
            " list in its List window.",
        ),
    ),
)
