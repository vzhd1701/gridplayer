from PyQt5 import QtWidgets
from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QConicalGradient, QPainter, QPen, QPolygonF

from gridplayer.utils.qt import translate
from gridplayer.widgets.settings_controls import DISABLED_OPACITY, theme_color


class QColorCircle(QtWidgets.QRadioButton):
    color_changed = pyqtSignal()

    def __init__(self, color, is_custom=False, **kwargs):
        super().__init__(**kwargs)

        self.color = color
        self.is_custom = is_custom

        circle_size = 36

        self.setFixedSize(circle_size, circle_size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self.draw_selected_outline(painter)

        self.draw_circle(painter)

    def draw_selected_outline(self, painter):
        if self.isChecked():
            color = QColor(self.palette().color(self.foregroundRole()))
            dot_line_pen = QPen(QBrush(color), 2, Qt.DotLine)
            painter.setPen(dot_line_pen)

            one_pixel_margin_circle = self.rect().adjusted(1, 1, -1, -1)
            painter.drawEllipse(one_pixel_margin_circle)

    def draw_circle(self, painter):
        # Draw color circle

        outline_color = QColor(self.palette().color(self.foregroundRole()))
        outline_color.setAlphaF(0.7)

        painter.setPen(QPen(QBrush(outline_color), 2))
        circle_rect = self.rect().adjusted(5, 5, -5, -5)

        if self.color is None:
            f = painter.font()
            moderately_big = 20
            f.setPixelSize(moderately_big)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignCenter, "…")
        else:
            painter.setBrush(self.color)

        painter.drawEllipse(circle_rect)

    def mousePressEvent(self, event):
        if self.is_custom:
            init_color = self.color or Qt.white
            new_color = QtWidgets.QColorDialog.getColor(
                init_color,
                self,
                translate(
                    "Dialog - Rename video - Select color", "Select color", "Header"
                ),
            )
            if new_color.isValid():
                self.color = new_color
                self.update()
                if self.isChecked():
                    # Re-selecting the custom swatch only changes the color.
                    self.color_changed.emit()
                else:
                    self.setChecked(True)
            else:
                return
        else:
            self.setChecked(True)


class QColorPalette(QtWidgets.QWidget):
    color_palette = (
        (255, 255, 255),
        (0, 0, 0),
        (87, 36, 194),
        (182, 41, 212),
        (252, 18, 51),
        (251, 95, 44),
        (229, 158, 37),
        (24, 168, 65),
        (26, 169, 178),
        (24, 133, 226),
        (13, 58, 153),
    )

    color_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAutoFillBackground(True)

        self.color_widgets = {
            col: QColorCircle(QColor(*col), parent=self) for col in self.color_palette
        }
        self.custom_color_widget = QColorCircle(None, is_custom=True, parent=self)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        for col_widget in self.color_widgets.values():
            main_layout.addWidget(col_widget)
            col_widget.toggled.connect(self._on_circle_toggled)
            col_widget.color_changed.connect(self.color_changed)
        main_layout.addWidget(self.custom_color_widget)
        self.custom_color_widget.toggled.connect(self._on_circle_toggled)
        self.custom_color_widget.color_changed.connect(self.color_changed)

        # A palette with nothing selected is not a valid state.
        self.color_widgets[(255, 255, 255)].setChecked(True)

    def _on_circle_toggled(self, checked):
        if checked:
            self.color_changed.emit()

    @property
    def color(self):
        for col_widget in self.color_widgets.values():
            if col_widget.isChecked():
                return col_widget.color
        return self.custom_color_widget.color

    @color.setter
    def color(self, color_rgb):
        if self.color_widgets.get(color_rgb):
            self.color_widgets[color_rgb].setChecked(True)
        else:
            self.custom_color_widget.color = QColor(*color_rgb)
            self.custom_color_widget.setChecked(True)


# the field: its size, the dot of colour in it, and the arrow
FIELD_SIZE = QSize(120, 24)
FIELD_RADIUS = 4
FIELD_PADDING = 6
DOT_PX = 14
ARROW_PX = 8

# the drop-down: its circles, the room between them, how many to a line,
# and the room left round them for the ring of the one picked
SWATCH_PX = 22
SWATCH_GAP = 8
SWATCH_COLUMNS = 6
RING_ROOM = 4


