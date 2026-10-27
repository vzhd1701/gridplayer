"""The settings pages' own controls: a switch for what is on or off, a
row of buttons for a choice short enough to show all of it, and buttons
that stay pressed for some of a few."""

from PyQt5.QtCore import QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette
from PyQt5.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QCheckBox,
    QFrame,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# the round corners of a card of settings, and of a list or a table's box
CARD_RADIUS = 6

# a button that is only an icon, as small as the icon lets it be
ICON_BUTTON_SIZE = QSize(24, 24)
# between a list's box and the list in it, for its square corners to be
# clear of the round ones
BOX_PADDING = 3

# how much lighter than a card a field on it is, in the dark theme
FIELD_LIGHTER = 128

SWITCH_SIZE = QSize(36, 20)
SWITCH_KNOB_MARGIN = 3
# room around the track for the ring that shows the keyboard is on it
FOCUS_MARGIN = 2

# how the switch and the buttons look while greyed out
DISABLED_OPACITY = 0.4

SEGMENT_PADDING = 10
SEGMENTS_HEIGHT = 24
SEGMENTS_RADIUS = 4

# between the buttons of ToggleChips, and between their lines
CHIPS_SPACING = 6


# the theme's colours, by the names gridplayer.params.theme gives them,
# as it put them in the palette
_ROLES = {
    "text": QPalette.Text,
    "base": QPalette.Base,
    "window": QPalette.Window,
    "button": QPalette.Button,
    "highlight": QPalette.Highlight,
}


def theme_color(widget: QWidget, name: str) -> QColor:
    """Read off the palette at each paint, as the theme put it there, rather
    than worked out from the settings and the system again: the two can
    differ until the theme is applied.

    Always the active colours: a greyed-out control fades as a whole.
    """

    return widget.palette().color(QPalette.Active, _ROLES[name])


def _is_dark(widget: QWidget) -> bool:
    return theme_color(widget, "base").lightness() < 128


def icon_button(icon: str, tooltip: str = "") -> QPushButton:
    """An icon alone, with what it does in its tooltip. Not the dialog's
    default once clicked: Enter is still OK."""

    button = QPushButton(QIcon.fromTheme(icon), "")
    button.setToolTip(tooltip)
    button.setFixedSize(ICON_BUTTON_SIZE)
    button.setAutoDefault(False)
    return button


def paint_card(widget: QWidget) -> QPainter:
    """The widget as a card: round corners, on the base colour. The painter,
    for what else goes on it."""

    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(theme_color(widget, "highlight"))
    painter.setBrush(theme_color(widget, "base"))
    painter.drawRoundedRect(
        QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
        CARD_RADIUS,
        CARD_RADIUS,
    )
    return painter


def fit_fields(card: QWidget):
    """The fields on a card a shade lighter than it in the dark theme,
    where they are filled with the card's own colour and their edge is
    barely darker than it. Again on each change of theme."""

    fill = theme_color(card, "base")
    if _is_dark(card):
        fill = fill.lighter(FIELD_LIGHTER)

    for field in card.findChildren((QLineEdit, QAbstractSpinBox)):
        palette = field.palette()
        palette.setColor(QPalette.Base, fill)
        field.setPalette(palette)


class RoundedBox(QWidget):
    """A list or a table in a box with round corners, as a card of settings
    has, in place of its own square frame."""

    def __init__(self, view: QFrame):
        super().__init__()

        view.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(view.sizePolicy())
        # by name in the theme's style sheet, which gives a table's header
        # no edges of its own, only a line under it
        self.setObjectName("rounded_box")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(BOX_PADDING, BOX_PADDING, BOX_PADDING, BOX_PADDING)
        lay.addWidget(view)

    def paintEvent(self, event):
        paint_card(self)


