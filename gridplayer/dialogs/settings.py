import contextlib
import logging
import subprocess

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import QCheckBox, QComboBox, QDialog, QLineEdit, QSpinBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.settings_dialog_ui import Ui_SettingsDialog
from gridplayer.params import env
from gridplayer.params.languages import LANGUAGES
from gridplayer.params.static import (
    AudioChannelMode,
    ColorScheme,
    DropAction,
    DropModifier,
    GridMode,
    SeekSyncMode,
    URLResolver,
    VideoAspect,
    VideoDriver,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.settings import Settings
from gridplayer.utils import log_config
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.keymap import default_keymap, merge_keymap
from gridplayer.utils.qt import qt_connect, translate
from gridplayer.widgets.keymap_tree_view import KeymapEditor
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
            "player/stay_on_top": self.playerStayOnTop,
            "player/start_maximized": self.playerStartMaximized,
            "player/start_fullscreen": self.playerStartFullscreen,
            "player/show_overlay_border": self.playerShowOverlayBorder,
            "player/color_scheme": self.playerColorScheme,
            "player/language": self.listLanguages,
            "player/keymap": self.keymapEditor,
            "player/recent_list_enabled": self.playerRecentList,
            "player/recent_list_max_size": self.playerRecentListSize,
            "playlist/grid_mode": self.gridMode,
            "playlist/grid_fit": self.gridFit,
            "playlist/grid_size": self.gridSize,
            "playlist/shuffle_on_load": self.gridShuffleOnLoad,
            "playlist/drop_action_internal": self.dropActionInternal,
            "playlist/drop_action_external": self.dropActionExternal,
            "playlist/drop_modifier": self.dropModifier,
            "playlist/save_position": self.playlistSavePosition,
            "playlist/save_state": self.playlistSaveState,
            "playlist/save_window": self.playlistSaveWindow,
            "playlist/seek_sync_mode": self.playlistSeekSyncMode,
            "playlist/track_changes": self.playlistTrackChanges,
            "playlist/disable_mouse_click_events": self.playlistDisableClickEvents,
            "playlist/disable_mouse_wheel_events": self.playlistDisableWheelEvents,
            "playlist/disable_overlay": self.playlistDisableOverlay,
            "video_defaults/aspect": self.videoAspect,
            "video_defaults/transform": self.videoTransform,
            "video_defaults/repeat": self.repeatMode,
            "video_defaults/audio_mode": self.videoAudioMode,
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
            "internal/force_native_drag_events": self.miscForceNativeDragEvents,
            "streaming/hls_via_streamlink": self.streamingHLSVIAStreamlink,
            "streaming/resolver_priority": self.streamingResolverPriority,
            "streaming/resolver_priority_patterns": self.streamingResolverPriorityPatterns,
        }

        self.ui_customize()
        self.ui_fill()

        self.ui_connect()
        self.ui_set_limits()

        self.load_settings()

        self.ui_customize_dynamic()

    def ui_customize(self):
        for btn in self.buttonBox.buttons():
            btn.setIcon(QIcon())

        self.ui_customize_section_index()

        _set_groupbox_header_bold(self.playerVideoDriverBox)

        if env.IS_LINUX:
            self.playerStayOnTop.hide()

        if not env.IS_LINUX:
            self.section_misc.hide()
            self.miscOpaqueHWOverlay.hide()
            self.miscFakeOverlayInvisibility.hide()
            self.miscForceNativeDragEvents.hide()

    def ui_customize_section_index(self):
        font = self.section_index.font()
        font.setPixelSize(16)
        self.section_index.setFont(font)

    def ui_fill(self):
        self.fill_playerVideoDriver()
        self.fill_gridMode()
        self.fill_dropActionInternal()
        self.fill_dropActionExternal()
        self.fill_dropModifier()
        self.fill_videoAspect()
        self.fill_videoTransform()
        self.fill_repeatMode()
        self.fill_logLevel()
        self.fill_logLevelVLC()
        self.fill_language()
        self.fill_colorScheme()
        self.fill_streamQuality()
        self.fill_playlistSeekSyncMode()
        self.fill_streamingResolverPriority()
        self.fill_videoAudioMode()

    def ui_set_limits(self):
        self.playerVideoDriverPlayers.setRange(1, MAX_VLC_PROCESSES)
        self.timeoutOverlay.setRange(1, 60)
        self.timeoutMouseHide.setRange(1, 60)
        self.logLimitSize.setRange(1, 1024 * 1024)
        self.logLimitBackups.setRange(1, 1000)
        self.timeoutVideoInit.setRange(1, 1000)
        self.playerRecentListSize.setRange(1, 100)

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
        self.playerRecentListSize.setEnabled(self.playerRecentList.isChecked())

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
            (self.playerRecentList.stateChanged, self.playerRecentListSize.setEnabled),
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
            translate("SettingsDialog", "Shortcuts"): self.page_general_shortcuts,
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
            subprocess.call(["xdg-open", log_path])
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

    def fill_videoTransform(self):
        transform_options = {
            VideoTransform.ROTATE_90: self.tr("Rotate 90"),
            VideoTransform.ROTATE_180: self.tr("Rotate 180"),
            VideoTransform.ROTATE_270: self.tr("Rotate 270"),
            VideoTransform.HFLIP: self.tr("Flip Horizontally"),
            VideoTransform.VFLIP: self.tr("Flip Vertically"),
            VideoTransform.TRANSPOSE: self.tr("Transpose"),
            VideoTransform.ANTITRANSPOSE: self.tr("Anti-transpose"),
            VideoTransform.NONE: self.tr("No Transform"),
        }

        _fill_combo_box(self.videoTransform, transform_options)

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

    def fill_dropActionInternal(self):
        actions = {
            DropAction.INSERT: self.tr("Move / Swap"),
            DropAction.REPLACE: self.tr("Replace"),
        }
        _fill_combo_box(self.dropActionInternal, actions)

    def fill_dropActionExternal(self):
        actions = {
            DropAction.INSERT: self.tr("Add"),
            DropAction.REPLACE: self.tr("Replace"),
        }
        _fill_combo_box(self.dropActionExternal, actions)

    def fill_dropModifier(self):
        # DropModifier.CTRL is Qt.ControlModifier: Ctrl on Win/Linux, Cmd on macOS.
        # Qt.MetaModifier is the Mac Control key — do not use that label here.
        if env.IS_MACOS:
            modifiers = {
                DropModifier.SHIFT: self.tr("Shift"),
                DropModifier.CTRL: self.tr("Cmd"),
                DropModifier.ALT: self.tr("Option"),
                DropModifier.NONE: self.tr("Disabled"),
            }
        else:
            modifiers = {
                DropModifier.SHIFT: self.tr("Shift"),
                DropModifier.CTRL: self.tr("Ctrl"),
                DropModifier.ALT: self.tr("Alt"),
                DropModifier.NONE: self.tr("Disabled"),
            }
        _fill_combo_box(self.dropModifier, modifiers)
        if env.IS_LINUX:
            # GNOME/Files only exposes Shift to this X11 window. Don't hide Ctrl/Alt:
            # they work inside the player, and on KDE for file-manager drops too.
            hint = self.tr(
                "On GNOME, dropping files from the file manager only honors Shift. "
                "Ctrl and Alt still work when dragging videos inside the player."
            )
            self.dropModifier.setToolTip(hint)
            self.dropModifierLabel.setToolTip(hint)

    def fill_playerVideoDriver(self):
        if env.IS_MACOS:
            video_drivers = {
                VideoDriver.VLC_HW_SP: f"{self.tr('Hardware SP')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_SW: f"{self.tr('Software')} <VLC {env.VLC_VERSION}>",
                VideoDriver.DUMMY: self.tr("Dummy"),
            }
        else:
            video_drivers = {
                VideoDriver.VLC_HW: f"{self.tr('Hardware')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_HW_SP: f"{self.tr('Hardware SP')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_SW: f"{self.tr('Software')} <VLC {env.VLC_VERSION}>",
                VideoDriver.DUMMY: self.tr("Dummy"),
            }

        _fill_combo_box(self.playerVideoDriver, video_drivers)

    def fill_language(self):
        for language in LANGUAGES:
            self.listLanguages.add_language_row(language)

    def fill_colorScheme(self):
        schemes = {
            ColorScheme.SYSTEM: self.tr("System"),
            ColorScheme.LIGHT: self.tr("Light"),
            ColorScheme.DARK: self.tr("Dark"),
        }

        _fill_combo_box(self.playerColorScheme, schemes)

    def fill_streamQuality(self):
        quality_codes = {
            "best": self.tr("Best"),
            "worst": self.tr("Worst"),
            "best_audio_only": self.tr("Best (Audio Only)"),
            "worst_audio_only": self.tr("Worst (Audio Only)"),
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

        quality_codes.update({code: code for code in standard_quality_codes})

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

    def fill_videoAudioMode(self):
        modes = {
            AudioChannelMode.UNSET: translate("Audio Mode", "Original"),
            AudioChannelMode.STEREO: translate("Audio Mode", "Stereo"),
            AudioChannelMode.RSTEREO: translate("Audio Mode", "Reverse Stereo"),
            AudioChannelMode.LEFT: translate("Audio Mode", "Left"),
            AudioChannelMode.RIGHT: translate("Audio Mode", "Right"),
            AudioChannelMode.DOLBYS: translate("Audio Mode", "Dolby Surround"),
            AudioChannelMode.HEADPHONES: translate("Audio Mode", "Headphones"),
            AudioChannelMode.MONO: translate("Audio Mode", "Mono"),
        }

        _fill_combo_box(self.videoAudioMode, modes)

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
            KeymapEditor: lambda e, v: e.set_bindings(
                merge_keymap(default_keymap(), v)
            ),
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
            KeymapEditor: "get_sparse_bindings",
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
