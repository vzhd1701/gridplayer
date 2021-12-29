from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPen


class QColorCircle(QtWidgets.QRadioButton):
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
            dot_line_pen = QPen(QBrush(QColor(Qt.black)), 2, Qt.DotLine)
            painter.setPen(dot_line_pen)

            one_pixel_margin_circle = self.rect().adjusted(1, 1, -1, -1)
            painter.drawEllipse(one_pixel_margin_circle)

    def draw_circle(self, painter):
        # Draw color circle
        if self.color in (Qt.white, None):  # noqa: WPS510
            painter.setPen(QPen(QBrush(QColor(Qt.gray)), 2))
            circle_rect = self.rect().adjusted(5, 5, -5, -5)
        else:
            painter.setPen(Qt.NoPen)
            circle_rect = self.rect().adjusted(4, 4, -4, -4)

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
                init_color, self, self.tr("Select color")
            )
            if new_color.isValid():
                self.color = new_color
                self.update()
            else:
                return
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
        main_layout.addWidget(self.custom_color_widget)

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


class QVideoRenameDialog(QtWidgets.QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.original_title = ""

        self.title = QtWidgets.QLineEdit(self)

        self.title_reset_button = QtWidgets.QPushButton(self.tr("Reset"), self)
        self.title_reset_button.clicked.connect(self.reset_title)

        self.palette = QColorPalette(parent=self)

        self.buttons = self.init_buttons()

        self.ui_setup()

    def init_buttons(self):
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        for btn in buttons.buttons():
            btn.setIcon(QIcon())

        return buttons

    def ui_setup(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        input_line = QtWidgets.QHBoxLayout()
        input_line.addWidget(self.title)
        input_line.addWidget(self.title_reset_button)

        main_layout.addLayout(input_line)
        main_layout.addWidget(self.palette)
        main_layout.addWidget(self.buttons)

    def reset_title(self):
        self.title.setText(self.original_title)

    @classmethod
    def get_edits(  # noqa: WPS211
        cls,
        parent,
        title,
        orig_title,
        cur_title,
        cur_color,
    ):
        dialog = cls(parent=parent)
        dialog.setWindowTitle(title)

        dialog.original_title = orig_title
        dialog.title.setText(cur_title)
        dialog.palette.color = cur_color

        if dialog.exec():
            new_title = dialog.title.text().strip() or cur_title
            new_color = dialog.palette.color.name(QColor.HexRgb)
            return new_title, new_color

        return cur_title, QColor(*cur_color).name(QColor.HexRgb)
