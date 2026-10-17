"""The settings pages' own controls: a switch for what is on or off, and a
row of buttons for a choice short enough to show all of it."""

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPalette
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# the round corners of a card of settings, and of a list or a table's box
CARD_RADIUS = 6
# between a list's box and the list in it, for its square corners to be
# clear of the round ones
BOX_PADDING = 3

SWITCH_SIZE = QSize(36, 20)
SWITCH_KNOB_MARGIN = 3
# room around the track for the ring that shows the keyboard is on it
FOCUS_MARGIN = 2

# how the switch and the buttons look while greyed out
DISABLED_OPACITY = 0.4

SEGMENT_PADDING = 10
SEGMENTS_HEIGHT = 24
SEGMENTS_RADIUS = 4


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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(theme_color(self, "highlight"))
        painter.setBrush(theme_color(self, "base"))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            CARD_RADIUS,
            CARD_RADIUS,
        )


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
