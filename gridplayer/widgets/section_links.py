"""A row of links to the sections of a long settings page, over what
scrolls: the one in view marked, and a click scrolls to the one clicked."""

from PyQt5.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from gridplayer.widgets.settings_controls import theme_color

LINK_PADDING = 9
LINK_HEIGHT = 22
LINK_SPACING = 6


class _FlowLayout(QLayout):
    """Left to right, onto the next line where the line is full."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._lay_out(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._lay_out(rect, move=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _lay_out(self, rect, move):
        x, y, line_height = rect.x(), rect.y(), 0

        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line_height > 0:
                x = rect.x()
                y += line_height + LINK_SPACING
                line_height = 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + LINK_SPACING
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()


class _Link(QAbstractButton):
    """A section's name in a pill, filled in while it is the one in view."""

    def __init__(self, text: str):
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)

    def sizeHint(self):
        width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(width + 2 * LINK_PADDING, LINK_HEIGHT)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        is_on = self.isChecked()
        pill = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = pill.height() / 2

        if is_on:
            painter.setPen(theme_color(self, "text"))
            painter.setBrush(theme_color(self, "text"))
        else:
            painter.setPen(theme_color(self, "highlight"))
            painter.setBrush(
                theme_color(self, "highlight" if self.underMouse() else "base")
            )
        if self.hasFocus():
            painter.setPen(theme_color(self, "text"))
        painter.drawRoundedRect(pill, radius, radius)

        painter.setPen(theme_color(self, "base" if is_on else "text"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class SectionLinks(QWidget):
    """Links to the sections of the page in a scroll area."""

    def __init__(self, scroll: QScrollArea, sections: list[tuple[str, QWidget]]):
        super().__init__()

        self._scroll = scroll
        self._sections = [widget for _, widget in sections]
        # the one clicked last, for when the page can't scroll as far as it
        self._picked = None

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = _FlowLayout(self)
        for index, (title, _) in enumerate(sections):
            link = _Link(title)
            self._group.addButton(link, index)
            layout.addWidget(link)

        self._group.idClicked.connect(self._go_to)
        scroll.verticalScrollBar().valueChanged.connect(self._follow)

        self._follow()

    @property
    def links(self) -> list[QAbstractButton]:
        return self._group.buttons()

    def _top_of(self, section: QWidget) -> int:
        return section.mapTo(self._scroll.widget(), QPoint(0, 0)).y()

    def _go_to(self, index: int):
        self._picked = index
        bar = self._scroll.verticalScrollBar()
        bar.setValue(min(self._top_of(self._sections[index]), bar.maximum()))
        self._follow()

    def _follow(self, *_):
        bar = self._scroll.verticalScrollBar()

        if self._picked is not None and bar.value() >= bar.maximum():
            # down at the end, the one clicked rather than one above it
            current = self._picked
        else:
            self._picked = None
            current = 0
            for index, section in enumerate(self._sections):
                if section.isVisibleTo(self._scroll) and (
                    self._top_of(section) <= bar.value()
                ):
                    current = index

        self._group.button(current).setChecked(True)
