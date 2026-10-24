"""The line between two cells is dragged with the mouse: the pointer turns
over it, the line shows once pressed, the cells go with it, it snaps where
the phone video
just fits, and not with Alt held. Esc puts it back, a double click evens
it out, and none of it is a click or a drag of a video. Undo takes a
drag back. Fit Lines to
Videos and Reset Lines do it from the menu, and Fit Shapes has no lines.
A short last row that Fill Gaps spreads has lines of its own, moved apart
from the columns over it, and with Link Rows off every row has, snapping
in line with the next. The line shows as soon as the pointer is on it,
and goes once the pointer leaves, unless "Show grid lines on hover" is off.
"""

import shutil

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QCursor, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.grid_state import GridState
from gridplayer.params.static import GridMode

# side by side, the phone video's whole picture is 300 * 9 / 16 wide, and
# the 16:9 one's 533: just more than there is. Small enough for the
# offscreen screen, 800 by 600, which the line's window is kept inside
WIDTH, HEIGHT = 700, 300
PHONE_FITS = 168.75


def _lines_manager(d):
    return d.player._managers_inst["grid_lines"]


def _widths(d):
    return [cell.geometry().width() for cell in d.cells]


def _row_widths(d, top):
    return [c.geometry().width() for c in d.cells if (c.geometry().top() == 0) == top]


