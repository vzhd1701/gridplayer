"""Free Tiles, Tile Overlap: On. A tile dragged onto another goes
over it, in front of it, and pointing there points at it; Send to Back
puts it behind, Undo in front again. Near a tile's edge its frame shows
its outline and the edge lit; while it is sized, dashed where it started
too, none of it once let go, and no overlay shown while it is held. Ctrl+Click puts a tile in front,
Ctrl+Shift+Click behind. Overlap off, a tile over another moves as
it likes until it is clear of it, and then stops at its edge. Closed and
opened again, a tile is where it was, as deep among the others.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDrag

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


def _order(d) -> list[str]:
    tiles = d.player._managers_inst["grid"]._free.tiles
    return [d.ctx.video_blocks.by_video_id(i).video_params.uri.name for i in tiles]


def _is_over(d, one, other) -> bool:
    return {one, other} in [set(pair) for pair in _overlapping(_rects(d))]


def _shown(lines) -> int:
    return sum(1 for line in lines if line.isVisible())


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
    _set(d, "a.mp4", (20, 20, 260, 155))
    _set(d, "b.mp4", (300, 20, 540, 155))
    _set(d, "c.mp4", (20, 200, 260, 335))

    a, b = _by_name(d, "a.mp4"), _by_name(d, "b.mp4")
    actions = d.ctx.actions
    actions["Bring to Front"].adapt()
    d.check("no stacking with Stop", actions["Bring to Front"].is_skipped)

    d.act(a, "Tile Overlap On")
    d.pump(0.2)
    d.check(
        "Tile Overlap on",
        d.ctx.commands.tile_overlap() == TileOverlap.ON,
        d.ctx.commands.tile_overlap(),
    )
    actions["Bring to Front"].adapt()
    d.check("stacking in the menu", not actions["Bring to Front"].is_skipped)

    # near a's right edge: its frame, the edge lit
    frame = d.player._managers_inst["free_tiles"]._frame
    _mouse(d, "move", _at(d, 259, 90))
    d.pump(0.1)
    d.check("outline shown", _shown(frame._outline) == 4, _shown(frame._outline))
    d.check("its edge lit", _shown(frame._lit) == 1, _shown(frame._lit))
    d.check("nothing dashed yet", _shown(frame._dashed) == 0)

    # b sized by its left edge over a: dashed where it started while held
    _set(d, "b.mp4", (300, 20, 540, 155))
    d.ctx.commands.set_tile_overlap(TileOverlap.ON)
    _drag(d, _at(d, 301, 90), _at(d, 200, 90), release=False)
    d.check("dashed while sized", _shown(frame._dashed) == 4, _shown(frame._dashed))
    shown = [c.video_params.uri.name for c in d.cells if c.overlay.is_shown]
    d.check("no overlay shown while sized", not shown, shown)
    d.shot("1_sizing_over")
    _mouse(d, "release", _at(d, 200, 90))
    d.pump(0.2)
    b_rect = _rects(d)["b.mp4"]
    d.check("b over a", _is_over(d, "a.mp4", "b.mp4"), b_rect)
    d.check(
        "b in front of a",
        _order(d).index("b.mp4") > _order(d).index("a.mp4"),
        _order(d),
    )
    d.check("no dashes once let go", _shown(frame._dashed) == 0)
    d.check("its overlay back once let go", b.overlay.is_shown)

    # a dragged by its middle over b: in front of it, pointed at there
    _drag(d, _at(d, 100, 90), _at(d, 160, 110))
    rects = _rects(d)
    d.check("a over b", _is_over(d, "a.mp4", "b.mp4"), rects)
    d.check("a in front", _order(d)[-1] == "a.mp4", _order(d))
    both = rects["a.mp4"].right - 5, rects["a.mp4"].center_y
    point = _at(d, *both)
    d.check("a pointed at", d.ctx.commands.get_cell_at(point) is a)
    d.shot("2_over")

    # Send to Back, and undone
    d.act(a, "Send to Back")
    d.pump(0.2)
    d.check("a behind", _order(d)[0] == "a.mp4", _order(d))
    d.check("b pointed at", d.ctx.commands.get_cell_at(point) is b)
    d.shot("3_behind")
    d.act(a, "Undo Grid Change")
    d.pump(0.2)
    d.check("a in front again", _order(d)[-1] == "a.mp4", _order(d))

    # Ctrl+Click on b's own part puts it in front, Ctrl+Shift+Click behind
    _set(d, "a.mp4", (20, 20, 260, 155))
    _set(d, "b.mp4", (200, 60, 440, 195))
    d.act(a, "Bring to Front")
    d.pump(0.2)
    own = _at(d, 400, 150)
    _mouse(d, "move", own)
    _mouse(d, "press", own, Qt.ControlModifier)
    _mouse(d, "release", own, Qt.ControlModifier)
    d.pump(0.2)
    d.check("Ctrl+Click put b in front", _order(d)[-1] == "b.mp4", _order(d))
    d.check("b still playing", not b.video_params.is_paused)
    modifiers = Qt.ControlModifier | Qt.ShiftModifier
    _mouse(d, "press", own, modifiers)
    _mouse(d, "release", own, modifiers)
    d.pump(0.2)
    d.check("Ctrl+Shift+Click put b behind", _order(d)[0] == "b.mp4", _order(d))

    # Stop: b, behind a, moves as it likes until it is clear of it, then
    # stops at its edge
    _set(d, "a.mp4", (20, 20, 260, 155))
    _set(d, "b.mp4", (200, 60, 440, 195))
    d.ctx.commands.set_tile_overlap(TileOverlap.OFF)
    _drag(d, _at(d, 400, 150), _at(d, 650, 150), steps=16)
    b_rect = _rects(d)["b.mp4"]
    d.check("b clear of a", not _overlapping(_rects(d)), _rects(d))
    _drag(d, _at(d, 650, 150), _at(d, 300, 150), steps=16)
    b_rect = _rects(d)["b.mp4"]
    d.check(
        "b stopped at a",
        not _overlapping(_rects(d)) and _near((b_rect.left,), (260,)),
        b_rect,
    )

    # closed over another and opened again: where it was, as deep
    d.ctx.commands.set_tile_overlap(TileOverlap.ON)
    _set(d, "b.mp4", (200, 60, 440, 195))
    d.act(b, "Send to Back")
    d.pump(0.2)
    rect, order = _rects(d)["b.mp4"], _order(d)
    d.act(b, "Close")
    d.wait_until(lambda: len(d.cells) == 2, "b closed")
    d.act(d.cells[0], "Reopen Closed Video")
    d.wait_until(lambda: len(d.cells) == 3, "b opened again")
    d.pump(0.3)
    d.check(
        "b back where it was, as deep",
        _near(_rects(d)["b.mp4"], rect) and _order(d) == order,
        (_rects(d)["b.mp4"], _order(d)),
    )
