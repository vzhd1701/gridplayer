from collections.abc import Callable
from typing import NamedTuple

from PyQt5.QtCore import QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QRegion,
)
from PyQt5.QtWidgets import QWidget

from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.layout.free_tiles import MOVE, Handle
from gridplayer.widgets.grid_line_mark import (
    EDGE_COLOR,
    FloatingMark,
    show_pooled,
)
from gridplayer.widgets.video_overlay_elements import (
    DISC_LEAST,
    DISC_SHARE,
    disc_line,
    paint_faded,
)

# how thick each kind of line is: the outline and where the tile started a
# hairline, the edges it is sized by a bar
OUTLINE = 1
LIT = 3
# where the tile would land, in Mosaic: its line, and how round its
# corners
LANDING = 2
LANDING_ROUND = 4

# the bar lit: how far in from the tile's edge, how far short of a side's
# ends, how long each arm of a corner's at most, and how round its bend
LIT_INSET = 3
LIT_SHORT = 8
LIT_ARM = 34
LIT_BEND = 6

# where the tile started: each dash, and the gap after it, in its widths
DASHES = (4, 3)

LINE_COLOR = QColor(255, 255, 255, 220)
LIT_COLOR = QColor("#f4f4f4")
DASHED_COLOR = QColor("#eeeeee")
# between the dashes, seen on a light ground as they are on a dark one
GAP_COLOR = QColor(17, 17, 17, 200)

# a soft shadow under the outline and the lit edges, inside the tile only,
# seen on any picture with the edge outside it sharp: widths beyond the
# line's own, each as dark
SHADOW = ((4, 40), (2, 70))
# room around a line for its shadow, in its window
MARGIN = 4

# the mark on a locked tile, as a drop's is on a cell (see OverlayDiscBadge):
# let through as much as an overlay over a video is
LOCK_DISC_OPACITY = 0.5
DISC_COLOR = QColor(0, 0, 0)
GLYPH_COLOR = QColor(255, 255, 255)


class _Line(NamedTuple):
    """A line of a tile's frame, as one piece shows it: the path, on the
    screen, and the window that shows what of it is there."""

    path: QPainterPath
    window: QRect


def _window_around(path: QPainterPath) -> QRect:
    # with room for the line's width and its shadow
    rect = path.boundingRect().toAlignedRect()
    return rect.adjusted(-MARGIN, -MARGIN, MARGIN + 1, MARGIN + 1)


def _alone(path: QPainterPath) -> _Line:
    return _Line(path, _window_around(path))


