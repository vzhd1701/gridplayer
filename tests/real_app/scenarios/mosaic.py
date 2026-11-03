"""Mosaic in the real app: chosen, the tiles are arranged. A tile
dragged by the mouse, or sized by its edge, goes where the pointer takes
it, the others filling the room around it as it goes; let go, it stays
there, the others as they were shown, and Undo takes it all back."""

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QDrag

from gridplayer.params.menu import SUBMENUS
from tests.real_app.scenarios.free_tiles import (
    HEIGHT,
    WIDTH,
    _at,
    _drag,
    _mouse,
    _near,
    _overlapping,
    _rects,
)


def _area(rect) -> float:
    return rect.width * rect.height


def _held_and_let_go(d, name, start, end, label):
    """A tile dragged from start to end and held, then let go: the others
    make room for it as it goes, and stay so."""

    before = _rects(d)
    _drag(d, start, end, release=False)
    d.pump(0.3)
    shown = _rects(d)
    d.check(
        f"{label}: while held, the others moved",
        any(not _near(r, before[n], slack=1) for n, r in shown.items() if n != name),
        (before, shown),
    )
    d.check(f"{label}: while held, none over another", not _overlapping(shown), shown)
    d.shot(f"{label}_held")

    _mouse(d, "release", end)
    d.pump(0.3)
    let_go = _rects(d)
    d.check(
        f"{label}: let go, all as shown",
        all(_near(let_go[n], r, slack=1) for n, r in shown.items()),
        (shown, let_go),
    )
    d.shot(f"{label}_let_go")
    return before, let_go


def scenario(d):
    QDrag.exec = lambda _drag, *_args: Qt.IgnoreAction

    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.picture_shape for c in d.cells), "shapes known")
    d.pump(0.5)

    d.act(d.cells[0], "Mosaic")
    d.pump(0.3)
    grid = d.player._managers_inst["grid"]
    d.check("Mosaic", grid._is_mosaic)

    # its menu: what is Free Tiles' alone not there
    actions = d.ctx.actions

    def shown(name):
        action = actions[name]
        return action.show_if is None or bool(action.show_if())

    there = [
        "Lock Tile",
        "Arrange Reorder to Fit",
        "Tile Crop 20%",
        "Snap to Window Edges",
    ]
    gone = [
        "Make Cell Bigger",
        "Reset Sizes",
        "Arrange Tiles",
        "Fit Tiles to Window",
        "Tile Overlap On",
        "Fill Space",
        "Fit Lines to Videos",
        "Reset Lines",
    ]
    d.check("in the menu", all(map(shown, there)), {n: shown(n) for n in there})
    d.check("not in the menu", not any(map(shown, gone)), {n: shown(n) for n in gone})
    # Reorder to Fit and Crop Limit in the Grid menu itself
    inline_if = SUBMENUS["Arrange"]["inline_if"]
    d.check("Arrange put in the menu", d.ctx.commands.resolve(inline_if)())
    d.check("none over another", not _overlapping(_rects(d)), _rects(d))
    d.shot("0_arranged")

    # each video's own buttons: only its lock
    overlay = d.cells[0].overlay
    d.check(
        "only the lock on the video",
        not overlay._cell_size_wanted
        and overlay._tile_buttons_wanted
        and not overlay._fill_buttons_wanted,
        (
            overlay._cell_size_wanted,
            overlay._tile_buttons_wanted,
            overlay._fill_buttons_wanted,
        ),
    )

    # a, by its middle, toward the bottom right corner
    a = _rects(d)["a.mp4"]
    start = _at(d, a.center_x, a.center_y)
    _, moved = _held_and_let_go(d, "a.mp4", start, start + QPoint(120, 80), "1_moved")
    d.check("a moved", moved["a.mp4"].left > a.left, (a, moved["a.mp4"]))

    # b made bigger by its left edge
    b = moved["b.mp4"]
    edge = _at(d, b.left + 1, b.center_y)
    before, sized = _held_and_let_go(d, "b.mp4", edge, edge - QPoint(120, 0), "2_sized")
    d.check("b bigger", _area(sized["b.mp4"]) > 1.2 * _area(b), (b, sized["b.mp4"]))

    d.act(d.cells[0], "Undo Grid Change")
    d.pump(0.3)
    undone = _rects(d)
    d.check(
        "undone: as before the sizing",
        all(_near(undone[n], r, slack=1) for n, r in before.items()),
        (before, undone),
    )

    # the window made narrower: arranged for it at once, not once done
    d.player.resize(WIDTH - 150, HEIGHT)
    d.pump(0.05)
    rects = _rects(d)
    width = d.ctx.commands.free_page().rect.width()
    d.check(
        "resized: arranged at once",
        grid._arranged_at == grid._area_size() and not _overlapping(rects),
        (grid._arranged_at, grid._area_size(), rects),
    )
    d.check(
        "resized: all in the window",
        all(r.right <= width + 0.5 for r in rects.values()),
        (width, rects),
    )
    d.shot("3_resized")
