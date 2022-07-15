import contextlib
import logging
import subprocess

from PyQt5.QtCore import QLocale, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon, QPalette
from PyQt5.QtWidgets import QCheckBox, QComboBox, QDialog, QLineEdit, QSpinBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.settings_dialog_ui import Ui_SettingsDialog
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
from gridplayer.settings import Settings
from gridplayer.utils import log_config
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.qt import qt_connect, translate
from gridplayer.widgets.language_list import LanguageList
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList

VIDEO_DRIVERS_MULTIPROCESS = (
    VideoDriver.VLC_SW,
    VideoDriver.VLC_HW,
)

MAX_VLC_PROCESSES = 64


def _fill_combo_box(combo_box, values_dict):
    for i_id, i_name in values_dict.items():
        combo_box.addItem(i_name, i_id)


def _set_combo_box(combo_box, data_value):
    idx = combo_box.findData(data_value)
    combo_box.setCurrentIndex(idx)


def _set_groupbox_header_bold(groupbox):
    font = groupbox.font()
    font.setBold(True)
    groupbox.setFont(font)

    # Restore the font of each children to regular.
    font.setBold(False)
    for child in groupbox.children():
        with contextlib.suppress(AttributeError):
            child.setFont(font)


class SettingsDialog(QDialog, Ui_SettingsDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self._log = logging.getLogger(self.__class__.__name__)

        self.setupUi(self)

        self.settings_map = {
            "player/video_driver": self.playerVideoDriver,
            "player/video_driver_players": self.playerVideoDriverPlayers,
            "player/video_init_timeout": self.timeoutVideoInit,
            "player/pause_background_videos": self.playerPauseBackgroundVideos,
            "player/pause_minimized": self.playerPauseWhenMinimized,
            "player/inhibit_screensaver": self.playerInhibitScreensaver,
            "player/one_instance": self.playerOneInstance,
            "player/show_overlay_border": self.playerShowOverlayBorder,
            "player/language": self.listLanguages,
            "playlist/grid_mode": self.gridMode,
            "playlist/grid_fit": self.gridFit,
            "playlist/grid_size": self.gridSize,
            "playlist/shuffle_on_load": self.gridShuffleOnLoad,
            "playlist/save_position": self.playlistSavePosition,
            "playlist/save_state": self.playlistSaveState,
            "playlist/save_window": self.playlistSaveWindow,
            "playlist/seek_sync_mode": self.playlistSeekSyncMode,
            "playlist/track_changes": self.playlistTrackChanges,
            "playlist/disable_click_pause": self.playlistDisableClickPause,
            "playlist/disable_wheel_seek": self.playlistDisableWheelSeek,
            "video_defaults/aspect": self.videoAspect,
            "video_defaults/repeat": self.repeatMode,
            "video_defaults/random_loop": self.videoRandomLoop,
            "video_defaults/muted": self.videoMuted,
            "video_defaults/paused": self.videoPaused,
            "video_defaults/stream_quality": self.streamQuality,
            "video_defaults/auto_reload_timer": self.streamAutoReloadTimer,
            "misc/overlay_hide": self.timeoutOverlayFlag,
            "misc/overlay_timeout": self.timeoutOverlay,
            "misc/mouse_hide": self.timeoutMouseHideFlag,
            "misc/mouse_hide_timeout": self.timeoutMouseHide,
            "misc/vlc_options": self.miscVLCOptions,
            "logging/log_level": self.logLevel,
            "logging/log_level_vlc": self.logLevelVLC,
            "logging/log_limit": self.logLimit,
            "logging/log_limit_size": self.logLimitSize,
            "logging/log_limit_backups": self.logLimitBackups,
            "internal/opaque_hw_overlay": self.miscOpaqueHWOverlay,
            "internal/fake_overlay_invisibility": self.miscFakeOverlayInvisibility,
            "streaming/hls_via_streamlink": self.streamingHLSVIAStreamlink,
            "streaming/resolver_priority": self.streamingResolverPriority,
            "streaming/resolver_priority_patterns": self.streamingResolverPriorityPatterns,  # noqa: E501
        }

        self.ui_customize()
        self.ui_fill()

        self.ui_connect()
        self.ui_set_limits()

        self.load_settings()

        self.ui_customize_dynamic()

    def ui_customize(self):  # noqa: WPS213
        for btn in self.buttonBox.buttons():
            btn.setIcon(QIcon())

        self.ui_customize_section_index()

        _set_groupbox_header_bold(self.playerVideoDriverBox)

        if not env.IS_LINUX:
            self.section_misc.hide()
            self.miscOpaqueHWOverlay.hide()
            self.miscFakeOverlayInvisibility.hide()

    def ui_customize_section_index(self):
        font = self.section_index.font()
        font.setPixelSize(16)  # noqa: WPS432
        self.section_index.setFont(font)

        pal = self.section_index.palette()
        col = pal.color(QPalette.Active, QPalette.Text)
        pal.setColor(QPalette.Disabled, QPalette.Text, col)
        self.section_index.setPalette(pal)

    def ui_fill(self):  # noqa: WPS213
        self.fill_playerVideoDriver()
        self.fill_gridMode()
        self.fill_videoAspect()
        self.fill_repeatMode()
        self.fill_logLevel()
        self.fill_logLevelVLC()
        self.fill_language()
        self.fill_streamQuality()
        self.fill_playlistSeekSyncMode()
        self.fill_streamingResolverPriority()

    def ui_set_limits(self):  # noqa: WPS213
        self.playerVideoDriverPlayers.setRange(1, MAX_VLC_PROCESSES)
        self.timeoutOverlay.setRange(1, 60)
        self.timeoutMouseHide.setRange(1, 60)
        self.logLimitSize.setRange(1, 1024 * 1024)
        self.logLimitBackups.setRange(1, 1000)
        self.timeoutVideoInit.setRange(1, 1000)

        self.gridSize.setRange(0, 1000)
        self.gridSize.setSpecialValueText(translate("Grid Size", "Auto"))

        self.streamAutoReloadTimer.setRange(0, 1000)
        self.streamAutoReloadTimer.setSpecialValueText(
            translate("Auto Reload Timer", "Disabled")
        )

    def ui_customize_dynamic(self):
        self.driver_selected(self.playerVideoDriver.currentIndex())
        self.timeoutMouseHide.setEnabled(self.timeoutMouseHideFlag.isChecked())
        self.timeoutOverlay.setEnabled(self.timeoutOverlayFlag.isChecked())
        self.logLimitSize.setEnabled(self.logLimit.isChecked())
        self.logLimitBackups.setEnabled(self.logLimit.isChecked())
        self.streamingWildcardHelp.setVisible(False)

        self.switch_page(None)

    def ui_connect(self):
        qt_connect(
            (self.playerVideoDriver.currentIndexChanged, self.driver_selected),
            (self.timeoutMouseHideFlag.stateChanged, self.timeoutMouseHide.setEnabled),
            (self.timeoutOverlayFlag.stateChanged, self.timeoutOverlay.setEnabled),
            (self.logFileOpen.clicked, self.open_logfile),
            (self.section_index.currentTextChanged, self.switch_page),
            (self.section_index.itemSelectionChanged, self.keep_index_selection),
            (self.logLimit.stateChanged, self.logLimitSize.setEnabled),
            (self.logLimit.stateChanged, self.logLimitBackups.setEnabled),
            (self.streamingWildcardHelpButton.clicked, self.toggle_wildcard_help),
        )

    def toggle_wildcard_help(self):
        self.streamingWildcardHelp.setVisible(
            not self.streamingWildcardHelp.isVisible()
        )

    def keep_index_selection(self):
        if not self.section_index.selectedItems():
            self.section_index.setCurrentItem(self.section_index.currentItem())

    def switch_page(self, page_name):
        pages_map = {
            translate("SettingsDialog", "Player"): self.page_general_player,
            translate("SettingsDialog", "Language"): self.page_general_language,
            translate("SettingsDialog", "Playlist"): self.page_defaults_playlist,
            translate("SettingsDialog", "Video"): self.page_defaults_video,
            translate("SettingsDialog", "Streaming"): self.page_misc_streaming,
            translate("SettingsDialog", "Logging"): self.page_misc_logging,
            translate("SettingsDialog", "Advanced"): self.page_misc_advanced,
        }

        if page_name is None:
            self.section_index.setCurrentRow(1)
            return

        page_widget = pages_map.get(page_name)

        if not page_widget:
            return

        self.section_page.setCurrentWidget(page_widget)

    def open_logfile(self):
        log_path = get_app_data_dir() / "gridplayer.log"

        self._log.debug(f"Opening log file {log_path}")

        if not log_path.is_file():
            return QCustomMessageBox.critical(
                self,
                translate("Dialog", "Error"),
                translate("Error", "Log file does not exist!"),
            )

        if env.IS_SNAP:
            # https://forum.snapcraft.io/t/xdg-open-or-gvfs-open-qdesktopservices-openurl-file-somelocation-file-txt-wont-open-the-file/16824
            subprocess.call(["xdg-open", log_path])  # noqa: S603, S607
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))

    def fill_logLevelVLC(self):
        log_levels = {
            log_config.DISABLED: translate("ErrorLevel", "None"),
            logging.ERROR: translate("ErrorLevel", "Error"),
            logging.WARNING: translate("ErrorLevel", "Warning"),
            logging.INFO: translate("ErrorLevel", "Info"),
            logging.DEBUG: translate("ErrorLevel", "Debug"),
        }

        _fill_combo_box(self.logLevelVLC, log_levels)

    def fill_logLevel(self):
        log_levels = {
            log_config.DISABLED: translate("ErrorLevel", "None"),
            logging.CRITICAL: translate("ErrorLevel", "Critical"),
            logging.ERROR: translate("ErrorLevel", "Error"),
            logging.WARNING: translate("ErrorLevel", "Warning"),
            logging.INFO: translate("ErrorLevel", "Info"),
            logging.DEBUG: translate("ErrorLevel", "Debug"),
        }

        _fill_combo_box(self.logLevel, log_levels)

    def fill_videoAspect(self):
        aspect_ratios = {
            VideoAspect.FIT: self.tr("Fit"),
            VideoAspect.STRETCH: self.tr("Stretch"),
            VideoAspect.NONE: self.tr("None"),
        }

        _fill_combo_box(self.videoAspect, aspect_ratios)

    def fill_repeatMode(self):
        repeat_modes = {
            VideoRepeat.SINGLE_FILE: self.tr("Single File"),
            VideoRepeat.DIR: self.tr("Directory"),
            VideoRepeat.DIR_SHUFFLE: self.tr("Directory (Shuffle)"),
        }

        _fill_combo_box(self.repeatMode, repeat_modes)

    def fill_gridMode(self):
        grid_modes = {
            GridMode.AUTO_ROWS: self.tr("Rows First"),
            GridMode.AUTO_COLS: self.tr("Columns First"),
        }

        _fill_combo_box(self.gridMode, grid_modes)

    def fill_playerVideoDriver(self):
        if env.IS_MACOS:
            video_drivers = {
                VideoDriver.VLC_HW_SP: "{0} <VLC {1}>".format(
                    self.tr("Hardware SP"), env.VLC_VERSION
                ),
                VideoDriver.VLC_SW: "{0} <VLC {1}>".format(
                    self.tr("Software"), env.VLC_VERSION
                ),
                VideoDriver.DUMMY: self.tr("Dummy"),
            }
        else:
            video_drivers = {
                VideoDriver.VLC_HW: "{0} <VLC {1}>".format(
                    self.tr("Hardware"), env.VLC_VERSION
                ),
                VideoDriver.VLC_HW_SP: "{0} <VLC {1}>".format(
                    self.tr("Hardware SP"), env.VLC_VERSION
                ),
                VideoDriver.VLC_SW: "{0} <VLC {1}>".format(
                    self.tr("Software"), env.VLC_VERSION
                ),
                VideoDriver.DUMMY: self.tr("Dummy"),
            }

        _fill_combo_box(self.playerVideoDriver, video_drivers)

    def fill_language(self):
        languages = {
            lang_id: {
                "language": QLocale(lang_id).nativeLanguageName().title(),
                "country": QLocale(lang_id).nativeCountryName().title(),
                "icon": f":/icons/flag_{lang_id}.svg",
                "author": lang["author"],
            }
            for lang_id, lang in SUPPORTED_LANGUAGES.items()
        }
        sorted_languages = dict(
            sorted(languages.items(), key=lambda x: x[1]["language"])
        )

        for lang_id, lang in sorted_languages.items():
            self.listLanguages.add_language_row(lang_id, lang)

    def fill_streamQuality(self):
        quality_codes = {
            "best": self.tr("Best"),
            "worst": self.tr("Worst"),
        }

        standard_quality_codes = [
            "2160p",
            "2160p60",
            "1440p",
            "1440p60",
            "1080p",
            "1080p60",
            "720p60",
            "720p",
            "480p",
            "360p",
            "240p",
            "144p",
        ]

        for code in standard_quality_codes:
            quality_codes[code] = code

        _fill_combo_box(self.streamQuality, quality_codes)

    def fill_playlistSeekSyncMode(self):
        seek_modes = {
            SeekSyncMode.DISABLED: self.tr("Disabled"),
            SeekSyncMode.PERCENT: self.tr("Percent"),
            SeekSyncMode.TIMECODE: self.tr("Timecode"),
        }

        _fill_combo_box(self.playlistSeekSyncMode, seek_modes)

    def fill_streamingResolverPriority(self):
        resolvers = {
            URLResolver.STREAMLINK: "Streamlink",
            URLResolver.YT_DLP: "yt-dlp",
            URLResolver.DIRECT: self.tr("Direct"),
        }

        _fill_combo_box(self.streamingResolverPriority, resolvers)

    def driver_selected(self, idx):
        driver_id = self.playerVideoDriver.itemData(idx)

        if driver_id in VIDEO_DRIVERS_MULTIPROCESS:
            self.playerVideoDriverPlayers.setDisabled(False)
        else:
            self.playerVideoDriverPlayers.setDisabled(True)

    def load_settings(self):
        elements_value_set_fun = {
            QCheckBox: lambda e, v: e.setChecked(v),
            QSpinBox: lambda e, v: e.setValue(v),
            QLineEdit: lambda e, v: e.setText(v),
            QComboBox: _set_combo_box,
            LanguageList: lambda e, v: e.setValue(v),
            ResolverPatternsList: lambda e, v: e.setDataRows(v),
        }

        for setting, element in self.settings_map.items():
            setting_value = Settings().get(setting)

            try:
                set_function = elements_value_set_fun[type(element)]
            except KeyError:
                raise ValueError(f"No element decoder for {setting}")

            set_function(element, setting_value)

    def save_settings(self):
        elements_value_read_attr = {
            QCheckBox: "isChecked",
            QSpinBox: "value",
            QLineEdit: "text",
            QComboBox: "currentData",
            LanguageList: "value",
            ResolverPatternsList: "rows_data",
        }

        for setting, element in self.settings_map.items():
            if not element.isEnabled():
                continue

            try:
                value_attr = elements_value_read_attr[type(element)]
            except KeyError:
                raise ValueError(f"No element decoder for {setting}")

            new_value = getattr(element, value_attr)()

            Settings().set(setting, new_value)

    def accept(self):
        self.save_settings()

        super().accept()
