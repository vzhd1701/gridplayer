"""Fit Shapes with videos made bigger and the videos reordered to fit. A
video made bigger from its own button gets a bigger tile, in its place;
one undo puts it back, and so does Reset Sizes. Reorder to Fit lays
videos of like shapes together, showing them no smaller, and keeps the
order the videos are in.
"""

import math

from gridplayer.params.static import GridMode

WIDTH, HEIGHT = 960, 540


def _boxes(d):
    """Each video's cell, on the screen, by its id."""

    return {cell.video_id: cell.geometry() for cell in d.cells if cell.isVisible()}


def _area(rect):
    return rect.width() * rect.height()


def _log_areas(d):
    return sum(math.log(_area(rect)) for rect in _boxes(d).values())


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    folder, shapes = d.media.folder, d.media.shapes
    d.open(
        folder / "a.mp4",
        shapes / "phone.mp4",
        folder / "b.mp4",
        shapes / "square.mp4",
        folder / "c.mp4",
    )
    d.wait_until(lambda: len(d.cells) == 5, "five cells")
    d.wait_until(lambda: all(c.is_playable for c in d.cells), "all playing")
    ids = [cell.video_id for cell in d.cells]

    d.ctx.commands.set_grid_mode(GridMode.AUTO_SHAPES)
    d.pump(0.8)
    d.shot("1_fit_shapes")

    # a made bigger, from its own button: no picker, in Fit Shapes
    a = d.cells[0]
    overlay = a.overlay
    d.check(
        "bigger and smaller, no picker",
        overlay.cell_bigger_button.isVisibleTo(overlay)
        and not overlay.cell_size_button.isVisibleTo(overlay),
    )
    before = _area(_boxes(d)[a.video_id])
    overlay.cell_bigger_button.clicked.emit()
    d.pump(0.8)
    after = _area(_boxes(d)[a.video_id])
    d.check("a bigger", after > before, (before, after))
    d.check("in its place", d.ctx.commands.layout_order() == ids)
    d.shot("2b_bigger")
    d.act(a, "Undo Grid Change")
    d.pump(0.8)
    d.check("a back", _area(_boxes(d)[a.video_id]) == before)

    # bigger again, from its menu, then all reset
    d.act(a, "Make Cell Bigger")
    d.pump(0.8)
    d.check("a bigger again", _area(_boxes(d)[a.video_id]) > before)
    d.act(a, "Reset Sizes")
    d.pump(0.8)
    d.check("reset", _area(_boxes(d)[a.video_id]) == before)
    d.check("nothing to reset", not d.ctx.commands.is_grid_sized())
    b = d.cells[2]

    # the videos reordered to fit
    before = _log_areas(d)
    d.act(b, "Reorder to Fit")
    d.pump(0.8)
    d.check("no smaller", _log_areas(d) >= before - 0.01, (before, _log_areas(d)))
    d.check("their order kept", d.ctx.commands.layout_order() == ids)
    d.shot("3_reordered")

    d.check(
        "still playing, all of them",
        len(d.cells) == 5 and all(cell.is_playable for cell in d.cells),
    )
