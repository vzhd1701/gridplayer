from __future__ import annotations

import math
import random
from collections.abc import Mapping
from enum import Enum, auto

from gridplayer.utils.drop_zone import DropZone, insert_index
from gridplayer.utils.layout.boxes import Box, picture_score

# what a video is taken to be shaped like until its own shape is known
DEFAULT_SHAPE = 16 / 9

# how much bigger the pictures must be, on average, for Auto to leave the
# line size it has for one that shows them better: dragging the window's
# edge would flip it to and fro where the two show them about as well
SWITCH_GAIN = 1.08


class FlowMode(Enum):
    ROWS = auto()
    COLS = auto()


class FlowLayout:
    """Wrapping 1D order for Auto (Rows/Columns First). No holes."""

    def __init__(
        self,
        mode: FlowMode = FlowMode.ROWS,
        size: int = 0,
        is_fit: bool = False,
        ids: list[str] | None = None,
        is_match_shapes: bool = False,
    ):
        self.mode = mode
        self.size = size
        self.is_fit = is_fit
        # on Auto, fit_to chooses the line size, else it is the square grid's
        self.is_match_shapes = is_match_shapes
        self.ids: list[str] = list(ids) if ids else []

        # the line size fit_to chose, and for how many videos in which mode
        self._fitted: tuple[int, FlowMode, int] | None = None

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

    def displayed_size(self) -> tuple[int, int]:
        line_size = self.line_size()
        lines = max(math.ceil(len(self.ids) / line_size), 1)

        if self.mode != FlowMode.COLS:
            return line_size, lines
        return lines, line_size

    def boxes(self) -> list[tuple[str, Box]]:
        """Where each video goes, in order.

        Videos fill the grid a line at a time: a row in Rows First, a column
        in Columns First. With Fill Gaps, those of a last line left short
        share all of it.
        """
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
        cols, rows = self.displayed_size()
        if not (0 <= row < rows and 0 <= col < cols):
            return None
        if self.mode == FlowMode.COLS:
            idx = col * rows + row
        else:
            idx = row * cols + col
        if idx >= len(self.ids):
            return None
        return self.ids[idx]

    def position_of(self, video_id: str) -> tuple[int, int] | None:
        if video_id not in self.ids:
            return None
        idx = self.ids.index(video_id)
        cols, rows = self.displayed_size()
        if self.mode == FlowMode.COLS:
            col, row = divmod(idx, rows)
        else:
            row, col = divmod(idx, cols)
        return row, col

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
