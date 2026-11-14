"""The sums and the bookkeeping of the mpv driver, with no libmpv. How it plays
is in tests/real_app/scenarios/mpv_basics.py."""

import ctypes
import logging
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.models.audio_device import AudioDevice
from gridplayer.models.audio_selection import (
    AudioDisabled,
    AudioExternal,
    AudioLanguage,
)
from gridplayer.models.chapter import Chapter
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleExternal,
    SubtitleTrackId,
)
from gridplayer.models.video import Video
from gridplayer.mpv_player import player as player_module
from gridplayer.mpv_player.conf import parse_conf
from gridplayer.mpv_player.deinterlace import deinterlace_options
from gridplayer.mpv_player.player import (
    _REFUSED_MODES,
    _ROOM_FILTER_BROKE,
    TIME_REPORT_MS,
    MpvPlayer,
    _AudioDevices,
    _cur_track_id,
    _params_sar,
    audio_chain,
    calc_fit_size,
    devices_of_first_output,
)
from gridplayer.mpv_player.quality import FAST, high_options
from gridplayer.mpv_player.renderer import (
    _DELETE_SYNC_PROTO,
    _FENCE_SYNC_PROTO,
    GL_BGRA,
    GL_RGBA,
    GL_RGBA8,
    OWN_WINDOW_START_TURN_MS,
    FrameFences,
    FrameSlot,
    MpvRenderService,
    RenderCalls,
    RenderedVideo,
    SoftwareRenderCalls,
    VideoRenderer,
    leaks_frame_fences,
)
from gridplayer.mpv_player.subtitles import (
    SubtitleView,
    subtitle_codepage,
    subtitle_limits,
    subtitle_options,
    subtitle_view,
)
from gridplayer.params.static import (
    AudioChannelMode,
    MpvCpuDecoding,
    MpvOutput,
    MpvPictureQuality,
    SeekAim,
    SeekPrecision,
    SubtitleOutline,
    VideoCellViewMode,
    VideoCrop,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoDriver,
    VideoTransform,
    ViewParams,
)
from gridplayer.params.subtitle_style import SUBTITLE_STYLE_DEFAULTS
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import (
    ViewPlacement,
    calc_full_size,
    calc_render_size,
)
from gridplayer.utils.log_config import DISABLED
from gridplayer.vlc_player.static import (
    DISABLED_TRACK,
    Media,
    MediaInput,
    StreamAudio,
    VideoTrack,
)
from gridplayer.widgets.video_frame_mpv import (
    MpvVideoSurface,
    VideoDriverMpv,
    VideoFrameMpv,
)


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


def test_surface_placement_follows_what_changes():
    surface = MpvVideoSurface()
    surface.resize(160, 90)
    surface.present_black(1920, 1080)
    surface.set_view(surface._view, VideoTransform.NONE, (1920, 1080))

    placed = surface.placement()
    assert surface.placement() is placed

    surface.resize(90, 90)
    assert surface.placement().target != placed.target

    surface.set_view(
        ViewParams(cell_view_mode=VideoCellViewMode.STRETCH),
        VideoTransform.NONE,
        (1920, 1080),
    )
    assert surface.placement().target == (0, 0, 90, 90)

    surface.present_black(960, 540)
    assert surface.placement().source == (0, 0, 960, 540)


def test_surface_paints_rgba_frames_as_they_are():
    surface = MpvVideoSurface()
    slot = FrameSlot()
    slot.writable(2, 1)[:] = bytes([255, 0, 0, 255, 0, 0, 255, 255])
    slot.is_rgba = True

    surface.present_frame(slot)

    image = surface.frame_image()
    assert image.pixelColor(0, 0).getRgb()[:3] == (255, 0, 0)
    assert image.pixelColor(1, 0).getRgb()[:3] == (0, 0, 255)


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


# what mpv 0.41 says its defaults are, of the options picture quality sets
_MPV_DEFAULTS = {
    "scale": "lanczos",
    "dscale": "hermite",
    "dither": "fruit",
    "correct-downscaling": True,
    "linear-downscaling": True,
    "sigmoid-upscaling": True,
    "hdr-compute-peak": "auto",
    "allow-delayed-peak-detect": False,
}
_HIGH = {
    "scale": "lanczos",
    "dscale": "hermite",
    "dither": "fruit",
    "correct-downscaling": "yes",
    "linear-downscaling": "yes",
    "sigmoid-upscaling": "yes",
    "hdr-compute-peak": "auto",
    "allow-delayed-peak-detect": "no",
}


class _FakeMpv:
    chapter_list = None
    mpv_version = "mpv v0.37.0"

    def __init__(self, **options):
        self.options = options
        self.commands = []
        self.callbacks = {}
        self.frame_says = "no"
        self.frames_read = 0
        self.time_says = "1.5"
        self.times_read = 0
        self.track_list = []
        self.audio_device_list = []
        self.is_terminated = False
        self.duration = 20.0
        self.event_callback = None
        self.observers = {}
        self._event_handle = "event handle"

    def register_event_callback(self, callback):
        self.event_callback = callback

    def observe_property(self, name, handler):
        self.observers[name] = handler

    def unobserve_property(self, name, handler):
        assert self.observers.pop(name) == handler

    def option_info(self, name):
        if name == "deinterlace":
            return {"type": "Choice", "choices": ["no", "yes", "auto"]}

        if name in _MPV_DEFAULTS:
            return {"type": "Flag", "default-value": _MPV_DEFAULTS[name]}

        return {"type": "Float"}

    def command(self, *args):
        self.commands.append(args)

    def command_async(self, *args, callback=None, **_kwargs):
        if args[:2] == ("expand-text", "${=time-pos:}"):
            self.times_read += 1
            callback(None, self.time_says)
            return

        if args[0] == "expand-text":
            self.frames_read += 1
            callback(None, self.frame_says)
            return

        self.commands.append(args)
        self.callbacks[args] = callback

    def terminate(self):
        self.is_terminated = True


def _mpv_module():
    return SimpleNamespace(
        MPV=lambda log_handler=None, loglevel=None, **options: _FakeMpv(**options),
        MpvEventID=SimpleNamespace(
            FILE_LOADED=8, PLAYBACK_RESTART=21, END_FILE=7, HOOK=25
        ),
        MpvEventEndFile=SimpleNamespace(ERROR=4),
        ShutdownError=RuntimeError,
        backend=MagicMock(),
    )


def _player(
    skip_frames=False,
    direct_rendering=True,
    is_software=False,
    is_live=False,
    is_audio_only=False,
    hwdec="auto",
    uri="file.mp4",
    media=None,
    cpu_when_low=False,
    wid=None,
    picture_quality=MpvPictureQuality.FAST,
    conf=None,
    **video,
):
    """`media`: more of the MediaInput."""

    media_input = MediaInput(
        uri=uri,
        is_live=is_live,
        is_audio_only=is_audio_only,
        size=(100, 100),
        video=Video(uri=uri, **video),
        **(media or {}),
    )
    return MpvPlayer(
        _mpv_module(),
        media_input,
        hwdec=hwdec,
        wake_renderer=MagicMock(),
        subtitle_style=SUBTITLE_STYLE_DEFAULTS,
        skip_frames=skip_frames,
        direct_rendering=direct_rendering,
        is_software=is_software,
        cpu_when_low=cpu_when_low,
        wid=wid,
        picture_quality=picture_quality,
        conf=conf,
    )


@pytest.fixture(autouse=True)
def _built_in_scripts_read(monkeypatch):
    """As if read already: reading makes an mpv of its own."""

    scripts = player_module._BuiltInScripts()
    scripts._options = {}
    monkeypatch.setattr(player_module, "_BUILT_IN_SCRIPTS_OFF", scripts)


@pytest.fixture(autouse=True)
def _no_refused_modes():
    _REFUSED_MODES.clear()

    yield

    _REFUSED_MODES.clear()


def _deinterlace_told(player):
    told = []

    for command in player.mpv.commands:
        if command[0] == "set" and command[1] in {"deinterlace", "hwdec"}:
            told.append(command[1:])
        elif command[:2] == ("vf", "set"):
            told.append(("vf", command[2]))

    return told


def _file_loaded(player):
    file_loaded = player._mpv_module.MpvEventID.FILE_LOADED

    player._on_event(SimpleNamespace(event_id=SimpleNamespace(value=file_loaded)))


def _restart(player):
    restart = player._mpv_module.MpvEventID.PLAYBACK_RESTART

    player._on_event(SimpleNamespace(event_id=SimpleNamespace(value=restart)))


_BY_NAME = {
    "deinterlace": VideoDeinterlace.ON,
    "deinterlace_mode": VideoDeinterlaceMode.YADIF,
}


def _filter_on_cpu():
    """A video playing with a mode by name, with nothing told yet to go by."""

    player = _player(**_BY_NAME)
    _file_loaded(player)
    player._on_hwdec("hwdec-current", "nvdec-copy")
    player.mpv.commands.clear()

    return player


def test_automatic_deinterlace_is_left_to_mpv():
    player = _player()

    player.start((100, 100))

    assert _deinterlace_told(player) == [("deinterlace", "auto")]


def test_deinterlace_starts_as_asked_with_nothing_told_that_is_already_so():
    player = _player(deinterlace=VideoDeinterlace.OFF)

    player.start((100, 100))

    assert _deinterlace_told(player) == []


def test_deinterlace_on_has_mpv_choose():
    player = _player(deinterlace=VideoDeinterlace.ON)

    player.start((100, 100))

    assert _deinterlace_told(player) == [("deinterlace", "yes")]


def test_deinterlace_mode_starts_decoding_to_the_cpu():
    player = _player(**_BY_NAME)

    assert player.mpv.options["hwdec"] == "auto-copy"


def test_deinterlace_mode_is_left_as_it_is_on_software():
    player = _player(hwdec="no", **_BY_NAME)

    assert player.mpv.options["hwdec"] == "no"

    _file_loaded(player)

    assert _deinterlace_told(player)[-1] == (
        "vf",
        "lavfi=[yadif=mode=send_frame]",
    )


def test_deinterlace_filter_waits_for_the_file():
    # a filter mpv can't start before that ends the file
    player = _player(**_BY_NAME)
    player._on_hwdec("hwdec-current", "nvdec-copy")

    player.start((100, 100))

    assert not any(told[0] == "vf" for told in _deinterlace_told(player))

    _file_loaded(player)

    assert ("vf", "lavfi=[yadif=mode=send_frame]") in _deinterlace_told(player)


def test_deinterlace_filter_waits_for_frames_off_the_gpu():
    # frames still on it stop the filter for good
    player = _player(deinterlace=VideoDeinterlace.OFF)
    _file_loaded(player)
    player._on_hwdec("hwdec-current", "nvdec")

    player.set_deinterlace(VideoDeinterlace.ON, VideoDeinterlaceMode.YADIF)

    assert _deinterlace_told(player) == [("hwdec", "auto-copy")]

    player._on_hwdec("hwdec-current", "nvdec-copy")

    assert _deinterlace_told(player)[-1] == ("vf", "lavfi=[yadif=mode=send_frame]")


def test_deinterlace_filter_goes_before_frames_go_back_on_the_gpu():
    player = _filter_on_cpu()

    player.set_deinterlace(VideoDeinterlace.OFF, VideoDeinterlaceMode.YADIF)

    assert _deinterlace_told(player) == [("vf", ""), ("hwdec", "auto")]


def test_deinterlace_filter_needs_no_report_from_a_decoder_with_no_hardware():
    # told to change, it stays as "no", and mpv can say None with nothing after it
    player = _player(deinterlace=VideoDeinterlace.OFF)
    _file_loaded(player)
    player._on_hwdec("hwdec-current", "no")
    player._on_hwdec("hwdec-current", None)
    player.mpv.commands.clear()

    player.set_deinterlace(VideoDeinterlace.ON, VideoDeinterlaceMode.YADIF)

    assert _deinterlace_told(player)[-1] == ("vf", "lavfi=[yadif=mode=send_frame]")


def test_only_a_filter_going_in_can_be_refused():
    player = _filter_on_cpu()

    player.set_deinterlace(VideoDeinterlace.OFF, VideoDeinterlaceMode.YADIF)

    assert player.mpv.callbacks["vf", "set", ""] is None


def test_a_filter_failing_as_the_video_closes_is_not_refused():
    player = _filter_on_cpu()
    player._is_closing = True

    player._on_filter_told(VideoDeinterlaceMode.YADIF, "shutting down", None)

    assert not _REFUSED_MODES


def test_deinterlace_mode_mpv_cannot_start_goes_to_its_own():
    player = _filter_on_cpu()

    player._on_filter_told(VideoDeinterlaceMode.YADIF, "no such filter", None)

    assert _deinterlace_told(player) == [
        ("deinterlace", "yes"),
        ("vf", ""),
        ("hwdec", "auto"),
    ]


def test_decoder_changing_on_an_open_file_goes_back_to_where_it_was():
    player = _player(deinterlace=VideoDeinterlace.OFF)
    _file_loaded(player)
    player.mpv.commands.clear()

    player.set_deinterlace(VideoDeinterlace.ON, VideoDeinterlaceMode.YADIF)

    assert player.mpv.commands == [
        ("set", "hwdec", "auto-copy"),
        ("seek", 0, "relative+exact"),
    ]


def test_decoder_changing_on_a_live_video_stays_where_it_is():
    player = _player(is_live=True, deinterlace=VideoDeinterlace.OFF)
    _file_loaded(player)
    player.mpv.commands.clear()

    player.set_deinterlace(VideoDeinterlace.ON, VideoDeinterlaceMode.YADIF)

    assert player.mpv.commands == [("set", "hwdec", "auto-copy")]


def test_a_filter_mpv_could_start_changes_nothing():
    player = _filter_on_cpu()

    player._on_filter_told(VideoDeinterlaceMode.YADIF, None, None)

    assert player.mpv.commands == []


def test_a_mode_refused_once_is_left_alone_by_later_videos():
    _filter_on_cpu()._on_filter_told(VideoDeinterlaceMode.YADIF, "no such filter", None)

    player = _player(**_BY_NAME)
    _file_loaded(player)
    player._on_hwdec("hwdec-current", "nvdec")

    assert player.mpv.options["hwdec"] == "auto"
    assert _deinterlace_told(player) == [("deinterlace", "yes")]


def test_a_mode_refused_leaves_the_others_as_they_are():
    player = _filter_on_cpu()
    player._on_filter_told(VideoDeinterlaceMode.IVTC, "no such filter", None)
    player.mpv.commands.clear()

    player.set_deinterlace(VideoDeinterlace.ON, VideoDeinterlaceMode.BOB)

    assert _deinterlace_told(player)[-1][0] == "vf"
    assert "separatefields" in _deinterlace_told(player)[-1][1]


@pytest.mark.parametrize(
    ("mode", "has_auto"),
    [
        (VideoDeinterlaceMode.AUTO, False),
        (VideoDeinterlaceMode.YADIF, False),
        (VideoDeinterlaceMode.YADIF, True),
    ],
)
def test_automatic_goes_by_the_frames_where_mpv_will_not(mode, has_auto):
    player = _player(deinterlace_mode=mode)
    player._has_auto_deinterlace = has_auto
    player._is_media_read = True
    _file_loaded(player)
    player._on_hwdec("hwdec-current", "no")
    player.mpv.commands.clear()

    player._on_time("time-pos", 1.0)

    assert _deinterlace_told(player) == []

    player.mpv.frame_says = "yes"
    player._on_time("time-pos", 2.0)

    assert _deinterlace_told(player)


def test_going_to_automatic_paused_asks_the_frame_on_show():
    # no time report is coming to go by
    player = _player(
        deinterlace=VideoDeinterlace.OFF, deinterlace_mode=VideoDeinterlaceMode.YADIF
    )
    _file_loaded(player)
    player.mpv.frame_says = "yes"

    player.set_deinterlace(VideoDeinterlace.AUTO, VideoDeinterlaceMode.YADIF)

    assert ("hwdec", "auto-copy") in _deinterlace_told(player)


def test_going_to_automatic_asks_again_once_the_deinterlacer_is_off():
    # the frame on show has been through it and doesn't say
    player = _filter_on_cpu()

    player.set_deinterlace(VideoDeinterlace.AUTO, VideoDeinterlaceMode.YADIF)

    assert _deinterlace_told(player) == [("vf", ""), ("hwdec", "auto")]

    player._on_hwdec("hwdec-current", "nvdec")
    player.mpv.frame_says = "yes"
    _restart(player)

    assert _deinterlace_told(player)[-1] == ("hwdec", "auto-copy")


def test_frames_are_not_asked_about_once_closing():
    player = _player(deinterlace_mode=VideoDeinterlaceMode.YADIF)
    player._is_media_read = True

    player.close()

    player._on_time("time-pos", 1.0)

    assert player.mpv.frames_read == 0


def test_terminating_waits_for_anything_being_sent():
    player = _player()
    player._is_closing = True
    terminated = threading.Event()
    player.mpv.terminate = terminated.set

    with player._telling:
        thread = threading.Thread(target=player._terminate)
        thread.start()

        assert not terminated.wait(0.05)

    thread.join()

    assert terminated.is_set()


def test_the_time_is_followed_only_while_paused():
    player = _player()

    assert "time-pos" not in player.mpv.observers

    player._on_pause("pause", True)
    assert player.mpv.observers["time-pos"] == player._on_time

    player._on_pause("pause", False)
    assert "time-pos" not in player.mpv.observers


