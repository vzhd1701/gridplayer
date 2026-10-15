from PyQt5.QtWidgets import QComboBox

from gridplayer.widgets.combo_box import combo_index


def _combo():
    combo = QComboBox()
    combo.addItem("A", "a")
    combo.addItem("B", "b")
    return combo


def test_the_item_that_has_the_value():
    assert combo_index(_combo(), "b") == 1


def test_the_first_item_for_a_value_none_has():
    assert combo_index(_combo(), "gone") == 0
