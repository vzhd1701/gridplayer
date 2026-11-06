"""The sums and the bookkeeping of the mpv driver, with no libmpv. How it plays
is in tests/real_app/scenarios/mpv_basics.py."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.mpv_player.player import MpvPlayer, _params_sar, calc_fit_size
from gridplayer.mpv_player.renderer import (
    FrameSlot,
    RenderedVideo,
    VideoRenderer,
)
from gridplayer.params.static import VideoDriver, VideoTransform
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import ViewPlacement, calc_render_size
from gridplayer.vlc_player.static import Media, MediaInput, VideoTrack
from gridplayer.widgets.video_frame_mpv import MpvVideoSurface, VideoDriverMpv


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


# -- how big to render


def _placed(source, target):
    return ViewPlacement(source=source, target=target)


def test_render_size_is_what_is_on_show():
    placement = _placed((0, 0, 1920, 1080), (0, 0, 480, 270))

    assert calc_render_size((1920, 1080), placement) == (480, 270)


def test_render_size_takes_the_screens_pixels():
    placement = _placed((0, 0, 1920, 1080), (0, 0, 480, 270))

    assert calc_render_size((1920, 1080), placement, device_ratio=1.5) == (720, 405)


def test_render_size_grows_with_the_zoom():
    # a quarter of the picture across all of the cell
    placement = _placed((480, 270, 480, 270), (0, 0, 480, 270))

    assert calc_render_size((1920, 1080), placement) == (1920, 1080)


def test_render_size_stops_at_what_the_picture_has():
    placement = _placed((0, 0, 640, 360), (0, 0, 1920, 1080))

    assert calc_render_size((640, 360), placement) == (640, 360)


def test_render_size_keeps_room_for_wide_pixels():
    # stored 320x360, shown 640x360
    placement = _placed((0, 0, 320, 360), (0, 0, 1280, 720))

    assert calc_render_size((320, 360), placement, pixel_aspect=2.0) == (640, 360)


def test_render_size_is_never_nothing():
    placement = _placed((0, 0, 1920, 1080), (0, 0, 1, 1))

    assert calc_render_size((1920, 1080), placement) == (2, 2)


@pytest.mark.parametrize(
    ("size", "box", "expected"),
    [
        ((1920, 1080), (480, 480), (480, 270)),
        ((1920, 1080), (480, 100), (178, 100)),
        ((640, 360), (1920, 1080), (640, 360)),
        ((640, 360), None, (640, 360)),
        ((640, 360), (0, 0), (640, 360)),
    ],
)
def test_fit_size(size, box, expected):
    assert calc_fit_size(size, box) == expected


# -- the frame and its surface


def test_surface_goes_by_the_tracks_size_not_the_frames():
    surface = MpvVideoSurface()
    surface.present_black(320, 180)

    surface.set_view(surface._view, VideoTransform.NONE, (1920, 1080))

    assert surface.picture_size() == (1920, 1080)


def test_surface_goes_by_the_frame_with_no_track_size():
    surface = MpvVideoSurface()
    surface.present_black(320, 180)

    surface.set_view(surface._view, VideoTransform.NONE, (0, 0))

    assert surface.picture_size() == (320, 180)


def test_surface_places_on_whole_pixels():
    surface = MpvVideoSurface()
    surface.resize(101, 101)
    surface.present_black(1920, 1080)
    surface.set_view(surface._view, VideoTransform.NONE, (1920, 1080))

    x, y, width, height = surface.placement().target

    assert all(value == int(value) for value in (x, y, width, height))


def test_surface_source_is_in_the_frames_pixels():
    surface = MpvVideoSurface()
    surface.resize(1920, 1080)
    surface.present_black(320, 180)
    surface.set_view(surface._view, VideoTransform.NONE, (1920, 1080))

    assert surface.placement().source == pytest.approx((0, 0, 320, 180))


# -- the triple buffer


def test_slot_keeps_its_buffer_for_the_same_size():
    slot = FrameSlot()

    first = slot.writable(4, 2)
    pixels = slot.pixels

    assert slot.writable(4, 2) is first
    assert slot.pixels is pixels
    assert len(pixels) == 4 * 2 * 4


def test_slot_makes_a_new_buffer_for_another_size():
    slot = FrameSlot()

    slot.writable(4, 2)
    old = slot.pixels
    slot.writable(2, 2)

    # what is on show can still be holding the old one
    assert slot.pixels is not old
    assert len(old) == 4 * 2 * 4


def test_a_published_frame_comes_out_once():
    video = RenderedVideo(player=None)
    back = video.back

    video.publish()
    assert video.has_fresh_frame

    assert video.latest() is back
    assert not video.has_fresh_frame
    assert video.latest() is back


def test_the_renderer_never_writes_what_is_on_show():
    video = RenderedVideo(player=None)

    for _ in range(5):
        on_show = video.latest()
        assert video.back is not on_show

        video.publish()
        assert video.back is not on_show


# -- one mpv instance, with python-mpv standing in


class _FakeMpv:
    def __init__(self, **options):
        self.options = options
        self.commands = []
        self.track_list = []
        self.duration = 20.0
        self.event_callback = None
        self.observers = {}

    def register_event_callback(self, callback):
        self.event_callback = callback

    def observe_property(self, name, handler):
        self.observers[name] = handler

    def command_async(self, *args):
        self.commands.append(args)


def _mpv_module():
    return SimpleNamespace(
        MPV=lambda log_handler, loglevel, **options: _FakeMpv(**options),
        MpvEventID=SimpleNamespace(FILE_LOADED=8, PLAYBACK_RESTART=21, END_FILE=7),
        MpvEventEndFile=SimpleNamespace(ERROR=4),
        ShutdownError=RuntimeError,
    )


def _player(is_live=False, is_audio_only=False, **video):
    media_input = MediaInput(
        uri="file.mp4",
        is_live=is_live,
        is_audio_only=is_audio_only,
        size=(100, 100),
        video=Video(uri="file.mp4", **video),
    )
    return MpvPlayer(
        _mpv_module(),
        media_input,
        hwdec="auto",
        wake_renderer=MagicMock(),
    )


def test_options_leave_no_hardware_saving_out():
    options = _player().mpv.options

    assert options["hwdec"] == "auto"
    assert options["hwdec_extra_frames"] == 0
    assert options["video_timing_offset"] == 0
    assert options["keepaspect"] is False
    assert options["ytdl"] is False


def test_options_start_where_it_was_left():
    assert _player(current_position=5000).mpv.options["start"] == "5.0"
    assert "start" not in _player().mpv.options


def test_options_start_paused():
    assert _player(is_paused=True).mpv.options["pause"] is True


def test_no_size_to_render_until_the_picture_says():
    player = _player()

    assert player.render_size() is None


def test_rotated_picture_swaps_the_size():
    player = _player()

    player._on_video_params(
        "video-params", {"w": 1920, "h": 1080, "dw": 1920, "dh": 1080, "rotate": 90}
    )

    assert player.render_size() == (1080, 1920)


def test_render_size_fits_the_box_until_the_view_says():
    player = _player()
    player.start((480, 480))

    player._on_video_params("video-params", {"dw": 1920, "dh": 1080})
    assert player.render_size() == (480, 270)

    player.set_render_size((960, 540))
    assert player.render_size() == (960, 540)


def test_a_new_render_size_wakes_the_renderer_only_when_new():
    player = _player()
    player._wake_renderer.reset_mock()

    player.set_render_size((100, 50))
    player.set_render_size((100, 50))

    player._wake_renderer.assert_called_once()


def test_no_commands_after_closing():
    player = _player()

    player.close()
    player.command("set", "pause", "yes")

    assert player.mpv.commands == []


def test_tracks_read_as_the_rest_of_the_app_has_them():
    player = _player()
    player.mpv.track_list = [
        {
            "type": "video",
            "id": 1,
            "selected": True,
            "demux-w": 1920,
            "demux-h": 1080,
            "demux-fps": 25.0,
            "demux-rotation": 90,
            "codec": "h264",
        },
        {"type": "video", "id": 2, "albumart": True},
        {
            "type": "audio",
            "id": 1,
            "selected": True,
            "default": True,
            "lang": "eng",
            "demux-channel-count": 2,
            "demux-samplerate": 48000,
            "codec": "aac",
        },
        {"type": "sub", "id": 1, "lang": "fra", "codec": "subrip", "external": True},
    ]

    media = player._media_from_tracks()

    assert media.length == 20000
    assert list(media.video_tracks) == [1]
    assert media.cur_video_track_id == 1
    assert media.video_tracks[1].video_dimensions == (1920, 1080)
    assert media.video_tracks[1].orientation == VideoTransform.ROTATE_90
    assert media.audio_tracks[1].channels == 2
    assert media.default_audio_track_id == 1
    assert media.external_subtitle_ids == (1,)
    assert not media.is_audio_only


def test_no_length_is_live():
    player = _player()
    player.mpv.duration = None

    assert player._media_from_tracks().is_live


def test_a_live_stream_has_no_length_whatever_mpv_says():
    player = _player(is_live=True)
    player.mpv.duration = 3600.0

    assert player._media_from_tracks().is_live


def test_random_start_with_no_length_still_loads():
    player = _player(is_start_random=True)
    player.mpv.duration = None
    loaded = MagicMock()
    player.media_loaded.connect(loaded)

    player._read_media()

    loaded.assert_called_once()
    assert player.media_input.is_live


def test_audio_only_has_no_video_tracks_even_if_the_file_does():
    player = _player(is_audio_only=True)
    player.mpv.duration = 10.0
    player.mpv.track_list = [{"type": "video", "id": 1, "demux-w": 640, "demux-h": 360}]

    assert player._media_from_tracks().is_audio_only


# -- the driver


def _driver():
    return VideoDriverMpv(
        render_service=MagicMock(),
        hwdec="auto",
        surface=MagicMock(),
        pane_box=lambda: (100, 100),
    )


def test_a_size_change_while_playing_reaches_the_tracks():
    driver = _driver()
    track = VideoTrack(
        video_dimensions=(640, 360),
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        fps=30,
        sar=(1, 1),
    )
    driver._media = Media(
        length=1000, video_tracks={1: track}, audio_tracks={}, cur_video_track_id=1
    )
    driver._is_load_reported = True
    told = MagicMock()
    driver.video_dimensions_changed.connect(told)

    driver._on_video_size(640, 480, (4, 3))

    assert track.video_dimensions == (640, 480)
    assert track.sar == (4, 3)
    told.assert_called_once_with(640, 480, (4, 3))


def test_a_libmpv_that_wont_start_is_an_error_on_the_cell(mocker):
    mocker.patch(
        "gridplayer.widgets.video_frame_mpv.MpvPlayer",
        side_effect=ValueError("Invalid value for mpv option"),
    )
    driver = _driver()
    failed = MagicMock()
    driver.error.connect(failed)

    driver.load_video(_player().media_input)

    failed.assert_called_once()
    assert "Invalid value" in failed.call_args.args[1][0]
    assert not driver._load_timeout.isActive()


# -- the render loop


def _rendered_video(size=(4, 2)):
    video = RenderedVideo(MagicMock())
    video.player.render_size.return_value = size
    video.render_context = MagicMock()
    video.render_context.update.return_value = False
    return video


@pytest.fixture
def renderer():
    made = VideoRenderer(MagicMock())
    made._gl = MagicMock()
    return made


def _round(renderer, video, *, is_frame):
    video.needs_update = True
    video.render_context.update.return_value = is_frame
    renderer._render_round()


def test_nothing_is_rendered_before_the_first_frame(renderer):
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False)

    video.render_context.render.assert_not_called()
    assert not video.has_fresh_frame

    _round(renderer, video, is_frame=True)

    video.render_context.render.assert_called_once()
    assert video.has_fresh_frame


def test_a_frame_before_the_size_is_rendered_once_the_size_comes(renderer):
    video = _rendered_video(size=None)
    renderer._videos.append(video)

    _round(renderer, video, is_frame=True)
    video.render_context.render.assert_not_called()

    video.player.render_size.return_value = (4, 2)
    renderer._render_round()

    video.render_context.render.assert_called_once()


def test_a_new_size_is_rendered_with_no_new_frame(renderer):
    video = _rendered_video()
    renderer._videos.append(video)
    _round(renderer, video, is_frame=True)

    video.player.render_size.return_value = (8, 4)
    renderer._render_round()

    assert video.render_context.render.call_count == 2
    assert video.rendered_size == (8, 4)


def test_one_video_failing_to_render_leaves_the_others(renderer):
    bad, good = _rendered_video(), _rendered_video()
    context = bad.render_context
    context.update.side_effect = ValueError("bad render state")
    renderer._videos.extend((bad, good))
    failed = MagicMock()
    renderer.failed.connect(failed)
    bad.needs_update = True
    good.needs_update = True
    good.render_context.update.return_value = True

    renderer._render_round()

    failed.assert_called_once_with(bad, "bad render state")
    assert renderer._videos == [good]
    context.free.assert_called_once()
    good.render_context.render.assert_called_once()


@pytest.mark.parametrize(
    ("params", "sar"),
    [
        ({"w": 1920, "h": 1080, "dw": 1920, "dh": 1080}, (1, 1)),
        ({"w": 320, "h": 360, "dw": 640, "dh": 360}, (2, 1)),
        ({"w": 720, "h": 576, "dw": 1024, "dh": 576}, (64, 45)),
        ({"dw": 640, "dh": 360}, None),
    ],
)
def test_pixel_shape_from_the_sizes(params, sar):
    assert _params_sar(params) == sar


# -- finding and loading


def test_manager_makes_no_render_service_for_vlc(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)

    manager = VideoDriverManager(context=SimpleNamespace())
    manager.video_driver()

    assert manager._mpv_render_service is None
