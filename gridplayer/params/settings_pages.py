"""Where each setting is shown: the settings index and every page in it.

A setting is named here by its key and defined in gridplayer.params.settings_fields,
the way a menu names its actions in gridplayer.params.menu. A Slot is a place the
dialog fills itself, for what isn't a setting.

The Playlist and Video pages are the Playlist Settings dialog's two tabs too.
"""

from gridplayer.params import env
from gridplayer.params.settings_fields.kinds import (
    Group,
    Indented,
    Note,
    Page,
    Row,
    Section,
    Slot,
)
from gridplayer.params.sponsorblock import CATEGORY_COLORS, category_setting
from gridplayer.utils.qt import translate

SPONSORBLOCK_URL = "https://sponsor.ajay.app/"

PLAYLIST_PAGE = (
    Section(
        translate("SettingsDialog", "Saving / Restoring"),
        "playlist/unsaved_changes",
        "playlist/save_window",
        "playlist/save_position",
        "playlist/save_state",
        "playlist/save_paths_relative",
    ),
    Section(
        translate("SettingsDialog", "Playback"),
        "playlist/pause_background_videos",
        "playlist/pause_minimized",
        "playlist/bookmarks_shared",
    ),
    Section(
        translate("SettingsDialog", "Step Sizes"),
        "playlist/seek_step_short",
        "playlist/seek_step_medium",
        "playlist/seek_step_long",
        "playlist/zoom_step",
        "playlist/zoom_proportional",
    ),
    Section(
        translate("SettingsDialog", "Folder Navigation"),
        "playlist/folder_skip_hidden",
        "playlist/folder_max_entries",
        "playlist/shuffle_avoid_open",
    ),
    Section(
        translate("SettingsDialog", "Sync"),
        "playlist/seek_sync_mode",
        "playlist/view_sync",
        "playlist/pause_sync",
        "playlist/rate_sync",
    ),
    Section(
        translate("SettingsDialog", "Input"),
        "playlist/disable_mouse_click_events",
        "playlist/disable_mouse_wheel_events",
    ),
    Section(
        translate("SettingsDialog", "Overlay"),
        "playlist/disable_overlay",
        "playlist/show_overlay_border",
        "playlist/overlay_hide_on_timeout",
        "playlist/overlay_timeout",
    ),
    Section(
        translate("SettingsDialog", "Grid"),
        "playlist/shuffle_on_load",
        "playlist/grid_mode",
        "playlist/grid_size",
        "playlist/grid_fit",
        "playlist/grid_rows",
        "playlist/grid_cols",
        "playlist/grid_preallocate",
    ),
    Section(
        translate("SettingsDialog", "Drag-n-Drop"),
        "playlist/drop_action_internal",
        "playlist/drop_action_external",
        "playlist/add_mode",
        "playlist/warn_many_cells",
    ),
    Section(
        translate("SettingsDialog", "Lists"),
        "playlist/list_view",
        "playlist/list_thumbnails",
        "playlist/list_get_info",
        "playlist/list_update",
    ),
)

VIDEO_PAGE = (
    Section(
        translate("SettingsDialog", "Overlay"),
        "video_defaults/color",
    ),
    Section(
        translate("SettingsDialog", "Audio"),
        "video_defaults/audio_track_mode",
        "video_defaults/audio_languages",
        "video_defaults/external_audio_autodiscover",
        "video_defaults/audio_mode",
        "video_defaults/volume",
        "video_defaults/muted",
    ),
    Section(
        translate("SettingsDialog", "Subtitles"),
        "video_defaults/subtitle_track_mode",
        "video_defaults/subtitle_languages",
        "video_defaults/subtitle_encoding",
        "video_defaults/external_subtitle_autodiscover",
    ),
    Section(
        translate("SettingsDialog", "Video"),
        "video_defaults/scale",
        "video_defaults/zoom_to_cursor",
        "video_defaults/aspect",
        "video_defaults/crop",
        "video_defaults/anchor",
        "video_defaults/shift_past_edges",
        "video_defaults/transform",
        "video_defaults/deinterlace",
        "video_defaults/deinterlace_mode",
    ),
    Section(
        translate("SettingsDialog", "Playback"),
        "video_defaults/end_action",
        "video_defaults/dir_recursive",
        "video_defaults/list_end_action",
        "video_defaults/list_fail_action",
        "video_defaults/list_fail_wait",
        "video_defaults/random_loop",
        "video_defaults/initial_state",
        "video_defaults/rate",
    ),
    Section(
        translate("SettingsDialog", "Streaming Videos"),
        "video_defaults/stream_quality",
        "video_defaults/quality_adapt_delay",
        "video_defaults/network_retry_mode",
        "video_defaults/network_retry_times",
        "video_defaults/auto_reload_timer",
    ),
)

SUBTITLE_STYLE_PAGE = (
    Section(
        translate("SettingsDialog", "Text"),
        "subtitles/font",
        "subtitles/size_scale",
        "subtitles/color",
        "subtitles/bold",
    ),
    Section(
        translate("SettingsDialog", "Effects"),
        "subtitles/outline",
        "subtitles/outline_color",
        "subtitles/shadow",
        "subtitles/shadow_color",
        "subtitles/background",
        "subtitles/background_color",
    ),
    Section(
        translate("SettingsDialog", "Position"),
        "subtitles/margin",
    ),
)

