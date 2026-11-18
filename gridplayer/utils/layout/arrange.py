"""Free Tiles' Arrange: the tiles not locked laid out anew around those that
are.

The room the locked tiles leave is cut along their edges into pieces, each
cut going right across what it cuts. The videos are shared out among the
pieces in the order they are read, and each piece is laid out as Fit Shapes
lays out the window. Of the ways to cut the room, the one that shows the
videos best is kept. What room a piece's videos leave goes to the edge of
the area it is on, not between them and the pieces and locked tiles beside
it (see _slack_of).
"""

from __future__ import annotations

import copy
import functools
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import accumulate, combinations, pairwise, product
from typing import NamedTuple

from gridplayer.utils.layout.boxes import Box
from gridplayer.utils.layout.flow_layout import (
    DEFAULT_SHAPE,
    FlowLayout,
    FlowMode,
    Lines,
    is_much_better,
    reorder_candidates,
)
from gridplayer.utils.layout.free_tiles import Rect, read_in_rows
from gridplayer.utils.layout.justified import (
    STRETCH_WORTH,
    Split,
    best_splits,
    justified_boxes,
)
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

# where the room a piece's videos leave goes, across and down: before them
# this share of it, the rest after them (see _slack_of)
CENTRED = (0.5, 0.5)

SplitFinder = Callable[[tuple, tuple | None], tuple[Split, ...]]


class _Run(NamedTuple):
    """A piece's videos in the lines they were laid out in: in the order
    they go in them, rows or columns of so many each."""

    ids: tuple[str, ...]
    lines: Lines


class _Laid(NamedTuple):
    """Videos laid out in a piece, or in them all: how well that shows them
    (see _tile_score), where each goes, in the area's pixels, and each
    piece's run."""

    score: float
    rects: dict[str, Rect]
    runs: tuple[_Run, ...]


class _Plan(NamedTuple):
    """How the videos were arranged: the room cut down first or along
    (see open_pieces), and each piece's run."""

    is_down: bool
    runs: tuple[_Run, ...]


_NO_RUN = _Run((), Lines((), False))
# a piece with no videos
_NONE_LAID = _Laid(0.0, {}, (_NO_RUN,))


# how many of the lines' splits ArrangeCache keeps, the last found
SPLITS_KEPT = 2048


