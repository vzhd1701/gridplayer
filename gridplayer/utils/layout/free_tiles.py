from __future__ import annotations

import math
import random
from collections.abc import Callable, Collection, Iterable, Iterator
from enum import Enum, auto
from itertools import product, takewhile
from typing import NamedTuple

from gridplayer.params.static import TileResize, TileSnap
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout.boxes import Box, within
from gridplayer.utils.layout.flow_layout import DEFAULT_SHAPE
from gridplayer.utils.layout.lines import LINE_REACH, MIN_CELL, SNAP_REACH

# a new video goes where there is room for a tile at least this much of the
# size the others have, along its width; else the tiles are arranged anew
ROOM_SHARE = 0.5

# two edges this near, in pixels, are taken to be in line, and a tile this
# far into another is not taken to be over it
_NEAR = 0.5

# off the page, or into another tile, by no more than this, in pixels, a
# tile is not
_HAIR = 1e-6

# two tiles this far into each other on a page one high are not taken to be
# one over the other: _NEAR, on a page about a thousand pixels high
_NEAR_SHARE = 5e-4

# how many halvings a move cut short at a tile in the way is looked for in
_STEPS = 16


class Rect(NamedTuple):
    """A tile on the page, in the page's pixels as it is shown."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    def moved(self, dx: float, dy: float) -> Rect:
        return Rect(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)

    def overlaps(self, other: Rect, margin: float = _NEAR) -> bool:
        """Whether the two are over each other by more than the margin."""

        return (
            self.left < other.right - margin
            and self.right > other.left + margin
            and self.top < other.bottom - margin
            and self.bottom > other.top + margin
        )

    def is_inside(self, other: Rect) -> bool:
        """Whether all of it is within the other, to a hair."""

        return (
            self.left >= other.left - _HAIR
            and self.top >= other.top - _HAIR
            and self.right <= other.right + _HAIR
            and self.bottom <= other.bottom + _HAIR
        )

    def is_across(self, other: Rect) -> bool:
        """Whether the two share any of their height: one is beside the
        other, if not over it."""

        return self.top < other.bottom - _NEAR and self.bottom > other.top + _NEAR

    def is_along(self, other: Rect) -> bool:
        """Whether the two share any of their width."""

        return self.left < other.right - _NEAR and self.right > other.left + _NEAR

    def span(self, is_column: bool) -> tuple[float, float]:
        """Where it begins and ends across (is_column), or down."""

        return (self.left, self.right) if is_column else (self.top, self.bottom)

    def middle(self, is_column: bool) -> float:
        return self.center_x if is_column else self.center_y

    def is_beside(self, other: Rect, is_column: bool) -> bool:
        """Whether one is beside the other, if not over it: across
        (is_column), or one above the other."""

        return self.is_across(other) if is_column else self.is_along(other)


class GuideKind(Enum):
    """What a tile is in line with: another tile beside it, edge to edge;
    another's edge, or middle, with its own; the page's edge, the page's
    middle with an edge, or with its own middle."""

    TOUCHING = auto()
    EDGES = auto()
    MIDDLES = auto()
    PAGE_EDGE = auto()
    PAGE_MIDDLE = auto()
    CENTERED = auto()
    START = auto()


_GUIDE_SNAPS = {
    GuideKind.TOUCHING: TileSnap.TILE_EDGES,
    GuideKind.EDGES: TileSnap.TILE_EDGES,
    GuideKind.MIDDLES: TileSnap.TILE_MIDDLES,
    GuideKind.PAGE_EDGE: TileSnap.WINDOW_EDGES,
    GuideKind.PAGE_MIDDLE: TileSnap.WINDOW_MIDDLE,
    GuideKind.CENTERED: TileSnap.WINDOW_MIDDLE,
    GuideKind.START: TileSnap.OLD_PLACE,
}


class Guide(NamedTuple):
    """A line a tile moved is in line with, to be shown while it is: a
    column's at x = position from y = start to end, a row's the other way,
    in the page's pixels."""

    is_column: bool
    position: float
    start: float
    end: float
    kind: GuideKind


class Gap(NamedTuple):
    """The room between a tile and the next beside it, or the page's edge
    (is_page): side to side (is_column), from x = start to end, along the
    height they share, from y = low to high; else from y = start to end,
    along the width they share. In the page's pixels."""

    is_column: bool
    start: float
    end: float
    low: float
    high: float
    is_page: bool

    @property
    def size(self) -> float:
        return self.end - self.start

    @property
    def position(self) -> float:
        """Where it is shown, across: in the middle of what they share."""

        return (self.low + self.high) / 2

    @property
    def area(self) -> Rect:
        if self.is_column:
            return Rect(self.start, self.low, self.end, self.high)
        return Rect(self.low, self.start, self.high, self.end)


class TilePlace(NamedTuple):
    """Where a tile was, to be put back there: as shares of the whole area
    it was shown in, how many tiles were behind it, and where the others
    were then, on a page one high of the area's shape, to put it back
    beside them wherever they are now."""

    box: Box
    depth: int
    is_locked: bool = False
    shape: float = DEFAULT_SHAPE
    others: tuple[tuple[str, Rect], ...] = ()


# Which edges a tile is held by: -1 the left (top), 1 the right (bottom), 0
# neither, for x and for y. Neither of either moves the whole tile.
Handle = tuple[int, int]
MOVE: Handle = (0, 0)


