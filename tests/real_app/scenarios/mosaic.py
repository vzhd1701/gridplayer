"""Mosaic in the real app: chosen, the tiles are arranged. A tile
dragged by the mouse, or sized by its edge, goes where the pointer takes
it, the others making room around where it would land, sliding there; let
go, it lands there, the others as they were shown, and Undo takes it all
back. Let go of near the window's edge, it lands against it, unless Pull
to Edge is off. Sized by its edge, it is locked at that size, and the window
resized, the others are arranged around it, none over another."""

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QDrag

from gridplayer.params.menu import SUBMENUS
from gridplayer.params.static import TilePull
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
)


def _area(rect) -> float:
    return rect.width * rect.height


def _in_place(d) -> bool:
    """Whether each video is where its tile is, on the screen: none on its
    way there still, nor about to be arranged around a tile held still."""

    page = d.ctx.commands.free_page()
    grid = d.player._managers_inst["grid"]
    # held still, the others are arranged in a moment, then slide
    if grid._rest_timer.isActive() or grid._grid.is_gliding():
        return False
    for video_id, rect in page.tiles.rects(
        page.rect.width(), page.rect.height()
    ).items():
        block = d.ctx.video_blocks.by_video_id(video_id)
        at = block.mapToGlobal(QPoint(0, 0)) - page.rect.topLeft()
        found = (at.x(), at.y(), at.x() + block.width(), at.y() + block.height())
        if not _near(found, rect, slack=1.5):
            return False
    return True


def _is_locked(d, name) -> bool:
    return d.ctx.commands.is_tile_locked(_by_name(d, name).video_id)


def _landing(d):
    return d.ctx.commands.free_tile_landing()


def _held_and_let_go(d, name, start, end, label):
    """A tile dragged from start to end and held, then let go: held still,
    the others make room around where it would land, and stay so."""

    before = _rects(d)
    _drag(d, start, end, release=False)
    d.wait_until(lambda: _in_place(d), f"{label}: held, the others in their places")
    shown = _rects(d)
    landing = _landing(d)
    d.check(f"{label}: while held, it would land", landing is not None)
    others = {n: r for n, r in shown.items() if n != name}
    d.check(
        f"{label}: while held, the others moved",
        any(not _near(r, before[n], slack=1) for n, r in others.items()),
        (before, shown),
    )
    d.check(
        f"{label}: while held, none over another, nor where it would land",
        not _overlapping({**others, name: landing}),
        (shown, landing),
    )
    d.shot(f"{label}_held")

    _mouse(d, "release", end)
    d.wait_until(lambda: _in_place(d), f"{label}: let go, all in their places")
    let_go = _rects(d)
    d.check(
        f"{label}: let go, it landed there, the others as shown",
        all(_near(let_go[n], r, slack=1) for n, r in {**others, name: landing}.items()),
        (shown, landing, let_go),
    )
    d.check(f"{label}: let go, none would land", _landing(d) is None)
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
        "Pull to Edge Near",
        "Animate Tiles",
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

    # a, by its middle, toward the bottom right corner: with Pull to Edge
    # off, it lands where it is let go of
    d.act(d.cells[0], "Pull to Edge Off")
    d.check("Pull to Edge off", d.ctx.commands.is_tile_pull(TilePull.OFF))
    a = _rects(d)["a.mp4"]
    start = _at(d, a.center_x, a.center_y)

    _, moved = _held_and_let_go(d, "a.mp4", start, start + QPoint(120, 80), "1_moved")
    d.check("a moved", moved["a.mp4"].left > a.left, (a, moved["a.mp4"]))
    d.act(d.cells[0], "Undo Grid Change")
    d.wait_until(lambda: _in_place(d), "undone, all in their places")

    # with Pull to Edge on, let go of near the window's left edge, it lands
    # against it, as big as it was; with Alt held, where it is let go
    d.act(d.cells[0], "Pull to Edge Near")
    a = _rects(d)["a.mp4"]
    start = _at(d, a.center_x, a.center_y)
    off_edge = QPoint(round(40 - a.left), 60)
    _drag(d, start, start + off_edge, release=False)
    d.wait_until(lambda: _in_place(d), "held near the edge, the others in place")
    held = _rects(d)["a.mp4"]
    landing = _landing(d)
    d.check(
        "held near the edge: where the pointer has it, to land against the edge",
        abs(held.left - 40) < 2 and landing.left == 0,
        (held, landing),
    )
    d.shot("1b_held_near_edge")
    _mouse(d, "release", start + off_edge)
    d.wait_until(lambda: _in_place(d), "let go near the edge, all in their places")
    pulled = _rects(d)["a.mp4"]
    d.check(
        "let go near the edge: against it, as big",
        pulled.left == 0 and abs(pulled.width - a.width) < 1,
        (a, pulled),
    )
    d.check("none over another", not _overlapping(_rects(d)), _rects(d))
    d.shot("1c_pulled")
    d.act(d.cells[0], "Undo Grid Change")
    d.wait_until(lambda: _in_place(d), "undone, all in their places")

    _drag(d, start, start + off_edge, modifiers=Qt.AltModifier)
    d.wait_until(lambda: _in_place(d), "let go with Alt, all in their places")
    free = _rects(d)["a.mp4"]
    d.check("let go with Alt: where it was let go", abs(free.left - 40) < 2, free)
    d.act(d.cells[0], "Undo Grid Change")
    d.wait_until(lambda: _in_place(d), "undone, all in their places")
    moved = _rects(d)

    # b made bigger by its left edge
    b = moved["b.mp4"]
    edge = _at(d, b.left + 1, b.center_y)
    before, sized = _held_and_let_go(d, "b.mp4", edge, edge - QPoint(120, 0), "2_sized")
    d.check("b bigger", _area(sized["b.mp4"]) > 1.2 * _area(b), (b, sized["b.mp4"]))
    d.check("sized by its edge: locked", _is_locked(d, "b.mp4"))

    d.act(d.cells[0], "Undo Grid Change")
    d.pump(0.3)
    undone = _rects(d)
    d.check(
        "undone: as before the sizing",
        all(_near(undone[n], r, slack=1) for n, r in before.items()),
        (before, undone),
    )
    d.check("undone: not locked", not _is_locked(d, "b.mp4"))

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

    # b sized again, so locked, and the window made narrower, then wider:
    # the others around it, none over another, all in the window
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.5)
    b = _rects(d)["b.mp4"]
    edge = _at(d, b.left + 1, b.center_y)
    _drag(d, edge, edge - QPoint(120, 0))
    d.wait_until(lambda: _in_place(d), "sized again, all in their places")
    d.check("sized again: locked", _is_locked(d, "b.mp4"))
    for width in (WIDTH - 100, WIDTH - 200, WIDTH - 100, WIDTH):
        d.player.resize(width, HEIGHT)
        d.pump(0.05)
    d.wait_until(lambda: not grid._arrange_timer.isActive(), "resize done")
    d.wait_until(lambda: _in_place(d), "resized with a lock, all in their places")
    rects = _rects(d)
    page = d.ctx.commands.free_page().rect
    d.check("resized with a lock: none over another", not _overlapping(rects), rects)
    d.check(
        "resized with a lock: all in the window",
        all(
            r.right <= page.width() + 0.5 and r.bottom <= page.height() + 0.5
            for r in rects.values()
        ),
        (page, rects),
    )
    d.check("resized with a lock: still locked", _is_locked(d, "b.mp4"))
    d.shot("4_locked_resized")
