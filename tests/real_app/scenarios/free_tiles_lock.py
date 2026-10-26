"""Free Tiles, Lock Tile: a locked tile is neither moved nor sized by
hand, its edges give no resize pointer, and the others stop at it, even
with Tile Overlap on, or pushing aside, a lock shown on it while one
is moved. It is in front of the others. Arrange Tiles leaves it where it
is, the others laid out beside it; Fit Tiles to Window makes it bigger
with them.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDrag

from gridplayer.params.static import TileOverlap
from tests.real_app.scenarios.free_tiles import (
    HEIGHT,
    WIDTH,
    _at,
    _by_name,
    _cursor,
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

    grid = d.player._managers_inst["grid"]
    a, b = _by_name(d, "a.mp4"), _by_name(d, "b.mp4")

    d.act(b, "Lock Tile")
    d.pump(0.2)
    d.check("b locked", grid._free.locked == {b.video_id}, grid._free.locked)
    d.check("b in front", list(grid._free.tiles)[-1] == b.video_id, None)

    # its edge: no resize pointer
    _mouse(d, "move", _at(d, 459, 70))
    d.pump(0.2)
    d.check("no resize pointer on b's edge", _cursor() is None, _cursor())

    # its middle dragged: it stays
    _drag(d, _at(d, 360, 70), _at(d, 400, 200))
    d.check("b stayed", _near(_rects(d)["b.mp4"], B), _rects(d)["b.mp4"])

    # another held: a lock on b, and only while it is
    badges = d.player._managers_inst["free_tiles"]._locks._badges
    _drag(d, _at(d, 120, 250), _at(d, 160, 250), release=False)
    shown = [x.geometry() for x in badges if x.isVisible()]
    b_middle = _at(d, 360, 70)
    d.check(
        "a lock on b while c is moved",
        len(shown) == 1 and shown[0].contains(b_middle),
        shown,
    )
    d.shot("0_lock_shown")
    _mouse(d, "release", _at(d, 160, 250))
    d.pump(0.2)
    d.check("no lock once let go", not any(x.isVisible() for x in badges), None)
    _set(d, "c.mp4", C)

    for overlap in TileOverlap:
        d.ctx.commands.set_tile_overlap(overlap)
        _set(d, "a.mp4", A)
        _drag(d, _at(d, 120, 70), _at(d, 260, 70))
        rects = _rects(d)
        d.check(
            f"a stopped at b ({overlap.name})",
            _near(rects["a.mp4"], (60, 20, 260, 120)) and _near(rects["b.mp4"], B),
            rects,
        )
    d.shot("1_stopped")

    d.act(a, "Arrange Tiles")
    d.pump(0.3)
    rects = _rects(d)
    d.check("b stayed when arranged", _near(rects["b.mp4"], B), rects["b.mp4"])
    d.check("arranged with none over another", not _overlapping(rects), rects)
    d.shot("2_arranged")
    d.act(a, "Undo Grid Change")
    d.pump(0.2)
    d.act(a, "Fit Tiles to Window")
    d.pump(0.3)
    rects = _rects(d)
    d.check(
        "b bigger with the others",
        rects["b.mp4"].width > 210 and not _overlapping(rects),
        rects,
    )

    d.act(b, "Lock Tile")
    d.pump(0.2)
    d.check("b let go of", grid._free.locked == set(), grid._free.locked)
