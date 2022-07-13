import contextlib

from PyQt5.QtCore import QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QTextLayout
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QSizePolicy, QWidget

from gridplayer.utils.darkmode import is_dark_mode


class StatusInfo(QWidget):
    padding_lr = 10
    padding_tb = 5
    border_radius = 10

    # below that 10px font will get cropped
    min_text_box_height = 12

    min_font_size = 10
    max_font_size = 16

    def __init__(self, text="", **kwargs):
        super().__init__(**kwargs)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMouseTracking(True)

        effect = QGraphicsOpacityEffect(self)
        half_transparent = 0.5
        effect.setOpacity(half_transparent)
        self.setGraphicsEffect(effect)

        if is_dark_mode():
            self.text_color = Qt.black
            self.bg_color = Qt.white
            self.bo_color_progress = QColor(Qt.gray).lighter()
        else:
            self.text_color = Qt.white
            self.bg_color = Qt.black
            self.bo_color_progress = QColor(Qt.gray).darker()

        self.text = text
        self.percent = 0

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        self._text = text

        self.setToolTip(text)

        self._adjust_font(self.size())
        self.update()

    @property
    def percent(self):
        return self._percent

    @percent.setter
    def percent(self, percent):
        self._percent = min(max(percent, 0), 100)
        self.update()

    def minimumSizeHint(self):
        if self.minimumHeight() - self.padding_tb * 2 < self.min_text_box_height:
            return QSize(-1, self.maximumHeight())

        if self._is_text_fits_minimum():
            return QSize(-1, self.minimumHeight())

        return QSize(-1, self.maximumHeight())

    def resizeEvent(self, event) -> None:
        self._adjust_font(event.size())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self._paint_box(painter)
        self._paint_text(painter)

    def _paint_box(self, painter):
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.border_radius, self.border_radius)
        painter.setClipPath(path)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.bg_color))

        painter.drawRect(self.rect())

        if self.percent > 0:
            painter.setBrush(QColor(Qt.gray).darker())
            percent = self.percent / 100
            percent_width = int(self.width() * percent)
            percent_rect = QRect(0, 0, percent_width, self.height())
            painter.drawRect(percent_rect)

    def _paint_text(self, painter):
        painter.setPen(QColor(self.text_color))
        painter.setBrush(Qt.NoBrush)

        width = self.rect().width()
        height = self.rect().height()

        text_box = self._text_box_for_size(width, height)

        lines = self._get_lines_to_draw(painter.font(), text_box)
        painter.drawText(text_box, Qt.AlignCenter, "\n".join(lines))

    def _adjust_font(self, size):
        text_box_max = self._text_box_for_size(size.width(), self.maximumHeight())
        text_box_min = self._text_box_for_size(size.width(), self.minimumHeight())

        if size.height() == self.maximumHeight():
            self._maximize_font(text_box_max, single_line=False)

        else:
            self._maximize_font(text_box_min, single_line=True)

    def _maximize_font(self, text_box, single_line):
        max_font_size = self._calc_max_font_size(text_box, single_line)
        font = self.font()
        font.setPixelSize(max_font_size)
        self.setFont(font)

    def _calc_max_font_size(self, text_box, single_line):
        font = self.font()
        font_size = self.min_font_size

        while font_size <= self.max_font_size:
            font_size += 1
            font.setPixelSize(font_size)

            if self._is_font_too_big(font, text_box, single_line):
                break

            if font_size == self.max_font_size:
                return self.max_font_size

        return font_size - 1

    def _is_font_too_big(self, font, text_box, single_line):
        if QFontMetrics(font).lineSpacing() > text_box.height():
            return True

        lines = self._get_lines_to_draw(font, text_box)

        if single_line and len(lines) > 1:
            return True

        return lines[-1].endswith("…")

    def _text_box_for_size(self, width, height):
        return QRect(0, 0, width, height).adjusted(
            self.padding_lr, self.padding_tb, -self.padding_lr, -self.padding_tb
        )

    def _is_text_fits_minimum(self) -> bool:  # noqa: WPS210
        text_box_max = self._text_box_for_size(
            self.geometry().width(), self.maximumHeight()
        )
        text_box_min = self._text_box_for_size(
            self.geometry().width(), self.minimumHeight()
        )

        calc_steps = [
            (text_box_min, True),
            (text_box_max, True),
            (text_box_min, False),
            (text_box_max, False),
        ]

        font_size = self.min_font_size
        text_box_final = text_box_max

        for text_box, is_single_line in calc_steps:
            new_font_size = self._calc_max_font_size(
                text_box, single_line=is_single_line
            )
            if new_font_size > font_size:
                font_size = new_font_size
                text_box_final = text_box

        return text_box_final is text_box_min

    def _get_lines_to_draw(self, font, text_box, max_lines=3):
        multiliner = TextMultiliner(self.text, font)

        return multiliner.get_multiline_text(
            max_lines=max_lines,
            max_width=text_box.width(),
            max_height=text_box.height(),
        )


class TextMultiliner(object):
    def __init__(self, text, font):
        self.font_metrics = QFontMetrics(font)
        self.line_spacing = self.font_metrics.lineSpacing()
        self.text_layout = QTextLayout(text, font)

        self.text = text

        self._lines = []
        self._cur_y = 0
        self._is_last_line = False

    @contextlib.contextmanager
    def text_layout_ctx(self):
        self.text_layout.beginLayout()
        yield
        self.text_layout.endLayout()

    def get_multiline_text(self, max_lines, max_width, max_height):
        self._lines = []
        self._cur_y = 0
        self._is_last_line = False

        with self.text_layout_ctx():
            while True:
                line = self._get_next_line(max_lines, max_width, max_height)

                if line is None:
                    break

                self._lines.append(line)

        return self._lines

    def _get_next_line(self, max_lines, max_width, max_height):
        line = self.text_layout.createLine()

        if self._is_last_line or not line.isValid():
            return None

        line.setLineWidth(max_width)

        next_line_y = self._cur_y + self.line_spacing

        can_fit_another_line = max_height >= next_line_y + self.line_spacing

        if can_fit_another_line and len(self._lines) < max_lines - 1:
            self._cur_y = next_line_y

            return self.text[line.textStart() : line.textStart() + line.textLength()]

        self._is_last_line = True

        last_line = self.text[line.textStart() :]
        return self.font_metrics.elidedText(last_line, Qt.ElideRight, max_width)