def _edge(widget) -> QColor:
    """A thin ring round a circle of colour, so that one the colour of what
    is behind it still shows."""

    color = QColor(theme_color(widget, "text"))
    color.setAlphaF(0.4)
    return color


def _any_color(rect: QRectF) -> QBrush:
    """The circle for a color of your own: all of them, round."""

    gradient = QConicalGradient(rect.center(), 90)
    for step in range(7):
        gradient.setColorAt(step / 6, QColor.fromHsv((360 - 60 * step) % 360, 220, 245))
    return QBrush(gradient)


class _Swatches(QtWidgets.QWidget):
    """The palette's colors as circles, and one more for any other: the one
    set if it is not in the palette, or all colors if it is."""

    picked = pyqtSignal(QColor)
    other_wanted = pyqtSignal()

    def __init__(self, current: QColor, parent=None):
        super().__init__(parent)

        palette = [QColor(*rgb) for rgb in QColorPalette.color_palette]
        self._colors: list[QColor | None] = [*palette, None]
        if current not in palette:
            self._colors[-1] = QColor(current)

        self._current = self._colors.index(current) if current in self._colors else -1
        self._hovered = -1
        # where the arrow keys are, starting on the one set
        self._keyed = max(self._current, 0)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def _rows(self) -> int:
        return -(-len(self._colors) // SWATCH_COLUMNS)

    def sizeHint(self):
        def side(count):
            return 2 * RING_ROOM + count * SWATCH_PX + (count - 1) * SWATCH_GAP

        return QSize(side(SWATCH_COLUMNS), side(self._rows()))

    def minimumSizeHint(self):
        return self.sizeHint()

    def _circle(self, index) -> QRectF:
        row, column = divmod(index, SWATCH_COLUMNS)
        step = SWATCH_PX + SWATCH_GAP
        return QRectF(
            RING_ROOM + column * step, RING_ROOM + row * step, SWATCH_PX, SWATCH_PX
        )

    def _at(self, pos) -> int:
        for index in range(len(self._colors)):
            if self._circle(index).contains(QPointF(pos)):
                return index
        return -1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        for index, color in enumerate(self._colors):
            circle = self._circle(index)

            painter.setPen(QPen(_edge(self), 1))
            painter.setBrush(_any_color(circle) if color is None else color)
            painter.drawEllipse(circle.adjusted(0.5, 0.5, -0.5, -0.5))

            ring = None
            if index == self._current:
                ring = theme_color(self, "text")
            elif index == self._hovered or (
                index == self._keyed and self.hasFocus() and self._hovered < 0
            ):
                ring = theme_color(self, "highlight")
            if ring is not None:
                painter.setPen(QPen(ring, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(circle.adjusted(-3, -3, 3, 3))

    def choose(self, index: int):
        color = self._colors[index]
        if color is None:
            # all colors: the system's own picker for one of them
            self.other_wanted.emit()
        else:
            self.picked.emit(QColor(color))

    def mouseMoveEvent(self, event):
        hovered = self._at(event.pos())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()

    def leaveEvent(self, event):
        self._hovered = -1
        self.update()

    def mouseReleaseEvent(self, event):
        index = self._at(event.pos())
        if event.button() == Qt.LeftButton and index >= 0:
            self.choose(index)

    def keyPressEvent(self, event):
        steps = {
            Qt.Key_Left: -1,
            Qt.Key_Right: 1,
            Qt.Key_Up: -SWATCH_COLUMNS,
            Qt.Key_Down: SWATCH_COLUMNS,
        }
        if event.key() in steps:
            keyed = self._keyed + steps[event.key()]
            if 0 <= keyed < len(self._colors):
                self._keyed = keyed
                self.update()
            return
        if event.key() in {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space}:
            self.choose(self._keyed)
            return
        super().keyPressEvent(event)


class _Rule(QtWidgets.QWidget):
    """A line across, in the grey the cards are edged with."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(1)

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), theme_color(self, "highlight"))


class _ColorPopup(QtWidgets.QFrame):
    """The colors to pick from, dropped down under the field, the way a
    list drops down under a combo box."""

    picked = pyqtSignal(QColor)

    def __init__(self, current: QColor, parent=None):
        super().__init__(parent, Qt.Popup)

        self._current = QColor(current)

        self.swatches = _Swatches(self._current, self)
        self.swatches.picked.connect(self._pick)
        self.swatches.other_wanted.connect(self.ask_other)

        self.other = QtWidgets.QPushButton(
            translate("SettingsDialog", "Other color...")
        )
        self.other.setFlat(True)
        self.other.clicked.connect(self.ask_other)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(6)
        layout.addWidget(self.swatches)
        layout.addWidget(_Rule())
        layout.addWidget(self.other, 0, Qt.AlignLeft)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(theme_color(self, "highlight"))
        painter.setBrush(theme_color(self, "base"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def show_under(self, field: QtWidgets.QWidget):
        """Under the field and lined up with it, or over it if there is
        no room below, and kept on the screen."""

        self.adjustSize()
        size = self.sizeHint()

        below = field.mapToGlobal(QPoint(0, field.height() + 2))
        screen = QtWidgets.QApplication.screenAt(below)
        area = (screen or QtWidgets.QApplication.primaryScreen()).availableGeometry()

        x = min(below.x(), area.right() - size.width())
        y = below.y()
        if y + size.height() > area.bottom():
            y = field.mapToGlobal(QPoint(0, 0)).y() - size.height() - 2

        self.move(max(x, area.left()), max(y, area.top()))
        self.show()
        self.swatches.setFocus()

    def _pick(self, color: QColor):
        self.hide()
        self.picked.emit(color)

    def ask_other(self):
        self.hide()
        color = QtWidgets.QColorDialog.getColor(
            self._current,
            self.parentWidget(),
            translate("Dialog - Rename video - Select color", "Select color", "Header"),
        )
        if color.isValid():
            self.picked.emit(color)


class QCompactColorPicker(QtWidgets.QAbstractButton):
    """A color as a field: a dot of it, its code, and an arrow; a click
    drops the palette down under it."""

    color_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._color = QColor("#ffffff")
        self._popup: _ColorPopup | None = None

        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_Hover)
        self.clicked.connect(self._open_popup)

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, color_rgb):
        new_color = QColor(*color_rgb)
        if new_color == self._color:
            return

        self._color = new_color
        self.update()
        self.color_changed.emit()

    def sizeHint(self):
        return FIELD_SIZE

    def minimumSizeHint(self):
        return FIELD_SIZE

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.isEnabled():
            painter.setOpacity(DISABLED_OPACITY)

        field = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        is_lit = self.hasFocus() or (self.underMouse() and self.isEnabled())
        painter.setPen(theme_color(self, "text" if is_lit else "highlight"))
        painter.setBrush(theme_color(self, "base"))
        painter.drawRoundedRect(field, FIELD_RADIUS, FIELD_RADIUS)

        dot = QRectF(FIELD_PADDING, (self.height() - DOT_PX) / 2, DOT_PX, DOT_PX)
        painter.setPen(QPen(_edge(self), 1))
        painter.setBrush(self._color)
        painter.drawEllipse(dot.adjusted(0.5, 0.5, -0.5, -0.5))

        text_left = int(dot.right()) + FIELD_PADDING
        arrow_left = self.width() - FIELD_PADDING - ARROW_PX
        painter.setPen(theme_color(self, "text"))
        painter.drawText(
            QRect(text_left, 0, arrow_left - text_left, self.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._color.name(QColor.HexRgb).upper(),
        )

        middle = self.height() / 2
        arrow = QPolygonF(
            [
                QPointF(arrow_left, middle - ARROW_PX / 4),
                QPointF(arrow_left + ARROW_PX, middle - ARROW_PX / 4),
                QPointF(arrow_left + ARROW_PX / 2, middle + ARROW_PX / 4),
            ]
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme_color(self, "text"))
        painter.drawPolygon(arrow)

    def keyPressEvent(self, event):
        # as a combo box opens its list
        if event.key() in {Qt.Key_Down, Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter}:
            self.click()
            return
        super().keyPressEvent(event)

    def _open_popup(self):
        # one at a time: hidden when done, the last one would stay till the
        # picker goes
        if self._popup is not None:
            self._popup.deleteLater()
        self._popup = _ColorPopup(self._color, self)
        self._popup.picked.connect(self._take)
        self._popup.show_under(self)

    def _take(self, color: QColor):
        self.color = color.getRgb()[:3]
