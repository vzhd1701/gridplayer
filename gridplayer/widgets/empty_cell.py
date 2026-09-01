from PyQt5.QtCore import QEvent, QRectF, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt5.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from gridplayer.params.static import FONT_SIZE_BIG_INFO
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.widgets.video_overlay_elements import OverlayDropIndicator

_CHROME_ALPHA = 90
_TEXT_ALPHA = 170


def _dashed_frame(widget):
    margin = max(6.0, min(widget.width(), widget.height()) / 24)
    rect = QRectF(widget.rect()).adjusted(margin, margin, -margin, -margin)
    stroke = min(6, max(2.0, margin / 4))
    radius = max(6.0, min(rect.width(), rect.height()) * 0.06)
    return rect, stroke, radius


class EmptyCell(QWidget):
    is_empty_cell = True

    def __init__(self, message=None, **kwargs):
        super().__init__(**kwargs)

        self._message = message

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._drop_indicator = OverlayDropIndicator(parent=self)
        layout.addWidget(self._drop_indicator)

        self._message_label = None

        if self._message:
            self._message_label = QLabel(
                self._message,
                parent=self.parent(),
            )
            self._message_label.setAlignment(Qt.AlignCenter)
            self._message_label.setWordWrap(True)
            self._message_label.setMargin(20)
            font = QFont("Hack", FONT_SIZE_BIG_INFO, QFont.Bold)
            self._message_label.setFont(font)

            layout.addWidget(self._message_label)

        self._apply_colors()

    def set_drop_indicator(self, indicator: DropIndicator):
        self._drop_indicator.set_indicator(indicator)
        if self._message_label:
            self._message_label.setVisible(indicator == DropIndicator.NONE)
        if indicator != DropIndicator.NONE:
            self._drop_indicator.raise_()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_label_margins()

    def _update_label_margins(self):
        if not self._message_label:
            return
        _, stroke, _ = _dashed_frame(self)
        margin = max(6.0, min(self.width(), self.height()) / 24)
        inset = stroke * 5
        pad = round(margin + inset)
        self.layout().setContentsMargins(pad, pad, pad, pad)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            self._apply_colors()

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

    def _apply_colors(self):
        self._drop_indicator.set_colors(
            self._chrome_color_on_cell(),
            self.palette().color(self.backgroundRole()),
        )

        if self._message_label:
            color = self._chrome_color(_TEXT_ALPHA)
            self._message_label.setStyleSheet(
                f"color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
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
            return

        self._paint_plus(painter, rect, stroke)

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
