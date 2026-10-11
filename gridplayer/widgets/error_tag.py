"""The tag of an error in a dialog: where it broke, filled in the theme's
border grey, and its code after it, rimmed as one."""

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import QSizePolicy, QWidget

from gridplayer.params.theme import current_colors

PADDING = 5
HEIGHT = 18
RADIUS = 3


def tag_widths(
    metrics: QFontMetrics, where: str, code: str, padding: float
) -> tuple[float, float]:
    """How wide its two parts are, either of them 0 left out."""

    where_width = metrics.horizontalAdvance(where) + padding * 2 if where else 0
    code_width = metrics.horizontalAdvance(code) + padding * 2 if code else 0

    return where_width, code_width


def paint_tag(
    painter: QPainter,
    rect: QRectF,
    where: str,
    code: str,
    widths: tuple[float, float],
    radius: float,
    fill: QColor,
    where_color: QColor,
    code_color: QColor,
):
    """The tag in rect, in the painter's font: where it broke filled, and
    its code after it, rimmed as one in the fill's colour."""

    where_width, code_width = widths

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    if where:
        where_rect = QRectF(rect.left(), rect.top(), where_width, rect.height())

        painter.setClipRect(where_rect)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)
        painter.setClipping(False)

        painter.setPen(where_color)
        painter.drawText(where_rect, Qt.AlignCenter, where)

    if code:
        painter.setPen(code_color)
        painter.drawText(
            QRectF(rect.left() + where_width, rect.top(), code_width, rect.height()),
            Qt.AlignCenter,
            code,
        )

    painter.setPen(QPen(fill, 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.restore()


class ErrorTag(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._where = ""
        self._code = ""

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_tag(self, where: str, code: str):
        self._where = where
        self._code = code

        self.setVisible(bool(where or code))
        self.updateGeometry()
        self.update()

    @property
    def tag(self) -> tuple[str, str]:
        return self._where, self._code

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(font.pointSizeF() - 1, 7))
        return font

    def _widths(self) -> tuple[float, float]:
        return tag_widths(QFontMetrics(self._font()), self._where, self._code, PADDING)

    def sizeHint(self) -> QSize:
        return QSize(sum(self._widths()) + 1, HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        colors = current_colors()
        text = QColor(colors["text"])

        widths = self._widths()

        painter = QPainter(self)
        painter.setFont(self._font())
        paint_tag(
            painter,
            QRectF(0, 0, sum(widths) + 1, HEIGHT),
            self._where,
            self._code,
            widths,
            RADIUS,
            QColor(colors["border"]),
            text,
            text,
        )
