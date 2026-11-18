"""What a combo does about a value it doesn't have, and about a list too long
to draw in one column."""

from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtGui import QPainter, QPalette, QStandardItemModel
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStylePainter,
)

from gridplayer.params.theme import secondary_text_color

# a list longer than this opens as one column the height of the screen
MAX_VISIBLE_COMBO_ITEMS = 12

# the room in the open list besides an item's text: its padding either side,
# and the scroll bar
POPUP_ROOM_PX = 48

# the most of the screen's width the open list takes
POPUP_MAX_SCREEN_SHARE = 0.8

# what an item keeps saying why it can't be picked
REASON_ROLE = Qt.ItemDataRole.UserRole + 100
REASON_MARGIN_PX = 8
REASON_GAP_PX = 24
GREYED_OPACITY = 0.47


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
    combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


class _ReasonDelegate(QStyledItemDelegate):
    """The combo's own drawing of an item, with its reason on the right."""

    def __init__(self, drawn_by, parent):
        super().__init__(parent)
        self._drawn_by = drawn_by

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        return self._drawn_by.sizeHint(option, index)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ):
        reason = index.data(REASON_ROLE)
        if not reason:
            self._drawn_by.paint(painter, option, index)
            return

        painter.save()

        # The theme's style sheet sets one text colour for every item, greyed
        # out or not, so the grey is the combo's own drawing seen through. Its
        # disabled text has a copy under it in the Light colour, which shows as
        # a blur on a dark theme.
        no_etching = QStyleOptionViewItem(option)
        no_etching.palette.setColor(
            QPalette.ColorRole.Light, Qt.GlobalColor.transparent
        )
        painter.setOpacity(GREYED_OPACITY)
        self._drawn_by.paint(painter, no_etching, index)
        painter.setOpacity(1)

        # darker than the grey name, or it's hard to read
        painter.setPen(secondary_text_color())
        painter.drawText(
            option.rect.adjusted(0, 0, -REASON_MARGIN_PX, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            reason,
        )
        painter.restore()


def _widen_popup(combo: QComboBox, width_of) -> None:
    """A combo's list as wide as its widest item, by `width_of(index)`."""

    widest = max(map(width_of, range(combo.count())), default=0)
    screen = (combo.screen() or QApplication.primaryScreen()).availableGeometry()

    combo.view().setMinimumWidth(
        min(widest + POPUP_ROOM_PX, int(screen.width() * POPUP_MAX_SCREEN_SHARE))
    )


class ReasonComboBox(QComboBox):
    """A combo where some choices can't be picked: greyed out with the reason
    on the right, its list wide enough to read them whole."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # through the view: the combo's own setter would delete the one it has
        self.view().setItemDelegate(_ReasonDelegate(self.itemDelegate(), self))

    def set_unavailable(self, reasons: dict) -> None:
        """Value -> why it can't be picked."""

        model = self.model()
        assert isinstance(model, QStandardItemModel)

        for value, reason in reasons.items():
            at = self.findData(value)
            if at >= 0:
                model.item(at).setEnabled(False)
                self.setItemData(at, reason, REASON_ROLE)

    def reason_of(self, value) -> str | None:
        at = self.findData(value)
        return self.itemData(at, REASON_ROLE) if at >= 0 else None

    def showPopup(self):
        metrics = self.view().fontMetrics()

        def width_of(at):
            reason = self.itemData(at, REASON_ROLE)
            room = metrics.horizontalAdvance(reason) + REASON_GAP_PX if reason else 0
            return metrics.horizontalAdvance(self.itemText(at)) + room

        _widen_popup(self, width_of)

        super().showPopup()


class ElidedComboBox(QComboBox):
    """A combo that can be narrower than what it says: its text cut short in
    the middle where it does not fit, rather than cut off, and its list as
    wide as the longest item in it opens to read them whole."""

    def paintEvent(self, event):
        painter = QStylePainter(self)

        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        field = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        option.currentText = self.fontMetrics().elidedText(
            option.currentText, Qt.TextElideMode.ElideMiddle, field.width()
        )

        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def showPopup(self):
        metrics = self.view().fontMetrics()

        _widen_popup(self, lambda at: metrics.horizontalAdvance(self.itemText(at)))

        super().showPopup()
