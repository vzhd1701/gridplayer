from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest

from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.widgets.settings_controls import SegmentedChoice, Switch, ToggleLabel
from gridplayer.widgets.settings_editors import make_editor


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
