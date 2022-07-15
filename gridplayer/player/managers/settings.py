from PyQt5.QtCore import pyqtSignal

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate


class SettingsManager(ManagerBase):
    reload = pyqtSignal()
    set_screensaver = pyqtSignal(int)
    set_log_level = pyqtSignal(int)
    set_log_level_vlc = pyqtSignal(int)

    @property
    def commands(self):
        return {"settings": self.cmd_settings}

    def cmd_settings(self):
        previous_settings = Settings().get_all()

        SettingsDialog(self.parent()).exec_()

        self._apply_settings(previous_settings)

        if self._is_restart_needed(previous_settings):
            QCustomMessageBox.information(
                self.parent(),
                translate("Dialog - Settings apply restart", "Settings", "Header"),
                translate(
                    "Dialog - Settings apply restart",
                    "Restart is required for the new settings to take effect.",
                ),
            )

        if self._is_reload_needed(previous_settings):
            self.reload.emit()

    def _apply_settings(self, previous_settings):
        checks = {
            "logging/log_level": self.set_log_level,
            "logging/log_level_vlc": self.set_log_level_vlc,
            "player/inhibit_screensaver": self.set_screensaver,
        }

        changes = self._setting_changes(previous_settings, tuple(checks))

        for c in changes:
            checks[c].emit(Settings().get(c))

    def _is_reload_needed(self, previous_settings):
        checks = {
            "player/video_driver",
            "player/video_driver_players",
            "internal/opaque_hw_overlay",
            "internal/fake_overlay_invisibility",
            "misc/vlc_options",
        }

        return self._setting_changes(previous_settings, checks)

    def _is_restart_needed(self, previous_settings):
        checks = {
            "player/language",
            "logging/log_limit",
            "logging/log_limit_size",
            "logging/log_limit_backups",
        }

        return self._setting_changes(previous_settings, checks)

    def _setting_changes(self, previous_settings, checks):
        return {k for k in checks if previous_settings[k] != Settings().get(k)}
