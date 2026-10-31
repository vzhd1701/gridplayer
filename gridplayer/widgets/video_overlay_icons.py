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
    painter.setPen(_line_pen(color_fg))
    painter.setBrush(Qt.NoBrush)

    box = _icon_box(rect)
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

    box = _icon_box(rect)
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


def _icon_box(rect) -> QRectF:
    return QRectF(QRect(rect).adjusted(6, 6, -6, -6))


def _line_pen(color_fg) -> QPen:
    return QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _part(box: QRectF, left, top, right, bottom) -> QRectF:
    # a part of the box, its edges as shares of the box's width and height
    return QRectF(
        box.left() + left * box.width(),
        box.top() + top * box.height(),
        (right - left) * box.width(),
        (bottom - top) * box.height(),
    )


def _draw_corners(painter, color_fg, box: QRectF, arm: float):
    """The four corners of a box, each a line along either edge."""

    path = QPainterPath()
    for corner, sign_x, sign_y in (
        (box.topLeft(), 1, 1),
        (box.topRight(), -1, 1),
        (box.bottomRight(), -1, -1),
        (box.bottomLeft(), 1, -1),
    ):
        path.moveTo(corner.x() + sign_x * arm, corner.y())
        path.lineTo(corner)
        path.lineTo(corner.x(), corner.y() + sign_y * arm)

    painter.setPen(_line_pen(color_fg))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)


def _fill(painter, color_fg, box: QRectF):
    painter.setPen(Qt.NoPen)
    painter.setBrush(color_fg)
    painter.drawRect(box)


def draw_fill_space(rect, painter, color_fg, color_bg):
    """A tile in the middle and the corners of the room round it: the tile
    made as big as the room. As the icon grid-fill-space."""

    painter.setRenderHint(QPainter.Antialiasing, True)

    box = _icon_box(rect)
    _draw_corners(painter, color_fg, box, box.width() * 0.26)
    _fill(painter, color_fg, _part(box, 0.34, 0.34, 0.66, 0.66))


def draw_fit_video(rect, painter, color_fg, color_bg):
    """A picture and the corners of the tile close round it: the tile made
    the picture's shape. As the icon grid-fit-tile."""

    painter.setRenderHint(QPainter.Antialiasing, True)

    # opened up from the icon's, the button's being so small
    box = _icon_box(rect)
    _draw_corners(painter, color_fg, _part(box, 0, 0.16, 1, 0.84), box.width() * 0.28)
    _fill(painter, color_fg, _part(box, 0.26, 0.38, 0.74, 0.62))


def draw_lock(rect, painter, color_fg, color_bg):
    """A padlock: the tile locked."""

    painter.setRenderHint(QPainter.Antialiasing, True)

    box = _icon_box(rect)
    body = QRectF(box.left(), box.top() + box.height() * 0.45, box.width(), 0)
    body.setBottom(box.bottom())

    shackle = box.width() * 0.6
    arc = QRectF(box.center().x() - shackle / 2, box.top(), shackle, box.height() * 0.6)
    path = QPainterPath()
    path.moveTo(arc.left(), body.top())
    path.lineTo(arc.left(), arc.center().y())
    path.arcTo(arc, 180, -180)
    path.lineTo(arc.right(), body.top())

    painter.setPen(_line_pen(color_fg))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    painter.setPen(Qt.NoPen)
    painter.setBrush(color_fg)
    painter.drawRoundedRect(body, 1.5, 1.5)


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