def _at(d, x, y=HEIGHT // 2) -> QPoint:
    return d.ctx.commands.grid_area().topLeft() + QPoint(x, y)


def _mouse(d, kind, pos, button=Qt.LeftButton, modifiers=Qt.NoModifier):
    """The pointer there, and the mouse event, as the window it is over has
    them from the system."""

    # offscreen, where the pointer is is what it was last put at
    QCursor.setPos(pos)

    window = d.player.windowHandle()
    local = window.mapFromGlobal(pos)

    if kind == "move" and modifiers != Qt.NoModifier:
        # a move with keys held, which QTest has no way to make
        event = QMouseEvent(
            QEvent.MouseMove, local, pos, Qt.NoButton, Qt.LeftButton, modifiers
        )
        QApplication.sendEvent(window, event)
    elif kind == "move":
        QTest.mouseMove(window, local)
    elif kind == "press":
        QTest.mousePress(window, button, modifiers, local)
    elif kind == "release":
        QTest.mouseRelease(window, button, modifiers, local)
    elif kind == "double":
        QTest.mouseDClick(window, button, modifiers, local)

    d.pump(0.1)


def _tag(d):
    """What the word beside the line says, None when it is not shown."""
    tag = _lines_manager(d)._tag
    if tag is None or not tag.isVisible():
        return None
    return tag._text


def _cursor():
    cursor = QApplication.overrideCursor()
    return None if cursor is None else cursor.shape()


def _mark(d):
    mark = _lines_manager(d)._mark
    if mark is None or not mark.isVisible():
        return None
    return mark.geometry()


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    d.open(d.media.shapes / "phone.mp4", d.media.shapes / "square.mp4")
    d.wait_until(lambda: len(d.cells) == 2, "two cells")
    d.wait_until(
        lambda: all(cell.picture_shape for cell in d.cells), "shapes known", timeout=20
    )
    d.wait_until(lambda: not any(c.video_params.is_paused for c in d.cells), "playing")
    d.pump(0.5)

    d.check("side by side, even", _widths(d) == [350, 350], _widths(d))

    # over the line: the pointer turns, the line shows
    _mouse(d, "move", _at(d, 300))
    d.check("no line away from it", _cursor() is None and _mark(d) is None)

    _mouse(d, "move", _at(d, 348))
    d.check("resize pointer on it", _cursor() == Qt.SplitHCursor, _cursor())
    d.check("the line shown on hover", _mark(d) is not None, _mark(d))

    # dragged: the line shows, the cells go with it, live
    _mouse(d, "press", _at(d, 348))
    mark = _mark(d)
    d.check(
        "the line shown on it",
        mark is not None
        and mark.width() == 4
        and mark.height() == HEIGHT
        and mark.x() + mark.width() // 2 == _at(d, 350).x(),
        mark,
    )
    _mouse(d, "move", _at(d, 300))
    _mouse(d, "move", _at(d, 250))
    d.check("cells follow the line", _widths(d) == [250, 450], _widths(d))
    d.shot("1_dragged")

    # near where the phone video just fits, it snaps there
    _mouse(d, "move", _at(d, 174))
    d.check("snapped where the phone fits", _widths(d)[0] == 169, _widths(d))
    mark = _mark(d)
    d.check("snapped line thicker", mark is not None and mark.width() == 6, mark)
    d.check("says why: the video on the left fits", _tag(d) == "Left fits", _tag(d))
    d.shot("2_snapped")

    # Alt held: no snapping
    _mouse(d, "move", _at(d, 174), modifiers=Qt.AltModifier)
    d.check("with Alt where the pointer is", _widths(d)[0] == 174, _widths(d))
    d.check("with Alt nothing said", _tag(d) is None, _tag(d))

    # the cells even
    _mouse(d, "move", _at(d, 345))
    d.check("snapped even", _widths(d) == [350, 350], _widths(d))
    d.check("says why: even", _tag(d) == "Even", _tag(d))

    _mouse(d, "move", _at(d, 174))
    _mouse(d, "release", _at(d, 174))
    d.check("left where it was let go", _widths(d)[0] == 169, _widths(d))
    weights = d.ctx.grid_state.col_weights
    d.check("kept in the grid state", len(weights) == 2, weights)
    d.check(
        "no click: still playing",
        not any(c.video_params.is_paused for c in d.cells),
    )
    d.check(
        "no video moved",
        [c.video_params.uri.name for c in d.cells] == ["phone.mp4", "square.mp4"],
    )

    # Esc puts it back where it was pressed
    _mouse(d, "move", _at(d, 170))
    _mouse(d, "press", _at(d, 170))
    _mouse(d, "move", _at(d, 450))
    d.check("dragged again", _widths(d)[0] == 450, _widths(d))
    QTest.keyClick(d.player, Qt.Key_Escape)
    d.pump(0.2)
    d.check("Esc puts it back", _widths(d)[0] == 169, _widths(d))
    _mouse(d, "release", _at(d, 450))
    d.check("let go after Esc: no move", _widths(d)[0] == 169, _widths(d))
    d.check("no pointer left", _cursor() is None and _mark(d) is None)

    # the drag undone and done again, the one put back by Esc no change
    d.act(d.cells[0], "Undo Grid Change")
    d.check("drag undone", _widths(d) == [350, 350], _widths(d))
    d.act(d.cells[0], "Redo Grid Change")
    d.check("drag redone", _widths(d)[0] == 169, _widths(d))

    # a double click evens the lines out
    _mouse(d, "move", _at(d, 169))
    _mouse(d, "double", _at(d, 169))
    d.check("double click evens out", _widths(d) == [350, 350], _widths(d))
    d.act(d.cells[0], "Undo Grid Change")
    d.check("double click undone", _widths(d)[0] == 169, _widths(d))
    d.act(d.cells[0], "Redo Grid Change")
    d.check("not single mode", not d.ctx.is_single_mode)
    d.check(
        "no click: still playing",
        not any(c.video_params.is_paused for c in d.cells),
    )

    # from the menu
    cell = d.cells[0]
    d.act(cell, "Fit Lines to Videos")
    d.pump(0.3)
    d.check(
        "fit: the phone video just fits",
        abs(_widths(d)[0] - PHONE_FITS) <= 1,
        _widths(d),
    )
    d.shot("3_fitted")
    d.act(cell, "Reset Lines")
    d.pump(0.3)
    d.check("reset: even", _widths(d) == [350, 350], _widths(d))

    # snapping off
    d.act(cell, "Snap Lines")
    _mouse(d, "move", _at(d, 349))
    _mouse(d, "press", _at(d, 349))
    _mouse(d, "move", _at(d, 174))
    d.check("snapping off: where the pointer is", _widths(d)[0] == 174, _widths(d))
    d.check("snapping off: nothing said", _tag(d) is None, _tag(d))
    _mouse(d, "release", _at(d, 174))
    d.act(cell, "Snap Lines")
    d.act(cell, "Reset Lines")
    d.pump(0.3)

    # Fixed Grid: the cells, and the empty one, go with the line at once,
    # and the pointer finds it where it went
    d.ctx.commands.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=3, preallocate=True)
    )
    d.pump(0.5)
    d.check("fixed: three even", _widths(d) == [233, 234], _widths(d))
    _mouse(d, "move", _at(d, 467))
    _mouse(d, "press", _at(d, 467))
    _mouse(d, "move", _at(d, 600))
    _mouse(d, "release", _at(d, 600))
    d.check("fixed: moved at once", _widths(d) == [233, 367], _widths(d))
    _mouse(d, "move", _at(d, 300))
    _mouse(d, "move", _at(d, 599))
    d.check("fixed: found where it went", _cursor() == Qt.SplitHCursor, _cursor())
    _mouse(d, "move", _at(d, 300))

    # Fit Shapes lays the videos out by their shapes: no lines to move
    d.ctx.commands.set_grid_mode(GridMode.AUTO_SHAPES)
    d.pump(0.5)
    _mouse(d, "move", _at(d, 300))
    line = d.ctx.commands.grid_lines()
    d.check("no lines in Fit Shapes", line is None)
    actions = d.ctx.actions
    for name in ("Fit Lines to Videos", "Reset Lines", "Snap Lines", "Link Rows"):
        actions[name].adapt()
        d.check(f"{name} hidden in Fit Shapes", actions[name].is_skipped)

    # Fill Gaps: three videos over two, the two with lines of their own
    for name in ("c.mp4", "d.mp4", "e.mp4"):
        shutil.copy(d.media.shapes / "square.mp4", d.out / name)
    d.open(*(d.out / name for name in ("c.mp4", "d.mp4", "e.mp4")))
    d.wait_until(lambda: len(d.cells) == 5, "five cells")
    d.ctx.commands.apply_grid_config(
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, is_match_shapes=False, size=3)
    )
    d.ctx.commands.reset_grid_lines()
    d.pump(0.5)
    d.check(
        "fill gaps: three over two",
        _row_widths(d, True) == [233, 234, 233] and _row_widths(d, False) == [350, 350],
        (_row_widths(d, True), _row_widths(d, False)),
    )

    top, bottom = HEIGHT // 4, HEIGHT * 3 // 4
    _mouse(d, "move", _at(d, 233, top))
    _mouse(d, "press", _at(d, 233, top))
    _mouse(d, "move", _at(d, 150, top))
    _mouse(d, "release", _at(d, 150, top))
    d.check(
        "a column moved: the short row stays",
        _row_widths(d, True)[0] == 150 and _row_widths(d, False) == [350, 350],
        (_row_widths(d, True), _row_widths(d, False)),
    )

    _mouse(d, "move", _at(d, 300, bottom))
    _mouse(d, "move", _at(d, 233, bottom))
    d.check("no column line in the short row", _cursor() is None, _cursor())
    _mouse(d, "move", _at(d, 351, bottom))
    d.check("the short row's own line", _cursor() == Qt.SplitHCursor, _cursor())
    _mouse(d, "press", _at(d, 351, bottom))
    _mouse(d, "move", _at(d, 250, bottom))
    _mouse(d, "release", _at(d, 250, bottom))
    d.check(
        "its line moved: the columns stay",
        _row_widths(d, False) == [250, 450] and _row_widths(d, True)[0] == 150,
        (_row_widths(d, True), _row_widths(d, False)),
    )
    d.check("kept", d.ctx.grid_state.line_weights != [], d.ctx.grid_state)

    # shown on hover, gone once the pointer leaves, and not once turned off
    _mouse(d, "move", _at(d, 300, bottom))
    _mouse(d, "move", _at(d, 251, bottom))
    mark = _mark(d)
    d.check("shown on hover", mark is not None and mark.width() == 4, mark)
    QApplication.sendEvent(d.player.windowHandle(), QEvent(QEvent.Leave))
    d.pump(0.4)
    d.check("gone once the pointer leaves", _mark(d) is None, _mark(d))
    d.check("its pointer too", _cursor() is None, _cursor())
    d.act(d.cells[0], "Show Grid Lines")
    _mouse(d, "move", _at(d, 251, bottom))
    d.check("not shown on hover once off", _mark(d) is None, _mark(d))
    d.check("its pointer still", _cursor() == Qt.SplitHCursor, _cursor())
    _mouse(d, "move", _at(d, 300, bottom))
    d.act(d.cells[0], "Show Grid Lines")

    # a sixth video fills the row: both rows have the columns
    shutil.copy(d.media.shapes / "square.mp4", d.out / "f.mp4")
    d.open(d.out / "f.mp4")
    d.wait_until(lambda: len(d.cells) == 6, "six cells")
    d.pump(0.5)
    columns = _row_widths(d, True)
    d.check(
        "full rows in the columns",
        columns[0] == 150 and _row_widths(d, False) == columns,
        (columns, _row_widths(d, False)),
    )

    # Link Rows off: nothing moves, until a row's line is moved
    d.act(d.cells[0], "Link Rows")
    d.pump(0.3)
    d.check("not linked", not d.ctx.grid_state.is_linked, d.ctx.grid_state)
    d.check(
        "unlinked: nothing moved",
        _row_widths(d, True) == columns and _row_widths(d, False) == columns,
        (_row_widths(d, True), _row_widths(d, False)),
    )

    _mouse(d, "move", _at(d, 150, top))
    _mouse(d, "press", _at(d, 150, top))
    _mouse(d, "move", _at(d, 110, top))
    d.check(
        "the top row's line alone",
        _row_widths(d, True)[0] == 110 and _row_widths(d, False) == columns,
        (_row_widths(d, True), _row_widths(d, False)),
    )
    mark = _mark(d)
    d.check(
        "its line over the top row only",
        mark is not None and mark.height() == HEIGHT // 2,
        mark,
    )
    d.shot("4_unlinked")

    # back near the bottom row's line: in line with it
    _mouse(d, "move", _at(d, 155, top))
    d.check("snapped in line", _row_widths(d, True) == columns, _row_widths(d, True))
    d.check("says why: aligned", _tag(d) == "Aligned", _tag(d))
    _mouse(d, "move", _at(d, 110, top))
    _mouse(d, "release", _at(d, 110, top))

    # Link Rows on: the rows' lines where they are on average
    d.act(d.cells[0], "Link Rows")
    d.pump(0.3)
    d.check("linked", d.ctx.grid_state.is_linked, d.ctx.grid_state)
    d.check("own lines gone", d.ctx.grid_state.line_weights == [], d.ctx.grid_state)
    d.check(
        "linked: on average",
        _row_widths(d, True)[0] == 130
        and _row_widths(d, False) == _row_widths(d, True),
        (_row_widths(d, True), _row_widths(d, False)),
    )

    # its name goes by the way the videos are laid out
    link = d.ctx.actions["Link Rows"]
    link.adapt()
    d.check("named for rows", link.text() == "Link Rows", link.text())
    d.ctx.commands.set_grid_mode(GridMode.AUTO_COLS)
    d.pump(0.3)
    link.adapt()
    d.check("named for columns", link.text() == "Link Columns", link.text())
