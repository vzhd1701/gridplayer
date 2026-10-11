"""The seek and the volume bars over a video: how their parts are painted."""

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage, QPainter

from gridplayer.widgets.video_overlay_elements import (
    BOX_RADIUS,
    OverlayProgressBar,
    OverlayVolumeBar,
)

DARK_PICTURE = QColor("#101010")


def _over_dark_picture(bar):
    image = QImage(bar.size(), QImage.Format_RGB32)
    image.fill(DARK_PICTURE)

    painter = QPainter(image)
    bar.render(painter, QPoint(0, 0))
    painter.end()

    return image


def _corner_pixels(image, corners):
    reach = int(BOX_RADIUS) + 1

    for corner_x, corner_y in corners:
        for dx in range(reach):
            for dy in range(reach):
                x = corner_x + dx if corner_x == 0 else corner_x - dx
                y = corner_y + dy if corner_y == 0 else corner_y - dy

                yield QColor(image.pixel(x, y))


def _assert_only_progress_and_picture(pixels, progress):
    """Each pixel the progress over the picture, partly or wholly, with none
    of the box's own fill showing round it."""

    for pixel in pixels:
        share = (pixel.red() - DARK_PICTURE.red()) / (
            progress.red() - DARK_PICTURE.red()
        )

        green = DARK_PICTURE.green() + share * (progress.green() - DARK_PICTURE.green())

        assert pixel.green() == pytest.approx(green, abs=3), pixel.name()


@pytest.fixture
def seek_bar():
    bar = OverlayProgressBar()
    bar.setAttribute(Qt.WA_DontShowOnScreen)
    bar.resize(200, 23)
    bar.color = QColor(Qt.white)

    yield bar

    bar.close()


@pytest.fixture
def volume_bar():
    bar = OverlayVolumeBar()
    bar.setAttribute(Qt.WA_DontShowOnScreen)
    bar.resize(23, 100)
    bar.color = QColor(Qt.white)

    yield bar

    bar.close()


class TestRoundedCorners:
    def test_the_seek_bar_has_no_pale_fringe_round_the_progress(self, seek_bar):
        seek_bar.position = 0.5

        image = _over_dark_picture(seek_bar)
        bottom = image.height() - 1

        _assert_only_progress_and_picture(
            _corner_pixels(image, [(0, 0), (0, bottom)]), seek_bar.color_progress
        )

    def test_the_volume_bar_has_no_pale_fringe_round_the_volume(self, volume_bar):
        volume_bar.position = 0.5

        image = _over_dark_picture(volume_bar)
        right = image.width() - 1
        bottom = image.height() - 1

        _assert_only_progress_and_picture(
            _corner_pixels(image, [(0, bottom), (right, bottom)]),
            volume_bar.color_progress,
        )


class TestAheadOfTheMouse:
    def test_it_stands_apart_from_the_bar_over_a_dark_picture(self, seek_bar):
        seek_bar.position = 0.2
        seek_bar.progress_select_x = 150
        seek_bar.underMouse = lambda: True

        image = _over_dark_picture(seek_bar)
        middle = image.height() // 2

        ahead = QColor(image.pixel(100, middle))
        rest = QColor(image.pixel(180, middle))

        assert ahead.name() == seek_bar.color_ahead.name()
        assert ahead.blue() - ahead.red() > 60
        assert abs(rest.blue() - rest.red()) < 5
