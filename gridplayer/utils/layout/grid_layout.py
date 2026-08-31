from __future__ import annotations

import random
from enum import Enum, auto

from gridplayer.models.grid_state import GridCell
from gridplayer.utils.drop_zone import DropZone


class Direction(Enum):
    LEFT = auto()
    RIGHT = auto()
    UP = auto()
    DOWN = auto()


ZONE_TO_DIR = {
    DropZone.BEFORE: Direction.LEFT,
    DropZone.AFTER: Direction.RIGHT,
    DropZone.ABOVE: Direction.UP,
    DropZone.BELOW: Direction.DOWN,
}

_DELTA = {
    Direction.LEFT: (0, -1),
    Direction.RIGHT: (0, 1),
    Direction.UP: (-1, 0),
    Direction.DOWN: (1, 0),
}


class GridLayout:
    def __init__(
        self,
        max_rows: int = 1,
        max_cols: int = 1,
        preallocate: bool = False,
        cells: list[GridCell] | None = None,
    ):
        self.max_rows = max(1, max_rows)
        self.max_cols = max(1, max_cols)
        self.preallocate = preallocate
        self.cells = [cell.model_copy() for cell in cells] if cells else []

    def copy(self) -> GridLayout:
        return GridLayout(
            max_rows=self.max_rows,
            max_cols=self.max_cols,
            preallocate=self.preallocate,
            cells=self.cells,
        )

    def occupied_ids(self) -> list[str]:
        return [cell.video_id for cell in self.cells if cell.video_id]

    def displayed_size(self, preallocate: bool | None = None) -> tuple[int, int]:
        """Return (cols, rows) actually shown."""
        if preallocate is None:
            preallocate = self.preallocate
        if preallocate:
            return max(self.max_cols, 1), max(self.max_rows, 1)

        occupied = [c for c in self.cells if c.video_id]
        if not occupied:
            return 1, 1

        rows = max(c.row + c.rowspan for c in occupied)
        cols = max(c.col + c.colspan for c in occupied)
        return max(cols, 1), max(rows, 1)

    def compact_edges(self) -> None:
        """Shift occupied cells so empty rows/cols on the outside disappear.

        Interior holes are kept. No-op when preallocate is on.
        """
        if self.preallocate:
            return

        occupied = [c for c in self.cells if c.video_id]
        if not occupied:
            self.cells = []
            return

        min_row = min(c.row for c in occupied)
        min_col = min(c.col for c in occupied)
        if min_row == 0 and min_col == 0:
            return

        self.cells = [
            c.model_copy(update={"row": c.row - min_row, "col": c.col - min_col})
            for c in occupied
        ]

    def empty_positions(self, preallocate: bool | None = None) -> list[tuple[int, int]]:
        cols, rows = self.displayed_size(preallocate)
        occ = self._occupied_map()
        return [
            (row, col)
            for row in range(rows)
            for col in range(cols)
            if (row, col) not in occ
        ]

    def free_capacity(self) -> int | None:
        occupied = sum(
            cell.rowspan * cell.colspan for cell in self.cells if cell.video_id
        )
        return max(self.max_rows * self.max_cols - occupied, 0)

    def id_at(self, row: int, col: int) -> str | None:
        cell = self._occupied_map().get((row, col))
        return cell.video_id if cell else None

    def order(self) -> list[str]:
        occ = self._occupied_map()
        ids: list[str] = []
        seen: set[str] = set()
        for row, col in self._iter_fill_positions():
            cell = occ.get((row, col))
            if cell and cell.video_id and cell.video_id not in seen:
                ids.append(cell.video_id)
                seen.add(cell.video_id)
        return ids

    def position_of(self, video_id: str) -> tuple[int, int] | None:
        cell = self._find_cell(video_id)
        if cell is None:
            return None
        return cell.row, cell.col

    def contains(self, video_id: str) -> bool:
        return self._find_cell(video_id) is not None

    def add(self, video_ids: list[str]) -> list[str]:
        return self.place_in_empties(video_ids)

    def remove(self, video_id: str) -> None:
        self.remove_video(video_id)

    def shuffle(self) -> None:
        occupied_ids = self.occupied_ids()
        if len(occupied_ids) <= 1:
            return
        shuffled = occupied_ids[:]
        random.shuffle(shuffled)
        if shuffled == occupied_ids:
            random.shuffle(shuffled)
        self.shuffle_occupied(shuffled)

    def replace_id(self, old_id: str, new_id: str) -> None:
        cell = self._find_cell(old_id)
        if cell is None:
            return
        self.cells = [
            c.model_copy(update={"video_id": new_id}) if c.video_id == old_id else c
            for c in self.cells
        ]

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
        row, col = self._resolve_pos(row, col, dst_id)

        if src_id:
            return self._drop_internal(src_id, row, col, zone, is_replace)

        if row is None or col is None or zone is None:
            return self.place_in_empties(video_ids)

        if zone == DropZone.CENTER:
            return self.drop_on_center(row, col, video_ids, is_replace=is_replace)

        direction = ZONE_TO_DIR.get(zone)
        if direction is None:
            return self.place_in_empties(video_ids)

        leftover, rejected = self.drop_on_edge(row, col, direction, video_ids)
        if not rejected:
            return leftover
        return self.place_in_empties(video_ids)

    def _drop_internal(
        self,
        src_id: str,
        row: int | None,
        col: int | None,
        zone: DropZone | None,
        is_replace: bool,
    ) -> list[str]:
        if row is None or col is None:
            return []

        if is_replace:
            dst_id = self.id_at(row, col)
            if not dst_id or dst_id == src_id:
                return []
            self.remove_video(src_id)
            self.occupy(row, col, src_id)
            self.compact_edges()
            return []

        if zone == DropZone.CENTER:
            self.drop_on_center(row, col, [src_id], is_internal=True)
            return []

        direction = ZONE_TO_DIR.get(zone)
        if direction is None:
            return [src_id]

        snapshot = [cell.model_copy() for cell in self.cells]
        self.remove_video(src_id)
        _leftover, rejected = self.drop_on_edge(row, col, direction, [src_id])
        if rejected:
            self.cells = snapshot
            return [src_id]
        return []

    def _resolve_pos(
        self,
        row: int | None,
        col: int | None,
        dst_id: str | None,
    ) -> tuple[int | None, int | None]:
        if row is not None and col is not None:
            return row, col
        if dst_id:
            pos = self.position_of(dst_id)
            if pos is not None:
                return pos
        return row, col

    def resize(
        self,
        max_rows: int,
        max_cols: int,
        preallocate: bool | None = None,
    ) -> list[str]:
        """Keep cells that still fit. Relocate clipped ones into remaining empties.

        Returns ids that do not fit in the new grid.
        """
        self.max_rows = max(1, max_rows)
        self.max_cols = max(1, max_cols)
        if preallocate is not None:
            self.preallocate = preallocate

        kept: list[GridCell] = []
        cut: list[GridCell] = []
        for cell in self.cells:
            if not cell.video_id:
                continue
            fits = (
                cell.row >= 0
                and cell.col >= 0
                and cell.row + cell.rowspan <= self.max_rows
                and cell.col + cell.colspan <= self.max_cols
            )
            if fits:
                kept.append(cell)
            else:
                cut.append(cell)

        cut.sort(key=lambda c: (c.row, c.col))

        self.cells = kept
        return self.place_in_empties([cell.video_id for cell in cut], compact=False)

    def pack_flow(self, video_ids: list[str]) -> None:
        coords = (
            (row, col) for row in range(self.max_rows) for col in range(self.max_cols)
        )

        self.cells = [
            GridCell(video_id=video_id, row=row, col=col)
            for (row, col), video_id in zip(coords, video_ids)
        ]

    def remove_video(self, video_id: str) -> None:
        self.cells = [cell for cell in self.cells if cell.video_id != video_id]

    def occupy(self, row: int, col: int, video_id: str) -> None:
        self.remove_video(video_id)
        occ = self._occupied_map()
        if (row, col) in occ:
            old = occ[row, col]
            self.cells = [c for c in self.cells if c is not old]
        self.cells.append(GridCell(video_id=video_id, row=row, col=col))

    def place_in_empties(
        self,
        video_ids: list[str],
        *,
        compact: bool = True,
        along: Direction | None = None,
    ) -> list[str]:
        """Fill displayed holes first, then grow within max. Returns leftover ids."""
        if not video_ids:
            return []

        for video_id in video_ids:
            self.remove_video(video_id)

        occ = self._occupied_map()
        leftover = list(video_ids)

        for row, col in self._iter_place_positions(occ, along=along):
            if not leftover:
                break
            if (row, col) in occ:
                continue
            video_id = leftover.pop(0)
            cell = GridCell(video_id=video_id, row=row, col=col)
            self.cells.append(cell)
            occ[row, col] = cell

        if compact:
            self.compact_edges()
        return leftover

    def shuffle_occupied(self, order: list[str]) -> None:
        occupied = [c for c in self.cells if c.video_id]
        if len(order) != len(occupied):
            raise ValueError("Shuffle order must match occupied cell count")

        it = iter(order)
        self.cells = [
            cell.model_copy(update={"video_id": next(it)}) if cell.video_id else cell
            for cell in self.cells
        ]

    def swap_videos(self, id_a: str, id_b: str) -> None:
        if id_a == id_b:
            return
        if self._find_cell(id_a) is None or self._find_cell(id_b) is None:
            return

        swapped = []
        for cell in self.cells:
            if cell.video_id == id_a:
                swapped.append(cell.model_copy(update={"video_id": id_b}))
            elif cell.video_id == id_b:
                swapped.append(cell.model_copy(update={"video_id": id_a}))
            else:
                swapped.append(cell)
        self.cells = swapped

    def drop_on_center(
        self,
        row: int,
        col: int,
        video_ids: list[str],
        *,
        is_replace: bool = False,
        is_internal: bool = False,
    ) -> list[str]:
        if not video_ids:
            return []

        existing = self._occupied_map().get((row, col))

        if is_internal and existing and existing.video_id and not is_replace:
            if existing.video_id == video_ids[0]:
                return video_ids[1:]
            self.swap_videos(existing.video_id, video_ids[0])
            self.compact_edges()
            return video_ids[1:]

        if existing is None:
            leftover, rejected = self.drop_on_edge(row, col, Direction.RIGHT, video_ids)
            if rejected:
                leftover = self.place_in_empties(video_ids)
            return leftover

        if is_replace and existing:
            self.occupy(row, col, video_ids[0])
            leftover = self.place_in_empties(video_ids[1:])
            self.compact_edges()
            return leftover

        leftover, rejected = self.drop_on_edge(row, col, Direction.LEFT, video_ids)
        if rejected:
            leftover = self.place_in_empties(video_ids)
        self.compact_edges()
        return leftover

    def drop_on_edge(
        self,
        row: int,
        col: int,
        direction: Direction,
        video_ids: list[str],
    ) -> tuple[list[str], bool]:
        if not video_ids:
            return [], False

        snapshot = [cell.model_copy() for cell in self.cells]
        ok, last_pos = self._drop_one_edge(row, col, direction, video_ids[0])
        if not ok or last_pos is None:
            self.cells = snapshot
            return video_ids, True

        remaining = video_ids[1:]
        d_row, d_col = _DELTA[direction]
        cur_r, cur_c = last_pos

        still: list[str] = []
        chain = True
        for video_id in remaining:
            if not chain:
                still.append(video_id)
                continue
            next_r, next_c = cur_r + d_row, cur_c + d_col
            occ = self._occupied_map()
            if self._in_max(next_r, next_c) and (next_r, next_c) not in occ:
                self.occupy(next_r, next_c, video_id)
                cur_r, cur_c = next_r, next_c
            else:
                still.append(video_id)
                chain = False

        leftover = self.place_in_empties(still, along=direction)
        self.compact_edges()
        return leftover, False

    def _occupied_map(self) -> dict[tuple[int, int], GridCell]:
        mapping: dict[tuple[int, int], GridCell] = {}
        for cell in self.cells:
            if not cell.video_id:
                continue
            for row in range(cell.row, cell.row + cell.rowspan):
                for col in range(cell.col, cell.col + cell.colspan):
                    mapping[row, col] = cell
        return mapping

    def _find_cell(self, video_id: str) -> GridCell | None:
        return next((c for c in self.cells if c.video_id == video_id), None)

    def _iter_fill_positions(self, rows_first: bool = True):
        if rows_first:
            for row in range(self.max_rows):
                for col in range(self.max_cols):
                    yield row, col
        else:
            for col in range(self.max_cols):
                for row in range(self.max_rows):
                    yield row, col

    def _rows_first_for(self, along: Direction | None) -> bool:
        if along in {Direction.LEFT, Direction.RIGHT}:
            return True
        if along in {Direction.UP, Direction.DOWN}:
            return False
        return True

    def _iter_place_positions(
        self,
        occ: dict[tuple[int, int], GridCell],
        along: Direction | None = None,
    ):
        """Interior holes of the current canvas, then unused max-grid cells."""
        rows_first = self._rows_first_for(along)
        disp_cols, disp_rows = self.displayed_size()
        for row, col in self._iter_fill_positions(rows_first):
            if row < disp_rows and col < disp_cols and (row, col) not in occ:
                yield row, col
        if self.preallocate:
            return
        for row, col in self._iter_fill_positions(rows_first):
            if (row >= disp_rows or col >= disp_cols) and (row, col) not in occ:
                yield row, col

    def _in_max(self, row: int, col: int) -> bool:
        return 0 <= row < self.max_rows and 0 <= col < self.max_cols

    def _in_displayed(self, row: int, col: int) -> bool:
        cols, rows = self.displayed_size()
        return 0 <= row < rows and 0 <= col < cols

    def _insert_grid_row(self, at_row: int) -> None:
        self.cells = [
            cell.model_copy(update={"row": cell.row + 1})
            if cell.row >= at_row
            else cell
            for cell in self.cells
        ]

    def _insert_grid_col(self, at_col: int) -> None:
        self.cells = [
            cell.model_copy(update={"col": cell.col + 1})
            if cell.col >= at_col
            else cell
            for cell in self.cells
        ]

    def _can_insert_row(self) -> bool:
        if not self.cells:
            return self.max_rows > 0
        return max(c.row + c.rowspan for c in self.cells) < self.max_rows

    def _can_insert_col(self) -> bool:
        if not self.cells:
            return self.max_cols > 0
        return max(c.col + c.colspan for c in self.cells) < self.max_cols

    def _shift_line(self, row: int, col: int, d_row: int, d_col: int) -> bool:
        """Make (row, col) empty by pushing 1x1 cells along the row or column.

        Stops at the first hole, or grows into unused max-grid cells. Other
        rows/cols are left alone.
        """
        occ = self._occupied_map()
        if (row, col) not in occ:
            return True

        hole_r, hole_c = row, col
        while self._in_max(hole_r, hole_c) and (hole_r, hole_c) in occ:
            hole_r += d_row
            hole_c += d_col
        if not self._in_max(hole_r, hole_c):
            return False

        steps: list[tuple[int, int]] = []
        cur_r, cur_c = row, col
        while (cur_r, cur_c) != (hole_r, hole_c):
            steps.append((cur_r, cur_c))
            cur_r += d_row
            cur_c += d_col

        for cur_r, cur_c in steps:
            cell = occ[cur_r, cur_c]
            if (
                cell.row != cur_r
                or cell.col != cur_c
                or cell.rowspan != 1
                or cell.colspan != 1
            ):
                return False

        for cur_r, cur_c in reversed(steps):
            cell = occ[cur_r, cur_c]
            moved = cell.model_copy(update={"row": cur_r + d_row, "col": cur_c + d_col})
            self.cells = [
                moved if x.video_id == cell.video_id else x for x in self.cells
            ]
            occ.pop((cur_r, cur_c))
            occ[cur_r + d_row, cur_c + d_col] = moved
        return True

    def _drop_one_edge(
        self, row: int, col: int, direction: Direction, video_id: str
    ) -> tuple[bool, tuple[int, int] | None]:
        # Drop may run after add_video_blocks parked this id in an empty slot.
        self.remove_video(video_id)
        occ = self._occupied_map()

        # Dropping on an empty cell fills it, regardless of edge zone.
        if self._in_max(row, col) and (row, col) not in occ:
            self.occupy(row, col, video_id)
            return True, (row, col)

        d_row, d_col = _DELTA[direction]
        n_r, n_c = row + d_row, col + d_col
        # Fill a hole in the current canvas. Cells past the displayed edge
        # are handled by grow / push so a new column/row stays aligned.
        if self._in_displayed(n_r, n_c) and (n_r, n_c) not in occ:
            self.occupy(n_r, n_c, video_id)
            return True, (n_r, n_c)

        if direction in {Direction.LEFT, Direction.RIGHT}:
            dest_r = row
            dest_c = col if direction == Direction.LEFT else col + 1
            if self._can_insert_col() and self._in_max(dest_r, dest_c):
                self._insert_grid_col(dest_c)
                self.occupy(dest_r, dest_c, video_id)
                return True, (dest_r, dest_c)
            push = (0, 1)
        else:
            dest_r = row if direction == Direction.UP else row + 1
            dest_c = col
            if self._can_insert_row() and self._in_max(dest_r, dest_c):
                self._insert_grid_row(dest_r)
                self.occupy(dest_r, dest_c, video_id)
                return True, (dest_r, dest_c)
            push = (1, 0)

        if not self._in_max(dest_r, dest_c):
            return False, None
        if not self._shift_line(dest_r, dest_c, *push):
            return False, None
        self.occupy(dest_r, dest_c, video_id)
        return True, (dest_r, dest_c)
