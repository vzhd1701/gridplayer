from collections.abc import Callable
from typing import NamedTuple

from PyQt5.QtCore import (
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSignalBlocker,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QCursor, QPainter, QPen, QRegion
from PyQt5.QtWidgets import QApplication, QHBoxLayout

from gridplayer.params.settings_fields import choices
from gridplayer.params.static import TileOverlap, TileResize
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
from gridplayer.utils.qt import translate
from gridplayer.widgets.grid_line_mark import (
    EDGE_COLOR,
    LINE_COLOR,
    GapMark,
    guides_clear_of,
    tile_snap_words,
)
from gridplayer.widgets.layout_editor import (
    CORNER_REACH,
    DIM_COLOR,
    DIM_TEXT_COLOR,
    EDGE_REACH,
    NAME_BACK_COLOR,
    SIZE_CURSORS,
    SWAP_COLOR,
    LayoutEditor,
    keys_text,
    modifier_name,
    paint_icon,
)
from gridplayer.widgets.settings_controls import (
    SegmentedChoice,
    Switch,
    ToggleChips,
    ToggleLabel,
)

# how far outside a tile the pointer takes its edges
OUTSIDE_REACH = 4

# the outline drawn on the tile's edge, inside it
OUTLINE_INSET = 1

# tiles this near overlapping only touch, for where a name goes
TOUCH = 0.5

# the buttons under a picked tile's name: lock, front, back
TOOL_SIZE = QRectF(0, 0, 24, 22)
TOOL_ICON = 14
TOOL_GAP = 2
TOOL_PADDING = 3
# between the name and the buttons under it
TOOLS_GAP = 4
TOOL_LIT_COLOR = QColor("#3a3a3a")
TOOL_OFF_COLOR = QColor("#6a6a6a")

# how far an arrow key moves the picked tile, and with Shift
NUDGE = 1
BIG_NUDGE = 10
# the arrows pressed one after another this soon are one change to undo
NUDGE_MS = 800

ARROWS = {
    Qt.Key_Left: (-1, 0),
    Qt.Key_Right: (1, 0),
    Qt.Key_Up: (0, -1),
    Qt.Key_Down: (0, 1),
}
OWN_KEYS = frozenset({*ARROWS, Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Delete})

# how wide the popup with the snaps is, for them to wrap
SNAPS_POPUP_WIDTH = 330


class TileSettings(NamedTuple):
    """The settings of Free Tiles the editor's bar changes: Tile Overlap,
    On Window Resize, Snap Tiles and Snap To, read and set."""

    overlap: Callable[[], TileOverlap]
    set_overlap: Callable[[TileOverlap], None]
    resize: Callable[[], TileResize]
    set_resize: Callable[[TileResize], None]
    is_snapping: Callable[[], bool]
    set_snapping: Callable[[bool], None]
    snaps: Callable[[], frozenset]
    set_snaps: Callable[[frozenset], None]


class _Label(NamedTuple):
    """A tile's name as it is drawn: the name as it fits, its box, the
    button to close the video in it, if shown, and the buttons under it, by
    what they do."""

    name: str
    box: QRectF
    close: QRectF | None
    tools: dict[str, QRectF]


class _Pending(NamedTuple):
    """A press on a tile, to move or size it once the pointer goes far
    enough, or swap it with another; a locked tile only the last, with no
    drag."""

    video_id: str
    handle: Handle
    drag: TileDrag | None
    at: QPoint


class TileEditor(LayoutEditor):
    """The tiles of Free Tiles, to move and size by hand: drawn over them,
    each an outline with its video's name.

    Dragged by an edge or a corner, a tile is sized; by the rest of it,
    moved: as it is outside the editor (see TileDrag), Tile Overlap, Snap To
    and all, the lines and gaps it snaps to drawn while it is, the others
    greyed and a dashed outline where it started. With the key that switches
    a drop held as it goes (Shift, unless the keymap says otherwise), a tile
    dragged by its middle onto another, even locked, swaps with it: their
    videos trade tiles, as a video dropped on another does outside. A double click on an edge
    stretches it to the next tile, or to the page's edge. The edges of a
    tile behind another are drawn dashed over the one in front, and taken
    there as well.

    A click picks a tile: under its name, buttons lock it, put it in
    front or behind; the arrow keys move it (Shift: further), and with Ctrl
    move its right or bottom edge; Tab picks the next, Delete closes it.
    The tile under the pointer, or the one picked, has a button in its name
    to close the video. A locked tile has a padlock by its name, and is
    neither moved nor sized.

    The bar has Arrange Tiles, Arrange Uncropped and Fit Tiles to Window,
    and Tile Overlap and Snap To, each in a small window of its own, before
    Undo, Redo and Done (see LayoutEditor).
    """

    is_tiles = True

    # tiles moved or sized: their rects on a page of the editor's size
    tiles_changed = pyqtSignal(object, float, float)
    # a tile going over the others, put in front of them
    front_requested = pyqtSignal(str)
    # one change to undo: begun, done, or put back
    change_started = pyqtSignal()
    change_finished = pyqtSignal()
    change_cancelled = pyqtSignal()
    stack_requested = pyqtSignal(str, bool)
    lock_requested = pyqtSignal(str, bool)
    close_requested = pyqtSignal(str)
    # a tile dragged onto another: their videos to trade tiles
    swap_requested = pyqtSignal(str, str)
    arrange_requested = pyqtSignal()
    arrange_uncropped_requested = pyqtSignal()
    fit_requested = pyqtSignal()

    def __init__(
        self,
        drag_of: Callable[..., TileDrag],
        settings: TileSettings,
        swap_key: Callable[[], Qt.KeyboardModifier | None],
        can_undo,
        can_redo,
        can_reopen,
        parent=None,
    ):
        super().__init__(can_undo, can_redo, can_reopen, parent)

        # the drag of a tile: drag_of(tiles, video_id, handle, page width,
        # page height, pointer)
        self._drag_of = drag_of
        self._settings = settings
        # the key held for a drag to swap, if any
        self._swap_key = swap_key

        self._tiles = FreeTiles()
        self._names: dict[str, str] = {}
        self._rects: dict[str, Rect] = {}

        self._picked: str | None = None
        # what the pointer is on: a tile and its edge, or its name's button
        self._hover: tuple[str, Handle] | None = None
        self._hover_button: tuple[str, str] | None = None
        # the button pressed, in a tile's name: the video, what it does
        self._pressed_button: tuple[str, str] | None = None

        self._pending: _Pending | None = None
        self._drag: TileDrag | None = None
        # the tile dragged to swap, and the one it is over, if any
        self._swapping: str | None = None
        self._swap_with: str | None = None
        self._guides: list[Guide] = []
        self._gaps: list[Gap] = []

        # arrow keys pressed one after another: one change
        self._is_nudging = False
        self._nudge_timer = QTimer(self)
        self._nudge_timer.setSingleShot(True)
        self._nudge_timer.setInterval(NUDGE_MS)
        self._nudge_timer.timeout.connect(self._end_nudge)

        self._make_bar()
        self._set_hint(translate("Edit Grid", "Drag edges to resize, tiles to move."))

    def _make_bar(self) -> None:
        self._arrange = self._bar_button(
            self.arrange_requested, translate("Actions", "Arrange Tiles"), "arrange"
        )
        self._arrange_uncropped = self._bar_button(
            self.arrange_uncropped_requested,
            translate("Actions", "Arrange Uncropped"),
            "arrange_uncropped",
        )
        self._fit = self._bar_button(
            self.fit_requested, translate("Actions", "Fit Tiles to Window"), "fit"
        )
        self._overlap = self._bar_button(
            self._show_overlap, translate("Tile Overlap", "Tile Overlap"), "overlap"
        )
        self._resize = self._bar_button(
            self._show_resize,
            translate("On Window Resize", "On Window Resize"),
            "window_resize",
        )
        self._snap = self._bar_button(
            self._show_snaps, translate("Snap To", "Snap To"), "snap"
        )
        for button in (self._overlap, self._resize, self._snap):
            button.setCheckable(True)

        self._lay_out_bar(
            (
                self._arrange,
                self._arrange_uncropped,
                self._fit,
                None,
                self._overlap,
                self._resize,
                self._snap,
            )
        )

    # --- the tiles ---

    def set_tiles(self, tiles: FreeTiles, names: dict[str, str]) -> None:
        """The tiles as they are now, on a page the editor's size, and the
        names of their videos."""

        self._tiles = tiles
        self._names = dict(names)
        self._rects = tiles.rects(self.width(), self.height())

        if self._picked not in self._rects:
            self._picked = None
        if self._dragged() is not None and self._dragged() not in self._rects:
            self.cancel_drag()
        if self._swap_with not in self._rects:
            self._swap_with = None

        if self._dragged() is None:
            self._hover_at(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def picked(self) -> str | None:
        return self._picked

    def pick(self, video_id: str | None) -> None:
        if video_id != self._picked:
            self._end_nudge()
            self._picked = video_id
            self.update()

    def is_dragging(self) -> bool:
        return self._dragged() is not None or self._pending is not None

    def _dragged(self) -> str | None:
        """The tile being moved, sized or swapped, if one is."""

        if self._drag is not None:
            return self._drag.video_id
        return self._swapping

    def cancel_drag(self) -> None:
        self._pending = None
        if self._swapping is not None:
            self._end_swap()
            return
        if self._drag is None:
            return
        self._drag = None
        self._clear_snapped()
        self.change_cancelled.emit()
        self._hover_at(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def finish(self) -> None:
        if self._drag is not None:
            self._finish_drag()
        if self._swapping is not None:
            self._end_swap()
        self._pending = None
        super().finish()

    def _end_change(self) -> None:
        self._end_nudge()

    def _is_locked(self, video_id: str) -> bool:
        return video_id in self._tiles.locked

    def _in_front_of(self, video_id: str) -> list[Rect]:
        ids = list(self._rects)
        return [self._rects[i] for i in ids[ids.index(video_id) + 1 :]]

    def _tile_at(self, point: QPoint) -> tuple[str, Handle] | None:
        """The tile at a point and what of it is there: an edge or a corner
        near it, to size it by, or the rest of it, to move it by. The edges
        of tiles behind the one in front first, but none behind a locked
        tile, and none of a locked tile."""

        x, y = point.x(), point.y()
        front_first = list(reversed(self._rects.items()))
        top = self._top_at(point)
        if top is not None and self._is_locked(top):
            return top, MOVE

        for video_id, rect in front_first:
            if self._is_locked(video_id) or not _contains(rect, x, y, OUTSIDE_REACH):
                continue
            handle = _handle_of(rect, x, y)
            if handle != MOVE:
                return video_id, handle

        return None if top is None else (top, MOVE)

    def _top_at(self, point: QPoint) -> str | None:
        """The tile in front at a point, if any."""

        return next(
            (
                video_id
                for video_id, rect in reversed(self._rects.items())
                if _contains(rect, point.x(), point.y(), 0)
            ),
            None,
        )

    # --- dragging ---

    def _start(self, pending: _Pending) -> None:
        self._pending = None
        self._drag = pending.drag
        self._hint_done()
        self.change_started.emit()
        self._set_cursor(pending.drag.handle, is_dragging=True)

    def _move_to(self, point: QPoint, modifiers) -> None:
        drag = self._drag
        is_snapping = not modifiers & Qt.AltModifier and self._settings.is_snapping()
        keeps_shape = not modifiers & Qt.ShiftModifier

        self._apply(drag, drag.moved((point.x(), point.y()), is_snapping, keeps_shape))

        guides = drag.guides() if is_snapping else []
        gaps = drag.gaps() if is_snapping else []
        words = tile_snap_words(guides, drag.fits, bool(gaps))
        self._show_snapped(guides_clear_of(guides, gaps), gaps, words, point)

    def _apply(self, drag: TileDrag, rect: Rect) -> None:
        """The tile dragged at rect, and those it pushed aside."""

        self.tiles_changed.emit(
            {**drag.pushed, drag.video_id: rect}, self.width(), self.height()
        )
        # over the others it goes, not under them; the tiles as they now are
        # (see set_tiles)
        if drag.is_over and self._tiles.is_under(drag.video_id):
            self.front_requested.emit(drag.video_id)

    def _finish_drag(self) -> None:
        self._drag = None
        self._clear_snapped()
        self.change_finished.emit()
        self._hover_at(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def _is_swap_held(self, modifiers) -> bool:
        key = self._swap_key()
        return key is not None and bool(modifiers & key)

    def _start_swap(self, video_id: str, point: QPoint) -> None:
        self._swapping = video_id
        self._hint_done()
        self.setCursor(Qt.ClosedHandCursor)
        self._swap_to(point)

    def _swap_to(self, point: QPoint) -> None:
        other = self._top_at(point)
        self._swap_with = None if other == self._swapping else other
        word = "" if self._swap_with is None else translate("Edit Grid", "Swap")
        self._show_snapped([], [], word, point)

    def _end_swap(self) -> None:
        self._swapping = None
        self._swap_with = None
        self._clear_snapped()
        self._hover_at(self.mapFromGlobal(QCursor.pos()))

    def _show_snapped(self, guides, gaps, words, point) -> None:
        self._guides = guides
        self._gaps = gaps
        self._show_tag(words, point)
        self.update()

    def _clear_snapped(self) -> None:
        self._show_snapped([], [], "", None)

    def _stretch(self, video_id: str, handle: Handle) -> None:
        """The tile's edges held stretched as far as they go."""

        drag = self._new_drag(video_id, handle, (0, 0))
        self.change_started.emit()
        self._apply(drag, drag.stretched())
        self.change_finished.emit()

    def _new_drag(self, video_id, handle, at) -> TileDrag:
        return self._drag_of(
            self._tiles, video_id, handle, self.width(), self.height(), at
        )

    # --- the keys ---

    def _is_own_key(self, event) -> bool:
        return super()._is_own_key(event) or (
            event.key() in OWN_KEYS and self._picked is not None
        )

    def focusNextPrevChild(self, is_next) -> bool:
        # Tab picks the next tile (see keyPressEvent)
        return False

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in ARROWS and self._picked is not None and not self.is_dragging():
            self._nudge(key, event.modifiers())
        elif key in {Qt.Key_Tab, Qt.Key_Backtab} and self._rects:
            is_back = key == Qt.Key_Backtab or event.modifiers() & Qt.ShiftModifier
            self._pick_next(-1 if is_back else 1)
        elif key == Qt.Key_Delete and self._picked is not None:
            self.close_requested.emit(self._picked)
        else:
            super().keyPressEvent(event)

    def _pick_next(self, step: int) -> None:
        order = self._tiles.order()
        if self._picked in order:
            at = (order.index(self._picked) + step) % len(order)
        else:
            at = 0 if step > 0 else -1
        self.pick(order[at])

    def _nudge(self, key, modifiers) -> None:
        """The picked tile moved by an arrow key, or its right or bottom
        edge with Ctrl: one change with those pressed soon after."""

        if self._is_locked(self._picked):
            return

        dx, dy = ARROWS[key]
        step = BIG_NUDGE if modifiers & Qt.ShiftModifier else NUDGE
        handle = MOVE
        if modifiers & Qt.ControlModifier:
            handle = (1, 0) if dx else (0, 1)

        if not self._is_nudging:
            self._is_nudging = True
            self._hint_done()
            self.change_started.emit()
        self._nudge_timer.start()

        drag = self._new_drag(self._picked, handle, (0, 0))
        self._apply(
            drag,
            drag.moved((dx * step, dy * step), is_snapping=False, keeps_shape=False),
        )

    def _end_nudge(self) -> None:
        self._nudge_timer.stop()
        if self._is_nudging:
            self._is_nudging = False
            self.change_finished.emit()

    # --- the mouse ---

    def _hover_at(self, point: QPoint) -> None:
        shown = self._hover, self._hover_button

        if self._is_on_bar(point):
            # nothing under the bar
            point = QPoint(-1, -1)

        self._hover_button = self._button_at(point)
        self._hover = None
        if self._hover_button is not None:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self._hover = self._tile_at(point) if self.rect().contains(point) else None
            if self._hover is None:
                self.unsetCursor()
            elif self._is_locked(self._hover[0]):
                self.setCursor(Qt.ArrowCursor)
            else:
                self._set_cursor(self._hover[1])

        if (self._hover, self._hover_button) != shown:
            self.setToolTip(self._tip_of(self._hover_button))
            self.update()

    def _tip_of(self, button: tuple[str, str] | None) -> str:
        if button is None:
            return ""
        return {
            "close": translate("Edit Grid", "Close"),
            "lock": translate("Actions", "Lock Tile"),
            "front": translate("Actions", "Bring to Front"),
            "back": translate("Actions", "Send to Back"),
        }[button[1]]

    def _set_cursor(self, handle: Handle, is_dragging=False) -> None:
        if handle == MOVE:
            self.setCursor(Qt.ClosedHandCursor if is_dragging else Qt.OpenHandCursor)
        else:
            self.setCursor(SIZE_CURSORS[handle])

    def _button_at(self, point: QPoint) -> tuple[str, str] | None:
        """The button in a tile's name the point is on: the video's, and
        "close", "lock", "front" or "back". Only the tiles picked or
        pointed at have any (see _label_of)."""

        pointf = QPointF(point)
        with_buttons = {
            self._picked,
            self._hover and self._hover[0],
            self._hover_button and self._hover_button[0],
        }
        for video_id in reversed(list(self._rects)):
            if video_id not in with_buttons:
                continue
            label = self._label_of(video_id)
            if label is None:
                continue
            if label.close is not None and label.close.contains(pointf):
                return video_id, "close"
            for tool, rect in label.tools.items():
                if rect.contains(pointf) and self._is_tool_on(video_id, tool):
                    return video_id, tool
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            if self.is_dragging():
                self.cancel_drag()
            return

        self._end_nudge()
        pos = event.pos()

        button = self._button_at(pos)
        if button is not None:
            self._pressed_button = button
            return

        found = self._tile_at(pos)
        if found is None:
            self.pick(None)
            return

        video_id, handle = found
        self.pick(video_id)
        drag = None
        if not self._is_locked(video_id):
            drag = self._new_drag(video_id, handle, (pos.x(), pos.y()))
        self._pending = _Pending(video_id, handle, drag, pos)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None:
            self._move_to(event.pos(), event.modifiers())
            return

        if self._swapping is not None:
            self._swap_to(event.pos())
            return

        if self._pending is not None:
            pending = self._pending
            distance = (event.pos() - pending.at).manhattanLength()
            if distance < QApplication.startDragDistance():
                return
            self._pending = None
            if pending.handle == MOVE and self._is_swap_held(event.modifiers()):
                self._start_swap(pending.video_id, event.pos())
            elif pending.drag is not None:
                self._start(pending)
                self._move_to(event.pos(), event.modifiers())
            return

        if self._pressed_button is None:
            self._hover_at(event.pos())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        if self._pressed_button is not None:
            pressed, self._pressed_button = self._pressed_button, None
            if self._button_at(event.pos()) == pressed:
                self._press_button(*pressed)
            return

        self._pending = None
        if self._drag is not None:
            self._finish_drag()
        elif self._swapping is not None:
            video_id, other = self._swapping, self._swap_with
            self._end_swap()
            if other is not None:
                self.swap_requested.emit(video_id, other)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        found = self._tile_at(event.pos())
        if found is None or found[1] == MOVE or self._is_locked(found[0]):
            # as a press, the second one
            self.mousePressEvent(event)
            return

        self._pending = None
        self._stretch(*found)

    def leaveEvent(self, event) -> None:
        if not self.is_dragging():
            self._hover = None
            self._hover_button = None
            self.update()

    def _press_button(self, video_id: str, button: str) -> None:
        if button == "close":
            self.close_requested.emit(video_id)
        elif button == "lock":
            self.lock_requested.emit(video_id, not self._is_locked(video_id))
        else:
            self.stack_requested.emit(video_id, button == "front")

    def _is_tool_on(self, video_id: str, tool: str) -> bool:
        if tool == "front":
            return self._tiles.is_under(video_id)
        if tool == "back":
            return self._tiles.is_over(video_id)
        return True

    # --- the popups ---

    def _show_overlap(self) -> None:
        choice = SegmentedChoice()
        for overlap, text in choices.tile_overlap().items():
            choice.addItem(text, overlap)

        def refresh():
            with QSignalBlocker(choice):
                choice.setCurrentIndex(choice.findData(self._settings.overlap()))

        refresh()
        choice.currentIndexChanged.connect(
            lambda _: self._settings.set_overlap(choice.currentData())
        )
        self._show_popup(
            self._overlap,
            translate("Tile Overlap", "Tile Overlap"),
            [choice],
            refresh=refresh,
        )

    def _show_resize(self) -> None:
        choice = SegmentedChoice()
        for resize, text in choices.tile_resize().items():
            choice.addItem(text, resize)

        def refresh():
            with QSignalBlocker(choice):
                choice.setCurrentIndex(choice.findData(self._settings.resize()))

        refresh()
        choice.currentIndexChanged.connect(
            lambda _: self._settings.set_resize(choice.currentData())
        )
        self._show_popup(
            self._resize,
            translate("On Window Resize", "On Window Resize"),
            [choice],
            refresh=refresh,
        )

    def _show_snaps(self) -> None:
        switch = Switch()
        switch_row = QHBoxLayout()
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.addWidget(switch)
        switch_row.addWidget(ToggleLabel(translate("Snap Lines", "Snap Tiles"), switch))
        switch_row.addStretch()

        chips = ToggleChips()
        chips.set_choices(choices.tile_snaps())

        def refresh():
            with QSignalBlocker(switch), QSignalBlocker(chips):
                switch.setChecked(self._settings.is_snapping())
                chips.set_picked(self._settings.snaps())
            chips.setEnabled(switch.isChecked())

        refresh()
        chips.changed.connect(lambda: self._settings.set_snaps(chips.picked()))

        def snapping(is_on):
            self._settings.set_snapping(is_on)
            chips.setEnabled(is_on)

        switch.toggled.connect(snapping)
        self._show_popup(
            self._snap,
            translate("Snap To", "Snap To"),
            [switch_row, chips],
            SNAPS_POPUP_WIDTH,
            refresh=refresh,
        )

    def _help_rows(self) -> list[tuple[str, str]]:
        shift = modifier_name(Qt.ShiftModifier)
        swap = self._swap_key()
        swap_rows = []
        if swap is not None:
            swap_rows.append(
                (
                    translate("Edit Grid", "{} + drag a tile").format(
                        modifier_name(swap)
                    ),
                    translate("Edit Grid", "Swap it with another"),
                )
            )
        return [
            (
                translate("Edit Grid", "Drag a tile"),
                translate("Edit Grid", "Move it"),
            ),
            *swap_rows,
            (
                translate("Edit Grid", "Drag an edge"),
                translate("Edit Grid", "Resize it"),
            ),
            (
                translate("Edit Grid", "{} + drag an edge").format(shift),
                translate("Edit Grid", "Resize to any shape"),
            ),
            (
                translate("Edit Grid", "{} + drag").format(
                    modifier_name(Qt.AltModifier)
                ),
                translate("Edit Grid", "No snapping"),
            ),
            (
                translate("Edit Grid", "Double-click an edge"),
                translate("Edit Grid", "Stretch it to the next tile"),
            ),
            (
                translate("Edit Grid", "{} while dragging").format(
                    keys_text(Qt.Key_Escape)
                ),
                translate("Edit Grid", "Put it back"),
            ),
            (
                translate("Edit Grid", "Click a tile"),
                translate("Edit Grid", "Pick it"),
            ),
            (
                translate("Edit Grid", "Arrows"),
                translate("Edit Grid", "Move the picked tile"),
            ),
            (
                translate("Edit Grid", "{} + arrows").format(shift),
                translate("Edit Grid", "Move it 10 px"),
            ),
            (
                translate("Edit Grid", "{} + arrows").format(
                    modifier_name(Qt.ControlModifier)
                ),
                translate("Edit Grid", "Resize it"),
            ),
            (
                translate("Edit Grid", "Tab, {} + Tab").format(shift),
                translate("Edit Grid", "Pick the next or previous tile"),
            ),
            (
                keys_text(Qt.Key_Delete),
                translate("Edit Grid", "Close the picked video"),
            ),
        ]

    # --- drawing ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_veil(painter)

        drag = self._drag
        dragged = self._dragged()
        # the tile dragged, and the one it swaps with
        lit = {dragged, self._swap_with}

        if self._swap_with is not None:
            painter.fillRect(_rect_f(self._rects[self._swap_with]), SWAP_COLOR)

        for video_id, rect in self._rects.items():
            if dragged is None:
                pen = QPen(LINE_COLOR, 2)
            elif video_id in lit:
                pen = QPen(LINE_COLOR, 3)
            else:
                pen = QPen(DIM_COLOR, 1)
            self._outline(painter, _rect_f(rect), pen, OUTLINE_INSET)

        # the edges of each tile hidden by those in front of it, dashed
        for video_id, rect in self._rects.items():
            front = _region(
                [r for r in self._in_front_of(video_id) if r.overlaps(rect)]
            )
            if front.isEmpty():
                continue
            painter.save()
            painter.setClipRegion(front)
            is_dim = dragged is not None and video_id not in lit
            color = DIM_COLOR if is_dim else LINE_COLOR
            self._outline(
                painter, _rect_f(rect), QPen(color, 1.5, Qt.DashLine), OUTLINE_INSET
            )
            painter.restore()

        if drag is not None:
            self._outline(
                painter,
                _rect_f(drag.start),
                QPen(LINE_COLOR, 1, Qt.DashLine),
                OUTLINE_INSET,
            )

        for video_id in self._rects:
            self._draw_label(
                painter, video_id, dragged is not None and video_id not in lit
            )

        if dragged is None:
            for video_id in {self._picked, self._hover and self._hover[0]}:
                if video_id in self._rects and not self._is_locked(video_id):
                    self._handles(painter, _rect_f(self._rects[video_id]), 1)

        for guide in self._guides:
            self._draw_guide(painter, guide)
        for gap in self._gaps:
            self._draw_gap(painter, gap)

    def _label_of(self, video_id: str) -> _Label | None:
        """Where a tile's name is drawn: in the middle of the biggest part
        of it no tile in front covers, the buttons under it if it is picked
        and there is room; None where it does not fit."""

        part = _biggest_shown(self._rects[video_id], self._in_front_of(video_id))
        if part is None:
            return None

        is_dragging = self._dragged() is not None
        has_close = not is_dragging and (
            video_id == self._picked
            or (self._hover is not None and self._hover[0] == video_id)
            or (self._hover_button is not None and self._hover_button[0] == video_id)
        )
        found = self._name_box(
            part,
            self._names.get(video_id, ""),
            has_close=has_close,
            has_icon=self._is_locked(video_id),
        )
        if found is None:
            return None
        name, box, close = found

        tools = {}
        tools_height = TOOL_SIZE.height() + 2 * TOOL_PADDING
        is_picked = video_id == self._picked and not is_dragging
        if is_picked and box.height() + TOOLS_GAP + tools_height + 8 <= part.height():
            # the name and the buttons, together in the middle
            lift = (TOOLS_GAP + tools_height) / 2
            box.translate(0, -lift)
            if close is not None:
                close.translate(0, -lift)
            top = box.bottom() + TOOLS_GAP + TOOL_PADDING
            width = 3 * TOOL_SIZE.width() + 2 * TOOL_GAP
            left = box.center().x() - width / 2
            for tool in ("lock", "front", "back"):
                tools[tool] = TOOL_SIZE.translated(left, top)
                left += TOOL_SIZE.width() + TOOL_GAP

        return _Label(name, box, close, tools)

    def _draw_label(self, painter, video_id: str, is_dim: bool) -> None:
        label = self._label_of(video_id)
        if label is None:
            return

        self._draw_name(
            painter,
            label.name,
            label.box,
            label.close,
            color=DIM_TEXT_COLOR if is_dim else LINE_COLOR,
            icon="lock" if self._is_locked(video_id) else None,
        )

        if label.tools:
            self._draw_tools(painter, video_id, label.tools)

    def _draw_tools(self, painter, video_id: str, tools: dict[str, QRectF]) -> None:
        rects = list(tools.values())
        bubble = QRectF(rects[0].topLeft(), rects[-1].bottomRight()).adjusted(
            -TOOL_PADDING, -TOOL_PADDING, TOOL_PADDING, TOOL_PADDING
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(NAME_BACK_COLOR)
        painter.drawRoundedRect(bubble, 6, 6)

        for tool, rect in tools.items():
            is_lit = tool == "lock" and self._is_locked(video_id)
            is_on = self._is_tool_on(video_id, tool)
            is_hovered = self._hover_button == (video_id, tool)
            if is_lit:
                back, color = LINE_COLOR, EDGE_COLOR
            else:
                back = TOOL_LIT_COLOR if is_hovered else QColor(Qt.transparent)
                color = LINE_COLOR if is_on else TOOL_OFF_COLOR
            painter.setPen(Qt.NoPen)
            painter.setBrush(back)
            painter.drawRoundedRect(rect, 4, 4)

            icon = QRectF(0, 0, TOOL_ICON, TOOL_ICON)
            icon.moveCenter(rect.center())
            paint_icon(painter, tool, icon, color)

    def _draw_guide(self, painter, guide: Guide) -> None:
        if guide.is_column:
            ends = (
                QPointF(guide.position, guide.start),
                QPointF(guide.position, guide.end),
            )
        else:
            ends = (
                QPointF(guide.start, guide.position),
                QPointF(guide.end, guide.position),
            )
        for color, width in ((EDGE_COLOR, 4), (LINE_COLOR, 2)):
            painter.setPen(QPen(color, width))
            painter.drawLine(*ends)

    def _draw_gap(self, painter, gap: Gap) -> None:
        """A line across the gap with a tick at each end, as GapMark is."""

        tick = GapMark.tick / 2
        if gap.is_column:
            lines = [
                (QPointF(gap.start, gap.position), QPointF(gap.end, gap.position)),
                (
                    QPointF(gap.start, gap.position - tick),
                    QPointF(gap.start, gap.position + tick),
                ),
                (
                    QPointF(gap.end, gap.position - tick),
                    QPointF(gap.end, gap.position + tick),
                ),
            ]
        else:
            lines = [
                (QPointF(gap.position, gap.start), QPointF(gap.position, gap.end)),
                (
                    QPointF(gap.position - tick, gap.start),
                    QPointF(gap.position + tick, gap.start),
                ),
                (
                    QPointF(gap.position - tick, gap.end),
                    QPointF(gap.position + tick, gap.end),
                ),
            ]
        for color, width in ((EDGE_COLOR, 3), (LINE_COLOR, 1)):
            painter.setPen(QPen(color, width))
            for line in lines:
                painter.drawLine(*line)


def _rect_f(rect: Rect) -> QRectF:
    return QRectF(QPointF(rect.left, rect.top), QPointF(rect.right, rect.bottom))


def _region(rects: list[Rect]) -> QRegion:
    # in whole pixels as the tiles are laid out, each edge rounded, not
    # widened: tiles that touch never overlap
    region = QRegion()
    for rect in rects:
        region = region.united(QRegion(QRect(*box_rect(Box(*rect), 1, 1))))
    return region


def _biggest_shown(rect: Rect, in_front: list[Rect]) -> QRectF | None:
    """The biggest part of a tile those in front of it leave showing, if
    any: it goes from the tile's left edge or the right edge of one in
    front, to its right edge or the left edge of one in front, and is as
    tall as the room between them. Tiles that only touch it cover none."""

    covers = [c for c in in_front if c.overlaps(rect, TOUCH)]
    lefts = sorted({rect.left, *(c.right for c in covers if c.right < rect.right)})
    rights = sorted({rect.right, *(c.left for c in covers if c.left > rect.left)})

    best, best_area = None, 0.0
    for left in lefts:
        for right in rights:
            if right - left <= TOUCH:
                continue
            across = sorted(
                (c.top, c.bottom)
                for c in covers
                if c.left < right - TOUCH and c.right > left + TOUCH
            )
            top = rect.top
            for bottom, next_top in (*across, (rect.bottom, rect.bottom)):
                area = (right - left) * (bottom - top)
                if area > best_area:
                    best_area = area
                    best = QRectF(QPointF(left, top), QPointF(right, bottom))
                top = max(top, next_top)
    return best


def _contains(rect: Rect, x: float, y: float, reach: float) -> bool:
    return (
        rect.left - reach <= x <= rect.right + reach
        and rect.top - reach <= y <= rect.bottom + reach
    )


def _handle_of(rect: Rect, x: float, y: float) -> Handle:
    """What of a tile is at a point: the edges near it, the corner where it
    is near two, none in the middle."""

    def near(reach) -> Handle:
        side_x = side_y = 0
        if abs(x - rect.left) <= reach:
            side_x = -1
        elif abs(x - rect.right) <= reach:
            side_x = 1
        if abs(y - rect.top) <= reach:
            side_y = -1
        elif abs(y - rect.bottom) <= reach:
            side_y = 1
        return side_x, side_y

    # a small tile keeps a middle to move it by
    corner = min(CORNER_REACH, rect.width / 4, rect.height / 4)
    found = near(corner)
    if all(found):
        return found
    return near(min(EDGE_REACH, rect.width / 4, rect.height / 4))
