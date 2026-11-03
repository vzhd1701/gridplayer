"""Free Tiles' Arrange: the tiles not locked laid out anew around those that
are.

The room the locked tiles leave is cut along their edges into pieces, each
cut going right across what it cuts. The videos are shared out among the
pieces in the order they are read, and each piece is laid out as Fit Shapes
lays out the window. Of the ways to cut the room, the one that shows the
videos best is kept.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable, Mapping, Sequence
from itertools import accumulate, combinations, pairwise, product
from typing import NamedTuple

from gridplayer.utils.layout.boxes import Box
from gridplayer.utils.layout.flow_layout import (
    DEFAULT_SHAPE,
    FlowLayout,
    FlowMode,
    reorder_candidates,
)
from gridplayer.utils.layout.free_tiles import Rect, read_in_rows
from gridplayer.utils.layout.justified import STRETCH_WORTH, Split, best_splits
from gridplayer.utils.layout.lines import MIN_CELL

# how much of each picture a piece's tiles may leave out to fill it, in
# percent: the least that does, as far as the limit allows
FILL_CROPS = (0, 5, 10, 15, 20, 25, 30, 40, 50)
# the share of a piece its tiles must cover to fill it
FILLED = 0.999

# how many times the tiles are laid out at most, each time read where they
# went, till they stay
ARRANGE_ROUNDS = 8

# with Reorder to Fit, how many orders two videos swapped are tried at most:
# a count, not a time, for the same tiles to be arranged the same each time
REORDER_TRIES = 200

# in pixels, what is too little to count
_HAIR = 1e-6

# in pixels, two edges this near are taken to be in line, and walls this far
# into each other or into a piece are not over it (as Rect.overlaps has it)
_NEAR = 0.5

SplitFinder = Callable[[tuple, tuple | None], tuple[Split, ...]]


class _Laid(NamedTuple):
    """Videos laid out in a piece: how well that shows them (see
    _tile_score), and where each goes, in the area's pixels."""

    score: float
    rects: dict[str, Rect]


# how many of the lines' splits ArrangeCache keeps, the last found
SPLITS_KEPT = 2048


class ArrangeCache:
    """What arrange_around works out, kept from one call to the next for
    the same videos, shapes and crop limit: the lines' splits, which do not
    change as the pieces do. Kept while a tile is held, the others arranged
    around it as it goes."""

    def __init__(self):
        self.find_splits: SplitFinder = functools.lru_cache(maxsize=SPLITS_KEPT)(
            best_splits.__wrapped__
        )


def arrange_around(
    width: float,
    height: float,
    walls: Sequence[Rect],
    ids: Sequence[str],
    at: Mapping[str, Rect],
    shapes: Mapping[str, float],
    crop_limit: int,
    is_reordered: bool = False,
    cache: ArrangeCache | None = None,
) -> dict[str, Box] | None:
    """Where each video goes, as shares of an area of this size, around
    the walls in it (the locked tiles; all of these in pixels). Each
    picture is cut by up to crop_limit percent to fill the room, and by no
    more than that does. None if the walls leave no room for a tile.

    The videos go in the order their tiles are read where they are now
    (at), piece by piece (see _read_by_piece); those with none after them,
    in the order of ids. Laid out again, read where they went, until they
    stay: arranged once more, they are left be. Reordered, they go in the
    order that shows them best, wherever their tiles are (see _reordered).
    shapes has each video's width for its height; a video not in it is
    taken to be DEFAULT_SHAPE. cache keeps what was worked out, for the
    same videos, shapes and crop limit (see ArrangeCache).
    """

    if not ids:
        return {}

    area = Rect(0, 0, width, height)
    # with no walls, all of it, however small
    cuts: list[list[Rect]] = [] if walls else [[area]]
    for is_down in (True, False) if walls else ():
        pieces = open_pieces(area, walls, is_down)
        if pieces and pieces not in cuts:
            cuts.append(pieces)
    if not cuts:
        return None

    # none cut, at the least
    crops = tuple(crop for crop in FILL_CROPS if crop <= max(crop_limit, 0))
    # each run of videos laid out in a piece once, for all the rounds
    if cache is None:
        find_splits = functools.cache(best_splits.__wrapped__)
    else:
        find_splits = cache.find_splits
    laid: dict[tuple, _Laid] = {}
    sharings = [_Sharing(pieces, shapes, crops, find_splits, laid) for pieces in cuts]

    def laid_out(at: Mapping[str, Rect]) -> dict[str, Rect]:
        found = []
        for sharing in sharings:
            pieces = sharing.pieces
            if is_reordered:
                order, counts = _reordered(sharing, ids, shapes)
                found.append(sharing.laid(order, counts))
            else:
                rows = _read_by_piece(pieces, ids, at, is_columns=False)
                columns = _read_by_piece(pieces, ids, at, is_columns=True)
                counts = sharing.climb(rows, column_ids=columns)[0]
                found.append(sharing.laid(rows, counts, columns))
        # on a tie, the first
        return max(found, key=lambda laid: laid.score).rects

    rects = laid_out(at)
    # reordered, where they are counts for nothing: once is enough
    for _ in range(ARRANGE_ROUNDS - 1 if not is_reordered else 0):
        again = laid_out(rects)
        if again == rects:
            break
        rects = again

    return {video_id: rect.as_box(width, height) for video_id, rect in rects.items()}