class _Piece(FloatingMark):
    """One line of a tile's frame: a side of the outline, the lit edges,
    or a side of where it started, seen over the tiles in front too.
    See-through around the line, where something draws see-through
    windows; else on its shadow's dark."""

    def __init__(self, parent):
        super().__init__(parent)

        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)

        self._path = QPainterPath()
        self._pen = QPen()
        self._shaded = QRect()
        self._under: QPen | None = None
        # the lines drawn, as shapes filled with their colours
        self._strokes: list[tuple[QPainterPath, QColor]] = []

    def show_path(
        self,
        line: _Line,
        strokes: Callable[[QPainterPath], list[tuple[QPainterPath, QColor]]],
        pen: QPen,
        shaded: QRect | None = None,
        under: QPen | None = None,
    ) -> None:
        """The line on the screen, drawn with the pen, over a shadow where
        it is in shaded (on the screen too), or over a line drawn with
        under. What is drawn of its path, as shapes on the screen, is asked
        of strokes (see _strokes): the pieces of a frame share it."""

        rect = line.window
        offset = QPointF(rect.topLeft())
        local = line.path.translated(-offset)
        shaded = QRect() if shaded is None else shaded.translated(-rect.topLeft())
        if (local, pen, shaded, under) != (
            self._path,
            self._pen,
            self._shaded,
            self._under,
        ):
            self._path = local
            self._pen = pen
            self._shaded = shaded
            self._under = under
            self._strokes = [
                (stroke.translated(-offset), color)
                for stroke, color in strokes(line.path)
            ]
            self.update()

        self.show_at(rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._is_translucent:
            painter.fillRect(self.rect(), EDGE_COLOR)

        if not self._shaded.isEmpty():
            painter.save()
            painter.setClipRect(self._shaded)
            width = self._pen.widthF()
            for extra, alpha in SHADOW:
                shadow = QPen(QColor(0, 0, 0, alpha), width + extra)
                shadow.setCapStyle(self._pen.capStyle())
                shadow.setJoinStyle(Qt.RoundJoin)
                painter.strokePath(self._path, shadow)
            painter.restore()

        for stroke, color in self._strokes:
            painter.fillPath(stroke, color)


def _strokes(
    path: QPainterPath, pen: QPen, under: QPen | None = None
) -> list[tuple[QPainterPath, QColor]]:
    """A line along a path drawn with the pen, over one drawn with under,
    as shapes to fill: a hairline stroked is drawn side by side, each
    corner only partly."""

    return [
        (QPainterPathStroker(each).createStroke(path), each.color())
        for each in (under, pen)
        if each is not None
    ]


def _line(x1, y1, x2, y2) -> QPainterPath:
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(x2, y2)
    return path


def _edges(rect: QRect, width: float = OUTLINE) -> list[QPainterPath]:
    """The four sides of a rectangle on the screen, as lines this thick
    along its outermost pixels, inside it."""

    inset = width / 2
    left, top = rect.x() + inset, rect.y() + inset
    right = rect.x() + rect.width() - inset
    bottom = rect.y() + rect.height() - inset
    return [
        _line(left, top, right, top),
        _line(left, bottom, right, bottom),
        _line(left, top, left, bottom),
        _line(right, top, right, bottom),
    ]


def _sides(rect: QRect, width: float = OUTLINE, round_by: float = 0) -> list[_Line]:
    """A rectangle's outline on the screen, as a line this thick along its
    outermost pixels, inside it, its corners this round: a piece for each
    side, each window showing its part of the whole line, the top and the
    bottom ones the corners. Put together, it is drawn once, each pixel
    by one window: a corner as it would be in one go, not one side's end
    and its shadow drawn over another's."""

    inset = width / 2
    whole = QPainterPath()
    inner = QRectF(rect).adjusted(inset, inset, -inset, -inset)
    if round_by:
        whole.addRoundedRect(inner, round_by, round_by)
    else:
        whole.addRect(inner)

    top, bottom, left, right = (_window_around(side) for side in _edges(rect, width))
    lines = [_Line(whole, top), _Line(whole, bottom)]
    for side in (left, right):
        # between the top's and the bottom's
        side.setTop(top.bottom() + 1)
        side.setBottom(bottom.top() - 1)
        if not side.isEmpty():
            lines.append(_Line(whole, side))
    return lines


def _lit(rect: QRect, handle: Handle) -> list[QPainterPath]:
    """The edges a tile is sized by from this handle, lit: a bar a little in
    from a side, short of its ends; at a corner, a rounded bend."""

    side_x, side_y = handle
    if handle == MOVE:
        return []

    # the middle of the bar, in from each edge
    inset = LIT_INSET + LIT / 2
    left, top = rect.x() + inset, rect.y() + inset
    right = rect.x() + rect.width() - inset
    bottom = rect.y() + rect.height() - inset
    x = left if side_x < 0 else right
    y = top if side_y < 0 else bottom

    if not side_y:
        return [_line(x, top + LIT_SHORT, x, bottom - LIT_SHORT)]
    if not side_x:
        return [_line(left + LIT_SHORT, y, right - LIT_SHORT, y)]

    # each arm a third of the shorter edge at most, out from the corner
    arm = min(LIT_ARM, min(rect.width(), rect.height()) / 3)
    bend = min(LIT_BEND, arm)
    path = QPainterPath(QPointF(x, y + side_y * -arm))
    path.lineTo(x, y + side_y * -bend)
    path.quadTo(x, y, x + side_x * -bend, y)
    path.lineTo(x + side_x * -arm, y)
    return [path]


def _pen(color: QColor, width: float, dashes=None) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.FlatCap if width == OUTLINE else Qt.RoundCap)
    # a square corner filled to its last pixel; a round one is rounded anyway
    pen.setJoinStyle(Qt.MiterJoin)
    if dashes is not None:
        pen.setDashPattern(list(dashes))
    return pen


