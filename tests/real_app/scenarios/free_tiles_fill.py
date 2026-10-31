"""Free Tiles: Fill Space, undone, Fit Tile to Video and Lock Tile, from
the video menu and from the tile's own overlay buttons."""

from gridplayer.utils.layout.free_tiles import Rect

SETTINGS = {"playlist/overlay_hide_on_timeout": False}


def _px(d, cell) -> tuple:
    page = d.ctx.commands.free_page()
    r = page.tiles.rects(page.rect.width(), page.rect.height())[cell.video_id]
    return tuple(round(v) for v in r)


def _buttons(cell) -> dict:
    o = cell.overlay
    return {
        name: (
            not getattr(o, name).isHidden(),
            getattr(o, name).is_available,
            getattr(o, name).is_down,
        )
        for name in ("fill_space_button", "fit_video_button", "lock_tile_button")
    }


def scenario(d):
    d.player.resize(1100, 640)
    d.pump(0.3)
    d.open(*d.media.clips[:3])
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.is_video_initialized for c in d.cells), "loaded")
    d.pump(0.5)

    a, b, c = d.cells
    d.act(a, "Free Tiles")
    d.pump(0.5)

    page = d.ctx.commands.free_page()
    width, height = page.rect.width(), page.rect.height()
    d.ctx.commands.set_free_tiles(
        {
            a.video_id: Rect(0, 0, width / 2, height / 2),
            b.video_id: Rect(width / 2, 0, width, height / 2),
            c.video_id: Rect(width * 0.6, height * 0.6, width * 0.9, height * 0.9),
        },
        width,
        height,
    )
    d.pump(0.5)
    d.note(f"page {width}x{height}; c {_px(d, c)}")

    for cell in d.cells:
        cell.show_overlay()
    d.pump(0.3)
    c.cell_size.sync_steps()
    d.note(f"c buttons {_buttons(c)}")
    d.check(
        "tile buttons shown",
        all(shown for shown, _, _ in _buttons(c).values()),
        _buttons(c),
    )
    d.shot("before")

    # from the overlay button
    c.overlay.fill_space_button.clicked.emit()
    d.pump(0.5)
    filled = _px(d, c)
    d.note(f"filled {filled} buttons {_buttons(c)}")
    d.check(
        "filled to the room below the top two",
        filled == (0, round(height / 2), width, height),
        filled,
    )
    d.check(
        "no room left: fill button off",
        not _buttons(c)["fill_space_button"][1],
        _buttons(c),
    )
    d.shot("filled")

    # undone, back where it was
    d.act(c, "Undo Grid Change")
    d.pump(0.5)
    back = _px(d, c)
    d.check(
        "undone",
        back
        == (
            round(width * 0.6),
            round(height * 0.6),
            round(width * 0.9),
            round(height * 0.9),
        ),
        back,
    )

    # from the menu
    d.act(c, "Fill Space")
    d.pump(0.5)
    d.check("filled from the menu", _px(d, c) == filled, _px(d, c))

    d.act(c, "Fit Tile to Video")
    d.pump(0.5)
    fit = _px(d, c)
    shape = c.picture_shape
    d.note(f"fit {fit} shape {shape}")
    d.check(
        "the tile its video's shape",
        abs((fit[2] - fit[0]) / (fit[3] - fit[1]) - shape) < 0.02,
        (fit, shape),
    )
    d.shot("fit")

    c.overlay.lock_tile_button.clicked.emit()
    d.pump(0.5)
    d.note(f"locked buttons {_buttons(c)}")
    d.check("locked", d.ctx.commands.is_tile_locked(c.video_id))
    d.check(
        "locked: lock down, fill and fit off",
        _buttons(c)["lock_tile_button"][2]
        and not _buttons(c)["fill_space_button"][1]
        and not _buttons(c)["fit_video_button"][1],
        _buttons(c),
    )
    d.shot("locked")

    # out of Free Tiles, the tile buttons go
    d.act(a, "Rows First")
    d.pump(0.5)
    d.check(
        "no tile buttons out of Free Tiles",
        not any(shown for shown, _, _ in _buttons(c).values()),
        _buttons(c),
    )