def open_pieces(area: Rect, walls: Sequence[Rect], is_down: bool) -> list[Rect]:
    """The room in the area the walls leave, cut along their edges, in the
    order the pieces are read; those too small for a tile left out.

    It is cut right across, down (is_down) where it can be, else along,
    then each part the other way, and so on, until no part has a wall in
    it. Where the walls lock into each other, leaving no line right across,
    only the biggest room between them is kept.
    """

    pieces = [
        piece
        for piece in _cut(area, walls, is_down)
        if min(piece.width, piece.height) >= MIN_CELL
    ]
    return [pieces[i] for i in read_in_rows(dict(enumerate(pieces)))]


def _cut(area: Rect, walls: Sequence[Rect], is_down: bool) -> list[Rect]:
    inside = [wall for wall in walls if wall.overlaps(area)]
    if not inside:
        return [area]
    if any(area.is_inside(wall) for wall in inside):
        return []

    for down in (is_down, not is_down):
        lines = _lines_across(area, inside, down)
        if lines:
            return [
                piece
                for part in _parts(area, lines, down)
                for piece in _cut(part, inside, not down)
            ]

    room = _biggest_room(area, inside)
    return [room] if room is not None else []


def _lines_across(area: Rect, walls: Sequence[Rect], is_down: bool) -> list[float]:
    """Where the area can be cut right across without cutting a wall: down
    it, or along it, at the walls' edges."""

    start, end = area.span(is_down)
    spans = [wall.span(is_down) for wall in walls]
    edges = {edge for span in spans for edge in span}
    lines: list[float] = []
    for edge in sorted(edges):
        if (
            start + _NEAR < edge < end - _NEAR
            and not any(low + _NEAR < edge < high - _NEAR for low, high in spans)
            and not (lines and edge - lines[-1] < _NEAR)
        ):
            lines.append(edge)
    return lines


def _parts(area: Rect, lines: Sequence[float], is_down: bool) -> list[Rect]:
    if is_down:
        edges = [area.left, *lines, area.right]
        return [
            Rect(left, area.top, right, area.bottom) for left, right in pairwise(edges)
        ]
    edges = [area.top, *lines, area.bottom]
    return [Rect(area.left, top, area.right, bottom) for top, bottom in pairwise(edges)]


def _biggest_room(area: Rect, walls: Sequence[Rect]) -> Rect | None:
    """The biggest rect in the area no wall is on, made of their edges,
    of those a tile fits in."""

    found = (
        Rect(*edges)
        for edges in product(
            {area.left, *(w.right for w in walls if area.left < w.right < area.right)},
            {area.top, *(w.bottom for w in walls if area.top < w.bottom < area.bottom)},
            {area.right, *(w.left for w in walls if area.left < w.left < area.right)},
            {area.bottom, *(w.top for w in walls if area.top < w.top < area.bottom)},
        )
    )
    return max(
        (
            rect
            for rect in found
            if min(rect.width, rect.height) >= MIN_CELL
            and not any(rect.overlaps(wall) for wall in walls)
        ),
        key=lambda rect: rect.width * rect.height,
        default=None,
    )


