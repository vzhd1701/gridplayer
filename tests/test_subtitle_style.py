"""What the subtitle style settings come to as options for mpv."""

import pytest

from gridplayer.params.static import SubtitleOutline
from gridplayer.params.subtitle_style import (
    MPV_OUTLINE_SIZE,
    MPV_SHADOW_OFFSET,
    MPV_SUB_MARGIN_Y,
    SUBTITLE_STYLE_DEFAULTS,
    mpv_subtitle_style_options,
)


def test_the_defaults_leave_font_and_box_alone():
    options = mpv_subtitle_style_options({})

    assert options["sub_scale"] == 1
    assert options["sub_bold"] is False
    assert options["sub_margin_y"] == MPV_SUB_MARGIN_Y
    assert "sub_font" not in options
    assert "sub_border_style" not in options
    assert "sub_back_color" not in options


def test_every_setting_has_a_default_to_fall_back_on():
    assert set(SUBTITLE_STYLE_DEFAULTS) >= {"subtitles/font", "subtitles/size_scale"}


def test_the_size_is_a_scale():
    assert mpv_subtitle_style_options({"subtitles/size_scale": 180})["sub_scale"] == 1.8


def test_a_font_is_passed_on():
    options = mpv_subtitle_style_options({"subtitles/font": "Arial"})

    assert options["sub_font"] == "Arial"


@pytest.mark.parametrize("outline", list(SubtitleOutline))
def test_every_outline_has_a_size(outline):
    options = mpv_subtitle_style_options({"subtitles/outline": outline})

    assert options["sub_outline_size"] == MPV_OUTLINE_SIZE[outline]


@pytest.mark.parametrize(("shadow", "offset"), [(True, MPV_SHADOW_OFFSET), (False, 0)])
def test_the_shadow(shadow, offset):
    options = mpv_subtitle_style_options({"subtitles/shadow": shadow})

    assert options["sub_shadow_offset"] == offset


def test_a_background_turns_the_box_on():
    options = mpv_subtitle_style_options(
        {"subtitles/background": True, "subtitles/background_color": "#0000ff"}
    )

    assert options["sub_border_style"] == "background-box"
    assert options["sub_back_color"] == "#0000ff"


def test_the_margin_adds_to_mpvs_own():
    options = mpv_subtitle_style_options({"subtitles/margin": 60})

    assert options["sub_margin_y"] == MPV_SUB_MARGIN_Y + 60


def test_the_margin_stops_at_the_edge():
    options = mpv_subtitle_style_options({"subtitles/margin": -1000})

    assert options["sub_margin_y"] == 0


@pytest.mark.parametrize("color", ["red", "#12345", "#gggggg", ""])
def test_a_colour_that_is_not_one_is_left_out(color):
    options = mpv_subtitle_style_options({"subtitles/color": color})

    assert "sub_color" not in options


def test_a_colour_without_its_hash_gets_one():
    options = mpv_subtitle_style_options({"subtitles/color": "ffff00"})

    assert options["sub_color"] == "#ffff00"
