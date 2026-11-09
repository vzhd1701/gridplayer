"""What subtitles look like, as options for mpv.

Text subtitles only. ASS and SSA carry their own styling.
"""

import string

from gridplayer.params.static import SubtitleOutline

SUBTITLE_STYLE_DEFAULTS = {
    "subtitles/font": "",
    "subtitles/size_scale": 100,
    "subtitles/color": "#ffffff",
    "subtitles/bold": False,
    "subtitles/outline": SubtitleOutline.NORMAL,
    "subtitles/outline_color": "#000000",
    "subtitles/shadow": True,
    "subtitles/shadow_color": "#000000",
    "subtitles/background": False,
    "subtitles/background_color": "#000000",
    "subtitles/margin": 0,
}

SUBTITLE_STYLE_SETTINGS = tuple(SUBTITLE_STYLE_DEFAULTS)

# mpv's own defaults, which the same knobs are worked out from
MPV_SUB_MARGIN_Y = 34
MPV_SHADOW_OFFSET = 1.5
MPV_OUTLINE_SIZE = {
    SubtitleOutline.NONE: 0,
    SubtitleOutline.THIN: 1,
    SubtitleOutline.NORMAL: 1.65,
    SubtitleOutline.THICK: 3,
}


def mpv_subtitle_style_options(style: dict) -> dict:
    """The same style as mpv options. Text subtitles only, as for VLC."""

    style = {**SUBTITLE_STYLE_DEFAULTS, **style}

    options = {
        "sub_scale": style["subtitles/size_scale"] / 100,
        "sub_bold": style["subtitles/bold"],
        "sub_outline_size": MPV_OUTLINE_SIZE[style["subtitles/outline"]],
        "sub_shadow_offset": MPV_SHADOW_OFFSET if style["subtitles/shadow"] else 0,
        "sub_margin_y": max(MPV_SUB_MARGIN_Y + style["subtitles/margin"], 0),
    }

    if style["subtitles/font"]:
        options["sub_font"] = style["subtitles/font"]

    colors = {
        "sub_color": "subtitles/color",
        "sub_outline_color": "subtitles/outline_color",
        "sub_shadow_color": "subtitles/shadow_color",
    }

    if style["subtitles/background"]:
        options["sub_border_style"] = "background-box"
        colors["sub_back_color"] = "subtitles/background_color"

    for option, key in colors.items():
        if _is_color(style[key]):
            options[option] = f"#{style[key].lstrip('#')}"

    return options


def _is_color(color: str) -> bool:
    """Whether this is a colour at all: six hex digits, a leading # or not.

    Anything else is somebody's hand-edited settings file.
    """

    digits = color.lstrip("#")

    return len(digits) == 6 and all(digit in string.hexdigits for digit in digits)
