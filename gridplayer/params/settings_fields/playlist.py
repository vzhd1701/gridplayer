from gridplayer.models.tile_snaps import TileSnaps
from gridplayer.params import env
from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    FlagsField,
    FloatSpinField,
    SettingField,
    SpinField,
    When,
)
from gridplayer.params.static import (
    MANY_CELLS,
    MAX_FIXED_SIZE,
    MAX_SEEK_STEP_SECONDS,
    MIN_SEEK_STEP_SECONDS,
    GridMode,
    StripMode,
)
from gridplayer.utils.qt import translate

# the grid options that only mean something in one kind of grid: the
# Auto modes that lay the videos out in lines of one length, and Fixed Grid
_GRID_LINES = (GridMode.AUTO_ROWS, GridMode.AUTO_COLS)
_GRID_SHAPES = (GridMode.AUTO_SHAPES,)
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
    CheckboxField(
        settings_key="playlist/save_all_settings",
        label=translate("SettingsDialog", "Save all settings in the playlist"),
        tooltip=translate(
            "SettingsDialog",
            "Saves every setting, so the playlist plays the same anywhere.",
        ),
    ),
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
    ComboField(
        settings_key="playlist/single_mode_strip",
        label=translate("Playlist Settings", "Strip mode"),
        choices=choices.strip_modes,
        buttons=True,
        tooltip=translate(
            "Playlist Settings",
            "The other videos play in a strip beside the big one."
            " In Strip, the one you pick trades places with the big one."
            " In Fixed Strip, every video keeps its place.",
        ),
    ),
    ComboField(
        settings_key="playlist/single_mode_strip_side",
        label=translate("Playlist Settings", "Strip side"),
        choices=choices.strip_sides,
        enabled_when=When(
            "playlist/single_mode_strip", (StripMode.SWAP, StripMode.FIXED)
        ),
        tooltip=translate(
            "Playlist Settings",
            "Auto puts it on the right of a wide window"
            " and along the bottom of a tall one.",
        ),
    ),
    ComboField(
        settings_key="playlist/single_mode_crop",
        label=translate("Playlist Settings", "Allow cropping when big"),
        choices=choices.single_mode_crops,
        buttons=True,
        tooltip=translate(
            "Playlist Settings",
            "How much a Fill video may be cut to fill the window."
            " If it needs more, it is shown whole.",
        ),
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
        settings_key="playlist/show_grid_lines",
        label=translate("Playlist Settings", "Show grid lines on hover"),
        tooltip=translate(
            "SettingsDialog", "Show the line between two videos under the pointer."
        ),
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
        label=translate("Grid Size", "Videos per row or column"),
        minimum=0,
        maximum=1000,
        special_text=translate("SettingsDialog", "Auto"),
        shown_when=When("playlist/grid_mode", _GRID_LINES),
    ),
    CheckboxField(
        settings_key="playlist/grid_fit",
        label=translate("Fill Gaps", "Fill gaps"),
        shown_when=When("playlist/grid_mode", _GRID_LINES),
    ),
    CheckboxField(
        settings_key="playlist/grid_match_shapes",
        label=translate("Match Shapes", "Match video shapes"),
        tooltip=translate(
            "Match Shapes",
            "Pick the number of columns that shows the videos biggest.",
        ),
        shown_when=When("playlist/grid_mode", _GRID_LINES),
        enabled_when=When("playlist/grid_size", (0,)),
    ),
    ComboField(
        settings_key="playlist/grid_crop",
        label=translate("Allow Cropping", "Allow cropping"),
        choices=choices.grid_crops,
        tooltip=translate(
            "Allow Cropping",
            "Cut up to this much off each video to fill the window.",
        ),
        buttons=True,
        shown_when=When("playlist/grid_mode", _GRID_SHAPES),
    ),
    CheckboxField(
        settings_key="playlist/grid_reorder",
        label=translate("Reorder to Fit", "Reorder videos to fit"),
        tooltip=translate(
            "Reorder to Fit",
            "Put videos of like shape together, so they show bigger.",
        ),
        shown_when=When("playlist/grid_mode", _GRID_SHAPES),
    ),
    SpinField(
        settings_key="playlist/grid_rows",
        label=translate("SettingsDialog", "Rows"),
        minimum=1,
        maximum=MAX_FIXED_SIZE,
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    SpinField(
        settings_key="playlist/grid_cols",
        label=translate("SettingsDialog", "Columns"),
        minimum=1,
        maximum=MAX_FIXED_SIZE,
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    CheckboxField(
        settings_key="playlist/grid_preallocate",
        label=translate("SettingsDialog", "Show all cells even when empty"),
        shown_when=When("playlist/grid_mode", _GRID_FIXED),
    ),
    CheckboxField(
        settings_key="playlist/grid_link",
        label=translate("Link Rows", "Link rows or columns"),
        tooltip=translate(
            "Link Rows",
            "Off, the lines in each row (or column) move on their own.",
        ),
        shown_when=When("playlist/grid_mode", _GRID_LINES),
    ),
    CheckboxField(
        settings_key="playlist/grid_line_snap",
        label=translate("Snap Lines", "Snap lines"),
        tooltip=translate(
            "SettingsDialog",
            "A dragged line stops where a video fits or the cells are even.",
        ),
    ),
    FlagsField(
        settings_key="playlist/tile_snaps",
        label=translate("Snap To", "Snap to"),
        choices=choices.tile_snaps,
        value_type=TileSnaps,
        shown_when=When("playlist/grid_mode", (GridMode.FREE,)),
        enabled_when=When("playlist/grid_line_snap"),
    ),
    ComboField(
        settings_key="playlist/tile_overlap",
        label=translate("Tile Overlap", "Tile overlap"),
        choices=choices.tile_overlap,
        buttons=True,
        shown_when=When("playlist/grid_mode", (GridMode.FREE,)),
        tooltip=translate(
            "Tile Overlap",
            "Whether a tile you move or size can go over the others, or"
            " pushes them aside.",
        ),
    ),
    ComboField(
        settings_key="playlist/tile_resize",
        label=translate("On Window Resize", "On window resize"),
        choices=choices.tile_resize,
        buttons=True,
        shown_when=When("playlist/grid_mode", (GridMode.FREE,)),
        tooltip=translate(
            "On Window Resize",
            "Scale to Fit: the tiles fill the window. Keep Tile Sizes: the"
            " empty space changes first, and tiles shrink only when they"
            " don't fit.",
        ),
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
