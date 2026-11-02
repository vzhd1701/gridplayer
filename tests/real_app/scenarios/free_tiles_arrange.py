"""Arrange around a locked tile in the middle, in the real app: the others
go on both sides of it, cut no more than the Crop Limit; Crop Limit Off
keeps their shapes; set from its menu item, it arranges them again."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDrag

from tests.real_app.scenarios.free_tiles import (
    HEIGHT,
    WIDTH,
    _by_name,
    _near,
    _overlapping,
    _rects,
    _set,
)

MIDDLE = (250, 100, 450, 300)


def _cut(rect, shape):
    stretch = (rect.width / rect.height) / shape
    return 1 - min(stretch, 1 / stretch)


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
    grid = d.player._managers_inst["grid"]
    d.check("crop limit 20% by default", grid._tile_crop == 20, grid._tile_crop)

    a, b = _by_name(d, "a.mp4"), _by_name(d, "b.mp4")
    _set(d, "a.mp4", MIDDLE)
    _set(d, "b.mp4", (0, 0, 100, 60))
    _set(d, "c.mp4", (600, 340, 700, 400))
    d.act(a, "Lock Tile")
    d.pump(0.2)
    d.shot("0_before")

    d.act(b, "Arrange Tiles")
    d.pump(0.3)
    rects = _rects(d)
    shapes = {c.video_params.uri.name: c.picture_shape for c in d.cells}
    d.check("a stayed", _near(rects["a.mp4"], MIDDLE), rects["a.mp4"])
    d.check("none over another", not _overlapping(rects), rects)
    sides = {
        name: "left"
        if r.right <= MIDDLE[0] + 1
        else "right"
        if r.left >= MIDDLE[2] - 1
        else "other"
        for name, r in rects.items()
        if name != "a.mp4"
    }
    d.check("one on each side of a", sorted(sides.values()) == ["left", "right"], sides)
    cuts = {n: round(_cut(r, shapes[n]), 3) for n, r in rects.items() if n != "a.mp4"}
    d.check("cut no more than 20%", all(c <= 0.2 + 1e-3 for c in cuts.values()), cuts)
    d.shot("1_arranged_20")

    d.act(b, "Tile Crop 0%")
    d.pump(0.3)
    rects = _rects(d)
    cuts = {n: round(_cut(r, shapes[n]), 3) for n, r in rects.items() if n != "a.mp4"}
    d.check(
        "Off: arranged again, shapes kept", all(c < 0.01 for c in cuts.values()), cuts
    )
    d.check("Off: a stayed", _near(rects["a.mp4"], MIDDLE), rects["a.mp4"])
    d.shot("2_arranged_off")

    d.act(b, "Undo Grid Change")
    d.pump(0.3)
    d.check("undone to 20%", grid._tile_crop == 20, grid._tile_crop)
