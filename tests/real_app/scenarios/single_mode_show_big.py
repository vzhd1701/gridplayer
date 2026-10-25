"""Show Big, which shares its keys: by default the double click Single Mode
ON / OFF has too. On a strip video, a double click shows it big; on the big
one, it leaves Single Mode. Given Next Video's key, N, Show Big takes it on
a strip video, and Next Video keeps it on the big one.
"""

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtTest import QTest


def _big(d):
    return d.ctx.commands.single_mode_video()


def _middle(cell) -> QPoint:
    return cell.mapToGlobal(QPoint(cell.width() // 2, cell.height() // 2))


def _point_at(d, cell):
    QCursor.setPos(_middle(cell))
    d.ctx.active_block = cell
    d.pump(0.2)


def _double_click(d, cell):
    _point_at(d, cell)
    window = d.player.windowHandle()
    local = window.mapFromGlobal(_middle(cell))
    QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, local)
    d.pump(0.5)


def _press_n(d, cell):
    _point_at(d, cell)
    QTest.keyClick(d.player, Qt.Key_N)
    d.pump(0.5)


def scenario(d):
    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    first, second, third = d.cells
    d.act(first, "Single Mode ON / OFF")
    d.act(first, "Single Mode Strip")
    d.pump(0.5)

    _double_click(d, second)
    d.check("a double click on a strip video shows it big", _big(d) is second)
    d.check("still single mode", d.ctx.is_single_mode)

    _double_click(d, second)
    d.check("a double click on the big one leaves", not d.ctx.is_single_mode)

    d.act(first, "Single Mode ON / OFF")
    d.pump(0.5)
    d.ctx.actions_manager.apply_bindings({"Show Big": ["N"]})
    d.check(
        "N kept by Next Video's QAction",
        "N" in [k.toString() for k in d.ctx.actions["Next Video"].shortcuts()],
    )
    d.player.activateWindow()

    _press_n(d, third)
    d.check("N on a strip video shows it big", _big(d) is third)

    _press_n(d, third)
    d.check("N on the big one is Next Video", _big(d) is first)
