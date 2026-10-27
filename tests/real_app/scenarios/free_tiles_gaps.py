"""Free Tiles, equal gaps. Off at first: a tile dragged beside two others
only lines up with them. Turned on in Snap To, it snaps to be as far from
them as they are from each other, the gaps marked and said so; not with
Alt. One dragged over a big tile into a corner snaps to the margin another
has in the corner across.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDrag
from PyQt5.QtTest import QTest

from gridplayer.params.static import TileSnap
from tests.real_app.scenarios.free_tiles import (
    HEIGHT,
    WIDTH,
    _at,
    _by_name,
    _drag,
    _mouse,
    _near,
    _rects,
    _set,
)


def _manager(d):
    return d.player._managers_inst["free_tiles"]


def _gap_marks(d):
    return [mark for mark in _manager(d)._gaps if mark.isVisible()]


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
    _set(d, "a.mp4", (20, 120, 180, 200))
    _set(d, "b.mp4", (210, 120, 370, 200))
    _set(d, "c.mp4", (420, 260, 580, 340))

    # off at first: c dragged up beside b, 33 from it, stays so
    _drag(d, _at(d, 500, 300), _at(d, 483, 163), release=False)
    rects = _rects(d)
    d.check(
        "not snapped to the gap", _near(rects["c.mp4"], (403, 120, 563, 200)), rects
    )
    d.check("no gaps marked", not _gap_marks(d), len(_gap_marks(d)))
    QTest.keyClick(d.player.windowHandle(), Qt.Key_Escape)
    d.pump(0.2)
    _mouse(d, "release", _at(d, 483, 163))
    d.pump(0.2)

    d.act(d.cells[0], "Snap to Equal Gaps")
    d.check(
        "Equal Gaps on",
        d.ctx.commands.is_tile_snap(TileSnap.EQUAL_GAPS),
        d.ctx.commands.is_tile_snap(TileSnap.EQUAL_GAPS),
    )

    # on: 30 from b, as a is
    _drag(d, _at(d, 500, 300), _at(d, 483, 163), release=False)
    rects = _rects(d)
    d.check("c snapped to the gap", _near(rects["c.mp4"], (400, 120, 560, 200)), rects)
    d.check("both gaps marked", len(_gap_marks(d)) == 2, len(_gap_marks(d)))
    tag = _manager(d)._tag
    d.check("said so", tag is not None and "Same gap" in tag._text, tag and tag._text)
    d.shot("1_row")
    _mouse(d, "release", _at(d, 483, 163))
    d.pump(0.2)
    d.check("marks gone once let go", not _gap_marks(d), len(_gap_marks(d)))

    # with Alt, moved as the pointer goes
    _drag(
        d,
        _at(d, 480, 160),
        _at(d, 485, 165),
        modifiers=Qt.AltModifier,
        release=False,
    )
    d.check("no marks with Alt", not _gap_marks(d), len(_gap_marks(d)))
    QTest.keyClick(d.player.windowHandle(), Qt.Key_Escape)
    d.pump(0.2)
    _mouse(d, "release", _at(d, 485, 165))
    d.pump(0.2)

    # over a big one: a in the top left corner, c taken to the bottom right
    a = _by_name(d, "a.mp4")
    d.act(a, "Tile Overlap On")
    d.pump(0.2)
    page = d.ctx.commands.free_page().rect
    width, height = page.width(), page.height()
    _set(d, "b.mp4", (0, 0, width, height))
    _set(d, "a.mp4", (16, 16, 144, 88))
    _set(d, "c.mp4", (300, 150, 428, 222))
    d.ctx.commands.bring_free_tile_to_front(a.video_id)
    d.ctx.commands.bring_free_tile_to_front(_by_name(d, "c.mp4").video_id)
    d.pump(0.2)

    # 4 and 3 short of a's margin
    left, top = width - 16 - 128, height - 16 - 72
    end = (364 + left - 300 - 4, 186 + top - 150 - 3)
    _drag(d, _at(d, 364, 186), _at(d, *end), release=False)
    rects = _rects(d)
    d.check(
        "c as far in from its corner as a",
        _near(rects["c.mp4"], (left, top, left + 128, top + 72)),
        rects["c.mp4"],
    )
    d.check("its margins and a's marked", len(_gap_marks(d)) == 4, len(_gap_marks(d)))
    d.shot("2_corner")
    _mouse(d, "release", _at(d, *end))
    d.pump(0.2)
