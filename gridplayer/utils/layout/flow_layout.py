from __future__ import annotations

import itertools
import math
import random
from collections.abc import Mapping
from enum import Enum, auto
from typing import NamedTuple

from gridplayer.utils.drop_zone import DropZone, insert_index
from gridplayer.utils.layout.boxes import (
    EVEN,
    Box,
    Weights,
    line_edges,
    picture_score,
)
from gridplayer.utils.layout.justified import (
    best_splits,
    justified_boxes,
    measure_split,
    split_scorer,
)

# what a video is taken to be shaped like until its own shape is known
DEFAULT_SHAPE = 16 / 9

# how much bigger the pictures must be, on average, for Auto to leave the
# line size it has for one that shows them better: dragging the window's
# edge would flip it to and fro where the two show them about as well
SWITCH_GAIN = 1.08

# in Fit Shapes, how many times more a video's picture counts for each step
# it is made bigger (fewer, smaller), and how many steps there are each way
SIZE_WORTH = 1.5
MAX_SIZE_STEPS = 8

# how much bigger, or smaller, a step makes a video's tile, at least
SIZE_STEP_GAIN = 1.02


class FlowMode(Enum):
    ROWS = auto()
    COLS = auto()
    # each video in a tile of its own shape (see justified_boxes)
    SHAPES = auto()


class Lines(NamedTuple):
    """How many videos each line takes, and whether the lines are columns."""

    lengths: tuple[int, ...]
    is_columns: bool


class _Fitted(NamedTuple):
    """What fit_to chose in Fit Shapes: for which videos, reordered or
    not, of which sizes; the videos in the order they are laid out, their
    shapes, and their lines."""

    key: tuple
    ids: tuple[str, ...]
    shapes: tuple[float, ...]
    lines: Lines


