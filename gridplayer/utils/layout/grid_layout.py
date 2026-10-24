from __future__ import annotations

import random
from enum import Enum, auto
from typing import NamedTuple

from gridplayer.models.grid_state import GridCell
from gridplayer.params.static import GridTemplate
from gridplayer.utils.drop_zone import DropZone
from gridplayer.utils.layout.boxes import EVEN, Box, Weights, grid_box


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


def _area(row: int, col: int, rowspan: int, colspan: int) -> set[tuple[int, int]]:
    # the places a cell there of that span covers
    return {
        (r, c) for r in range(row, row + rowspan) for c in range(col, col + colspan)
    }


def _covered(cell: GridCell) -> set[tuple[int, int]]:
    return _area(cell.row, cell.col, cell.rowspan, cell.colspan)


class _BigDrop(NamedTuple):
    big: GridCell
    # the video it is dropped beside, and on which side of it
    beside: str
    direction: Direction
    # its corner in the free cells on that side, and pushed in next to it
    hole: tuple[int, int]
    spot: tuple[int, int]


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

        # its cells being resized by hand (see GridEditManager): all of
        # them shown, as with preallocate, and the empty ones kept
        self.is_editing = False

    @property
    def shows_every_cell(self) -> bool:
        """Whether all of its cells are shown, the empty ones too."""

        return self.preallocate or self.is_editing

    def copy(self) -> GridLayout:
        grid = GridLayout(
            max_rows=self.max_rows,
            max_cols=self.max_cols,
            preallocate=self.preallocate,
            cells=self.cells,
        )
        grid.is_editing = self.is_editing
        return grid

    def occupied_ids(self) -> list[str]:
        return [cell.video_id for cell in self.cells if cell.video_id]

    def displayed_size(self, preallocate: bool | None = None) -> tuple[int, int]:
        """Return (cols, rows) actually shown."""
        if preallocate is None:
            preallocate = self.shows_every_cell
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

        Interior holes are kept. No-op when preallocate is on, or while
        the cells are edited.
        """
        if self.shows_every_cell:
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

    def boxes(self, weights: Weights = EVEN) -> list[tuple[GridCell, Box]]:
        """Where each video's cell goes, over all the cells it spans, the
        lines between them where the weights have them."""
        cols, rows = self.displayed_size()
        return [
            (
                cell,
                grid_box(
                    cell.row,
                    cell.col,
                    rows,
                    cols,
                    cell.rowspan,
                    cell.colspan,
                    weights,
                ),
            )
            for cell in self.cells
            if cell.video_id
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

    def span_of(self, video_id: str) -> tuple[int, int] | None:
        """How many rows and columns a video's cell covers."""

        cell = self._find_cell(video_id)
        if cell is None:
            return None
        return cell.rowspan, cell.colspan

    def set_span(self, video_id: str, rowspan: int, colspan: int) -> bool:
        """Make a video's cell cover rowspan x colspan cells, over where it
        is: where it covers the fewest other videos, then as near its top
        left corner as it can. Those it covers go to the free cells nearest
        them; the others stay where they are, and what it frees stays free.

        Where the videos it covers have nowhere to go, those after it, row
        by row, move along to make room, in their order. False, and nothing
        changed, where there is no room for them that way either."""

        cell = self._find_cell(video_id)
        if cell is None or not (
            1 <= rowspan <= self.max_rows and 1 <= colspan <= self.max_cols
        ):
            return False

        big = cell.model_copy(
            update={
                "row": min(cell.row, self.max_rows - rowspan),
                "col": min(cell.col, self.max_cols - colspan),
                "rowspan": rowspan,
                "colspan": colspan,
            }
        )

        spots = sorted(
            self._spots_over(cell, big),
            key=lambda spot: self._in_the_way(video_id, _area(*spot, rowspan, colspan)),
        )
        if any(self.place(video_id, row, col, rowspan, colspan) for row, col in spots):
            return True

        placed = self._flowed_after(big)
        if placed is None:
            return False
        self.cells = sorted(placed, key=self._index)
        self.compact_edges()
        return True

    def _in_the_way(self, video_id: str, area: set[tuple[int, int]]) -> int:
        # how many other videos a video's cell covers, over the area
        return sum(
            1
            for c in self.cells
            if c.video_id and c.video_id != video_id and _covered(c) & area
        )

    def _flowed_after(self, big: GridCell) -> list[GridCell] | None:
        """The cells with big in, the videos from its place on moved along
        in their order; None where they do not all fit."""

        start = self._index(big)
        moving = [
            c
            for c in self._others(big)
            if self._index(c) >= start or _covered(c) & _covered(big)
        ]
        return self._resettled(
            big, moving, lambda occupied, other: self._first_fit(occupied, other, start)
        )

    def _others(self, big: GridCell) -> list[GridCell]:
        return [c for c in self.cells if c.video_id and c.video_id != big.video_id]

    def _resettled(self, big: GridCell, moving: list[GridCell], find_spot):
        """The cells with big in, those moving each put, in their order,
        where find_spot(occupied, cell) finds; None where it finds none."""

        placed = [c for c in self._others(big) if c not in moving]
        placed.append(big)

        occupied = set().union(*(_covered(c) for c in placed))
        for other in sorted(moving, key=self._index):
            spot = find_spot(occupied, other)
            if spot is None:
                return None
            moved = other.model_copy(update={"row": spot[0], "col": spot[1]})
            placed.append(moved)
            occupied |= _covered(moved)
        return placed

    def _spots_over(self, cell: GridCell, big: GridCell) -> list[tuple[int, int]]:
        """Where big's corner can go with it over some of the cell, in the
        grid: nearest where it would be first."""

        spots = [
            (row, col)
            for row in range(self.max_rows - big.rowspan + 1)
            for col in range(self.max_cols - big.colspan + 1)
            if _area(row, col, big.rowspan, big.colspan) & _covered(cell)
        ]
        return sorted(
            spots, key=lambda spot: abs(spot[0] - big.row) + abs(spot[1] - big.col)
        )

    def place(
        self, video_id: str, row: int, col: int, rowspan: int, colspan: int
    ) -> bool:
        """Put a video's cell at (row, col), rowspan x colspan cells: moved,
        resized, or both. The videos it then covers go to the free places
        nearest where they were, those it left first, so that one moved
        onto another of its size swaps with it. False, and nothing changed,
        where they do not all fit."""

        cell = self._find_cell(video_id)
        if cell is None or not self._fits(row, col, rowspan, colspan):
            return False

        big = cell.model_copy(
            update={"row": row, "col": col, "rowspan": rowspan, "colspan": colspan}
        )
        left = _covered(cell) - _covered(big)

        displaced = [c for c in self._others(big) if _covered(c) & _covered(big)]
        placed = self._resettled(
            big,
            displaced,
            lambda occupied, other: self._nearest_fit(occupied, other, left),
        )
        if placed is None:
            return False

        self.cells = sorted(placed, key=self._index)
        self.compact_edges()
        return True

    def can_place(
        self, video_id: str, row: int, col: int, rowspan: int, colspan: int
    ) -> bool:
        return self.copy().place(video_id, row, col, rowspan, colspan)

    def stepped(self, video_id: str, rows: int, cols: int) -> tuple[int, int] | None:
        """The span a video's cell has with rows and columns more (fewer,
        if less than nought), from one to as many as the grid has. None
        where that is the span it has."""

        span = self.span_of(video_id)
        if span is None:
            return None
        stepped = (
            min(max(span[0] + rows, 1), self.max_rows),
            min(max(span[1] + cols, 1), self.max_cols),
        )
        return None if stepped == span else stepped

    def steps(self, video_id: str, rows: int, cols: int) -> list[tuple[int, int]]:
        """The spans to try for a video's cell made a step bigger or smaller
        (see stepped), the first there is room for. A step in both ways
        tries one way only after, the way it has fewer cells first, to keep
        it near square: a cell made bigger grows as far as there is room."""

        first = self.stepped(video_id, rows, cols)
        if first is None:
            return []

        spans = [first]
        if rows and cols:
            rowspan, colspan = self.span_of(video_id)
            by_rows = self.stepped(video_id, rows, 0)
            by_cols = self.stepped(video_id, 0, cols)
            ways = (by_cols, by_rows) if colspan <= rowspan else (by_rows, by_cols)
            spans.extend(s for s in ways if s is not None and s not in spans)
        return spans

    def step_span(self, video_id: str, rows: int, cols: int) -> tuple[int, int] | None:
        """The first of the spans for the step (see steps) there is room for;
        None where there is room for none."""

        rowspan, colspan = self.span_of(video_id) or (1, 1)
        free = self.free_capacity()
        return next(
            (
                span
                for span in self.steps(video_id, rows, cols)
                if span[0] * span[1] - rowspan * colspan <= free
                and self.copy().set_span(video_id, *span)
            ),
            None,
        )

    def apply_template(self, template: GridTemplate, video_ids: list[str]) -> None:
        """The grid made the template, the videos put in its cells in their
        order, as many as it has cells for."""

        self.max_rows = template.rows
        self.max_cols = template.cols

        places = template.places()
        self.cells = [
            GridCell(video_id=video_id, row=row, col=col, rowspan=rs, colspan=cs)
            for video_id, (row, col, rs, cs) in zip(video_ids, places)
        ]
        self.cells.sort(key=self._index)
        self.compact_edges()

    def big_cells(self) -> list[GridCell]:
        """The videos' cells that cover more than one."""

        return [
            c for c in self.cells if c.video_id and (c.rowspan, c.colspan) != (1, 1)
        ]

    def is_template(self, template: GridTemplate) -> bool:
        """Whether the grid is the template: its size, and its big cells
        where the template has them."""

        big = {(c.row, c.col, c.rowspan, c.colspan) for c in self.big_cells()}
        return (self.max_cols, self.max_rows) == (
            template.cols,
            template.rows,
        ) and big == set(template.big)

    def _index(self, cell: GridCell) -> int:
        # where the cell's top left corner comes, going row by row
        return cell.row * self.max_cols + cell.col

    def _nearest_fit(
        self, occupied: set, cell: GridCell, preferred: set
    ) -> tuple[int, int] | None:
        """The free place for a cell of its span, all of it in preferred
        if there is one, else nearest where it is: of those as near, one
        further on, row by row, so that its order stays."""

        spots = []
        for row in range(self.max_rows - cell.rowspan + 1):
            for col in range(self.max_cols - cell.colspan + 1):
                spot = _area(row, col, cell.rowspan, cell.colspan)
                if spot & occupied:
                    continue
                distance = abs(row - cell.row) + abs(col - cell.col)
                is_before = (row, col) < (cell.row, cell.col)
                spots.append((not spot <= preferred, distance, is_before, row, col))

        if not spots:
            return None
        *_, row, col = min(spots)
        return row, col

    def _first_fit(
        self, occupied: set, cell: GridCell, start: int
    ) -> tuple[int, int] | None:
        """The first place from start on, row by row, a cell of its span
        fits in, none of it occupied."""

        span = cell.rowspan, cell.colspan
        for index in range(start, self.max_rows * self.max_cols):
            row, col = divmod(index, self.max_cols)
            if self._fits(row, col, *span) and not _area(row, col, *span) & occupied:
                return row, col
        return None

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
            if not self._trade_places(src_id, row, col):
                self.drop_on_center(row, col, [src_id], is_internal=True)
            return []

        direction = ZONE_TO_DIR.get(zone)
        if direction is None:
            return [src_id]

        snapshot = [cell.model_copy() for cell in self.cells]
        if self.span_of(src_id) != (1, 1):
            is_dropped = self._drop_big_beside(src_id, row, col, direction)
        else:
            self.remove_video(src_id)
            _leftover, rejected = self.drop_on_edge(row, col, direction, [src_id])
            is_dropped = not rejected
        if not is_dropped:
            self.cells = snapshot
            return [src_id]
        return []

    def _trade_places(self, video_id: str, row: int, col: int) -> bool:
        """A video dropped on the one at (row, col), their cells of other
        sizes: the bigger moves to the other's place, as near its corner as
        the grid lets it, keeping its size, and the videos it then covers
        go to where it was. False, and nothing changed, for cells of a size,
        which swap their videos, or where they cannot."""

        cell = self._find_cell(video_id)
        other = self._occupied_map().get((row, col))
        if cell is None or other is None or other.video_id == video_id:
            return False
        if (cell.rowspan, cell.colspan) == (other.rowspan, other.colspan):
            return False

        mover, there = (
            (cell, other) if cell.rowspan * cell.colspan > 1 else (other, cell)
        )
        return self.place(
            mover.video_id,
            min(there.row, self.max_rows - mover.rowspan),
            min(there.col, self.max_cols - mover.colspan),
            mover.rowspan,
            mover.colspan,
        )

    def _drop_big_beside(
        self, video_id: str, row: int, col: int, direction: Direction
    ) -> bool:
        """A big cell dropped on a side of the cell at (row, col), keeping
        its size. Into the free cells on that side, if they are; else next
        to it, the cells in its way pushed along (that cell itself, where
        it goes before it); else back from the grid's edge, the videos it
        then covers going to the free cells nearest them, should that cell
        still be on that side. Across, it lines up with that cell. False,
        and nothing changed, where none of them can be."""

        big = self._find_cell(video_id)
        rowspan, colspan = big.rowspan, big.colspan

        beside = self._occupied_map().get((row, col))
        if beside is None or beside is big:
            spot_row = min(row, self.max_rows - rowspan)
            spot_col = min(col, self.max_cols - colspan)
            return self.place(video_id, spot_row, spot_col, rowspan, colspan)

        top, left = beside.row, beside.col
        bottom, right = top + beside.rowspan, left + beside.colspan
        across_row = min(top, self.max_rows - rowspan)
        across_col = min(left, self.max_cols - colspan)
        hole, spot = {
            Direction.UP: ((top - rowspan, across_col), (top, across_col)),
            Direction.DOWN: ((bottom, across_col), (bottom, across_col)),
            Direction.LEFT: ((across_row, left - colspan), (across_row, left)),
            Direction.RIGHT: ((across_row, right), (across_row, right)),
        }[direction]
        drop = _BigDrop(big, beside.video_id, direction, hole, spot)

        for way in ("_into_hole", "_pushing_in", "_nearest_beside"):
            grid = self.copy()
            grid.remove_video(video_id)
            if getattr(grid, way)(drop):
                self.cells = grid.cells
                return True
        return False

    def _into_hole(self, drop: _BigDrop) -> bool:
        if not self._is_free(*drop.hole, drop.big.rowspan, drop.big.colspan):
            return False
        self._put(drop.big, *drop.hole)
        return True

    def _pushing_in(self, drop: _BigDrop) -> bool:
        row, col = drop.spot
        big = drop.big.model_copy(update={"row": row, "col": col})
        if not self._fits(row, col, big.rowspan, big.colspan):
            return False

        push = _DELTA[
            Direction.DOWN
            if drop.direction in {Direction.UP, Direction.DOWN}
            else Direction.RIGHT
        ]
        while taken := sorted(_covered(big) & self._occupied_map().keys()):
            if not self._shift_line(*taken[-1], *push):
                return False
        self._put(drop.big, row, col)
        return True

    def _nearest_beside(self, drop: _BigDrop) -> bool:
        rowspan, colspan = drop.big.rowspan, drop.big.colspan
        row = min(max(drop.hole[0], 0), self.max_rows - rowspan)
        col = min(max(drop.hole[1], 0), self.max_cols - colspan)
        self.cells.append(drop.big)
        if not self.place(drop.big.video_id, row, col, rowspan, colspan):
            return False

        big, beside = self._find_cell(drop.big.video_id), self._find_cell(drop.beside)
        return {
            Direction.UP: beside.row >= big.row + big.rowspan,
            Direction.DOWN: beside.row + beside.rowspan <= big.row,
            Direction.LEFT: beside.col >= big.col + big.colspan,
            Direction.RIGHT: beside.col + beside.colspan <= big.col,
        }[drop.direction]

    def _is_free(self, row: int, col: int, rowspan: int, colspan: int) -> bool:
        return self._fits(row, col, rowspan, colspan) and not (
            _area(row, col, rowspan, colspan) & self._occupied_map().keys()
        )

    def _fits(self, row: int, col: int, rowspan: int, colspan: int) -> bool:
        # a cell there of that span, all of it in the grid
        return (
            0 <= row
            and 0 <= col
            and 1 <= rowspan <= self.max_rows - row
            and 1 <= colspan <= self.max_cols - col
        )

    def _put(self, cell: GridCell, row: int, col: int) -> None:
        self.cells.append(cell.model_copy(update={"row": row, "col": col}))
        self.cells.sort(key=self._index)
        self.compact_edges()

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
            if 0 <= cell.row < self.max_rows and 0 <= cell.col < self.max_cols:
                # a big cell made to fit, as far as it does not
                kept.append(
                    cell.model_copy(
                        update={
                            "rowspan": min(cell.rowspan, self.max_rows - cell.row),
                            "colspan": min(cell.colspan, self.max_cols - cell.col),
                        }
                    )
                )
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
        """Put a video at (row, col), in place of the one there: in the
        whole of its cell, should it be a big one."""

        self.remove_video(video_id)
        old = self._occupied_map().get((row, col))
        if old is None:
            self.cells.append(GridCell(video_id=video_id, row=row, col=col))
            return
        self.cells = [
            c.model_copy(update={"video_id": video_id}) if c is old else c
            for c in self.cells
        ]

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
        if self.shows_every_cell:
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
        # a big cell it goes through gets a row more
        self.cells = [
            cell.model_copy(update={"row": cell.row + 1})
            if cell.row >= at_row
            else cell.model_copy(update={"rowspan": cell.rowspan + 1})
            if cell.row + cell.rowspan > at_row
            else cell
            for cell in self.cells
        ]

    def _insert_grid_col(self, at_col: int) -> None:
        self.cells = [
            cell.model_copy(update={"col": cell.col + 1})
            if cell.col >= at_col
            else cell.model_copy(update={"colspan": cell.colspan + 1})
            if cell.col + cell.colspan > at_col
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
        """Make (row, col) empty by pushing the cell there one step along,
        and each cell in its way, and in theirs, as far as the first holes.

        A big cell moves as one, pushing all it comes up against. False,
        and nothing moved, when one would go past the max grid.
        """
        occ = self._occupied_map()
        first = occ.get((row, col))
        if first is None:
            return True

        pushed = [first]
        for cell in pushed:
            for cur_r, cur_c in _covered(cell):
                to = (cur_r + d_row, cur_c + d_col)
                if not self._in_max(*to):
                    return False
                other = occ.get(to)
                if other is not None and all(other is not p for p in pushed):
                    pushed.append(other)

        self.cells = [
            cell.model_copy(update={"row": cell.row + d_row, "col": cell.col + d_col})
            if any(cell is p for p in pushed)
            else cell
            for cell in self.cells
        ]
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

        # the sides of the cell there, a big one's beyond its other cells
        cell = occ.get((row, col))
        top, left = (cell.row, cell.col) if cell else (row, col)
        bottom = top + cell.rowspan if cell else row + 1
        right = left + cell.colspan if cell else col + 1

        n_r, n_c = {
            Direction.LEFT: (row, left - 1),
            Direction.RIGHT: (row, right),
            Direction.UP: (top - 1, col),
            Direction.DOWN: (bottom, col),
        }[direction]
        # Fill a hole in the current canvas. Cells past the displayed edge
        # are handled by grow / push so a new column/row stays aligned.
        if self._in_displayed(n_r, n_c) and (n_r, n_c) not in occ:
            self.occupy(n_r, n_c, video_id)
            return True, (n_r, n_c)

        if direction in {Direction.LEFT, Direction.RIGHT}:
            dest_r = row
            dest_c = left if direction == Direction.LEFT else right
            if self._can_insert_col() and self._in_max(dest_r, dest_c):
                self._insert_grid_col(dest_c)
                self.occupy(dest_r, dest_c, video_id)
                return True, (dest_r, dest_c)
            push = (0, 1)
        else:
            dest_r = top if direction == Direction.UP else bottom
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
