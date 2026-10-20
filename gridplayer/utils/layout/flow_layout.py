from __future__ import annotations

import math
import random
from collections.abc import Mapping
from enum import Enum, auto
from typing import NamedTuple

from gridplayer.utils.drop_zone import DropZone, insert_index
from gridplayer.utils.layout.boxes import Box, picture_score
from gridplayer.utils.layout.justified import (
    Split,
    best_splits,
    justified_boxes,
    measure_split,
    split_score,
)

# what a video is taken to be shaped like until its own shape is known
DEFAULT_SHAPE = 16 / 9

# how much bigger the pictures must be, on average, for Auto to leave the
# line size it has for one that shows them better: dragging the window's
# edge would flip it to and fro where the two show them about as well
SWITCH_GAIN = 1.08


class FlowMode(Enum):
    ROWS = auto()
    COLS = auto()
    # each video in a tile of its own shape (see justified_boxes)
    SHAPES = auto()


class Lines(NamedTuple):
    """How many videos each line takes, and whether the lines are columns."""

    lengths: tuple[int, ...]
    is_columns: bool


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
    ):
        self.mode = mode
        self.size = size
        self.is_fit = is_fit
        # on Auto, fit_to chooses the line size, else it is the square grid's
        self.is_match_shapes = is_match_shapes
        self.ids: list[str] = list(ids) if ids else []
        # in Fit Shapes, the percent of a picture its tile may leave out
        self.crop = crop

        # the line size fit_to chose, and for how many videos in which mode
        self._fitted: tuple[int, FlowMode, int] | None = None

        # in Fit Shapes, the lines fit_to chose and for which videos, with
        # the shapes and the area's size it was given
        self._fitted_lines: tuple[tuple[str, ...], Lines] | None = None
        self._shapes: list[float] = []
        self._area = (16, 9)

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

    def _fit_lines(self, width: int, height: int, shapes: Mapping[str, float]):
        """Fit Shapes: choose the rows or columns that show the videos best
        (see best_splits). The lines there are now are kept unless others
        show the pictures SWITCH_GAIN times bigger.
        """

        if width <= 0 or height <= 0:
            return

        self._shapes = [shapes.get(video_id) or DEFAULT_SHAPE for video_id in self.ids]
        self._area = (width, height)

        count = len(self.ids)
        if count == 0:
            return

        # a row is as long as its tiles' shapes add up to, a column as tall
        # as their heights for their widths do
        weights = {
            False: tuple(self._shapes),
            True: tuple(1 / shape for shape in self._shapes),
        }

        def score(split: Split, is_columns: bool) -> float:
            area = (height, width) if is_columns else (width, height)
            return split_score(split, weights[is_columns], *area, self._crop_share())

        best, best_score = None, -math.inf
        for is_columns in (False, True):
            for split in best_splits(weights[is_columns]):
                candidate_score = score(split, is_columns)
                if candidate_score > best_score:
                    best = Lines(split.lengths, is_columns)
                    best_score = candidate_score

        ids = tuple(self.ids)
        if self._fitted_lines is not None and self._fitted_lines[0] == ids:
            kept = self._fitted_lines[1]
            kept_split = measure_split(weights[kept.is_columns], kept.lengths)
            kept_score = score(kept_split, kept.is_columns)
            if best_score <= kept_score + count * math.log(SWITCH_GAIN):
                best = kept

        self._fitted_lines = (ids, best)

    def _crop_share(self) -> float:
        return min(max(self.crop, 0), 50) / 100

    def _lines(self) -> Lines:
        """How the videos are laid out in lines now."""

        count = len(self.ids)

        if self.mode == FlowMode.SHAPES:
            fitted = self._fitted_lines
            if fitted is not None and fitted[0] == tuple(self.ids):
                return fitted[1]
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

    def boxes(self) -> list[tuple[str, Box]]:
        """Where each video goes, in order.

        Videos fill the grid a line at a time: a row in Rows First, a column
        in Columns First. With Fill Gaps, those of a last line left short
        share all of it. In Fit Shapes, each takes a tile of its shape, in
        the lines fit_to chose, stretched by up to crop.
        """
        if self.mode == FlowMode.SHAPES:
            shapes = self._shapes
            if len(shapes) != len(self.ids):
                shapes = [DEFAULT_SHAPE] * len(self.ids)
            boxes = justified_boxes(
                shapes, *self._lines(), *self._area, self._crop_share()
            )
            return list(zip(self.ids, boxes))

        return self._boxes(self.line_size())

    def _boxes(self, line_size: int) -> list[tuple[str, Box]]:
        line_count = max(math.ceil(len(self.ids) / line_size), 1)
        last_line = len(self.ids) - line_size * (line_count - 1)

        boxes = []
        for index, video_id in enumerate(self.ids):
            line, place = divmod(index, line_size)
            places = last_line if self.is_fit and line == line_count - 1 else line_size

            along = (place / places, (place + 1) / places)
            across = (line / line_count, (line + 1) / line_count)
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
        return self.ids[sum(lengths[:line]) + place]

    def position_of(self, video_id: str) -> tuple[int, int] | None:
        if video_id not in self.ids:
            return None
        place = self.ids.index(video_id)
        lengths, is_columns = self._lines()
        line = 0
        while place >= lengths[line]:
            place -= lengths[line]
            line += 1
        return (place, line) if is_columns else (line, place)

    def order(self) -> list[str]:
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
