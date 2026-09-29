"""The opaque floating overlay: its window cut to the shape of what is on it.

Whatever is outside that shape is never painted, so everything on it has to
be inside the shape before it paints: a label that is not comes up blank, or
as it was the last time it was painted there.
"""

import pytest
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.widgets.video_overlay import OverlayBlockFloating

LENGTH = 60000


@pytest.fixture
def overlay():
    holder = QWidget()
    holder.setAttribute(Qt.WA_DontShowOnScreen)
    holder.resize(640, 360)

    overlay = OverlayBlockFloating(holder)
    overlay.make_opaque()
    overlay.resize(640, 360)
    overlay.set_color("#ffffff")
    overlay.set_is_stopped(False)
    overlay.set_position(27000, LENGTH)

    holder.show()
    overlay.show()
    QApplication.processEvents()

    yield overlay

    overlay.close()
    holder.close()


def _covers(mask: QRegion, rect: QRect) -> bool:
    return QRegion(rect).subtracted(mask).isEmpty()


def _hover(overlay, fraction):
    bar = overlay.progress_bar
    x = round(bar.width() * fraction)

    overlay.floating_progress.on_mouse_over(
        bar.mapTo(overlay, QPoint(x, 0)), x / bar.width(), bar.width()
    )

    return overlay.floating_progress


def _pointer_tip(label):
    return QPoint(label.x() + label._pointer_x, label.y() + label.height() - 2)


class TestComingBack:
    def test_the_shape_it_comes_back_with_takes_in_the_title(self, overlay):
        """A link's title arrives while the video loads, with it hidden."""

        overlay.hide()
        overlay.set_label("The Apple Product I Still Fanboy Over")
        overlay.refresh_opaque_mask()

        assert _covers(overlay.mask(), overlay.label_text.geometry())

    def test_what_is_hidden_with_it_stays_out(self, overlay):
        overlay.hide()
        overlay.set_is_chrome_visible(False)

        assert not overlay.mask().intersects(overlay.label_text.geometry())


class TestTheHoverLabel:
    def test_it_is_in_the_shape_before_it_paints(self, overlay):
        label = _hover(overlay, 0.5)

        box = label.geometry().adjusted(0, 0, 0, -10)

        assert _covers(overlay.mask(), box)
        assert overlay.mask().contains(_pointer_tip(label))

    def test_it_is_cut_to_its_box_and_its_pointer(self, overlay):
        label = _hover(overlay, 0.5)

        shape = label.mask()
        bottom = label.height() - 1

        assert _covers(shape, QRect(0, 0, label.width(), label.height() - 10))
        assert shape.contains(QPoint(label._pointer_x, bottom - 1))
        # beside the pointer is not the label's
        assert not shape.contains(QPoint(0, bottom))
        assert not shape.contains(QPoint(label.width() - 1, bottom))

    def test_the_shape_follows_it_along_the_bar(self, overlay):
        _hover(overlay, 0.2)
        label = _hover(overlay, 0.7)

        assert _covers(overlay.mask(), label.geometry().adjusted(0, 0, 0, -10))
        assert overlay.mask().contains(_pointer_tip(label))

    def test_the_pointer_follows_it_to_the_end_of_the_bar(self, overlay):
        """Pushed in at the end, the label stays put and its pointer moves."""

        _hover(overlay, 0.99)
        label = _hover(overlay, 1.0)

        assert overlay.mask().contains(_pointer_tip(label))

    def test_gone_it_leaves_the_shape(self, overlay):
        label = _hover(overlay, 0.5)
        box = label.geometry().adjusted(0, 0, 0, -10)

        label.on_mouse_left()

        # what is left there is the bar and the time, not the label
        above_the_bar = box.intersected(
            QRect(0, 0, overlay.width(), overlay.progress_bar.y())
        )
        assert not overlay.mask().intersects(above_the_bar)


class TestTheNotice:
    def test_it_is_in_the_shape_as_soon_as_it_shows(self, overlay):
        overlay.set_info_label("Skipped: Sponsor")

        assert _covers(overlay.mask(), overlay.label_info.geometry())


class TestGrowing:
    def test_what_the_shape_grows_into_is_painted_again(self, overlay, mocker):
        update = mocker.spy(overlay, "update")
        old_mask = QRegion(overlay.mask())

        label = _hover(overlay, 0.5)

        revealed = overlay.mask().subtracted(old_mask)
        repainted = QRegion()
        for call in update.call_args_list:
            if call.args:
                repainted += QRegion(call.args[0])

        assert not revealed.isEmpty()
        assert revealed.subtracted(repainted).isEmpty()
        assert label.isVisible()
