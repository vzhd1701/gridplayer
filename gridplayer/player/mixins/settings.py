from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params_static import VideoDriver
from gridplayer.settings import Settings
from gridplayer.utils import log_config


class PlayerSettingsMixin(object):
    def cmd_settings(self):
        previous_settings = Settings().get_all()

        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()

        self._apply_settings(previous_settings)

        if self._is_reload_needed(previous_settings):
            self.reload_playlist()

    def _apply_settings(self, previous_settings):
        checks = (
            "logging/log_level",
            "logging/log_level_vlc",
            "player/inhibit_screensaver",
        )

        changes = self._setting_changes(previous_settings, checks)

        if changes["logging/log_level"]:
            self._apply_logging_log_level()

        if changes["logging/log_level_vlc"]:
            self._apply_logging_log_level_vlc()

        if changes["player/inhibit_screensaver"]:
            self._apply_player_inhibit_screensaver()

    def _apply_player_inhibit_screensaver(self):
        self.is_paused_change()

    def _apply_logging_log_level_vlc(self):
        self.driver_mgr.set_log_level_vlc(Settings().get("logging/log_level_vlc"))

    def _apply_logging_log_level(self):
        log_config.set_root_level(Settings().get("logging/log_level"))
        self.driver_mgr.set_log_level(Settings().get("logging/log_level"))

    def _is_reload_needed(self, previous_settings):
        checks = (
            "player/video_driver",
            "player/video_driver_players",
            "internal/opaque_hw_overlay",
        )

        changes = self._setting_changes(previous_settings, checks)

        if changes["player/video_driver"]:
            return True

        is_current_engine_multiproc = Settings().get("player/video_driver") in {
            VideoDriver.VLC_HW,
            VideoDriver.VLC_SW,
        }

        if changes["player/video_driver_players"] and is_current_engine_multiproc:
            return True

        return changes["internal/opaque_hw_overlay"]

    def _setting_changes(self, previous_settings, checks):
        return {k: previous_settings[k] != Settings().get(k) for k in checks}