def _read_by_piece(
    pieces: Sequence[Rect],
    ids: Sequence[str],
    at: Mapping[str, Rect],
    is_columns: bool,
) -> list[str]:
    """The videos as their tiles are read, piece by piece, each piece row
    by row (or column by column): a tile is in the piece its middle is in,
    or the nearest. Those with no tile after them all, as ids has them.

    Read so, the tiles are read in the order they were laid out in: an
    Arrange done again leaves them where they are.
    """

    by_piece: list[dict[str, Rect]] = [{} for _ in pieces]
    for video_id in ids:
        rect = at.get(video_id)
        if rect is not None:
            by_piece[_nearest(pieces, rect)][video_id] = rect

    found = [i for rects in by_piece for i in read_in_rows(rects, is_columns)]
    return found + [i for i in ids if i not in at]


def _nearest(pieces: Sequence[Rect], rect: Rect) -> int:
    """The piece the middle of the rect is in, or the nearest to it."""

    x, y = rect.center_x, rect.center_y

    def away(piece: Rect) -> float:
        dx = max(piece.left - x, 0.0, x - piece.right)
        dy = max(piece.top - y, 0.0, y - piece.bottom)
        return dx * dx + dy * dy

    return min(range(len(pieces)), key=lambda i: away(pieces[i]))


def _reordered(
    sharing: _Sharing, ids: Sequence[str], shapes: Mapping[str, float]
) -> tuple[list[str], list[int]]:
    """The order that shows the videos best, and how many go in each piece:
    of Reorder to Fit's orders (see reorder_candidates) and by shape the
    other way, the best; then, with more than one piece, two at a time
    swapped while that shows them better, up to REORDER_TRIES orders, each
    piece keeping as many; then shared out once more.

    Begun from their shapes, not from where their tiles are, it comes to
    the same each time.
    """

    def shape_of(video_id: str) -> float:
        return shapes.get(video_id) or DEFAULT_SHAPE

    orders = reorder_candidates(ids, shape_of)
    if len(orders) > 1:
        orders.append(orders[1][::-1])
    best_order, counts, best = max(
        ((order, *sharing.climb(order)) for order in orders),
        key=lambda found: found[2],
    )

    # in one piece, swaps gain next to nothing on the orders above (as in
    # Fit Shapes), and each lays all the videos out anew
    if len(sharing.pieces) > 1:
        tries = 0
        is_better = True
        while is_better and tries < REORDER_TRIES:
            is_better = False
            for i, j in combinations(range(len(best_order)), 2):
                if tries == REORDER_TRIES:
                    break
                if shape_of(best_order[i]) == shape_of(best_order[j]):
                    continue
                tried = list(best_order)
                tried[i], tried[j] = tried[j], tried[i]
                tries += 1
                score = sharing.score(tried, counts)
                if score > best + _HAIR:
                    best_order, best, is_better = tried, score, True

    return best_order, sharing.climb(best_order, counts)[0]


