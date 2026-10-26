from PyQt5.QtCore import QPointF, QRect, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.layout.free_tiles import MOVE, Handle
from gridplayer.widgets.grid_line_mark import EDGE_COLOR, FloatingMark

# how thick each kind of line is: the outline and where the tile started a
# hairline, the edges it is sized by a bar
OUTLINE = 1
LIT = 3

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

    def show_path(
        self,
        path: QPainterPath,
        pen: QPen,
        shaded: QRect | None = None,
        under: QPen | None = None,
    ) -> None:
        """The line along a path on the screen, drawn with the pen, over a
        shadow where it is in shaded (on the screen too), or over a line
        drawn with under."""

        rect = path.boundingRect().toAlignedRect()
        rect = rect.adjusted(-MARGIN, -MARGIN, MARGIN + 1, MARGIN + 1)

        local = path.translated(-QPointF(rect.topLeft()))
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

        if self._under is not None:
            painter.strokePath(self._path, self._under)
        painter.strokePath(self._path, self._pen)


def _line(x1, y1, x2, y2) -> QPainterPath:
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(x2, y2)
    return path


def _edges(rect: QRect) -> list[QPainterPath]:
    """The four sides of a rectangle on the screen, as hairlines along its
    outermost pixels, inside it."""

    left, top = rect.x() + 0.5, rect.y() + 0.5
    right = rect.x() + rect.width() - 0.5
    bottom = rect.y() + rect.height() - 0.5
    return [
        _line(left, top, right, top),
        _line(left, bottom, right, bottom),
        _line(left, top, left, bottom),
        _line(right, top, right, bottom),
    ]


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
    pen.setJoinStyle(Qt.RoundJoin)
    if dashes is not None:
        pen.setDashPattern(list(dashes))
    return pen


class TileFrame:
    """What the pointer is about to move or size in Free Tiles, or is: the
    tile's outline, the edges it is sized by lit, and while it is moved or
    sized, dashed where it started, which Esc puts it back to. On the
    screen, inside the tile's edges, where its overlay would draw; over
    the tiles in front of it too, to show all of its shape."""

    def __init__(self, parent: QWidget):
        self._parent = parent

        # made as they are first needed, the lit ones over the outline
        self._outline: list[_Piece] = []
        self._lit: list[_Piece] = []
        self._dashed: list[_Piece] = []

        self._pens = (
            _pen(DASHED_COLOR, OUTLINE, DASHES),
            _pen(GAP_COLOR, OUTLINE),
            _pen(LINE_COLOR, OUTLINE),
            _pen(LIT_COLOR, LIT),
        )
        # what is shown now, not to be made again for the same
        self._shown = None

    def show(self, rect: QRect, handle: Handle, start: QRect | None = None) -> None:
        """The tile at rect on the screen, sized by handle (or moved), from
        start, if it is being."""

        if (rect, handle, start) == self._shown:
            return
        self._shown = (rect, handle, start)

        dashed_pen, gap_pen, line_pen, lit_pen = self._pens
        dashed = [] if start is None or start == rect else _edges(start)
        self._show_lines(self._dashed, dashed, dashed_pen, under=gap_pen)
        self._show_lines(self._outline, _edges(rect), line_pen, shaded=rect)
        self._show_lines(self._lit, _lit(rect, handle), lit_pen, shaded=rect)

    def hide(self) -> None:
        self._shown = None
        for piece in (*self._outline, *self._lit, *self._dashed):
            if piece.isVisible():
                piece.hide()

    def _show_lines(self, pool, paths, pen, shaded=None, under=None) -> None:
        while len(pool) < len(paths):
            pool.append(_Piece(self._parent))

        for piece, path in zip(pool, paths):
            piece.show_path(path, pen, shaded, under)

        for piece in pool[len(paths) :]:
            if piece.isVisible():
                piece.hide()
