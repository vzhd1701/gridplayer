import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.settings_fields.kinds import Indented, Section
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.settings import default_value
from gridplayer.widgets.settings_controls import SegmentedChoice, Switch, ToggleLabel
from gridplayer.widgets.settings_editors import make_editor
from gridplayer.widgets.settings_form import SettingsForm


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
