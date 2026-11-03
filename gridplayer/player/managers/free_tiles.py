from typing import NamedTuple

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication

from gridplayer.models.tile_snaps import TileSnaps
from gridplayer.params.gestures import GESTURE_ZOOM_SELECT
from gridplayer.params.static import GridMode, TileOverlap, TileSnap
from gridplayer.player.managers.layout_drag import LayoutDragManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.drag_n_drop import query_drop_modifiers
from gridplayer.utils.keymap import drop_switch_modifier, is_gesture_press
from gridplayer.utils.layout.boxes import Box, box_rect
from gridplayer.utils.layout.free_tiles import (
    MOVE,
    FreeTiles,
    Gap,
    Guide,
    Handle,
    Rect,
    TileDrag,
)
from gridplayer.utils.qt import is_modal_open
from gridplayer.widgets.grid_line_mark import (
    GridLineTag,
    ShapeMark,
    guides_clear_of,
    show_pooled,
    tile_snap_words,
)
from gridplayer.widgets.layout_editor import SIZE_CURSORS
from gridplayer.widgets.tile_frame import TileFrame, TileLocks


class _Pointed(NamedTuple):
    """What of a tile the pointer is on: the tiles, where their page is on
    the screen, the tile's video, the edge or corner (see handle_at), and
    where the pointer is on the page."""

    tiles: FreeTiles
    page: QRect
    video_id: str
    handle: Handle
    at: tuple[float, float]


