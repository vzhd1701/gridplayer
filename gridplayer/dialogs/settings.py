import logging
import os
import platform
import subprocess

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import QCheckBox, QComboBox, QDialog, QSpinBox

from gridplayer import params_vlc, params_env
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.utils import log_config
from gridplayer.params_static import GridMode, VideoAspect, VideoDriver
from gridplayer.settings import get_app_data_dir, settings
from gridplayer.dialogs.settings_ui import Ui_SettingsDialog

logger = logging.getLogger(__name__)


def _fill_combo_box(combo_box, values_dict):
    for i_id, i_name in values_dict.items():
        combo_box.addItem(i_name, i_id)


class SettingsDialog(QDialog, Ui_SettingsDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setupUi(self)
        self.customize_ui()

        self.settings_map = {
            "player/video_driver": self.playerVideoDriver,
            "player/video_driver_players": self.playerVideoDriverPlayers,
            "player/pause_background_videos": self.playerPauseBackgroundVideos,
            "player/pause_minimized": self.playerPauseWhenMinimized,
            "player/inhibit_screensaver": self.playerInhibitScreensaver,
            "player/one_instance": self.playerOneInstance,
            "playlist/grid_mode": self.playlistGridMode,
            "playlist/save_position": self.playlistSavePosition,
            "playlist/save_state": self.playlistSaveState,
            "playlist/save_window": self.playlistSaveWindow,
            "video_defaults/aspect": self.videoAspect,
            "video_defaults/random_loop": self.videoRandomLoop,
            "video_defaults/muted": self.videoMuted,
            "video_defaults/paused": self.videoPaused,
            "misc/overlay_timeout": self.miscOverlayTimeout,
            "misc/mouse_hide": self.miscMouseHide,
            "misc/mouse_hide_timeout": self.miscMouseHideTimeout,
            "logging/log_level": self.logLevel,
            "logging/log_level_vlc": self.logLevelVLC,
        }

        self.video_drivers_multiprocess = {
            VideoDriver.VLC_SW,
            VideoDriver.VLC_HW,
        }

        self.fill_playerVideoDriver()
        self.fill_playlistGridMode()
        self.fill_videoAspect()
        self.fill_logLevel()
        self.fill_logLevelVLC()

        self.playerVideoDriver.currentIndexChanged.connect(self.driver_selected)
        self.miscMouseHide.stateChanged.connect(self.miscMouseHideTimeout.setEnabled)
        self.logFileOpen.clicked.connect(self.open_logfile)

        self.load_settings()

        self.driver_selected(self.playerVideoDriver.currentIndex())
        self.miscMouseHideTimeout.setEnabled(self.miscMouseHide.isChecked())

        self.playerVideoDriverPlayers.setRange(1, 64)
        self.miscOverlayTimeout.setRange(1, 60)
        self.miscMouseHideTimeout.setRange(1, 60)

        for btn in self.buttonBox.buttons():
            btn.setIcon(QIcon())

    def customize_ui(self):
        font = self.playerVideoDriverBox.font()
        font.setBold(True)
        self.playerVideoDriverBox.setFont(font)

        # Restore the font of each children to regular.
        font.setBold(False)
        for child in self.playerVideoDriverBox.children():
            try:
                child.setFont(font)
            except AttributeError:
                pass

        if platform.system() == "Darwin":
            self.lay_body.setContentsMargins(4, 0, 0, 0)
            self.horizontalLayout.setContentsMargins(0, 0, 15, 0)
            self.lay_playerVideoDriverPlayers.setContentsMargins(3, 0, 2, 0)
            self.playerVideoDriverBox.setStyleSheet(
                "QGroupBox:title{padding: 0 4px 0 3px;margin-left:-5px;}"
            )

    def open_logfile(self):
        log_path = os.path.join(get_app_data_dir(), "gridplayer.log")

        logger.debug(f"Opening log file {log_path}")

        if not os.path.isfile(log_path):
            return QCustomMessageBox.critical(self, "Error", "Log file does not exist!")

        if params_env.IS_SNAP:
            # https://forum.snapcraft.io/t/xdg-open-or-gvfs-open-qdesktopservices-openurl-file-somelocation-file-txt-wont-open-the-file/16824
            subprocess.call(["xdg-open", log_path])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(log_path))

    def fill_logLevelVLC(self):
        log_levels = {
            log_config.DISABLED: "None",
            logging.ERROR: "Error",
            logging.WARNING: "Warning",
            logging.INFO: "Info",
            logging.DEBUG: "Debug",
        }

        _fill_combo_box(self.logLevelVLC, log_levels)

    def fill_logLevel(self):
        log_levels = {
            log_config.DISABLED: "None",
            logging.CRITICAL: "Critical",
            logging.ERROR: "Error",
            logging.WARNING: "Warning",
            logging.INFO: "Info",
            logging.DEBUG: "Debug",
        }

        _fill_combo_box(self.logLevel, log_levels)

    def fill_videoAspect(self):
        aspect_ratios = {
            VideoAspect.FIT: "Fit",
            VideoAspect.STRETCH: "Stretch",
            VideoAspect.NONE: "None",
        }

        _fill_combo_box(self.videoAspect, aspect_ratios)

    def fill_playlistGridMode(self):
        grid_modes = {
            GridMode.AUTO_ROWS: "Auto Rows First",
            GridMode.AUTO_COLS: "Auto Columns First",
        }

        _fill_combo_box(self.playlistGridMode, grid_modes)

    def fill_playerVideoDriver(self):
        video_drivers_disabled = []

        video_drivers = {
            VideoDriver.VLC_HW: f"Hardware <VLC {params_vlc.VLC_VERSION}>",
            VideoDriver.VLC_SW: f"Software <VLC {params_vlc.VLC_VERSION}>",
            VideoDriver.DUMMY: "Dummy",
        }

        _fill_combo_box(self.playerVideoDriver, video_drivers)

        for vd in video_drivers_disabled:
            idx = self.playerVideoDriver.findData(vd)
            self.playerVideoDriver.model().item(idx).setEnabled(False)

    def driver_selected(self, idx):
        driver_id = self.playerVideoDriver.itemData(idx)

        if driver_id in self.video_drivers_multiprocess:
            self.playerVideoDriverPlayers.setDisabled(False)
        else:
            self.playerVideoDriverPlayers.setDisabled(True)

    def load_settings(self):
        for setting, element in self.settings_map.items():
            setting_value = settings.get(setting)

            if isinstance(element, QCheckBox):
                element.setChecked(setting_value)
            elif isinstance(element, QSpinBox):
                element.setValue(setting_value)
            elif isinstance(element, QComboBox):
                idx = element.findData(setting_value)
                element.setCurrentIndex(idx)
            else:
                raise ValueError(f"No element encoder for {setting}")

    def save_settings(self):
        for setting, element in self.settings_map.items():
            if not element.isEnabled():
                continue

            new_value = None

            if isinstance(element, QCheckBox):
                new_value = element.isChecked()
            if isinstance(element, QSpinBox):
                new_value = element.value()
            if isinstance(element, QComboBox):
                new_value = element.currentData()

            if new_value is None:
                raise ValueError(f"No element decoder for {setting}")

            settings.set(setting, new_value)

    def accept(self):
        self.save_settings()

        super().accept()