def test_loaded_paused_the_time_is_followed():
    assert "time-pos" in _player(is_paused=True).mpv.observers


def test_the_time_is_read_while_playing():
    player = _player()
    player._is_media_read = True
    times = []
    player.time_changed.connect(times.append)

    assert player._time_reads.interval() == TIME_REPORT_MS

    player._read_time()
    player.mpv.time_says = "1.6"
    # read when asked, however soon after the last
    player._read_time()

    assert times == [1501, 1601]


@pytest.mark.parametrize("says", ["", "(error)"])
def test_no_time_to_read_reports_nothing(says):
    player = _player()
    player._is_media_read = True
    player.mpv.time_says = says
    times = []
    player.time_changed.connect(times.append)

    player._read_time()

    assert times == []


def test_the_time_is_not_read_while_paused_or_before_loading():
    player = _player()

    player._read_time()
    player._is_media_read = True
    player._on_pause("pause", True)
    player._read_time()

    assert player.mpv.times_read == 0


def test_the_time_is_read_as_a_seek_lands():
    player = _player()
    player._is_media_read = True

    _restart(player)

    assert player.mpv.times_read == 1


def test_a_time_standing_still_is_said_only_where_a_seek_landed():
    player = _player()
    player._is_media_read = True
    times = []
    player.time_changed.connect(times.append)

    player._read_time()
    # a stream waiting for more
    player._read_time()
    # a seek landing where it was
    _restart(player)

    assert times == [1501, 1501]


@pytest.mark.parametrize("is_stopped", [True, False])
def test_a_live_stream_stopped_or_played_follows_the_time_as_paused(is_stopped):
    # mpv's pause is left as it was, so it won't say
    player = _player(is_live=True, is_paused=not is_stopped, uri="http://proxy/video")

    player._set_live_stopped(is_stopped)

    assert ("time-pos" in player.mpv.observers) is is_stopped


def test_closing_stops_reading_the_time():
    player = _player()

    player.close()

    assert not player._time_reads.isActive()


def test_automatic_left_to_mpv_reads_no_frames():
    player = _player()
    player._is_media_read = True

    player._on_time("time-pos", 1.0)

    assert player.mpv.frames_read == 0


def test_old_libmpv_is_not_told_automatic():
    with patch.object(_FakeMpv, "option_info", lambda _self, _name: {"type": "Flag"}):
        player = _player()

    player.start((100, 100))

    assert _deinterlace_told(player) == []


@pytest.mark.parametrize("mode", list(VideoDeinterlaceMode))
def test_every_deinterlace_mode_asks_for_something(mode):
    options = deinterlace_options(VideoDeinterlace.ON, mode, True, False)

    if mode == VideoDeinterlaceMode.AUTO:
        assert options == {"deinterlace": "yes", "vf": ""}
    else:
        assert options["deinterlace"] == "no"
        assert options["vf"].startswith("lavfi=[")


def test_chapters_are_read_with_the_media():
    player = _player()
    player.mpv.chapter_list = [
        {"title": "Intro", "time": 0.0},
        {"title": "Part One", "time": 15.0004},
        {"time": 30.5},
    ]

    media = player._media_from_tracks()

    assert media.chapters == (
        Chapter(start_ms=0, name="Intro"),
        Chapter(start_ms=15_000, name="Part One"),
        Chapter(start_ms=30_500),
    )


def test_chapters_arriving_after_the_load_are_sent_on():
    player = _player()
    player._media = player._media_from_tracks()
    player._is_media_read = True
    sent = []
    player.chapters_changed.connect(sent.append)

    player._on_chapter_list("chapter-list", [{"title": "One", "time": 5.0}])
    player._on_chapter_list("chapter-list", [{"title": "One", "time": 5.0}])

    assert len(sent) == 1
    assert sent[0].chapters == (Chapter(start_ms=5_000, name="One"),)


def test_chapters_arriving_after_the_load_keep_the_media_shared():
    # the frame sets the tracks chosen on this same one, for the driver and player to see
    player = _player()
    media = player._media_from_tracks()
    player._media = media
    player._is_media_read = True

    player._on_chapter_list("chapter-list", [{"title": "One", "time": 5.0}])

    assert player._media is media


def test_chapters_before_the_load_are_left_for_it_to_read():
    player = _player()
    sent = []
    player.chapters_changed.connect(sent.append)

    player._on_chapter_list("chapter-list", [{"title": "One", "time": 5.0}])

    assert sent == []


def _quality_sent(player) -> dict:
    return {c[1]: c[2] for c in player.mpv.commands if c[0] == "set" and c[1] in FAST}


def _playing_at(player, dims=(1920, 1080), shown=(1920, 1080)):
    """All of the picture on show."""

    player.start((100, 100))
    player._on_video_params("video-params", {"dw": dims[0], "dh": dims[1]})
    player.set_shown_size(shown, dims)


def test_it_starts_scaling_fast():
    options = _player(picture_quality=MpvPictureQuality.AUTO).mpv.options

    for name, value in FAST.items():
        assert options[name.replace("-", "_")] == value


def test_an_option_of_its_own_goes_before_fast(mocker):
    options = player_module.MpvPlayer._options
    mocker.patch.object(
        player_module.MpvPlayer,
        "_options",
        lambda self: {**options(self), "scale": "spline36"},
    )

    assert _player().mpv.options["scale"] == "spline36"


def test_high_is_what_mpv_has_by_default():
    player = _player(picture_quality=MpvPictureQuality.HIGH)
    player.start((100, 100))

    assert _quality_sent(player) == _HIGH
    assert player.is_scaling_high


def test_fast_holds_whatever_the_size():
    player = _player(picture_quality=MpvPictureQuality.FAST)
    _playing_at(player)

    assert _quality_sent(player) == {}
    assert not player.is_scaling_high


def test_auto_goes_by_the_size_shown():
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    _playing_at(player)

    assert _quality_sent(player) == _HIGH

    player.mpv.commands.clear()
    player.set_shown_size((960, 540), (1920, 1080))

    assert _quality_sent(player) == FAST


def test_auto_is_fast_until_the_sizes_are_known():
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    player.start((1920, 1080))
    player._on_video_params("video-params", {"dw": 1920, "dh": 1080})

    assert _quality_sent(player) == {}


def test_auto_keeps_fast_for_a_picture_shrunk_a_lot():
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    _playing_at(player, dims=(3840, 2160))

    assert _quality_sent(player) == {}

    player.set_shown_size((3840, 2160), (3840, 2160))

    assert _quality_sent(player) == _HIGH


def test_auto_goes_by_the_part_of_the_picture_on_show():
    # 4K zoomed in 4 times, over a 1080p window: made bigger, not smaller
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    _playing_at(player, dims=(3840, 2160))

    player.set_shown_size((1920, 1080), (960, 540))

    assert _quality_sent(player) == _HIGH


def test_auto_holds_high_a_little_past_the_line():
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    _playing_at(player)

    player.set_shown_size((1000, 900), (1920, 1080))
    assert player.is_scaling_high

    player.set_shown_size((900, 800), (1920, 1080))
    assert not player.is_scaling_high

    player.set_shown_size((1000, 900), (1920, 1080))
    assert not player.is_scaling_high


def test_auto_sends_nothing_while_the_level_stays():
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    _playing_at(player)
    player.mpv.commands.clear()

    player.set_shown_size((1900, 1060), (1920, 1080))

    assert _quality_sent(player) == {}


def test_the_level_changes_while_it_plays():
    player = _player(picture_quality=MpvPictureQuality.FAST)
    _playing_at(player)

    player.set_picture_quality(MpvPictureQuality.HIGH)

    assert _quality_sent(player) == _HIGH


def test_taking_up_high_or_leaving_it_is_said():
    player = _player(picture_quality=MpvPictureQuality.AUTO)
    said = []
    player.scaling_changed.connect(lambda: said.append(player.is_scaling_high))
    _playing_at(player, shown=(960, 540))

    player.set_shown_size((1920, 1080), (1920, 1080))
    player.set_shown_size((1910, 1070), (1920, 1080))
    player.set_shown_size((960, 540), (1920, 1080))

    assert said == [True, False]


def test_a_scaling_change_as_a_video_loads_is_heard(mocker):
    # the size kept from the last video takes High up as the player is made
    player = _player(picture_quality=MpvPictureQuality.HIGH)
    player._is_scaling_high = False
    mocker.patch("gridplayer.widgets.video_frame_mpv.MpvPlayer", return_value=player)
    heard = MagicMock()
    driver = VideoDriverMpv(
        render_service=MagicMock(),
        hwdec="auto",
        is_software=False,
        cpu_when_low=False,
        surface=MagicMock(),
        pane_box=lambda: (100, 100),
        full_size=lambda: (0, 0),
        is_on_show=lambda: True,
        on_scaling_changed=heard,
    )
    driver.set_shown_size((1920, 1080), (1920, 1080))

    driver.load_video(player.media_input)
    QApplication.processEvents()

    heard.assert_called_once()
    driver.cleanup_start()


def test_software_mpv_keeps_its_own_scaling():
    player = _player(is_software=True, picture_quality=MpvPictureQuality.HIGH)
    _playing_at(player)
    player.set_picture_quality(MpvPictureQuality.AUTO)

    assert _quality_sent(player) == {}


def test_high_keeps_fast_for_what_this_mpv_does_not_say():
    info = {"scale": {"default-value": "lanczos"}, "dither": {}}

    assert high_options(info.get) == {**FAST, "scale": "lanczos"}


def test_high_is_not_taken_up_where_this_mpv_says_nothing(mocker):
    mocker.patch.object(_FakeMpv, "option_info", return_value=None)
    player = _player(picture_quality=MpvPictureQuality.HIGH)
    _playing_at(player)

    assert _quality_sent(player) == {}
    assert not player.is_scaling_high


def _conf(text):
    return parse_conf(text)[0]


def _set_commands(player, name):
    return [c[2] for c in player.mpv.commands if c[:2] == ("set", name)]


def test_mpv_conf_goes_over_the_apps_own_as_it_starts():
    player = _player(conf=_conf("deband=yes\nvd-lavc-skipframe=nonref\n"))
    player.start((100, 100))

    sets = [c for c in player.mpv.commands if c[0] in ("set", "loadfile")]
    assert sets.index(("set", "deband", "yes")) < len(sets) - 1
    assert sets[-1][0] == "loadfile"
    assert _set_commands(player, "vd-lavc-skipframe") == ["nonref"]


def test_what_mpv_conf_set_the_app_leaves_alone():
    player = _player(
        picture_quality=MpvPictureQuality.AUTO, conf=_conf("scale=spline36")
    )
    _playing_at(player)

    player.set_shown_size((960, 540), (1920, 1080))
    player.set_skip_frames(True)

    assert _set_commands(player, "scale") == ["spline36"]


def test_the_decoder_of_mpv_conf_gives_way_to_deinterlacing(mocker):
    mocker.patch.object(player_module.MpvPlayer, "_apply_deinterlace")
    player = _player(conf=_conf("hwdec=nvdec"))
    player._deinterlace_options["vf"] = "bwdif"

    player.start((100, 100))

    assert _set_commands(player, "hwdec") == []


def test_the_decoder_of_mpv_conf_can_be_set_again_by_the_app():
    player = _player(conf=_conf("hwdec=nvdec"))
    player.start((100, 100))

    player.set_option("hwdec", "auto-copy")

    assert _set_commands(player, "hwdec")[-2:] == ["nvdec", "auto-copy"]


def test_a_value_mpv_wont_take_is_skipped(mocker, caplog):
    def command(self, *args):
        if args == ("set", "deband", "maybe"):
            raise ValueError("invalid value")
        self.commands.append(args)

    mocker.patch.object(_FakeMpv, "command", command)
    player = _player(conf=_conf("deband=maybe\ndither=no"))

    with caplog.at_level(logging.WARNING):
        player.start((100, 100))

    assert _set_commands(player, "dither")[-1] == "no"
    assert "BAD_VALUE: deband=maybe" in caplog.text
    assert "deband" not in player._conf_names


def test_mpv_conf_is_read_only_while_it_is_on(mocker):
    made = mocker.patch("gridplayer.widgets.video_frame_mpv.MpvPlayer")
    mocker.patch("gridplayer.widgets.video_frame_mpv.conf_lines", return_value=["line"])
    media_input = _player().media_input
    settings = {"player/mpv_conf": True, "player/video_init_timeout": 120}
    mocker.patch.object(Settings(), "get", side_effect=settings.get)
    driver = _driver()

    driver.load_video(media_input)
    driver.cleanup_start()
    assert made.call_args.kwargs["conf"] == ["line"]

    settings["player/mpv_conf"] = False
    driver.load_video(media_input)
    driver.cleanup_start()
    assert made.call_args.kwargs["conf"] is None


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


def test_options_on_linux_try_pulse_before_pipewires_own(monkeypatch):
    """mpv's PipeWire output starts slow on a sink gone to sleep."""

    monkeypatch.setattr(player_module.env, "IS_LINUX", True)

    assert _player().mpv.options["ao"] == "pulse,pipewire,alsa"


def test_options_into_its_own_window_on_windows(monkeypatch):
    monkeypatch.setattr(player_module.env, "IS_WINDOWS", True)

    options = _player(wid=1234).mpv.options

    assert options["vo"] == "gpu"
    assert options["gpu_api"] == "d3d11"
    assert options["wid"] == 1234
    # the overlay over it takes the mouse
    assert options["input_cursor"] is False
    assert options["cursor_autohide"] == "no"
    # the render API's
    assert "video_timing_offset" not in options


def test_options_into_its_own_window_lay_the_line_out_by_all_of_the_picture():
    # mpv 0.37 shrank it as much again as the picture went past the window
    options = _player(wid=1234).mpv.options

    assert options["sub_use_margins"] is False
    assert options["sub_scale_with_window"] is False


def test_options_into_its_own_window_leave_the_decoder_s_spare_frames_to_mpv():
    # with none, d3d11va runs out on AV1 and mpv goes from decoder to decoder
    assert "hwdec_extra_frames" not in _player(wid=1234).mpv.options


def test_options_into_its_own_window_elsewhere_leave_the_api_to_mpv(monkeypatch):
    monkeypatch.setattr(player_module.env, "IS_WINDOWS", False)

    assert "gpu_api" not in _player(wid=1234).mpv.options


def test_options_through_the_render_api_by_default():
    options = _player().mpv.options

    assert options["vo"] == "libmpv"
    assert "wid" not in options


def test_options_start_where_it_was_left():
    assert _player(current_position=5000).mpv.options["start"] == "5.0"
    assert "start" not in _player().mpv.options


def test_options_start_paused():
    assert _player(is_paused=True).mpv.options["pause"] is True


def test_options_skip_frames_only_when_asked():
    assert _player().mpv.options["vd_lavc_skipframe"] == "default"
    assert _player(skip_frames=True).mpv.options["vd_lavc_skipframe"] == "nonref"


def test_direct_rendering_is_left_to_mpv_unless_turned_off():
    assert "vd_lavc_dr" not in _player().mpv.options
    assert _player(direct_rendering=False).mpv.options["vd_lavc_dr"] == "no"


def _knowing(*names):
    started = []

    def make(**options):
        reader = MagicMock(options=list(names))
        started.append((options, reader))
        return reader

    return SimpleNamespace(MPV=make), started


def test_built_in_scripts_are_left_out_of_those_mpv_has():
    module, started = _knowing(
        "vo", "load-stats-overlay", "load-osd-console", "load-auto-profiles"
    )

    off = player_module._BuiltInScripts().off(module)

    assert off == {
        "load_stats_overlay": False,
        "load_osd_console": False,
        "load_auto_profiles": False,
    }
    ((options, reader),) = started
    assert options["load_scripts"] is False
    reader.terminate.assert_called_once()


def test_built_in_scripts_take_the_consoles_new_name_where_there_is_one():
    module, _ = _knowing(
        "load-console", "load-osd-console", "load-select", "load-context-menu"
    )

    off = player_module._BuiltInScripts().off(module)

    assert off == {
        "load_console": False,
        "load_select": False,
        "load_context_menu": False,
    }


def test_built_in_scripts_are_read_once():
    module, started = _knowing("load-select")
    scripts = player_module._BuiltInScripts()

    scripts.off(module)
    scripts.off(module)

    assert len(started) == 1


def test_built_in_scripts_left_on_when_mpv_wont_start():
    module = SimpleNamespace(MPV=MagicMock(side_effect=RuntimeError("no")))

    assert player_module._BuiltInScripts().off(module) == {}


def test_built_in_scripts_left_on_when_mpv_wont_say_its_options():
    reader = MagicMock()
    type(reader).options = property(MagicMock(side_effect=RuntimeError("no")))
    module = SimpleNamespace(MPV=lambda **_options: reader)

    assert player_module._BuiltInScripts().off(module) == {}
    reader.terminate.assert_called_once()


def test_the_audio_devices_are_read_without_the_built_in_scripts(
    monkeypatch, audio_devices
):
    scripts = player_module._BuiltInScripts()
    scripts._options = {"load_select": False}
    monkeypatch.setattr(player_module, "_BUILT_IN_SCRIPTS_OFF", scripts)
    module, made = _device_reader(_PULSE_LISTED)

    audio_devices.read(module)

    assert made[0].options["load_select"] is False


def test_options_leave_the_built_in_scripts_out(monkeypatch):
    scripts = player_module._BuiltInScripts()
    scripts._options = {"load_select": False}
    monkeypatch.setattr(player_module, "_BUILT_IN_SCRIPTS_OFF", scripts)

    assert _player().mpv.options["load_select"] is False


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


