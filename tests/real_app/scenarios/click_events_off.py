"""Clicking a cell with "Disable Mouse Click Events" on does nothing, a live
stream's cell as much as a file's (#219: an RTSP stream still paused).

A click goes to the window, as the system sends it, and on to whatever is
under it there: the video, the overlay or the cell.
"""

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication


def scenario(d):
    live = d.serve_live(d.media.hls / "v0")
    d.open(live.url, d.media.clips[0])
    stream = d.wait_for_cell("live.m3u8")
    clip = d.wait_for_cell("a.mp4")

    # as it comes: a click pauses
    for cell in (stream, clip):
        _click(d, cell)
        d.wait_until(
            lambda cell=cell: cell.video_params.is_paused,
            f"{cell.title}: a click pauses",
        )
        d.act(cell, "Play / Pause")
        d.wait_until(
            lambda cell=cell: _is_playing(cell), f"{cell.title}: playing again"
        )

    d.act(clip, "Disable Mouse Click Events")
    d.check("clicks are off", d.ctx.is_disable_mouse_click_events)

    for cell in (stream, clip):
        d.check(f"{cell.title}: playing before", _is_playing(cell), d.state(cell))
        _click(d, cell)
        _click(d, cell, double=True)
        d.wait(1)
        d.check(
            f"{cell.title}: a click does nothing",
            _is_playing(cell) and not d.ctx.is_single_mode,
            d.state(cell),
        )

    d.act(clip, "Disable Mouse Click Events")


def _is_playing(cell) -> bool:
    return cell.is_playable and not cell.video_params.is_paused


def _click(d, cell, double=False):
    """In the cell, off its middle, where the overlay may have a button."""

    top = cell.window()
    window = top.windowHandle()
    spot = cell.mapTo(top, QPoint(cell.width() // 3, cell.height() // 3))

    # the pointer there first, which makes it the cell a click is for
    QCursor.setPos(top.mapToGlobal(spot))
    QApplication.sendEvent(
        window,
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(spot),
            QPointF(top.mapToGlobal(spot)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    d.wait_until(lambda: d.ctx.active_block is cell, f"{cell.title} is active")

    if double:
        QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=spot)
    else:
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=spot)

    d.pump(0.3)