class Switch(QCheckBox):
    """A checkbox drawn as a switch: dark when on, light grey when off.

    Its label is a ToggleLabel of its own, to the left of the row.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # by the keyboard, not by a click, so the ring shows only for keys
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        return SWITCH_SIZE + QSize(2 * FOCUS_MARGIN, 2 * FOCUS_MARGIN)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.isEnabled():
            painter.setOpacity(DISABLED_OPACITY)

        track = QRectF(
            (self.width() - SWITCH_SIZE.width()) / 2,
            (self.height() - SWITCH_SIZE.height()) / 2,
            SWITCH_SIZE.width(),
            SWITCH_SIZE.height(),
        )
        radius = track.height() / 2

        if self.hasFocus():
            painter.setPen(theme_color(self, "text"))
            painter.setBrush(Qt.NoBrush)
            ring = track.adjusted(-1.5, -1.5, 1.5, 1.5)
            painter.drawRoundedRect(ring, radius + 1.5, radius + 1.5)

        is_on = self.isChecked()

        painter.setPen(Qt.NoPen)
        painter.setBrush(theme_color(self, "text" if is_on else "highlight"))
        painter.drawRoundedRect(track, radius, radius)

        knob = track.height() - 2 * SWITCH_KNOB_MARGIN
        if is_on:
            left = track.right() - SWITCH_KNOB_MARGIN - knob
            fill = "base"
        else:
            left = track.left() + SWITCH_KNOB_MARGIN
            # light on the grey either way: dark on dark would be lost
            fill = "text" if _is_dark(self) else "base"
        painter.setBrush(theme_color(self, fill))
        painter.drawEllipse(QRectF(left, track.top() + SWITCH_KNOB_MARGIN, knob, knob))


class ToggleLabel(QLabel):
    """A switch's label: clicking it flips the switch, as a checkbox's own
    text would."""

    def __init__(self, text: str, switch: Switch):
        super().__init__(text)
        self._switch = switch

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and self.rect().contains(event.pos())
            and self._switch.isEnabled()
        ):
            self._switch.click()
        super().mouseReleaseEvent(event)


class FlowLayout(QLayout):
    """Left to right, onto the next line where the line is full."""

    def __init__(self, parent=None, spacing: int = 0):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
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
                y += line_height + self._spacing
                line_height = 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()


class ToggleBox(QAbstractButton):
    """A name in a box, filled while it is on, as the part of a
    SegmentedChoice picked is."""

    padding = SEGMENT_PADDING
    box_height = SEGMENTS_HEIGHT
    # None for round ends, a pill
    radius: float | None = SEGMENTS_RADIUS
    # the box while off
    off_color = "button"

    def __init__(self, text: str):
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.TabFocus)

    def sizeHint(self):
        width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(width + 2 * self.padding, self.box_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        is_enabled = self.isEnabled()
        if not is_enabled:
            painter.setOpacity(DISABLED_OPACITY)

        is_on = self.isChecked()
        if is_on:
            painter.setPen(theme_color(self, "text"))
            painter.setBrush(theme_color(self, "text"))
        else:
            is_hovered = self.underMouse() and is_enabled
            painter.setPen(theme_color(self, "highlight"))
            painter.setBrush(
                theme_color(self, "highlight" if is_hovered else self.off_color)
            )
        if self.hasFocus():
            painter.setPen(theme_color(self, "text"))

        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = box.height() / 2 if self.radius is None else self.radius
        painter.drawRoundedRect(box, radius, radius)

        painter.setPen(theme_color(self, "base" if is_on else "text"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class ToggleChips(QWidget):
    """Some of a few short items, each a button that stays pressed while it
    is on, onto the next line where the line is full."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._chips: dict = {}
        self._flow = FlowLayout(self, CHIPS_SPACING)

    def set_choices(self, choices: dict) -> None:
        """value -> text"""

        for value, text in choices.items():
            chip = ToggleBox(text)
            chip.toggled.connect(lambda *_: self.changed.emit())
            self._chips[value] = chip
            self._flow.addWidget(chip)

    def set_picked(self, picked: frozenset) -> None:
        for value, chip in self._chips.items():
            chip.blockSignals(True)
            chip.setChecked(value in picked)
            chip.blockSignals(False)

    def picked(self) -> frozenset:
        return frozenset(v for v, chip in self._chips.items() if chip.isChecked())


