"""A cell's size from the video itself, in a Fixed Grid: the buttons in its
overlay's title bar make it a step bigger and smaller, and the third picks
its size from a small grid, as a table's is picked. In an Auto grid the
buttons are not there. The video's menu has the sizes in Cell Size.
A step there is no room for is greyed. In a narrow cell the buttons go
under the name and the close button.
"""

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QCursor, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.menu import SECTIONS
from gridplayer.params.static import GridMode
from gridplayer.widgets.grid_span_picker import CELL, GAP, PADDING, GridSpanPicker

WIDTH, HEIGHT = 900, 560


def _overlay(cell):
    return cell.overlay


def _span(d, cell):
    return d.ctx.commands.grid_cell_span(cell.video_id)


def _picker():
    return next(
        (w for w in QApplication.topLevelWidgets() if isinstance(w, GridSpanPicker)),
        None,
    )


def _cell_size_menu(d, cell) -> list[str]:
    """The titles shown in the video's menu's Cell Size, opened on it. (Not
    the menu itself: offscreen, the clipboard that one of its items asks
    is None.)"""

    d.ctx.active_block = cell
    items = next(
        item[1:]
        for item in SECTIONS["video_active"]
        if isinstance(item, tuple) and item[0] == "Cell Size"
    )
    actions = [d.ctx.actions[name] for name in items if name != "---"]
    return [
        action.title for action in actions if not action.show_if or action.show_if()
    ]


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    folder = d.media.folder
    d.open(folder / "a.mp4", folder / "b.mp4", folder / "c.mp4")
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.is_playable for c in d.cells), "all playing")
    a, b, c = d.cells

    overlay = _overlay(a)
    d.check("no buttons in Auto", not overlay.cell_bigger_button.isVisibleTo(overlay))

    titles = _cell_size_menu(d, a)
    d.check("no Cell Size in Auto", titles == [], titles)

    # as Edit Grid makes it, the size it is; Fixed Grid asks for one
    d.ctx.commands.make_grid_fixed()
    d.wait_until(
        lambda: d.ctx.grid_state.mode == GridMode.FIXED, "a Fixed Grid", timeout=5
    )
    d.ctx.commands.resize_fixed_grid(3, 3)
    d.pump(0.5)

    d.check("the buttons there", overlay.cell_bigger_button.isVisibleTo(overlay))
    d.check("and the picker's", overlay.cell_size_button.isVisibleTo(overlay))

    # a step bigger, from its own button
    overlay.cell_bigger_button.clicked.emit()
    d.pump(0.5)
    d.check("A two by two", _span(d, a) == (2, 2), _span(d, a))
    d.shot("1_bigger")

    # and smaller again, the pointer on it: greyed at once, not once the
    # grid settles
    button = overlay.cell_smaller_button
    QCursor.setPos(button.mapToGlobal(button.rect().center()))
    button.clicked.emit()
    d.pump(0.05)
    d.check("A one cell again", _span(d, a) == (1, 1), _span(d, a))
    d.check("its Smaller greyed at once", not button.is_available)
    d.check("its Bigger not", overlay.cell_bigger_button.is_available)

    # B three wide, picked
    overlay = _overlay(b)
    overlay.cell_size_button.clicked.emit()
    d.wait_until(lambda: _picker() is not None, "the picker shown", timeout=5)
    picker = _picker()
    d.check("of the grid's size", (picker._rows, picker._cols) == (3, 3))
    d.check("its button lit", overlay.cell_size_button.is_down)
    d.check(
        "a click outside only closes it",
        picker.testAttribute(Qt.WA_NoMouseReplay),
    )
    d.shot("2_picker", widget=picker)

    at = QPoint(PADDING + 2 * (CELL + GAP) + CELL // 2, PADDING + CELL // 2)
    QApplication.sendEvent(
        picker,
        QMouseEvent(
            QEvent.MouseMove, QPointF(at), Qt.NoButton, Qt.NoButton, Qt.NoModifier
        ),
    )
    d.check("three by one shown", picker._pick == (1, 3), picker._pick)
    QTest.mouseRelease(picker.windowHandle(), Qt.LeftButton, Qt.NoModifier, at)
    d.pump(0.5)
    d.check("B three wide", _span(d, b) == (1, 3), _span(d, b))
    d.check("the picker gone", _picker() is None)
    d.check("its button no longer lit", not overlay.cell_size_button.is_down)

    # back to one cell, from its menu
    d.act(b, "Reset Cell Size")
    d.pump(0.5)
    d.check("B one cell", _span(d, b) == (1, 1), _span(d, b))
    d.act(b, "Undo Grid Change")
    d.pump(0.5)
    d.check("B three wide again", _span(d, b) == (1, 3), _span(d, b))
    d.shot("3_picked")

    # the menu's Cell Size
    titles = _cell_size_menu(d, c)
    d.check(
        "Cell Size in a Fixed Grid",
        titles[:7]
        == [
            "Bigger",
            "Smaller",
            "Reset Size",
            "Wider",
            "Narrower",
            "Taller",
            "Shorter",
        ],
        titles,
    )
    d.act(c, "Make Cell Taller")
    d.pump(0.5)
    d.check("C two high", _span(d, c) == (2, 1), _span(d, c))

    # narrow cells: under the name and the close button
    d.player.resize(700, 520)
    d.pump(0.8)
    overlay = _overlay(a)
    d.check(
        "under the name",
        overlay.info_bar.indexOf(overlay.cell_bigger_button) >= 0
        and overlay.cell_bigger_button.isVisibleTo(overlay),
        overlay.width(),
    )
    d.shot("4_narrow")

    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.8)
    # as the pointer coming over it shows it
    a.show_overlay()
    d.pump(0.3)
    d.check(
        "back in the title",
        overlay.title_bar.indexOf(overlay.cell_bigger_button) >= 0
        and overlay.cell_bigger_button.isVisibleTo(overlay),
        (overlay.isVisible(), overlay.width()),
    )

    d.check(
        "still playing, all of them",
        len(d.cells) == 3 and all(cell.is_playable for cell in d.cells),
    )
