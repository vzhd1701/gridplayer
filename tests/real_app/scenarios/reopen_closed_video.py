"""Reopen Closed Video: the video closed last opened again where it was, as
it was. In an Auto grid, the middle one comes back in the middle, paused
where it was. Closed at its end, one comes back from its start. In Edit
Grid, a big cell closed with the button in its name comes back from the
bar's button, of its size, in its place. The Recently Closed menu lists the
closes, the last first, and reopens any of them. Closing the playlist forgets
them all.
"""

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QCursor, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import VideoEndAction

RECENTLY_CLOSED = "menu_generator_recently_closed"


def _names(d):
    return [
        b.video_params.uri.name
        for b in d.ctx.video_blocks.blocks_for_ids(d.ctx.commands.layout_order())
    ]


def _by_name(d, name):
    return next(b for b in d.cells if b.video_params.uri.name == name)


def _can_reopen(d):
    return d.ctx.actions["Reopen Closed Video"].is_enabled


def _editor(d):
    return d.player._managers_inst["grid_edit"]._editor


def _click_in_editor(d, point: QPoint):
    """Pointed at, as the system would have it, then clicked."""

    editor = _editor(d)
    window = editor.windowHandle()
    QCursor.setPos(editor.mapToGlobal(point))
    d.pump(0.05)
    # a move with no button held, which QTest's never comes as
    QApplication.sendEvent(
        editor,
        QMouseEvent(
            QEvent.MouseMove, QPointF(point), Qt.NoButton, Qt.NoButton, Qt.NoModifier
        ),
    )
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
    d.pump(0.05)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point)
    d.pump(0.05)


def scenario(d):
    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    d.wait_until(lambda: all(c.is_video_initialized for c in d.cells), "loaded")
    d.check("nothing to reopen at first", not _can_reopen(d))

    # the middle one, paused halfway, closed and opened again
    middle = _by_name(d, "b.mp4")
    d.act(middle, "50%")
    d.run(middle, "active", "set_pause", True)
    d.wait_until(lambda: middle.video_params.is_paused, "paused")
    d.pump(0.5)
    position = middle.time
    d.act(middle, "Close")
    d.wait_until(lambda: len(d.cells) == 2, "closed")
    d.check("it can be reopened", _can_reopen(d))

    d.act(d.cells[0], "Reopen Closed Video")
    d.wait_until(lambda: len(d.cells) == 3, "reopened")
    back = _by_name(d, "b.mp4")
    d.check("back in the middle", _names(d) == ["a.mp4", "b.mp4", "c.mp4"], _names(d))
    d.wait_until(lambda: back.is_video_initialized, "loaded again")
    # as the player has it, once it has had time to say
    d.pump(1.0)
    d.check("still paused", back.video_params.is_paused)
    d.check(
        "where it was",
        abs(back.time - position) < 500,
        (back.time, position),
    )
    d.check("nothing more to reopen", not _can_reopen(d))

    # two closed: the menu lists them, the last first, either reopened
    d.act(_by_name(d, "c.mp4"), "Close")
    d.wait_until(lambda: len(d.cells) == 2, "c closed")
    d.act(_by_name(d, "a.mp4"), "Close")
    d.wait_until(lambda: len(d.cells) == 1, "a closed")
    listed = d.menu(d.cells[0], RECENTLY_CLOSED)
    d.check(
        "listed, the last first",
        [title.split("	")[0] for title in listed] == ["a.mp4", "c.mp4"],
        listed,
    )
    d.choose(d.cells[0], RECENTLY_CLOSED, "c.mp4")
    d.wait_until(lambda: len(d.cells) == 2, "c reopened from the menu")
    d.check(
        "the other still listed",
        [title.split("	")[0] for title in d.menu(d.cells[0], RECENTLY_CLOSED)]
        == ["a.mp4"],
    )
    d.act(d.cells[0], "Reopen Closed Video")
    d.wait_until(lambda: len(d.cells) == 3, "a reopened")
    d.check("all back in order", _names(d) == ["a.mp4", "b.mp4", "c.mp4"], _names(d))

    # closed at its end: back from its start
    last = _by_name(d, "c.mp4")
    d.run(last, "active", "set_end_action", VideoEndAction.CLOSE)
    d.run(last, "active", "set_pause", False)
    d.act(last, "90%")
    d.wait_until(lambda: len(d.cells) == 2, "closed at its end", timeout=20)
    d.act(d.cells[0], "Reopen Closed Video")
    d.wait_until(lambda: len(d.cells) == 3, "reopened")
    again = _by_name(d, "c.mp4")
    d.run(again, "active", "set_end_action", VideoEndAction.LOOP_FILE)
    d.wait_until(lambda: again.is_video_initialized, "loaded again")
    d.pump(1.0)
    d.check("from its start", 0 < again.time < 3000, again.time)

    # in Edit Grid: a big cell closed by its button, reopened by the bar's
    d.act(d.cells[0], "Edit Grid")
    d.pump(0.5)
    first = _by_name(d, "a.mp4")
    d.run(first, "set_grid_cell_span", first.video_id, 1, 2)
    d.pump(0.3)
    cells = {c.video_id: c for c in d.ctx.grid_state.cells}
    big = cells[first.video_id]
    d.check("a big cell", (big.rowspan, big.colspan) == (1, 2), big)

    editor = _editor(d)
    cell = next(c for c in editor._cells if c.video_id == first.video_id)
    _click_in_editor(d, editor.close_rect_of(cell).center().toPoint())
    d.wait_until(lambda: len(d.cells) == 2, "closed from the editor")
    d.check("the bar's button on", editor._reopen.isEnabled())

    editor._reopen.click()
    d.wait_until(lambda: len(d.cells) == 3, "reopened from the bar")
    cells = {c.video_id: c for c in d.ctx.grid_state.cells}
    back = cells.get(first.video_id)
    d.check(
        "of its size, in its place",
        back is not None
        and (back.row, back.col, back.rowspan, back.colspan)
        == (big.row, big.col, big.rowspan, big.colspan),
        (back, big),
    )
    d.check("the bar's button off", not editor._reopen.isEnabled())
    d.shot("1_editor", widget=editor)
    editor.done.emit()
    d.pump(0.3)

    # closing the playlist forgets them
    d.act(d.cells[0], "Close")
    d.wait_until(lambda: len(d.cells) == 2, "one more closed")
    d.check("it can be reopened", _can_reopen(d))
    d.act(d.cells[0], "Close Playlist")
    d.wait_until(lambda: not d.cells, "the playlist closed")
    d.check("nothing to reopen after", not _can_reopen(d))
