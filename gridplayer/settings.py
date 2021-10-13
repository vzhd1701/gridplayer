import logging
import os
import platform
import sys
from enum import Enum

from PyQt5.QtCore import QSettings, QStandardPaths

from gridplayer.utils.log_config import DISABLED
from gridplayer.params_static import GridMode, VideoAspect, VideoDriver

default_settings = {
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


def is_portable():
    if platform.system() != "Windows":
        return False

    portable_data_dir = os.path.join(os.path.dirname(sys.executable), "portable_data")

    return os.path.isdir(portable_data_dir)


def get_app_data_dir():
    if is_portable():
        return os.path.join(os.path.dirname(sys.executable), "portable_data")

    app_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)

    if not os.path.isdir(app_dir):
        os.makedirs(app_dir)

    return app_dir


class Settings(object):
    def __init__(self):
        settings_path = os.path.join(get_app_data_dir(), "settings.ini")

        self.settings = QSettings(settings_path, QSettings.IniFormat)

    def get(self, setting):
        setting_type = type(default_settings[setting])

        if issubclass(setting_type, Enum):
            setting_value = self.settings.value(setting, default_settings[setting])
            if isinstance(setting_value, str):
                return setting_type(setting_value)

        return self.settings.value(
            setting, default_settings[setting], type=setting_type
        )

    def set(self, setting_name, setting_value):
        if isinstance(setting_value, Enum):
            setting_value = setting_value.value

        self.settings.setValue(setting_name, setting_value)

    def get_all(self):
        return {k: self.get(k) for k in default_settings}

    def sync(self):
        self.settings.sync()


settings = Settings()
