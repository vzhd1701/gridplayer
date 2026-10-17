"""Setting keys and their playlist storage attributes, without presentation metadata."""

from types import MappingProxyType

PLAYLIST_ATTRS: MappingProxyType[str, str] = MappingProxyType(
    {
        "playlist/unsaved_changes": "unsaved_changes",
        "playlist/save_window": "save_window",
        "playlist/save_position": "save_position",
        "playlist/save_state": "save_state",
        "playlist/save_paths_relative": "save_paths_relative",
        "playlist/save_all_settings": "save_all_settings",
        "playlist/pause_background_videos": "pause_background_videos",
        "playlist/pause_minimized": "pause_minimized",
        "playlist/bookmarks_shared": "bookmarks_shared",
        "playlist/seek_step_short": "seek_step_short",
        "playlist/seek_step_medium": "seek_step_medium",
        "playlist/seek_step_long": "seek_step_long",
        "playlist/zoom_step": "zoom_step",
        "playlist/zoom_proportional": "zoom_proportional",
        "playlist/folder_skip_hidden": "folder_skip_hidden",
        "playlist/folder_max_entries": "folder_max_entries",
        "playlist/shuffle_avoid_open": "shuffle_avoid_open",
        "playlist/seek_sync_mode": "seek_sync_mode",
        "playlist/view_sync": "view_sync",
        "playlist/pause_sync": "pause_sync",
        "playlist/rate_sync": "rate_sync",
        "playlist/disable_mouse_click_events": "disable_mouse_click_events",
        "playlist/disable_mouse_wheel_events": "disable_mouse_wheel_events",
        "playlist/disable_overlay": "disable_overlay",
        "playlist/show_overlay_border": "show_overlay_border",
        "playlist/overlay_hide_on_timeout": "overlay_hide_on_timeout",
        "playlist/overlay_timeout": "overlay_timeout",
        "playlist/shuffle_on_load": "shuffle_on_load",
        "playlist/drop_action_internal": "drop_action_internal",
        "playlist/drop_action_external": "drop_action_external",
        "playlist/add_mode": "add_mode",
        "playlist/warn_many_cells": "warn_many_cells",
        "playlist/list_view": "list_view",
        "playlist/list_thumbnails": "list_thumbnails",
        "playlist/list_get_info": "list_get_info",
        "playlist/list_update": "list_update",
    }
)

VIDEO_DEFAULT_ATTRS: MappingProxyType[str, str] = MappingProxyType(
    {
        "video_defaults/color": "color",
        "video_defaults/audio_track_mode": "audio_track_mode",
        "video_defaults/audio_languages": "audio_languages",
        "video_defaults/external_audio_autodiscover": "external_audio_autodiscover",
        "video_defaults/audio_mode": "audio_mode",
        "video_defaults/volume": "volume",
        "video_defaults/muted": "muted",
        "video_defaults/subtitle_track_mode": "subtitle_track_mode",
        "video_defaults/subtitle_languages": "subtitle_languages",
        "video_defaults/subtitle_encoding": "subtitle_encoding",
        "video_defaults/external_subtitle_autodiscover": "external_subtitle_autodiscover",
        "video_defaults/scale": "scale",
        "video_defaults/zoom_to_cursor": "zoom_to_cursor",
        "video_defaults/aspect": "aspect",
        "video_defaults/crop": "crop",
        "video_defaults/anchor": "anchor",
        "video_defaults/shift_past_edges": "shift_past_edges",
        "video_defaults/transform": "transform",
        "video_defaults/deinterlace": "deinterlace",
        "video_defaults/deinterlace_mode": "deinterlace_mode",
        "video_defaults/end_action": "end_action",
        "video_defaults/dir_recursive": "dir_recursive",
        "video_defaults/list_end_action": "list_end_action",
        "video_defaults/list_fail_action": "list_fail_action",
        "video_defaults/list_fail_wait": "list_fail_wait",
        "video_defaults/random_loop": "random_loop",
        "video_defaults/initial_state": "initial_state",
        "video_defaults/rate": "rate",
        "video_defaults/stream_quality": "stream_quality",
        "video_defaults/quality_adapt_delay": "quality_adapt_delay",
        "video_defaults/network_retry_mode": "network_retry_mode",
        "video_defaults/network_retry_times": "network_retry_times",
        "video_defaults/auto_reload_timer": "auto_reload_timer",
    }
)

GRID_STATE_ATTR: MappingProxyType[str, str] = MappingProxyType(
    {
        "playlist/grid_mode": "mode",
        "playlist/grid_size": "size",
        "playlist/grid_fit": "is_fit",
        "playlist/grid_rows": "rows",
        "playlist/grid_cols": "cols",
        "playlist/grid_preallocate": "preallocate",
    }
)

# the field of a video each video default fills; the track modes fill the
# pick of a track, by what the mode makes of it (models.video)
VIDEO_PARAM_ATTRS: MappingProxyType[str, str] = MappingProxyType(
    {
        "video_defaults/color": "color",
        "video_defaults/audio_track_mode": "audio_selection",
        "video_defaults/audio_languages": "audio_languages",
        "video_defaults/external_audio_autodiscover": "is_external_audio_autodiscover",
        "video_defaults/audio_mode": "audio_channel_mode",
        "video_defaults/volume": "volume",
        "video_defaults/muted": "is_muted",
        "video_defaults/subtitle_track_mode": "subtitle_selection",
        "video_defaults/subtitle_languages": "subtitle_languages",
        "video_defaults/subtitle_encoding": "subtitle_encoding",
        "video_defaults/external_subtitle_autodiscover": (
            "is_external_subtitle_autodiscover"
        ),
        "video_defaults/scale": "scale",
        "video_defaults/zoom_to_cursor": "is_zoom_to_cursor",
        "video_defaults/aspect": "aspect_mode",
        "video_defaults/crop": "crop",
        "video_defaults/anchor": "anchor",
        "video_defaults/shift_past_edges": "is_shift_past_edges",
        "video_defaults/transform": "transform",
        "video_defaults/deinterlace": "deinterlace",
        "video_defaults/deinterlace_mode": "deinterlace_mode",
        "video_defaults/end_action": "end_action",
        "video_defaults/dir_recursive": "is_dir_recursive",
        "video_defaults/list_end_action": "list_end_action",
        "video_defaults/list_fail_action": "list_fail_action",
        "video_defaults/list_fail_wait": "list_fail_wait_sec",
        "video_defaults/random_loop": "is_start_random",
        "video_defaults/initial_state": "playback_state",
        "video_defaults/rate": "rate",
        "video_defaults/stream_quality": "stream_quality",
        "video_defaults/quality_adapt_delay": "quality_adapt_delay_sec",
        "video_defaults/network_retry_mode": "network_retry_mode",
        "video_defaults/network_retry_times": "network_retry_times",
        "video_defaults/auto_reload_timer": "auto_reload_timer_min",
    }
)
