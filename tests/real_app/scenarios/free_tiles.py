"""Free Tiles: the grid made tiles where its cells are, moved and sized by
hand with the mouse. A tile dragged by its middle goes with the pointer
and stops at one in the way, sliding along it; that is no click of the
video, nor a drag of it, while a click still is. Sized by a corner it
keeps its shape and its other corner, and stops at a tile in the way, Esc
puts it back, a word by the pointer says what it snapped to. One tight under
another, of another shape than its video's, sized by its side keeps its
shape, with no jump, and grows away from the one above, never over it,
nor moved over it after. Shift frees its shape, and a double click on an
edge stretches it to the page's edge. Arrange Tiles lays them out anew,
and Undo takes that back. A video added goes where there is room. Single
Mode leaves the tiles as they were. The window made wider, the tiles
stay as big, in the middle, the room beside them free to move one to,
which makes the layout the window's shape; made back untouched, they are
as they were. Rows First takes the videos in the order the tiles are
read in.
"""

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QCursor, QDrag, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import GridMode
from gridplayer.utils.layout.free_tiles import Rect

WIDTH, HEIGHT = 700, 400


def _page(d):
    return d.ctx.commands.free_page()


def _at(d, x, y) -> QPoint:
    return _page(d).rect.topLeft() + QPoint(round(x), round(y))


def _rects(d) -> dict[str, Rect]:
    page = _page(d)
    rects = page.tiles.rects(page.rect.width(), page.rect.height())
    return {
        d.ctx.video_blocks.by_video_id(video_id).video_params.uri.name: rect
        for video_id, rect in rects.items()
    }


def _near(rect, expected, slack=1.5) -> bool:
    return all(abs(a - b) <= slack for a, b in zip(rect, expected, strict=True))


def _by_name(d, name):
    return next(b for b in d.cells if b.video_params.uri.name == name)


def _set(d, name, rect):
    page = _page(d)
    d.ctx.commands.set_free_tiles(
        {_by_name(d, name).video_id: Rect(*rect)},
        page.rect.width(),
        page.rect.height(),
    )
    d.pump(0.2)


def _mouse(d, kind, pos, modifiers=Qt.NoModifier):
    """The pointer there, and the mouse event, as the window it is over has
    them from the system."""

    QCursor.setPos(pos)
    window = d.player.windowHandle()
    local = window.mapFromGlobal(pos)

    if kind == "move":
        buttons = QApplication.mouseButtons()
        event = QMouseEvent(
            QEvent.MouseMove, local, pos, Qt.NoButton, buttons, modifiers
        )
        QApplication.sendEvent(window, event)
    elif kind == "press":
        QTest.mousePress(window, Qt.LeftButton, modifiers, local)
    elif kind == "release":
        QTest.mouseRelease(window, Qt.LeftButton, modifiers, local)
    elif kind == "double":
        QTest.mouseDClick(window, Qt.LeftButton, modifiers, local)

    d.pump(0.1)


def _drag(d, start, end, modifiers=Qt.NoModifier, steps=8, release=True):
    _mouse(d, "move", start)
    _mouse(d, "press", start)
    # a pixel at a time at first, as a mouse goes: a drag of the video
    # would start there (see DragNDropManager)
    toward = end - start
    nudge = QPoint(
        (toward.x() > 0) - (toward.x() < 0), (toward.y() > 0) - (toward.y() < 0)
    )
    for _ in range(4):
        _mouse(d, "move", start + nudge, modifiers)
    for step in range(1, steps + 1):
        at = start + (end - start) * step / steps
        _mouse(d, "move", at, modifiers)
    if release:
        _mouse(d, "release", end, modifiers)
        d.pump(0.2)


def _cursor():
    cursor = QApplication.overrideCursor()
    return None if cursor is None else cursor.shape()


def _overlapping(rects) -> list:
    found = list(rects.items())
    return [
        (a, b)
        for i, (a, ra) in enumerate(found)
        for b, rb in found[i + 1 :]
        if ra.overlaps(rb)
    ]


