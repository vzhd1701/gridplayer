import contextlib
import logging
import subprocess

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.settings_dialog_ui import Ui_SettingsDialog
from gridplayer.params import env
from gridplayer.params.defaults_fields import PLAYLIST_FIELDS, VIDEO_FIELDS
from gridplayer.params.languages import LANGUAGES
from gridplayer.params.static import (
    ColorScheme,
    HWCropBorderOffset,
    URLResolver,
    VideoDriver,
)
from gridplayer.settings import Settings
from gridplayer.utils import log_config
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.cookies import cookie_store, same_cookies
from gridplayer.utils.keymap import default_keymap, merge_keymap
from gridplayer.utils.qt import qt_connect, translate
from gridplayer.version import __app_url__
from gridplayer.widgets.defaults_form import DefaultsForm
from gridplayer.widgets.keymap_tree_view import KeymapEditor
from gridplayer.widgets.language_list import LanguageList
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList

VIDEO_DRIVERS_MULTIPROCESS = (
    VideoDriver.VLC_SW,
    VideoDriver.VLC_HW,
)

MAX_VLC_PROCESSES = 64

COOKIES_FAQ_URL = (
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
)
COOKIES_README_URL = f"{__app_url__}#streaming-cookies"

# where each entry in the section index keeps the page it opens
SECTION_PAGE_ROLE = Qt.UserRole


def _fill_combo_box(combo_box, values_dict):
    for i_id, i_name in values_dict.items():
        combo_box.addItem(i_name, i_id)


def _set_combo_box(combo_box, data_value):
    idx = combo_box.findData(data_value)
    combo_box.setCurrentIndex(idx)


def _replace_scroll_page(scroll, form):
    old = scroll.takeWidget()
    if old is not None:
        old.deleteLater()
    scroll.setWidget(form)