class ArrangeCache:
    """What arrange_around works out, kept from one call to the next for
    the same videos, shapes and crop limit: the lines' splits, which do not
    change as the pieces do, and how they were arranged the last time, to
    stay so while no other way shows them much better (see _kept). Kept
    while a tile is held, the others arranged around it as it goes, and
    as the window is resized."""

    def __init__(self):
        self.find_splits: SplitFinder = functools.lru_cache(maxsize=SPLITS_KEPT)(
            best_splits.__wrapped__
        )
        self.plan: _Plan | None = None


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
    laid: dict[tuple, _Laid] | None = None,
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
    same videos, shapes and crop limit (see ArrangeCache): with it, and not
    reordered, they stay arranged as the last time, in the room there is
    now, unless another way shows the pictures SWITCH_GAIN times bigger.
    A wall moved a little at a time would else flip them to and fro where
    two ways show them about as well. laid keeps each piece's lay-outs,
    to share between calls for the same videos, shapes and crop limit.
    """

    if not ids:
        return {}

    area = Rect(0, 0, width, height)
    ways = _ways_to_cut(area, walls)
    # cut the same both ways, the once
    cuts = {
        is_down: pieces
        for is_down, pieces in ways.items()
        if pieces and (is_down or pieces != ways[True])
    }
    if not cuts:
        return None

    # none cut, at the least
    crops = tuple(crop for crop in FILL_CROPS if crop <= max(crop_limit, 0))
    # each run of videos laid out in a piece once, for all the rounds
    if cache is None:
        find_splits = functools.cache(best_splits.__wrapped__)
    else:
        find_splits = cache.find_splits
    if laid is None:
        laid = {}
    sharings = {
        is_down: _Sharing(pieces, area, shapes, crops, find_splits, laid)
        for is_down, pieces in cuts.items()
    }

    def laid_out(at: Mapping[str, Rect]) -> tuple[_Laid, bool]:
        found = []
        for is_down, sharing in sharings.items():
            pieces = sharing.pieces
            if is_reordered:
                order, counts = _reordered(sharing, ids, shapes)
                found.append((sharing.laid(order, counts), is_down))
            else:
                rows = _read_by_piece(pieces, ids, at, is_columns=False)
                columns = _read_by_piece(pieces, ids, at, is_columns=True)
                counts = sharing.climb(rows, column_ids=columns)[0]
                found.append((sharing.laid(rows, counts, columns), is_down))
        # on a tie, the first
        return max(found, key=lambda one: one[0].score)

    best, is_down = laid_out(at)
    # reordered, where they are counts for nothing: once is enough
    for _ in range(ARRANGE_ROUNDS - 1 if not is_reordered else 0):
        again, again_is_down = laid_out(best.rects)
        if again.rects == best.rects:
            break
        best, is_down = again, again_is_down

    if cache is not None and not is_reordered:
        plan = _Plan(is_down, best.runs)
        if cache.plan is not None and plan != cache.plan:
            kept = _kept(cache.plan, ways, area, ids, shapes, crops)
            if kept is not None and not is_much_better(
                best.score, kept.score, len(ids)
            ):
                best, plan = kept, cache.plan
        cache.plan = plan

    return {i: rect.as_box(width, height) for i, rect in best.rects.items()}


def _ways_to_cut(area: Rect, walls: Sequence[Rect]) -> dict[bool, list[Rect]]:
    """The room the walls leave in pieces, cut down first and along first
    (see open_pieces)."""

    if not walls:
        # all of it, however small
        return {True: [area], False: [area]}
    return {is_down: open_pieces(area, walls, is_down) for is_down in (True, False)}


def _kept(
    plan: _Plan,
    ways: Mapping[bool, Sequence[Rect]],
    area: Rect,
    ids: Sequence[str],
    shapes: Mapping[str, float],
    crops: Sequence[int],
) -> _Laid | None:
    """The videos arranged as the plan has them, in the room there is now:
    cut the same way, each piece's videos in the lines they had. None if
    that cannot be: the room is in more pieces, or fewer, or the videos
    are others."""

    pieces = ways[plan.is_down]
    planned = [video_id for run in plan.runs for video_id in run.ids]
    if len(pieces) != len(plan.runs) or sorted(planned) != sorted(ids):
        return None

    return _all_laid(
        [
            _lay_out_as(piece, run, shapes, crops, _slack_of(piece, area))
            for piece, run in zip(pieces, plan.runs, strict=True)
        ]
    )


def _all_laid(runs: Sequence[_Laid]) -> _Laid:
    """The pieces' videos, each laid out in its own, all together."""

    rects = {}
    for run in runs:
        rects.update(run.rects)
    return _Laid(
        sum(run.score for run in runs),
        rects,
        tuple(piece_run for run in runs for piece_run in run.runs),
    )


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
        area: Rect,
        shapes: Mapping[str, float],
        crops: Sequence[int],
        find_splits: SplitFinder,
        laid: dict[tuple, _Laid],
    ):
        self.pieces = pieces
        self._area = area
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
        return _all_laid(self.runs(ids, counts, column_ids))

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
                _slack_of(self.pieces[piece], self._area),
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
    slack: tuple[float, float],
) -> _Laid:
    """The videos laid out in the piece as Fit Shapes lays them out, cut
    by the least of the crops that fills it, else by the most; column_ids
    them in the order they go down columns in. What room they leave goes
    around them as slack has it (see _slid)."""

    if not ids:
        return _NONE_LAID

    shown = {video_id: shapes.get(video_id) or DEFAULT_SHAPE for video_id in ids}
    run = _NO_RUN
    boxes = []
    for crop in crops:
        flow = FlowLayout(
            mode=FlowMode.SHAPES, ids=list(ids), column_ids=list(column_ids), crop=crop
        )
        flow.fit_to(piece.width, piece.height, shown, find_splits)
        run = _Run(tuple(flow.order()), flow.lines())
        boxes = [box for _, box in flow.boxes()]
        if _is_filled(boxes):
            break

    return _laid_in(piece, run, boxes, shown, slack)


