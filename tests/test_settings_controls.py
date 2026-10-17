import pytest
from PyQt5.QtCore import QDeadlineTimer, QEvent, QPoint, Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QScrollArea

from gridplayer.params.settings_fields.kinds import Indented, Section
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.params.static import ProxyMode
from gridplayer.settings import default_value
from gridplayer.widgets.settings_controls import SegmentedChoice, Switch, ToggleLabel
from gridplayer.widgets.settings_editors import make_editor
from gridplayer.widgets.settings_form import ROW_HEIGHT, SCROLL_MS, SettingsForm


def _choice(*items):
    choice = SegmentedChoice()
    for text, value in items:
        choice.addItem(text, value)
    choice.resize(choice.sizeHint())
    return choice


class TestSegmentedChoice:
    def test_it_starts_on_the_first_item(self):
        choice = _choice(("Fit", "fit"), ("None", "none"))

        assert choice.currentIndex() == 0
        assert choice.currentData() == "fit"

    def test_it_finds_an_item_by_its_value_as_a_combo_would(self):
        choice = _choice(("Fit", "fit"), ("None", "none"))

        assert choice.findData("none") == 1
        assert choice.findData("missing") == -1

    def test_a_click_picks_the_item_under_it(self):
        choice = _choice(("Fit", "fit"), ("Stretch", "stretch"), ("None", "none"))
        picked = []
        choice.currentIndexChanged.connect(picked.append)

        QTest.mouseClick(choice, Qt.LeftButton, pos=QPoint(choice.width() - 3, 5))

        assert picked == [2]
        assert choice.currentData() == "none"

    def test_arrows_step_and_stop_at_the_ends(self):
        choice = _choice(("A", 1), ("B", 2))

        QTest.keyClick(choice, Qt.Key_Right)
        QTest.keyClick(choice, Qt.Key_Right)
        assert choice.currentIndex() == 1

        QTest.keyClick(choice, Qt.Key_Left)
        QTest.keyClick(choice, Qt.Key_Left)
        assert choice.currentIndex() == 0

    def test_picking_the_current_one_again_is_not_a_change(self):
        choice = _choice(("A", 1), ("B", 2))
        picked = []
        choice.currentIndexChanged.connect(picked.append)

        choice.setCurrentIndex(0)

        assert picked == []


class TestSwitch:
    def test_clicking_its_label_flips_it(self):
        switch = Switch()
        label = ToggleLabel("Muted", switch)

        QTest.mouseClick(label, Qt.LeftButton)

        assert switch.isChecked()

    def test_a_greyed_out_one_stays_as_it_is(self):
        switch = Switch()
        switch.setEnabled(False)
        label = ToggleLabel("Muted", switch)

        QTest.mouseClick(label, Qt.LeftButton)

        assert not switch.isChecked()


def test_a_short_choice_is_a_row_of_buttons_and_a_long_one_a_list():
    assert isinstance(
        make_editor(FIELDS["video_defaults/aspect"]).widget, SegmentedChoice
    )
    assert not isinstance(
        make_editor(FIELDS["video_defaults/end_action"]).widget, SegmentedChoice
    )


class TestSubOptionsShowOnlyWhenTheyApply:
    @pytest.fixture
    def form(self):
        form = SettingsForm(
            (
                Section(
                    "Timeouts",
                    "misc/mouse_hide",
                    Indented("misc/mouse_hide_timeout"),
                    "player/video_init_timeout",
                ),
            ),
            reset_to=default_value,
        )
        form.set_values({"misc/mouse_hide": False})

        yield form

        form.deleteLater()

    def test_one_that_does_not_apply_is_not_there(self, form):
        assert not form._rows["misc/mouse_hide_timeout"].isVisibleTo(form)
        assert not form.is_enabled("misc/mouse_hide_timeout")

    def test_it_comes_back_with_the_one_it_belongs_to(self, form):
        form.widget("misc/mouse_hide").click()

        assert form._rows["misc/mouse_hide_timeout"].isVisibleTo(form)
        assert form.is_enabled("misc/mouse_hide_timeout")

    def test_one_that_is_not_a_sub_option_is_greyed_out_instead(self):
        form = SettingsForm(
            ("misc/mouse_hide", "misc/mouse_hide_timeout"), reset_to=default_value
        )
        form.set_values({"misc/mouse_hide": False})
        # a widget put in a layout is shown once the event loop gets to it
        QApplication.processEvents()

        assert form._rows["misc/mouse_hide_timeout"].isVisibleTo(form)
        assert not form.is_enabled("misc/mouse_hide_timeout")


