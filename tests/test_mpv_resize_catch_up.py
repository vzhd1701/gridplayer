"""While a resize goes on, an MPV picture grown well past its frame is drawn at
the size it has got to, rather than blown up until the resize ends."""

from unittest.mock import MagicMock

import pytest

from gridplayer.widgets.video_frame_mpv import VideoFrameMpv


def _frame(*, is_resizing=True, frame_size=(400, 225), wanted=(900, 506)):
    frame = MagicMock()
    frame._settle_timer.isActive.return_value = is_resizing
    frame.video_surface.has_frame.return_value = True
    frame.video_surface.frame_size.return_value = frame_size
    frame._render_size_now.return_value = wanted
    return frame


def test_a_picture_grown_well_past_its_frame_catches_up():
    frame = _frame()

    VideoFrameMpv._catch_up_render_size(frame)

    frame.video_driver.set_render_size.assert_called_once_with((900, 506))


@pytest.mark.parametrize(
    "frame",
    [
        _frame(frame_size=(860, 484)),
        _frame(wanted=(300, 169)),
        _frame(is_resizing=False),
    ],
    ids=["nearly as big", "shrinking", "resize over"],
)
def test_otherwise_it_waits_for_the_resize_to_end(frame):
    VideoFrameMpv._catch_up_render_size(frame)

    frame.video_driver.set_render_size.assert_not_called()