def _lay_out_as(
    piece: Rect,
    run: _Run,
    shapes: Mapping[str, float],
    crops: Sequence[int],
    slack: tuple[float, float],
) -> _Laid:
    """The videos laid out in the piece in the lines they had, whatever
    its size is now: cut as in _lay_out."""

    if not run.ids:
        return _NONE_LAID

    shown = {video_id: shapes.get(video_id) or DEFAULT_SHAPE for video_id in run.ids}
    boxes = []
    for crop in crops:
        boxes = justified_boxes(
            [shown[video_id] for video_id in run.ids],
            *run.lines,
            piece.width,
            piece.height,
            crop / 100,
        )
        if _is_filled(boxes):
            break

    return _laid_in(piece, run, boxes, shown, slack)


def _slack_of(piece: Rect, area: Rect) -> tuple[float, float]:
    """Where the room a piece's videos leave goes (see _slid):
    to the edge of the area the piece is on, the videos against the pieces
    and walls beside it, not apart from them with a gap between; evenly
    around them in a piece on both edges, or on neither."""

    def share(low: float, high: float, start: float, end: float) -> float:
        on_start, on_end = low <= start + _NEAR, high >= end - _NEAR
        if on_start and not on_end:
            return 1.0
        if on_end and not on_start:
            return 0.0
        return 0.5

    return (
        share(piece.left, piece.right, area.left, area.right),
        share(piece.top, piece.bottom, area.top, area.bottom),
    )


def _slid(boxes: Sequence[Box], slack: tuple[float, float]) -> Sequence[Box]:
    """The boxes, laid out evenly in the room, moved together so that of
    the room they leave this share is before them, across and down."""

    if slack == CENTRED or not boxes:
        return boxes
    left = min(b.left for b in boxes)
    top = min(b.top for b in boxes)
    across = (1 - (max(b.right for b in boxes) - left)) * slack[0] - left
    down = (1 - (max(b.bottom for b in boxes) - top)) * slack[1] - top
    return [
        Box(b.left + across, b.top + down, b.right + across, b.bottom + down)
        for b in boxes
    ]


def _covered(boxes: Iterable[Box]) -> float:
    return sum((b.right - b.left) * (b.bottom - b.top) for b in boxes)


def _is_filled(boxes: Sequence[Box]) -> bool:
    return _covered(boxes) >= FILLED


def _laid_in(
    piece: Rect,
    run: _Run,
    boxes: Sequence[Box],
    shown: Mapping[str, float],
    slack: tuple[float, float],
) -> _Laid:
    rects = {
        video_id: Rect.of_box(box, piece)
        for video_id, box in zip(run.ids, _slid(boxes, slack), strict=True)
    }
    score = sum(_tile_score(rect, shown[i]) for i, rect in rects.items())
    return _Laid(score, rects, (run,))


def _tile_score(rect: Rect, shape: float) -> float:
    """How well a tile shows its picture, as Fit Shapes counts it: the log
    of its area, what it is stretched by cutting the picture counted at
    STRETCH_WORTH."""

    if rect.width <= _HAIR or rect.height <= _HAIR:
        return -math.inf

    stretch = abs(math.log(rect.width / rect.height / shape))
    return math.log(rect.width * rect.height) - (1 - STRETCH_WORTH) * stretch


# --- locked tiles giving a little ---

# how much bigger or smaller, each way, a locked tile may be made in Mosaic to
# close the room the others leave, its shape kept: the nearest its own size
# first, where two close as much
GIVES = (1.0, 0.95, 1.05, 0.9, 1.1, 0.85, 1.15)
# the give a tile has is kept while another leaves no more than this share of
# the area less empty: not changed to and fro as the window is resized
GIVE_KEEP = 0.01
# a give that leaves less than this share of the area empty is not looked
# past: what more one could close would hardly show
GIVE_ENOUGH = 0.01


