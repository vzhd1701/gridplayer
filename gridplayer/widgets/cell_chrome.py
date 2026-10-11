from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen

CHROME_ALPHA = 90
TEXT_ALPHA = 170

# The frame of a cell with no picture runs close round its edge, where the
# overlay's border runs round a video's, which leaves the overlay's controls
# where they are over a video, clear of it: a few pixels in, a line of two
# or three, its corners rounded a little more than the controls' boxes.
FRAME_MARGIN = 3.0
FRAME_STROKE_MIN = 2.0
FRAME_STROKE_MAX = 3.0
FRAME_RADIUS_MIN = 5.0
FRAME_RADIUS_MAX = 8.0

# the dashes of an empty cell's frame, longer in a larger cell, and the gaps
# between them as a share of them
FRAME_DASH_MIN = 8.0
FRAME_DASH_MAX = 18.0
FRAME_DASH_GAP = 0.6


def dashed_frame(widget):
    """The frame's line, along its middle, how thick it is, and how round
    its corners are."""

    side = min(widget.width(), widget.height())
    stroke = min(max(side / 200, FRAME_STROKE_MIN), FRAME_STROKE_MAX)
    margin = FRAME_MARGIN + stroke / 2
    rect = QRectF(widget.rect()).adjusted(margin, margin, -margin, -margin)
    radius = min(max(side * 0.02, FRAME_RADIUS_MIN), FRAME_RADIUS_MAX)
    return rect, stroke, radius


def _frame_dashes(widget, stroke: float) -> list[float]:
    """The dashes and gaps, in the pen's widths, as Qt has them; each dash
    drawn a pen's width longer for its round ends, taken off its gap."""

    side = min(widget.width(), widget.height())
    dash = min(max(side / 25, FRAME_DASH_MIN), FRAME_DASH_MAX)
    gap = dash * FRAME_DASH_GAP

    return [max(dash - stroke, 1.0) / stroke, (gap + stroke) / stroke]


def chrome_color(widget, alpha=CHROME_ALPHA) -> QColor:
    color = QColor(widget.palette().color(widget.foregroundRole()))
    color.setAlpha(alpha)
    return color


def chrome_color_on_cell(widget) -> QColor:
    """Opaque color matching dashed chrome composited on this cell."""
    fg = widget.palette().color(widget.foregroundRole())
    bg = widget.palette().color(widget.backgroundRole())
    t = CHROME_ALPHA / 255
    return QColor(
        round(fg.red() * t + bg.red() * (1 - t)),
        round(fg.green() * t + bg.green() * (1 - t)),
        round(fg.blue() * t + bg.blue() * (1 - t)),
    )


def paint_outline(
    widget,
    painter: QPainter | None = None,
    *,
    dashed: bool = True,
    is_active: bool = False,
) -> None:
    """The cell's frame: in the text's own grey for the active cell, where a
    cell with a picture has a border of the overlay's instead."""

    own_painter = painter is None
    if own_painter:
        painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    rect, stroke, radius = dashed_frame(widget)
    pen = QPen(chrome_color(widget, TEXT_ALPHA if is_active else CHROME_ALPHA))
    pen.setWidthF(stroke)
    if dashed:
        pen.setDashPattern(_frame_dashes(widget, stroke))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect, radius, radius)
    if own_painter:
        painter.end()


def paint_dashed_outline(widget, painter: QPainter | None = None) -> None:
    paint_outline(widget, painter, dashed=True)


def paint_solid_outline(
    widget, painter: QPainter | None = None, *, is_active: bool = False
) -> None:
    paint_outline(widget, painter, dashed=False, is_active=is_active)


def idle_disc_rect(widget) -> QRectF:
    side = max(min(widget.width(), widget.height()) * 0.6, 24.0)
    return QRectF(
        (widget.width() - side) / 2,
        (widget.height() - side) / 2,
        side,
        side,
    )


def paint_idle_disc(widget, painter: QPainter | None = None) -> None:
    """The stopped cell's disc, a square cut out of it."""

    own_painter = painter is None
    if own_painter:
        painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    circle = idle_disc_rect(widget)
    painter.setPen(Qt.NoPen)
    painter.setBrush(chrome_color(widget))
    painter.drawEllipse(circle)

    side = circle.width() * 0.36
    square = QRectF(
        circle.center().x() - side / 2,
        circle.center().y() - side / 2,
        side,
        side,
    )
    radius = max(2.0, side * 0.12)
    painter.setBrush(widget.palette().color(widget.backgroundRole()))
    painter.drawRoundedRect(square, radius, radius)
    if own_painter:
        painter.end()
