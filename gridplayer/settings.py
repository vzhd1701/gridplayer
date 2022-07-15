import logging
from contextlib import suppress
from enum import Enum

from pydantic import BaseModel, Field
from PyQt5.QtCore import QLocale, QSettings

from gridplayer.models.resolver_patterns import ResolverPatterns
from gridplayer.params import env
from gridplayer.params.static import (
    SUPPORTED_LANGUAGES,
    GridMode,
    SeekSyncMode,
    URLResolver,
    VideoAspect,
    VideoDriver,
    VideoRepeat,
)
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.log_config import DISABLED

SETTINGS = None


def default_language():
    lang = QLocale().system().name()
    if lang in SUPPORTED_LANGUAGES:
        return lang
    return "en_US"


_default_settings = {
    "player/video_driver": VideoDriver.VLC_HW,
    "player/video_driver_players": 4,
    "player/video_init_timeout": 120,
    "player/pause_background_videos": True,
    "player/pause_minimized": True,
    "player/inhibit_screensaver": True,
    "player/one_instance": True,
    "player/show_overlay_border": False,
    "player/language": default_language(),
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
    "video_defaults/repeat": VideoRepeat.SINGLE_FILE,
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
    "streaming/resolver_priority_patterns": ResolverPatterns(__root__=[]),
}

if env.IS_MACOS:
    _default_settings["player/video_driver"] = VideoDriver.VLC_HW_SP


class _Settings(object):
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

        return self.settings.value(
            setting, _default_settings[setting], type=setting_type
        )

    def set(self, setting_name, setting_value):
        if isinstance(setting_value, Enum):
            setting_value = setting_value.value

        if isinstance(setting_value, BaseModel):
            setting_value = setting_value.json()

        self.settings.setValue(setting_name, setting_value)

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


def Settings():
    global SETTINGS  # noqa: WPS420

    if not SETTINGS:
        SETTINGS = _Settings()  # noqa: WPS442

    return SETTINGS


def default_field(setting_name):
    return Field(default_factory=lambda: Settings().get(setting_name))