def _video_tracks(player):
    player.mpv.track_list = [
        {"type": "video", "id": 1, "demux-w": 640, "demux-h": 360, "codec": "h264"}
    ]


def test_own_window_is_held_before_making_its_output():
    player = _player(wid=5)
    _video_tracks(player)
    due = MagicMock()
    player.output_due.connect(due)
    continued = player._mpv_module.backend.mpv_hook_continue

    _preloaded(player)

    continued.assert_not_called()
    due.assert_called_once_with(player)

    player.let_output_start()
    player.let_output_start()

    assert _hook_answered(player)


@pytest.mark.parametrize("kind", ["render API", "no picture", "audio only", "closing"])
def test_held_only_into_its_own_window_with_a_picture(kind):
    player = _player(wid=None if kind == "render API" else 5)
    if kind != "no picture":
        _video_tracks(player)
    if kind == "audio only":
        player.media_input.is_audio_only = True
    if kind == "closing":
        player.close()
    due = MagicMock()
    player.output_due.connect(due)

    _preloaded(player)

    assert _hook_answered(player)
    due.assert_not_called()


def test_own_window_held_is_stopped_before_it_goes_on_as_it_closes():
    # let go of as it is, it would make its output on its way out
    player = _player(wid=5)
    _video_tracks(player)
    _preloaded(player)
    player.close()

    assert not player.let_output_start()
    player._mpv_module.backend.mpv_hook_continue.assert_not_called()
    last_told = _last_told_on_answer(player)

    player._terminate()

    assert last_told == [("stop",)]
    assert _hook_answered(player)
    assert player.mpv.is_terminated


def _last_told_on_answer(player):
    """What mpv was last told as each hook was answered."""

    last_told = []
    player._mpv_module.backend.mpv_hook_continue.side_effect = lambda *_: (
        last_told.append(player.mpv.commands[-1])
    )

    return last_told


def test_closing_as_its_file_opens_it_s_stopped_before_it_goes_on():
    # let go on as it is, it would make its output alongside the one whose turn it is
    player = _player(wid=5)
    _video_tracks(player)
    last_told = _last_told_on_answer(player)
    player.close()

    _preloaded(player)

    assert last_told == [("stop",)]
    assert _hook_answered(player)


def test_terminating_as_its_file_opens_nothing_more_is_sent():
    player = _player(wid=5)
    _video_tracks(player)
    player.close()
    player._terminate()

    _preloaded(player)

    assert ("stop",) not in player.mpv.commands
    assert _hook_answered(player)


def test_live_stream_paused_while_held_is_let_go_of_stopped():
    player = _player(wid=5, is_live=True)
    _video_tracks(player)
    _preloaded(player)
    last_told = _last_told_on_answer(player)

    player.set_pause(True)

    assert last_told == [("stop",)]
    assert _hook_answered(player)
    # its turn passes at once
    assert not player.let_output_start()


def test_own_window_says_when_its_output_is_up():
    player = _player(wid=5)
    up = MagicMock()
    player.output_done.connect(up)

    player.mpv.observers["vo-configured"]("vo-configured", False)
    up.assert_not_called()
    player.mpv.observers["vo-configured"]("vo-configured", True)
    up.assert_called_once_with()

    assert "vo-configured" not in _player().mpv.observers


def _playing_in_own_window():
    """Into its own window, its output made, with two video tracks."""

    player = _player(wid=5)
    player.mpv.track_list = [
        {"type": "video", "id": track_id, "demux-w": 640, "demux-h": 360}
        for track_id in (1, 2)
    ]
    _preloaded(player)
    player.let_output_start()
    _vo_configured(player, True)
    player._media = player._media_from_tracks()

    due = MagicMock()
    player.output_due.connect(due)
    done = MagicMock()
    player.output_done.connect(done)

    return player, due, done


def _vo_configured(player, is_configured):
    player.mpv.observers["vo-configured"]("vo-configured", is_configured)


def _vid_told(player):
    return [command for command in player.mpv.commands if command[:2] == ("set", "vid")]


def test_own_window_video_turned_off_lets_go_of_its_output_in_its_turn():
    player, due, done = _playing_in_own_window()

    player.select_track("vid", DISABLED_TRACK)

    due.assert_called_once_with(player)
    assert _vid_told(player) == []

    assert player.let_output_start()
    assert _vid_told(player) == [("set", "vid", "no")]

    _vo_configured(player, True)
    done.assert_not_called()
    _vo_configured(player, False)
    done.assert_called_once_with()


def test_own_window_video_turned_on_again_makes_its_output_in_its_turn():
    player, due, done = _playing_in_own_window()
    player.select_track("vid", DISABLED_TRACK)
    player.let_output_start()
    _vo_configured(player, False)
    due.reset_mock()
    done.reset_mock()

    player.select_track("vid", 2)

    due.assert_called_once_with(player)
    assert _vid_told(player) == [("set", "vid", "no")]

    assert player.let_output_start()
    assert _vid_told(player)[-1] == ("set", "vid", "2")

    _vo_configured(player, True)
    done.assert_called_once_with()


def test_own_window_another_video_track_keeps_its_output():
    player, due, _done = _playing_in_own_window()

    player.select_track("vid", 2)

    due.assert_not_called()
    assert _vid_told(player) == [("set", "vid", "2")]


def test_own_window_video_turned_off_and_on_before_its_turn_passes_it():
    player, _due, _done = _playing_in_own_window()

    player.select_track("vid", DISABLED_TRACK)
    player.select_track("vid", 1)

    assert not player.let_output_start()
    assert ("set", "vid", "no") not in _vid_told(player)


def test_own_window_video_turned_off_as_it_s_held_makes_no_output():
    player = _player(wid=5)
    _video_tracks(player)
    _preloaded(player)
    player._media = player._media_from_tracks()
    due = MagicMock()
    player.output_due.connect(due)

    player.select_track("vid", DISABLED_TRACK)

    due.assert_not_called()
    assert _vid_told(player) == [("set", "vid", "no")]
    # let go on, its turn passing at once
    assert not player.let_output_start()
    assert _hook_answered(player)


def test_own_window_video_turned_off_with_its_output_gone_passes_its_turn():
    # a live stream stopped as it was paused
    player, _due, _done = _playing_in_own_window()
    _vo_configured(player, False)

    player.select_track("vid", DISABLED_TRACK)

    assert not player.let_output_start()
    assert _vid_told(player) == [("set", "vid", "no")]


def test_own_window_live_stream_stopped_sets_the_track_due_at_once():
    player, _due, _done = _playing_in_own_window()
    player.media_input.is_live = True
    player.select_track("vid", DISABLED_TRACK)

    player.set_pause(True)

    assert ("set", "vid", "no") in _vid_told(player)
    assert not player.let_output_start()


def test_own_window_held_wants_its_output_up_before_it_goes_on():
    player, _due, done = _playing_in_own_window()
    player.select_track("vid", DISABLED_TRACK)
    player.let_output_start()
    _vo_configured(player, False)
    done.reset_mock()
    player.select_track("vid", 1)
    player._mpv_module.backend.mpv_hook_continue.reset_mock()
    _preloaded(player)
    # mpv's thread says its output is up as soon as it's let go on
    player._mpv_module.backend.mpv_hook_continue.side_effect = lambda *_: (
        _vo_configured(player, True)
    )

    assert player.is_output_held
    assert player.let_output_start()
    assert not player.is_output_held
    done.assert_called_once_with()


def test_video_track_picked_before_the_tracks_are_read_is_set_at_once():
    player = _player(wid=5)
    due = MagicMock()
    player.output_due.connect(due)

    player.select_track("vid", 1)

    due.assert_not_called()
    assert _vid_told(player) == [("set", "vid", "1")]


def test_video_turned_off_and_on_at_once_through_the_render_api():
    player = _player()
    _video_tracks(player)
    player._media = player._media_from_tracks()
    due = MagicMock()
    player.output_due.connect(due)

    player.select_track("vid", DISABLED_TRACK)
    player.select_track("vid", 1)

    due.assert_not_called()
    assert _vid_told(player) == [("set", "vid", "no"), ("set", "vid", "1")]


def test_random_start_is_picked_before_anything_is_decoded():
    player = _player(is_start_random=True)

    player._mpv_module.backend.mpv_hook_add.assert_called_once()

    _preloaded(player)

    assert 0 <= float(player.mpv.start) <= 20
    assert float(player.mpv.start) * 1000 == pytest.approx(
        player.media_input.initial_time
    )
    assert _hook_answered(player)


def test_only_a_random_start_picks_a_start():
    for player in (_player(), _player(is_start_random=True, current_position=5000)):
        _preloaded(player)

        assert not hasattr(player.mpv, "start")
        assert _hook_answered(player)


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


def _driver(full_size=lambda: (0, 0), is_on_show=lambda: True):
    return VideoDriverMpv(
        render_service=MagicMock(),
        hwdec="auto",
        is_software=False,
        cpu_when_low=False,
        surface=MagicMock(),
        pane_box=lambda: (100, 100),
        full_size=full_size,
        is_on_show=is_on_show,
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


def _seeking(monkeypatch, precision, at_ms=22_000):
    """A two-minute video at a time, seeking as the setting says."""

    monkeypatch.setattr(
        "gridplayer.widgets.video_frame_mpv.Settings",
        lambda: SimpleNamespace(get=lambda _key: precision),
    )
    driver = _driver_playing()
    driver._media.length = 120_000

    if at_ms is not None:
        driver._on_time(at_ms)

    return driver


def test_the_frame_passes_on_what_a_seek_is_for():
    # VLC's frame, which it's made of, tells its driver the time alone
    frame = SimpleNamespace(video_driver=MagicMock())

    VideoFrameMpv.set_time(frame, 5000, SeekAim.HAND)

    frame.video_driver.set_time.assert_called_once_with(5000, SeekAim.HAND)


def test_the_last_time_reported_goes_on_to_the_block(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.EXACT, at_ms=None)
    told = []
    driver.time_changed.connect(told.append)

    driver._on_time(5000)

    assert told == [5000]


@pytest.mark.parametrize("aim", list(SeekAim))
def test_every_seek_is_exact_when_set_so(monkeypatch, aim):
    driver = _seeking(monkeypatch, SeekPrecision.EXACT)

    driver.set_time(27_000, aim)

    assert driver._player.mpv.commands == [("seek", 27.0, "absolute+exact")]


@pytest.mark.parametrize("precision", list(SeekPrecision))
def test_a_frame_step_or_a_synced_seek_is_always_exact(monkeypatch, precision):
    driver = _seeking(monkeypatch, precision)

    driver.set_time(27_000, SeekAim.EXACT)

    assert driver._player.mpv.commands == [("seek", 27.0, "absolute+exact")]


def test_a_seek_by_hand_lands_on_the_key_frame_before_it(monkeypatch):
    # short of it, as VLC lands, and never past the end
    driver = _seeking(monkeypatch, SeekPrecision.EXACT_MARKS)

    driver.set_time(27_000, SeekAim.HAND)

    assert driver._player.mpv.commands == [("seek", 27.0, "absolute+keyframes")]


def _taken(player):
    """mpv has the last seek: it says so in turn with its events."""

    command = player.mpv.commands[-1]
    player.mpv.callbacks[command](None, None)


def test_one_forwards_is_looked_at_once_mpv_has_it(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.EXACT_MARKS)

    driver.set_time(27_000, SeekAim.HAND)

    assert driver._player._forward_seek is None

    _taken(driver._player)

    assert driver._player._forward_seek == (22.0, 27.0)


def test_one_backwards_is_not(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.EXACT_MARKS)

    driver.set_time(17_000, SeekAim.HAND)

    assert driver._player.mpv.callbacks[driver._player.mpv.commands[-1]] is None


def test_seeks_one_after_another_go_from_the_last_one(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.EXACT_MARKS)

    driver.set_time(27_000, SeekAim.HAND)
    driver.set_time(32_000, SeekAim.HAND)
    _taken(driver._player)

    assert driver._player._forward_seek == (27.0, 32.0)


def _landed(player, at_s):
    player.mpv.time_pos = at_s
    _restart(player)


def _forwards(player, at_s, exact_s, from_s):
    player.seek_key_frame(at_s, exact_s, from_s=from_s)
    _taken(player)


def test_forwards_landing_where_it_was_or_behind_goes_there_exactly():
    # 3 s on from 19 s, with a key frame every 6 s, was 18 s, and pressed again,
    # 18 s again: a seek key would go nowhere
    player = _player()
    _forwards(player, 22.0, 21.98, from_s=19.0)

    _landed(player, 18.0)

    assert player.mpv.commands[-1] == ("seek", 21.98, "absolute+exact")


def test_forwards_landing_further_on_stays():
    player = _player()
    _forwards(player, 27.0, 26.98, from_s=19.0)

    _landed(player, 24.0)

    assert player.mpv.commands == [("seek", 27.0, "absolute+keyframes")]


def test_it_is_looked_at_the_once():
    player = _player()
    _forwards(player, 22.0, 21.98, from_s=19.0)
    _landed(player, 18.0)

    _landed(player, 18.0)

    assert len(player.mpv.commands) == 2


def test_the_one_before_landing_after_the_next_is_made_says_nothing():
    # the first lands, behind where the second goes from, before mpv has the second
    player = _player()
    player.seek_key_frame(22.0, 21.98, from_s=19.0)
    player.seek_key_frame(25.0, 24.98, from_s=22.0)
    first_taken = player.mpv.callbacks[("seek", 22.0, "absolute+keyframes")]
    first_taken(None, None)

    _landed(player, 18.0)

    assert player.mpv.commands[-1] == ("seek", 25.0, "absolute+keyframes")


def test_an_exact_seek_after_it_leaves_nothing_to_look_at():
    player = _player()
    player.seek_key_frame(22.0, 21.98, from_s=19.0)

    player.seek_exact(40.0)
    taken_late = player.mpv.callbacks[("seek", 22.0, "absolute+keyframes")]
    taken_late(None, None)
    _landed(player, 40.0)

    assert player.mpv.commands[-1] == ("seek", 40.0, "absolute+exact")
    assert player._forward_seek is None


def test_a_seek_by_hand_from_nowhere_known_lands_before_it(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.FAST, at_ms=None)

    driver.set_time(27_000, SeekAim.HAND)

    assert driver._player.mpv.commands == [("seek", 27.0, "absolute+keyframes")]


def test_a_bookmark_or_chapter_is_exact_unless_all_are_fast(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.EXACT_MARKS)

    driver.set_time(30_000, SeekAim.MARK)

    assert driver._player.mpv.commands == [("seek", 30.0, "absolute+exact")]


def test_a_fast_bookmark_lands_short_of_it_never_past(monkeypatch):
    driver = _seeking(monkeypatch, SeekPrecision.FAST, at_ms=10_000)

    driver.set_time(30_000, SeekAim.MARK)

    assert driver._player.mpv.commands == [("seek", 30.0, "absolute+keyframes")]


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
    video.player.is_drawn.return_value = True
    video.player.has_restarted = True
    video.render_context = MagicMock()
    video.render_context.update.return_value = False
    video.render_calls = MagicMock()
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

    video.render_calls.draw.assert_not_called()
    assert not video.has_fresh_frame

    _round(renderer, video, is_frame=True)

    video.render_calls.draw.assert_called_once()
    assert video.has_fresh_frame


def test_a_frame_before_the_size_is_rendered_once_the_size_comes(renderer):
    video = _rendered_video(size=None)
    renderer._videos.append(video)

    _round(renderer, video, is_frame=True)
    video.render_calls.draw.assert_not_called()

    video.player.render_size.return_value = (4, 2)
    renderer._render_round()

    video.render_calls.draw.assert_called_once()


def test_a_new_size_is_rendered_with_no_new_frame(renderer):
    video = _rendered_video()
    renderer._videos.append(video)
    _round(renderer, video, is_frame=True)

    video.player.render_size.return_value = (8, 4)
    renderer._render_round()

    assert video.render_calls.draw.call_count == 2
    assert video.rendered_size == (8, 4)


def test_a_frame_mpv_let_go_of_before_it_was_rendered_is_rendered(renderer):
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False, said_ago=0.25)

    assert video.render_calls.draw.call_count == 1

    # and just the once
    renderer._render_round()

    assert video.render_calls.draw.call_count == 1


def test_an_update_just_now_with_no_frame_has_lost_nothing(renderer):
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False)

    assert video.render_calls.draw.call_count == 0


def test_nothing_is_lost_until_the_video_has_started(renderer):
    video = _rendered_video()
    video.player.has_restarted = False
    renderer._videos.append(video)

    # drawn now it would be black, and taken for the first picture
    _round(renderer, video, is_frame=False, said_ago=0.25)

    assert video.render_calls.draw.call_count == 0

    video.player.has_restarted = True
    renderer._render_round()

    assert video.render_calls.draw.call_count == 1


def test_a_frame_that_came_after_all_is_rendered_once(renderer):
    video = _rendered_video()
    video.player.has_restarted = False
    renderer._videos.append(video)

    _round(renderer, video, is_frame=False, said_ago=0.25)
    video.player.has_restarted = True
    _round(renderer, video, is_frame=True)

    assert video.render_calls.draw.call_count == 1

    renderer._render_round()

    assert video.render_calls.draw.call_count == 1


def _drawn(video) -> int:
    return video.render_calls.draw.call_count


def _taken_not_drawn(video) -> int:
    return video.render_calls.skip.call_count