PAGES = (
    Group(
        translate("SettingsDialog", "General"),
        Page(
            "player",
            translate("SettingsDialog", "Player"),
            "player/color_scheme",
            "player/one_instance",
            "player/stay_on_top",
            "player/start_maximized",
            "player/start_fullscreen",
            "player/inhibit_screensaver",
            "player/media_keys_background",
            Section(
                (
                    translate("SettingsDialog", "Menu bar")
                    if env.IS_MACOS
                    else translate("SettingsDialog", "Tray")
                ),
                "player/tray_icon",
                Indented(
                    "player/minimize_to_tray",
                    "player/close_to_tray",
                    "player/hide_taskbar",
                    "player/tray_stop_video",
                ),
                Slot("tray_unavailable"),
            ),
            Section(
                translate("SettingsDialog", "History"),
                Row("player/recent_list_enabled", "player/recent_list_max_size"),
                "player/reopen_last_playlist",
            ),
            Section(
                translate("SettingsDialog", "Timeouts"),
                "player/video_init_timeout",
                Row("misc/mouse_hide", "misc/mouse_hide_timeout"),
            ),
            Section(
                translate("SettingsDialog", "Memory"),
                "player/list_max_mb",
            ),
            Section(
                translate("SettingsDialog", "Cache"),
                "cache/mode",
                "cache/max_mb",
                Slot("cache_clear"),
            ),
            Section(
                translate("SettingsDialog", "Screenshots"),
                "screenshots/dir",
                Row("screenshots/filename_template", Slot("screenshot_template_help")),
                Row("screenshots/format", "screenshots/jpg_quality"),
            ),
        ),
        Page(
            "subtitle_style",
            translate("SettingsDialog", "Subtitle Style"),
            *SUBTITLE_STYLE_PAGE,
            note=translate(
                "SettingsDialog",
                "Applies to text subtitles. ASS and SSA subtitles keep their own"
                " style, except the position.",
            ),
        ),
        Page(
            "shortcuts",
            translate("SettingsDialog", "Shortcuts"),
            "player/keymap",
            scroll=False,
        ),
        Page(
            "language",
            translate("SettingsDialog", "Language"),
            "player/language",
            Note(
                translate(
                    "SettingsDialog",
                    '<p>If you have a handful of free time and a desire to support this project, please <a href="https://crowdin.com/project/gridplayer">help with the translation</a>. No coding skills or special software is required!</p><p><a href="https://github.com/vzhd1701/gridplayer#translations">Full list of translators</a></p>',
                )
            ),
            scroll=False,
        ),
    ),
    Group(
        translate("SettingsDialog", "Defaults"),
        Page("playlist", translate("SettingsDialog", "Playlist"), *PLAYLIST_PAGE),
        Page("video", translate("SettingsDialog", "Video"), *VIDEO_PAGE),
    ),
    Group(
        translate("SettingsDialog", "Streaming"),
        Page(
            "resolution",
            translate("SettingsDialog", "Link Resolution"),
            "streaming/hls_via_streamlink",
            "streaming/resolver_priority",
            Section(
                "yt-dlp",
                "streaming/js_runtime_path",
                Slot("youtube_test"),
            ),
            Section(
                translate("SettingsDialog", "Resolver priority patterns"),
                "streaming/resolver_priority_patterns",
                Slot("wildcard_help"),
            ),
            scroll=False,
        ),
        Page(
            "sponsorblock",
            "SponsorBlock",
            "sponsorblock/enabled",
            Indented(*(category_setting(category) for category in CATEGORY_COLORS)),
            note=translate(
                "SettingsDialog",
                '<p>Every YouTube video you play is checked on SponsorBlock, where viewers mark sponsors, self-promotion and similar segments. Only a short prefix of a hash of the video\'s ID is sent.</p><p>Segments from <a href="{URL}">SponsorBlock</a>, under CC BY-NC-SA 4.0.</p>',
            ).format(URL=SPONSORBLOCK_URL),
        ),
        Page(
            "cookies",
            translate("SettingsDialog", "Cookies"),
            "cookies/enabled",
            Slot("cookies_list", fills=True),
            "cookies/allow_update",
            Note(
                translate(
                    "SettingsDialog",
                    "Cookies are login credentials. Anyone with access to this"
                    " computer can read them.",
                )
            ),
            Slot("cookies_howto"),
            scroll=False,
        ),
        Page(
            "network",
            translate("SettingsDialog", "Network"),
            "network/proxy_mode",
            "network/proxy_url",
            "network/timeout",
            "network/user_agent",
            "network/force_ipv4",
            "network/verify_tls",
            "network/allow_http_in_playlists",
            Note(
                translate(
                    "SettingsDialog",
                    "These settings apply to http and https links. Other links,"
                    " such as rtsp and rtmp, are opened by the player itself, and"
                    " only the user agent applies to them.",
                )
            ),
            Slot("network_test"),
        ),
    ),
    Group(
        translate("SettingsDialog", "Advanced"),
        Page(
            "decoder",
            translate("SettingsDialog", "Video Decoder"),
            Section(
                translate("SettingsDialog", "Video Decoder"),
                "player/video_driver",
                "player/video_driver_players",
            ),
            Section(
                translate(
                    "SettingsDialog",
                    'VLC Options [<a href="https://wiki.videolan.org/VLC_command-line_help/">reference</a>]',
                ),
                "misc/vlc_options",
            ),
            Section(
                translate("SettingsDialog", "Experimental"),
                "internal/opaque_hw_overlay",
                "internal/fake_overlay_invisibility",
                "internal/force_native_drag_events",
                "internal/hw_crop_border_offset",
            ),
        ),
        Page(
            "logging",
            translate("SettingsDialog", "Logging"),
            "logging/log_limit",
            "logging/log_limit_size",
            "logging/log_limit_backups",
            Section(
                translate("SettingsDialog", "Logging levels"),
                "logging/log_level",
                "logging/log_level_vlc",
            ),
        ),
    ),
)
