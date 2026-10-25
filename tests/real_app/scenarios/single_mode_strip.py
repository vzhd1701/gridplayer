"""Single Mode with the strip on: the video shown big, the others small in
a strip on the right, still playing. Strip, in Single Mode, turns it on.
Shown big, by the menu and by a double click on it, one of the strip takes
the big place; Next Video does too. The line between the big video and
the strip is dragged as the grid's are, snapping where the big video just
fits, and Undo takes it back. Leaving Single Mode puts the grid back.
"""

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import StripMode

# a window twice as wide as tall: the 16:9 videos' strip, at a quarter of
# the height a video, is 100 * 16 / 9 = 178 wide, and the big one just
# fits at 400 * 16 / 9 = 711
WIDTH, HEIGHT = 800, 400
STRIP_LINE = WIDTH - 178
MAIN_FITS = 711


def _big(d):
    return d.ctx.commands.single_mode_video()


def _boxes(d):
    return [
        (
            c.geometry().x(),
            c.geometry().y(),
            c.geometry().width(),
            c.geometry().height(),
        )
        for c in d.cells
    ]


def _at(d, x, y=HEIGHT // 2) -> QPoint:
    return d.ctx.commands.grid_area().topLeft() + QPoint(x, y)


def _mouse(d, kind, pos):
    QCursor.setPos(pos)
    window = d.player.windowHandle()
    local = window.mapFromGlobal(pos)
    if kind == "move":
        QTest.mouseMove(window, local)
    elif kind == "press":
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, local)
    elif kind == "release":
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, local)
    elif kind == "double":
        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, local)
    d.pump(0.15)


def _tag(d):
    tag = d.player._managers_inst["grid_lines"]._tag
    if tag is None or not tag.isVisible():
        return None
    return tag._text


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.picture_shape for c in d.cells), "shapes known")
    d.wait_until(lambda: not any(c.video_params.is_paused for c in d.cells), "playing")
    in_grid = _boxes(d)

    d.act(d.cells[0], "Single Mode ON / OFF")
    d.pump(0.5)
    d.check("single mode", d.ctx.is_single_mode)

    d.act(d.cells[0], "Single Mode Strip")
    d.pump(0.5)
    d.check("strip on", d.ctx.commands.is_single_mode_strip_set_to(StripMode.SWAP))
    d.check("all in sight", all(c.isVisible() for c in d.cells))
    boxes = _boxes(d)
    d.check("the first big", boxes[0] == (0, 0, STRIP_LINE, HEIGHT), boxes)
    d.check(
        "the others in the strip, a quarter of the height each",
        [b[0] for b in boxes[1:]] == [STRIP_LINE] * 2
        and [b[3] for b in boxes[1:]] == [100, 100],
        boxes,
    )
    d.check(
        "the strip keeps playing",
        not any(c.video_params.is_paused for c in d.cells),
    )
    d.shot("1_strip")

    # shown big from its menu
    d.ctx.active_block = d.cells[2]
    d.check(
        "the menu offers to show the strip's one big (Enter Single Mode)",
        not d.ctx.commands.is_single_video_big(),
    )
    d.act(d.cells[2], "Single Mode ON / OFF")
    d.pump(0.3)
    d.check("the third big", _big(d) is d.cells[2], _boxes(d))
    d.check("still single mode", d.ctx.is_single_mode)
    d.check("the third on the left", d.cells[2].geometry().x() == 0, _boxes(d))

    # Next Video: the one after it, round to the first
    d.act(d.cells[2], "Next Video")
    d.pump(0.3)
    d.check("next is the first", _big(d) is d.cells[0], _boxes(d))

    # a double click on one in the strip
    second = d.cells[1].geometry()
    _mouse(d, "move", d.cells[1].mapToGlobal(second.center() - second.topLeft()))
    _mouse(d, "double", d.cells[1].mapToGlobal(second.center() - second.topLeft()))
    d.pump(0.3)
    d.check("a double click shows it big", _big(d) is d.cells[1], _boxes(d))
    d.check("still single mode after it", d.ctx.is_single_mode)
    d.shot("2_swapped")

    # the strip's line dragged, snapping where the big one fits
    _mouse(d, "move", _at(d, STRIP_LINE - 1))
    d.check(
        "resize pointer on the strip's line",
        QApplication.overrideCursor() is not None
        and QApplication.overrideCursor().shape() == Qt.SplitHCursor,
    )
    _mouse(d, "press", _at(d, STRIP_LINE - 1))
    _mouse(d, "move", _at(d, 680))
    _mouse(d, "move", _at(d, MAIN_FITS - 5))
    d.check(
        "snapped where the big one fits",
        d.cells[1].geometry().width() == MAIN_FITS,
        _boxes(d),
    )
    d.check("says so", _tag(d) == "Left fits", _tag(d))
    _mouse(d, "release", _at(d, MAIN_FITS - 5))
    d.check(
        "kept in the grid state",
        d.ctx.grid_state.strip_share is not None,
        d.ctx.grid_state.strip_share,
    )
    d.check("still single mode after the drag", d.ctx.is_single_mode)
    d.shot("3_moved")

    d.act(d.cells[1], "Undo Grid Change")
    d.pump(0.3)
    d.check(
        "undone",
        d.cells[1].geometry().width() == STRIP_LINE
        and d.ctx.grid_state.strip_share is None,
        _boxes(d),
    )

    d.act(d.cells[1], "Single Mode ON / OFF")
    d.pump(0.5)
    d.check("single mode left", not d.ctx.is_single_mode)
    d.check("the grid as it was", _boxes(d) == in_grid, _boxes(d))
