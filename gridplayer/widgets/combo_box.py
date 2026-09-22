"""What a combo does about a list too long to draw in one column."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox

# a list longer than this opens as one column the height of the screen
MAX_VISIBLE_COMBO_ITEMS = 12


def cap_popup_height(combo: QComboBox, item_count: int) -> None:
    """Give a long list a scroll bar instead of the whole screen.

    maxVisibleItems is ignored while the popup is the platform's own, and
    combobox-popup is what gives it up. Only the lists long enough to need
    it are asked to, so the rest keep the popup the platform draws.

    The bar has to be asked for as well. A combo builds its list with the
    scroll bar off whatever the style, which suits a list drawn whole and
    leaves a capped one scrolling with nothing to say that it can.
    """

    if item_count <= MAX_VISIBLE_COMBO_ITEMS:
        return

    combo.setMaxVisibleItems(MAX_VISIBLE_COMBO_ITEMS)
    combo.setStyleSheet("QComboBox { combobox-popup: 0; }")
    combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
