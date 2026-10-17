import contextlib
import logging
import subprocess
import threading

from PyQt5.QtCore import QLocale, QSize, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QIcon, QPainter
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.checkup import CheckupDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.settings_draft import SettingsMode, SetValue
from gridplayer.params import env
from gridplayer.params.settings_fields.kinds import Page
from gridplayer.params.settings_pages import PAGES
from gridplayer.params.static import CacheMode
from gridplayer.params.theme import set_secondary
from gridplayer.settings import Settings, default_value
from gridplayer.utils import cache
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.cookies import cookie_store, same_cookies
from gridplayer.utils.network import opts_for
from gridplayer.utils.qt import translate
from gridplayer.utils.screenshots import unknown_specifiers
from gridplayer.version import __app_url__
from gridplayer.widgets.cookie_store_list import CookieStoreList
from gridplayer.widgets.custom_menu import CustomMenu
from gridplayer.widgets.settings_current_page_stack import CurrentPageStackedWidget
from gridplayer.widgets.settings_form import SettingsForm
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea

COOKIES_FAQ_URL = (
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
)
COOKIES_README_URL = f"{__app_url__}#streaming-cookies"

# where each entry in the section index keeps the page it opens
SECTION_PAGE_ROLE = Qt.UserRole

# a button that is only an icon, as small as the icon lets it be
ICON_BUTTON_SIZE = QSize(24, 24)

# the index: its entries, and the group headings over them
INDEX_ITEM_PX = 13
INDEX_ITEM_HEIGHT = 28
INDEX_HEADING_PX = 11
# room over a heading, to set its group apart from the one before
INDEX_HEADING_HEIGHT = 34

PAGE_TITLE_PX = 16
SCROLL_BAR_GAP = 8
PAGE_TITLE_ICON_PX = 20
NOTE_ICON_PX = 16


class _Icon(QWidget):
    """An icon of the theme, drawn as the theme is now, light or dark."""

    def __init__(self, name: str, size: int):
        super().__init__()
        self._icon = QIcon.fromTheme(name)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        self._icon.paint(QPainter(self), self.rect())


def _with_note(form, text):
    """A page with something said at the top of it.

    Not a tooltip on any one row, because what it says is true of the
    whole page. At the top rather than the bottom because the page is
    longer than it is tall and the bottom of it is behind a scroll.
    """

    page = QWidget()

    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    note = QLabel(text)
    note.setWordWrap(True)
    note.setOpenExternalLinks(True)
    set_secondary(note)

    line = QHBoxLayout()
    line.setSpacing(8)
    line.addWidget(_Icon("information", NOTE_ICON_PX), 0, Qt.AlignTop)
    line.addWidget(note, 1)

    layout.addLayout(line)
    layout.addWidget(form)

    return page


def _page_title(page: Page) -> QWidget:
    title = QLabel(page.title)
    font = title.font()
    font.setPixelSize(PAGE_TITLE_PX)
    font.setBold(True)
    title.setFont(font)

    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(2, 0, 0, 0)
    line.setSpacing(8)
    if page.icon is not None:
        line.addWidget(_Icon(page.icon, PAGE_TITLE_ICON_PX))
    line.addWidget(title, 1)

    return holder


def _help_button(text=None):
    """A question mark, and what it explains beside it if there is room:
    flat then, as a link would be."""

    button = QPushButton(QIcon.fromTheme("question"), text or "")
    if text:
        button.setFlat(True)
    else:
        button.setFixedSize(ICON_BUTTON_SIZE)
    return button


def _in_a_row(*widgets, right=False):
    """Widgets on a line, on the left of it or on the right; a None between
    them pushes the rest to the right."""

    row = QWidget()

    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    if right:
        layout.addStretch(1)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        else:
            layout.addWidget(widget)
    if not right and None not in widgets:
        layout.addStretch(1)

    return row