def scenario(d):
    # a drag of a video, which would hold the tile still until let go
    video_drags = []
    QDrag.exec = lambda _drag, *_args: video_drags.append(1) or Qt.IgnoreAction

    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.picture_shape for c in d.cells), "shapes known")
    d.wait_until(lambda: not any(c.video_params.is_paused for c in d.cells), "playing")
    d.pump(0.5)

    # the cells made tiles, nothing moving
    cells = {c.video_params.uri.name: c.geometry() for c in d.cells}
    d.act(d.cells[0], "Free Tiles")
    d.pump(0.3)
    d.check("Free Tiles", d.ctx.commands.is_grid_free())
    now = {c.video_params.uri.name: c.geometry() for c in d.cells}
    d.check("each tile where its cell was", now == cells, (now, cells))

    # laid out by hand, to know where they are
    _set(d, "a.mp4", (20, 20, 260, 155))
    _set(d, "b.mp4", (300, 20, 540, 155))
    _set(d, "c.mp4", (20, 200, 260, 335))
    d.shot("1_tiles")

    # tight under a, wider than its video: sized by its side, no jump, and
    # down, away from a; moved up after, it stops at a
    _set(d, "a.mp4", (20, 20, 290, 155))
    _set(d, "c.mp4", (20, 155, 380, 290))
    _drag(d, _at(d, 379, 222), _at(d, 440, 222))
    c_rect = _rects(d)["c.mp4"]
    d.check(
        "c sized by its side kept its shape and grew away from a",
        _near(c_rect, (20, 155, 440, 312.5)),
        c_rect,
    )
    _drag(d, _at(d, 200, 240), _at(d, 200, 100))
    c_rect = _rects(d)["c.mp4"]
    d.check("c moved up stopped at a", _near(c_rect, (20, 155, 440, 312.5)), c_rect)
    d.check("no tile over another", not _overlapping(_rects(d)), _rects(d))
    _set(d, "a.mp4", (20, 20, 260, 155))
    _set(d, "c.mp4", (20, 200, 260, 335))

    # the pointer turns on an edge, not in the middle
    _mouse(d, "move", _at(d, 21, 90))
    d.check(
        "a resize pointer on the left edge", _cursor() == Qt.SizeHorCursor, _cursor()
    )
    _mouse(d, "move", _at(d, 140, 90))
    d.check("none in the middle", _cursor() is None, _cursor())

    # b dragged by its middle to where c is: flush against a, slid down
    b = _by_name(d, "b.mp4")
    _drag(d, _at(d, 420, 87), _at(d, 160, 300))
    rects = _rects(d)
    d.check(
        "b stopped at a and slid down past c",
        _near(rects["b.mp4"], (260, 233, 500, 368)),
        rects["b.mp4"],
    )
    d.check("no tile over another", not _overlapping(rects), _overlapping(rects))
    d.check("the drag no click of b", not b.video_params.is_paused)
    d.check("nor a drag of the video", not video_drags, len(video_drags))
    d.shot("2_moved")

    # a click is still one
    c = _by_name(d, "c.mp4")
    _mouse(d, "move", _at(d, 140, 270))
    _mouse(d, "press", _at(d, 140, 270))
    _mouse(d, "release", _at(d, 140, 270))
    d.wait_until(lambda: c.video_params.is_paused, "a click pauses c", timeout=3)
    d.run(c, "active", "set_pause", False)

    # a sized by its corner, the pointer going over c below it: its shape
    # and its top left corner kept, its bottom on c
    _drag(d, _at(d, 259, 154), _at(d, 400, 300))
    a = _rects(d)["a.mp4"]
    d.check("a stopped at c, its shape kept", _near(a, (20, 20, 340, 200)), a)

    # Esc puts it back, with nothing to undo
    undo = d.player._managers_inst["grid"]._undo
    undo_before = len(undo)
    _drag(d, _at(d, 339, 199), _at(d, 200, 120), release=False)
    QTest.keyClick(d.player.windowHandle(), Qt.Key_Escape)
    d.pump(0.1)
    _mouse(d, "release", _at(d, 200, 120))
    a = _rects(d)["a.mp4"]
    d.check("Esc put a back", _near(a, (20, 20, 340, 200)), a)
    d.check("nothing to undo from Esc", len(undo) == undo_before, len(undo))

    # snapped to the page's edge: lines and a word say so; Esc
    _drag(d, _at(d, 140, 270), _at(d, 124, 270), release=False)
    tag = d.player._managers_inst["free_tiles"]._tag
    said = tag._text if tag is not None and tag.isVisible() else None
    # its top at the page's middle too, as it was, and on a's bottom
    d.check(
        "c at the page's edge, and it says so",
        said == "Page middle, Page edge, Touching",
        said,
    )
    d.shot("3_snapped")
    QTest.keyClick(d.player.windowHandle(), Qt.Key_Escape)
    d.pump(0.1)
    _mouse(d, "release", _at(d, 124, 270))
    d.check("no word once let go", not tag.isVisible())
    c_rect = _rects(d)["c.mp4"]
    d.check("Esc put c back", _near(c_rect, (20, 200, 260, 335)), c_rect)

    # the application left while it is held (Alt+Tab): let go of there,
    # nothing of it left over the other windows, one change to undo
    _drag(d, _at(d, 140, 270), _at(d, 124, 270), release=False)
    manager = d.player._managers_inst["free_tiles"]
    QApplication.sendEvent(
        QApplication.instance(), QEvent(QEvent.ApplicationDeactivate)
    )
    d.pump(0.1)
    frame = manager._frame
    left_shown = [
        w
        for w in (*manager._guides, tag, *frame._outline, *frame._lit, *frame._dashed)
        if w.isVisible()
    ]
    d.check("let go of on leaving", manager._drag is None)
    d.check("nothing shown once left", not left_shown, left_shown)
    _mouse(d, "release", _at(d, 124, 270))
    d.act(d.cells[0], "Undo Grid Change")
    d.pump(0.3)
    c_rect = _rects(d)["c.mp4"]
    d.check("undone, c back", _near(c_rect, (20, 200, 260, 335)), c_rect)

    # Shift: any shape
    _drag(d, _at(d, 140, 334), _at(d, 140, 380), modifiers=Qt.ShiftModifier)
    c_rect = _rects(d)["c.mp4"]
    d.check("c made taller, as wide", _near(c_rect, (20, 200, 260, 380)), c_rect)

    # a double click on b's right edge: to the page's edge
    _mouse(d, "move", _at(d, 499, 300))
    _mouse(d, "double", _at(d, 499, 300))
    d.pump(0.2)
    b_rect = _rects(d)["b.mp4"]
    d.check(
        "b stretched to the page's edge", _near(b_rect, (260, 233, 700, 368)), b_rect
    )
    d.shot("3_sized")

    # undone, one step back; Arrange, and undone
    by_hand = _rects(d)
    d.act(d.cells[0], "Arrange Tiles")
    d.pump(0.3)
    rects = _rects(d)
    d.check("arranged: none over another", not _overlapping(rects), rects)
    d.check("arranged anew", rects != by_hand, rects)
    d.shot("4_arranged")
    d.act(d.cells[0], "Undo Grid Change")
    d.pump(0.3)
    d.check("Arrange undone", _rects(d) == by_hand, _rects(d))

    # a video added: where there is room
    d.open(d.media.clips[0])
    d.wait_until(lambda: len(d.cells) == 4, "four cells")
    d.pump(0.5)
    rects = _page(d).tiles.rects(_page(d).rect.width(), _page(d).rect.height())
    d.check(
        "four tiles, none over another",
        len(rects) == 4 and not _overlapping(rects),
        rects,
    )
    d.shot("5_added")

    # Single Mode and back: the tiles as they were
    tiles = dict(_page(d).tiles.tiles)
    d.act(d.cells[0], "Single Mode ON / OFF")
    d.pump(0.5)
    d.check("Single Mode", d.ctx.is_single_mode)
    d.act(d.cells[0], "Single Mode ON / OFF")
    d.pump(0.5)
    d.check("the tiles as they were", _page(d).tiles.tiles == tiles)

    # the window made wider: the tiles as they were, in the middle, the
    # room beside them free; made back, as before
    free = d.player._managers_inst["grid"]._free
    stored = dict(free.tiles)
    page_shape = free.page_shape
    sizes = {name: (r.width, r.height) for name, r in _rects(d).items()}
    d.player.resize(WIDTH + 300, HEIGHT)
    d.pump(0.5)
    page = _page(d)
    d.check("the page is all of the area", page.rect == d.ctx.commands.grid_area())
    rects = _rects(d)
    d.check(
        "wider: the tiles as big",
        all(_near((r.width, r.height), sizes[n]) for n, r in rects.items()),
        rects,
    )
    d.check(
        "in the middle",
        abs(min(r.left for r in rects.values()) - 150) < 30,
        rects,
    )
    d.shot("6_wider")
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.5)
    d.check(
        "made back: as they were",
        free.tiles == stored and free.page_shape == page_shape,
    )

    # wider again, the rightmost tile moved into the room beside
    d.player.resize(WIDTH + 300, HEIGHT)
    d.pump(0.5)
    name, rect = max(_rects(d).items(), key=lambda item: item[1].right)
    middle = _at(d, rect.center_x, rect.center_y)
    _drag(d, middle, middle + QPoint(400, 0), steps=16)
    moved = _rects(d)[name]
    width = _page(d).rect.width()
    d.check("moved into the room beside", moved.right > width - 2, (moved, width))
    area = d.ctx.commands.grid_area()
    d.check(
        "the layout now the window's shape",
        abs(free.page_shape - area.width() / area.height()) < 0.01,
        (free.page_shape, page_shape),
    )
    d.shot("7_moved_beside")
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.5)

    # back to Rows First: in the order the tiles are read in
    order = _page(d).tiles.order()
    d.run(d.cells[0], "set_grid_mode", GridMode.AUTO_ROWS)
    d.pump(0.3)
    d.check("not Free Tiles", not d.ctx.commands.is_grid_free())
    d.check(
        "the videos in reading order",
        d.ctx.commands.layout_order() == order,
        (d.ctx.commands.layout_order(), order),
    )
