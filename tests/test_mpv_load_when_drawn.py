"""An MPV cell has loaded once its picture can be drawn: a GL surface starts a
while after the cell is made, and the cell is loading until then."""

from unittest.mock import MagicMock

from gridplayer.widgets.video_frame_mpv import VideoDriverMpv


def _driver(*, has_frame=True, is_drawing=True):
    driver = MagicMock()
    driver._has_frame = False
    driver._surface.has_frame.return_value = has_frame
    driver._surface.is_drawing.return_value = is_drawing
    return driver


def test_a_frame_on_a_drawing_surface_reports_the_load():
    driver = _driver()

    VideoDriverMpv._report_frame(driver)

    assert driver._has_frame
    driver._report_load.assert_called_once()


def test_a_frame_waits_for_its_surface_to_draw():
    driver = _driver(is_drawing=False)

    VideoDriverMpv._report_frame(driver)

    assert not driver._has_frame
    driver._report_load.assert_not_called()


def test_a_surface_that_starts_before_any_frame_reports_nothing():
    driver = _driver(has_frame=False)

    VideoDriverMpv._report_frame(driver)

    driver._report_load.assert_not_called()