class SegmentedChoice(QWidget):
    """A choice of a few short items, side by side as one row of buttons.

    Answers what a settings form asks of a QComboBox, so the two can stand
    in for each other.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._items: list[tuple[str, object]] = []
        self._current = -1
        self._hovered = -1

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # what a combo answers

    def addItem(self, text: str, data=None):
        self._items.append((text, data))
        if self._current < 0:
            self._current = 0
            self.currentIndexChanged.emit(0)
        self.updateGeometry()
        self.update()

    def clear(self):
        self._items = []
        self._current = -1
        self.updateGeometry()
        self.update()

    def count(self) -> int:
        return len(self._items)

    def itemText(self, index: int) -> str:
        return self._items[index][0]

    def itemData(self, index: int):
        return self._items[index][1]

    def findData(self, data) -> int:
        for index, (_, item_data) in enumerate(self._items):
            if item_data == data:
                return index
        return -1

    def currentIndex(self) -> int:
        return self._current

    def currentData(self):
        return self._items[self._current][1] if self._current >= 0 else None

    def currentText(self) -> str:
        return self._items[self._current][0] if self._current >= 0 else ""

    def setCurrentIndex(self, index: int):
        if not -1 <= index < len(self._items) or index == self._current:
            return
        self._current = index
        self.update()
        self.currentIndexChanged.emit(index)

    # drawn

    def _widths(self) -> list[int]:
        metrics = self.fontMetrics()
        return [
            metrics.horizontalAdvance(text) + 2 * SEGMENT_PADDING
            for text, _ in self._items
        ]

    def _segments(self) -> list[QRectF]:
        segments, left = [], 0.5
        for width in self._widths():
            segments.append(QRectF(left, 0.5, width, self.height() - 1))
            left += width
        return segments

    def sizeHint(self):
        return QSize(sum(self._widths()) + 1, SEGMENTS_HEIGHT)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _segment_at(self, pos) -> int:
        for index, segment in enumerate(self._segments()):
            if segment.left() <= pos.x() < segment.right():
                return index
        return -1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        is_enabled = self.isEnabled()
        if not is_enabled:
            painter.setOpacity(DISABLED_OPACITY)

        segments = self._segments()
        if not segments:
            return

        outline = QRectF(segments[0].topLeft(), segments[-1].bottomRight())
        shape = QPainterPath()
        shape.addRoundedRect(outline, SEGMENTS_RADIUS, SEGMENTS_RADIUS)

        painter.setPen(Qt.NoPen)
        painter.setBrush(theme_color(self, "button"))
        painter.drawPath(shape)

        painter.save()
        painter.setClipPath(shape)
        for index, segment in enumerate(segments):
            if index == self._current:
                painter.fillRect(segment, theme_color(self, "text"))
            elif index == self._hovered and is_enabled:
                painter.fillRect(segment, theme_color(self, "highlight"))
        painter.restore()

        painter.setPen(theme_color(self, "highlight"))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(shape)
        for segment in segments[1:]:
            painter.drawLine(segment.topLeft(), segment.bottomLeft())

        if self.hasFocus():
            painter.setPen(theme_color(self, "text"))
            painter.drawRoundedRect(
                outline.adjusted(1, 1, -1, -1), SEGMENTS_RADIUS, SEGMENTS_RADIUS
            )

        for index, (segment, (text, _)) in enumerate(
            zip(segments, self._items, strict=True)
        ):
            is_current = index == self._current
            painter.setPen(theme_color(self, "base" if is_current else "text"))
            painter.drawText(segment, Qt.AlignCenter, text)

    # picked

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self._segment_at(event.pos())
            if index >= 0:
                self.setCurrentIndex(index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        hovered = self._segment_at(event.pos())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        steps = {Qt.Key_Left: -1, Qt.Key_Right: 1}
        if event.key() in steps and self._items:
            index = self._current + steps[event.key()]
            self.setCurrentIndex(max(0, min(index, len(self._items) - 1)))
            return
        super().keyPressEvent(event)
