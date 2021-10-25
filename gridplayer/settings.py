import logging
import os
from enum import Enum

from PyQt5.QtCore import QSettings

from gridplayer.params_static import GridMode, VideoAspect, VideoDriver
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.log_config import DISABLED

SETTINGS = None

_default_settings = {
    "player/video_driver": VideoDriver.VLC_HW,
    "player/video_driver_players": 4,
    "player/pause_background_videos": True,
    "player/pause_minimized": True,
    "player/inhibit_screensaver": True,
    "player/one_instance": True,
    "playlist/grid_mode": GridMode.AUTO_ROWS,
    "playlist/save_position": False,
    "playlist/save_state": False,
    "playlist/save_window": False,
    "video_defaults/aspect": VideoAspect.FIT,
    "video_defaults/random_loop": False,
    "video_defaults/muted": True,
    "video_defaults/paused": False,
    "misc/overlay_timeout": 1,
    "misc/mouse_hide": True,
    "misc/mouse_hide_timeout": 3,
    "logging/log_level": logging.WARNING,
    "logging/log_level_vlc": DISABLED,
    "internal/opaque_hw_overlay": False,
}


class _Settings(object):
    def __init__(self):
        settings_path = os.path.join(get_app_data_dir(), "settings.ini")

        self.settings = QSettings(settings_path, QSettings.IniFormat)

        logging.getLogger("Settings").debug(f"Settings path: {settings_path}")

    def get(self, setting):
        setting_type = type(_default_settings[setting])

        if issubclass(setting_type, Enum):
            setting_value = self.settings.value(setting, _default_settings[setting])
            if isinstance(setting_value, str):
                return setting_type(setting_value)

        return self.settings.value(
            setting, _default_settings[setting], type=setting_type
        )

    def set(self, setting_name, setting_value):
        if isinstance(setting_value, Enum):
            setting_value = setting_value.value

        self.settings.setValue(setting_name, setting_value)

    def get_all(self):
        return {k: self.get(k) for k in _default_settings}

    def sync(self):
        self.settings.sync()

    @property
    def filename(self):
        return self.settings.fileName()


def Settings():
    global SETTINGS  # noqa: WPS420

    if not SETTINGS:
        SETTINGS = _Settings()  # noqa: WPS442

    return SETTINGS
