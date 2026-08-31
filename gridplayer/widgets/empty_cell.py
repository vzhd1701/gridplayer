from PyQt5.QtCore import QEvent, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QTextOption
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from gridplayer.params.static import FONT_SIZE_BIG_INFO
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.widgets.video_overlay_elements import OverlayDropIndicator

_CHROME_ALPHA = 90
_TEXT_ALPHA = 170


def _dashed_frame(widget):
    margin = max(6.0, min(widget.width(), widget.height()) / 12)
    rect = QRectF(widget.rect()).adjusted(margin, margin, -margin, -margin)
    stroke = max(2.0, margin / 4)
    radius = max(6.0, min(rect.width(), rect.height()) * 0.12)
    return rect, stroke, radius


class EmptyCell(QWidget):
    is_empty_cell = True

    def __init__(self, message=None, **kwargs):
        super().__init__(**kwargs)

        self._message = message

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if message:
            self.setFont(QFont("Hack", FONT_SIZE_BIG_INFO, QFont.Bold))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._drop_indicator = OverlayDropIndicator(parent=self)
        layout.addWidget(self._drop_indicator)
        self._apply_indicator_colors()

    def set_drop_indicator(self, indicator: DropIndicator):
        self._drop_indicator.set_indicator(indicator)
        if indicator != DropIndicator.NONE:
            self._drop_indicator.raise_()
        self.update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            self._apply_indicator_colors()

    def _chrome_color(self, alpha=_CHROME_ALPHA) -> QColor:
        color = QColor(self.palette().color(self.foregroundRole()))
        color.setAlpha(alpha)
        return color

    def _chrome_color_on_cell(self) -> QColor:
        """Opaque color matching dashed chrome composited on this cell."""
        fg = self.palette().color(self.foregroundRole())
        bg = self.palette().color(self.backgroundRole())
        t = _CHROME_ALPHA / 255
        return QColor(
            round(fg.red() * t + bg.red() * (1 - t)),
            round(fg.green() * t + bg.green() * (1 - t)),
            round(fg.blue() * t + bg.blue() * (1 - t)),
        )

    def _apply_indicator_colors(self):
        self._drop_indicator.set_colors(
            self._chrome_color_on_cell(),
            self.palette().color(self.backgroundRole()),
        )

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect, stroke, radius = _dashed_frame(self)

        pen = QPen(self._chrome_color())
        pen.setWidthF(stroke)
        pen.setStyle(Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        if self._drop_indicator.isVisible():
            return

        if self._message:
            self._paint_message(painter, rect, stroke)
            return

        self._paint_plus(painter, rect, stroke)

    def _paint_message(self, painter, rect, stroke):
        inset = stroke * 5
        text_rect = rect.adjusted(inset, inset, -inset, -inset)
        painter.setPen(self._chrome_color(_TEXT_ALPHA))
        painter.setFont(self.font())
        option = QTextOption()
        option.setAlignment(Qt.AlignCenter)
        option.setWrapMode(QTextOption.WordWrap)
        painter.drawText(text_rect, self._message, option)

    def _paint_plus(self, painter, rect, stroke):
        plus = max(8.0, min(rect.width(), rect.height()) / 4)
        bar = stroke
        cx, cy = rect.center().x(), rect.center().y()
        cap = bar / 2

        horizontal = QPainterPath()
        horizontal.addRoundedRect(
            QRectF(cx - plus, cy - bar / 2, plus * 2, bar), cap, cap
        )
        vertical = QPainterPath()
        vertical.addRoundedRect(
            QRectF(cx - bar / 2, cy - plus, bar, plus * 2), cap, cap
        )

        painter.setPen(Qt.NoPen)
        painter.fillPath(horizontal.united(vertical), self._chrome_color())
