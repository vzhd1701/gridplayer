"""The painted picture: black only where the picture isn't, with nothing left of
what was there before, on any cell size and screen scale."""

import math

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QColor, QImage, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.params.static import VideoCellViewMode, VideoTransform, ViewParams
from gridplayer.widgets.video_surface_sw import SoftwareVideoSurface

GREEN = 0xFF00FF00
# what a pixel left unpainted shows
STALE = QColor(255, 0, 255)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _surface(size, frame=(160, 90), mode=VideoCellViewMode.FIT, zoom=1.0):
    surface = SoftwareVideoSurface()
    surface.resize(*size)

    frame_w, frame_h = frame
    surface.present_rgb32(GREEN.to_bytes(4, "little") * frame_w * frame_h, *frame)
    surface.set_view(
        ViewParams(cell_view_mode=mode, scale=zoom), VideoTransform.NONE, frame
    )

    return surface


def _painted(surface, ratio=1.0) -> QImage:
    image = QImage(
        math.floor(surface.width() * ratio),
        math.floor(surface.height() * ratio),
        QImage.Format_RGB32,
    )
    image.setDevicePixelRatio(ratio)
    image.fill(STALE)

    # the widget's own painting only, as on screen, where it's opaque
    surface.render(image, QPoint(), QRegion(), QWidget.DrawChildren)

    return image


def _colors(image) -> set[str]:
    found = set()

    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)

            if color == STALE:
                found.add("stale")
            elif color.green() > 128:
                found.add("picture")
            elif max(color.red(), color.green(), color.blue()) < 40:
                found.add("black")
            else:
                found.add(f"edge {color.name()}")

    return found


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("size", [(160, 90), (101, 77), (333, 100), (77, 201)])
def test_nothing_is_left_unpainted(size, ratio):
    assert "stale" not in _colors(_painted(_surface(size), ratio))


@pytest.mark.parametrize("ratio", [1.0, 1.5])
def test_a_picture_smaller_than_its_cell_has_black_beside_it(ratio):
    image = _painted(_surface((300, 90)), ratio)

    assert image.pixelColor(0, 0).name() == "#000000"
    assert image.pixelColor(image.width() - 1, image.height() - 1).name() == "#000000"
    assert image.pixel(image.width() // 2, image.height() // 2) == GREEN


@pytest.mark.parametrize("ratio", [1.0, 1.5])
def test_zoomed_out_off_centre_nothing_is_left_unpainted(ratio):
    surface = _surface((217, 133), zoom=0.37)

    assert "stale" not in _colors(_painted(surface, ratio))


def test_a_picture_that_covers_its_cell_is_not_filled_under():
    surface = _surface((320, 180))

    filled = sum(bar.width() * bar.height() for bar in surface._bars((0, 0, 320, 180)))

    # only the edge a pixel wide
    assert filled < 2 * (320 + 180) + 4


def test_with_no_picture_it_is_all_black():
    surface = SoftwareVideoSurface()
    surface.resize(50, 30)

    assert _colors(_painted(surface)) == {"black"}