class FreeTiles:
    """Free Tiles: each video in a tile of its own, placed and sized by hand
    on a page of the size it was last given. The tiles keep their shapes and
    places among themselves as the window is resized: scaled together to
    fill it, or kept as big as they were made, made smaller only to fit (see
    TileResize, and boxes). The page takes the area's size, all of it, when
    they are changed (see fill), to use the room beside.

    A tile is kept as its edges' shares of the page's width and height,
    the tiles in the order they are one over another, the one in front
    last. Where they may go over each other is up to how they are moved
    (see TileDrag).

    A tile locked is neither moved nor sized by hand, nor pushed aside,
    nor gone over: the others stop at its edges. It is in front of those
    not locked, and stays where it is when they are arranged, or shuffled.

    A video added goes where there is the most room for it, in a tile the
    size the others have, if there is room enough (see ROOM_SHARE); none
    found, it is left over, for the tiles to be arranged anew.
    """

    def __init__(
        self,
        tiles: dict[str, Box] | None = None,
        page_shape=DEFAULT_SHAPE,
        locked=(),
        page_height: float | None = None,
        resize: TileResize = TileResize.FIT,
        is_as_placed: bool = False,
    ):
        self.tiles: dict[str, Box] = dict(tiles or {})
        # the page's width over its height
        self.page_shape = page_shape
        # its height in pixels, None not known
        self.page_height = page_height
        # what the tiles do as the area is resized (see boxes)
        self.resize = resize
        # whether they are shown as they were placed, in an area the page's
        # size, not resized since (see boxes)
        self.is_as_placed = is_as_placed
        # the videos whose tiles are locked
        self.locked: set[str] = set(locked)
        # each video's shape, for its tile when it is added
        self.shape_of: Callable[[str], float] = lambda _video_id: DEFAULT_SHAPE

    def copy(self) -> FreeTiles:
        tiles = FreeTiles(
            self.tiles,
            self.page_shape,
            self.locked,
            self.page_height,
            self.resize,
            self.is_as_placed,
        )
        tiles.shape_of = self.shape_of
        return tiles

    def clear(self) -> None:
        self.tiles = {}
        self.locked = set()

    # --- the page ---

    def set_page(self, width: float, height: float) -> None:
        """The page an area of this size, the tiles as they are on it:
        shown so, as they are placed, until the area is resized (see
        boxes)."""

        self.page_shape = width / height
        self.page_height = height
        self.is_as_placed = True

    def fill(self, width: float, height: float) -> None:
        """The page made an area of this size, all of it, the tiles where
        they are shown in it (see set_page)."""

        if width <= 0 or height <= 0:
            return
        self.tiles = dict(self.boxes(width, height))
        self.set_page(width, height)

    def filled(self, width: float, height: float) -> FreeTiles:
        tiles = self.copy()
        tiles.fill(width, height)
        return tiles

    def set_resize(self, resize: TileResize, width: float, height: float) -> None:
        """What the tiles do as an area, of this size now, is resized: kept
        as big as they are shown in it now (KEEP), or made to fit it at
        once (FIT)."""

        if resize == TileResize.KEEP:
            self.fill(width, height)
        else:
            self.is_as_placed = False
        self.resize = resize

    def resized_to(self, width: float, height: float) -> None:
        """The area the tiles are shown in this size now: if it is not the
        page's, they are no longer shown as they were placed, and will not
        be again when it is made that size back (see boxes)."""

        if not self._is_page_size(width, height):
            self.is_as_placed = False

    def _is_page_size(self, width: float, height: float) -> bool:
        if not self.page_height:
            return False
        page_width = self.page_height * self.page_shape
        return (
            abs(width - page_width) < _NEAR and abs(height - self.page_height) < _NEAR
        )

    def boxes(self, width: int, height: int) -> list[tuple[str, Box]]:
        """The tiles as shares of an area of this size.

        As they were placed, in an area the page's size not resized since.
        Else all of them scaled together to fill it (TileResize.FIT), or as
        big as they were made, made smaller only to fit (KEEP); in the
        middle of it. Their size not known, that of a playlist saved before
        it was kept, as made on a page as big as the area allows.
        """

        if width <= 0 or height <= 0 or not self.tiles:
            return list(self.tiles.items())
        if self.is_as_placed and self._is_page_size(width, height):
            return list(self.tiles.items())

        # not known, the page as big as the area allows
        page_height = self.page_height or min(height, width / self.page_shape)
        rects = _fitted(
            self.rects(page_height * self.page_shape, page_height),
            width,
            height,
            max_scale=1.0 if self.resize == TileResize.KEEP else math.inf,
        )
        return [
            (
                video_id,
                Box(r.left / width, r.top / height, r.right / width, r.bottom / height),
            )
            for video_id, r in rects.items()
        ]

    def rects(self, page_width: float, page_height: float) -> dict[str, Rect]:
        """The tiles on a page of this size, in its pixels."""

        return {
            video_id: Rect(
                box.left * page_width,
                box.top * page_height,
                box.right * page_width,
                box.bottom * page_height,
            )
            for video_id, box in self.tiles.items()
        }

    def set_rect(
        self, video_id: str, rect: Rect, page_width: float, page_height: float
    ) -> None:
        self.tiles[video_id] = Box(
            rect.left / page_width,
            rect.top / page_height,
            rect.right / page_width,
            rect.bottom / page_height,
        )

    def handle_at(
        self, x: float, y: float, page_width: float, page_height: float
    ) -> tuple[str, Handle] | None:
        """The tile at a point on the page and what of it is there: an edge
        or a corner, within LINE_REACH of it, to size it by, or the rest of
        it, to move it by. The tile the point is in goes first, where two
        meet, the one in front where one is over another. None of a locked
        tile, nor of those behind it there, their edges either."""

        rects = self.rects(page_width, page_height)
        inside = [i for i, r in reversed(rects.items()) if _contains(r, x, y)]
        locked = [rects[i] for i in inside if i in self.locked]
        others = [
            i
            for i in rects
            if i not in inside
            and i not in self.locked
            and not any(rects[i].overlaps(r) for r in locked)
        ]
        inside = list(takewhile(lambda i: i not in self.locked, inside))

        for video_id in inside + others:
            rect = rects[video_id]
            reach = min(LINE_REACH, rect.width / 4, rect.height / 4)
            if not _contains(rect, x, y, LINE_REACH):
                continue

            side_x = _side(x, rect.left, rect.right, reach)
            side_y = _side(y, rect.top, rect.bottom, reach)
            if (side_x, side_y) != MOVE or video_id in inside:
                return video_id, (side_x, side_y)

        return None

    # --- Layout ---

    def displayed_size(self) -> tuple[int, int]:
        # as a grid of as many cells would be, near enough square
        count = max(len(self.tiles), 1)
        cols = math.ceil(math.sqrt(count))
        return cols, -(-count // cols)

    def id_at(self, row: int, col: int) -> str | None:
        return None

    def order(self, is_columns: bool = False) -> list[str]:
        """The videos as the tiles are read, row by row: a tile is in the
        row of the one before it if it starts above that row's bottom. Or
        column by column, likewise."""

        rects = self.rects(self.page_shape, 1)
        if is_columns:
            # turned on their side, the columns read as rows
            rects = {
                i: Rect(r.top, r.left, r.bottom, r.right) for i, r in rects.items()
            }
        rows: list[list[str]] = []
        row_bottom = 0.0
        for video_id in sorted(rects, key=lambda i: (rects[i].top, rects[i].left)):
            rect = rects[video_id]
            if rows and rect.top < row_bottom - 1e-6:
                rows[-1].append(video_id)
                row_bottom = min(row_bottom, rect.bottom)
            else:
                rows.append([video_id])
                row_bottom = rect.bottom
        return [i for row in rows for i in sorted(row, key=lambda i: rects[i].left)]

    def contains(self, video_id: str) -> bool:
        return video_id in self.tiles

    def add(self, video_ids: list[str]) -> list[str]:
        """Each video put where there is the most room for it; those there
        is not room enough for, left over."""

        leftover = []
        for video_id in video_ids:
            if video_id in self.tiles:
                continue
            rect = self._room_for(self.shape_of(video_id))
            if rect is None:
                leftover.append(video_id)
                continue
            self.set_rect(video_id, rect, self.page_shape, 1)
        self._restack()
        return leftover

    def remove(self, video_id: str) -> None:
        self.tiles.pop(video_id, None)
        self.locked.discard(video_id)

    def free_capacity(self) -> int | None:
        return None

    def place_of(self, video_id: str, width: float, height: float) -> TilePlace:
        """Where a tile is, as it is shown in an area of this size, and the
        others around it."""

        filled = self.filled(width, height)
        rects = filled.rects(filled.page_shape, 1)
        return TilePlace(
            filled.tiles[video_id],
            list(self.tiles).index(video_id),
            video_id in self.locked,
            filled.page_shape,
            tuple((i, r) for i, r in rects.items() if i != video_id),
        )

    def put_back(self, video_id: str, place: TilePlace, is_over: bool = False) -> bool:
        """A video's tile back where it was beside the others still there,
        wherever they are shown now, as deep among them, if nothing is
        there now, or if tiles may go over each other (is_over), but for a
        locked one. The page is to be the area they are shown in (see
        fill); no room left on it beside them, all of them are made to fit
        it (see boxes)."""

        self.tiles.pop(video_id, None)
        others = self.rects(self.page_shape, 1)
        rect = _beside(place, others) or _box_rect(place.box, self.page_shape)
        if any(
            rect.overlaps(other, _NEAR_SHARE)
            for i, other in others.items()
            if not is_over or i in self.locked
        ):
            return False

        box = Box(
            rect.left / self.page_shape,
            rect.top,
            rect.right / self.page_shape,
            rect.bottom,
        )
        tiles = list(self.tiles.items())
        tiles.insert(min(place.depth, len(tiles)), (video_id, box))
        self.tiles = dict(tiles)
        if place.is_locked:
            self.locked.add(video_id)
        self._restack()

        page = Rect(0, 0, self.page_shape, 1)
        if self.page_height and not _is_near_inside(rect, page):
            self.is_as_placed = False
            self.fill(self.page_height * self.page_shape, self.page_height)
        return True

    def fit_to_page(self) -> None:
        """The tiles made as big as the page lets them, all together, kept
        where they are among themselves, in the middle of it."""

        rects = self.rects(self.page_shape, 1)
        if not rects:
            return

        for video_id, rect in _fitted(rects, self.page_shape, 1).items():
            self.set_rect(video_id, rect, self.page_shape, 1)

    def fit_shape(self, video_id: str, shape: float) -> None:
        """A video's tile made its shape, as big as it can be inside the
        tile it had, in the middle of it; locked, left as it is."""

        if video_id in self.locked:
            return
        rect = _box_rect(self.tiles[video_id], self.page_shape)
        width = min(rect.width, rect.height * shape)
        height = width / shape
        left = rect.center_x - width / 2
        top = rect.center_y - height / 2
        self.set_rect(
            video_id, Rect(left, top, left + width, top + height), self.page_shape, 1
        )

    def shuffle(self) -> None:
        """The videos swapped about among the tiles, which stay put; those
        in locked tiles stay in them."""

        ids = [i for i in self.tiles if i not in self.locked]
        if len(ids) <= 1:
            return
        shuffled = ids[:]
        while shuffled == ids:
            random.shuffle(shuffled)
        others = iter(shuffled)
        self.tiles = {
            (video_id if video_id in self.locked else next(others)): box
            for video_id, box in self.tiles.items()
        }

    def replace_id(self, old_id: str, new_id: str) -> None:
        self.tiles = {
            (new_id if video_id == old_id else video_id): box
            for video_id, box in self.tiles.items()
        }
        self.locked = {new_id if i == old_id else i for i in self.locked}

    def drop(
        self,
        video_ids: list[str],
        row: int | None,
        col: int | None,
        zone: DropZone | None,
        *,
        is_replace: bool = False,
        src_id: str | None = None,
        dst_id: str | None = None,
    ) -> list[str]:
        """A video dropped on another's tile takes it: the two trade
        places, or, replacing, the other is closed (by the caller); a lock
        stays with the tile. New ones go where there is room."""

        if src_id is None:
            return self.add(video_ids)

        if dst_id is None or dst_id == src_id or dst_id not in self.tiles:
            return []

        src_box = self.tiles[src_id]
        self.tiles[src_id] = self.tiles[dst_id]
        if is_replace:
            del self.tiles[dst_id]
        else:
            self.tiles[dst_id] = src_box

        # each in the other's tile: the one closed with it
        traded = {src_id: dst_id, dst_id: src_id}
        self.locked = {traded.get(i, i) for i in self.locked} & set(self.tiles)
        self._restack()
        return []

    # --- one over another ---

    def stack(self, video_id: str, is_front: bool) -> None:
        """A tile put in front of all the others, or behind them: of those
        locked, if it is, else of those not."""

        box = self.tiles.pop(video_id)
        if is_front:
            self.tiles[video_id] = box
        else:
            self.tiles = {video_id: box, **self.tiles}
        self._restack()

    def set_locked(self, video_id: str, is_locked: bool) -> None:
        """A tile locked, and put in front of all the others, or let go of."""

        if is_locked:
            self.locked.add(video_id)
            self.stack(video_id, True)
        else:
            self.locked.discard(video_id)

    def _restack(self) -> None:
        """The locked tiles in front of the others."""

        self.tiles = {
            **{i: box for i, box in self.tiles.items() if i not in self.locked},
            **{i: box for i, box in self.tiles.items() if i in self.locked},
        }

    def is_under(self, video_id: str) -> bool:
        """Whether another tile is over this one, which it can be put in
        front of (see stack)."""

        ids = list(self.tiles)
        in_front = ids[ids.index(video_id) + 1 :]
        return self._overlaps_any(video_id, self._alike(video_id, in_front))

    def is_over(self, video_id: str) -> bool:
        """Whether this tile is over another, which it can be put behind."""

        ids = list(self.tiles)
        behind = ids[: ids.index(video_id)]
        return self._overlaps_any(video_id, self._alike(video_id, behind))

    def is_crowded(self, video_id: str) -> bool:
        """Whether this tile and another, not locked, are one over the
        other: room to be made (see make_room)."""

        others = [i for i in self.tiles if i != video_id and i not in self.locked]
        return self._overlaps_any(video_id, others)

    def _alike(self, video_id: str, ids: list[str]) -> list[str]:
        """Those of the tiles that are locked if this one is, else those
        not: the ones it can be put in front of, or behind."""

        is_locked = video_id in self.locked
        return [i for i in ids if (i in self.locked) == is_locked]

    def _overlaps_any(self, video_id: str, others: list[str]) -> bool:
        """Whether this tile and any of the others are one over the other."""

        rects = self.rects(self.page_shape, 1)
        return any(rects[video_id].overlaps(rects[i], _NEAR_SHARE) for i in others)

    def is_stacked(self) -> bool:
        """Whether any tile is over another, locked or not."""

        ids = list(self.tiles)
        return any(self._overlaps_any(i, ids[at + 1 :]) for at, i in enumerate(ids))

    def make_room(self, video_id: str) -> bool:
        """Room made for a tile: each one it is over or under set aside (see
        _pushed_aside), but none to less than ROOM_SHARE of its width, nor
        one locked. False, with nothing changed, if that leaves one too
        small."""

        rects = self.rects(self.page_shape, 1)
        by = rects.pop(video_id)
        pushed = _pushed_aside(
            rects,
            by,
            Rect(0, 0, self.page_shape, 1),
            lambda spot: ROOM_SHARE * min(spot.width, spot.height),
            fixed=self.locked,
        )
        if pushed is None:
            return False

        for other_id, rect in pushed.items():
            self.set_rect(other_id, rect, self.page_shape, 1)
        return True

    def open_area(self) -> Box | None:
        """The biggest part of the page no locked tile is on, as shares of
        it: all of it, with none; None, with none of it left."""

        rects = self.rects(self.page_shape, 1)
        walls = [rects[i] for i in self.locked]

        # each made of the page's edges and the walls'
        found = (
            Rect(*edges)
            for edges in product(
                {0.0, *(w.right for w in walls)},
                {0.0, *(w.bottom for w in walls)},
                {self.page_shape, *(w.left for w in walls)},
                {1.0, *(w.top for w in walls)},
            )
        )
        best = max(
            (
                rect
                for rect in found
                if rect.width > _HAIR
                and rect.height > _HAIR
                and not any(rect.overlaps(w, _NEAR_SHARE) for w in walls)
            ),
            key=lambda rect: rect.width * rect.height,
            default=None,
        )

        if best is None:
            return None
        return Box(
            best.left / self.page_shape,
            best.top,
            best.right / self.page_shape,
            best.bottom,
        )

    def arrange(self, boxes: Iterable[tuple[str, Box]], area: Box) -> None:
        """Tiles laid out anew at boxes, as shares of an area of the page
        (see open_area), the others left where they are."""

        laid_out = {video_id: within(box, area) for video_id, box in boxes}
        kept = {i: box for i, box in self.tiles.items() if i not in laid_out}
        self.tiles = {**laid_out, **kept}
        self._restack()

    # --- room ---

    def _room_for(self, shape: float) -> Rect | None:
        """Where a tile of this shape goes, on a page one high: the most
        room there is for it, up to the size the others have, and in the
        middle of that room; None if there is not room enough."""

        rects = list(self.rects(self.page_shape, 1).values())
        if not rects:
            return None

        areas = sorted(r.width * r.height for r in rects)
        wanted = (areas[len(areas) // 2] * shape) ** 0.5

        rect = _most_room(rects, Rect(0, 0, self.page_shape, 1), shape, wanted)
        if rect is None or rect.width < wanted * ROOM_SHARE:
            return None
        return rect


def _box_rect(box: Box, page_width: float) -> Rect:
    # on a page one high
    return Rect(box.left * page_width, box.top, box.right * page_width, box.bottom)


def _outline(rects: Iterable[Rect]) -> Rect:
    """The least rect all of these are in."""

    rects = list(rects)
    return Rect(
        min(r.left for r in rects),
        min(r.top for r in rects),
        max(r.right for r in rects),
        max(r.bottom for r in rects),
    )


def _scaled(rect: Rect, scale: float, x: float, y: float) -> Rect:
    return Rect(
        x + rect.left * scale,
        y + rect.top * scale,
        x + rect.right * scale,
        y + rect.bottom * scale,
    )


def _fitted(
    rects: dict[str, Rect], width: float, height: float, max_scale: float = math.inf
) -> dict[str, Rect]:
    """The rects scaled together as big as an area of this size lets them,
    up to max_scale, kept where they are among themselves, in the middle of
    it."""

    group = _outline(rects.values())
    scale = min(
        width / max(group.width, _HAIR), height / max(group.height, _HAIR), max_scale
    )
    x = (width - group.width * scale) / 2 - group.left * scale
    y = (height - group.height * scale) / 2 - group.top * scale
    return {video_id: _scaled(r, scale, x, y) for video_id, r in rects.items()}


def _beside(place: TilePlace, rects: dict[str, Rect]) -> Rect | None:
    """Where a tile put back goes beside those of the others there when it
    was taken away still there, at rects now: moved and scaled as they
    were since, together. None if none of them are."""

    was = {i: r for i, r in place.others if i in rects}
    if not was:
        return None

    before = _outline(was.values())
    now = _outline(rects[i] for i in was)
    scale = min(
        now.width / max(before.width, _HAIR), now.height / max(before.height, _HAIR)
    )
    rect = _box_rect(place.box, place.shape)
    return _scaled(
        rect, scale, now.left - before.left * scale, now.top - before.top * scale
    )


def _is_near_inside(rect: Rect, area: Rect) -> bool:
    return (
        rect.left >= area.left - _NEAR_SHARE
        and rect.top >= area.top - _NEAR_SHARE
        and rect.right <= area.right + _NEAR_SHARE
        and rect.bottom <= area.bottom + _NEAR_SHARE
    )


def _most_room(
    rects: list[Rect],
    page: Rect,
    shape: float,
    wanted: float,
    near: tuple[float, float] | None = None,
) -> Rect | None:
    """A tile of this shape where there is the most room for it on the page
    among the tiles, up to wanted wide, in the middle of that room; None if
    there is none. Of rooms as big, the one nearest the point near, if
    given, else the highest, then the leftmost."""

    best = None
    for room in _rooms(rects, page, shape):
        distance = 0.0
        if near is not None:
            distance = math.hypot(room.center_x - near[0], room.center_y - near[1])
        key = (min(room.width, wanted), -distance, -room.top, -room.left)
        if best is None or key > best[0]:
            best = (key, room)

    if best is None:
        return None

    room = best[1]
    width = min(room.width, wanted)
    height = width / shape
    left = room.center_x - width / 2
    top = room.center_y - height / 2
    return Rect(left, top, left + width, top + height)


def _rooms(rects: list[Rect], page: Rect, shape: float) -> Iterator[Rect]:
    """Empty places of this shape on a page with its top left corner at 0,
    0, each as big as it can be from its top left corner: at the page's
    edges, and at the right and the bottom of each tile."""

    xs = sorted({0.0, *(r.right for r in rects)})
    ys = sorted({0.0, *(r.bottom for r in rects)})

    for x in xs:
        for y in ys:
            width = min(page.right - x, (page.bottom - y) * shape)
            for rect in rects:
                if rect.right <= x or rect.bottom <= y:
                    continue
                # in its way once wider than to its left edge and taller
                # than to its top one
                width = min(width, max(rect.left - x, (rect.top - y) * shape))
            if width > 1e-6:
                yield Rect(x, y, x + width, y + width / shape)


def _pushed_aside(
    spots: dict[str, Rect],
    by: Rect,
    page: Rect,
    least: Callable[[Rect], float],
    kept: dict[str, Rect] | None = None,
    fixed: Collection[str] = (),
    left: Rect | None = None,
) -> dict[str, Rect] | None:
    """Each tile a tile at by covers made room for, but those fixed: as big
    as it can be, of its own shape, in what by leaves of its own place (see
    _set_aside). Left less than ROOM_SHARE of its width there, or smaller
    than least says, it goes out of its place, if it is bigger there (see
    _room_out); and once out, it comes back only to be bigger in its place.
    None if one would be smaller than least says, on its shorter side.

    Out of its place, it goes as near as it can to the place the tile at by
    left (left), as if the two swapped, or else to its own; and it is grown
    again once the others are all where they end up, one set aside after it
    perhaps having left it more room."""

    # where each of the others is: at its spot, until set aside
    places = dict(spots)
    pushed = {}
    # those gone out of their place, and the point each goes toward
    out = {}
    for video_id, spot in spots.items():
        if video_id in fixed or not by.overlaps(spot, _HAIR):
            continue

        rect = _set_aside(spot, by)
        width = 0.0 if rect is None else rect.width
        was = (kept or {}).get(video_id)
        is_out = was is not None and not was.is_inside(spot)
        if (
            rect is None
            or min(rect.width, rect.height) < least(spot) - _HAIR
            or width < spot.width * ROOM_SHARE
            or (is_out and width < spot.width)
        ):
            toward = left or spot
            near = (toward.center_x, toward.center_y)
            # not its own place: it is leaving that
            taken = [by, *(r for i, r in places.items() if i != video_id)]
            room = _room_out(spot, taken, page, near, was)
            if room is not None and room.width > width:
                rect = room
                out[video_id] = near

        if rect is None or min(rect.width, rect.height) < least(spot) - _HAIR:
            return None
        pushed[video_id] = places[video_id] = rect

    for video_id, near in out.items():
        spot = spots[video_id]
        taken = [by, *(r for i, r in places.items() if i != video_id)]
        pushed[video_id] = places[video_id] = _settled(
            places[video_id], taken, page, spot.width / spot.height, spot.width, near
        )
    return pushed


def _room_out(
    spot: Rect,
    taken: list[Rect],
    page: Rect,
    near: tuple[float, float],
    was: Rect | None,
) -> Rect | None:
    """Where a tile pushed out of its spot goes, clear of the others taken:
    where it was (was), while that is free, grown there and moved toward
    the point near as there is room (see _settled); elsewhere only to be as
    big as it was at its spot, or with nowhere it was. Of the places with
    the most room, the one nearest near. None if there is none."""

    shape = spot.width / spot.height
    wanted = spot.width
    room = was
    if room is not None and any(room.overlaps(t, _HAIR) for t in taken):
        room = None
    if room is not None:
        room = _settled(room, taken, page, shape, wanted, near)
        if room.width >= wanted - _HAIR:
            return room

    elsewhere = _most_room(taken, page, shape, wanted, near)
    if elsewhere is not None:
        elsewhere = _settled(elsewhere, taken, page, shape, wanted, near)
        if room is None or elsewhere.width >= wanted - _HAIR:
            return elsewhere
    return room


def _settled(
    rect: Rect,
    taken: list[Rect],
    page: Rect,
    shape: float,
    wanted: float,
    near: tuple[float, float],
) -> Rect:
    """A tile pushed out of its place, at rect: slid toward the point
    near as far as it is clear (see _slid), and grown back up to wanted
    wide there (see _grown), then slid again."""

    rect = _slid(rect, taken, page, *near)
    rect = _grown(rect, taken, page, shape, wanted)
    return _slid(rect, taken, page, *near)


def _slid(rect: Rect, taken: list[Rect], page: Rect, x: float, y: float) -> Rect:
    """A tile at rect slid across, then down, toward its middle at x, y,
    as far as it goes clear of the others taken and the page's edges."""

    for is_column in (True, False):
        low, high = rect.span(is_column)
        page_low, page_high = page.span(is_column)
        shift = (x if is_column else y) - (low + high) / 2
        if shift > 0:
            shift = min(shift, page_high - high)
        else:
            shift = max(shift, page_low - low)
        cross_low, cross_high = rect.span(not is_column)
        for other in taken:
            other_low, other_high = other.span(not is_column)
            # not in its way unless sharing more than a hair of its side
            if other_low >= cross_high - _HAIR or other_high <= cross_low + _HAIR:
                continue
            # clear of it already, so ahead of it if beginning after it
            other_low, other_high = other.span(is_column)
            if shift > 0 and other_low > low:
                shift = min(shift, max(other_low - high, 0.0))
            elif shift < 0 and other_high < high:
                shift = max(shift, min(other_high - low, 0.0))
        rect = rect.moved(shift, 0) if is_column else rect.moved(0, shift)
    return rect


# where a tile grows from (see _grown): its middle first, then its
# corners and the middles of its sides, as shares of its width and height
_ANCHORS = (
    (0.5, 0.5),
    *((x, y) for x in (0, 0.5, 1) for y in (0, 0.5, 1) if (x, y) != (0.5, 0.5)),
)


def _grown(
    rect: Rect, taken: list[Rect], page: Rect, shape: float, wanted: float
) -> Rect:
    """A tile at rect, of this shape, grown as big as it can be up to
    wanted wide, clear of the others taken and the page's edges, still over
    all of rect: from its middle, a corner or the middle of a side, the
    first of those as big."""

    best = rect
    for fx, fy in _ANCHORS:
        x = rect.left + fx * rect.width
        y = rect.top + fy * rect.height
        width = min(wanted, _grows_to(x, fx, page.left, page.right, 1.0))
        width = min(width, _grows_to(y, fy, page.top, page.bottom, shape))
        for other in taken:
            width = min(
                width,
                max(
                    _meets(x, fx, other.left, other.right, 1.0),
                    _meets(y, fy, other.top, other.bottom, shape),
                ),
            )
        if width > best.width + _HAIR:
            height = width / shape
            left, top = x - fx * width, y - fy * height
            best = Rect(left, top, left + width, top + height)
    return best


def _grows_to(at: float, share: float, low: float, high: float, scale: float) -> float:
    """How wide a tile grows, across (scale 1) or down (its shape), from a
    point at share of its span, before it reaches low or high."""

    width = float("inf")
    if share > 0:
        width = min(width, (at - low) * scale / share)
    if share < 1:
        width = min(width, (high - at) * scale / (1 - share))
    return width


def _meets(at: float, share: float, low: float, high: float, scale: float) -> float:
    """How wide a tile grows, as in _grows_to, before it is over a span
    from low to high by more than a hair, across (scale 1) or down."""

    width = 0.0
    if at >= high - _HAIR:
        if share == 0:
            return float("inf")
        width = (at - high + _HAIR) * scale / share
    if at <= low + _HAIR:
        if share == 1:
            return float("inf")
        width = max(width, (low + _HAIR - at) * scale / (1 - share))
    return width


def _set_aside(spot: Rect, by: Rect) -> Rect | None:
    """A tile at spot, of its shape, as big as it can be in what by leaves
    of it: the part left beside it, above or below, the first of those as
    big. In there, it is as far from by as by covers more of one end of
    spot than of the other, so that it goes along smoothly as by is moved
    (see _away)."""

    shape = spot.width / spot.height
    best = None
    for room in (
        spot._replace(right=min(spot.right, by.left)),
        spot._replace(left=max(spot.left, by.right)),
        spot._replace(bottom=min(spot.bottom, by.top)),
        spot._replace(top=max(spot.top, by.bottom)),
    ):
        if room.width <= _HAIR or room.height <= _HAIR:
            continue
        width = min(room.width, room.height * shape)
        if best is not None and width <= best.width:
            continue

        height = width / shape
        left = room.left + _away(spot.left, spot.right, by.left, by.right) * (
            room.width - width
        )
        top = room.top + _away(spot.top, spot.bottom, by.top, by.bottom) * (
            room.height - height
        )
        best = Rect(left, top, left + width, top + height)
    return best


def _away(low: float, high: float, by_low: float, by_high: float) -> float:
    """Where along a span from low to high something is put to be away
    from another from by_low to by_high: 0 at its low end, 1 at the high,
    toward the end more of it is left at; by over all of it, toward the
    end it covers the least beyond."""

    before = max(0.0, by_low - low)
    after = max(0.0, high - by_high)
    if before + after > _HAIR:
        return after / (before + after)

    beyond = (by_high - by_low) - (high - low)
    if beyond <= _HAIR:
        return 0.5
    return min(max((low - by_low) / beyond, 0.0), 1.0)


class _Room(NamedTuple):
    """The room a tile is in, across (is_column) or down: the nearest
    tile beside it before it (to the left, or above) and after it, not over
    it, None for the page's edge; and where it begins and ends, at them."""

    before: Rect | None
    after: Rect | None
    begin: float
    end: float

    @property
    def is_by_tile(self) -> bool:
        return self.before is not None or self.after is not None


def _room(rect: Rect, others: Iterable[Rect], page: Rect, is_column: bool) -> _Room:
    low, high = rect.span(is_column)
    before = after = None
    for other in others:
        if not rect.is_beside(other, is_column):
            continue
        other_low, other_high = other.span(is_column)
        if other_high <= low + _NEAR:
            if before is None or other_high > before.span(is_column)[1]:
                before = other
        elif other_low >= high - _NEAR:
            if after is None or other_low < after.span(is_column)[0]:
                after = other

    begin, end = page.span(is_column)
    if before is not None:
        begin = before.span(is_column)[1]
    if after is not None:
        end = after.span(is_column)[0]
    return _Room(before, after, begin, end)


def _gap(
    rect: Rect, other: Rect | None, start: float, end: float, is_column: bool
) -> Gap | None:
    """The room from start to end between rect and the tile beside it, or
    the page's edge (None), along what they share; None where they touch."""

    if end - start <= _NEAR:
        return None
    low, high = rect.span(not is_column)
    if other is not None:
        other_low, other_high = other.span(not is_column)
        low, high = max(low, other_low), min(high, other_high)
    return Gap(is_column, start, end, low, high, other is None)


def _gaps_beside(
    rect: Rect, others: list[Rect], page: Rect, is_column: bool
) -> list[Gap]:
    """The room before rect and after it, where there is any (see _gap).
    By the page's edges either side, only the less, its margin, and none
    where the two are the same: it is centered, and said so (see
    TileDrag.guides)."""

    room = _room(rect, others, page, is_column)
    low, high = rect.span(is_column)
    gaps = [
        gap
        for gap in (
            _gap(rect, room.before, room.begin, low, is_column),
            _gap(rect, room.after, high, room.end, is_column),
        )
        if gap is not None
    ]
    if len(gaps) == 2 and gaps[0].is_page and gaps[1].is_page:
        if abs(gaps[0].size - gaps[1].size) < _NEAR:
            return []
        return [min(gaps, key=lambda gap: gap.size)]
    return gaps


def _is_same_size(gap: Gap, other: Gap) -> bool:
    """Whether two are as big, but not by the page's same edge: two margins
    there are only edges lined up (see TileDrag.guides)."""

    if abs(gap.size - other.size) >= _NEAR:
        return False
    if gap.is_page and other.is_page:
        return (
            abs(gap.start - other.start) >= _NEAR and abs(gap.end - other.end) >= _NEAR
        )
    return True


def _gaps_between(rects: list[Rect], page: Rect, is_column: bool) -> list[Gap]:
    """The room between each tile and those beside it, or the page's
    edges, each once."""

    gaps = {}
    for i, rect in enumerate(rects):
        rest = rects[:i] + rects[i + 1 :]
        for gap in _gaps_beside(rect, rest, page, is_column):
            gaps[gap] = None
    return list(gaps)


def _contains(rect: Rect, x: float, y: float, reach: float = 0) -> bool:
    return (
        rect.left - reach <= x <= rect.right + reach
        and rect.top - reach <= y <= rect.bottom + reach
    )


def _reach(low: float, high: float, at: float, side: int) -> tuple[float, float]:
    """How far from at a span from low to high begins and ends, going the
    way of side: right (down), or left (up)."""

    if side > 0:
        return low - at, high - at
    return at - high, at - low


def _side(at: float, low: float, high: float, reach: float) -> int:
    if abs(at - low) <= reach:
        return -1
    if abs(at - high) <= reach:
        return 1
    return 0


class _Targets(NamedTuple):
    """What a tile snaps to, by the others, across (True) and down: where
    an edge snaps to, and a middle, and the room between them, if it snaps
    to gaps."""

    lines: dict[bool, list[float]]
    middles: dict[bool, list[float]]
    gaps: dict[bool, list[Gap]]


class TileDrag:
    """A tile moved, or sized by an edge or a corner, by the pointer.

    It goes where the pointer takes it, but never off the page, nor over
    another tile unless told it may (is_over): one in the way stops it, and
    a move slides along it instead. Where it can go nowhere on the way, it
    stays where it was.

    Told to push them (is_pushing), it goes where the pointer takes it too,
    each tile it goes over set aside, made smaller in its own place or put
    where there is room, in the place it left if it can be (see
    _pushed_aside, and pushed): always from where
    they were at the press, so that they come back as it goes away. One it
    would make smaller than MIN_CELL stops it, as one in the way does. Those
    it was over at the press, it goes over.

    Whichever it is told, a locked tile stops it, as one in the way does,
    but one it was over at the press.

    Sized, it keeps the shape it has (unless told not to), the edge held
    where the pointer is and the one across from it where it was. By a
    side, the other two each give half, or, one of them against a tile or
    the page's edge at the press, all of it goes the other way. By a
    corner, the corner across from it stays where it was. Either way it
    grows no further than the page's edge, or a tile in the way, and never
    moves. It is never made smaller than MIN_CELL, nor a corner pulled
    past the one across.

    Snapping, an edge (or the middle) near enough another tile's, or the
    page's, goes to it (see SNAP_REACH); and to where it started, moved,
    or sized once an edge held has been away. What it is then in line with
    is shown (see guides). So does an edge to where it is as far from the
    tile beside it, or the page's edge, as two others are, or another from
    the page's edge, or as the tile is on its other side (see gaps). Sized
    to any shape, it snaps to its video's, where the picture fits it with
    no bars (see fits). Each of these it snaps to only if told (snaps).
    In the page's pixels, which are the screen's.
    """

    def __init__(
        self,
        tiles: FreeTiles,
        video_id: str,
        handle: Handle,
        page_width: float,
        page_height: float,
        pointer: tuple[float, float],
        shape: float | None = None,
        *,
        snaps: Collection[TileSnap],
        is_over: bool = False,
        is_pushing: bool = False,
    ):
        rects = tiles.rects(page_width, page_height)

        self.video_id = video_id
        self.handle = handle
        self.page = Rect(0, 0, page_width, page_height)
        self.start = rects[video_id]
        # what it snaps to, snapping
        self.snaps = frozenset(snaps)
        self._spots = {i: r for i, r in rects.items() if i != video_id}
        self.others = list(self._spots.values())
        # what it snaps to, by the set of those pushed aside: the others stay
        # where they are while it is moved, but those pushed
        self._targets_by: dict[frozenset[str], _Targets] = {}
        # those now, and where the others are now, pushed or not, until
        # those pushed change
        self._now: tuple[_Targets, list[Rect]] | None = None
        # the shape it keeps, sized, and its video's, which it snaps to sized
        # to any shape
        self.shape = self.start.width / max(self.start.height, 1e-9)
        self.video_shape = shape
        # sized to its video's shape, the last time it was moved
        self.fits = False

        self._press = pointer
        self._last = pointer
        self.rect = self.start

        # going over the others as it likes (Tile Overlap: On), or pushing
        # them aside (Push Aside)
        self.is_over = is_over
        self.is_pushing = is_pushing
        # one made overlapping, by hand in the file, or before the tiles were
        # kept apart: moved as it likes until it is clear of the others
        self._is_kept_apart = (
            not is_over
            and not is_pushing
            and not any(self.start.overlaps(r) for r in self.others)
        )

        # pushing, the others set aside, and those set aside before put back
        # where they were, to be shown so
        self.pushed: dict[str, Rect] = {}
        # those it is over at the press, not pushed
        self._fixed = frozenset(
            i for i, r in self._spots.items() if self.start.overlaps(r)
        )
        # the locked tiles, and those of them in its way, whichever way it
        # may go
        locked = {i: r for i, r in self._spots.items() if i in tiles.locked}
        self.locked = list(locked.values())
        self._walls = [r for i, r in locked.items() if i not in self._fixed]
        # the last tile pushed for, and what it pushed
        self._last_push: tuple[Rect, dict[str, Rect] | None] | None = None

        # sized by a side, the end of the other two edges held still: the
        # first (top, left) or the last, against something; None, neither
        self._held_end = self._end_against()
        # gone far enough from where it started, across (True) and down
        # (False), to snap back there and say so
        self._left_start = {True: False, False: False}

    @property
    def is_move(self) -> bool:
        return self.handle == MOVE

    def moved(
        self, pointer: tuple[float, float], is_snapping=True, keeps_shape=True
    ) -> Rect:
        """Where the tile goes for the pointer there."""

        def place(at):
            return self._place(at, is_snapping, keeps_shape)

        rect = place(pointer)
        if self._is_valid(rect):
            self._last = pointer
        else:
            if self.is_move:
                # along the way it can go across, then the way it can go down
                across = self._furthest(self._last, (pointer[0], self._last[1]), place)
                self._last = self._furthest(across, (across[0], pointer[1]), place)
            else:
                self._last = self._furthest(self._last, pointer, place)

            rect = place(self._last)
            if not self._is_valid(rect):
                # nowhere it can go on the way there
                return self.rect

        if not self._is_kept_apart and not self.is_over and not self.is_pushing:
            self._is_kept_apart = not any(rect.overlaps(r) for r in self.others)

        # within a hair of the page's edge, on it
        self.rect = Rect(
            max(rect.left, self.page.left),
            max(rect.top, self.page.top),
            min(rect.right, self.page.right),
            min(rect.bottom, self.page.bottom),
        )
        self._push_for(self.rect)
        self.fits = (
            not keeps_shape
            and self._is_fitting(is_snapping)
            and self._is_fit(self.rect.width, self.rect.height)
        )
        return self.rect

    def guides(self) -> list[Guide]:
        """What the tile is in line with where it is: an edge or its middle
        at another's, or the page's."""

        rect = self.rect
        page = self.page
        guides = []

        def lines(is_column: bool, own: tuple[float, float, float]):
            """Each line one of the tile's own is at, with what it is: its
            edges and middle in turn, then those of the page or the other."""

            if is_column:
                yield page, page.left, GuideKind.PAGE_EDGE
                yield page, page.right, GuideKind.PAGE_EDGE
                middle = page.center_x
            else:
                yield page, page.top, GuideKind.PAGE_EDGE
                yield page, page.bottom, GuideKind.PAGE_EDGE
                middle = page.center_y
            # its own middle there, not an edge
            if abs(own[2] - middle) < _NEAR:
                yield page, middle, GuideKind.CENTERED
            else:
                yield page, middle, GuideKind.PAGE_MIDDLE

            for other_id, spot in self._spots.items():
                # pushed, where it is now
                other = self.pushed.get(other_id, spot)
                theirs = (*other.span(is_column), other.middle(is_column))
                is_beside = rect.is_beside(other, is_column)
                for i, j in ((0, 1), (1, 0), (0, 0), (1, 1)):
                    if abs(own[i] - theirs[j]) < _NEAR:
                        # one edge on the other's across from it, side by side
                        is_touching = i != j and is_beside
                        kind = GuideKind.TOUCHING if is_touching else GuideKind.EDGES
                        yield other, theirs[j], kind
                yield other, theirs[2], GuideKind.MIDDLES

        for is_column in (True, False):
            if is_column:
                own = (rect.left, rect.right, rect.center_x)
                across = (page.top, page.bottom)
            else:
                own = (rect.top, rect.bottom, rect.center_y)
                across = (page.left, page.right)

            seen = set()
            for other, position, kind in lines(is_column, own):
                if kind is GuideKind.MIDDLES:
                    is_at = abs(own[2] - position) < _NEAR
                else:
                    is_at = any(abs(edge - position) < _NEAR for edge in own)
                if (position, kind) in seen or not is_at:
                    continue
                seen.add((position, kind))

                # along the page, or along the two tiles
                if other is page:
                    start, end = across
                elif is_column:
                    start = min(rect.top, other.top)
                    end = max(rect.bottom, other.bottom)
                else:
                    start = min(rect.left, other.left)
                    end = max(rect.right, other.right)
                guides.append(Guide(is_column, position, start, end, kind))
        guides += self._start_guides()
        return [g for g in guides if _GUIDE_SNAPS[g.kind] in self.snaps]

    def gaps(self) -> list[Gap]:
        """The room beside the tile where it is as big as others have, or
        as on its other side, to be shown while it is: the tile's and
        theirs (see _gaps_beside)."""

        if TileSnap.EQUAL_GAPS not in self.snaps:
            return []

        shown = {}
        for is_column in (True, False):
            own = _gaps_beside(self.rect, self._places(), self.page, is_column)
            theirs = self._gaps_of(self.rect, is_column)
            for gap in own:
                same = [other for other in theirs if _is_same_size(gap, other)]
                if same:
                    shown.update(dict.fromkeys([gap, *same]))

            if len(own) == 2 and _is_same_size(*own):
                shown.update(dict.fromkeys(own))
        return list(shown)

    def snap_to(self, snaps: Collection[TileSnap]) -> None:
        """What it snaps to from now on, changed while it is held."""

        self.snaps = frozenset(snaps)
        self._targets_by = {}
        self._now = None

    def _start_guides(self) -> list[Guide]:
        """Where the tile's edges are back in line with the dashed outline
        of where it started, once they have been away that way: moved, any
        of them; sized, the ones held."""

        rect, start = self.rect, self.start
        guides = []
        for is_column, side in ((True, self.handle[0]), (False, self.handle[1])):
            if not self._left_start[is_column]:
                continue
            if is_column:
                own, old = (rect.left, rect.right), (start.left, start.right)
                span = (min(rect.top, start.top), max(rect.bottom, start.bottom))
            else:
                own, old = (rect.top, rect.bottom), (start.top, start.bottom)
                span = (min(rect.left, start.left), max(rect.right, start.right))

            if not self.is_move:
                if not side:
                    continue
                own = (own[0] if side < 0 else own[1],)
            guides.extend(
                Guide(is_column, position, *span, GuideKind.START)
                for position in old
                if any(abs(edge - position) < _NEAR for edge in own)
            )
        return guides

    def stretched(self) -> Rect:
        """The tile's edges held stretched as far as they go: to the next
        tile, or to the page's edge."""

        rect = self.start
        side_x, side_y = self.handle
        left, top, right, bottom = rect

        if side_x:
            room = _room(rect, self.others, self.page, True)
            left, right = (room.begin, right) if side_x < 0 else (left, room.end)
        if side_y:
            room = _room(rect, self.others, self.page, False)
            top, bottom = (room.begin, bottom) if side_y < 0 else (top, room.end)

        stretched = Rect(left, top, right, bottom)
        # a corner's two edges each as far as they go may meet a tile only
        # one of them was clear of
        if not self._is_valid(stretched):
            stretched = rect
        # those pushed by a move before it, pushed for it instead
        self._push_for(stretched)
        return stretched

    # --- inside ---

    def _place(self, pointer, is_snapping: bool, keeps_shape: bool) -> Rect:
        dx = pointer[0] - self._press[0]
        dy = pointer[1] - self._press[1]
        if abs(dx) > SNAP_REACH:
            self._left_start[True] = True
        if abs(dy) > SNAP_REACH:
            self._left_start[False] = True

        if self.is_move:
            rect = self.start.moved(dx, dy)
            # kept on the page
            rect = rect.moved(
                max(0.0, -rect.left) - max(0.0, rect.right - self.page.right),
                max(0.0, -rect.top) - max(0.0, rect.bottom - self.page.bottom),
            )
            if is_snapping:
                dx = self._snap_shift(rect, True)
                dy = self._snap_shift(rect.moved(dx, 0), False)
                if TileSnap.EQUAL_GAPS in self.snaps:
                    # moved down, it may be beside others, whose gaps across
                    # are not the same: across again, and down again for
                    # that, until the two agree, a few times at most
                    for _ in range(2):
                        again = self._snap_shift(rect.moved(0, dy), True)
                        if abs(again - dx) < _NEAR:
                            break
                        dx = again
                        dy = self._snap_shift(rect.moved(dx, 0), False)
                rect = rect.moved(dx, dy)
            return rect

        return self._sized(dx, dy, is_snapping, keeps_shape)

    def _sized(self, dx, dy, is_snapping, keeps_shape) -> Rect:
        side_x, side_y = self.handle
        left, top, right, bottom = self.start

        # the edges held, where the pointer takes them, snapped: by a
        # corner, each with the other where it is
        if side_x < 0:
            left += dx
        elif side_x > 0:
            right += dx
        if side_y < 0:
            top += dy
        elif side_y > 0:
            bottom += dy
        snap = (is_snapping, keeps_shape)
        if side_x:
            edge = self._snapped(Rect(left, top, right, bottom), True, side_x, *snap)
            left, right = (edge, right) if side_x < 0 else (left, edge)
        if side_y:
            edge = self._snapped(Rect(left, top, right, bottom), False, side_y, *snap)
            top, bottom = (edge, bottom) if side_y < 0 else (top, edge)

        # never smaller than MIN_CELL either way, nor turned inside out
        least = min(MIN_CELL, self.start.width, self.start.height)
        least_width = least_height = least
        if keeps_shape:
            least_width = max(least, least * self.shape)
            least_height = max(least, least / self.shape)
        if side_x < 0:
            left = min(left, right - least_width)
        elif side_x > 0:
            right = max(right, left + least_width)
        if side_y < 0:
            top = min(top, bottom - least_height)
        elif side_y > 0:
            bottom = max(bottom, top + least_height)

        if side_x and side_y:
            rect = Rect(left, top, right, bottom)
            if not keeps_shape and self._is_fitting(is_snapping):
                rect = self._fitted(*rect)
            return self._cornered(rect, keeps_shape)

        # off the page, it is cut short where it reaches the edge (see moved)
        if keeps_shape:
            return self._shaped(left, top, right, bottom)

        if self._is_fitting(is_snapping):
            return self._fitted(left, top, right, bottom)
        return Rect(left, top, right, bottom)

    def _is_fitting(self, is_snapping: bool) -> bool:
        """Whether, sized to any shape, it snaps to its video's."""

        return (
            is_snapping
            and bool(self.video_shape)
            and TileSnap.VIDEO_SHAPE in self.snaps
        )

    def _is_fit(self, width: float, height: float) -> bool:
        return bool(self.video_shape) and abs(width - height * self.video_shape) < 1

    def _fitted(self, left, top, right, bottom) -> Rect:
        """Sized to any shape, the edges held snapped to where the tile is
        its video's shape, if near enough: by a corner, across first."""

        side_x, side_y = self.handle
        width, height = right - left, bottom - top

        if side_x and abs(width - height * self.video_shape) <= SNAP_REACH:
            width = height * self.video_shape
            if side_x < 0:
                left = right - width
            else:
                right = left + width
        elif side_y and abs(height - width / self.video_shape) <= SNAP_REACH:
            height = width / self.video_shape
            if side_y < 0:
                top = bottom - height
            else:
                bottom = top + height

        return Rect(left, top, right, bottom)

    def _shaped(self, left, top, right, bottom) -> Rect:
        """Sized by a side, the edges made the tile's shape: the other two
        each give half, or all of it away from the end held (see
        _end_against). Where that takes it into a tile, or off the page, it
        is cut short (see moved)."""

        start = self.start
        if self.handle[0]:
            low, high = self._grown(
                start.top, start.bottom, (right - left) / self.shape
            )
            return Rect(left, low, right, high)
        low, high = self._grown(start.left, start.right, (bottom - top) * self.shape)
        return Rect(low, top, high, bottom)

    def _grown(self, low: float, high: float, size: float) -> tuple[float, float]:
        if self._held_end == -1:
            return low, low + size
        if self._held_end == 1:
            return high - size, high
        middle = (low + high) / 2
        return middle - size / 2, middle + size / 2

    def _end_against(self) -> int | None:
        """Sized by a side, the end of the other two edges against a tile or
        the page's edge at the press, to be held still: -1 the first (top,
        left), 1 the last, None neither; both, the first."""

        side_x, side_y = self.handle
        if self.is_move or (side_x and side_y):
            return None

        start, page = self.start, self.page
        others = self._in_way
        if side_x:
            beside = [o for o in others if o.is_along(start)]
            is_first = start.top <= page.top + _NEAR or any(
                abs(o.bottom - start.top) < _NEAR for o in beside
            )
            is_last = start.bottom >= page.bottom - _NEAR or any(
                abs(o.top - start.bottom) < _NEAR for o in beside
            )
        else:
            beside = [o for o in others if o.is_across(start)]
            is_first = start.left <= page.left + _NEAR or any(
                abs(o.right - start.left) < _NEAR for o in beside
            )
            is_last = start.right >= page.right - _NEAR or any(
                abs(o.left - start.right) < _NEAR for o in beside
            )

        if is_first:
            return -1
        if is_last:
            return 1
        return None

    def _cornered(self, rect: Rect, keeps_shape: bool) -> Rect:
        """Sized by a corner, the corner across from it where it was: as big
        as the pointer makes it (keeping its shape, the way the pointer went
        furthest), but no further than the page's edge, nor, kept apart,
        into a tile in the way, nor ever into a locked one. To any shape,
        against one in the way it slides along it: the edge that went into
        it the least stops at it."""

        side_x, side_y = self.handle
        start, page = self.start, self.page
        # the corner held still
        x = start.left if side_x > 0 else start.right
        y = start.top if side_y > 0 else start.bottom

        room_x = page.right - x if side_x > 0 else x - page.left
        room_y = page.bottom - y if side_y > 0 else y - page.top
        # how far from it each tile ahead begins, across and down
        ahead = []
        for other in self._in_way:
            begin_x, end_x = _reach(other.left, other.right, x, side_x)
            begin_y, end_y = _reach(other.top, other.bottom, y, side_y)
            if end_x > _HAIR and end_y > _HAIR:
                ahead.append((begin_x, begin_y))

        width, height = rect.width, rect.height
        if keeps_shape:
            width = min(max(width, height * self.shape), room_x, room_y * self.shape)
            for begin_x, begin_y in ahead:
                width = min(width, max(begin_x, begin_y * self.shape))
            height = width / self.shape
        else:
            width, height = min(width, room_x), min(height, room_y)
            while True:
                into = [
                    (begin_x, begin_y)
                    for begin_x, begin_y in ahead
                    if width > begin_x + _HAIR and height > begin_y + _HAIR
                ]
                if not into:
                    break
                begin_x, begin_y = into[0]
                if width - begin_x <= height - begin_y:
                    width = begin_x
                else:
                    height = begin_y

        left = x if side_x > 0 else x - width
        top = y if side_y > 0 else y - height
        return Rect(left, top, left + width, top + height)

    def _lines_of(self, is_column: bool, others: list[Rect]) -> list[float]:
        """Where an edge snaps to: the others' edges, the page's, and the
        page's middle, to split it in two; those it snaps to."""

        page, snaps = self.page, self.snaps
        lines = []
        if TileSnap.WINDOW_EDGES in snaps:
            lines += page.span(is_column)
        if TileSnap.WINDOW_MIDDLE in snaps:
            lines.append(page.middle(is_column))
        if TileSnap.TILE_EDGES in snaps:
            for other in others:
                lines += other.span(is_column)
        return lines

    def _middles_of(self, is_column: bool, others: list[Rect]) -> list[float]:
        middles = []
        if TileSnap.WINDOW_MIDDLE in self.snaps:
            middles.append(self.page.middle(is_column))
        if TileSnap.TILE_MIDDLES in self.snaps:
            middles += [other.middle(is_column) for other in others]
        return middles

    def _targets(self) -> _Targets:
        """What it snaps to: not where those pushed aside were, which is
        empty, or under the tile."""

        return self._snapping_now()[0]

    def _places(self) -> list[Rect]:
        """Where the others are now, those pushed aside too: the tiles beside
        it, which the room it has is measured to."""

        return self._snapping_now()[1]

    def _snapping_now(self) -> tuple[_Targets, list[Rect]]:
        if self._now is None:
            places = [self.pushed.get(i, r) for i, r in self._spots.items()]
            self._now = (self._targets_aside(), places)
        return self._now

    def _targets_aside(self) -> _Targets:
        aside = frozenset(i for i, r in self.pushed.items() if r != self._spots[i])
        targets = self._targets_by.get(aside)
        if targets is None:
            others = [r for i, r in self._spots.items() if i not in aside]
            sides = (True, False)
            gaps = {c: [] for c in sides}
            if TileSnap.EQUAL_GAPS in self.snaps:
                for c in sides:
                    gaps[c] = _gaps_between(others, self.page, c)
            targets = _Targets(
                {c: self._lines_of(c, others) for c in sides},
                {c: self._middles_of(c, others) for c in sides},
                gaps,
            )
            self._targets_by[aside] = targets
        return targets

    def _gaps_of(self, rect: Rect, is_column: bool) -> list[Gap]:
        """The room between the others, and by the page's edges, but where
        the tile at rect is."""

        return [
            gap
            for gap in self._targets().gaps[is_column]
            if not rect.overlaps(gap.area)
        ]

    def _room_of(
        self, rect: Rect, is_column: bool
    ) -> tuple[_Room, set[float], set[float]]:
        """The room the tile at rect is in, and how big the room others
        have is (see _gaps_of), to be as far from what is before it, and
        after it. Not, by the page's edge, as far as another is from the
        same edge: that is only their edges lined up (see _is_same_size)."""

        room = _room(rect, self._places(), self.page, is_column)
        page_low, page_high = self.page.span(is_column)
        gaps = self._gaps_of(rect, is_column)
        before = {
            gap.size
            for gap in gaps
            if room.before is not None
            or not gap.is_page
            or abs(gap.start - page_low) >= _NEAR
        }
        after = {
            gap.size
            for gap in gaps
            if room.after is not None
            or not gap.is_page
            or abs(gap.end - page_high) >= _NEAR
        }
        return room, before, after

    def _gap_shifts(self, rect: Rect, is_column: bool) -> list[float]:
        """How far a tile moved goes to be as far from one beside it, or the
        page's edge, as others are from theirs (see _gaps_of), or as far
        from the one on either side."""

        room, before, after = self._room_of(rect, is_column)
        low, high = rect.span(is_column)
        if not room.is_by_tile:
            # between the page's edges, a margin only less than the other
            # once there (see _gaps_beside)
            free = room.end - room.begin - (high - low)
            before = {size for size in before if 2 * size <= free - _NEAR}
            after = {size for size in after if 2 * size <= free - _NEAR}
        shifts = [room.begin + size - low for size in before]
        shifts += [room.end - size - high for size in after]
        # in the middle of the page, it is centered (see _lines_of)
        if room.is_by_tile:
            shifts.append((room.begin + room.end - low - high) / 2)
        return shifts

    def _gap_lines(
        self, rect: Rect, is_column: bool, side: int, keeps_shape: bool
    ) -> list[float]:
        """Where the edge held of the tile at rect snaps to be as far from
        one beside it, or the page's edge, as others are from theirs (see
        _gaps_of), or as the edge across from it is from the one on its
        side."""

        if keeps_shape and not all(self.handle):
            # by a side, the other two edges as the shape takes them
            rect = self._shaped(*rect)
        low, high = rect.span(is_column)

        room, before, after = self._room_of(rect, is_column)
        sizes = before if side < 0 else after
        across = room.end - high if side < 0 else low - room.begin
        if room.is_by_tile:
            if across > _NEAR:
                sizes.add(across)
        else:
            # between the page's edges, a margin only less than the other
            # (see _gaps_beside)
            sizes = {size for size in sizes if size <= across - _NEAR}

        if side < 0:
            return [room.begin + size for size in sizes]
        return [room.end - size for size in sizes]

    def _snapped(
        self,
        rect: Rect,
        is_column: bool,
        side: int,
        is_snapping: bool,
        keeps_shape: bool,
    ) -> float:
        """Where the edge held, on side, of the tile at rect goes."""

        position = rect.span(is_column)[side > 0]
        if not is_snapping:
            return position
        lines = self._targets().lines[is_column]
        if TileSnap.EQUAL_GAPS in self.snaps:
            gap_lines = self._gap_lines(rect, is_column, side, keeps_shape)
            lines = [*lines, *gap_lines]
        if self._left_start[is_column] and TileSnap.OLD_PLACE in self.snaps:
            lines = [*lines, *self.start.span(is_column)]
        near = [line for line in lines if abs(line - position) <= SNAP_REACH]
        return min(near, key=lambda line: abs(line - position), default=position)

    def _snap_shift(self, rect: Rect, is_column: bool) -> float:
        """How far a tile moved goes to put an edge, or its middle, in line
        with the nearest near enough."""

        edges, middle = rect.span(is_column), rect.middle(is_column)
        targets = self._targets()
        lines = targets.lines[is_column]
        # where it started too: moved along a row, kept in its column
        if TileSnap.OLD_PLACE in self.snaps:
            lines = [*lines, *self.start.span(is_column)]

        shifts = [line - edge for line in lines for edge in edges]
        shifts += [line - middle for line in targets.middles[is_column]]
        if TileSnap.EQUAL_GAPS in self.snaps:
            shifts += self._gap_shifts(rect, is_column)
        near = [shift for shift in shifts if abs(shift) <= SNAP_REACH]
        return min(near, key=abs, default=0.0)

    def _is_valid(self, rect: Rect) -> bool:
        page = self.page
        if (
            rect.left < page.left - _HAIR
            or rect.top < page.top - _HAIR
            or rect.right > page.right + _HAIR
            or rect.bottom > page.bottom + _HAIR
        ):
            return False
        # by no more than a hair: where it stops, it is up against the other
        if any(rect.overlaps(other, _HAIR) for other in self._in_way):
            return False
        return not self.is_pushing or self._pushed(rect) is not None

    @property
    def _in_way(self) -> list[Rect]:
        """The tiles it stops at: all the others, kept apart from them, else
        the locked ones."""

        return self.others if self._is_kept_apart else self._walls

    def _pushed(self, rect: Rect) -> dict[str, Rect] | None:
        """The others set aside for the tile at rect, from where they were
        at the press; None if it cannot go there (see _pushed_aside)."""

        if self._last_push is not None and self._last_push[0] == rect:
            return self._last_push[1]

        pushed = _pushed_aside(
            self._spots,
            rect,
            self.page,
            lambda spot: min(MIN_CELL, spot.width, spot.height),
            kept=self.pushed,
            fixed=self._fixed,
            left=self.start,
        )
        self._last_push = (rect, pushed)
        return pushed

    def _push_for(self, rect: Rect) -> None:
        """The others set aside for the tile gone to rect: those set aside
        before and not now back where they were."""

        if not self.is_pushing:
            return
        pushed = self._pushed(rect)
        if pushed is None:
            return
        self.pushed = {**{i: self._spots[i] for i in self.pushed}, **pushed}
        self._now = None

    def _furthest(self, start, end, place):
        """The point furthest along from start to end the tile can go to,
        start being one it can."""

        if self._is_valid(place(end)):
            return end

        low, high = 0.0, 1.0
        for _ in range(_STEPS):
            middle = (low + high) / 2
            at = (
                start[0] + (end[0] - start[0]) * middle,
                start[1] + (end[1] - start[1]) * middle,
            )
            if self._is_valid(place(at)):
                low = middle
            else:
                high = middle

        return (
            start[0] + (end[0] - start[0]) * low,
            start[1] + (end[1] - start[1]) * low,
        )
