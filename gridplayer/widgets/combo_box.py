"""What a combo does about a value it doesn't have, and about a list too long
to draw in one column."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
)

# a list longer than this opens as one column the height of the screen
MAX_VISIBLE_COMBO_ITEMS = 12

# the room in the open list besides an item's text: its padding either side,
# and the scroll bar
POPUP_ROOM_PX = 48

# the most of the screen's width the open list takes
POPUP_MAX_SCREEN_SHARE = 0.8


def combo_index(combo: QComboBox, value) -> int:
    """The item that has the value, or the first one for a value none has."""

    return max(combo.findData(value), 0)


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


class ElidedComboBox(QComboBox):
    """A combo that can be narrower than what it says: its text cut short in
    the middle where it does not fit, rather than cut off, and its list as
    wide as the longest item in it opens to read them whole."""

    def paintEvent(self, event):
        painter = QStylePainter(self)

        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        field = self.style().subControlRect(
            QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, self
        )
        option.currentText = self.fontMetrics().elidedText(
            option.currentText, Qt.ElideMiddle, field.width()
        )

        painter.drawControl(QStyle.CE_ComboBoxLabel, option)

    def showPopup(self):
        metrics = self.view().fontMetrics()
        widest = max(
            (metrics.horizontalAdvance(self.itemText(n)) for n in range(self.count())),
            default=0,
        )

        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()

        self.view().setMinimumWidth(
            min(widest + POPUP_ROOM_PX, int(screen.width() * POPUP_MAX_SCREEN_SHARE))
        )

        super().showPopup()