def _hidden_after_its_first_frame(renderer):
    video = _rendered_video()
    renderer._videos.append(video)
    _round(renderer, video, is_frame=True)

    video.player.is_drawn.return_value = False
    renderer._gl.reset_mock()

    return video


def test_hidden_its_frames_are_taken_and_not_drawn(renderer):
    """Not taken, mpv waits 200 ms on each, and the video crawls."""

    video = _hidden_after_its_first_frame(renderer)
    video.latest()

    for _ in range(3):
        _round(renderer, video, is_frame=True)

    assert _taken_not_drawn(video) == 3
    assert _drawn(video) == 1
    renderer._gl.glReadPixels.assert_not_called()
    assert not video.has_fresh_frame


def test_hidden_with_no_new_frame_nothing_is_asked_of_mpv(renderer):
    video = _hidden_after_its_first_frame(renderer)

    renderer._render_round()
    _round(renderer, video, is_frame=False, said_ago=0.25)
    video.player.render_size.return_value = (8, 4)
    renderer._render_round()

    assert _drawn(video) == 1
    assert _taken_not_drawn(video) == 0


def test_hidden_before_its_first_frame_it_is_drawn(renderer):
    """A cell has loaded once it has a picture: one added out of sight too."""

    video = _rendered_video()
    video.player.is_drawn.return_value = False
    renderer._videos.append(video)

    _round(renderer, video, is_frame=True)

    assert _drawn(video) == 1
    assert video.has_fresh_frame


def test_on_show_again_the_last_frame_taken_is_drawn_at_once(renderer):
    video = _hidden_after_its_first_frame(renderer)
    _round(renderer, video, is_frame=True)

    video.player.is_drawn.return_value = True
    renderer._render_round()

    assert _drawn(video) == 2
    assert video.has_fresh_frame

    # and just the once
    renderer._render_round()

    assert _drawn(video) == 2


def test_on_show_again_with_nothing_taken_meanwhile_nothing_is_drawn(renderer):
    video = _hidden_after_its_first_frame(renderer)

    video.player.is_drawn.return_value = True
    renderer._render_round()

    assert _drawn(video) == 1


def test_frames_are_drawn_only_on_show_or_for_a_screenshot():
    player = _player()
    assert player.is_drawn()

    player.set_on_show(False)
    assert not player.is_drawn()

    player.hold_render_size((1920, 1080))
    assert player.is_drawn()

    player.hold_render_size(None)
    assert not player.is_drawn()


def test_going_out_of_sight_and_back_wakes_the_renderer_only_when_new():
    player = _player()
    player._wake_renderer.reset_mock()

    player.set_on_show(True)
    player._wake_renderer.assert_not_called()

    player.set_on_show(False)
    player.set_on_show(False)
    player.set_on_show(True)

    assert player._wake_renderer.call_count == 2


def test_a_video_loaded_out_of_sight_starts_out_of_sight(mocker):
    made = mocker.patch("gridplayer.widgets.video_frame_mpv.MpvPlayer")
    driver = _driver(is_on_show=lambda: False)

    driver.load_video(_player().media_input)

    made.return_value.set_on_show.assert_called_once_with(False)


def test_going_out_of_sight_is_passed_on_to_the_player():
    driver = _driver()
    driver._player = _player()

    driver.set_on_show(False)

    assert not driver._player.is_on_show


def test_going_out_of_sight_with_no_player_does_nothing():
    _driver().set_on_show(False)


def test_a_restart_wakes_the_renderer_for_a_frame_held_back():
    player = _player()
    player._wake_renderer.reset_mock()

    assert not player.has_restarted

    ids = player._mpv_module.MpvEventID
    player._on_event(MagicMock(**{"event_id.value": ids.PLAYBACK_RESTART}))

    assert player.has_restarted
    assert player._wake_renderer.called


def _gl_output(renderer, *videos):
    renderer.is_gl_output = True
    for number, video in enumerate(videos):
        for at, slot in enumerate(video.slots()):
            slot.texture = 10 * (number + 1) + at
        renderer._videos.append(video)


def test_with_gl_output_frames_go_out_as_textures_finished_once_a_round(renderer):
    """Drawn by Qt's contexts, a texture has to be finished before it's shown."""

    first, second = _rendered_video(), _rendered_video()
    _gl_output(renderer, first, second)
    finished_before = []
    renderer._gl.glFinish.side_effect = lambda: finished_before.append(
        (first.has_fresh_frame, second.has_fresh_frame)
    )

    for video in (first, second):
        video.needs_update = True
        video.render_context.update.return_value = True
    renderer._render_round()

    renderer._gl.glFinish.assert_called_once()
    assert finished_before == [(False, False)]
    assert first.has_fresh_frame
    assert second.has_fresh_frame
    renderer._gl.glReadPixels.assert_not_called()

    # drawn into the back one, which goes round to the front
    shown = first.latest()
    assert shown.texture == 10
    assert (shown.width, shown.height) == (4, 2)


def test_with_gl_output_a_texture_is_sized_again_only_for_a_new_size(renderer):
    video = _rendered_video()
    _gl_output(renderer, video)

    # the GUI taking each, so all three go round
    for _ in range(4):
        _round(renderer, video, is_frame=True)
        video.latest()

    # three slots, each sized once
    assert renderer._gl.glTexImage2D.call_count == 3

    video.player.render_size.return_value = (8, 4)
    _round(renderer, video, is_frame=True)

    assert renderer._gl.glTexImage2D.call_count == 4


def test_read_back_nothing_is_finished(renderer):
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=True)

    renderer._gl.glFinish.assert_not_called()
    renderer._gl.glReadPixels.assert_called_once()


@pytest.mark.parametrize(
    ("is_gles", "extensions", "read", "texture", "is_rgba"),
    [
        (False, b"", GL_BGRA, GL_RGBA8, False),
        (True, b"GL_OES_x GL_EXT_read_format_bgra", GL_BGRA, GL_RGBA, False),
        (True, b"GL_OES_x", GL_RGBA, GL_RGBA, True),
    ],
)
def test_read_back_takes_what_opengl_es_gives(
    renderer, is_gles, extensions, read, texture, is_rgba
):
    renderer._context = SimpleNamespace(is_gles=is_gles)
    renderer._gl.glGetString.return_value = extensions
    renderer._pick_formats()
    video = _rendered_video()
    renderer._videos.append(video)

    _round(renderer, video, is_frame=True)

    assert renderer._gl.glReadPixels.call_args.args[4] == read
    assert renderer._gl.glTexImage2D.call_args.args[2] == texture
    assert video.latest().is_rgba is is_rgba


def test_the_texture_on_show_can_be_taken_as_its_video_goes(renderer):
    video = _rendered_video()
    _gl_output(renderer, video)
    _round(renderer, video, is_frame=True)
    shown = video.latest().texture

    assert not video.take_shown_texture(shown + 1)
    assert not video.take_shown_texture(0)
    assert video.take_shown_texture(shown)

    renderer._free_video(video)

    deleted = {
        call.args[1]._obj.value for call in renderer._gl.glDeleteTextures.call_args_list
    }
    assert deleted == {10, 11, 12} - {shown}


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
    good.render_calls.draw.assert_called_once()


# python-mpv's types as libmpv sees them, as it can't be loaded here
class _Param(ctypes.Structure):
    _fields_ = [("type_id", ctypes.c_int), ("data", ctypes.c_void_p)]

    TYPES = {"opengl_fbo": (3, None), "flip_y": (4, bool)}
    TYPES.update(block_for_target_time=(12, bool), skip_rendering=(13, bool))


class _FBO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ("fbo", "w", "h", "internal_format")]

    def __init__(self, w, h, fbo=0, internal_format=0):
        super().__init__(fbo, w, h, internal_format)


def _what_libmpv_is_told(params) -> dict:
    told = {}

    for param in params:
        if param.type_id == 0:
            return told

        if param.type_id == 3:
            fbo = _FBO.from_address(param.data)
            told[3] = {"fbo": fbo.fbo, "w": fbo.w, "h": fbo.h}
        else:
            told[param.type_id] = ctypes.c_int.from_address(param.data).value

    raise AssertionError("no end to the parameters")


@pytest.fixture
def render_calls():
    told = []
    module = SimpleNamespace(
        MpvRenderParam=_Param,
        MpvOpenGLFBO=_FBO,
        _mpv_render_context_render=lambda handle, params: told.append(
            (handle, _what_libmpv_is_told(params))
        ),
    )

    return RenderCalls(module, MagicMock(handle="handle"), fbo=7), told


def test_a_frame_is_drawn_as_python_mpv_would_ask(render_calls):
    calls, told = render_calls

    calls.draw(640, 360)
    calls.draw(320, 180)

    assert told == [
        ("handle", {3: {"fbo": 7, "w": 640, "h": 360}, 4: 0, 12: 0}),
        ("handle", {3: {"fbo": 7, "w": 320, "h": 180}, 4: 0, 12: 0}),
    ]


def test_a_frame_is_taken_not_drawn_as_python_mpv_would_ask(render_calls):
    calls, told = render_calls

    calls.skip()

    assert told == [("handle", {13: 1, 12: 0})]


def _what_software_is_told(params) -> dict:
    told = {}

    for param in params:
        if param.type_id == 0:
            return told

        if param.type_id == 17:
            told["size"] = tuple((ctypes.c_int * 2).from_address(param.data))
        elif param.type_id == 18:
            told["format"] = ctypes.string_at(param.data)
        elif param.type_id == 19:
            told["stride"] = ctypes.c_size_t.from_address(param.data).value
        elif param.type_id == 20:
            told["pixels"] = param.data
        else:
            told[param.type_id] = ctypes.c_int.from_address(param.data).value

    raise AssertionError("no end to the parameters")


def _software_calls():
    told = []
    module = SimpleNamespace(
        MpvRenderParam=_Param,
        _mpv_render_context_render=lambda handle, params: told.append(
            _what_software_is_told(params)
        ),
    )

    return SoftwareRenderCalls(module, MagicMock(handle="handle")), told


def test_software_draws_into_the_pixels_it_is_given():
    calls, told = _software_calls()
    pixels = FrameSlot().writable(640, 360)

    calls.draw(640, 360, ctypes.addressof(pixels))
    calls.draw(320, 180, 1234)

    # opaque, as Qt paints the fourth byte as it finds it
    assert told == [
        {
            "size": (640, 360),
            "format": b"bgra",
            "stride": 2560,
            "pixels": ctypes.addressof(pixels),
            12: 0,
        },
        {"size": (320, 180), "format": b"bgra", "stride": 1280, "pixels": 1234, 12: 0},
    ]


def test_software_takes_a_frame_without_drawing_it():
    calls, told = _software_calls()

    calls.skip()

    assert told == [{13: 1, 12: 0}]


def test_software_renders_straight_into_the_back_frame():
    renderer = VideoRenderer(MagicMock(), is_software=True)
    video = _rendered_video((8, 4))
    video.has_new_frame = True
    renderer._videos.append(video)

    renderer._render_round()

    width, height, pixels = video.render_calls.draw.call_args.args
    assert (width, height) == (8, 4)
    # handed over to the GUI's side as it's done
    assert video.latest().width == 8
    assert pixels == ctypes.addressof(video.latest()._pixels_ctypes)


def test_software_has_no_gl_context(mocker):
    made = mocker.patch("gridplayer.mpv_player.renderer.create_gl_context")
    renderer = VideoRenderer(MagicMock(), is_software=True)
    renderer._is_stopping = True

    renderer.run()

    made.assert_not_called()


def _service_making_renderers(mocker):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    started = mocker.patch.object(
        MpvRenderService,
        "_start_renderer",
        side_effect=lambda sw: MagicMock(is_software=sw),
    )

    return MpvRenderService(), started


def test_the_renderer_is_of_the_kind_of_the_first_video(mocker):
    service, started = _service_making_renderers(mocker)

    service.add(RenderedVideo(MagicMock(), is_software=True), MagicMock())
    service.add(RenderedVideo(MagicMock(), is_software=True), MagicMock())

    assert [call.args for call in started.call_args_list] == [(True,)]
    assert service._renderer.add.call_count == 2

    # a driver change reloads, which cleans up before the others come
    service.cleanup()
    service.add(RenderedVideo(MagicMock()), MagicMock())

    assert started.call_args_list[-1].args == (False,)


def test_a_video_of_another_kind_with_no_cleanup_gets_a_renderer_of_its_kind(mocker):
    service, _ = _service_making_renderers(mocker)
    service.add(RenderedVideo(MagicMock(), is_software=True), MagicMock())
    software_renderer = service._renderer

    service.add(RenderedVideo(MagicMock()), MagicMock())

    software_renderer.stop.assert_called_once()
    assert service._renderer.is_software is False


@pytest.mark.parametrize(
    ("driver", "cpu_decoding", "hwdec", "is_software", "cpu_when_low"),
    [
        (VideoDriver.MPV_HW, MpvCpuDecoding.OFF, "auto", False, False),
        (VideoDriver.MPV_HW, MpvCpuDecoding.AUTO, "auto", False, True),
        (VideoDriver.MPV_HW, MpvCpuDecoding.ON, "no", False, False),
        (VideoDriver.MPV_SW, MpvCpuDecoding.OFF, "no", True, False),
    ],
)
def test_manager_picks_how_mpv_decodes_and_draws(
    mocker, driver, cpu_decoding, hwdec, is_software, cpu_when_low
):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    mocker.patch.object(MpvRenderService, "_join_qt_share_group", return_value=None)
    settings = {"player/mpv_cpu_decoding": cpu_decoding}
    mocker.patch.object(Settings(), "get", side_effect=settings.get)

    frame = VideoDriverManager(context=SimpleNamespace())._mpv_video_frame(driver)

    assert frame.keywords["hwdec"] == hwdec
    assert frame.keywords["is_software"] is is_software
    assert frame.keywords["cpu_when_low"] is cpu_when_low


@pytest.mark.parametrize(
    ("driver", "platform", "frame_class"),
    [
        (VideoDriver.MPV_HW, "windows", "VideoFrameMpvWindow"),
        # libmpv's software renderer has no window of its own to draw into
        (VideoDriver.MPV_SW, "windows", "VideoFrameMpv"),
        # no window to give mpv
        (VideoDriver.MPV_HW, "offscreen", "VideoFrameMpv"),
    ],
)
def test_manager_has_mpv_draw_into_its_own_windows_where_it_can(
    mocker, monkeypatch, driver, platform, frame_class
):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    mocker.patch.object(MpvRenderService, "_join_qt_share_group", return_value=None)
    monkeypatch.setattr("gridplayer.utils.video_driver.env.IS_WINDOWS", True)
    monkeypatch.setattr(
        "gridplayer.utils.video_driver._qt_platform_name", lambda: platform
    )
    settings = {
        "player/mpv_cpu_decoding": MpvCpuDecoding.OFF,
        "player/mpv_output": MpvOutput.WINDOW,
    }
    mocker.patch.object(Settings(), "get", side_effect=settings.get)

    frame = VideoDriverManager(context=SimpleNamespace())._mpv_video_frame(driver)

    assert frame.func.__name__ == frame_class


def test_a_video_s_render_calls_go_with_its_render_context(renderer):
    video = _rendered_video()
    renderer._videos.append(video)
    renderer._fbo = 1

    renderer._free_video(video)

    assert video.render_calls is None


# -- libmpv 0.40 and 0.41's fence a frame


@pytest.mark.parametrize(
    ("version", "leaks"),
    [
        ("v0.40.0", True),
        ("0.40.0", True),
        ("v0.40.0-3-gabc1234", True),
        ("v0.41.0", True),
        ("v0.41.0-112-gabc1234", True),
        # f74adc4 itself, and the test libmpv on Windows
        ("v0.41.0-113-gf74adc4", False),
        ("v0.41.0-1044-g14f2d48cb", False),
        ("v0.42.0", False),
        ("v0.39.0", False),
        ("v0.37.0", False),
        ("", False),
        (None, False),
    ],
)
def test_libmpv_versions_that_leave_a_fence_a_frame(version, leaks):
    assert leaks_frame_fences(version) is leaks


class _GLSync:
    """glFenceSync and glDeleteSync standing in, as C functions."""

    def __init__(self):
        self.made = []
        self.deleted = []
        self._fence_sync = _FENCE_SYNC_PROTO(self._make)
        self._delete_sync = _DELETE_SYNC_PROTO(self.deleted.append)

    def _make(self, _condition, _flags):
        self.made.append(0x1000 + len(self.made))
        return self.made[-1]

    def addresses(self) -> tuple[int, int]:
        return tuple(
            ctypes.cast(fn, ctypes.c_void_p).value
            for fn in (self._fence_sync, self._delete_sync)
        )


def test_only_the_last_fence_of_a_frame_is_deleted():
    gl = _GLSync()
    fences = FrameFences(*gl.addresses())
    given = _FENCE_SYNC_PROTO(fences.address)

    given(0x9117, 0)
    fences.forget()
    # an upload's, then the frame's own
    assert given(0x9117, 0) == 0x1001
    given(0x9117, 0)
    fences.delete_last()

    assert gl.deleted == [0x1002]


def test_a_frame_with_no_fence_deletes_none():
    gl = _GLSync()
    fences = FrameFences(*gl.addresses())
    given = _FENCE_SYNC_PROTO(fences.address)

    given(0x9117, 0)
    fences.forget()
    fences.delete_last()
    fences.delete_last()

    assert gl.deleted == []