class FreeTilesManager(LayoutDragManager):
    """Moving and sizing the tiles of Free Tiles by hand.

    On a tile's edge or corner (see FreeTiles.handle_at) the pointer turns
    to a resize one, and pressed there the left button sizes the tile,
    which keeps its shape unless Shift is held: then it snaps to its
    video's, the picture with no bars around it. Pressed anywhere else on
    it, the tile is moved once the pointer goes far enough, as a drag of
    the video would start: the press is the video's still, a click or a
    double click as ever, but never a drag of the video (see
    is_tile_pressed). Held once it goes far enough, the key that switches
    a drop leaves the drag to the video's (see DragNDropManager), to trade
    places with another, or take its place.

    Neither goes off the page, nor over another tile unless Tile Overlap
    is on: then the tile is put in front of any it goes over as it is
    moved or sized (see TileDrag). With Push Aside, those it goes over are
    made smaller, or moved where there is room, as it goes. Each snaps to
    the edges and middles of the others and of the page, to where it
    started and to its video's shape, as Snap To says, shown as lines while
    it is in line with them; and, if told, to be as
    far from those beside it as others are, the gaps marked (a line along
    a mark left out); a word by the pointer saying what they are, unless
    Alt is held, or Snap Lines is off.
    Esc puts the tile back, and any it pushed.
    A double click on an edge stretches it to the next tile, or to the
    page's edge.

    A locked tile is neither: a press on it is the video's, and the others
    stop at its edges, a lock shown on it while one is moved or sized.

    The tile's frame shows what the pointer is about to move or size, and
    what it is (see TileFrame).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag: TileDrag | None = None
        # where the page was when the tile was pressed on, on the screen
        self._page = QRect()
        # a press on a tile, to move it once the pointer goes far enough:
        # the drag to start, where it was pressed, and where the page was
        self._pressed: tuple[TileDrag, QPoint, QRect] | None = None

        self._guides: list[ShapeMark] = []
        self._gaps: list[ShapeMark] = []
        self._tag: GridLineTag | None = None
        self._frame = TileFrame(self.parent())
        self._locks = TileLocks(self.parent())

    @property
    def commands(self):
        return {
            "is_tile_pressed": self.is_tile_pressed,
            "is_tile_snap": self.is_tile_snap,
            "toggle_tile_snap": self.toggle_tile_snap,
            "tile_snaps": self.tile_snaps,
            "set_tile_snaps": self.set_tile_snaps,
            "tile_drag_of": self.tile_drag_of,
        }

    def is_tile_snap(self, snap: TileSnap) -> bool:
        return snap in PlaylistSettings().get("playlist/tile_snaps")

    def tile_snaps(self) -> frozenset[TileSnap]:
        return PlaylistSettings().get("playlist/tile_snaps").root

    def set_tile_snaps(self, snaps: frozenset[TileSnap]) -> None:
        PlaylistSettings().set("playlist/tile_snaps", TileSnaps(snaps))

    def toggle_tile_snap(self, snap: TileSnap) -> None:
        snaps = PlaylistSettings().get("playlist/tile_snaps").toggled(snap)
        PlaylistSettings().set("playlist/tile_snaps", snaps)
        # by a key, a tile may be held
        if self._drag is not None:
            self._drag.snap_to(snaps.root)

    def is_tile_pressed(self) -> bool:
        """Whether a press on a tile is the tile's still, to be moved once
        the pointer goes far enough. Once it is moved, the press is
        forgotten as a video's (see _begin_drag)."""

        return self._pressed is not None

    def mouse_move(self, event):
        if self._drag is not None:
            if not event.buttons() & Qt.LeftButton:
                # let go of somewhere the release never came from
                self._finish()
                return None

            self._move_to(QCursor.pos(), event.modifiers())
            return True

        if self._pressed is not None and event.buttons() & Qt.LeftButton:
            return self._move_if_far(event) or None

        if event.buttons() == Qt.NoButton:
            self._pressed = None
            self._hover_under_pointer()
        return None

    def mouse_release(self, event):
        self._pressed = None
        return super().mouse_release(event)

    def mouse_double_click(self, event):
        if event.button() != Qt.LeftButton:
            return None

        # the second press of it took the edge
        if self._drag is not None:
            drag = self._drag
            self._finish()
        else:
            pointed = self._tile_under_pointer()
            if pointed is None or pointed.handle == MOVE:
                return None
            drag = self._drag_of(pointed)
            self._page = pointed.page

        self._ctx.commands.begin_grid_change()
        self._set_tiles(drag, drag.stretched())
        self._ctx.commands.end_grid_change()

        self._swallowed_buttons.add(event.button())
        return True

    # --- inside ---

    def _press(self, event):
        self._pressed = None
        if event.button() != Qt.LeftButton:
            return None

        pointed = self._tile_under_pointer()
        if pointed is None:
            return None

        # a selection to zoom to, the gesture's
        if is_gesture_press(GESTURE_ZOOM_SELECT, event):
            return None

        drag = self._drag_of(pointed)
        if drag.is_move:
            if not self._is_movable(drag.video_id, event):
                return None
            # the video's press still: a click, or a drag of the tile
            self._pressed = (drag, QCursor.pos(), pointed.page)
            return None

        self._start(drag, pointed.page)
        self._swallowed_buttons.add(event.button())
        return True

    def _leave(self):
        self._pressed = None
        self._set_cursor(None)
        self._frame.hide()
        # until the pointer is seen over the player again: over another
        # application's window, it is nowhere else of its own
        self._check_timer.stop()

    def _is_free_now(self) -> bool:
        """Whether the tiles can still be moved by hand: neither Single Mode
        nor another mode come while one was held."""

        return self._ctx.commands.is_grid_free() and not self._ctx.is_single_mode

    def _tile_under_pointer(self) -> _Pointed | None:
        """What of a tile the pointer is on, if the tiles can be moved now."""

        if is_modal_open() or self._ctx.is_drag_ui or self._is_pointer_taken():
            return None

        free = self._ctx.commands.free_page()
        if free is None:
            return None

        pos = QCursor.pos()
        if self.is_elsewhere_at(pos):
            return None

        page = free.rect
        local = pos - page.topLeft()
        found = free.tiles.handle_at(local.x(), local.y(), page.width(), page.height())
        if found is None:
            return None

        video_id, handle = found
        if handle != MOVE and self._is_control_at(video_id, pos):
            # the overlay's button or bar by the edge: its own, as on the
            # rest of the tile
            handle = MOVE
        return _Pointed(free.tiles, page, video_id, handle, (local.x(), local.y()))

    def _drag_of(self, pointed: _Pointed) -> TileDrag:
        """The drag of the tile pointed at, from where the pointer is."""

        return self.tile_drag_of(
            pointed.tiles,
            pointed.video_id,
            pointed.handle,
            pointed.page.width(),
            pointed.page.height(),
            pointed.at,
        )

    def tile_drag_of(
        self,
        tiles: FreeTiles,
        video_id: str,
        handle: Handle,
        page_width: float,
        page_height: float,
        pointer: tuple[float, float],
    ) -> TileDrag:
        """A tile's drag by its handle, from where the pointer is on its
        page, as the settings say: Snap To and Tile Overlap. In Mosaic,
        over the others, which make room for it as it goes: what it snaps
        to of them, only the locked tiles, which stay."""

        overlap = self._ctx.commands.tile_overlap()
        is_mosaic = self._ctx.commands.is_grid_mode_set_to(GridMode.MOSAIC)
        if is_mosaic:
            tiles = tiles.copy()
            tiles.tiles = {
                i: box
                for i, box in tiles.tiles.items()
                if i == video_id or i in tiles.locked
            }
        return TileDrag(
            tiles,
            video_id,
            handle,
            page_width,
            page_height,
            pointer,
            self._shape_of(video_id),
            snaps=self.tile_snaps(),
            is_over=is_mosaic or overlap == TileOverlap.ON,
            is_pushing=not is_mosaic and overlap == TileOverlap.PUSH,
        )

    def _shape_of(self, video_id: str) -> float | None:
        block = self._ctx.video_blocks.by_video_id(video_id)
        return block.picture_shape if block is not None else None

    def _is_movable(self, video_id: str, event) -> bool:
        """Whether a press on a tile is one to move it by, once far enough:
        not on its overlay's controls, nor to drag the picture about."""

        block = self._ctx.video_blocks.by_video_id(video_id)
        if block is None or block.overlay.is_control_at(QCursor.pos()):
            return False
        return not self._ctx.commands.is_pan_press(event)

    def _is_control_at(self, video_id: str, global_pos: QPoint) -> bool:
        block = self._ctx.video_blocks.by_video_id(video_id)
        return block is not None and block.overlay.is_control_at(global_pos)

    def _move_if_far(self, event) -> bool:
        drag, pressed_at, page = self._pressed
        pos = QCursor.pos()
        if (pos - pressed_at).manhattanLength() < QApplication.startDragDistance():
            return False

        self._pressed = None

        # the drop's own key held: the video's drag, not the tile's
        switch = drop_switch_modifier()
        if switch is not None and query_drop_modifiers(event) & switch:
            return False

        self._start(drag, page)
        # the press was the video's: its release no click of it
        self._swallowed_buttons.add(Qt.LeftButton)
        self._move_to(pos, event.modifiers())
        return True

    def _hover_under_pointer(self):
        pointed = self._tile_under_pointer()
        if pointed is None or pointed.handle == MOVE:
            self._set_cursor(None)
            self._frame.hide()
            self._check_timer.stop()
            return

        page = pointed.page
        rect = pointed.tiles.rects(page.width(), page.height())[pointed.video_id]
        self._set_cursor(SIZE_CURSORS[pointed.handle])
        self._frame.show(_on_screen(rect, page), pointed.handle)
        self._check_timer.start()

    def _start(self, drag: TileDrag, page: QRect):
        self._drag = drag
        self._page = page
        self._begin_drag()

        self._set_cursor(SIZE_CURSORS.get(drag.handle, Qt.SizeAllCursor))
        self._locks.show([_on_screen(rect, page) for rect in drag.locked])

    def _move_to(self, global_pos: QPoint, modifiers):
        if not self._is_free_now():
            # Single Mode, or another mode, come while it was held
            self._finish()
            return

        drag = self._drag
        local = global_pos - self._page.topLeft()
        is_snapping = (
            not modifiers & Qt.AltModifier and self._ctx.commands.is_grid_line_snap()
        )
        keeps_shape = not modifiers & Qt.ShiftModifier

        rect = drag.moved((local.x(), local.y()), is_snapping, keeps_shape)
        self._set_tiles(drag, rect)
        if drag.is_over:
            # over the others it goes, not under them
            self._ctx.commands.bring_free_tile_to_front(drag.video_id)
        self._frame.show(
            _on_screen(rect, self._page),
            drag.handle,
            _on_screen(drag.start, self._page),
        )

        guides = drag.guides() if is_snapping else []
        gaps = drag.gaps() if is_snapping else []
        self._show_guides(guides_clear_of(guides, gaps))
        self._show_gaps(gaps)
        self._show_tag(tile_snap_words(guides, drag.fits, bool(gaps)), global_pos)

    def _set_tiles(self, drag: TileDrag, rect: Rect):
        """The tile dragged at rect, and those it pushed aside."""

        self._ctx.commands.set_free_tiles(
            {**drag.pushed, drag.video_id: rect},
            self._page.width(),
            self._page.height(),
            drag.video_id,
        )

    def _finish(self):
        self._end_drag()
        self._drag = None
        self._pressed = None

        self._show_guides([])
        self._show_gaps([])
        self._show_tag("", QPoint())
        self._frame.hide()
        self._locks.hide()

        # still on an edge, or gone
        self._hover_under_pointer()

    def _cancel(self):
        if self._drag is not None and self._is_free_now():
            # the tiles as they were, the page's shape too: nothing to undo
            self._ctx.commands.cancel_grid_change()

        self._finish()

    def _show_guides(self, guides: list[Guide]):
        def show(mark: ShapeMark, guide: Guide):
            along, across = self._page_at(guide.is_column)
            mark.show_guide(
                guide.is_column,
                along + guide.position,
                across + guide.start,
                across + guide.end,
                [across + point for point in guide.points],
            )

        show_pooled(self._guides, lambda: ShapeMark(self.parent()), guides, show)

    def _show_gaps(self, gaps: list[Gap]):
        def show(mark: ShapeMark, gap: Gap):
            along, across = self._page_at(gap.is_column)
            mark.show_gap(
                gap.is_column,
                along + gap.start,
                along + gap.end,
                across + gap.position,
            )

        show_pooled(self._gaps, lambda: ShapeMark(self.parent()), gaps, show)

    def _page_at(self, is_column: bool) -> tuple[int, int]:
        """Where the page is on the screen: across and down (is_column), or
        down and across."""

        page = self._page
        return (page.x(), page.y()) if is_column else (page.y(), page.x())

    def _show_tag(self, text: str, pointer: QPoint):
        """The word saying what the tile is in line with, by the pointer;
        none where it is in line with nothing."""

        if not text:
            if self._tag is not None and self._tag.isVisible():
                self._tag.hide()
            return

        if self._tag is None:
            self._tag = GridLineTag(self.parent())
        self._tag.show_text(text, True, pointer, self._page)


def _on_screen(rect: Rect, page: QRect) -> QRect:
    """A tile on a page at page on the screen, in whole pixels, as its cell
    is laid out."""

    return QRect(*box_rect(Box(*rect), 1, 1)).translated(page.topLeft())
