"""Edit Grid in Free Tiles: a window over the tiles, each outlined with
its name. A tile dragged by
its middle moves, one undo putting it back; with Shift held, onto
another, the two swap, one undo too. A click picks it: the arrow
keys move it, one change to undo for those pressed one after another;
Tab picks the next. The lock under its name locks it. With Tile Overlap
on, from the bar, a tile dragged over another goes in front, the edge of
the one behind taken where it is hidden. Delete closes the picked video,
the bar's Reopen opens it again. A bar button's popup is closed by a
second click on it, not opened again. On Window Resize, set from the bar,
follows its key while its popup is up. Snap Lines' key turns
Snap To's switch while it is up. "?" lists the editor's keys. A
player's key still does its action in the editor. Esc is done: the
overlays back. The bar's switch to Grid makes it a Fixed Grid, its cells
edited, the bar where it was dragged to; Undo makes it Free Tiles again,
its tiles edited, Redo the Fixed Grid; to Tiles, Free Tiles again. From
Auto (Fit Shapes), Edit Grid makes Free Tiles; from Auto rows, a Fixed
Grid, which Undo takes back to rows, the editor gone.
"""

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QCursor, QKeySequence, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import GridMode, TileOverlap, TileResize
from gridplayer.widgets.settings_controls import SegmentedChoice, Switch
from gridplayer.widgets.tile_editor import NUDGE_MS
from tests.real_app.scenarios.free_tiles import (
    HEIGHT,
    WIDTH,
    _by_name,
    _near,
    _rects,
    _set,
)

A = (20, 20, 220, 120)
B = (300, 20, 500, 120)
C = (20, 220, 220, 320)


def _editor(d):
    return d.player._managers_inst["tile_edit"]._editor


def _mouse(d, kind, point: QPoint):
    """The mouse at a point of the editor, as its window has it from the
    system."""

    editor = _editor(d)
    window = editor.windowHandle()
    QCursor.setPos(editor.mapToGlobal(point))
    if kind == "hover":
        d.pump(0.05)
        QApplication.sendEvent(
            editor,
            QMouseEvent(
                QEvent.MouseMove,
                QPointF(point),
                Qt.NoButton,
                Qt.NoButton,
                Qt.NoModifier,
            ),
        )
    elif kind == "move":
        QTest.mouseMove(window, point)
    elif kind == "press":
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
    else:
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point)
    d.pump(0.05)


def _drag(d, start: QPoint, end: QPoint, release=True):
    _mouse(d, "move", start)
    _mouse(d, "press", start)
    for step in range(1, 9):
        _mouse(d, "move", start + (end - start) * step / 8)
    if release:
        _mouse(d, "release", end)
    d.pump(0.3)


def _shift_drag(d, start: QPoint, end: QPoint):
    """A drag with Shift held, the key that switches a drop."""

    editor = _editor(d)
    QTest.mousePress(editor, Qt.LeftButton, Qt.ShiftModifier, start)
    for step in range(1, 9):
        QApplication.sendEvent(
            editor,
            QMouseEvent(
                QEvent.MouseMove,
                QPointF(start + (end - start) * step / 8),
                Qt.NoButton,
                Qt.LeftButton,
                Qt.ShiftModifier,
            ),
        )
        d.pump(0.02)
    QTest.mouseRelease(editor, Qt.LeftButton, Qt.ShiftModifier, end)
    d.pump(0.3)


def _click(d, point: QPoint):
    _mouse(d, "move", point)
    _mouse(d, "press", point)
    _mouse(d, "release", point)
    d.pump(0.2)