def _gl_context_with_sync(gl: _GLSync):
    fence_sync, delete_sync = gl.addresses()
    addresses = {b"glFenceSync": fence_sync, b"glDeleteSync": delete_sync}

    return MagicMock(get_proc_address=lambda name: addresses.get(name, 7))


@pytest.mark.parametrize(
    ("version", "is_wrapped"), [("v0.40.0", True), ("v0.42.0", False)]
)
def test_mpv_is_given_the_fence_keeper_only_where_it_leaks(
    monkeypatch, renderer, version, is_wrapped
):
    monkeypatch.setattr(player_module.env, "MPV_VERSION", version)
    gl = _GLSync()
    renderer._context = _gl_context_with_sync(gl)

    given = renderer._get_proc_address(None, b"glFenceSync")

    assert (given != gl.addresses()[0]) is is_wrapped
    assert renderer._get_proc_address(None, b"glFenceSync") == given
    assert renderer._get_proc_address(None, b"glFinish") == 7


def test_a_frame_s_fence_is_deleted_once_it_is_drawn(renderer):
    video = _rendered_video()
    renderer._videos.append(video)
    calls = MagicMock()
    renderer._frame_fences = calls.fences
    video.render_calls = calls.render_calls

    _round(renderer, video, is_frame=True)

    assert [name for name, *_ in calls.mock_calls] == [
        "fences.forget",
        "render_calls.draw",
        "fences.delete_last",
    ]


def test_a_frame_taken_out_of_sight_deletes_no_fence(renderer):
    video = _hidden_after_its_first_frame(renderer)
    renderer._frame_fences = MagicMock()

    _round(renderer, video, is_frame=True)

    assert _taken_not_drawn(video) == 1
    renderer._frame_fences.delete_last.assert_not_called()


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


def test_skipping_frames_goes_to_a_video_in_its_own_window_too(mocker):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    service = MpvRenderService()
    player = MagicMock()
    service.add_own_window(player)

    service.set_skip_frames(True)

    player.set_skip_frames.assert_called_once_with(True)


def test_own_window_kept_until_its_mpv_is_terminated(mocker):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    service = MpvRenderService()
    player = MagicMock()
    window = MagicMock()
    service.add_own_window(player)

    service.remove_own_window(player, window)

    window.deleteLater.assert_not_called()
    service.set_skip_frames(True)
    player.set_skip_frames.assert_not_called()

    service._forget_player(player)

    window.deleteLater.assert_called_once_with()
    assert player not in service._players_alive


def _own_window_starts(mocker, count, *, in_turn=True):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    mocker.patch("gridplayer.mpv_player.renderer.OWN_WINDOWS_START_IN_TURN", in_turn)
    service = MpvRenderService()
    players = [MagicMock() for _ in range(count)]

    for player in players:
        _held(service, player)

    # the first, once what made them is done
    service._start_turn.timeout.emit()

    return service, players, [player.let_output_start for player in players]


def _held(service, player=None):
    """A player added, and held as it's preloaded: what lets it go on."""

    player = player or MagicMock()
    service.add_own_window(player)
    service._queue_output(player)

    return player.let_output_start


def test_own_window_opens_its_file_at_once(mocker):
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    service = MpvRenderService()
    player = MagicMock()

    service.add_own_window(player)

    player.output_due.connect.assert_called_once_with(
        service._queue_output, Qt.QueuedConnection
    )
    assert not service._start_turn.isActive()


def test_own_window_closed_as_it_s_held_is_never_let_go_on(mocker):
    # it's stopped as it closes, see MpvPlayer._terminate
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    service = MpvRenderService()
    player = MagicMock()
    service.add_own_window(player)
    service.remove_own_window(player, MagicMock())

    service._queue_output(player)
    service._start_turn.timeout.emit()

    player.let_output_start.assert_not_called()


def test_own_window_first_starts_once_what_made_it_is_done(mocker):
    # a reload shows its cells after making their players: under X11, mpv
    # never shows its window if its parent is shown as it starts
    mocker.patch("gridplayer.mpv_player.renderer.load_mpv")
    service = MpvRenderService()

    start = _held(service)

    start.assert_not_called()
    assert service._start_turn.isActive()
    assert service._start_turn.interval() == 0

    service._start_turn.timeout.emit()

    start.assert_called_once_with()


def test_own_windows_start_one_at_a_time(mocker):
    service, players, starts = _own_window_starts(mocker, 3)

    starts[0].assert_called_once_with()
    starts[1].assert_not_called()

    # what an mpv says once its output is up, or it plays, or fails, or a
    # seek of one already playing
    service._on_started(players[1])
    starts[1].assert_not_called()

    service._on_started(players[0], "Player error", ())
    starts[1].assert_called_once_with()
    starts[2].assert_not_called()

    service._on_started(players[1])
    starts[2].assert_called_once_with()


def test_own_windows_start_together_where_they_needn_t_take_turns(mocker):
    # under X11, which never crashed: still once what made them is done
    service, players, starts = _own_window_starts(mocker, 3, in_turn=False)

    for start in starts:
        start.assert_called_once_with()
    players[0].output_done.connect.assert_not_called()
    assert not service._start_turn.isActive()

    start = _held(service)

    start.assert_not_called()
    service._start_turn.timeout.emit()
    start.assert_called_once_with()


def _closed_one_going(service):
    going = MagicMock()
    _held(service, going)
    service._start_turn.timeout.emit()
    service.remove_own_window(going, MagicMock())

    return going


@pytest.mark.parametrize("in_turn", [False, True])
def test_own_window_starts_once_one_closed_is_gone(mocker, in_turn):
    # the heap broke as one let go of its output and another set its own up:
    # glibc's under X11, Direct3D 11's on AMD under Windows
    service, _, _ = _own_window_starts(mocker, 0, in_turn=in_turn)
    going = _closed_one_going(service)

    start = _held(service)
    service._start_turn.timeout.emit()

    start.assert_not_called()
    assert service._start_turn.isActive()

    service._forget_player(going)
    service._start_turn.timeout.emit()

    start.assert_called_once_with()


def test_own_window_waits_for_one_closed_only_so_long(mocker):
    service, _, _ = _own_window_starts(mocker, 0, in_turn=False)
    _closed_one_going(service)
    mocker.patch("gridplayer.mpv_player.renderer.OWN_WINDOW_GONE_WAIT_MS", 0)

    start = _held(service)
    service._start_turn.timeout.emit()

    start.assert_called_once_with()


def test_own_window_video_track_turn_waits_only_for_its_output(mocker):
    # playing, it says it has restarted on a seek, whatever its output is doing
    service, _, _ = _own_window_starts(mocker, 0)
    player = MagicMock(is_output_held=False)

    _held(service, player)
    service._start_turn.timeout.emit()

    player.output_done.connect.assert_called_once()
    for signal in (player.playback_restarted, player.failed, player.end_reached):
        signal.connect.assert_not_called()


def test_own_window_lets_go_of_its_signals_once_its_turn_is_over(mocker):
    # mpv says playback restarted on every seek too, all its life
    service, players, _ = _own_window_starts(mocker, 2)
    signals = (
        players[0].output_done,
        players[0].playback_restarted,
        players[0].failed,
        players[0].end_reached,
    )

    for signal in signals:
        signal.connect.assert_called_once()
    players[1].output_done.connect.assert_not_called()

    service._on_started(players[0])

    for signal in signals:
        signal.disconnect.assert_called_once_with(signal.connect.return_value)
    players[1].output_done.connect.assert_called_once()

    service.cleanup()

    players[1].output_done.disconnect.assert_called_once()


def test_own_window_no_longer_held_passes_its_turn_at_once(mocker):
    # a live stream paused while it waited: it makes no output to wait for
    service, _, _ = _own_window_starts(mocker, 0)
    gone_on = [_held(service) for _ in range(3)]
    gone_on[0].return_value = False

    service._start_turn.timeout.emit()

    gone_on[0].assert_called_once_with()
    gone_on[1].assert_called_once_with()
    gone_on[2].assert_not_called()
    assert service._start_turn.interval() == OWN_WINDOW_START_TURN_MS


def test_own_window_starts_next_once_it_s_had_its_turn(mocker):
    service, _, starts = _own_window_starts(mocker, 2)

    assert service._start_turn.isActive()
    assert service._start_turn.interval() == OWN_WINDOW_START_TURN_MS

    service._start_turn.timeout.emit()

    starts[1].assert_called_once_with()


def test_own_window_closed_gives_up_its_turn_or_never_starts(mocker):
    service, players, starts = _own_window_starts(mocker, 3)

    service.remove_own_window(players[1], MagicMock())
    service.remove_own_window(players[0], MagicMock())

    # once what closed it is done: a reload's cells are shown after
    starts[2].assert_not_called()
    assert service._start_turn.isActive()
    assert service._start_turn.interval() == 0

    service._start_turn.timeout.emit()

    # and once those closed are gone
    starts[2].assert_not_called()
    service._forget_player(players[0])
    service._forget_player(players[1])
    service._start_turn.timeout.emit()

    starts[1].assert_not_called()
    starts[2].assert_called_once_with()


def test_own_window_starts_forgotten_on_cleanup(mocker):
    service, _, starts = _own_window_starts(mocker, 2)

    service.cleanup()
    assert not service._start_turn.isActive()
    start = _held(service)
    service._start_turn.timeout.emit()

    start.assert_called_once_with()
    starts[1].assert_not_called()


def test_manager_makes_no_render_service_for_vlc(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)

    manager = VideoDriverManager(context=SimpleNamespace())
    manager.video_driver()

    assert manager._mpv_render_service is None


# -- the sound


@pytest.fixture(autouse=True)
def audio_devices(monkeypatch):
    devices = _AudioDevices()
    monkeypatch.setattr(player_module, "_AUDIO_DEVICES", devices)
    _ROOM_FILTER_BROKE.clear()

    yield devices

    _ROOM_FILTER_BROKE.clear()


@pytest.fixture
def room_file(monkeypatch):
    monkeypatch.setattr("gridplayer.mpv_player.player._room_file", lambda: "room.sofa")


def _audio_player(track_list=(), **video_fields):
    player = _player(**video_fields)
    player.mpv.track_list = list(track_list)
    player.emitted = []
    player.tracks_changed.connect(player.emitted.append)

    return player


_VIDEO_TRACK = {"type": "video", "id": 1, "selected": True}
_ENGLISH = {"type": "audio", "id": 1, "lang": "eng", "selected": True}
_SPANISH = {"type": "audio", "id": 2, "lang": "spa", "default": True}
_FILE_TRACK = {"type": "audio", "id": 3, "external": True}
_FILE_TRACK_2 = {"type": "audio", "id": 4, "external": True}


def _option_sets(player):
    return [command[1:] for command in player.mpv.commands if command[0] == "set"]


def test_the_tracks_of_a_kind_are_told_apart():
    player = _audio_player(
        [
            _VIDEO_TRACK,
            _ENGLISH,
            _SPANISH,
            _FILE_TRACK,
            {"type": "sub", "id": 1, "lang": "eng", "forced": True},
            {"type": "sub", "id": 2, "external": True},
        ]
    )

    tracks = player._read_tracks()

    assert list(tracks.audio_tracks) == [1, 2, 3]
    assert tracks.external_audio_ids == (3,)
    assert tracks.cur_audio_track_id == 1
    assert tracks.external_subtitle_ids == (2,)
    assert tracks.default_subtitle_track_id == 1


@pytest.mark.parametrize(
    ("listed", "default"),
    [
        ([_ENGLISH, _SPANISH], 2),
        ([_ENGLISH], 1),
        # one of a file, picked and all, says nothing of the video's own
        ([_FILE_TRACK, _ENGLISH], 1),
        ([_FILE_TRACK], None),
    ],
)
def test_the_default_track_is_the_first_marked_or_the_first(listed, default):
    assert _audio_player(listed)._read_tracks().default_audio_track_id == default


def test_a_song_picture_is_no_video():
    player = _audio_player(
        [{"type": "video", "id": 1, "albumart": True, "selected": True}, _ENGLISH]
    )

    assert player._read_tracks().video_tracks == {}


def test_told_to_leave_the_picture_out_there_is_none():
    player = _player(is_audio_only=True)
    player.mpv.track_list = [_VIDEO_TRACK, _ENGLISH]

    media = player._media_from_tracks()

    assert media.video_tracks == {}
    assert media.cur_video_track_id is None
    assert media.is_audio_only


def test_nothing_asked_for_leaves_the_tracks_to_mpv():
    player = _audio_player([_VIDEO_TRACK, _ENGLISH, _SPANISH])

    player._pick_tracks()

    assert player.mpv.commands == []


def test_a_language_picks_its_track_before_it_starts():
    player = _audio_player(
        [_VIDEO_TRACK, _ENGLISH, _SPANISH], audio_selection=AudioLanguage(tag="spa")
    )

    player._pick_tracks()

    assert _option_sets(player) == [("aid", "2")]


def test_a_file_picked_answers_for_its_tracks():
    player = _audio_player(
        [_VIDEO_TRACK, _ENGLISH, _FILE_TRACK, _FILE_TRACK_2],
        audio_selection=AudioExternal(file="C:/a.mka", track=1),
    )

    player._pick_tracks()

    assert _option_sets(player) == [("aid", "4")]


def test_a_file_that_brought_nothing_goes_by_the_rest():
    player = _audio_player(
        [_VIDEO_TRACK, _ENGLISH], audio_selection=AudioExternal(file="C:/a.mka")
    )

    player._pick_tracks()

    assert player.mpv.commands == []


def test_sound_off_is_asked_for():
    player = _audio_player([_VIDEO_TRACK, _ENGLISH], audio_selection=AudioDisabled())

    player._pick_tracks()

    assert _option_sets(player) == [("aid", "no")]


@pytest.mark.parametrize(
    ("listed", "video"),
    [
        # a song: the picture isn't there to keep playing
        ([_ENGLISH], {}),
        # the picture off and the sound off, as saved
        ([_VIDEO_TRACK, _ENGLISH], {"video_track_id": -1}),
    ],
)
def test_sound_off_with_no_picture_would_leave_nothing_to_play(listed, video):
    player = _audio_player(listed, audio_selection=AudioDisabled(), **video)

    player._pick_tracks()

    assert ("aid", "no") not in _option_sets(player)


def test_sound_off_when_told_to_leave_the_picture_out():
    player = _player(is_audio_only=True, audio_selection=AudioDisabled())
    player.mpv.track_list = [_VIDEO_TRACK, _ENGLISH]

    player._pick_tracks()

    assert ("aid", "no") not in _option_sets(player)


def test_told_to_leave_the_picture_out_a_saved_track_doesnt_bring_it_back():
    player = _player(is_audio_only=True, video_track_id=1)
    player.mpv.track_list = [_VIDEO_TRACK, _ENGLISH]

    player._pick_tracks()

    assert not [one for one in _option_sets(player) if one[0] == "vid"]


def test_no_subtitles_to_switch_off_is_nothing_to_say():
    player = _audio_player([_VIDEO_TRACK, _ENGLISH])

    player._pick_tracks()

    assert ("sid", "no") not in _option_sets(player)


def test_a_picture_switched_off_stays_off_given_sound_to_play():
    player = _audio_player([_VIDEO_TRACK, _ENGLISH], video_track_id=-1)

    assert player._wanted_video_track_id(player._read_tracks()) == -1


def test_a_picture_is_kept_with_no_sound_to_play_instead():
    player = _audio_player([_VIDEO_TRACK], video_track_id=-1)

    assert player._wanted_video_track_id(player._read_tracks()) is None


def test_a_video_track_from_another_driver_is_left_out():
    # VLC counts all the tracks together, from 0
    player = _audio_player([_VIDEO_TRACK, _ENGLISH], video_track_id=0)

    assert player._wanted_video_track_id(player._read_tracks()) is None


def test_switched_off_and_none_there_are_not_the_same():
    assert _cur_track_id(None, {1: "a track"}) == -1
    assert _cur_track_id(None, {}) is None
    assert _cur_track_id(1, {1: "a track"}) == 1


_LISTED = [
    {"name": "auto", "description": "Autoselect device"},
    {"name": "alsa", "description": "Default (alsa)"},
    {"name": "alsa/hw:0", "description": "A card"},
    {"name": "pulse/one", "description": "Speakers"},
    {"name": "pulse/two", "description": "Headphones"},
    {"name": "jack", "description": "Default (jack)"},
]
_PULSE_LISTED = [one for one in _LISTED if "pulse" in one["name"]]


def test_devices_are_of_the_first_output_tried():
    assert devices_of_first_output(_LISTED, ("pipewire", "pulse", "alsa")) == (
        AudioDevice(id="pulse/one", name="Speakers"),
        AudioDevice(id="pulse/two", name="Headphones"),
    )


def test_devices_go_on_to_the_next_output():
    listed = [one for one in _LISTED if not one["name"].startswith("pulse")]

    assert devices_of_first_output(listed, ("pipewire", "pulse", "alsa")) == (
        AudioDevice(id="alsa/hw:0", name="A card"),
    )


def test_devices_of_the_first_listed_when_any_output_will_do():
    listed = [
        {"name": "auto", "description": "Autoselect device"},
        {"name": "wasapi/{a}", "description": "Speakers"},
        {"name": "openal", "description": "Default (openal)"},
    ]

    assert devices_of_first_output(listed) == (
        AudioDevice(id="wasapi/{a}", name="Speakers"),
    )


def test_no_devices_to_name():
    assert devices_of_first_output([{"name": "auto", "description": "Auto"}]) == ()


