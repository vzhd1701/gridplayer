from pathlib import Path

import pytest

from gridplayer.mpv_player import abilities
from gridplayer.mpv_player.abilities import Abilities, _filters_in
from gridplayer.mpv_player.deinterlace import unavailable_modes
from gridplayer.params.settings_fields.choices import unavailable_deinterlace_modes
from gridplayer.params.static import VideoDeinterlaceMode, VideoDriver
from gridplayer.utils import media_libs, video_driver

# as mpv logs it for `vf set lavfi=[help]`, then its own lavfi options
_LISTED = [
    "Available libavfilter filters:\n",
    "  bwdif            Deinterlace the input image.\n",
    "  scale            Scale the input video size and/or convert the image format.\n",
    "  yadif            Deinterlace the input image.\n",
    "\n",
    "This lists video->video filters only. Refer to\n",
    " graph                          String (default: )\n",
    "    o-remove\n",
]

# MPVKit's, the macOS package's: few filters, few demuxers
_SMALL = Abilities(
    frozenset({"bwdif", "scale", "yadif"}),
    frozenset({"ass", "srt", "webvtt", "matroska,webm", "mov,mp4,m4a,3gp,3g2,mj2"}),
)

_NOT_ASKED = Abilities(frozenset(), frozenset())


def test_the_filters_are_read_from_the_list_up_to_its_end():
    assert list(_filters_in(_LISTED)) == ["bwdif", "scale", "yadif"]


def test_nothing_listed_is_no_filter_at_all():
    assert list(_filters_in(["Total: 9 options\n"])) == []


def test_the_modes_a_small_ffmpeg_has_not_the_filters_for():
    assert unavailable_modes(_SMALL) == {
        VideoDeinterlaceMode.DISCARD,
        VideoDeinterlaceMode.BLEND,
        VideoDeinterlaceMode.BOB,
        VideoDeinterlaceMode.LINEAR,
        VideoDeinterlaceMode.IVTC,
    }


@pytest.mark.parametrize("known", [None, _NOT_ASKED])
def test_every_mode_is_there_while_it_isnt_known(known):
    assert unavailable_modes(known) == set()


@pytest.mark.parametrize(
    ("name", "is_read"),
    [
        ("film.srt", True),
        ("film.ASS", True),
        ("film.vtt", True),
        ("film.mks", True),
        ("film.idx", False),
        ("film.sub", False),
        ("film.smi", False),
        # no one demuxer to go by
        ("film.txt", True),
    ],
)
def test_the_subtitle_files_a_small_ffmpeg_reads(name, is_read):
    assert _SMALL.reads_subtitle_file(Path(name)) is is_read


def test_every_subtitle_file_is_read_while_it_isnt_known():
    assert _NOT_ASKED.reads_subtitle_file(Path("film.idx"))


def test_an_mpv_that_cant_be_asked_is_taken_to_have_everything(monkeypatch):
    class _Broken:
        def MPV(self, **_options):
            raise OSError("no")

    monkeypatch.setattr(abilities, "_known", None)

    assert abilities.ask(_Broken()) == _NOT_ASKED


@pytest.mark.parametrize(
    ("driver", "greyed"),
    [
        (
            VideoDriver.MPV_HW,
            {
                VideoDeinterlaceMode.DISCARD,
                VideoDeinterlaceMode.BLEND,
                VideoDeinterlaceMode.BOB,
                VideoDeinterlaceMode.LINEAR,
                VideoDeinterlaceMode.IVTC,
            },
        ),
        # VLC has every mode
        (VideoDriver.VLC_HW, set()),
    ],
)
def test_settings_grey_out_the_modes_this_mpv_has_not_got(monkeypatch, driver, greyed):
    monkeypatch.setattr(abilities, "_known", _SMALL)
    monkeypatch.setattr(video_driver, "session_video_driver", lambda _picked: driver)
    monkeypatch.setattr(media_libs, "lib_problem", lambda _lib: None)

    assert set(unavailable_deinterlace_modes()) == greyed
