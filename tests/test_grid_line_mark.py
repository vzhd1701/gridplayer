"""The marks shown over the player while a line or a tile is moved."""

from PyQt5.QtCore import QPoint, QRect

from gridplayer.widgets import grid_line_mark
from gridplayer.widgets.grid_line_mark import GridLineTag, ShapeMark

ROOM = QRect(0, 0, 800, 600)


def test_the_word_kept_over_a_line_shown_after_it(mocker):
    # a guide that comes up while the word is up would be stacked over it
    tag = GridLineTag()
    guide = ShapeMark()
    raised = mocker.patch.object(tag, "_put_on_top")

    tag.show_text("Edges lined up", True, QPoint(100, 100), ROOM)
    tag.show_text("Edges lined up", True, QPoint(100, 110), ROOM)
    times = raised.call_count

    guide.show_guide(True, 50, 0, 400, (0, 400))
    tag.show_text("Edges lined up", True, QPoint(100, 120), ROOM)

    # on top as it comes up, not put there on each move; after the guide
    assert times == 0
    assert raised.call_count == 1

    tag.hide()
    guide.hide()


def test_cut_once_the_window_is_its_new_size(mocker):
    # with no compositor: X11 cuts a shape set before the window grows to
    # the size it was then, the rest never seen
    mocker.patch.object(grid_line_mark, "is_compositor_running", return_value=False)
    tag = GridLineTag()
    cut_at = []
    mocker.patch.object(tag, "setMask", side_effect=lambda _: cut_at.append(tag.size()))

    tag.show_text("Page middle", True, QPoint(100, 100), ROOM)
    tag.show_text("Page middle, Edges lined up", True, QPoint(100, 100), ROOM)
    tag.show_text("Page middle, Edges lined up", True, QPoint(100, 120), ROOM)

    assert len(cut_at) == 2
    assert cut_at[1] == tag.size()
    assert cut_at[1].width() > cut_at[0].width()

    tag.hide()