def _key(d, key, modifiers=Qt.NoModifier):
    QTest.keyClick(_editor(d), key, modifiers)
    d.pump(0.05)


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.picture_shape for c in d.cells), "shapes known")
    d.pump(0.5)

    d.act(d.cells[0], "Free Tiles")
    d.pump(0.3)
    _set(d, "a.mp4", A)
    _set(d, "b.mp4", B)
    _set(d, "c.mp4", C)

    grid = d.player._managers_inst["grid"]
    a, b, c = (_by_name(d, name).video_id for name in ("a.mp4", "b.mp4", "c.mp4"))
    actions = d.ctx.actions

    d.act(d.cells[0], "Edit Grid")
    d.pump(0.3)
    editor = _editor(d)
    d.check("the editor shown", editor is not None and editor.isVisible())
    page = d.ctx.commands.free_page()
    d.check(
        "over the tiles",
        editor.geometry() == page.rect,
        (editor.geometry(), page.rect),
    )
    d.check("overlays hidden", d.ctx.is_disable_overlay)
    d.check("ticked in the menu", actions["Edit Grid"].check_if())
    d.shot("1_editor", widget=editor)

    # a dragged by its middle, to the right
    _drag(d, QPoint(120, 70), QPoint(170, 70))
    d.check("a moved", _near(_rects(d)["a.mp4"], (70, 20, 270, 120)), _rects(d))
    d.check("a picked by it", editor.picked() == a, editor.picked())
    editor._action_buttons["undo"].click()
    d.pump(0.3)
    d.check("put back by Undo", _near(_rects(d)["a.mp4"], A), _rects(d))

    # a dragged onto b with Shift held: the two swap, one change to undo
    _shift_drag(d, QPoint(120, 70), QPoint(400, 70))
    rects = _rects(d)
    d.check(
        "swapped",
        _near(rects["a.mp4"], B) and _near(rects["b.mp4"], A),
        rects,
    )
    editor._action_buttons["undo"].click()
    d.pump(0.3)
    rects = _rects(d)
    d.check(
        "swap undone",
        _near(rects["a.mp4"], A) and _near(rects["b.mp4"], B),
        rects,
    )

    # the arrow keys: three single steps, a big one, one change
    _click(d, QPoint(120, 70))
    d.check("a picked by a click", editor.picked() == a, editor.picked())
    for _ in range(3):
        _key(d, Qt.Key_Right)
    _key(d, Qt.Key_Down, Qt.ShiftModifier)
    d.check("a nudged", _near(_rects(d)["a.mp4"], (23, 30, 223, 130)), _rects(d))
    _key(d, Qt.Key_Right, Qt.ControlModifier)
    d.check("its right edge, with Ctrl", _near(_rects(d)["a.mp4"], (23, 30, 224, 130)))
    d.pump(NUDGE_MS / 1000 + 0.3)
    editor._action_buttons["undo"].click()
    d.pump(0.3)
    d.check("one Undo for the keys", _near(_rects(d)["a.mp4"], A), _rects(d))

    # Tab: b, the next as they are read
    _click(d, QPoint(120, 70))
    _key(d, Qt.Key_Tab)
    d.check("Tab picks b", editor.picked() == b, editor.picked())

    # b's lock, under its name
    lock = editor._label_of(b).tools["lock"].center().toPoint()
    d.shot("2_picked", widget=editor)
    _click(d, lock)
    d.check("b locked", grid._free.locked == {b}, grid._free.locked)
    _click(d, lock)
    d.check("b let go of", not grid._free.locked, grid._free.locked)

    # Tile Overlap on, from the bar
    editor._overlap.click()
    d.pump(0.3)
    popup = editor._popup
    d.check("Tile Overlap shown", popup is not None and popup.isVisible())
    d.shot("3_overlap")
    choice = popup.findChild(SegmentedChoice)
    choice.setCurrentIndex(choice.findData(TileOverlap.ON))
    d.check(
        "set to On",
        d.ctx.commands.tile_overlap() == TileOverlap.ON,
        d.ctx.commands.tile_overlap(),
    )

    # a second click on its button closes it, and opens no other
    button = editor._overlap
    at = button.mapTo(editor, button.rect().center())
    _click(d, at)
    d.check("closed by its button", editor._popup is None, editor._popup)
    d.check("the button let go of", not button.isChecked())
    d.pump(0.4)
    _click(d, at)
    d.check("opened again by the next click", editor._popup is not None)
    _click(d, at)
    d.check("and closed by the one after", editor._popup is None)

    # On Window Resize, from the bar; its key, pressed with it up: the
    # popup follows
    d.pump(0.4)
    before = _rects(d)
    d.ctx.actions["On Window Resize Fit"].setShortcuts([QKeySequence("Ctrl+Alt+R")])
    d.pump(0.3)
    editor._resize.click()
    d.pump(0.3)
    choice = editor._popup.findChild(SegmentedChoice)
    d.check("On Window Resize shown", choice.currentData() == TileResize.FIT)
    d.shot("3b_window_resize", widget=editor)
    d.shot("3c_window_resize_popup", widget=editor._popup)
    choice.setCurrentIndex(choice.findData(TileResize.KEEP))
    d.check("set to Keep Tile Sizes", d.ctx.commands.tile_resize() == TileResize.KEEP)
    QTest.keyClick(editor._popup, Qt.Key_R, Qt.ControlModifier | Qt.AltModifier)
    d.pump(0.3)
    d.check("its key set it back", d.ctx.commands.tile_resize() == TileResize.FIT)
    d.check(
        "the popup with it",
        choice.currentData() == TileResize.FIT,
        choice.currentData(),
    )
    button = editor._resize
    _click(d, button.mapTo(editor, button.rect().center()))
    d.check("closed by its button", editor._popup is None, editor._popup)
    d.pump(0.4)
    # Scale to Fit fits the tiles to the window at once: both changes undone
    editor._action_buttons["undo"].click()
    editor._action_buttons["undo"].click()
    d.pump(0.3)
    d.check("Keep Tile Sizes undone", d.ctx.commands.tile_resize() == TileResize.FIT)
    rects = _rects(d)
    d.check(
        "the tiles where they were",
        all(_near(rects[name], tuple(before[name])) for name in before),
        rects,
    )

    # Snap Lines' key, pressed with Snap To up: its switch follows
    d.ctx.actions["Snap Lines"].setShortcuts([QKeySequence("Ctrl+Alt+S")])
    d.pump(0.3)
    editor._snap.click()
    d.pump(0.3)
    switch = editor._popup.findChild(Switch)
    is_on = d.ctx.commands.is_grid_line_snap()
    d.check("Snap Tiles as it is", switch.isChecked() == is_on)
    QTest.keyClick(editor._popup, Qt.Key_S, Qt.ControlModifier | Qt.AltModifier)
    d.pump(0.3)
    d.check("its key turned it", d.ctx.commands.is_grid_line_snap() != is_on)
    d.check("the switch with it", switch.isChecked() != is_on)
    d.check("Snap To still up", editor._popup is not None)
    editor._popup.close()
    d.pump(0.5)
    _key(d, Qt.Key_S, Qt.ControlModifier | Qt.AltModifier)
    d.check("and in the editor", d.ctx.commands.is_grid_line_snap() == is_on)
    d.ctx.actions["Snap Lines"].setShortcuts([])

    # c over a: in front of it
    _drag(d, QPoint(120, 270), QPoint(150, 120))
    order = list(grid._free.tiles)
    d.check("c in front of a", order.index(c) > order.index(a), order)
    d.shot("4_over", widget=editor)

    # a's bottom edge, under c, still a's
    rects = _rects(d)
    bottom = round(rects["a.mp4"].bottom) - 2
    taken = editor._tile_at(QPoint(round(rects["c.mp4"].center_x), bottom))
    d.check("a's hidden edge taken", taken == (a, (0, 1)), taken)

    # Delete closes the picked one, Reopen opens it again
    _click(d, QPoint(380, 70))
    d.check("b picked", editor.picked() == b, editor.picked())
    _key(d, Qt.Key_Delete)
    d.wait_until(lambda: len(d.cells) == 2, "b closed")
    d.check("reopen on", editor._action_buttons["reopen"].isEnabled())
    editor._action_buttons["reopen"].click()
    d.wait_until(lambda: len(d.cells) == 3, "b open again")
    d.pump(0.5)
    d.check("b where it was", _near(_rects(d)["b.mp4"], B, 2), _rects(d))

    # the keys, from "?"
    editor._help.click()
    d.pump(0.3)
    d.check("the keys listed", editor._popup is not None)
    d.shot("5_keys", widget=editor._popup)
    editor._popup.close()
    d.pump(0.5)

    # a player's own key: Space plays and pauses
    paused = [cell.video_params.is_paused for cell in d.cells]
    _key(d, Qt.Key_Space)
    d.pump(0.5)
    d.note(
        {"paused before": paused, "after": [c.video_params.is_paused for c in d.cells]}
    )
    d.check(
        "Space still the player's",
        [c.video_params.is_paused for c in d.cells] != paused,
    )
    _key(d, Qt.Key_Space)
    d.pump(0.3)

    # Esc: done
    _key(d, Qt.Key_Escape)
    d.pump(0.3)
    d.check("the editor gone", _editor(d) is None)
    d.check("overlays back", not d.ctx.is_disable_overlay)
    d.check("unticked", not actions["Edit Grid"].check_if())

    # the bar's switch: Grid, then Tiles again, the bar kept where it was
    grid_edit = d.player._managers_inst["grid_edit"]
    d.act(d.cells[0], "Edit Grid")
    d.pump(0.3)
    editor = _editor(d)
    editor._bar.offset = QPoint(-100, -150)
    editor.place_bar()
    bar_at = editor._bar.geometry()
    editor._kind.setCurrentIndex(editor._kind.findData(False))
    d.pump(0.5)
    d.check("a Fixed Grid", d.ctx.commands.is_grid_fixed())
    d.check("its cells edited", grid_edit._editor is not None)
    d.check("the tiles' editor gone", _editor(d) is None)
    d.check("overlays still hidden", d.ctx.is_disable_overlay)
    d.check("still ticked", actions["Edit Grid"].check_if())
    d.check(
        "the bar where it was",
        grid_edit._editor._bar.geometry().top() == bar_at.top(),
        (grid_edit._editor._bar.geometry(), bar_at),
    )
    d.check("no hint", grid_edit._editor._hint.isHidden())
    d.shot("6_switched", widget=grid_edit._editor)

    # the switch undone: the tiles' editor again; redone: the cells'
    grid_edit._editor._action_buttons["undo"].click()
    d.pump(0.5)
    d.check("undone: Free Tiles", d.ctx.commands.is_grid_free())
    d.check("its tiles edited", _editor(d) is not None and grid_edit._editor is None)
    d.check("the switch says Tiles", _editor(d)._kind.currentData() is True)
    _editor(d)._action_buttons["redo"].click()
    d.pump(0.5)
    d.check("redone: a Fixed Grid", d.ctx.commands.is_grid_fixed())
    d.check("its cells edited", grid_edit._editor is not None and _editor(d) is None)
    d.check("overlays hidden all along", d.ctx.is_disable_overlay)
    grid_edit._editor._kind.setCurrentIndex(1)
    d.pump(0.5)
    d.check("Free Tiles again", d.ctx.commands.is_grid_free())
    d.check("the tiles edited", _editor(d) is not None)
    d.check("the cells' editor gone", grid_edit._editor is None)
    d.act(d.cells[0], "Edit Grid")
    d.pump(0.3)
    d.check("Edit Grid again: done", _editor(d) is None)
    d.check("overlays back again", not d.ctx.is_disable_overlay)

    # from the Auto modes: Fit Shapes made Free Tiles, rows a Fixed Grid
    d.ctx.commands.set_grid_mode(GridMode.AUTO_SHAPES)
    d.pump(0.3)
    d.act(d.cells[0], "Edit Grid")
    d.pump(0.3)
    d.check("Fit Shapes: Free Tiles", d.ctx.commands.is_grid_free())
    d.check("its tiles edited", _editor(d) is not None)
    _key(d, Qt.Key_Escape)
    d.ctx.commands.set_grid_mode(GridMode.AUTO_ROWS)
    d.pump(0.3)
    d.act(d.cells[0], "Edit Grid")
    d.pump(0.3)
    d.check("rows: a Fixed Grid", d.ctx.commands.is_grid_fixed())
    d.check("its cells edited", grid_edit._editor is not None)

    # undone back to rows: nothing to edit, the editor gone
    grid_edit._editor._action_buttons["undo"].click()
    d.pump(0.5)
    d.check(
        "rows again",
        d.ctx.commands.is_grid_mode_set_to(GridMode.AUTO_ROWS),
        d.ctx.grid_state.mode,
    )
    d.check("no editor", grid_edit._editor is None and _editor(d) is None)
    d.check("overlays back at last", not d.ctx.is_disable_overlay)