class TestARowShownByAChange:
    """Sub-options that appear under the setting just changed."""

    @pytest.fixture
    def page(self):
        form = SettingsForm(
            (
                Section(
                    "Timeouts",
                    "player/video_init_timeout",
                    "misc/mouse_hide",
                    Indented("misc/mouse_hide_timeout"),
                ),
            ),
            reset_to=default_value,
        )
        form.set_values({"misc/mouse_hide": False})
        # room above, so the page has to scroll to get to the end of it
        form.layout().insertSpacing(0, 600)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form)
        scroll.resize(400, 300)
        scroll.show()
        _wait(SCROLL_MS)

        # shown once and put away again, as on a page that has been used
        form.widget("misc/mouse_hide").click()
        _wait(SCROLL_MS * 2)
        form.widget("misc/mouse_hide").click()
        _wait(SCROLL_MS)

        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

        yield form, scroll

        scroll.close()
        scroll.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_the_page_is_at_its_new_height_before_it_is_painted(self, page):
        """Laid out in the height it had until the event loop came round, every
        row was squeezed for a moment, and the page seemed to jump."""

        form, _ = page

        form.widget("misc/mouse_hide").click()

        assert form.height() == form.sizeHint().height()
        assert form._rows["misc/mouse_hide"].height() >= ROW_HEIGHT

    def test_it_is_scrolled_into_view(self, page):
        form, scroll = page
        row = form._rows["misc/mouse_hide_timeout"]

        form.widget("misc/mouse_hide").click()
        _wait(SCROLL_MS * 2)

        bottom = row.mapTo(scroll.viewport(), QPoint(0, row.height())).y()
        assert bottom <= scroll.viewport().height()


class TestFieldsOnACard:
    @pytest.fixture
    def form(self):
        form = SettingsForm(("network/user_agent",), reset_to=default_value)
        yield form
        form.deleteLater()

    @staticmethod
    def _fill(widget):
        return widget.palette().color(QPalette.Active, QPalette.Base)

    @staticmethod
    def _themed(form, base):
        palette = form.palette()
        palette.setColor(QPalette.Base, QColor(base))
        form.setPalette(palette)

    def test_in_the_dark_one_is_lighter_than_the_card(self, form):
        """Filled with the card's own colour, a field was barely there."""

        self._themed(form, "#3a3a3a")

        card = form._rows["network/user_agent"].parentWidget()
        field = form.widget("network/user_agent")
        assert self._fill(field).lightness() > self._fill(card).lightness()

    def test_in_the_light_one_it_is_as_white_as_the_card(self, form):
        self._themed(form, "#3a3a3a")
        self._themed(form, "#ffffff")

        assert self._fill(form.widget("network/user_agent")) == QColor("#ffffff")


def test_the_bar_of_a_changed_sub_option_runs_along_its_label_and_field():
    """Measured from the edges of the row, it hung below what is in it: a
    sub-option has no room above it, and the usual room below."""

    form = SettingsForm(
        (Section("Proxy", "network/proxy_mode", Indented("network/proxy_url")),),
        reset_to=default_value,
    )
    form.set_values({"network/proxy_mode": ProxyMode.CUSTOM})
    form.resize(500, 300)
    form.show()
    _wait(50)

    row = form._rows["network/proxy_url"]
    field = form.widget("network/proxy_url")
    bar = row.mark_bar()
    field_bottom = field.mapTo(row, QPoint(0, field.height())).y()

    assert bar.top() == 0
    assert bar.bottom() == field_bottom

    form.close()
    form.deleteLater()


def _wait(ms):
    deadline = QDeadlineTimer(ms)
    while not deadline.hasExpired():
        QApplication.processEvents()


def test_a_list_says_itself_what_is_changed_in_it_with_no_bar():
    """The bar down the whole side of a list was a black stripe."""

    form = SettingsForm(("player/keymap",), reset_to=default_value)
    keymap = form.widget("player/keymap")

    bindings = keymap.get_bindings()
    bindings[next(iter(bindings))] = ["Ctrl+F12"]
    keymap.set_bindings(bindings)
    keymap.bindings_changed.emit()

    assert form.is_modified("player/keymap")
    assert not form.is_marked("player/keymap")

    form.deleteLater()
