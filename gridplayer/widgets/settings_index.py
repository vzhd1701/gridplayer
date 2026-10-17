"""The list of settings pages down the left of the Settings dialog: group
headings small and grey, and each page with its icon, the one open on a
soft round shade, straight on the dialog with no frame around it."""

from PyQt5.QtCore import QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter
from PyQt5.QtWidgets import (
    QFrame,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
)

from gridplayer.params.theme import secondary_text_color
from gridplayer.widgets.settings_controls import theme_color

INDEX_WIDTH = 206

ITEM_PX = 13
ITEM_HEIGHT = 32
# Lucide's own size: smaller, its lines are scaled off the pixel grid and blur
ICON_PX = 24
# the icon in from the edge of the shade, and the name in from the icon
ICON_INSET = 10
ICON_GAP = 11
SHADE_RADIUS = 7

HEADING_PX = 11
HEADING_INSET = 8
# under a heading, to its first entry, and over it, from the last group
HEADING_BOTTOM = 6
FIRST_HEADING_HEIGHT = 24
HEADING_HEIGHT = 38

# how much of the highlight colour the shade takes: the page open, and the
# one under the pointer
PICKED_SHADE = 0.55
HOVER_SHADE = 0.25


def _is_heading(index) -> bool:
    return not index.flags() & Qt.ItemIsSelectable


class _IndexDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        widget = option.widget
        rect = option.rect
        font = index.data(Qt.FontRole) or option.font
        painter.setFont(font)

        if _is_heading(index):
            painter.setPen(secondary_text_color())
            painter.drawText(
                rect.adjusted(HEADING_INSET, 0, 0, -HEADING_BOTTOM),
                Qt.AlignLeft | Qt.AlignBottom,
                index.data(Qt.DisplayRole),
            )
            painter.restore()
            return

        shade = None
        if option.state & QStyle.State_Selected:
            shade = PICKED_SHADE
        elif option.state & QStyle.State_MouseOver:
            shade = HOVER_SHADE

        if shade is not None:
            color = QColor(theme_color(widget, "highlight"))
            color.setAlphaF(shade)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRectF(rect).adjusted(0, 1, 0, -1), SHADE_RADIUS, SHADE_RADIUS
            )

        left = rect.left() + ICON_INSET
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            top = rect.top() + (rect.height() - ICON_PX) // 2
            icon.paint(painter, QRect(left, top, ICON_PX, ICON_PX))
        left += ICON_PX + ICON_GAP

        painter.setPen(theme_color(widget, "text"))
        painter.drawText(
            rect.adjusted(left - rect.left(), 0, 0, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            index.data(Qt.DisplayRole),
        )

        painter.restore()


class SettingsIndex(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # by name in the theme's style sheet, which leaves it on the
        # dialog's own colour
        self.setObjectName("section_index")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(INDEX_WIDTH)
        self.setMinimumHeight(350)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAttribute(Qt.WA_Hover)
        self.setIconSize(QSize(ICON_PX, ICON_PX))
        self.setItemDelegate(_IndexDelegate(self))

        font = self.font()
        font.setPixelSize(ITEM_PX)
        self.setFont(font)

        self._heading_font = self.font()
        self._heading_font.setBold(True)
        self._heading_font.setPixelSize(HEADING_PX)

    def add_heading(self, title: str) -> QListWidgetItem:
        """Small and in capitals: a heading over entries, not one of them;
        and can't be picked."""

        is_first = self.count() == 0

        heading = QListWidgetItem(title.upper(), self)
        heading.setFont(self._heading_font)
        heading.setFlags(Qt.NoItemFlags)
        heading.setSizeHint(
            QSize(0, FIRST_HEADING_HEIGHT if is_first else HEADING_HEIGHT)
        )
        return heading

    def add_page(self, title: str, icon: str | None) -> QListWidgetItem:
        item = QListWidgetItem(title, self)
        if icon is not None:
            item.setIcon(QIcon.fromTheme(icon))
        item.setSizeHint(QSize(0, ITEM_HEIGHT))
        return item
