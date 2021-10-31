import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QPainter, QPainterPath, QPen


def draw_volume_on(rect, painter, color):
    draw_volume_off(rect, painter, color)

    painter.fillRect(
        rect.x() + 5 + 6 + 3, rect.y() + 6, 4, rect.height() - 12, color  # noqa: WPS432
    )


def draw_volume_off(rect, painter, color):
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()

    path.moveTo(rect.x() + 5, round(rect.height() / 2) - 3)

    path.lineTo(rect.x() + 5 + 3, round(rect.height() / 2) - 3)
    path.lineTo(rect.x() + 5 + 6, 4)
    path.lineTo(rect.x() + 5 + 6, rect.height() - 4)
    path.lineTo(rect.x() + 5 + 3, round(rect.height() / 2) + 3)
    path.lineTo(rect.x() + 5, round(rect.height() / 2) + 3)

    path.lineTo(rect.x() + 5, round(rect.height() / 2) - 3)

    painter.setPen(Qt.NoPen)
    painter.fillPath(path, QBrush(color))


def draw_play(rect, painter, color):
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()

    path.moveTo(rect.x() + 5, rect.y() + 4)
    path.lineTo(rect.width() - 5, round(rect.height() / 2))
    path.lineTo(rect.x() + 5, rect.height() - 4)
    path.lineTo(rect.x() + 5, rect.y() + 4)

    painter.setPen(Qt.NoPen)
    painter.fillPath(path, QBrush(color))


def draw_pause(rect, painter, color):
    painter.fillRect(rect.x() + 5, rect.y() + 4, 5, rect.height() - 8, color)
    painter.fillRect(rect.width() - 5 - 5, rect.y() + 4, 5, rect.height() - 8, color)


def draw_cross(rect, painter, color):
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(color, 4))

    line_len = round(math.sqrt((rect.width() - 10) ** 2 + (rect.width() - 10) ** 2))

    painter.drawLine(
        rect.x() + 5,
        rect.y() + 5,
        rect.x() + line_len,
        rect.y() + line_len,
    )
    painter.drawLine(
        rect.x() + line_len,
        rect.y() + 5,
        rect.x() + 5,
        rect.y() + line_len,
    )
