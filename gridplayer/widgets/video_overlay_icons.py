import math

from PyQt5.QtCore import QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen


def draw_volume_on(rect, painter, color_fg, color_bg):
    draw_volume_off(rect, painter, color_fg, color_bg)

    painter.fillRect(
        rect.x() + 5 + 6 + 3, rect.y() + 6, 4, rect.height() - 12, color_fg
    )


def draw_volume_off(rect, painter, color_fg, color_bg):
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
    painter.fillPath(path, QBrush(color_fg))


def draw_play(rect, painter, color_fg, color_bg):
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()

    path.moveTo(rect.x() + 5, rect.y() + 4)
    path.lineTo(rect.width() - 5, round(rect.height() / 2))
    path.lineTo(rect.x() + 5, rect.height() - 4)
    path.lineTo(rect.x() + 5, rect.y() + 4)

    painter.setPen(Qt.NoPen)
    painter.fillPath(path, QBrush(color_fg))


def draw_pause(rect, painter, color_fg, color_bg):
    painter.fillRect(rect.x() + 5, rect.y() + 4, 5, rect.height() - 8, color_fg)
    painter.fillRect(rect.width() - 5 - 5, rect.y() + 4, 5, rect.height() - 8, color_fg)


def draw_stop(rect, painter, color_fg, color_bg):
    """A square as wide as play and pause are, as heavy as pause looks."""

    painter.setRenderHint(QPainter.Antialiasing, True)

    side = rect.width() - 10
    square = QRectF(rect.x() + 5, rect.y() + (rect.height() - side) // 2, side, side)

    painter.setPen(Qt.NoPen)
    painter.setBrush(color_fg)
    painter.drawRoundedRect(square, 1.5, 1.5)


def draw_cross(rect, painter, color_fg, color_bg):
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(color_fg, 4))

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


def _draw_arrows(rect, painter, color_fg, is_out):
    """Two arrows along the diagonal: out to the corners, or in from them
    to the middle.

    Each a single path, so that where its lines meet a see-through colour
    is not laid on twice; its head's sides on whole pixels, to be sharp.
    """

    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    box = QRectF(QRect(rect).adjusted(6, 6, -6, -6))
    center = box.center()
    head = round(box.width() * 0.4)
    gap = 1.5

    for corner, sign_x, sign_y in (
        (box.topRight(), 1, -1),
        (box.bottomLeft(), -1, 1),
    ):
        near = QPointF(center.x() + sign_x * gap, center.y() + sign_y * gap)
        tip, tail = (corner, near) if is_out else (near, corner)
        if not is_out:
            tip = QPointF(round(tip.x()), round(tip.y()))

        # the head's two sides, back from its tip along the axes, and the
        # shaft
        back = -1 if is_out else 1
        path = QPainterPath()
        path.moveTo(tip.x() + back * sign_x * head, tip.y())
        path.lineTo(tip)
        path.lineTo(tip.x(), tip.y() + back * sign_y * head)
        path.moveTo(tip)
        path.lineTo(tail)
        painter.drawPath(path)


def draw_grow(rect, painter, color_fg, color_bg):
    _draw_arrows(rect, painter, color_fg, is_out=True)


def draw_shrink(rect, painter, color_fg, color_bg):
    _draw_arrows(rect, painter, color_fg, is_out=False)


def draw_cell_size(rect, painter, color_fg, color_bg):
    """A grid of two by two, its first cell filled: a cell's size picked.
    Its lines on whole pixels, to be sharp."""

    painter.setRenderHint(QPainter.Antialiasing, True)

    box = QRectF(QRect(rect).adjusted(6, 6, -6, -6))
    half = round(box.width() / 2)

    painter.setPen(Qt.NoPen)
    painter.setBrush(color_fg)
    painter.drawRect(QRectF(box.topLeft(), box.center()))

    painter.setPen(QPen(color_fg, 2))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(box, 1.5, 1.5)
    painter.drawLine(
        QPointF(box.left() + half, box.top()), QPointF(box.left() + half, box.bottom())
    )
    painter.drawLine(
        QPointF(box.left(), box.top() + half), QPointF(box.right(), box.top() + half)
    )


def draw_list(rect, painter, color_fg, color_bg):
    """Three lines, the list's sign."""

    thickness = max(2, round(rect.height() / 4.5))

    for row in range(3):
        y = rect.y() + (rect.height() - thickness) * row // 2
        painter.fillRect(rect.x(), y, rect.width(), thickness, color_fg)


def draw_spin_circle(
    rect: QRect, painter: QPainter, color_fg: QColor, color_bg: QColor, spin: int
):
    painter.setRenderHint(QPainter.Antialiasing, True)

    rect_spin = rect.adjusted(5, 5, -5, -5)

    # a ring with a gap going round, drawn rather than cut out of the ring:
    # the box under it may let the picture through
    painter.setPen(QPen(color_fg, 3, Qt.SolidLine, Qt.RoundCap))
    painter.drawArc(rect_spin, (-spin + 90) * 16, 16 * 270)
