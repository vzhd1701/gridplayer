from unittest.mock import Mock

from gridplayer.models.video import Video
from gridplayer.mpv_player.static import MediaInput
from gridplayer.params.static import NO_FILL_LIMIT
from gridplayer.widgets.video_block_view import ViewControl


def test_a_video_loads_with_the_limit():
    media_input = MediaInput(
        uri="file:///video.mp4",
        is_live=False,
        is_audio_only=False,
        size=(640, 360),
        video=Video(uri="file:///video.mp4"),
        fill_limit=30,
    )

    assert media_input.view.fill_limit == 30


def test_a_video_keeps_the_limit_and_shows_by_it():
    block = Mock()
    view = ViewControl(block)

    view.set_fill_limit(30)

    assert view.fill_limit == 30
    block.video_driver.set_fill_limit.assert_called_once_with(30)


def test_a_video_with_no_driver_yet_keeps_the_limit_for_its_load():
    block = Mock(video_driver=None)
    view = ViewControl(block)

    view.set_fill_limit(30)

    assert view.fill_limit == 30


def test_a_video_not_shown_big_has_no_limit():
    assert ViewControl(Mock()).fill_limit == NO_FILL_LIMIT