def _replace_layout_page(page, form):
    layout = page.layout()
    if layout is None:
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
    else:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
    layout.addWidget(form)


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
            "player/inhibit_screensaver": self.playerInhibitScreensaver,
            "player/one_instance": self.playerOneInstance,
            "player/stay_on_top": self.playerStayOnTop,
            "player/start_maximized": self.playerStartMaximized,
            "player/start_fullscreen": self.playerStartFullscreen,
            "player/color_scheme": self.playerColorScheme,
            "player/language": self.listLanguages,
            "player/keymap": self.keymapEditor,
            "player/recent_list_enabled": self.playerRecentList,
            "player/recent_list_max_size": self.playerRecentListSize,
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
            "internal/hw_crop_border_offset": self.miscHWCropBorder,
            "streaming/hls_via_streamlink": self.streamingHLSVIAStreamlink,
            "streaming/resolver_priority": self.streamingResolverPriority,
            "streaming/resolver_priority_patterns": self.streamingResolverPriorityPatterns,
            "cookies/enabled": self.cookiesEnabled,
            "cookies/allow_update": self.cookiesAllowUpdate,
        }

        self.ui_customize()
        self.ui_fill()

        self.ui_connect()
        self.ui_set_limits()

        self.load_settings()

        self.ui_customize_dynamic()

    def ui_customize(self):
        self.ui_customize_section_index()

        _set_groupbox_header_bold(self.playerVideoDriverBox)

        self.playlist_defaults_form = DefaultsForm(PLAYLIST_FIELDS, show_reset=False)
        self.video_defaults_form = DefaultsForm(VIDEO_FIELDS, show_reset=False)
        _replace_scroll_page(self.page_defaults_playlist, self.playlist_defaults_form)
        _replace_scroll_page(self.page_defaults_video, self.video_defaults_form)

        if env.IS_LINUX:
            self.playerStayOnTop.hide()

        if not env.IS_LINUX:
            self.miscOpaqueHWOverlay.hide()
            self.miscFakeOverlayInvisibility.hide()
            self.miscForceNativeDragEvents.hide()

    def ui_customize_section_index(self):
        font = self.section_index.font()
        font.setPixelSize(16)
        self.section_index.setFont(font)

        self.bind_section_pages()

    def bind_section_pages(self):
        """Tie every entry in the index to the page it opens.

        Going by the entry's text would mean matching a translated string
        against another one, which stops matching the moment either side
        is reworded and leaves a section that quietly opens nothing.
        """

        pages = (
            self.page_general_player,
            self.page_general_shortcuts,
            self.page_general_language,
            self.page_defaults_playlist,
            self.page_defaults_video,
            self.page_streaming_resolution,
            self.page_streaming_cookies,
            self.page_advanced_decoder,
            self.page_advanced_logging,
        )

        sections = self.section_items

        if len(sections) != len(pages):
            raise ValueError(
                f"{len(sections)} section(s) in the index"
                f" but {len(pages)} page(s) to open"
            )

        for item, page in zip(sections, pages):
            item.setData(SECTION_PAGE_ROLE, page)

    @property
    def section_items(self):
        """The entries that open a page, leaving out the group headings."""

        items = (
            self.section_index.item(row) for row in range(self.section_index.count())
        )

        return [item for item in items if item.flags() & Qt.ItemIsSelectable]

    def ui_fill(self):
        self.fill_playerVideoDriver()
        self.fill_logLevel()
        self.fill_logLevelVLC()
        self.fill_language()
        self.fill_colorScheme()
        self.fill_streamingResolverPriority()
        self.fill_hwCropBorder()

    def ui_set_limits(self):
        self.playerVideoDriverPlayers.setRange(1, MAX_VLC_PROCESSES)
        self.timeoutMouseHide.setRange(1, 60)
        self.logLimitSize.setRange(1, 1024 * 1024)
        self.logLimitBackups.setRange(1, 1000)
        self.timeoutVideoInit.setRange(1, 1000)
        self.playerRecentListSize.setRange(1, 100)

    def ui_customize_dynamic(self):
        self.driver_selected(self.playerVideoDriver.currentIndex())
        self.timeoutMouseHide.setEnabled(self.timeoutMouseHideFlag.isChecked())
        self.logLimitSize.setEnabled(self.logLimit.isChecked())
        self.logLimitBackups.setEnabled(self.logLimit.isChecked())
        self.streamingWildcardHelp.setVisible(False)
        self.playerRecentListSize.setEnabled(self.playerRecentList.isChecked())

        self.switch_page(None)
        self.adjustSize()

    def ui_connect(self):
        qt_connect(
            (self.playerVideoDriver.currentIndexChanged, self.driver_selected),
            (self.timeoutMouseHideFlag.stateChanged, self.timeoutMouseHide.setEnabled),
            (self.logFileOpen.clicked, self.open_logfile),
            (self.section_index.currentItemChanged, self.switch_page),
            (self.section_index.itemSelectionChanged, self.keep_index_selection),
            (self.logLimit.stateChanged, self.logLimitSize.setEnabled),
            (self.logLimit.stateChanged, self.logLimitBackups.setEnabled),
            (self.streamingWildcardHelpButton.clicked, self.toggle_wildcard_help),
            (self.playerRecentList.stateChanged, self.playerRecentListSize.setEnabled),
            (self.cookiesList.error, self.cookie_import_failed),
            (self.cookiesHowToButton.clicked, self.show_cookies_howto),
        )

    def cookie_import_failed(self, message):
        QCustomMessageBox.critical(self, translate("Dialog", "Error"), message)

    def toggle_wildcard_help(self):
        self.streamingWildcardHelp.setVisible(
            not self.streamingWildcardHelp.isVisible()
        )

    def show_cookies_howto(self):
        """Explain the export in a box of its own.

        The Cookies page is mostly table, and the table stops being a
        table below about 125px. A procedure long enough to be worth
        reading does not fit in what is left, and translations run
        longer than the English it would have been measured against.
        """

        howto = translate(
            "SettingsDialog - Cookies",
            "<p>Export from a private window, and close it when you are"
            " done:</p>"
            "<ol>"
            "<li>Open a private browsing window and log in to the site.</li>"
            "<li>In the same tab, go to a page that will not keep talking to"
            " the site, such as <tt>/robots.txt</tt>.</li>"
            "<li>Export the site's cookies with a cookies.txt browser"
            " extension.</li>"
            "<li>Close the window <b>without logging out</b>. Logging out kills"
            " the session you just exported.</li>"
            "<li>Import the file here, or paste it.</li>"
            "</ol>"
            "<p>Sites like YouTube rotate cookies on open tabs. Export from"
            " your normal session, keep browsing, and your copy goes stale,"
            " usually within hours. A private window you never reopen has"
            " nothing left to rotate them.</p>"
            '<p><a href="{README}">Full instructions</a> &middot;'
            ' <a href="{FAQ}">yt-dlp FAQ</a></p>',
        ).format(README=COOKIES_README_URL, FAQ=COOKIES_FAQ_URL)

        QCustomMessageBox.information(
            self,
            translate("SettingsDialog - Cookies", "How to export cookies"),
            howto,
        )

    def keep_index_selection(self):
        if not self.section_index.selectedItems():
            self.section_index.setCurrentItem(self.section_index.currentItem())

    def switch_page(self, section_item, _previous=None):
        if section_item is None:
            self.section_index.setCurrentItem(self.section_items[0])
            return

        page = section_item.data(SECTION_PAGE_ROLE)

        if page is None:
            return

        self.section_page.setCurrentWidget(page)

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

    def fill_playerVideoDriver(self):
        if env.IS_MACOS:
            video_drivers = {
                VideoDriver.VLC_HW_SP: f"{self.tr('Hardware SP')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_SW: f"{self.tr('Software')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_SW_SP: f"{self.tr('Software SP')} <VLC {env.VLC_VERSION}>",
                VideoDriver.DUMMY: self.tr("Dummy"),
            }
        else:
            video_drivers = {
                VideoDriver.VLC_HW: f"{self.tr('Hardware')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_HW_SP: f"{self.tr('Hardware SP')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_SW: f"{self.tr('Software')} <VLC {env.VLC_VERSION}>",
                VideoDriver.VLC_SW_SP: f"{self.tr('Software SP')} <VLC {env.VLC_VERSION}>",
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

    def fill_streamingResolverPriority(self):
        resolvers = {
            URLResolver.STREAMLINK: "Streamlink",
            URLResolver.YT_DLP: "yt-dlp",
            URLResolver.DIRECT: self.tr("Direct"),
        }

        _fill_combo_box(self.streamingResolverPriority, resolvers)

    def fill_hwCropBorder(self):
        values = {
            HWCropBorderOffset.AUTO: self.tr("Auto"),
            HWCropBorderOffset.DISABLED: self.tr("Disabled"),
            HWCropBorderOffset.PX2: self.tr("2 px"),
            HWCropBorderOffset.PX4: self.tr("4 px"),
            HWCropBorderOffset.PX6: self.tr("6 px"),
            HWCropBorderOffset.PX8: self.tr("8 px"),
            HWCropBorderOffset.PX10: self.tr("10 px"),
            HWCropBorderOffset.PX12: self.tr("12 px"),
        }

        _fill_combo_box(self.miscHWCropBorder, values)

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

        defaults = {
            spec.settings_key: Settings().get(spec.settings_key)
            for spec in (*PLAYLIST_FIELDS, *VIDEO_FIELDS)
        }
        self.playlist_defaults_form.set_values(defaults)
        self.video_defaults_form.set_values(defaults)

        self.cookiesList.set_jar(cookie_store().jar)

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

        form_values = {
            **self.playlist_defaults_form.values(),
            **self.video_defaults_form.values(),
        }
        for key, value in form_values.items():
            if not (
                self.playlist_defaults_form.is_enabled(key)
                or self.video_defaults_form.is_enabled(key)
            ):
                continue
            Settings().set(key, value)

        self.save_cookies()

    def save_cookies(self):
        """Put the jar the page is showing on the disk.

        Left until now on purpose: an import or a removal is staged in
        the widget, so Cancel undoes it the way it undoes anything else
        in this dialog.
        """

        store = cookie_store()
        jar = self.cookiesList.jar

        if jar is None:
            if not store.is_empty:
                store.clear()
            return

        if not same_cookies(jar, store.jar):
            store.save(jar)

    def accept(self):
        self.save_settings()

        super().accept()
