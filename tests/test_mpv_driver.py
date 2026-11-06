"""The sums and the bookkeeping of the mpv driver, with no libmpv. How it plays
is in tests/real_app/scenarios/mpv_basics.py."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.mpv_player.player import MpvPlayer, _params_sar, calc_fit_size
from gridplayer.mpv_player.renderer import (
    FrameSlot,
    MpvRenderService,
    RenderedVideo,
    VideoRenderer,
)
from gridplayer.params.static import (
    VideoCellViewMode,
    VideoCrop,
    VideoDriver,
    VideoTransform,
    ViewParams,
)
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import (
    ViewPlacement,
    calc_full_size,
    calc_render_size,
)
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


def test_render_size_of_a_turned_picture_stops_at_what_it_has_each_way():
    # all of a 1920x1080 picture on its side, on a screen with room to spare
    placement = _placed((0, 0, 1920, 1080), (0, 0, 2160, 3840))

    assert calc_render_size(
        (1920, 1080), placement, transform=VideoTransform.ROTATE_90
    ) == (1080, 1920)


def test_render_size_of_a_turned_picture_is_what_is_on_show():
    placement = _placed((0, 0, 1920, 1080), (0, 0, 270, 480))

    assert calc_render_size(
        (1920, 1080), placement, transform=VideoTransform.ROTATE_90
    ) == (270, 480)


@pytest.mark.parametrize(
    ("picture", "transform", "pixel_aspect", "expected"),
    [
        ((1920, 1080), VideoTransform.NONE, 1.0, (1920, 1080)),
        ((1920, 1080), VideoTransform.HFLIP, 1.0, (1920, 1080)),
        ((1920, 1080), VideoTransform.ROTATE_180, 1.0, (1920, 1080)),
        ((1920, 1080), VideoTransform.ROTATE_90, 1.0, (1080, 1920)),
        ((1920, 1080), VideoTransform.TRANSPOSE, 1.0, (1080, 1920)),
        ((320, 360), VideoTransform.NONE, 2.0, (640, 360)),
        ((640, 360), VideoTransform.NONE, 0.5625, (640, 640)),
        ((320, 360), VideoTransform.ROTATE_90, 2.0, (360, 640)),
        ((0, 0), VideoTransform.NONE, 1.0, (0, 0)),
    ],
)
def test_full_size(picture, transform, pixel_aspect, expected):
    assert calc_full_size(picture, transform, pixel_aspect) == expected


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


def _surface_showing(transform, pixels):
    """A surface a frame fills, of this many BGRA pixels in a row."""

    surface = MpvVideoSurface()
    surface.resize(len(pixels), 1)
    surface.set_view(
        ViewParams(cell_view_mode=VideoCellViewMode.STRETCH), transform, None
    )

    buffer = bytearray()
    for color in pixels:
        buffer += color.to_bytes(4, "little")

    surface.present_rgb32(bytes(buffer), len(pixels), 1)

    return surface


RED, BLUE = 0xFFFF0000, 0xFF0000FF


@pytest.mark.parametrize(
    ("transform", "expected"),
    [
        (VideoTransform.NONE, (RED, BLUE)),
        # a turn is mpv's, and a flip up and down leaves a single row as it is
        (VideoTransform.ROTATE_90, (RED, BLUE)),
        (VideoTransform.VFLIP, (RED, BLUE)),
        (VideoTransform.ANTITRANSPOSE, (RED, BLUE)),
        (VideoTransform.HFLIP, (BLUE, RED)),
        (VideoTransform.TRANSPOSE, (BLUE, RED)),
    ],
)
def test_surface_flips_what_it_gives_for_a_screenshot(transform, expected):
    image = _surface_showing(transform, (RED, BLUE)).frame_image()

    assert (image.pixel(0, 0), image.pixel(1, 0)) == expected


def test_surface_flips_the_other_way_on_a_file_on_its_side():
    surface = _surface_showing(VideoTransform.VFLIP, (RED, BLUE))
    surface.set_file_on_its_side(True)
    image = surface.frame_image()

    # up and down for the frame as stored is across once it's on its side
    assert (image.pixel(0, 0), image.pixel(1, 0)) == (BLUE, RED)

    surface = _surface_showing(VideoTransform.HFLIP, (RED, BLUE))
    surface.set_file_on_its_side(True)
    image = surface.frame_image()

    assert (image.pixel(0, 0), image.pixel(1, 0)) == (RED, BLUE)


def _painted_row(surface):
    image = surface.grab().toImage()

    # painted flipped, a colour can come out a shade off
    return [
        BLUE if image.pixelColor(x, 0).blue() > image.pixelColor(x, 0).red() else RED
        for x in range(image.width())
    ]


def test_surface_paints_a_flip_across():
    colors = (RED, RED, RED, BLUE)

    assert _painted_row(_surface_showing(VideoTransform.NONE, colors)) == list(colors)
    assert _painted_row(_surface_showing(VideoTransform.HFLIP, colors)) == list(
        reversed(colors)
    )


def test_surface_flips_the_part_on_show_not_the_same_part_of_the_frame():
    colors = (RED, RED, RED, BLUE)

    surface = _surface_showing(VideoTransform.HFLIP, colors)
    # half of the picture as shown is cut off its left, where the blue has gone
    surface.set_view(
        ViewParams(
            cell_view_mode=VideoCellViewMode.STRETCH, crop=VideoCrop(2, 0, 0, 0)
        ),
        VideoTransform.HFLIP,
        None,
    )

    assert set(_painted_row(surface)) == {RED}


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
        self._event_handle = "event handle"

    def register_event_callback(self, callback):
        self.event_callback = callback

    def observe_property(self, name, handler):
        self.observers[name] = handler

    def command_async(self, *args):
        self.commands.append(args)


def _mpv_module():
    return SimpleNamespace(
        MPV=lambda log_handler, loglevel, **options: _FakeMpv(**options),
        MpvEventID=SimpleNamespace(
            FILE_LOADED=8, PLAYBACK_RESTART=21, END_FILE=7, HOOK=25
        ),
        MpvEventEndFile=SimpleNamespace(ERROR=4),
        ShutdownError=RuntimeError,
        backend=MagicMock(),
    )


def _player(skip_frames=False, is_live=False, is_audio_only=False, **video):
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
        skip_frames=skip_frames,
    )


def test_options_leave_no_hardware_saving_out():
    options = _player().mpv.options

    assert options["hwdec"] == "auto"
    assert options["hwdec_extra_frames"] == 0
    assert options["video_timing_offset"] == 0
    assert options["keepaspect"] is False
    assert options["ytdl"] is False


@pytest.mark.parametrize(
    ("transform", "degrees"),
    [
        (VideoTransform.ROTATE_90, 90),
        (VideoTransform.ROTATE_180, 180),
        (VideoTransform.ROTATE_270, 270),
        (VideoTransform.TRANSPOSE, 90),
        (VideoTransform.ANTITRANSPOSE, 90),
    ],
)
def test_options_turn_the_picture(transform, degrees):
    assert _player(transform=transform).mpv.options["video_rotate"] == degrees


@pytest.mark.parametrize(
    "transform", [VideoTransform.NONE, VideoTransform.HFLIP, VideoTransform.VFLIP]
)
def test_options_leave_the_file_to_say_with_no_turn(transform):
    assert "video_rotate" not in _player(transform=transform).mpv.options


def test_options_start_where_it_was_left():
    assert _player(current_position=5000).mpv.options["start"] == "5.0"
    assert "start" not in _player().mpv.options


def test_options_start_paused():
    assert _player(is_paused=True).mpv.options["pause"] is True


def test_options_skip_frames_only_when_asked():
    assert _player().mpv.options["vd_lavc_skipframe"] == "default"
    assert _player(skip_frames=True).mpv.options["vd_lavc_skipframe"] == "nonref"


def test_skipping_frames_switches_while_playing():
    player = _player()

    player.set_skip_frames(True)
    player.set_skip_frames(False)

    assert player.mpv.commands == [
        ("set", "vd-lavc-skipframe", "nonref"),
        ("set", "vd-lavc-skipframe", "default"),
    ]


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


def test_a_held_size_goes_over_the_views_until_let_go():
    player = _player()
    player._on_video_params(None, {"dw": 1920, "dh": 1080, "w": 1920, "h": 1080})
    player.set_render_size((480, 270))

    player.hold_render_size((1920, 1080))

    assert player.render_size() == (1920, 1080)
    assert player._wake_renderer.called

    # what the view says in the meantime is what it goes back to
    player.set_render_size((640, 360))
    assert player.render_size() == (1920, 1080)

    player.hold_render_size(None)
    assert player.render_size() == (640, 360)


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


def _preloaded(player):
    player._on_event(
        SimpleNamespace(event_id=SimpleNamespace(value=25), data=SimpleNamespace(id=7))
    )


def _hook_answered(player):
    continued = player._mpv_module.backend.mpv_hook_continue

    continued.assert_called_once()

    return continued.call_args.args[1].value == 7


def test_random_start_is_picked_before_anything_is_decoded():
    player = _player(is_start_random=True)

    player._mpv_module.backend.mpv_hook_add.assert_called_once()

    _preloaded(player)

    assert 0 <= float(player.mpv.start) <= 20
    assert float(player.mpv.start) * 1000 == player.media_input.initial_time
    assert _hook_answered(player)


def test_only_a_random_start_waits_for_the_length():
    for player in (_player(), _player(is_start_random=True, current_position=5000)):
        player._mpv_module.backend.mpv_hook_add.assert_not_called()


def test_random_start_with_no_length_still_loads():
    player = _player(is_start_random=True)
    player.mpv.duration = None
    loaded = MagicMock()
    player.media_loaded.connect(loaded)

    _preloaded(player)
    player._read_media()

    loaded.assert_called_once()
    assert player.media_input.is_live
    assert _hook_answered(player)


def test_closing_still_answers_the_hook_mpv_waits_on():
    player = _player(is_start_random=True)
    player.close()

    _preloaded(player)

    assert not hasattr(player.mpv, "start")
    assert _hook_answered(player)


def test_a_failed_hook_is_still_answered():
    player = _player(is_start_random=True)
    player.media_input = None

    with pytest.raises(AttributeError):
        _preloaded(player)

    assert _hook_answered(player)


@pytest.mark.parametrize(
    "seconds",
    [
        # 30 fps: on a whole millisecond, and on either side of one
        5.0, 5.033333, 5.066667,
        # 23.976 fps in an mp4, and in an mkv's whole milliseconds, rounded
        # up and rounded down
        5.005, 5.088417, 5.172, 5.130,
    ],
)  # fmt: skip
def test_the_time_of_a_frame_is_in_that_frame(seconds):
    fps = 30 if seconds in {5.0, 5.033333, 5.066667} else 24000 / 1001
    ms_per_frame = 1000 / fps
    player = _player()
    player._is_media_read = True
    times = []
    player.time_changed.connect(times.append)

    player._on_time("time-pos", seconds)

    assert times[0] // ms_per_frame == round(seconds * fps)


def test_audio_only_has_no_video_tracks_even_if_the_file_does():
    player = _player(is_audio_only=True)
    player.mpv.duration = 10.0
    player.mpv.track_list = [{"type": "video", "id": 1, "demux-w": 640, "demux-h": 360}]

    assert player._media_from_tracks().is_audio_only


# -- the driver


def _driver(full_size=lambda: (0, 0)):
    return VideoDriverMpv(
        render_service=MagicMock(),
        hwdec="auto",
        surface=MagicMock(),
        pane_box=lambda: (100, 100),
        full_size=full_size,
    )


def _driver_playing(fps=None):
    driver = _driver()
    driver._player = _player()
    driver._media = Media(
        length=20_000,
        video_tracks={
            1: VideoTrack(
                video_dimensions=(640, 360),
                fps=fps,
                bitrate=0,
                language=None,
                description=None,
                codec="h264",
            )
        },
        audio_tracks={},
        cur_video_track_id=1,
    )

    return driver


def test_a_seek_aims_half_a_frame_back_for_the_frame_a_time_is_in():
    driver = _driver_playing(fps=25)

    driver.set_time(1020)

    assert driver._player.mpv.commands == [("seek", 1.0, "absolute+exact")]


def test_a_seek_with_no_frame_rate_to_go_by_goes_to_the_time():
    driver = _driver_playing()

    driver.set_time(1020)

    assert driver._player.mpv.commands == [("seek", 1.02, "absolute+exact")]


def test_a_seek_to_the_start_stays_at_the_start():
    driver = _driver_playing(fps=25)

    driver.set_time(0)

    assert driver._player.mpv.commands == [("seek", 0, "absolute+exact")]


def test_a_quick_pause_and_play_both_reach_mpv():
    driver = _driver_playing()

    # mpv hasn't said it paused by the time it's asked to play
    driver.set_pause(True)
    driver.set_pause(False)

    assert driver._player.mpv.commands == [
        ("set", "pause", "yes"),
        ("set", "pause", "no"),
    ]


def test_asking_for_what_it_was_just_asked_only_answers():
    driver = _driver_playing()
    answers = []
    driver.playback_status_changed.connect(answers.append)

    driver.set_pause(True)
    driver.set_pause(True)

    assert driver._player.mpv.commands == [("set", "pause", "yes")]
    assert answers == [True]


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


def _driver_for_screenshots(shown=(320, 180), full=(1920, 1080)):
    driver = _driver(full_size=lambda: full)
    driver._player = _player()
    driver._player.hold_render_size = MagicMock()
    driver._surface.frame_size.return_value = shown

    driver.taken = []
    driver.screenshot_taken.connect(driver.taken.append)

    return driver


def _frame_shown(driver, width, height):
    driver._surface.frame_size.return_value = (width, height)
    driver.show_frame(MagicMock(pixels=b"", width=width, height=height))


def test_a_screenshot_waits_for_the_frame_at_the_pictures_size():
    driver = _driver_for_screenshots()

    driver.screenshot()

    driver._player.hold_render_size.assert_called_once_with((1920, 1080))
    assert driver.taken == []

    # one made before it was asked
    _frame_shown(driver, 320, 180)
    assert driver.taken == []

    _frame_shown(driver, 1920, 1080)
    assert driver.taken == [""]
    driver._player.hold_render_size.assert_called_with(None)

    # that's all that was asked
    _frame_shown(driver, 1920, 1080)
    assert driver.taken == [""]

    driver.cleanup_start()


def test_a_screenshot_of_a_frame_at_its_size_already_takes_no_rendering():
    driver = _driver_for_screenshots(shown=(1920, 1080))

    driver.screenshot()

    assert driver.taken == [""]
    assert not driver._screenshot_timeout.isActive()


def test_screenshots_asked_while_waiting_each_get_the_frame():
    driver = _driver_for_screenshots()

    driver.screenshot()
    driver.screenshot()
    _frame_shown(driver, 1920, 1080)

    assert driver.taken == ["", ""]

    driver.cleanup_start()


def test_a_screenshot_makes_do_with_the_frame_on_show_if_none_comes():
    driver = _driver_for_screenshots()

    driver.screenshot()
    driver._screenshot_timeout.timeout.emit()

    assert driver.taken == [""]
    driver._player.hold_render_size.assert_called_with(None)
    assert not driver._screenshot_timeout.isActive()


def test_a_screenshot_with_no_picture_says_so_at_once():
    driver = _driver_for_screenshots(full=(0, 0))

    driver.screenshot()

    assert driver.taken == [""]
    assert not driver._screenshot_timeout.isActive()


def test_closing_drops_the_screenshots_waiting():
    driver = _driver_for_screenshots()
    driver._rendered = MagicMock()

    driver.screenshot()
    driver.cleanup_start()

    assert not driver._screenshot_timeout.isActive()
    assert driver._screenshots_due == 0


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
    video.player.has_restarted = True
    video.render_context = MagicMock()
    video.render_context.update.return_value = False
    return video


@pytest.fixture
def renderer():
    made = VideoRenderer(MagicMock())
    made._gl = MagicMock()
    return made


def _round(renderer, video, *, is_frame, said_ago=0.0):
    video.needs_update = True
    video.update_said_at = time.monotonic() - said_ago
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


def test_a_frame_mpv_let_go_of_before_it_was_rendered_is_rendered(renderer):
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False, said_ago=0.25)

    assert video.render_context.render.call_count == 1

    # and just the once
    renderer._render_round()

    assert video.render_context.render.call_count == 1


def test_an_update_just_now_with_no_frame_has_lost_nothing(renderer):
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False)

    assert video.render_context.render.call_count == 0


def test_nothing_is_lost_until_the_video_has_started(renderer):
    video = _rendered_video()
    video.player.has_restarted = False
    renderer._videos.append(video)

    # drawn now it would be black, and taken for the first picture
    _round(renderer, video, is_frame=False, said_ago=0.25)

    assert video.render_context.render.call_count == 0

    video.player.has_restarted = True
    renderer._render_round()

    assert video.render_context.render.call_count == 1


def test_a_frame_that_came_after_all_is_rendered_once(renderer):
    video = _rendered_video()
    video.player.has_restarted = False
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False, said_ago=0.25)
    video.player.has_restarted = True
    _round(renderer, video, is_frame=True)

    assert video.render_context.render.call_count == 1

    renderer._render_round()

    assert video.render_context.render.call_count == 1


def test_a_restart_wakes_the_renderer_for_a_frame_held_back():
    player = _player()
    player._wake_renderer.reset_mock()

    assert not player.has_restarted

    ids = player._mpv_module.MpvEventID
    player._on_event(MagicMock(**{"event_id.value": ids.PLAYBACK_RESTART}))

    assert player.has_restarted
    assert player._wake_renderer.called


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


def test_manager_has_nobody_to_tell_of_skipping_frames_on_vlc():
    manager = VideoDriverManager(context=SimpleNamespace())

    manager.set_mpv_skip_frames(True)

    assert manager._mpv_render_service is None


def test_skipping_frames_goes_to_every_video_there_is(mocker):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    service = MpvRenderService()
    videos = [RenderedVideo(MagicMock()), RenderedVideo(MagicMock())]
    service._listeners = dict.fromkeys(videos)

    manager = VideoDriverManager(context=SimpleNamespace())
    manager._mpv_render_service = service
    manager.set_mpv_skip_frames(True)

    for video in videos:
        video.player.set_skip_frames.assert_called_once_with(True)


def test_manager_makes_no_render_service_for_vlc(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)

    manager = VideoDriverManager(context=SimpleNamespace())
    manager.video_driver()

    assert manager._mpv_render_service is None