def _device_reader(listed=()):
    """An mpv module whose every mpv lists these, and the mpvs it has made."""

    made = []

    def make(**options):
        made.append(_FakeMpv(**options))
        made[-1].audio_device_list = list(listed)
        return made[-1]

    return SimpleNamespace(MPV=make), made


def test_a_videos_own_mpv_never_reads_the_devices():
    # it would stay connected to the sound server for as long as it lives
    module, made = _device_reader(_PULSE_LISTED)
    player = _audio_player()
    player._mpv_module = module

    player._pick_audio_device()

    assert len(made) == 1
    assert made[0] is not player.mpv
    assert made[0].is_terminated
    assert len(player._audio_devices) == 2


def test_a_grid_opening_shares_one_read(audio_devices):
    module, made = _device_reader(_PULSE_LISTED)

    first = audio_devices.read(module)
    second = audio_devices.read(module)

    assert first == second
    assert len(made) == 1


def test_the_devices_are_read_again_later(monkeypatch, audio_devices):
    module, made = _device_reader(_PULSE_LISTED)
    now = [100.0]
    monkeypatch.setattr("gridplayer.mpv_player.player.time.monotonic", lambda: now[0])

    audio_devices.read(module)
    now[0] += 60
    audio_devices.read(module)

    assert len(made) == 2


def test_devices_that_cant_be_read_are_none(audio_devices):
    def make(**_options):
        raise OSError("no")

    assert audio_devices.read(SimpleNamespace(MPV=make)) == ()


def test_a_device_gone_leaves_the_sound_where_it_is():
    player = _audio_player()
    player._audio_devices = (AudioDevice(id="pulse/one", name="Speakers"),)

    player.set_audio_device(AudioDevice(id="pulse/gone", name="Gone"))

    assert _option_sets(player) == []


def test_a_device_of_another_driver_is_found_by_name():
    player = _audio_player()
    player._audio_devices = (AudioDevice(id="pulse/one", name="Speakers"),)

    player.set_audio_device(AudioDevice(id="one", name="Speakers"))

    assert _option_sets(player) == [("audio-device", "pulse/one")]


def test_no_device_is_the_machines_own():
    player = _audio_player()

    player.set_audio_device(None)

    assert _option_sets(player) == [("audio-device", "auto")]


def test_the_device_picked_goes_in_before_the_sound_starts():
    module, _ = _device_reader(_PULSE_LISTED)
    wanted = AudioDevice(id="pulse/two", name="Headphones")
    player = _audio_player(audio_device=wanted)
    player._mpv_module = module

    player._pick_audio_device()

    assert player.mpv.audio_device == "pulse/two"


def test_the_channel_mode_is_told_once():
    player = _audio_player()

    player.set_channel_mode(AudioChannelMode.UNSET)
    assert player.mpv.commands == []

    player.set_channel_mode(AudioChannelMode.LEFT)
    player.set_channel_mode(AudioChannelMode.LEFT)

    sets = _option_sets(player)

    assert len(sets) == 2
    assert sets[0][0] == "af"
    assert "c0=c0|c1=c0" in sets[0][1]
    assert sets[1] == ("audio-channels", "stereo")


def test_a_file_added_comes_back_on_the_list():
    player = _audio_player(
        [_VIDEO_TRACK, _ENGLISH, _FILE_TRACK],
        audio_selection=AudioExternal(file="C:/a.mka"),
    )
    player._media = Media(
        length=1000,
        video_tracks={1: "kept"},
        audio_tracks={1: "before"},
        cur_audio_track_id=1,
        audio_devices=(AudioDevice(id="pulse/one"),),
    )

    player._on_audio_file_added(None, None)

    media = player.emitted[0]

    assert list(media.audio_tracks) == [1, 3]
    assert media.external_audio_ids == (3,)
    assert media.cur_audio_track_id == 3
    # what the file has nothing to do with stays as it was
    assert media.video_tracks == {1: "kept"}
    assert media.audio_devices == (AudioDevice(id="pulse/one"),)
    assert ("aid", "3") in _option_sets(player)


def test_a_file_that_failed_changes_nothing():
    # told of it, the frame would take it for a file that needs a reload to play
    player = _audio_player([_VIDEO_TRACK, _ENGLISH])
    player._media = Media(length=1000, video_tracks={}, audio_tracks={1: "before"})

    player._on_audio_file_added(SystemError("no"), None)

    assert player.emitted == []
    assert _option_sets(player) == []


def test_a_file_added_while_closing_is_nobodys_business():
    player = _audio_player([_VIDEO_TRACK, _ENGLISH])
    player._media = Media(length=1000, video_tracks={}, audio_tracks={})
    player.close()

    player._on_audio_file_added(None, None)

    assert player.emitted == []


def _track_driver(media):
    driver = _driver()
    driver._media = media
    driver._player = MagicMock()

    return driver


def _media_with(cur_video=1, cur_audio=1):
    return Media(
        length=1000,
        video_tracks={1: "picture"},
        audio_tracks={1: "sound", 2: "more"},
        cur_video_track_id=cur_video,
        cur_audio_track_id=cur_audio,
    )


def test_a_track_goes_to_mpv():
    driver = _track_driver(_media_with())

    driver.set_audio_track(2)

    driver._player.select_track.assert_called_once_with("aid", 2)


@pytest.mark.parametrize("track_id", [None, 7])
def test_a_track_not_there_is_not_asked_for(track_id):
    # mpv would take it, and play nothing
    driver = _track_driver(_media_with())

    driver.set_audio_track(track_id)
    driver.set_video_track(track_id)

    assert not driver._player.select_track.called


def test_the_sound_goes_off_with_a_picture_to_show():
    driver = _track_driver(_media_with())

    driver.set_audio_track(-1)

    driver._player.select_track.assert_called_once_with("aid", -1)


def test_the_sound_stays_with_no_picture():
    driver = _track_driver(_media_with(cur_video=-1))

    driver.set_audio_track(-1)

    assert not driver._player.select_track.called


def test_the_picture_stays_with_no_sound():
    driver = _track_driver(_media_with(cur_audio=-1))

    driver.set_video_track(-1)

    assert not driver._player.select_track.called


def test_a_track_list_that_changed_is_passed_on():
    driver = _track_driver(_media_with())
    driver.tracks_changed_emit = MagicMock()

    media = _media_with()
    driver._on_tracks_changed(media)

    assert driver._media is media
    driver.tracks_changed_emit.assert_called_once_with(media)


@pytest.mark.parametrize(
    ("delay_ms", "said"),
    [(0, "0.0"), (1500, "1.5"), (-250, "-0.25")],
)
def test_the_delay_is_in_seconds(delay_ms, said):
    driver = _track_driver(_media_with())

    driver.set_audio_delay(delay_ms)

    driver._player.set_option.assert_called_once_with("audio-delay", said)


def _one_channel(track):
    return dict(track, **{"demux-channel-count": 1})


def _levels(player):
    return [one for one in _option_sets(player) if one[0] == "audio-swresample-o"]


def test_a_stereo_mix_of_one_channel_keeps_its_level():
    chain = audio_chain(AudioChannelMode.UNSET, 1)

    assert "rematrix_volume" in chain["audio-swresample-o"]
    # left to a sound server, it can come out turned down all the same
    assert chain["audio-channels"] == "stereo"


def test_mono_goes_out_on_two_channels():
    chain = audio_chain(AudioChannelMode.MONO, 2)

    assert chain["audio-channels"] == "stereo"
    assert "c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1" in chain["af"]


def test_left_alone_a_track_of_more_goes_out_as_mpv_sees_fit():
    assert audio_chain(AudioChannelMode.UNSET, 6)["audio-channels"] == "auto-safe"


@pytest.mark.parametrize("track_channels", [0, 2, 6])
def test_nothing_else_is_raised(track_channels):
    chain = audio_chain(AudioChannelMode.STEREO, track_channels)

    assert chain["audio-swresample-o"] == ""


@pytest.mark.usefixtures("room_file")
def test_the_room_effect_is_for_a_surround_track():
    chain = audio_chain(AudioChannelMode.HEADPHONES, 6)

    assert "sofalizer=sofa=room.sofa" in chain["af"]
    assert chain["audio-channels"] == "stereo"


@pytest.mark.usefixtures("room_file")
@pytest.mark.parametrize(
    ("mode", "track_channels"),
    [
        # nothing to move about, as on VLC
        (AudioChannelMode.HEADPHONES, 2),
        (AudioChannelMode.HEADPHONES, 1),
        (AudioChannelMode.HEADPHONES, 0),
        (AudioChannelMode.STEREO, 6),
    ],
)
def test_otherwise_it_is_the_plain_mix(mode, track_channels):
    assert audio_chain(mode, track_channels)["af"] == ""


def test_no_file_for_the_room_effect_is_the_plain_mix(monkeypatch):
    monkeypatch.setattr("gridplayer.mpv_player.player._room_file", lambda: None)

    assert audio_chain(AudioChannelMode.HEADPHONES, 6)["af"] == ""


def test_the_room_file_is_only_looked_for_when_it_is_of_use(monkeypatch):
    # looking for libVLC on Linux with none there runs gcc and ld
    looked = MagicMock(return_value=None)
    monkeypatch.setattr("gridplayer.mpv_player.player._room_file", looked)

    audio_chain(AudioChannelMode.UNSET, 6)
    audio_chain(AudioChannelMode.HEADPHONES, 2)

    looked.assert_not_called()


def test_the_level_goes_by_the_track_picked_before_it_starts():
    player = _audio_player([_VIDEO_TRACK, _one_channel(_ENGLISH), _SPANISH])

    player._pick_tracks()

    # the first marked is what it will play, and that's two channels or not saying
    assert _levels(player) == []

    player = _audio_player(
        [_VIDEO_TRACK, _ENGLISH, _one_channel(_SPANISH)],
        audio_selection=AudioLanguage(tag="spa"),
    )

    player._pick_tracks()

    assert len(_levels(player)) == 1


def test_the_level_follows_a_track_switch():
    player = _audio_player()
    player._media = Media(
        length=1000,
        video_tracks={},
        audio_tracks={
            1: SimpleNamespace(channels=2),
            2: SimpleNamespace(channels=1),
        },
    )

    player.select_track("aid", 2)
    player.select_track("aid", 2)
    player.select_track("aid", 1)

    assert _option_sets(player) == [
        ("audio-swresample-o", "rematrix_volume=1.41421356"),
        ("audio-channels", "stereo"),
        ("aid", "2"),
        ("aid", "2"),
        ("audio-swresample-o", ""),
        ("audio-channels", "auto-safe"),
        ("aid", "1"),
    ]


@pytest.mark.usefixtures("room_file")
def test_a_room_filter_that_wont_start_gives_way_to_the_plain_mix():
    player = _audio_player()
    player._heard_channels = 6

    player.set_channel_mode(AudioChannelMode.HEADPHONES)

    assert "sofalizer" in dict(_option_sets(player))["af"]

    player.mpv.commands.clear()
    player._on_log("error", "ffmpeg", "Parsed_sofalizer_0: Can't find SOFA-file")

    assert _option_sets(player) == [("af", "")]


@pytest.mark.usefixtures("room_file")
def test_every_cell_with_the_filter_gives_way():
    players = [_audio_player(), _audio_player()]

    for player in players:
        player._heard_channels = 6
        player.set_channel_mode(AudioChannelMode.HEADPHONES)
        player.mpv.commands.clear()

    for player in players:
        player._on_log("error", "ffmpeg", "Parsed_sofalizer_0: Can't find SOFA-file")

    assert [_option_sets(player) for player in players] == [[("af", "")], [("af", "")]]


@pytest.mark.usefixtures("room_file")
def test_a_libmpv_without_the_filter_gives_way_too():
    player = _audio_player()
    player._heard_channels = 6
    player.set_channel_mode(AudioChannelMode.HEADPHONES)
    player.mpv.commands.clear()

    # FFmpeg made without libmysofa, as Homebrew's
    player._on_log("error", "ffmpeg", "AVFilterGraph: No such filter: 'sofalizer'")

    assert _option_sets(player) == [("af", "")]


@pytest.mark.parametrize(
    ("lib", "room"),
    [
        # Windows: beside libvlc.dll
        ("VLC/libvlc.dll", "VLC/hrtfs"),
        # macOS: VLC.app has it in share, beside its lib
        ("MacOS/lib/libvlc.dylib", "MacOS/share/hrtfs"),
    ],
)
def test_the_room_file_is_found_where_vlc_keeps_it(tmp_path, monkeypatch, lib, room):
    (tmp_path / lib).parent.mkdir(parents=True)
    (tmp_path / lib).touch()
    (tmp_path / room).mkdir(parents=True)
    (tmp_path / room / "dodeca_and_7channel_3DSL_HRTF.sofa").touch()
    monkeypatch.setattr(player_module, "find_libvlc", lambda: str(tmp_path / lib))
    player_module._room_file.cache_clear()

    try:
        found = player_module._room_file()
    finally:
        player_module._room_file.cache_clear()

    assert found is not None
    assert found.endswith(f"{room}/dodeca_and_7channel_3DSL_HRTF.sofa")


def test_an_error_that_only_has_the_word_in_it_is_something_else():
    _audio_player()._on_log("error", "cplayer", "Can not open file sofalizer.m4a")

    assert not _ROOM_FILTER_BROKE.is_set()


@pytest.mark.usefixtures("room_file")
def test_nor_is_it_tried_again_on_the_next_video():
    _audio_player()._on_log("error", "ffmpeg", "Parsed_sofalizer_0: no")

    assert audio_chain(AudioChannelMode.HEADPHONES, 6)["af"] == ""


# -- the subtitles


_OWN_SUB = {"type": "sub", "id": 1, "lang": "eng", "default": True, "codec": "subrip"}
_OTHER_SUB = {"type": "sub", "id": 2, "lang": "fre", "codec": "subrip"}


def _sub_file(track_id, path, **fields):
    return {
        "type": "sub",
        "id": track_id,
        "external": True,
        "external-filename": str(path),
        "title": "made up by mpv",
        **fields,
    }


def _sid_set(player):
    return [one[1] for one in _option_sets(player) if one[0] == "sid"]


def test_subtitles_start_off_with_tracks_to_switch_off():
    player = _audio_player([_VIDEO_TRACK, _OWN_SUB])

    player._pick_tracks()

    assert _sid_set(player) == ["no"]


def test_subtitle_marked_by_the_file_is_asked_for_by_name():
    player = _audio_player(
        [_VIDEO_TRACK, _OTHER_SUB, _OWN_SUB], subtitle_selection=SubtitleDefault()
    )

    player._pick_tracks()

    assert _sid_set(player) == ["1"]


def test_no_subtitle_marked_is_none_rather_than_mpvs_pick_of_a_file(tmp_path):
    player = _audio_player(
        [_VIDEO_TRACK, _OTHER_SUB, _sub_file(3, tmp_path / "a.srt")],
        subtitle_selection=SubtitleDefault(),
    )

    player._pick_tracks()

    assert _sid_set(player) == ["no"]


def test_a_file_never_counts_as_the_one_marked(tmp_path):
    player = _audio_player([_sub_file(1, tmp_path / "a.srt", default=True)])

    assert player._read_tracks().default_subtitle_track_id is None


def test_subtitle_picked_goes_by_its_file_not_where_it_comes_among_them(tmp_path):
    first, second = tmp_path / "a.srt", tmp_path / "b.srt"

    player = _audio_player(
        [_VIDEO_TRACK, _OWN_SUB, _sub_file(2, first), _sub_file(3, second)],
        subtitle_selection=SubtitleExternal(file=second),
    )

    player._pick_tracks()

    assert _sid_set(player) == ["3"]


def test_subtitle_picked_goes_by_its_place_in_its_file(tmp_path):
    index = tmp_path / "a.idx"

    player = _audio_player(
        [_VIDEO_TRACK, _sub_file(1, index), _sub_file(2, index)],
        subtitle_selection=SubtitleExternal(file=index, track=1),
    )

    player._pick_tracks()

    assert _sid_set(player) == ["2"]


def test_subtitle_kept_by_number_from_another_driver_goes_by_where_it_comes():
    player = _audio_player(
        [_VIDEO_TRACK, _OWN_SUB, _OTHER_SUB],
        subtitle_selection=SubtitleTrackId(id=4, position=1),
    )

    player._pick_tracks()

    assert _sid_set(player) == ["2"]


def test_a_title_mpv_made_for_a_file_is_nobodys(tmp_path):
    path = tmp_path / "a.srt"

    track = _audio_player([_sub_file(1, path)])._read_tracks().subtitle_tracks[1]

    assert track.description is None
    assert track.file == path


def test_subtitle_files_open_with_the_video_by_their_paths(tmp_path):
    path = tmp_path / "a b.idx"
    player = _player()
    player.media_input.selected_subtitle_slaves = (path.as_uri(),)

    player.start((100, 100))

    assert ("change-list", "sub-files", "append", str(path)) in player.mpv.commands


def test_a_subtitle_file_added_is_shown_once_it_has_said_what_it_brought(tmp_path):
    path = tmp_path / "a.srt"
    player = _audio_player(
        [_VIDEO_TRACK, _OWN_SUB], subtitle_selection=SubtitleExternal(file=path)
    )
    player._media = player._media_from_tracks()

    player.add_subtitle_file(path.as_uri())

    assert player.mpv.commands[-1] == ("sub-add", str(path), "auto")
    assert not _sid_set(player)

    player.mpv.track_list.append(_sub_file(2, path))
    player._on_subtitle_file_added(None, None)

    assert _sid_set(player) == ["2"]
    assert player.emitted[-1].external_subtitle_ids == (2,)
    assert player.emitted[-1].cur_subtitle_track_id == 2


