import json
import logging
from contextlib import suppress
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field
from PyQt5.QtCore import QSettings

from gridplayer.models.keymap_overrides import KeymapOverrides
from gridplayer.models.recent_list import (
    RecentList,
    RecentListPlaylists,
    RecentListVideos,
)
from gridplayer.models.resolver_patterns import ResolverPatterns
from gridplayer.params import env
from gridplayer.params.gestures import (
    GESTURE_DROP_SWITCH,
    GESTURE_PAN,
    GESTURE_ZOOM_SELECT,
)
from gridplayer.params.languages import get_system_language
from gridplayer.params.static import (
    AddMode,
    AudioChannelMode,
    AudioTrackMode,
    CacheMode,
    ColorScheme,
    DropAction,
    GridMode,
    HWCropBorderOffset,
    ListEndAction,
    ListFailAction,
    ListUpdate,
    ListView,
    NetworkRetryMode,
    ProxyMode,
    ScreenshotFormat,
    SeekSyncMode,
    SponsorBlockMode,
    SubtitleTrackMode,
    UnsavedChangesMode,
    URLResolver,
    VideoAnchor,
    VideoAspect,
    VideoCrop,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoDriver,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.params.subtitle_encodings import DEFAULT_ENCODING
from gridplayer.params.subtitle_style import SUBTITLE_STYLE_DEFAULTS
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.log_config import DISABLED

SETTINGS = None


_default_settings = {
    "player/video_driver": VideoDriver.VLC_HW,
    "player/video_driver_players": 4,
    "player/video_init_timeout": 120,
    "player/inhibit_screensaver": True,
    "player/media_keys_background": True,
    "player/one_instance": True,
    "player/stay_on_top": False,
    "player/start_maximized": False,
    "player/start_fullscreen": False,
    # the icon in the tray (the menu bar on macOS), and what goes there
    "player/tray_icon": False,
    "player/minimize_to_tray": False,
    "player/close_to_tray": False,
    "player/hide_taskbar": False,
    "player/tray_stop_video": False,
    # the note that the player is still running, shown the first time it
    # is closed to the tray
    "player/tray_note_shown": False,
    "player/language": get_system_language(),
    "player/color_scheme": ColorScheme.SYSTEM,
    "player/keymap": KeymapOverrides({}),
    "player/recent_list_enabled": True,
    "player/recent_list_max_size": 10,
    "player/reopen_last_playlist": False,
    "player/list_max_mb": 512,
    # empty means the screenshots folder in the app data folder, worked out
    # when a screenshot is taken so it follows a portable or moved data dir
    "screenshots/dir": "",
    # in the style of mpv screenshot-template, see gridplayer.utils.screenshots
    "screenshots/filename_template": "%F_%P",
    "screenshots/format": ScreenshotFormat.PNG,
    "screenshots/jpg_quality": 90,
    # thumbnails and the like, kept so they are not downloaded again;
    # see gridplayer.utils.cache
    "cache/mode": CacheMode.DISK,
    "cache/max_mb": 1024,
    "playlist/grid_mode": GridMode.AUTO_ROWS,
    "playlist/grid_fit": True,
    "playlist/grid_size": 0,
    "playlist/grid_rows": 3,
    "playlist/grid_cols": 3,
    "playlist/grid_preallocate": False,
    "playlist/save_paths_relative": False,
    "playlist/save_position": False,
    "playlist/save_state": False,
    "playlist/save_window": False,
    "playlist/seek_sync_mode": SeekSyncMode.DISABLED,
    "playlist/view_sync": False,
    "playlist/pause_sync": False,
    "playlist/rate_sync": False,
    "playlist/bookmarks_shared": True,
    "playlist/seek_step_short": 5.0,
    "playlist/seek_step_medium": 15.0,
    "playlist/seek_step_long": 30.0,
    "playlist/zoom_step": 10,
    "playlist/zoom_proportional": False,
    "playlist/folder_skip_hidden": True,
    "playlist/folder_max_entries": 50000,
    "playlist/shuffle_avoid_open": False,
    "playlist/unsaved_changes": UnsavedChangesMode.ASK,
    "playlist/shuffle_on_load": False,
    "playlist/drop_action_internal": DropAction.INSERT,
    "playlist/drop_action_external": DropAction.INSERT,
    "playlist/add_mode": AddMode.CELL_EACH,
    "playlist/warn_many_cells": True,
    "playlist/list_view": ListView.TITLES,
    "playlist/list_thumbnails": True,
    "playlist/list_get_info": False,
    "playlist/list_update": ListUpdate.ON_LOAD,
    "playlist/disable_mouse_click_events": False,
    "playlist/disable_mouse_wheel_events": False,
    "playlist/disable_overlay": False,
    "playlist/pause_background_videos": True,
    "playlist/pause_minimized": True,
    "playlist/show_overlay_border": True,
    "playlist/overlay_hide_on_timeout": True,
    "playlist/overlay_timeout": 3,
    "video_defaults/aspect": VideoAspect.FIT,
    "video_defaults/transform": VideoTransform.NONE,
    "video_defaults/deinterlace": VideoDeinterlace.AUTO,
    "video_defaults/deinterlace_mode": VideoDeinterlaceMode.AUTO,
    "video_defaults/end_action": VideoEndAction.LOOP_FILE,
    "video_defaults/dir_recursive": False,
    "video_defaults/list_end_action": ListEndAction.START_OVER,
    "video_defaults/list_fail_action": ListFailAction.PLAY_NEXT,
    "video_defaults/list_fail_wait": 2,
    "video_defaults/audio_mode": AudioChannelMode.UNSET,
    "video_defaults/audio_track_mode": AudioTrackMode.DEFAULT,
    "video_defaults/audio_languages": "",
    "video_defaults/external_audio_autodiscover": False,
    "video_defaults/subtitle_track_mode": SubtitleTrackMode.DISABLED,
    "video_defaults/subtitle_languages": "",
    "video_defaults/subtitle_encoding": DEFAULT_ENCODING,
    "video_defaults/external_subtitle_autodiscover": False,
    "video_defaults/random_loop": False,
    "video_defaults/muted": True,
    "video_defaults/initial_state": VideoInitialState.PLAYING,
    "video_defaults/rate": 1.0,
    "video_defaults/scale": 1.0,
    "video_defaults/zoom_to_cursor": False,
    "video_defaults/volume": 1.0,
    "video_defaults/color": "#ffffff",
    "video_defaults/crop": VideoCrop(0, 0, 0, 0),
    "video_defaults/anchor": VideoAnchor.CENTER,
    "video_defaults/shift_past_edges": False,
    "video_defaults/stream_quality": "best",
    "video_defaults/quality_adapt_delay": 15,
    "video_defaults/network_retry_mode": NetworkRetryMode.TIMES,
    "video_defaults/network_retry_times": 3,
    "video_defaults/auto_reload_timer": 0,
    # what subtitles look like, which VLC settles per process rather
    # than per video; see gridplayer.params.subtitle_style
    **SUBTITLE_STYLE_DEFAULTS,
    "misc/mouse_hide": True,
    "misc/mouse_hide_timeout": 5,
    "misc/vlc_options": "",
    "logging/log_level": logging.WARNING,
    "logging/log_level_vlc": DISABLED,
    "logging/log_limit": False,
    "logging/log_limit_size": 10,
    "logging/log_limit_backups": 1,
    "internal/opaque_hw_overlay": False,
    "internal/fake_overlay_invisibility": False,
    "internal/force_native_drag_events": False,
    "internal/hw_crop_border_offset": HWCropBorderOffset.AUTO,
    "streaming/hls_via_streamlink": True,
    "streaming/resolver_priority": URLResolver.STREAMLINK,
    "streaming/resolver_priority_patterns": ResolverPatterns([]),
    # empty means look in the usual places, which is most of them.
    # See gridplayer.utils.js_runtime for what those are and why
    "streaming/js_runtime_path": "",
    # Off until asked for: every YouTube video played would otherwise be
    # looked up on a server that is neither YouTube nor ours. Only sponsors
    # are skipped out of the box, as in the extension; the plugs and the
    # reminders are only marked. See gridplayer.params.sponsorblock
    "sponsorblock/enabled": False,
    "sponsorblock/sponsor": SponsorBlockMode.SKIP,
    "sponsorblock/selfpromo": SponsorBlockMode.SHOW,
    "sponsorblock/interaction": SponsorBlockMode.SHOW,
    "sponsorblock/intro": SponsorBlockMode.OFF,
    "sponsorblock/outro": SponsorBlockMode.OFF,
    "sponsorblock/preview": SponsorBlockMode.OFF,
    "sponsorblock/hook": SponsorBlockMode.OFF,
    "sponsorblock/filler": SponsorBlockMode.OFF,
    "sponsorblock/music_offtopic": SponsorBlockMode.OFF,
    "sponsorblock/poi_highlight": SponsorBlockMode.SHOW,
    "cookies/enabled": True,
    "cookies/allow_update": True,
    "network/proxy_mode": ProxyMode.SYSTEM,
    "network/proxy_url": "",
    # empty means the one built in, which is what every request goes out
    # with unless the user has a reason to say otherwise
    "network/user_agent": "",
    # IPv6 that is advertised but does not work stalls every request until
    # it times out, and nothing here races the two families the way a
    # browser does. Forcing IPv4 is the way out of that.
    "network/force_ipv4": False,
    # zero leaves each library on its own default rather than imposing one
    # number on clients that have thought about it separately
    "network/timeout": 0,
    "network/verify_tls": True,
    # Streamlink refuses an http link in an https playlist; VLC, mpv and
    # ffmpeg follow it, and some IPTV hosts depend on that
    "network/allow_http_in_playlists": True,
    "recent_list_videos": RecentListVideos(),
    "recent_list_playlists": RecentListPlaylists(),
    # the playlist file open when the player was last closed, empty for none
    "last_playlist": "",
}

if env.IS_MACOS:
    _default_settings["player/video_driver"] = VideoDriver.VLC_HW_SP


class _Settings:
    def __init__(self):
        settings_path = get_app_data_dir() / "settings.ini"

        self.settings = QSettings(str(settings_path), QSettings.IniFormat)

        logging.getLogger("Settings").debug(f"Settings path: {settings_path}")

        self._migrate_legacy_keys()

    def _migrate_legacy_keys(self):
        """Rename obsolete setting keys once; write only new names."""
        renames = {
            "playlist/disable_click_pause": "playlist/disable_mouse_click_events",
            "playlist/disable_wheel_seek": "playlist/disable_mouse_wheel_events",
            "player/pause_background_videos": "playlist/pause_background_videos",
            "player/pause_minimized": "playlist/pause_minimized",
            "player/show_overlay_border": "playlist/show_overlay_border",
            "misc/overlay_hide": "playlist/overlay_hide_on_timeout",
            "misc/overlay_timeout": "playlist/overlay_timeout",
        }
        for old_key, new_key in renames.items():
            if self.settings.contains(old_key) and not self.settings.contains(new_key):
                self.settings.setValue(new_key, self.settings.value(old_key))
            if self.settings.contains(old_key):
                self.settings.remove(old_key)

        self._migrate_track_changes_flag()
        self._migrate_paused_to_initial_state()
        self._migrate_repeat_to_end_action()
        self._migrate_mouse_triggers()

    def _migrate_track_changes_flag(self):
        """Legacy bool "warn about unsaved changes" flag → close mode enum."""
        old_key = "playlist/track_changes"
        new_key = "playlist/unsaved_changes"

        if not self.settings.contains(old_key):
            return

        if not self.settings.contains(new_key):
            legacy_value = str(self.settings.value(old_key)).lower()
            mode = "discard" if legacy_value == "false" else "ask"
            self.settings.setValue(new_key, mode)

        self.settings.remove(old_key)

    def _migrate_paused_to_initial_state(self):
        """Legacy bool paused default → Playing / Paused initial state."""
        old_key = "video_defaults/paused"
        new_key = "video_defaults/initial_state"

        if not self.settings.contains(old_key):
            return

        if not self.settings.contains(new_key):
            legacy_value = str(self.settings.value(old_key)).lower()
            state = "paused" if legacy_value in {"true", "1"} else "playing"
            self.settings.setValue(new_key, state)

        self.settings.remove(old_key)

    def _migrate_repeat_to_end_action(self):
        """Legacy Repeat enum + key → When finished / end_action."""
        old_key = "video_defaults/repeat"
        new_key = "video_defaults/end_action"
        aliases = {
            "none": VideoEndAction.STOP.value,
            "single_file": VideoEndAction.LOOP_FILE.value,
            "dir": VideoEndAction.NEXT_FILE.value,
            "dir_shuffle": VideoEndAction.SHUFFLE_FILE.value,
        }

        if self.settings.contains(old_key) and not self.settings.contains(new_key):
            value = self.settings.value(old_key)
            if isinstance(value, str):
                value = aliases.get(value, value)
            self.settings.setValue(new_key, value)
        if self.settings.contains(old_key):
            self.settings.remove(old_key)

        if not self.settings.contains(new_key):
            return
        current = self.settings.value(new_key)
        if isinstance(current, str) and current in aliases:
            self.settings.setValue(new_key, aliases[current])

    def _migrate_mouse_triggers(self):
        """The drags once picked from lists, and the key held to switch a
        drop, into the keymap, where they are set alongside the shortcuts.

        One set to its old default is left to the keymap's, the same.
        """
        drags = {
            "middle": "Middle-Drag",
            "ctrl": "Ctrl+Drag",
            "shift": "Shift+Drag",
            "alt": "Alt+Drag",
        }
        holds = {"shift": "Hold Shift", "ctrl": "Hold Ctrl", "alt": "Hold Alt"}
        moved = {
            "player/pan_trigger": (GESTURE_PAN, "middle", drags),
            "player/zoom_select_trigger": (GESTURE_ZOOM_SELECT, "none", drags),
            "playlist/drop_modifier": (GESTURE_DROP_SWITCH, "shift", holds),
        }

        if not any(self.settings.contains(old_key) for old_key in moved):
            return

        overrides = dict(self.get("player/keymap").root)

        for old_key, (gesture_id, old_default, keys) in moved.items():
            if not self.settings.contains(old_key):
                continue

            value = str(self.settings.value(old_key))
            if value != old_default and gesture_id not in overrides:
                overrides[gesture_id] = [keys[value]] if value in keys else []

            self.settings.remove(old_key)

        self.set("player/keymap", KeymapOverrides(overrides))

    def get(self, setting):
        setting_type = type(_default_settings[setting])

        if issubclass(setting_type, Enum):
            return self._parse_enum(setting_type, setting)

        if issubclass(setting_type, BaseModel):
            return self._parse_pydantic(setting_type, setting)

        if issubclass(setting_type, RecentList):
            return self._parse_list(setting_type, setting)

        if issubclass(setting_type, tuple):
            return self._parse_named_tuple(setting_type, setting)

        return self.settings.value(
            setting, _default_settings[setting], type=setting_type
        )

    def set(self, setting_name, setting_value):
        setting_type = type(_default_settings[setting_name])

        if setting_type is not type(setting_value):
            raise ValueError(
                f"Setting {setting_name} is of type {setting_type}"
                f" but value is of type {type(setting_value)}"
            )

        if issubclass(setting_type, RecentList):
            self._save_list(setting_name, setting_value)
            return

        setting_value = self._get_storage_value(setting_value)

        self.settings.setValue(setting_name, setting_value)

    def reset(self, setting_name):
        """Back to the default by forgetting it, so that a default changed
        in a later version reaches it too."""

        self.settings.remove(setting_name)

    def get_all(self):
        return {k: self.get(k) for k in _default_settings}

    def sync(self):
        self.settings.sync()

    def sync_get(self, setting):
        self.sync()
        return self.get(setting)

    @property
    def filename(self):
        return self.settings.fileName()

    def _parse_enum(self, setting_type, setting):
        setting_value = self.settings.value(setting)

        if isinstance(setting_value, str):
            with suppress(ValueError):
                return setting_type(setting_value)

        return _default_settings[setting]

    def _parse_pydantic(self, setting_type, setting):
        setting_value = self.settings.value(setting)

        if isinstance(setting_value, str):
            with suppress(ValueError, TypeError):
                if hasattr(setting_type, "model_validate_json"):
                    return setting_type.model_validate_json(setting_value)
                return setting_type.parse_raw(setting_value)

        return _default_settings[setting]

    def _parse_list(self, setting_type, setting):
        res_list = []

        self.settings.beginGroup(setting)
        res_list.extend(self.settings.value(key) for key in self.settings.childKeys())
        self.settings.endGroup()

        return setting_type(res_list)

    def _parse_named_tuple(self, setting_type, setting):
        setting_value = self.settings.value(setting)

        if isinstance(setting_value, str):
            with suppress(ValueError, TypeError):
                values = setting_value.split(",")
                if len(values) == len(setting_type._fields):
                    return setting_type(*(json.loads(v) for v in values))

        return _default_settings[setting]

    def _save_list(self, setting_name, setting_value):
        self.settings.remove(setting_name)

        if not setting_value:
            return

        self.settings.beginGroup(setting_name)
        for i, item in enumerate(setting_value):
            self.settings.setValue(str(i), self._get_storage_value(item))
        self.settings.endGroup()

    def _get_storage_value(self, setting_value):
        if isinstance(setting_value, Enum):
            return setting_value.value

        if isinstance(setting_value, BaseModel):
            return setting_value.model_dump_json()

        if isinstance(setting_value, tuple):
            return ",".join(str(v) for v in setting_value)

        if isinstance(setting_value, (Path, str)):
            return str(setting_value)

        return str(setting_value)


def Settings():
    global SETTINGS

    if not SETTINGS:
        SETTINGS = _Settings()

    return SETTINGS


def default_value(setting_name):
    """What a setting is out of the box, on this system."""

    return _default_settings[setting_name]


def default_field(setting_name):
    return Field(default_factory=lambda: Settings().get(setting_name))