class TileFrame:
    """What the pointer is about to move or size in Free Tiles, or is: the
    tile's outline, the edges it is sized by lit, and while it is moved or
    sized, dashed where it started, which Esc puts it back to; in Mosaic,
    a thicker line where it would land, let go of now, if not where it
    is, its corners round. On the screen, inside the tile's edges, where
    its overlay would draw; over the tiles in front of it too, to show all
    of its shape. Each is a window of its own for each side (see _sides),
    not one over the whole tile: with nothing to draw see-through
    windows, it would cover the picture."""

    def __init__(self, parent: QWidget):
        self._parent = parent

        # made as they are first needed, the lit ones over the outline
        self._outline: list[_Piece] = []
        self._lit: list[_Piece] = []
        self._dashed: list[_Piece] = []
        self._landing: list[_Piece] = []

        self._pens = (
            _pen(DASHED_COLOR, OUTLINE, DASHES),
            _pen(GAP_COLOR, OUTLINE),
            _pen(LINE_COLOR, OUTLINE),
            _pen(LIT_COLOR, LIT),
        )
        self._landing_pen = _pen(LIT_COLOR, LANDING)
        # what is shown now, not to be made again for the same
        self._shown = None

    def show(
        self,
        rect: QRect,
        handle: Handle,
        start: QRect | None = None,
        landing: QRect | None = None,
    ) -> None:
        """The tile at rect on the screen, sized by handle (or moved), from
        start, if it is being, to land at landing, if not where it is."""

        if (rect, handle, start, landing) == self._shown:
            return
        self._shown = (rect, handle, start, landing)

        dashed_pen, gap_pen, line_pen, lit_pen = self._pens
        dashed = [] if start is None or start == rect else _sides(start)
        self._show_lines(self._dashed, dashed, dashed_pen, under=gap_pen)
        lands = []
        if landing is not None and landing != rect:
            lands = _sides(landing, LANDING, LANDING_ROUND)
        self._show_lines(self._landing, lands, self._landing_pen, shaded=landing)
        self._show_lines(self._outline, _sides(rect), line_pen, shaded=rect)
        lit = [_alone(path) for path in _lit(rect, handle)]
        self._show_lines(self._lit, lit, lit_pen, shaded=rect)

    def hide(self) -> None:
        self._shown = None
        for piece in (*self._outline, *self._lit, *self._dashed, *self._landing):
            if piece.isVisible():
                piece.hide()

    def _show_lines(self, pool, paths, pen, shaded=None, under=None) -> None:
        # a frame's sides share one path: drawn once for them all, by the
        # first piece it changed for
        drawn: dict[int, list[tuple[QPainterPath, QColor]]] = {}

        def strokes(path: QPainterPath) -> list[tuple[QPainterPath, QColor]]:
            if id(path) not in drawn:
                drawn[id(path)] = _strokes(path, pen, under)
            return drawn[id(path)]

        show_pooled(
            pool,
            lambda: _Piece(self._parent),
            paths,
            lambda piece, line: piece.show_path(line, strokes, pen, shaded, under),
        )


def _lock(disc: QRectF) -> QPainterPath:
    """A lock in a disc, as the drop's glyphs are, its line as thick: its
    shackle's line made a shape, its body, and the keyhole cut out of it."""

    radius = disc.width() / 2
    x, y = disc.center().x(), disc.center().y()
    stroke = disc_line(radius)

    def at(dx: float, dy: float) -> QPointF:
        return QPointF(x + dx * radius, y + dy * radius)

    # the legs, from in the body up to where the shackle bends
    legs, bend = 0.24, -0.2
    line = QPainterPath(at(-legs, 0.1))
    line.lineTo(at(-legs, bend))
    line.arcTo(QRectF(at(-legs, bend - legs), at(legs, bend + legs)), 180, -180)
    line.lineTo(at(legs, 0.1))

    stroker = QPainterPathStroker()
    stroker.setWidth(stroke)
    stroker.setCapStyle(Qt.FlatCap)
    stroker.setJoinStyle(Qt.RoundJoin)

    body = QPainterPath()
    body.addRoundedRect(QRectF(at(-0.4, -0.02), at(0.4, 0.52)), stroke, stroke)

    # a slot as wide as most of the line, round at its ends
    hole = QPainterPath()
    width = stroke * 0.8
    slot = QRectF(x - width / 2, y + 0.12 * radius, width, 0.26 * radius)
    hole.addRoundedRect(slot, width / 2, width / 2)

    return stroker.createStroke(line).united(body).subtracted(hole)


class _LockBadge(FloatingMark):
    """A lock on a dark disc, filling the window, in the middle of a locked
    tile: let through as an overlay is, where something draws see-through
    windows; else solid, the window cut to the disc."""

    def __init__(self, parent):
        super().__init__(parent)

        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)

    def resizeEvent(self, event) -> None:
        if not self._is_translucent:
            self.setMask(QRegion(self.rect(), QRegion.Ellipse))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._is_translucent:
            paint_faded(painter, self.rect(), LOCK_DISC_OPACITY, self._paint_disc)
        else:
            self._paint_disc(painter)

    def _paint_disc(self, painter: QPainter) -> None:
        disc = QRectF(self.rect())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(DISC_COLOR)
        painter.drawEllipse(disc)
        painter.fillPath(_lock(disc), GLYPH_COLOR)


class TileLocks:
    """The locked tiles, marked while another is moved or sized: those it
    stops at, or goes nowhere near."""

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._badges: list[_LockBadge] = []

    def show(self, rects: list[QRect]) -> None:
        """A mark in the middle of each tile at rects, on the screen."""

        def show(badge, rect):
            side = round(max(min(rect.width(), rect.height()) * DISC_SHARE, DISC_LEAST))
            box = QRect(0, 0, side, side)
            box.moveCenter(rect.center())
            badge.show_at(box)

        show_pooled(self._badges, lambda: _LockBadge(self._parent), rects, show)

    def hide(self) -> None:
        self.show([])