def test_a_subtitle_file_with_nothing_in_it_changes_nothing(tmp_path):
    player = _audio_player([_VIDEO_TRACK, _OWN_SUB])
    player._media = player._media_from_tracks()

    player._on_subtitle_file_added(("Error running mpv command", -12), None)

    assert not player.emitted
    assert not _sid_set(player)


def test_subtitle_delay_and_character_set_start_with_it():
    player = _player(subtitle_delay_ms=1500, subtitle_encoding="Windows-1251")

    assert player.mpv.options["sub_delay"] == 1.5
    assert player.mpv.options["sub_codepage"] == "Windows-1251"


def test_no_character_set_named_is_left_to_mpv():
    assert "sub_codepage" not in _player().mpv.options


def test_a_character_set_of_seven_bits_is_taken_at_its_word():
    assert subtitle_codepage("ISO-2022-JP-2") == "+ISO-2022-JP-2"
    assert subtitle_codepage("KOI8-R") == "KOI8-R"


_STYLE = dict(SUBTITLE_STYLE_DEFAULTS)


def test_subtitle_style_of_nothing_touched_has_everything_to_go_back_to():
    options = subtitle_options(_STYLE, SubtitleView())

    assert options["sub-font"] == "sans-serif"
    assert options["sub-scale"] == "1.0000"
    assert options["sub-color"] == "#ffffff"
    assert options["sub-bold"] == "no"
    assert options["sub-border-style"] == "outline-and-shadow"
    assert options["sub-pos"] == "100.00"


@pytest.mark.parametrize(
    ("setting", "value", "option", "expected"),
    [
        ("subtitles/font", "Arial", "sub-font", "Arial"),
        ("subtitles/size_scale", 200, "sub-scale", "2.0000"),
        ("subtitles/color", "#ff0000", "sub-color", "#ff0000"),
        ("subtitles/bold", True, "sub-bold", "yes"),
        ("subtitles/outline", SubtitleOutline.NONE, "sub-outline-size", "0"),
        ("subtitles/outline_color", "#00ff00", "sub-outline-color", "#00ff00"),
        ("subtitles/shadow", False, "sub-shadow-offset", "0"),
        ("subtitles/shadow_color", "#0000ff", "sub-shadow-color", "#800000ff"),
        ("subtitles/background", True, "sub-border-style", "background-box"),
    ],
)
def test_subtitle_style_says_what_each_setting_asks(setting, value, option, expected):
    assert subtitle_options({**_STYLE, setting: value}, SubtitleView())[option] == (
        expected
    )


def test_subtitle_colour_that_isnt_one_is_the_usual():
    style = {**_STYLE, "subtitles/color": "not a colour"}

    assert subtitle_options(style, SubtitleView())["sub-color"] == "#ffffff"


def test_subtitle_raised_goes_for_what_mpv_doesnt_style_too():
    # sub-pos reaches ASS, where sub-margin-y doesn't
    style = {**_STYLE, "subtitles/margin": 72}

    assert subtitle_options(style, SubtitleView())["sub-pos"] == "90.00"


@pytest.mark.parametrize(
    ("picture_height", "frame_height", "expected"),
    [
        # a big picture in a small cell goes by the picture's pixels
        (720, 360, "90.00"),
        # a small picture in a big cell by the screen's
        (360, 720, "90.00"),
        (360, 360, "80.00"),
    ],
)
def test_subtitle_raised_goes_by_the_more_pixels(
    picture_height, frame_height, expected
):
    source = (0, 0, frame_height, frame_height)
    size = (frame_height, frame_height)
    view = subtitle_view(source, size, size, picture_height)

    style = {**_STYLE, "subtitles/margin": 72}

    assert subtitle_options(style, view)["sub-pos"] == expected


def test_subtitle_raised_past_the_top_stays_at_the_top():
    style = {**_STYLE, "subtitles/margin": 500}
    view = subtitle_view((0, 0, 360, 360), (360, 360), (360, 360), 360)

    assert subtitle_options(style, view)["sub-pos"] == "0.00"


def test_subtitle_side_margin_is_the_same_on_screen_zoomed_in():
    whole = SubtitleView()
    zoomed = subtitle_view((250, 250, 500, 500), (1000, 1000), (1000, 1000), 1000)

    def on_screen(view):
        options = subtitle_options(_STYLE, view)
        cut = zoomed.cut_off_each_side if view is zoomed else 0

        # what mpv draws it at, in the picture, then as much bigger as it's zoomed
        margin = int(options["sub-margin-x"]) * float(options["sub-scale"])

        return (margin - cut) / view.height

    assert on_screen(zoomed) == pytest.approx(on_screen(whole), abs=1)


# what each said, read from the real one: 0.37 is the oldest taken
_LIBMPV_OPTIONS = {
    "0.37": {
        "sub-margin-x": {"type": "Integer", "max": 300.0},
        "sub-pos": {"type": "Float"},
    },
    "0.40": {
        "sub-margin-x": {"type": "Integer", "max": 300.0},
        "sub-pos": {"type": "Float"},
        "sub-outline-size": {"type": "Float"},
        "sub-border-style": {"type": "Choice"},
    },
    "0.41": {
        "sub-margin-x": {"type": "Integer", "max": 2147483647.0},
        "sub-pos": {"type": "Float"},
        "sub-outline-size": {"type": "Float"},
        "sub-border-style": {"type": "Choice"},
    },
}


def _limits_of(version):
    return subtitle_limits(_LIBMPV_OPTIONS[version].get)


@pytest.mark.parametrize("version", ["0.37"])
def test_subtitle_outline_goes_by_its_old_name_on_an_old_libmpv(version):
    style = {
        **_STYLE,
        "subtitles/outline": SubtitleOutline.THICK,
        "subtitles/outline_color": "#00ff00",
    }

    options = subtitle_options(style, SubtitleView(), _limits_of(version))

    assert options["sub-border-size"] == "3"
    assert options["sub-border-color"] == "#00ff00"
    assert "sub-outline-size" not in options
    assert "sub-outline-color" not in options


@pytest.mark.parametrize("version", ["0.37"])
def test_subtitle_box_is_only_its_colour_on_an_old_libmpv(version):
    limits = _limits_of(version)

    plain = subtitle_options(_STYLE, SubtitleView(), limits)
    boxed = subtitle_options(
        {
            **_STYLE,
            "subtitles/background": True,
            "subtitles/background_color": "#123456",
        },
        SubtitleView(),
        limits,
    )

    assert "sub-border-style" not in plain
    assert plain["sub-back-color"] == "#00000000"
    assert boxed["sub-back-color"] == "#FF123456"


def test_subtitle_box_colour_is_only_there_with_a_box():
    style = {**_STYLE, "subtitles/background_color": "#123456"}

    plain = subtitle_options(style, SubtitleView())
    boxed = subtitle_options({**style, "subtitles/background": True}, SubtitleView())

    assert plain["sub-back-color"] == "#00000000"
    assert boxed["sub-back-color"] == "#FF123456"


@pytest.mark.parametrize(
    ("version", "expected"), [("0.37", 300), ("0.40", 300), ("0.41", 665)]
)
def test_subtitle_side_margin_stays_in_what_this_libmpv_takes(version, expected):
    # zoomed in twice, a video of 16:9
    view = subtitle_view((480, 270, 960, 540), (1920, 1080), (1920, 1080), 1080)

    options = subtitle_options(_STYLE, view, _limits_of(version))

    assert int(options["sub-margin-x"]) == expected


def test_subtitle_options_on_the_newest_are_as_they_are_with_no_limits():
    assert subtitle_options(_STYLE, SubtitleView(), _limits_of("0.41")) == (
        subtitle_options(_STYLE, SubtitleView())
    )


def test_subtitle_options_a_player_sends_are_for_its_libmpv():
    player = _player()
    player._subtitle_limits = _limits_of("0.37")

    player.start((100, 100))

    told = dict(_option_sets(player))

    assert "sub-border-size" in told
    assert "sub-outline-size" not in told


def test_subtitle_size_of_nothing_in_a_hand_edited_file_is_the_least_there_is():
    style = {**_STYLE, "subtitles/size_scale": 0}

    assert subtitle_options(style, SubtitleView())["sub-scale"] == "0.1000"


def test_subtitle_margins_dont_grow_with_its_size():
    plain = subtitle_options(_STYLE, SubtitleView())
    double = subtitle_options({**_STYLE, "subtitles/size_scale": 200}, SubtitleView())

    assert int(double["sub-margin-y"]) == int(plain["sub-margin-y"]) / 2
    assert int(double["sub-margin-x"]) == round(int(plain["sub-margin-x"]) / 2)


def test_subtitle_stays_in_what_is_on_show():
    # a frame 1000 high with 500 of it on show, ending at 750
    view = subtitle_view((0, 250, 1000, 500), (1000, 1000), (1000, 1000), 1000)
    options = subtitle_options(_STYLE, view)

    assert options["sub-pos"] == "75.00"
    assert options["sub-scale"] == "0.5000"


def test_subtitle_keeps_inside_what_is_cut_off_the_sides():
    whole = subtitle_options(
        _STYLE, subtitle_view((0, 0, 1000, 1000), (1000, 1000), (1000, 1000), 1000)
    )
    cut = subtitle_options(
        _STYLE, subtitle_view((250, 0, 500, 1000), (1000, 1000), (1000, 1000), 1000)
    )

    # a quarter of 720 either side
    assert int(cut["sub-margin-x"]) == int(whole["sub-margin-x"]) + 180


def test_subtitle_options_go_on_only_when_they_change():
    player = _player()
    player.start((100, 100))
    told = len(_option_sets(player))

    assert told

    player.set_subtitle_view(SubtitleView())
    assert len(_option_sets(player)) == told

    player.set_subtitle_style({**SUBTITLE_STYLE_DEFAULTS, "subtitles/bold": True})
    assert _option_sets(player)[told:] == [("sub-bold", "yes")]


def test_render_size_keeps_a_small_picture_small_with_nothing_to_keep_sharp():
    placement = _placed((0, 0, 320, 180), (0, 0, 1280, 720))

    assert calc_render_size((320, 180), placement) == (320, 180)


def test_render_size_goes_up_to_the_cell_for_something_to_keep_sharp():
    placement = _placed((0, 0, 320, 180), (0, 0, 1280, 720))

    assert calc_render_size((320, 180), placement, sharp_in=(1280, 720)) == (1280, 720)


def test_render_size_for_something_to_keep_sharp_takes_no_more_for_a_zoom():
    # zoomed in four times, a picture the cell's size has all it needs
    placement = _placed((0, 0, 80, 45), (0, 0, 1280, 720))

    assert calc_render_size((320, 180), placement, sharp_in=(1280, 720)) == (1280, 720)


def test_render_size_of_a_big_picture_is_as_it_was_to_keep_sharp():
    placement = _placed((0, 0, 1920, 1080), (0, 0, 640, 360))

    assert calc_render_size((1920, 1080), placement, sharp_in=(640, 360)) == (640, 360)


def _filters_sent(player) -> list[str]:
    return [
        command[2] for command in player.mpv.commands if command[:2] == ("vf", "set")
    ]


def _software_player(file_turn=0, **video):
    player = _player(is_software=True, hwdec="no", **video)
    # as mpv lists it while it preloads: nothing selected yet
    player.mpv.track_list = [{"type": "video", "id": 1, "demux-rotation": file_turn}]

    return player


def test_software_leaves_turns_to_filters_and_scales_cheaply():
    options = _player(is_software=True, transform=VideoTransform.ROTATE_90).mpv.options

    assert options["video_rotate"] == "no"
    assert options["sws_allow_zimg"] is False
    assert options["sws_scaler"] == "fast-bilinear"


def test_opengl_has_no_software_scaler():
    assert "sws_scaler" not in _player().mpv.options


@pytest.mark.parametrize(
    ("file_turn", "transform", "sent"),
    [
        (0, VideoTransform.NONE, []),
        (90, VideoTransform.NONE, ["lavfi=[transpose=clock]"]),
        (0, VideoTransform.ROTATE_270, ["lavfi=[transpose=cclock]"]),
        (90, VideoTransform.ROTATE_90, ["lavfi=[hflip,vflip]"]),
        # all the way round
        (270, VideoTransform.ROTATE_90, []),
        # turned as ROTATE_90, the flip painted
        (180, VideoTransform.TRANSPOSE, ["lavfi=[transpose=cclock]"]),
    ],
)
def test_software_turns_the_picture_before_it_starts(file_turn, transform, sent):
    player = _software_player(file_turn, transform=transform)

    _preloaded(player)

    assert _filters_sent(player) == sent
    assert _hook_answered(player)


def test_software_turns_by_the_video_track_it_shows():
    player = _player(is_software=True, hwdec="no", video_track_id=2)
    player.mpv.track_list = [
        {"type": "video", "id": 1, "selected": True, "demux-rotation": 0},
        {"type": "video", "id": 2, "demux-rotation": 90},
    ]

    _preloaded(player)

    assert _filters_sent(player) == ["lavfi=[transpose=clock]"]


@pytest.mark.parametrize(
    ("listed", "taken"),
    [
        ([{"type": "video", "id": 1}, {"type": "video", "id": 2}], 1),
        ([{"type": "video", "id": 1}, {"type": "video", "id": 2, "default": True}], 2),
        ([{"type": "video", "id": 1, "albumart": True}, {"type": "video", "id": 2}], 2),
        ([{"type": "audio", "id": 1}], None),
    ],
)
def test_the_video_track_mpv_takes_when_left_alone(listed, taken):
    player = _player()
    player.mpv.track_list = listed

    assert player._file_video_track_id() == taken


def test_opengl_leaves_the_files_turn_to_mpv():
    player = _player()
    player.mpv.track_list = [
        {"type": "video", "id": 1, "selected": True, "demux-rotation": 90}
    ]

    _preloaded(player)

    assert _filters_sent(player) == []


def test_software_deinterlaces_before_it_turns():
    player = _software_player(90, **_BY_NAME)
    _preloaded(player)

    _file_loaded(player)

    assert _filters_sent(player)[-1] == (
        "lavfi=[yadif=mode=send_frame],lavfi=[transpose=clock]"
    )

    player.set_deinterlace(VideoDeinterlace.OFF, VideoDeinterlaceMode.YADIF)

    assert _filters_sent(player)[-1] == "lavfi=[transpose=clock]"
    # it's deinterlacing's that can be refused, and it's gone
    assert player.mpv.callbacks["vf", "set", "lavfi=[transpose=clock]"] is None


@pytest.mark.parametrize(("file_turn", "dims"), [(0, (640, 360)), (90, (360, 640))])
def test_software_picture_has_the_shape_the_filter_turns_it_to(file_turn, dims):
    # video-params is of the picture before the filters, and says no rotation
    player = _software_player(file_turn)
    _preloaded(player)

    player._on_video_params("video-params", {"dw": 640, "dh": 360, "rotate": 0})

    assert player._dims == dims


def test_software_turns_again_for_another_video_track():
    player = _player(is_software=True, hwdec="no")
    player.mpv.track_list = [
        {"type": "video", "id": 1, "selected": True, "demux-rotation": 0},
        {"type": "video", "id": 2, "demux-rotation": 90},
    ]
    _preloaded(player)
    _file_loaded(player)

    player.select_track("vid", 2)

    assert _filters_sent(player) == ["lavfi=[transpose=clock]"]


def test_software_plays_on_when_its_turn_is_refused(caplog):
    player = _software_player(90)

    def refuse(*args):
        if args[0] == "vf":
            # what python-mpv raises for a command mpv refuses
            raise SystemError("filter refused")
        player.mpv.commands.append(args)

    player.mpv.command = refuse

    with caplog.at_level(logging.ERROR):
        _preloaded(player)

    assert _hook_answered(player)
    # the next try goes, mpv having kept what it had
    assert player._filters_sent == ""
    assert "refused" in caplog.text


def test_a_refused_chain_is_sent_again_once_asked_for():
    player = _software_player(90, **_BY_NAME)
    _preloaded(player)
    _file_loaded(player)
    chain = _filters_sent(player)[-1]

    player._on_filter_told(VideoDeinterlaceMode.YADIF, "no such filter", None)

    # without the mode: the turn alone, though it was sent before the mode was
    assert _filters_sent(player)[-1] == "lavfi=[transpose=clock]"
    assert chain != "lavfi=[transpose=clock]"


def test_software_flips_by_a_filter_not_a_shader():
    player = _software_player(90)
    _preloaded(player)
    player.mpv.commands.clear()

    assert player.set_flip_in_mpv((True, False))

    assert _filters_sent(player) == ["lavfi=[transpose=clock],lavfi=[hflip]"]
    assert not any(command[0] == "change-list" for command in player.mpv.commands)

    assert not player.set_flip_in_mpv(None)

    assert _filters_sent(player)[-1] == "lavfi=[transpose=clock]"


def test_flip_in_mpv_is_a_shader_for_as_long_as_it_is_asked(tmp_path):
    player = _player()

    with patch.object(player_module, "get_app_cache_dir", return_value=tmp_path):
        assert player.set_flip_in_mpv((True, False))
        assert player.set_flip_in_mpv((True, False))

    shader = tmp_path / "mpv_flip_across.hook"

    assert player.mpv.commands == [
        ("change-list", "glsl-shaders", "clr", ""),
        ("change-list", "glsl-shaders", "append", str(shader)),
    ]
    assert "1.0 - HOOKED_pos.x" in shader.read_text()

    player.mpv.commands.clear()
    assert not player.set_flip_in_mpv(None)
    assert not player.set_flip_in_mpv(None)

    assert player.mpv.commands == [("change-list", "glsl-shaders", "clr", "")]


