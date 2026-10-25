"""Single Mode with the Fixed Strip: every video keeps its place in the
strip, the one shown big too, its place held and marked. A double click on
one in the strip shows it big, the held place going with it; one on the
held place leaves Single Mode, as one on the big video does. The Strip
menu item switches to the strip whose videos trade places. The Strip
Mode submenu is there in Single Mode only; its Off takes the strip away,
its Left puts it on the left.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtTest import QTest

from gridplayer.params.static import StripMode

# a window twice as wide as tall: the 16:9 videos' strip, at a quarter of
# the height a video, is 100 * 16 / 9 = 178 wide; its three tiles, 100 high,
# in the middle of its length
WIDTH, HEIGHT = 800, 400
STRIP_LINE = WIDTH - 178
TILE_TOPS = [50, 150, 250]


def _big(d):
    return d.ctx.commands.single_mode_video()


def _held(d):
    return d.player._managers_inst["grid"]._held_place


def _box(widget):
    g = widget.geometry()
    return g.x(), g.y(), g.width(), g.height()


def _double_click(d, widget):
    pos = widget.mapToGlobal(widget.rect().center())
    QCursor.setPos(pos)
    window = d.player.windowHandle()
    local = window.mapFromGlobal(pos)
    QTest.mouseMove(window, local)
    d.pump(0.15)
    QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, local)
    d.pump(0.3)


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.picture_shape for c in d.cells), "shapes known")

    d.check(
        "no strip items in the grid's menu",
        not d.ctx.actions["Single Mode Fixed Strip"].show_if()
        and not d.ctx.actions["Strip Side Left"].show_if(),
    )

    d.act(d.cells[0], "Single Mode ON / OFF")
    d.pump(0.5)
    d.check("single mode", d.ctx.is_single_mode)
    d.check(
        "the strip items in Single Mode's",
        d.ctx.actions["Single Mode Fixed Strip"].show_if(),
    )
    d.check(
        "the sides greyed out with no strip",
        not d.ctx.actions["Strip Side Left"].is_enabled,
    )

    d.act(d.cells[0], "Single Mode Fixed Strip")
    d.pump(0.5)
    d.check(
        "fixed strip on",
        d.ctx.commands.is_single_mode_strip_set_to(StripMode.FIXED),
    )
    d.check("the first big", _box(d.cells[0]) == (0, 0, STRIP_LINE, HEIGHT))
    d.check(
        "its place held first in the strip, the others after it",
        _held(d).isVisible()
        and [_box(_held(d))[1], _box(d.cells[1])[1], _box(d.cells[2])[1]] == TILE_TOPS
        and all(_box(w)[0] == STRIP_LINE for w in (_held(d), d.cells[1], d.cells[2])),
        [_box(_held(d)), _box(d.cells[1]), _box(d.cells[2])],
    )
    d.shot("1_fixed")

    # a double click on the third: it is big, its place held
    third = _box(d.cells[2])
    _double_click(d, d.cells[2])
    d.check("the third big", _big(d) is d.cells[2])
    d.check("the held place where the third was", _box(_held(d)) == third)
    d.check(
        "the first back in its own place",
        _box(d.cells[0])[1] == TILE_TOPS[0],
        _box(d.cells[0]),
    )
    d.check("the second where it was", _box(d.cells[1])[1] == TILE_TOPS[1])
    d.shot("2_third_big")

    # the Strip instead: the held place gone, the third's tile the first's
    d.act(d.cells[2], "Single Mode Strip")
    d.pump(0.3)
    d.check("the strip on", d.ctx.commands.is_single_mode_strip_set_to(StripMode.SWAP))
    d.check("no held place", not _held(d).isVisible())
    d.act(d.cells[2], "Single Mode Fixed Strip")
    d.pump(0.3)
    d.check("the fixed strip again", _held(d).isVisible())

    # off, and back
    d.act(d.cells[2], "Single Mode Strip Off")
    d.pump(0.3)
    d.check(
        "off: only the big one",
        not _held(d).isVisible()
        and [c.isVisible() for c in d.cells] == [False, False, True],
        [c.isVisible() for c in d.cells],
    )
    d.act(d.cells[2], "Single Mode Fixed Strip")
    d.pump(0.3)

    # on the left
    d.act(d.cells[2], "Strip Side Left")
    d.pump(0.3)
    d.check(
        "the big one on the right",
        _box(d.cells[2]) == (WIDTH - STRIP_LINE, 0, STRIP_LINE, HEIGHT),
        _box(d.cells[2]),
    )
    d.check(
        "the strip on the left",
        all(_box(w)[0] == 0 for w in (d.cells[0], d.cells[1], _held(d))),
        [_box(w) for w in (d.cells[0], d.cells[1], _held(d))],
    )
    d.shot("3_left")

    # a double click on the held place: out of Single Mode
    _double_click(d, _held(d))
    d.check("single mode left", not d.ctx.is_single_mode)
    d.check("no held place after", not _held(d).isVisible())
    d.check("all in sight", all(c.isVisible() for c in d.cells))
