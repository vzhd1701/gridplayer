"""A template makes a Fixed Grid with a big cell, the first video in it.
Make Cell Smaller and Make Cell Bigger change the active video's cell,
the videos after it moving along, and Undo and Redo take each change back
and do it again: the template too, back to the Auto grid there was.
"""

from gridplayer.params.static import GridMode

WIDTH, HEIGHT = 600, 450


def _rects(d):
    """Each video's cell, as shares of the grid's area, by its file."""

    area = d.ctx.commands.grid_area()
    return {
        cell.video_params.uri.name: (
            round(cell.x() / area.width(), 2),
            round(cell.y() / area.height(), 2),
            round(cell.width() / area.width(), 2),
            round(cell.height() / area.height(), 2),
        )
        for cell in d.cells
    }


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    folder = d.media.folder
    d.open(
        folder / "a.mp4",
        folder / "b.mp4",
        folder / "c.mp4",
        d.media.shapes / "square.mp4",
    )
    d.wait_until(lambda: len(d.cells) == 4, "four cells")
    d.wait_until(lambda: all(c.is_playable for c in d.cells), "all playing")
    first = d.cells[0]
    d.pump(0.5)

    actions = d.ctx.actions
    d.check("no undo yet", not actions["Undo Grid Change"].is_enabled)
    d.check("bigger cells only in Fixed Grid", actions["Make Cell Bigger"].is_skipped)

    d.act(first, "Grid Template 1 + 5")
    d.pump(0.3)
    state = d.ctx.grid_state
    d.check("Fixed Grid", state.mode == GridMode.FIXED, state.mode)
    d.check("the template ticked", actions["Grid Template 1 + 5"].check_if())
    d.check(
        "the first video in the big cell",
        first.geometry().size() == d.cells[1].geometry().size() * 2,
        (first.geometry(), d.cells[1].geometry()),
    )
    d.shot("1_template")

    d.act(first, "Make Cell Smaller")
    d.pump(0.3)
    d.check("smaller", first.geometry().size() == d.cells[1].geometry().size())
    d.check("not the template now", not actions["Grid Template 1 + 5"].check_if())
    d.check("can't go smaller", not actions["Make Cell Smaller"].is_enabled)
    d.shot("2_smaller")

    d.act(first, "Make Cell Bigger")
    d.pump(0.3)
    d.check("bigger again", actions["Grid Template 1 + 5"].check_if())

    d.act(first, "Undo Grid Change")
    d.act(first, "Undo Grid Change")
    d.pump(0.3)
    d.check("undone to the template", actions["Grid Template 1 + 5"].check_if())

    d.act(first, "Undo Grid Change")
    d.pump(0.3)
    state = d.ctx.grid_state
    d.check("undone to Auto", state.mode == GridMode.AUTO_ROWS, state.mode)
    d.check(
        "all the same size again",
        len({c.geometry().size().width() for c in d.cells}) == 1,
        _rects(d),
    )
    d.check("nothing more to undo", not actions["Undo Grid Change"].is_enabled)

    d.act(first, "Redo Grid Change")
    d.pump(0.3)
    d.check("redone", actions["Grid Template 1 + 5"].check_if(), _rects(d))
    d.shot("3_redone")

    d.check(
        "the videos all still there, playing",
        len(d.cells) == 4 and all(c.is_playable for c in d.cells),
    )