def test_flip_in_mpv_that_cant_be_written_stays_painted(tmp_path):
    player = _player()
    # a file where the folder would have to be
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("")

    with patch.object(player_module, "get_app_cache_dir", return_value=not_a_folder):
        assert not player.set_flip_in_mpv((True, False))

    assert not player.mpv.commands


def test_flip_in_mpv_gets_its_shader_back_after_the_cache_is_cleared(tmp_path):
    player = _player()
    shader = tmp_path / "mpv_flip_across.hook"

    with patch.object(player_module, "get_app_cache_dir", return_value=tmp_path):
        assert player.set_flip_in_mpv((True, False))
        shader.unlink()
        assert not player.set_flip_in_mpv(None)
        assert player.set_flip_in_mpv((True, False))

    assert shader.is_file()


def test_surface_leaves_the_flip_to_mpv_while_it_does_it():
    surface = _surface_showing(VideoTransform.HFLIP, (RED, BLUE))
    surface.set_flip_in_mpv(True)
    image = surface.frame_image()

    assert (image.pixel(0, 0), image.pixel(1, 0)) == (RED, BLUE)
    assert surface.flip() == (True, False)

    surface.set_flip_in_mpv(False)
    image = surface.frame_image()

    assert (image.pixel(0, 0), image.pixel(1, 0)) == (BLUE, RED)


# Streams ---------------------------------------------------------------------


def _stream_player(stream_audio=None, http_headers=None, is_live=False, **media):
    return _player(
        is_live=is_live,
        uri="http://proxy/video",
        media={
            "stream_audio": stream_audio,
            "http_headers": http_headers or {},
            "is_proxied": True,
            **media,
        },
    )


_STREAM_AUDIO = StreamAudio(uri="http://proxy/audio", title="Audio 128k", language="de")


def _audio_file_track(track_id, file, **fields):
    return {
        "id": track_id,
        "type": "audio",
        "external": True,
        "external-filename": file,
        "title": "?stream_id=1&session_id=2",
        **fields,
    }


def test_a_streams_own_sound_opens_as_a_file_before_the_video():
    player = _stream_player(_STREAM_AUDIO)

    player.start((100, 100))

    commands = player.mpv.commands

    assert commands.index(
        ("change-list", "audio-files", "append", "http://proxy/audio")
    ) < commands.index(("loadfile", "http://proxy/video"))


def test_a_streams_own_sound_is_no_file_to_the_menus():
    player = _stream_player(_STREAM_AUDIO)
    player.mpv.track_list = [_audio_file_track(1, "http://proxy/audio")]

    tracks = player._read_tracks()

    assert tracks.external_audio_ids == ()
    assert tracks.default_audio_track_id == 1
    assert tracks.audio_tracks[1].description == "Audio 128k"
    assert tracks.audio_tracks[1].language == "de"


def test_a_file_put_beside_a_streams_sound_is_still_a_file():
    player = _stream_player(_STREAM_AUDIO)
    player.mpv.track_list = [
        _audio_file_track(1, "http://proxy/audio"),
        _audio_file_track(2, "file:///commentary.m4a"),
    ]

    assert player._read_tracks().external_audio_ids == (2,)


def test_a_links_headers_go_where_mpv_takes_them():
    player = _stream_player(
        http_headers={
            "User-Agent": "Box/1.0",
            "Referer": "http://ref.example/",
            "X-Token": "a, b",
        }
    )

    player.start((100, 100))

    commands = player.mpv.commands

    assert ("set", "user-agent", "Box/1.0") in commands
    assert ("set", "referrer", "http://ref.example/") in commands
    # a value that has a comma in it stays the one value
    assert ("change-list", "http-header-fields", "append", "X-Token: a, b") in commands


def test_pausing_a_live_stream_lets_it_go():
    player = _stream_player(is_live=True)
    player._dims = (640, 360)
    said = []
    player.paused_changed.connect(said.append)

    player.set_pause(True)

    assert ("stop",) in player.mpv.commands
    assert ("set", "pause", "yes") not in player.mpv.commands
    assert said == [True]
    assert player.is_paused


def test_a_stopped_live_stream_has_only_black_to_draw_so_draws_nothing():
    player = _stream_player(is_live=True)
    player._dims = (640, 360)

    player.set_pause(True)

    assert player.render_size() is None


def test_playing_a_live_stream_again_opens_it_again():
    player = _stream_player(is_live=True)
    player._dims = (640, 360)
    player.set_pause(True)
    player.mpv.commands.clear()
    said = []
    player.paused_changed.connect(said.append)

    player.set_pause(False)

    assert ("loadfile", "http://proxy/video") in player.mpv.commands
    assert said == [False]
    assert not player.is_paused
    # the picture stays until there's another
    assert player.render_size() is None

    _restart(player)

    assert player.render_size() is not None


def test_a_live_stream_opened_again_is_loaded_once_with_its_tracks_read_again():
    player = _stream_player(is_live=True)
    loaded, changed = [], []
    player.media_loaded.connect(loaded.append)
    player.tracks_changed.connect(changed.append)
    _file_loaded(player)

    player.mpv.track_list = [{"type": "audio", "id": 1, "selected": True}]
    _file_loaded(player)

    assert len(loaded) == 1
    assert list(changed[-1].audio_tracks) == [1]
    assert player._media is changed[-1]


def test_files_added_to_a_live_stream_are_opened_again_with_it():
    player = _stream_player(is_live=True)

    player.add_audio_file("C:/dub.mka")
    subtitles = Path("C:/subs.srt")
    player.add_subtitle_file(subtitles.as_uri())

    commands = player.mpv.commands

    assert ("change-list", "audio-files", "append", "C:/dub.mka") in commands
    assert ("change-list", "sub-files", "append", str(subtitles)) in commands


def test_files_added_to_a_video_are_not_kept_for_opening_again():
    player = _stream_player()

    player.add_audio_file("C:/dub.mka")

    assert not [c for c in player.mpv.commands if c[0] == "change-list"]


def test_pausing_a_video_stays_a_pause():
    player = _stream_player()

    player.set_pause(True)

    assert ("set", "pause", "yes") in player.mpv.commands
    assert ("stop",) not in player.mpv.commands


def test_no_length_means_no_going_round():
    player = _stream_player()
    player.mpv.duration = None

    _file_loaded(player)

    assert player.media_input.is_live
    assert ("set", "loop-file", "no") in player.mpv.commands


def test_staying_open_at_the_end_is_no_pause_of_the_viewers():
    assert _stream_player().mpv.options["keep_open_pause"] is False


def _live_driver():
    driver = _driver_playing()
    driver._player = _stream_player(is_live=True)
    driver._is_load_reported = True

    return driver


def test_a_live_stream_is_not_seeked_or_sped_up():
    driver = _live_driver()

    driver.set_time(5000)
    driver.set_playback_rate(2.0)

    assert not [
        command
        for command in driver._player.mpv.commands
        if command[0] == "seek" or command[:2] == ("set", "speed")
    ]


def test_a_live_stream_that_wont_play_again_times_out(monkeypatch):
    monkeypatch.setattr(
        "gridplayer.widgets.video_frame_mpv.Settings",
        lambda: SimpleNamespace(get=lambda _key: 7),
    )
    driver = _live_driver()
    driver.set_pause(True)
    said = []
    driver.error.connect(lambda message, _lines: said.append(message))

    driver.set_pause(False)

    assert driver._rejoin_timeout.interval() == 7000
    assert driver._rejoin_timeout.isActive()

    driver._rejoin_timeout.timeout.emit()

    assert said == ["Buffering timeout"]


def test_a_live_stream_playing_again_is_in_time():
    driver = _live_driver()
    driver.set_pause(True)
    driver.set_pause(False)

    driver._on_playback_restarted()

    assert not driver._rejoin_timeout.isActive()


def test_a_live_stream_paused_again_is_not_waited_on():
    driver = _live_driver()
    driver.set_pause(True)
    driver.set_pause(False)

    driver.set_pause(True)

    assert not driver._rejoin_timeout.isActive()


def test_a_screenshot_of_a_stopped_live_stream_is_of_what_is_up():
    driver = _driver_for_screenshots()
    driver._player = _stream_player(is_live=True)
    driver._player._dims = (640, 360)
    driver._player.set_pause(True)

    driver.screenshot()

    assert driver.taken == [""]


@pytest.fixture
def _failures_at_once(mocker):
    """No wait for the reason, with these having theirs from the start."""

    timer = mocker.patch("gridplayer.mpv_player.player.threading.Timer")
    timer.side_effect = lambda _wait, report, args: SimpleNamespace(
        start=lambda: report(*args), daemon=False
    )


def _failures_of(driver):
    said = []
    driver._player.failed.connect(lambda message, lines: said.append((message, lines)))

    return said


@pytest.mark.usefixtures("_failures_at_once")
def test_a_live_stream_running_out_says_so():
    driver = _live_driver()
    said = _failures_of(driver)

    driver._on_end_reached()

    assert [message for message, _ in said] == ["Live stream ended"]


@pytest.mark.usefixtures("_failures_at_once")
def test_the_end_of_something_that_never_played_says_so():
    driver = _driver_playing()
    driver._is_load_reported = False
    said = _failures_of(driver)

    driver._on_end_reached()

    assert [message for message, _ in said] == ["Video stopped before initialization"]


@pytest.mark.usefixtures("_failures_at_once")
def test_the_end_of_a_video_that_plays_is_nothing_wrong():
    driver = _driver_playing()
    driver._is_load_reported = True
    said = _failures_of(driver)

    driver._on_end_reached()

    assert not said


@pytest.mark.usefixtures("_failures_at_once")
def test_a_video_fails_once():
    player = _stream_player()
    said = []
    player.failed.connect(lambda message, _lines: said.append(message))

    player.fail("One")
    player.fail("Two")

    assert said == ["One"]


def _report_failure(timer):
    """What the failure's timer runs once it's up."""

    timer.call_args.args[1](*timer.call_args.kwargs["args"])


def test_a_failure_waits_for_its_reason(mocker):
    # mpv's events come before its log
    timer = mocker.patch("gridplayer.mpv_player.player.threading.Timer")
    player = _stream_player()
    said = []
    player.failed.connect(lambda _message, lines: said.append(lines))

    player.fail("Player error")
    player._on_log("error", "cplayer", "Failed to recognize file format.\n")

    _report_failure(timer)

    assert said == [("cplayer: Failed to recognize file format.",)]


def test_a_failure_as_the_video_closes_says_nothing(mocker):
    timer = mocker.patch("gridplayer.mpv_player.player.threading.Timer")
    player = _stream_player()
    said = []
    player.failed.connect(lambda message, _lines: said.append(message))

    player.fail("Player error")
    player.close()
    _report_failure(timer)

    assert not said


# The log ---------------------------------------------------------------------


def test_errors_are_kept_for_a_failure_whatever_is_logged(caplog):
    player = _stream_player()

    with caplog.at_level(logging.DEBUG):
        player._on_log("error", "lavf", "no good\n")

    assert list(player._log_lines) == ["lavf: no good"]
    assert "no good" not in caplog.text


def test_what_mpv_says_is_logged_at_its_level_once_asked_for(caplog):
    player = _stream_player()
    player.mpv.set_loglevel = MagicMock()

    player.set_log_level(logging.WARNING)

    assert player.mpv.set_loglevel.call_args.args == ("warn",)

    with caplog.at_level(logging.DEBUG):
        player._on_log("warn", "lavf", "careful\n")
        player._on_log("v", "lavf", "chatter\n")

    assert "careful" in caplog.text
    assert "chatter" not in caplog.text


def test_turned_off_mpv_is_only_asked_for_errors():
    player = _stream_player()
    player.mpv.set_loglevel = MagicMock()

    player.set_log_level(DISABLED)

    assert player.mpv.set_loglevel.call_args.args == ("error",)


def test_the_log_level_is_not_sent_once_closing():
    player = _stream_player()
    player.mpv.set_loglevel = MagicMock()
    player.close()

    player.set_log_level(logging.DEBUG)

    player.mpv.set_loglevel.assert_not_called()


def test_taking_too_long_to_load_says_so():
    driver = _driver_playing()
    said = []
    driver.error.connect(lambda message, lines: said.append(message))

    driver._on_load_timeout()

    assert said == ["Timed out loading video"]


def test_no_way_to_draw_is_said_with_why():
    driver = _driver_playing()
    said = []
    driver.error.connect(lambda message, lines: said.append((message, lines)))

    driver.render_failed("no GL context")

    assert said == [("Player error", ("no GL context",))]


def test_a_proxy_link_goes_in_with_any_segment_allowed():
    # the proxy's look like no file: see player._ANY_SEGMENT_LINK
    player = _stream_player()

    assert "extension_picky=0" in player.mpv.options["demuxer_lavf_o"]


def test_a_playlist_on_disk_keeps_ffmpeg_picky():
    assert "demuxer_lavf_o" not in _player().mpv.options


def test_a_link_mpv_opens_itself_keeps_ffmpeg_picky():
    player = _stream_player(is_proxied=False)

    assert "demuxer_lavf_o" not in player.mpv.options


def test_a_stream_with_a_file_in_fragments_is_not_sought_in_through_its_cache():
    player = _stream_player(has_fragmented_file=True)

    assert player.mpv.options["demuxer_seekable_cache"] == "no"


def test_any_other_stream_keeps_its_cache_for_seeks():
    # the sound comes out behind after a seek on HLS of TS segments without it
    assert "demuxer_seekable_cache" not in _stream_player().mpv.options


# -- Decode on the CPU set to Auto


def _auto_player(is_room, hwdec="auto", size=(1920, 1080), **player):
    room = MagicMock()
    room.take.return_value = "claim" if is_room else None

    player = _player(hwdec=hwdec, cpu_when_low=True, **player)
    player.mpv.track_list = [
        {"type": "video", "id": 1, "demux-w": size[0], "demux-h": size[1]}
    ]
    player.room = room

    return player


def _preloaded_with(player):
    with patch.object(player_module, "video_memory_room", return_value=player.room):
        _preloaded(player)


def _decoder_set(player):
    return [
        command[2] for command in player.mpv.commands if command[:2] == ("set", "hwdec")
    ]


def test_auto_with_room_left_decodes_on_the_gpu():
    player = _auto_player(is_room=True)

    _preloaded_with(player)

    player.room.take.assert_called_once_with((1920, 1080))
    assert _decoder_set(player) == []
    assert _hook_answered(player)


def test_auto_with_no_room_left_decodes_on_the_cpu():
    player = _auto_player(is_room=False, size=(3840, 2160))

    _preloaded_with(player)

    player.room.take.assert_called_once_with((3840, 2160))
    assert _decoder_set(player) == ["no"]
    assert _hook_answered(player)


def test_auto_on_the_cpu_stays_there_with_deinterlacing():
    player = _auto_player(is_room=False, **_BY_NAME)
    _preloaded_with(player)

    player._on_hwdec("hwdec-current", "no")
    _file_loaded(player)

    # not to auto-copy, as a deinterlacer on the GPU's frames would have it
    assert ("hwdec", "auto-copy") not in _deinterlace_told(player)
    assert player._deinterlace_options["hwdec"] == "no"


def test_auto_picks_once_as_the_video_first_starts():
    player = _auto_player(is_room=True)
    _preloaded_with(player)

    player.mpv.commands.clear()
    player.room.take.return_value = None
    _preloaded_with(player)

    player.room.take.assert_called_once()
    assert _decoder_set(player) == []


def _restarted(player):
    player._on_event(SimpleNamespace(event_id=SimpleNamespace(value=21), data=None))


def test_auto_s_claim_on_the_gpu_ends_with_the_first_frame():
    player = _auto_player(is_room=True)
    _preloaded_with(player)

    with patch.object(player_module, "video_memory_room", return_value=player.room):
        _restarted(player)
        _restarted(player)

    player.room.started.assert_called_once_with("claim")


def test_auto_s_claim_on_the_gpu_ends_once_mpv_says_what_it_decodes_with():
    player = _auto_player(is_room=True)
    _preloaded_with(player)

    with patch.object(player_module, "video_memory_room", return_value=player.room):
        player._on_hwdec("hwdec-current", "nvdec")

    player.room.started.assert_called_once_with("claim")


def test_auto_s_claim_on_the_gpu_ends_closing_before_it_starts():
    player = _auto_player(is_room=True)
    _preloaded_with(player)

    with patch.object(player_module, "video_memory_room", return_value=player.room):
        player.close()

    player.room.started.assert_called_once_with("claim")


def test_auto_leaves_cpu_decoding_alone():
    player = _auto_player(is_room=False, hwdec="no")

    _preloaded_with(player)

    player.room.take.assert_not_called()


def test_auto_takes_no_room_for_sound_alone():
    player = _auto_player(is_room=False, is_audio_only=True)

    _preloaded_with(player)

    player.room.take.assert_not_called()


def test_not_on_auto_no_room_is_asked_for():
    player = _player()
    player.mpv.track_list = [{"type": "video", "id": 1, "demux-w": 1920}]

    with patch.object(player_module, "video_memory_room") as room:
        _preloaded(player)

    room.assert_not_called()