class _Sharing:
    """Videos shared out among the pieces, in order, so many to each: each
    run of videos laid out in a piece once, kept in laid for other orders
    and shares (see _lay_out)."""

    def __init__(
        self,
        pieces: Sequence[Rect],
        shapes: Mapping[str, float],
        crops: Sequence[int],
        find_splits: SplitFinder,
        laid: dict[tuple, _Laid],
    ):
        self.pieces = pieces
        self._shapes = shapes
        self._crops = crops
        self._find_splits = find_splits
        self._laid = laid

    def runs(
        self,
        ids: Sequence[str],
        counts: Sequence[int],
        column_ids: Sequence[str] | None = None,
    ) -> list[_Laid]:
        """Each piece's videos laid out in it: column_ids the order they go
        down columns in, if not as along rows."""

        starts = [0, *accumulate(counts)]
        return [
            self._run(piece, tuple(ids[starts[piece] : starts[piece + 1]]), column_ids)
            for piece in range(len(self.pieces))
        ]

    def score(
        self,
        ids: Sequence[str],
        counts: Sequence[int],
        column_ids: Sequence[str] | None = None,
    ) -> float:
        return sum(run.score for run in self.runs(ids, counts, column_ids))

    def climb(
        self,
        ids: Sequence[str],
        counts: Sequence[int] | None = None,
        column_ids: Sequence[str] | None = None,
    ) -> tuple[list[int], float]:
        """How many videos each piece is to have, and how well that shows
        them: from these counts, or each piece's share of the room, a video
        at a time going over to the next piece, or back, while that shows
        them better."""

        counts = list(counts) if counts is not None else _shares(self.pieces, len(ids))
        best = self.score(ids, counts, column_ids)
        is_better = True
        while is_better:
            is_better = False
            for piece in range(len(self.pieces) - 1):
                for way in (1, -1):
                    giving = piece if way == 1 else piece + 1
                    if not counts[giving]:
                        continue
                    tried = list(counts)
                    tried[piece] -= way
                    tried[piece + 1] += way
                    score = self.score(ids, tried, column_ids)
                    if score > best + _HAIR:
                        counts, best, is_better = tried, score, True
        return counts, best

    def laid(
        self,
        ids: Sequence[str],
        counts: Sequence[int],
        column_ids: Sequence[str] | None = None,
    ) -> _Laid:
        runs = self.runs(ids, counts, column_ids)
        rects = {}
        for run in runs:
            rects.update(run.rects)
        return _Laid(sum(run.score for run in runs), rects)

    def _run(
        self, piece: int, run: tuple[str, ...], column_ids: Sequence[str] | None
    ) -> _Laid:
        if column_ids is None:
            columns = run
        else:
            members = set(run)
            columns = tuple(i for i in column_ids if i in members)
        laid = self._laid
        key = (self.pieces[piece], run, columns)
        if key not in laid:
            laid[key] = _lay_out(
                self.pieces[piece],
                run,
                columns,
                self._shapes,
                self._crops,
                self._find_splits,
            )
        return laid[key]


def _shares(pieces: Sequence[Rect], count: int) -> list[int]:
    """So many videos for each piece as its share of the room."""

    areas = [piece.width * piece.height for piece in pieces]
    total = sum(areas)
    exact = [count * area / total for area in areas]
    counts = [math.floor(share) for share in exact]
    by_rest = sorted(range(len(pieces)), key=lambda i: counts[i] - exact[i])
    for i in by_rest[: count - sum(counts)]:
        counts[i] += 1
    return counts


def _lay_out(
    piece: Rect,
    ids: Sequence[str],
    column_ids: Sequence[str],
    shapes: Mapping[str, float],
    crops: Sequence[int],
    find_splits: SplitFinder,
) -> _Laid:
    """The videos laid out in the piece as Fit Shapes lays them out, cut
    by the least of the crops that fills it, else by the most; column_ids
    them in the order they go down columns in."""

    if not ids:
        return _Laid(0.0, {})

    shown = {video_id: shapes.get(video_id) or DEFAULT_SHAPE for video_id in ids}
    boxes = []
    for crop in crops:
        flow = FlowLayout(
            mode=FlowMode.SHAPES, ids=list(ids), column_ids=list(column_ids), crop=crop
        )
        flow.fit_to(piece.width, piece.height, shown, find_splits)
        boxes = flow.boxes()
        covered = sum((b.right - b.left) * (b.bottom - b.top) for _, b in boxes)
        if covered >= FILLED:
            break

    rects = {video_id: Rect.of_box(box, piece) for video_id, box in boxes}
    score = sum(_tile_score(rect, shown[i]) for i, rect in rects.items())
    return _Laid(score, rects)


def _tile_score(rect: Rect, shape: float) -> float:
    """How well a tile shows its picture, as Fit Shapes counts it: the log
    of its area, what it is stretched by cutting the picture counted at
    STRETCH_WORTH."""

    if rect.width <= _HAIR or rect.height <= _HAIR:
        return -math.inf

    stretch = abs(math.log(rect.width / rect.height / shape))
    return math.log(rect.width * rect.height) - (1 - STRETCH_WORTH) * stretch