class FlowLayout:
    """Wrapping 1D order for Auto (Rows/Columns First, Fit Shapes). No holes."""

    def __init__(
        self,
        mode: FlowMode = FlowMode.ROWS,
        size: int = 0,
        is_fit: bool = False,
        ids: list[str] | None = None,
        is_match_shapes: bool = False,
        crop: int = 0,
        is_linked: bool = True,
        is_reordered: bool = False,
    ):
        self.mode = mode
        self.size = size
        self.is_fit = is_fit
        # on Auto, fit_to chooses the line size, else it is the square grid's
        self.is_match_shapes = is_match_shapes
        self.ids: list[str] = list(ids) if ids else []
        # in Fit Shapes, the percent of a picture its tile may leave out
        self.crop = crop
        # the lines between the videos of a row go across all the rows, else
        # each row has its own (see own_lines)
        self.is_linked = is_linked
        # in Fit Shapes, the videos put in the order that shows them best
        self.is_reordered = is_reordered
        # in Fit Shapes, how many steps bigger videos are made (smaller,
        # less than nought): how much more their pictures count
        self.sizes: dict[str, int] = {}

        # the line size fit_to chose, and for how many videos in which mode
        self._fitted: tuple[int, FlowMode, int] | None = None

        # in Fit Shapes, the lines fit_to chose and for which videos, and
        # the area's size it was given
        self._fitted_lines: _Fitted | None = None
        self._area = (16, 9)
        self._shapes: dict[str, float] = {}
        # the sizes size_step found, by video and way, and for what layout
        self._size_steps: dict[tuple[str, int], int | None] = {}
        self._size_steps_for: tuple | None = None

    def line_size(self) -> int:
        """How many videos go in a line: a row in Rows First, a column in
        Columns First.

        The size set, or on Auto the one fit_to chose for these videos,
        the square grid's until then.
        """
        count = len(self.ids)
        if count <= 1:
            return 1

        if self.size:
            return self.size

        if (
            self.is_match_shapes
            and self._fitted is not None
            and self._fitted[:2] == (count, self.mode)
        ):
            return self._fitted[2]

        return math.ceil(math.sqrt(count))

    def fit_to(self, width: int, height: int, shapes: Mapping[str, float]) -> None:
        """On Auto with is_match_shapes, choose the line size that shows
        the videos best in an area of this size (see picture_score).

        shapes has each video's width for its height, by id; a video not in
        it is taken to be DEFAULT_SHAPE. The line size there is now is kept
        unless another shows the pictures SWITCH_GAIN times bigger.
        """
        if self.mode == FlowMode.SHAPES:
            self._fit_lines(width, height, shapes)
            return

        count = len(self.ids)
        if not self.is_match_shapes or self.size or count <= 1:
            return

        if width <= 0 or height <= 0:
            return

        video_shapes = [shapes.get(video_id) or DEFAULT_SHAPE for video_id in self.ids]

        def score(line_size: int) -> float:
            placed = zip((box for _id, box in self._boxes(line_size)), video_shapes)
            return picture_score(placed, width, height)

        # for each number of lines, the fewest videos a line can take
        line_sizes = sorted({math.ceil(count / lines) for lines in range(1, count + 1)})
        scores = {line_size: score(line_size) for line_size in line_sizes}
        best = max(line_sizes, key=scores.__getitem__)

        line_size = self.line_size()
        kept = scores.get(line_size)
        if kept is None:
            kept = score(line_size)

        if scores[best] > kept + count * math.log(SWITCH_GAIN):
            line_size = best

        self._fitted = (count, self.mode, line_size)

    def _fit_lines(
        self,
        width: int,
        height: int,
        shapes: Mapping[str, float],
        find_splits=best_splits,
    ):
        """Fit Shapes: choose the rows or columns that show the videos best
        (see best_splits). The lines there are now are kept unless others
        show the pictures SWITCH_GAIN times bigger.

        Reordered, the videos are tried in a few orders as well as their
        own, of like shapes together, and go in the one that shows them
        best. Those made bigger count for more (see sizes).
        """

        if width <= 0 or height <= 0:
            return

        self._area = (width, height)
        self._shapes = dict(shapes)
        if not self.ids:
            return

        def shape_of(video_id):
            return shapes.get(video_id) or DEFAULT_SHAPE

        orders = [self.ids]
        if self.is_reordered and len(self.ids) > 2:
            by_shape = sorted(self.ids, key=shape_of)
            # the widest in the middle, the narrowest out to the ends
            orders += [by_shape, by_shape[::2] + by_shape[1::2][::-1]]

        def scorer(weights, worth, is_columns):
            area = (height, width) if is_columns else (width, height)
            return split_scorer(weights, *area, self._crop_share(), worth)

        key = self._fit_key()
        best, best_score = None, -math.inf
        for order in orders:
            ids = tuple(order)
            video_shapes = tuple(shape_of(i) for i in ids)
            worth = self._worth(ids)
            for is_columns in (False, True):
                weights = _line_weights(video_shapes, is_columns)
                score = scorer(weights, worth, is_columns)
                for split in find_splits(weights, worth):
                    candidate_score = score(split)
                    if candidate_score > best_score:
                        lines = Lines(split.lengths, is_columns)
                        best = _Fitted(key, ids, video_shapes, lines)
                        best_score = candidate_score

        kept = self._fitted_lines
        if kept is not None and kept.key == key:
            kept_shapes = tuple(shape_of(i) for i in kept.ids)
            kept_worth = self._worth(kept.ids)
            weights = _line_weights(kept_shapes, kept.lines.is_columns)
            kept_split = measure_split(weights, kept.lines.lengths, kept_worth)
            kept_score = scorer(weights, kept_worth, kept.lines.is_columns)(kept_split)
            if best_score <= kept_score + len(self.ids) * math.log(SWITCH_GAIN):
                best = kept._replace(shapes=kept_shapes)

        self._fitted_lines = best

    def sized(self) -> dict[str, int]:
        """The videos there are made bigger or smaller, by their sizes."""

        return {i: size for i, size in self.sizes.items() if size and i in self.ids}

    def _worth(self, ids) -> tuple[float, ...] | None:
        """How much each video's picture counts, by its size; None where
        none is made bigger or smaller."""

        steps = [self.sizes.get(i, 0) for i in ids]
        if not any(steps):
            return None
        return tuple(SIZE_WORTH**step for step in steps)

    def size_step(self, video_id: str, way: int) -> int | None:
        """In Fit Shapes, the size (see sizes) a video is made a step bigger
        (way 1) or smaller (way -1) by: the nearest that makes its tile
        bigger, or smaller, in the area it was last fit to; of those that
        make it the same, the nearest nought. None where none does."""

        if self.mode != FlowMode.SHAPES or video_id not in self.ids:
            return None

        layout = (
            self._fit_key(),
            self._area,
            tuple(sorted(self._shapes.items())),
            self._crop_share(),
        )
        if layout != self._size_steps_for:
            self._size_steps, self._size_steps_for = {}, layout

        if (video_id, way) not in self._size_steps:
            self._size_steps[video_id, way] = self._find_size_step(video_id, way)
        return self._size_steps[video_id, way]

    def _find_size_step(self, video_id: str, way: int) -> int | None:
        area = self._tile_area(video_id)
        if not area:
            return None

        step = self.sizes.get(video_id, 0)
        saved = dict(self.sizes), self._fitted_lines

        def area_at(size):
            self.sizes[video_id] = size
            # not cached: each size is tried once, and would push out the
            # splits the layout itself has to find again
            self._fit_lines(*self._area, self._shapes, best_splits.__wrapped__)
            return self._tile_area(video_id)

        try:
            # the more a video counts, the bigger its tile, so the first size
            # far enough is found by halves
            sizes = range(step + way, way * MAX_SIZE_STEPS + way, way)
            areas = {}
            low, high = 0, len(sizes)
            while low < high:
                middle = (low + high) // 2
                areas[middle] = area_at(sizes[middle])
                if (areas[middle] / area) ** way < SIZE_STEP_GAIN:
                    low = middle + 1
                else:
                    high = middle
            if low == len(sizes):
                return None

            size, found = sizes[low], areas[low]
            # on towards nought, as far as the tile stays as it is
            while size * way < 0 and abs(area_at(size + way) / found - 1) < 1e-6:
                size += way
            return size
        finally:
            self.sizes, self._fitted_lines = saved

    def _tile_area(self, video_id: str) -> float:
        box = next((box for i, box in self.boxes() if i == video_id), None)
        if box is None:
            return 0.0
        return (box.right - box.left) * (box.bottom - box.top)

    def _fit_key(self) -> tuple:
        sizes = tuple(self.sizes.get(i, 0) for i in self.ids)
        return tuple(self.ids), self.is_reordered, sizes

    def _fitted_shapes(self) -> _Fitted | None:
        """What fit_to chose in Fit Shapes, if it was for these videos."""

        fitted = self._fitted_lines
        if fitted is None or fitted.key != self._fit_key():
            return None
        return fitted

    def _crop_share(self) -> float:
        return min(max(self.crop, 0), 50) / 100

    def _lines(self) -> Lines:
        """How the videos are laid out in lines now."""

        count = len(self.ids)

        if self.mode == FlowMode.SHAPES:
            fitted = self._fitted_shapes()
            if fitted is not None:
                return fitted.lines
            # until fit_to has chosen, in rows as the square grid has them
            is_columns = False
            line_size = math.ceil(math.sqrt(count)) if count > 1 else 1
        else:
            is_columns = self.mode == FlowMode.COLS
            line_size = self.line_size()

        full, rest = divmod(count, line_size)
        lengths = (line_size,) * full + ((rest,) if rest else ())
        return Lines(lengths or (0,), is_columns)

    def is_columns(self) -> bool:
        """Whether the videos are laid out a column at a time."""

        return self._lines().is_columns

    def displayed_size(self) -> tuple[int, int]:
        lengths, is_columns = self._lines()
        line_size = max(max(lengths), 1)
        lines = len(lengths)

        if not is_columns:
            return line_size, lines
        return lines, line_size

    def boxes(self, weights: Weights = EVEN) -> list[tuple[str, Box]]:
        """Where each video goes, in order.

        Videos fill the grid a line at a time: a row in Rows First, a column
        in Columns First, the lines between the cells where the weights
        have them, a line's own where it has them (see own_lines). In Fit
        Shapes, each takes a tile of its shape, in the lines fit_to chose,
        stretched by up to crop.
        """
        if self.mode == FlowMode.SHAPES:
            fitted = self._fitted_shapes()
            if fitted is None:
                ids, shapes = self.ids, [DEFAULT_SHAPE] * len(self.ids)
            else:
                ids, shapes = fitted.ids, fitted.shapes
            boxes = justified_boxes(
                shapes, *self._lines(), *self._area, self._crop_share()
            )
            return list(zip(ids, boxes))

        return self._boxes(self.line_size(), weights)

    def own_lines(self) -> dict[int, int]:
        """The lines (rows in Rows First) whose lines between the videos
        are their own, by index, and how many places each has for them.

        With Link Rows off, every line, as many places as a full one has.
        Else only a last line left short that Fill Gaps spreads its videos
        over all of, a place for each.
        """

        if self.mode == FlowMode.SHAPES:
            return {}

        return self._own_lines(self.line_size())

    def _own_lines(self, line_size: int) -> dict[int, int]:
        full, rest = divmod(len(self.ids), line_size)

        own = {}
        if not self.is_linked:
            own = dict.fromkeys(range(full + bool(rest)), line_size)
        if rest and self.is_fit:
            own[full] = rest
        return own

    def linked(self, weights: Weights) -> Weights:
        """The lines as they are to be once Link Rows is turned on: the
        full lines' own made one, where they are on average. Those of a
        line Fill Gaps spreads stay its own."""

        if self.mode == FlowMode.SHAPES or not self.ids:
            return weights

        line_size = self.line_size()
        field = "rows" if self.mode == FlowMode.COLS else "cols"
        shared = getattr(weights, field)

        full, rest = divmod(len(self.ids), line_size)
        totals = [0.0] * line_size
        for line in range(full):
            edges = line_edges(line_size, weights.line_weights(line, line_size, shared))
            for place, (low, high) in enumerate(itertools.pairwise(edges)):
                totals[place] += high - low

        linked = weights._replace(lines=())
        if full:
            linked = linked._replace(**{field: tuple(total / full for total in totals)})
        if rest and self.is_fit:
            linked = linked.with_line(full, weights.line_weights(full, rest, ()))
        return linked

    def _boxes(self, line_size: int, weights: Weights = EVEN) -> list[tuple[str, Box]]:
        line_count = max(math.ceil(len(self.ids) / line_size), 1)

        if self.mode == FlowMode.COLS:
            along_weights, across_weights = weights.rows, weights.cols
        else:
            along_weights, across_weights = weights.cols, weights.rows

        along_edges = line_edges(line_size, along_weights)
        across_edges = line_edges(line_count, across_weights)

        own_edges = {
            line: line_edges(places, weights.line_weights(line, places, along_weights))
            for line, places in self._own_lines(line_size).items()
        }

        boxes = []
        for index, video_id in enumerate(self.ids):
            line, place = divmod(index, line_size)
            edges = own_edges.get(line, along_edges)

            along = (edges[place], edges[place + 1])
            across = (across_edges[line], across_edges[line + 1])
            if self.mode == FlowMode.COLS:
                box = Box(across[0], along[0], across[1], along[1])
            else:
                box = Box(along[0], across[0], along[1], across[1])
            boxes.append((video_id, box))
        return boxes

    def id_at(self, row: int, col: int) -> str | None:
        lengths, is_columns = self._lines()
        line, place = (col, row) if is_columns else (row, col)
        if not (0 <= line < len(lengths) and 0 <= place < lengths[line]):
            return None
        return self.order()[sum(lengths[:line]) + place]

    def position_of(self, video_id: str) -> tuple[int, int] | None:
        shown = self.order()
        if video_id not in shown:
            return None
        place = shown.index(video_id)
        lengths, is_columns = self._lines()
        line = 0
        while place >= lengths[line]:
            place -= lengths[line]
            line += 1
        return (place, line) if is_columns else (line, place)

    def order(self) -> list[str]:
        """The videos in the order they are laid out in: in Fit Shapes, the
        one fit_to chose, reordered or not."""

        if self.mode == FlowMode.SHAPES:
            fitted = self._fitted_shapes()
            if fitted is not None:
                return list(fitted.ids)
        return list(self.ids)

    def contains(self, video_id: str) -> bool:
        return video_id in self.ids

    def add(self, video_ids: list[str]) -> list[str]:
        for video_id in video_ids:
            if video_id in self.ids:
                self.ids.remove(video_id)
            self.ids.append(video_id)
        return []

    def remove(self, video_id: str) -> None:
        self.ids = [i for i in self.ids if i != video_id]

    def free_capacity(self) -> int | None:
        return None

    def shuffle(self) -> None:
        if len(self.ids) <= 1:
            return
        original = self.ids[:]
        random.shuffle(self.ids)
        if self.ids == original:
            random.shuffle(self.ids)

    def replace_id(self, old_id: str, new_id: str) -> None:
        self.ids = [new_id if i == old_id else i for i in self.ids]

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
        if src_id:
            return self._drop_internal(src_id, dst_id, zone, is_replace)

        if not video_ids:
            return []

        if dst_id is None or zone is None:
            return self.add(video_ids)

        if dst_id not in self.ids:
            return self.add(video_ids)

        if is_replace:
            self.replace_id(dst_id, video_ids[0])
            rest = video_ids[1:]
            if not rest:
                return []
            at = self.ids.index(video_ids[0]) + 1
            return self._insert_ids(rest, at)

        at = insert_index(self.ids.index(dst_id), zone)
        return self._insert_ids(video_ids, at)

    def _drop_internal(
        self,
        src_id: str,
        dst_id: str | None,
        zone: DropZone | None,
        is_replace: bool,
    ) -> list[str]:
        if dst_id is None or src_id not in self.ids:
            return []
        if src_id == dst_id:
            return []
        if dst_id not in self.ids:
            return []

        if is_replace:
            src_idx = self.ids.index(src_id)
            dst_idx = self.ids.index(dst_id)
            self.ids.pop(src_idx)
            if src_idx < dst_idx:
                dst_idx -= 1
            self.ids[dst_idx] = src_id
            return []

        if zone == DropZone.CENTER or zone is None:
            si, di = self.ids.index(src_id), self.ids.index(dst_id)
            self.ids[si], self.ids[di] = self.ids[di], self.ids[si]
            return []

        self.ids.remove(src_id)
        at = insert_index(self.ids.index(dst_id), zone)
        self.ids.insert(at, src_id)
        return []

    def _insert_ids(self, video_ids: list[str], at: int) -> list[str]:
        for video_id in video_ids:
            if video_id in self.ids:
                old = self.ids.index(video_id)
                self.ids.pop(old)
                if old < at:
                    at -= 1
        at = max(0, min(at, len(self.ids)))
        self.ids[at:at] = video_ids
        return []


def _line_weights(shapes, is_columns: bool) -> tuple[float, ...]:
    # a row is as long as its tiles' shapes add up to, a column as tall as
    # their heights for their widths do
    if is_columns:
        return tuple(1 / shape for shape in shapes)
    return tuple(shapes)
