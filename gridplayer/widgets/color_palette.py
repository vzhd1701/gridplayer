from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

from gridplayer.utils.qt import translate


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


class _QColorPopup(QtWidgets.QDialog):
    """Small modal popup hosting the circle palette."""

    color_changed = pyqtSignal()

    def __init__(self, current_color, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            translate("Dialog - Rename video - Select color", "Select color", "Header")
        )
        self.setModal(True)

        self._palette = QColorPalette(parent=self)
        self._palette.color = current_color
        self._palette.color_changed.connect(self._on_selected)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(9, 9, 9, 9)
        layout.addWidget(self._palette)

    def _on_selected(self):
        self.color_changed.emit()
        self.accept()

    @property
    def color(self):
        return self._palette.color


class QCompactColorPicker(QtWidgets.QToolButton):
    """Compact color swatch that opens the circle palette in a popup."""

    color_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._color = QColor("#ffffff")

        self.setFixedSize(28, 22)
        self.clicked.connect(self._open_popup)

        self._update_swatch()

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, color_rgb):
        new_color = QColor(*color_rgb)
        if new_color == self._color:
            return

        self._color = new_color
        self._update_swatch()
        self.color_changed.emit()

    def _update_swatch(self):
        swatch = QPixmap(20, 14)
        swatch.fill(self._color)

        painter = QPainter(swatch)
        painter.setPen(QColor("black"))
        painter.drawRect(0, 0, 19, 13)
        painter.end()

        self.setIcon(QIcon(swatch))

    def _open_popup(self):
        popup = _QColorPopup(self._color.getRgb()[:3], self)

        def _apply_selected():
            self.color = popup.color.getRgb()[:3]
            popup.accept()

        popup.color_changed.connect(_apply_selected)
        popup.exec_()