class SettingsDialog(QDialog):
    """The pages of gridplayer.params.settings_pages, each one a SettingsForm.

    What is here is what a page can't say for itself: the buttons and lists
    that aren't settings (the Slots), and the few settings that lean on each
    other in a way a rule can't put.
    """

    # what the cache comes to, worked out on a thread of its own
    cache_measured = pyqtSignal(object)

    def __init__(self, parent):
        super().__init__(parent)

        self._log = logging.getLogger(self.__class__.__name__)

        # every page by its id, as it sits in the stack, and the form on it
        self.pages: dict[str, QWidget] = {}
        self.forms: dict[str, SettingsForm] = {}
        # the page each setting is on, by id
        self._page_id_of: dict[str, str] = {}
        self._index_items: dict[str, QListWidgetItem] = {}
        self._form_on: dict[QWidget, SettingsForm] = {}

        # minimize's own tick, while hiding from the taskbar ticks it for it
        self._minimize_to_tray_own = None

        self.ui_build()
        self.ui_connect()

        self.load_settings()

        self.measure_cache()
        self.switch_page(None)
        self.adjustSize()

    # building

    def ui_build(self):
        self.setWindowTitle(translate("SettingsDialog", "Settings"))
        self.setSizeGripEnabled(True)
        self.setModal(True)

        self.section_index = QListWidget()
        # by name in the theme's style sheet, which draws the group headings,
        # disabled so they can't be picked, in the text color rather than grey
        self.section_index.setObjectName("section_index")
        self.section_index.setMinimumSize(QSize(200, 350))
        self.section_index.setMaximumWidth(200)
        self.section_index.setIconSize(QSize(16, 16))
        font = self.section_index.font()
        font.setPixelSize(INDEX_ITEM_PX)
        self.section_index.setFont(font)

        self.section_page = CurrentPageStackedWidget(min_width=500)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self.section_index)
        body.addWidget(self.section_page)

        self.dataDirOpen = QPushButton(
            QIcon.fromTheme("show-in-folder"),
            translate("SettingsDialog", "Open data folder"),
        )
        self.dataDirOpen.setMinimumWidth(130)
        self.dataDirOpen.setToolTip(
            translate(
                "SettingsDialog",
                "Holds the log, settings and cookies. You can also put a JavaScript"
                " runtime here.",
            )
        )

        self.resetPage = QPushButton(
            QIcon.fromTheme("reset"), translate("SettingsDialog", "Reset Page")
        )
        self.resetPage.setToolTip(
            translate("SettingsDialog", "Put the settings on this page back to default")
        )

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        buttons = QHBoxLayout()
        buttons.addWidget(self.dataDirOpen)
        buttons.addWidget(self.resetPage)
        buttons.addWidget(self.buttonBox, 1)

        root = QVBoxLayout(self)
        root.addLayout(body, 1)
        root.addLayout(buttons)

        # the pages last, built where they go: a widget moved under another
        # parent is styled over again, all of it, and the pages are most of
        # what the dialog has
        self._build_index()

    def _build_index(self):
        heading_font = self.section_index.font()
        heading_font.setBold(True)
        heading_font.setPixelSize(INDEX_HEADING_PX)

        slots = self._slots()

        for group_index, group in enumerate(PAGES):
            # small and in capitals: a heading over entries, not one of them
            heading = QListWidgetItem(group.title.upper(), self.section_index)
            heading.setFont(heading_font)
            heading.setFlags(Qt.NoItemFlags)
            heading.setTextAlignment(Qt.AlignLeft | Qt.AlignBottom)
            height = INDEX_ITEM_HEIGHT if group_index == 0 else INDEX_HEADING_HEIGHT
            heading.setSizeHint(QSize(0, height))

            for page in group.pages:
                item = QListWidgetItem(page.title, self.section_index)
                if page.icon is not None:
                    item.setIcon(QIcon.fromTheme(page.icon))
                item.setSizeHint(QSize(0, INDEX_ITEM_HEIGHT))
                item.setData(SECTION_PAGE_ROLE, self._build_page(page, slots))
                self._index_items[page.id] = item

    def _build_page(self, page: Page, slots) -> QWidget:
        form = SettingsForm(
            page.items,
            reset_to=default_value,
            mode=SettingsMode.DEFAULTS,
            slots=slots,
        )

        self.forms[page.id] = form
        for key in form.keys():
            self._page_id_of[key] = page.id

        content = form if page.note is None else _with_note(form, page.note)

        # the title over what scrolls, so it stays in view
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(_page_title(page))
        self.section_page.addWidget(widget)

        if page.scroll:
            # clear of the scroll bar
            content.layout().setContentsMargins(0, 0, SCROLL_BAR_GAP, 0)
            scroll = PageScrollArea()
            layout.addWidget(scroll, 1)
            scroll.setWidget(content)
        else:
            layout.addWidget(content, 1)

        widget.setObjectName(f"page_{page.id}")

        self.pages[page.id] = widget
        self._form_on[widget] = form

        return widget

    def _slots(self):
        """What fills each Slot of the pages: _slot_<name>."""

        return {
            name.removeprefix("_slot_"): getattr(self, name)
            for name in dir(type(self))
            if name.startswith("_slot_")
        }

    def _slot_tray_unavailable(self):
        self.playerTrayUnavailable = QLabel(
            translate("SettingsDialog", "Your desktop has no tray.")
        )
        self.playerTrayUnavailable.setVisible(
            not QSystemTrayIcon.isSystemTrayAvailable()
        )
        return self.playerTrayUnavailable

    def _slot_cache_clear(self):
        self.cacheClear = QToolButton()
        self.cacheClear.setIcon(QIcon.fromTheme("trash"))
        self.cacheClear.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.cacheClear.setText(translate("SettingsDialog", "Clear"))
        self.cacheClear.setPopupMode(QToolButton.MenuButtonPopup)
        self.cacheClear.setToolTip(
            translate(
                "SettingsDialog", "Delete everything in the cache folder:\n{FOLDER}"
            ).format(FOLDER=cache.cache_root())
        )
        self.cacheClear.clicked.connect(self.clear_cache)

        # the folder it is in, opened from the arrow beside Clear
        cache_menu = CustomMenu(parent=self.cacheClear)
        self.cache_open_action = cache_menu.addAction(
            QIcon.fromTheme("show-in-folder"),
            translate("SettingsDialog", "Open Folder"),
            self.open_cache_dir,
        )
        self.cacheClear.setMenu(cache_menu)

        self.cacheSize = QLabel()

        return _in_a_row(self.cacheSize, None, self.cacheClear)

    def _slot_screenshot_template_help(self):
        self.screenshotsFilenameTemplateHelpButton = _help_button()
        self.screenshotsFilenameTemplateHelpButton.setToolTip(
            translate("SettingsDialog", "Screenshot file name format")
        )
        self.screenshotsFilenameTemplateHelpButton.clicked.connect(
            self.show_screenshot_template_help
        )
        return self.screenshotsFilenameTemplateHelpButton

    def _slot_youtube_test(self):
        self.streamingTestButton = QPushButton(
            QIcon.fromTheme("checkup"),
            translate("SettingsDialog", "Test a YouTube link"),
        )
        self.streamingTestButton.setToolTip(
            translate(
                "SettingsDialog",
                "Open a YouTube link step by step and show which step fails",
            )
        )
        self.streamingTestButton.clicked.connect(self.run_youtube_checkup)
        return _in_a_row(self.streamingTestButton, right=True)

    def _slot_wildcard_help(self):
        self.streamingWildcardHelpButton = _help_button(
            translate("SettingsDialog", "Wildcard syntax")
        )
        self.streamingWildcardHelpButton.clicked.connect(self.toggle_wildcard_help)

        self.streamingWildcardHelp = QLabel(
            translate(
                "SettingsDialog",
                "<p><b>The asterisk</b> * matches zero or more characters.<br>\n"
                "<b>The question mark</b> ? matches exactly one character.</p>\n"
                "<p><i>For Host Wildcard only:</i><br>\n"
                "*.example.com will match both example.com and www.example.com<br>\n"
                "**.example.com will match subdomains <b>only</b></p>",
            )
        )
        self.streamingWildcardHelp.setVisible(False)

        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_in_a_row(self.streamingWildcardHelpButton))
        layout.addWidget(self.streamingWildcardHelp)

        return holder

    def _slot_cookies_list(self):
        self.cookiesList = CookieStoreList()
        self.cookiesList.error.connect(self.cookie_import_failed)
        return self.cookiesList

    def _slot_cookies_howto(self):
        self.cookiesHowToButton = _help_button(
            translate("SettingsDialog", "How to export cookies")
        )
        self.cookiesHowToButton.clicked.connect(self.show_cookies_howto)

        return _in_a_row(self.cookiesHowToButton)

    def _slot_network_test(self):
        self.networkTestButton = QPushButton(
            QIcon.fromTheme("checkup"), translate("SettingsDialog", "Test network")
        )
        self.networkTestButton.setToolTip(
            translate(
                "SettingsDialog",
                "Test these settings on a real link and show which step fails",
            )
        )
        self.networkTestButton.clicked.connect(self.run_network_checkup)
        return _in_a_row(self.networkTestButton, right=True)

    def ui_connect(self):
        self.section_index.currentItemChanged.connect(self.switch_page)
        self.section_index.itemSelectionChanged.connect(self.keep_index_selection)

        self.dataDirOpen.clicked.connect(self.open_data_dir)
        self.resetPage.clicked.connect(self.reset_page)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.cache_measured.connect(self.show_cache_size)

        for form in self.forms.values():
            form.values_changed.connect(self.update_reset_page)

        self.form_of("player/tray_icon").values_changed.connect(
            self.tray_options_changed
        )
        self.form_of("cache/mode").values_changed.connect(self.cache_mode_selected)

    # the settings, wherever they are

    def form_of(self, key: str) -> SettingsForm:
        return self.forms[self._page_id_of[key]]

    def widget(self, key: str) -> QWidget:
        """What a setting is edited with."""

        return self.form_of(key).widget(key)

    def value(self, key: str):
        """A setting as the page has it now, saved or not."""

        return self.form_of(key).value(key)

    # pages

    @property
    def section_items(self):
        """The entries that open a page, leaving out the group headings."""

        items = (
            self.section_index.item(row) for row in range(self.section_index.count())
        )

        return [item for item in items if item.flags() & Qt.ItemIsSelectable]

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
        self.update_reset_page()

    def show_page(self, page_id: str):
        self.section_index.setCurrentItem(self._index_items[page_id])

    def show_page_of(self, key: str):
        self.show_page(self._page_id_of[key])

    @property
    def current_form(self) -> SettingsForm | None:
        return self._form_on.get(self.section_page.currentWidget())

    def update_reset_page(self, *_):
        form = self.current_form
        self.resetPage.setEnabled(form is not None and form.has_modified())

    def reset_page(self):
        """The page back to the factory defaults, until Cancel."""

        form = self.current_form
        if form is None:
            return

        if (
            form is self.form_of("player/minimize_to_tray")
            and self._minimize_to_tray_own is not None
        ):
            # ticked for hiding from the taskbar: let go of first, to be reset
            # and saved with the rest, and ticked again by tray_options_changed
            # if it still has to be
            self._minimize_to_tray_own = None
            form.lock("player/minimize_to_tray", False)

        form.reset_all()

    # settings that lean on each other

    def tray_options_changed(self, *_):
        form = self.form_of("player/tray_icon")

        is_tray = form.is_enabled("player/tray_icon") and form.value("player/tray_icon")

        # with no taskbar button, minimizing can only go to the tray
        is_forced = bool(
            is_tray
            and form.is_available("player/hide_taskbar")
            and form.value("player/hide_taskbar")
        )

        minimize = form.widget("player/minimize_to_tray")

        if is_forced and self._minimize_to_tray_own is None:
            self._minimize_to_tray_own = minimize.isChecked()
            minimize.setChecked(True)
        elif not is_forced and self._minimize_to_tray_own is not None:
            own, self._minimize_to_tray_own = self._minimize_to_tray_own, None
            minimize.setChecked(own)

        # a locked one is left as it is on save, see save_settings
        form.lock("player/minimize_to_tray", is_forced)

    def cache_mode_selected(self, *_):
        # nothing on disk to see, kept in memory
        self.cache_open_action.setEnabled(self.value("cache/mode") == CacheMode.DISK)

    # loading and saving

    def load_settings(self):
        for form in self.forms.values():
            form.set_values({key: Settings().get(key) for key in form.keys()})

        self.cookiesList.set_jar(cookie_store().jar)

        self.tray_options_changed()
        self.cache_mode_selected()
        self.update_reset_page()

    def save_settings(self):
        for form in self.forms.values():
            for key, change in form.persistence_result().items():
                if isinstance(change, SetValue):
                    Settings().set(key, change.value)
                else:
                    Settings().reset(key)

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

    def is_screenshot_template_valid(self):
        template = self.widget("screenshots/filename_template")

        unknown = unknown_specifiers(template.text())

        if not unknown:
            return True

        QCustomMessageBox.warning(
            self,
            translate("SettingsDialog", "Screenshots"),
            translate(
                "SettingsDialog", "Unknown specifiers in the file name: {SPECIFIERS}"
            ).format(SPECIFIERS=", ".join(unknown)),
            info=translate("SettingsDialog", "Write %% for a percent sign."),
        )

        self.show_page_of("screenshots/filename_template")
        template.setFocus()

        return False

    def accept(self):
        if not self.is_screenshot_template_valid():
            return

        self.save_settings()

        super().accept()

    # what the buttons do

    def run_youtube_checkup(self):
        """Resolve a real link the way playback would, step by step.

        It lives on this page rather than beside the cookies because
        two of its six steps are about cookies and the other four are
        about whether a link resolves at all, which is what this page
        is for. The runtime it can report as missing is set here too.

        Every setting it uses is read off the pages rather than out of
        the store: the point is to try what is on screen, which may be
        a runtime folder just typed, a proxy just changed, or an import
        of cookies nobody has pressed OK on yet.
        """

        # yt-dlp and streamlink are slow to import, and the settings dialog
        # is imported at startup
        from gridplayer.utils.ytdlp_checkup import YouTubeCheckup

        checkup = YouTubeCheckup(
            jar=self.cookiesList.jar,
            are_cookies_enabled=self.value("cookies/enabled"),
            js_runtime_path=self.value("streaming/js_runtime_path"),
            net_opts=self.network_opts_on_page,
        )

        CheckupDialog(self, checkup).exec_()

    def run_network_checkup(self):
        """Try the network settings as the page has them now.

        Read off the widgets rather than out of the store, for the same
        reason the cookies test is: what somebody wants tried is what
        they have just typed, and they have not pressed OK yet.
        """

        # slow to import for the same reason as the YouTube one
        from gridplayer.utils.network_checkup import NetworkCheckup

        CheckupDialog(self, NetworkCheckup(self.network_opts_on_page)).exec_()

    @property
    def network_opts_on_page(self):
        """The Network page as the settings it would be saved as."""

        return opts_for(
            proxy_mode=self.value("network/proxy_mode"),
            proxy_url=self.value("network/proxy_url"),
            user_agent=self.value("network/user_agent"),
            force_ipv4=self.value("network/force_ipv4"),
            timeout=self.value("network/timeout"),
            verify_tls=self.value("network/verify_tls"),
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
            translate("SettingsDialog - Cookies", "Cookies", "Header"),
            translate("SettingsDialog - Cookies", "How to export cookies"),
            info=howto,
        )

    def show_screenshot_template_help(self):
        """The specifiers, in a box of their own.

        Seven of them with what each gives is a table, and a table does not
        go in a tooltip anyone can read or under a field on a page that is
        already full. See gridplayer.utils.screenshots for what they do.
        """

        help_text = translate(
            "SettingsDialog",
            "<p>The file name is made from the format, with these replaced:</p>"
            "<table cellspacing='0' cellpadding='3'>"
            "<tr><td><tt>%f</tt></td><td>video name</td></tr>"
            "<tr><td><tt>%F</tt></td><td>video name without extension</td></tr>"
            "<tr><td><tt>%p</tt></td><td>position in the video, 01-02-03</td></tr>"
            "<tr><td><tt>%P</tt></td>"
            "<td>position in the video with milliseconds, 01-02-03.456</td></tr>"
            "<tr><td><tt>%n</tt></td>"
            "<td>number, 0001 and up, the first one not taken yet</td></tr>"
            "<tr><td><tt>%D</tt></td><td>date, 2026-09-24</td></tr>"
            "<tr><td><tt>%T</tt></td>"
            "<td>date and time, 2026-09-24_13-05-09</td></tr>"
            "<tr><td><tt>%tY</tt></td><td>year, 2026</td></tr>"
            "<tr><td><tt>%ty</tt></td><td>year, 26</td></tr>"
            "<tr><td><tt>%tm</tt></td><td>month, 09</td></tr>"
            "<tr><td><tt>%td</tt></td><td>day, 24</td></tr>"
            "<tr><td><tt>%tH</tt></td><td>hour, 13</td></tr>"
            "<tr><td><tt>%tM</tt></td><td>minute, 05</td></tr>"
            "<tr><td><tt>%tS</tt></td><td>second, 09</td></tr>"
            "<tr><td><tt>%%</tt></td><td>a percent sign</td></tr>"
            "</table>"
            "<p>For example:</p>"
            "<table cellspacing='0' cellpadding='3'>"
            "<tr><td><tt>%F_%P</tt></td><td><tt>clip_00-01-02.345.png</tt></td></tr>"
            "<tr><td><tt>%D_%n</tt></td>"
            "<td><tt>2026-09-24_0001.png</tt></td></tr>"
            "<tr><td><tt>%F %T</tt></td>"
            "<td><tt>clip 2026-09-24_13-05-09.png</tt></td></tr>"
            "</table>"
            "<p>Without <tt>%n</tt>, a name that is taken gets a number"
            " in brackets after it. Characters a file name can't have are"
            " replaced with <tt>_</tt>. Leave the format empty to go back to"
            " <tt>%F_%P</tt>.</p>",
        )

        QCustomMessageBox.information(
            self,
            translate("SettingsDialog", "Screenshots"),
            translate("SettingsDialog", "Screenshot file name format"),
            info=help_text,
        )

    # folders and the cache

    def open_cache_dir(self):
        folder = cache.cache_root()

        # opened before anything was kept there, as an empty folder
        folder.mkdir(parents=True, exist_ok=True)

        self._open_folder(folder)

    def open_data_dir(self):
        """The folder rather than the log file that used to be opened.

        The log is in there and named for what it is, so nothing is lost
        by stopping one short of it, and the folder is now somewhere a
        person is sent for reasons of their own: it is where a
        JavaScript runtime goes on the packages that cannot see one
        installed anywhere else. See gridplayer.utils.js_runtime.
        """

        self._open_folder(get_app_data_dir())

    def _open_folder(self, folder):
        self._log.debug(f"Opening folder {folder}")

        if env.IS_SNAP:
            # https://forum.snapcraft.io/t/xdg-open-or-gvfs-open-qdesktopservices-openurl-file-somelocation-file-txt-wont-open-the-file/16824
            subprocess.call(["xdg-open", folder])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def measure_cache(self, first=None):
        """What the cache comes to, put beside Clear once it is known.

        On a thread of its own, after whatever is to be done first: a
        large cache is a lot of files to look over, or to delete.
        """

        def work():
            if first is not None:
                first()

            size = cache.kept_bytes()

            # the dialog may have gone meanwhile
            with contextlib.suppress(RuntimeError):
                self.cache_measured.emit(size)

        threading.Thread(target=work, name="cache size", daemon=True).start()

    def clear_cache(self):
        """Cleared at once rather than on OK: nothing is lost but what
        would be downloaded again."""

        self.cacheClear.setEnabled(False)
        self.cacheSize.setText(translate("SettingsDialog", "Clearing..."))

        self.measure_cache(first=cache.clear)

    def show_cache_size(self, size):
        self.cacheClear.setEnabled(size > 0)

        if size == 0:
            self.cacheSize.setText(translate("SettingsDialog", "Empty"))
            return

        megabytes = QLocale().toString(max(size / cache.MB, 0.1), "f", 1)

        self.cacheSize.setText(
            translate("SettingsDialog", "{SIZE} MB used").format(SIZE=megabytes)
        )
