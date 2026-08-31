from __future__ import annotations

import math
import random
from enum import Enum, auto

from gridplayer.utils.drop_zone import DropZone, insert_index


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
    ):
        self.mode = mode
        self.size = size
        self.is_fit = is_fit
        self.ids: list[str] = list(ids) if ids else []

    def displayed_size(self) -> tuple[int, int]:
        count = len(self.ids)
        if count <= 1:
            return 1, 1

        grid_size = self.size
        if grid_size == 0:
            grid_size = math.ceil(math.sqrt(count))

        grid_slices = math.ceil(count / grid_size)
        if self.mode != FlowMode.COLS:
            return grid_size, grid_slices
        return grid_slices, grid_size

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
