"""Edit Grid: an Auto grid made a Fixed Grid of its size, every cell of
it outlined in a window over the grid. A video's cell dragged by its edge
takes the next column, the video there going to a free cell; dragged by a
corner where the videos in its way have nowhere to go, it shows "No room"
and stays. The bar adds a row, and then it can. Dragged by the middle onto
another video, the other lit and "Swap" by the pointer, the two swap.
Ctrl+Z in it undoes. The gap beside a cell
is the line there, dragged to move it, one undo putting it back; where
it snaps, a word by it says to what. The bar's Reset Lines evens them,
Fit Lines to Videos fits them, each one undo; its magnet turns snapping off,
and follows Snap Lines turned on from the menu. The button in a video's
name closes
it. Esc is done: the videos' overlays
back, and only the cells with videos shown.
"""

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QCursor, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import GridMode

WIDTH, HEIGHT = 640, 400


def _editor(d):
    return d.player._managers_inst["grid_edit"]._editor


def _spans(d):
    return {
        cell.video_id: (cell.row, cell.col, cell.rowspan, cell.colspan)
        for cell in d.ctx.grid_state.cells
    }


def _mouse(d, kind, point: QPoint):
    """The mouse at a point of the editor, as its window has it from the
    system."""

    editor = _editor(d)
    window = editor.windowHandle()
    QCursor.setPos(editor.mapToGlobal(point))
    if kind == "hover":
        # a move with no button held, which QTest's never comes as; after
        # what the cursor put there brings, a leave of the window among it
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
        return
    if kind == "move":
        QTest.mouseMove(window, point)
    elif kind == "press":
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
    else:
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point)
    d.pump(0.05)


def _drag(d, start: QPoint, end: QPoint, release=True):
    _mouse(d, "move", start)
    _mouse(d, "press", start)
    for step in range(1, 5):
        _mouse(d, "move", start + (end - start) * step / 4)
    if release:
        _mouse(d, "release", end)
    d.pump(0.3)