def arrange_giving(
    width: float,
    height: float,
    walls: Mapping[str, Rect],
    ids: Sequence[str],
    at: Mapping[str, Rect],
    shapes: Mapping[str, float],
    crop_limit: int,
    is_reordered: bool = False,
    cache: ArrangeCache | None = None,
    gives: Mapping[str, float] | None = None,
    is_kept: bool = False,
) -> tuple[dict[str, Box], dict[str, Rect], dict[str, float]] | None:
    """As arrange_around, around walls (the locked tiles, by video), each
    made a little bigger or smaller (see GIVES) where that leaves less of
    the area empty, the biggest first; about its corner nearest the area's,
    inside the area, and not over another. Its own size is kept while no
    give leaves GIVE_KEEP of the area less empty, and so is the give it had
    the last time (gives): then it is back as it was where it can be, and
    not changed to and fro at each step of a resize. Kept (is_kept), each
    gives what it had, no other looked for. Also the walls as given, and
    how much each was. None if the walls leave no room."""

    gives = gives or {}
    given = dict(walls)
    scales: dict[str, float] = {}
    # what is worked out shared by all the ways tried: each piece laid out,
    # and each set of walls arranged around, once
    laid: dict[tuple, _Laid] = {}
    arranged: dict[tuple, tuple[dict[str, Box] | None, ArrangeCache | None]] = {}

    def arranged_around(trial: Mapping[str, Rect]):
        key = tuple(trial.items())
        if key not in arranged:
            # from the plan of the last time, whichever is tried first
            tried_cache = copy.copy(cache)
            boxes = arrange_around(
                width,
                height,
                list(trial.values()),
                ids,
                at,
                shapes,
                crop_limit,
                is_reordered,
                tried_cache,
                laid,
            )
            arranged[key] = boxes, tried_cache
        return arranged[key]

    def is_clear(video_id: str, rect: Rect) -> bool:
        return not any(rect.overlaps(w) for i, w in given.items() if i != video_id)

    for video_id in sorted(walls, key=lambda i: -walls[i].width * walls[i].height):
        had = gives.get(video_id, 1.0)
        if is_kept:
            # as it gave, where that is over none of the others (at their
            # own size, which leaves its own clear)
            for scale in dict.fromkeys((had, 1.0)):
                rect = given_rect(walls[video_id], scale, width, height)
                if is_clear(video_id, rect):
                    given[video_id] = rect
                    scales[video_id] = scale
                    break
            continue

        tried: list[tuple[float, float, Rect]] = []
        # its own size first, then the give it had
        for scale in dict.fromkeys((1.0, had, *GIVES)):
            rect = given_rect(walls[video_id], scale, width, height)
            if not is_clear(video_id, rect):
                continue
            trial = {**given, video_id: rect}
            boxes = arranged_around(trial)[0]
            if boxes is None:
                continue
            walled = sum(r.width * r.height for r in trial.values())
            empty = 1 - _covered(boxes.values()) - walled / (width * height)
            tried.append((empty, scale, rect))
            if empty < GIVE_ENOUGH:
                break
        if not tried:
            continue
        best = min(tried, key=lambda one: one[0])
        # its own size, or else the give it had, where about as good
        _empty, scale, rect = next(
            (
                one
                for one in tried
                if one[1] in (1.0, had) and one[0] <= best[0] + GIVE_KEEP
            ),
            best,
        )
        given[video_id] = rect
        scales[video_id] = scale

    boxes, tried_cache = arranged_around(given)
    if boxes is None:
        return None
    if cache is not None:
        cache.plan = tried_cache.plan
    return boxes, given, scales


def given_rect(rect: Rect, scale: float, width: float, height: float) -> Rect:
    """A tile this much bigger or smaller, about its corner nearest the
    area's: against the same edges; inside the area."""

    if scale == 1.0:
        return rect
    tile_width = min(rect.width * scale, width)
    tile_height = min(rect.height * scale, height)
    if rect.center_x < width / 2:
        left = rect.left
    else:
        left = rect.right - tile_width
    if rect.center_y < height / 2:
        top = rect.top
    else:
        top = rect.bottom - tile_height
    left = min(max(left, 0.0), width - tile_width)
    top = min(max(top, 0.0), height - tile_height)
    return Rect(left, top, left + tile_width, top + tile_height)
