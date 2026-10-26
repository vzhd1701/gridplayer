"""Free Tiles, Tile Overlap: Push Aside. A tile dragged onto another makes
it smaller in its own place, keeping its shape, and it comes back as the
tile goes away; over too much of it, it goes where there is room. Esc puts
them all back with nothing to undo; let go of, the drag is one change to
undo. Make Room sets aside the tiles one is over.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDrag
from PyQt5.QtTest import QTest

from gridplayer.params.static import TileOverlap
from tests.real_app.scenarios.free_tiles import (
    HEIGHT,
    WIDTH,
    _at,
    _by_name,
    _drag,
    _mouse,
    _near,
    _overlapping,
    _rects,
    _set,
)

A = (20, 20, 220, 120)
B = (260, 20, 460, 120)
C = (20, 200, 220, 300)


def _is_inside(rect, spot) -> bool:
    return (
        rect.left >= spot[0] - 0.5
        and rect.top >= spot[1] - 0.5
        and rect.right <= spot[2] + 0.5
        and rect.bottom <= spot[3] + 0.5
    )


def _shape(rect) -> float:
    return rect.width / rect.height


def scenario(d):
    QDrag.exec = lambda _drag, *_args: Qt.IgnoreAction

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

    a = _by_name(d, "a.mp4")
    d.act(a, "Tile Overlap Push")
    d.pump(0.2)
    d.check(
        "Push Aside on",
        d.ctx.commands.tile_overlap() == TileOverlap.PUSH,
        d.ctx.commands.tile_overlap(),
    )

    # a dragged by its middle onto b, held: b smaller in its own place
    _drag(d, _at(d, 120, 70), _at(d, 220, 70), release=False)
    rects = _rects(d)
    b_rect = rects["b.mp4"]
    d.check("a went onto b's place", rects["a.mp4"].right > B[0], rects["a.mp4"])
    d.check("none over another", not _overlapping(rects), rects)
    d.check(
        "b smaller in its place, of its shape",
        b_rect.width < 199
        and _is_inside(b_rect, B)
        and _near((_shape(b_rect),), (2,), 0.05),
        b_rect,
    )
    d.shot("1_pushed")

    # back again, still held: b as it was
    _mouse(d, "move", _at(d, 125, 70))
    _mouse(d, "move", _at(d, 120, 70))
    d.pump(0.1)
    d.check("b back as a goes away", _near(_rects(d)["b.mp4"], B), _rects(d)["b.mp4"])

    # Esc: all back, nothing to undo
    undo = d.player._managers_inst["grid"]._undo
    undone = len(undo)
    _mouse(d, "move", _at(d, 220, 70))
    QTest.keyClick(d.player.windowHandle(), Qt.Key_Escape)
    d.pump(0.2)
    _mouse(d, "release", _at(d, 220, 70))
    d.pump(0.2)
    rects = _rects(d)
    d.check(
        "Esc put them back",
        _near(rects["a.mp4"], A) and _near(rects["b.mp4"], B),
        rects,
    )
    d.check("nothing to undo from Esc", len(undo) == undone, len(undo))

    # over most of b: b goes where there is room, as big as it was
    _drag(d, _at(d, 120, 70), _at(d, 320, 70))
    rects = _rects(d)
    b_rect = rects["b.mp4"]
    d.check("none over another once let go", not _overlapping(rects), rects)
    d.check(
        "b gone where there is room",
        not _is_inside(b_rect, B) and _near((b_rect.width,), (200,)),
        b_rect,
    )
    d.shot("2_jumped")
    d.act(a, "Undo Grid Change")
    d.pump(0.2)
    rects = _rects(d)
    d.check(
        "one change undone",
        _near(rects["a.mp4"], A) and _near(rects["b.mp4"], B),
        rects,
    )

    # Make Room: a put over b, b set aside
    d.ctx.commands.set_tile_overlap(TileOverlap.ON)
    _set(d, "a.mp4", (100, 20, 300, 120))
    d.act(a, "Make Room")
    d.pump(0.2)
    rects = _rects(d)
    d.check("Make Room left none over another", not _overlapping(rects), rects)
    d.check("a stayed", _near(rects["a.mp4"], (100, 20, 300, 120)), rects["a.mp4"])
    d.check("b in its place", _is_inside(rects["b.mp4"], B), rects["b.mp4"])
    d.shot("3_made_room")