def _inside(rect, x_share, y_share) -> QPoint:
    return QPoint(
        round(rect.left() + rect.width() * x_share),
        round(rect.top() + rect.height() * y_share),
    )


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    folder = d.media.folder
    d.open(
        folder / "a.mp4",
        folder / "b.mp4",
        folder / "c.mp4",
        d.media.shapes / "square.mp4",
    )
    d.wait_until(lambda: len(d.cells) == 4, "four cells")
    d.wait_until(lambda: all(c.is_playable for c in d.cells), "all playing")
    a, b, c, sq = (cell.video_id for cell in d.cells)
    d.pump(0.5)

    d.act(d.cells[0], "Edit Grid")
    d.pump(0.3)
    editor = _editor(d)
    d.check("the editor shown", editor is not None and editor.isVisible())
    state = d.ctx.grid_state
    d.check("made a Fixed Grid", state.mode == GridMode.FIXED, state.mode)
    d.check("of its size", (state.rows, state.cols) == (2, 2), state)
    d.check(
        "over the grid",
        editor.geometry() == d.ctx.commands.grid_area(),
        (editor.geometry(), d.ctx.commands.grid_area()),
    )
    d.check("overlays hidden", d.ctx.is_disable_overlay)
    d.check("ticked in the menu", d.ctx.actions["Edit Grid"].check_if())
    d.shot("1_editor", widget=editor)

    # a column more, from the bar
    editor._more_cols.click()
    d.pump(0.3)
    d.check("three columns", d.ctx.grid_state.cols == 3, d.ctx.grid_state)
    d.check(
        "the new ones empty, shown",
        len(d.player._managers_inst["grid"]._empty_cells) == 2,
    )

    # A's right edge to the next line: B goes to the free cell beside it
    editor = _editor(d)
    rect = editor.rect_of(0, 0, 1, 1)
    _drag(
        d,
        QPoint(rect.right() - 4, rect.center().y()),
        QPoint(editor.rect_of(0, 1, 1, 1).right(), rect.center().y()),
    )
    spans = _spans(d)
    d.check("A two cells wide", spans[a] == (0, 0, 1, 2), spans)
    d.check("B moved to the free cell", spans[b] == (0, 2, 1, 1), spans)

    # A's corner down a row: C and D in the way, one free cell
    rect = editor.rect_of(0, 0, 1, 2)
    end = _inside(editor.rect_of(1, 1, 1, 1), 0.9, 0.9)
    _drag(d, QPoint(rect.right() - 4, rect.bottom() - 4), end, release=False)
    d.check("no room shown", not editor._is_target_ok, editor._target)
    d.shot("2_no_room", widget=editor)
    _mouse(d, "release", end)
    d.pump(0.3)
    d.check("A as it was", _spans(d)[a] == (0, 0, 1, 2), _spans(d))

    # a row more, and then there is
    editor._more_rows.click()
    d.pump(0.3)
    rect = editor.rect_of(0, 0, 1, 2)
    _drag(
        d,
        QPoint(rect.right() - 4, rect.bottom() - 4),
        QPoint(editor.rect_of(1, 1, 1, 1).right(), editor.rect_of(1, 1, 1, 1).bottom()),
    )
    spans = _spans(d)
    d.check("A two by two", spans[a] == (0, 0, 2, 2), spans)
    d.check(
        "C and the square moved, nearest",
        {spans[c][:2], spans[sq][:2]} == {(1, 2), (2, 0)},
        spans,
    )
    d.shot("3_big", widget=editor)

    # the bar dragged up out of the way, and kept there
    bar = editor._bar
    grab = bar.geometry().topLeft() + QPoint(4, bar.height() // 2)
    _drag(d, grab, grab - QPoint(0, 150))
    moved = bar.geometry()
    d.check("bar moved up", moved.top() < HEIGHT - 150, moved)
    editor._more_cols.click()
    editor._fewer_cols.click()
    d.pump(0.3)
    d.check("bar kept there", _editor(d)._bar.geometry() == moved, bar.geometry())

    # dragged by a button that is off, as well
    redo = editor._action_buttons["redo"]
    d.check("redo off", not redo.isEnabled())
    grab = bar.mapTo(editor, redo.geometry().center())
    _drag(d, grab, grab + QPoint(0, 60))
    d.check("bar moved by it", bar.geometry().top() == moved.top() + 60, bar.geometry())

    # B dragged by its middle onto C: C lit, a word saying so; let go,
    # they swap
    b_at, c_at = spans[b], spans[c]
    _drag(
        d,
        editor.rect_of(*b_at).center(),
        editor.rect_of(*c_at).center(),
        release=False,
    )
    swapping = editor._swap_with
    d.check("C lit", swapping is not None and swapping.video_id == c, swapping)
    d.check(
        "the swap said",
        editor._tag is not None
        and editor._tag.isVisible()
        and editor._tag._text == "Swap",
    )
    d.shot("3_swap", widget=editor)
    _mouse(d, "release", editor.rect_of(*c_at).center())
    d.pump(0.3)
    d.check("the word gone", not editor._tag.isVisible())
    spans = _spans(d)
    d.check("swapped", spans[b] == c_at and spans[c] == b_at, spans)

    # undone with its key, in the editor
    QTest.keyClick(editor, Qt.Key_Z, Qt.ControlModifier)
    d.pump(0.3)
    d.check("swap undone", _spans(d)[b] == b_at, _spans(d))

    d.check(
        "no click: still playing",
        not any(cell.video_params.is_paused for cell in d.cells),
    )

    # the gap between A and the column beside it is a line, moved left
    editor = _editor(d)
    line_x = editor.rect_of(0, 2, 1, 1).left()
    at = QPoint(line_x, editor.rect_of(0, 2, 1, 1).center().y())
    _mouse(d, "hover", at)
    d.check("a line under the pointer", editor._hover_line is not None)
    d.check("Reset Lines off, the lines even", not editor._reset_lines.isEnabled())
    _drag(d, at, at - QPoint(80, 0))
    weights = d.ctx.grid_state.col_weights
    d.check("the columns no longer even", len(set(weights)) > 1, weights)
    d.check("A as big as it was", _spans(d)[a] == (0, 0, 2, 2), _spans(d))
    d.shot("4_line", widget=editor)

    QTest.keyClick(_editor(d), Qt.Key_Z, Qt.ControlModifier)
    d.pump(0.3)
    d.check("one undo puts it back", not d.ctx.grid_state.col_weights)

    # the bar's Reset Lines, then Fit Lines to Videos, each one undo
    _drag(d, at, at - QPoint(80, 0))
    editor = _editor(d)
    d.check("Reset Lines on", editor._reset_lines.isEnabled())
    editor._reset_lines.click()
    d.pump(0.3)
    weights = d.ctx.grid_state.col_weights
    d.check("reset: even", len(set(weights)) <= 1, weights)
    shown = _editor(d)._col_weights
    d.check("the editor drawing them even", len(set(shown)) <= 1, shown)
    d.check("Reset Lines off again", not _editor(d)._reset_lines.isEnabled())
    QTest.keyClick(_editor(d), Qt.Key_Z, Qt.ControlModifier)
    d.pump(0.3)
    QTest.keyClick(_editor(d), Qt.Key_Z, Qt.ControlModifier)
    d.pump(0.3)
    d.check("both undone", not d.ctx.grid_state.col_weights)
    fit = _editor(d)._fit_lines
    d.check(
        "Fit Lines as the menu has it",
        fit.isEnabled() == d.ctx.commands.is_grid_lines_fittable(),
    )
    if fit.isEnabled():
        fit.click()
        d.pump(0.3)
        weights = d.ctx.grid_state.col_weights
        d.check("fitted: the lines moved", bool(weights))
        shown = _editor(d)._col_weights
        d.check("the editor drawing them there", shown == tuple(weights), shown)
        QTest.keyClick(_editor(d), Qt.Key_Z, Qt.ControlModifier)
        d.pump(0.3)
        d.check("fit undone", not d.ctx.grid_state.col_weights)

    # moved a little, it snaps back to even, and says so
    editor = _editor(d)
    _drag(d, at, at + QPoint(3, 0), release=False)
    tag = editor._tag
    d.check(
        "the snap said",
        tag is not None and tag.isVisible() and tag._text == "Even",
        tag and tag._text,
    )
    d.shot("4_snapped", widget=editor)
    _mouse(d, "release", at + QPoint(3, 0))
    d.pump(0.2)
    d.check("and no longer, let go", not editor._tag.isVisible())

    # Snap Lines off from the bar's magnet, on again by its menu item
    d.check("the magnet pressed in", editor._snap.isChecked())
    editor._snap.click()
    d.pump(0.2)
    d.check("snapping off", not d.ctx.commands.is_grid_line_snap())
    d.check("the magnet let out", not editor._snap.isChecked())
    _drag(d, at, at + QPoint(3, 0), release=False)
    d.check("no snap said", not editor._tag.isVisible())
    _mouse(d, "release", at + QPoint(3, 0))
    d.pump(0.2)
    QTest.keyClick(_editor(d), Qt.Key_Z, Qt.ControlModifier)
    d.pump(0.3)
    d.ctx.actions["Snap Lines"].trigger()
    d.pump(0.2)
    d.check("snapping on", d.ctx.commands.is_grid_line_snap())
    d.check("the magnet pressed in again", _editor(d)._snap.isChecked())

    # the square closed with the button in its name
    editor = _editor(d)
    square = next(cell for cell in editor.cells() if cell.video_id == sq)
    close = editor.close_rect_of(square).center().toPoint()
    _mouse(d, "hover", close)
    d.check("the close button under the pointer", editor._close_at(close) == square)
    d.shot("5_close", widget=editor)
    _mouse(d, "press", close)
    _mouse(d, "release", close)
    d.wait_until(lambda: len(d.cells) == 3, "the square closed")
    d.check("the others where they were", _spans(d)[a] == (0, 0, 2, 2), _spans(d))

    # closing it left nothing to undo: the next change can be, at once
    editor = _editor(d)
    d.check("nothing to undo", not editor._action_buttons["undo"].isEnabled())
    editor._more_rows.click()
    d.pump(0.2)
    d.check("then undo lit", editor._action_buttons["undo"].isEnabled())
    editor._action_buttons["undo"].click()
    d.pump(0.2)

    # done
    QTest.keyClick(editor, Qt.Key_Escape)
    d.pump(0.3)
    d.check("editor gone", _editor(d) is None)
    d.check("overlays back", not d.ctx.is_disable_overlay)
    d.check("not ticked", not d.ctx.actions["Edit Grid"].check_if())
    state = d.ctx.grid_state
    d.check("still a Fixed Grid", state.mode == GridMode.FIXED, state)
    d.check("A still big", _spans(d)[a] == (0, 0, 2, 2), _spans(d))
    d.check(
        "the other videos still there, playing",
        len(d.cells) == 3 and all(cell.is_playable for cell in d.cells),
    )
    d.shot("6_done")

    # Done with a line still held: let go of where it is, one change to undo
    d.act(d.cells[0], "Edit Grid")
    d.wait_until(lambda: _editor(d) is not None, "the editor again")
    d.pump(0.3)
    editor = _editor(d)
    at = QPoint(
        editor.rect_of(0, 2, 1, 1).left(), editor.rect_of(0, 2, 1, 1).center().y()
    )
    _drag(d, at, at - QPoint(80, 0), release=False)
    QTest.keyClick(editor, Qt.Key_Return)
    d.pump(0.3)
    d.check("editor gone", _editor(d) is None)
    weights = d.ctx.grid_state.col_weights
    d.check("the line where it was let go", len(set(weights)) > 1, weights)
    d.ctx.actions["Undo Grid Change"].trigger()
    d.pump(0.3)
    weights = d.ctx.grid_state.col_weights
    d.check("undone: even again", len({round(w, 6) for w in weights}) <= 1, weights)
