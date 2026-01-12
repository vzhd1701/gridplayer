import logging
from contextlib import suppress
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field
from PyQt5.QtCore import QSettings

from gridplayer.models.recent_list import (
    RecentList,
    RecentListPlaylists,
    RecentListVideos,
)
from gridplayer.models.resolver_patterns import ResolverPatterns
from gridplayer.params import env
from gridplayer.params.languages import get_system_language
from gridplayer.params.static import (
    AudioChannelMode,
    GridMode,
    SeekSyncMode,
    URLResolver,
    VideoAspect,
    VideoDriver,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.log_config import DISABLED

SETTINGS = None


_default_settings = {
    "player/video_driver": VideoDriver.VLC_HW,
    "player/video_driver_players": 4,
    "player/video_init_timeout": 120,
    "player/pause_background_videos": True,
    "player/pause_minimized": True,
    "player/inhibit_screensaver": True,
    "player/one_instance": True,
    "player/stay_on_top": False,
    "player/show_overlay_border": False,
    "player/language": get_system_language(),
    "player/recent_list_enabled": True,
    "player/recent_list_max_size": 10,
    "playlist/grid_mode": GridMode.AUTO_ROWS,
    "playlist/grid_fit": True,
    "playlist/grid_size": 0,
    "playlist/save_position": False,
    "playlist/save_state": False,
    "playlist/save_window": False,
    "playlist/seek_sync_mode": SeekSyncMode.DISABLED,
    "playlist/track_changes": True,
    "playlist/shuffle_on_load": False,
    "playlist/disable_click_pause": False,
    "playlist/disable_wheel_seek": False,
    "video_defaults/aspect": VideoAspect.FIT,
    "video_defaults/transform": VideoTransform.NONE,
    "video_defaults/repeat": VideoRepeat.SINGLE_FILE,
    "video_defaults/audio_mode": AudioChannelMode.UNSET,
    "video_defaults/random_loop": False,
    "video_defaults/muted": True,
    "video_defaults/paused": False,
    "video_defaults/stream_quality": "best",
    "video_defaults/auto_reload_timer": 0,
    "misc/overlay_hide": True,
    "misc/overlay_timeout": 3,
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
    "streaming/hls_via_streamlink": True,
    "streaming/resolver_priority": URLResolver.STREAMLINK,
    "streaming/resolver_priority_patterns": ResolverPatterns([]),
    "recent_list_videos": RecentListVideos(),
    "recent_list_playlists": RecentListPlaylists(),
}

if env.IS_MACOS:
    _default_settings["player/video_driver"] = VideoDriver.VLC_HW_SP


class _Settings:
    def __init__(self):
        settings_path = get_app_data_dir() / "settings.ini"

        self.settings = QSettings(str(settings_path), QSettings.IniFormat)

        logging.getLogger("Settings").debug(f"Settings path: {settings_path}")

    def get(self, setting):
        setting_type = type(_default_settings[setting])

        if issubclass(setting_type, Enum):
            return self._parse_enum(setting_type, setting)

        if issubclass(setting_type, BaseModel):
            return self._parse_pydantic(setting_type, setting)

        if issubclass(setting_type, RecentList):
            return self._parse_list(setting_type, setting)

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
        self.set(setting_name, _default_settings[setting_name])

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
            with suppress(ValueError):
                return setting_type.parse_raw(setting_value)

        return _default_settings[setting]

    def _parse_list(self, setting_type, setting):
        res_list = []

        self.settings.beginGroup(setting)
        res_list.extend(self.settings.value(key) for key in self.settings.childKeys())
        self.settings.endGroup()

        return setting_type(res_list)

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

        if isinstance(setting_value, (Path, str)):
            return str(setting_value)

        return str(setting_value)


def Settings():
    global SETTINGS

    if not SETTINGS:
        SETTINGS = _Settings()

    return SETTINGS


def default_field(setting_name):
    return Field(default_factory=lambda: Settings().get(setting_name))
