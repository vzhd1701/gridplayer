"""What subtitles look like on mpv, and keeping them on show.

mpv draws them into the frame, so what the view cuts off the picture would take them
with it. As VLC Hardware does, they stay in the part on show, the same size on screen.
"""

from dataclasses import dataclass
from math import inf

from gridplayer.params.static import SubtitleOutline
from gridplayer.params.subtitle_style import (
    BACKGROUND_OPACITY,
    SHADOW_OPACITY,
    SUBTITLE_STYLE_DEFAULTS,
    SUBTITLE_STYLE_SETTINGS,
    hex_digits,
)
from gridplayer.settings import Settings

# Files in these have no byte that isn't also ASCII, so they'd pass for UTF-8, which
# mpv tries first unless told not to
_SEVEN_BIT_ENCODINGS = {"ISO-2022-CN-EXT", "ISO-2022-JP-2", "ISO-2022-KR"}

# mpv's sizes are for a picture 720 high, whatever size it's drawn at
_VIRTUAL_HEIGHT = 720

# What makes an untouched mpv look like an untouched VLC Hardware, compared side by side
_FONT_SIZE = 50
# As little as the setting goes down to: a hand-edited file can say anything
_LEAST_SIZE = 0.1
_MARGIN_BOTTOM = 34
_MARGIN_SIDES = 25
_OUTLINE_SIZES = {
    SubtitleOutline.NONE: 0,
    SubtitleOutline.THIN: 1,
    SubtitleOutline.NORMAL: 2,
    SubtitleOutline.THICK: 3,
}
_SHADOW_OFFSET = 2.5

_FONT_DEFAULT = "sans-serif"
_NO_COLOR = "#00000000"


@dataclass(frozen=True)
class SubtitleView:
    """What of the picture is on show, in shares of it."""

    bottom: float = 1.0
    height: float = 1.0
    # in mpv's sizes
    cut_off_each_side: float = 0.0
    # how many pixels high the setting for raising them goes by
    pixels_high: int = _VIRTUAL_HEIGHT


@dataclass(frozen=True)
class SubtitleLimits:
    """What's different on an older libmpv, which refuses what it doesn't have. Seen
    on 0.37, and the side margin on 0.40 too, each refused with no error to
    show for it: a line then stays as it was.
    """

    has_outline_options: bool = True
    has_border_style: bool = True
    largest_side_margin: float = inf


_NO_LIMITS = SubtitleLimits()


def subtitle_limits(option_info) -> SubtitleLimits:
    """Going by python-mpv's MPV.option_info, which says None for no such option."""

    side_margin = option_info("sub-margin-x") or {}

    return SubtitleLimits(
        has_outline_options=option_info("sub-outline-size") is not None,
        has_border_style=option_info("sub-border-style") is not None,
        largest_side_margin=side_margin.get("max", inf),
    )


def current_subtitle_style() -> dict:
    return {key: Settings().get(key) for key in SUBTITLE_STYLE_SETTINGS}


def subtitle_codepage(encoding: str) -> str:
    return f"+{encoding}" if encoding in _SEVEN_BIT_ENCODINGS else encoding


def subtitle_view(
    source,
    source_size: tuple[int, int],
    frame_size: tuple[int, int],
    full_height: int,
) -> SubtitleView:
    """For a placement's source, of a picture this size in those pixels, drawn in a
    frame this size.

    Raising them goes by the picture's pixels, or the screen's for a picture smaller
    than its cell, as VLC Hardware has it.
    """

    source_w, source_h = source_size
    frame_w, frame_h = frame_size
    _, y, width, height = source

    width_on_show = min(width / source_w, 1.0)

    return SubtitleView(
        bottom=min((y + height) / source_h, 1.0),
        height=min(height / source_h, 1.0),
        cut_off_each_side=(
            (1 - width_on_show) / 2 * _VIRTUAL_HEIGHT * frame_w / frame_h
        ),
        pixels_high=max(full_height, frame_h),
    )


def subtitle_options(
    style: dict, view: SubtitleView, limits: SubtitleLimits = _NO_LIMITS
) -> dict[str, str]:
    """Everything mpv is to be told, so that going back to a default gets there too."""

    background = style["subtitles/background"]
    outline = style["subtitles/outline"]
    margin = style["subtitles/margin"]

    size = max(style["subtitles/size_scale"] / 100, _LEAST_SIZE)
    # as much as the picture is bigger than what's on show
    scale = size * view.height
    raised = margin / view.pixels_high * view.height
    # past the top mpv would refuse it, and stay where it was
    position = max(view.bottom - raised, 0) * 100
    side_margin = (_MARGIN_SIDES * view.height + view.cut_off_each_side) / scale

    options = {
        "sub-font": style["subtitles/font"] or _FONT_DEFAULT,
        "sub-font-size": str(_FONT_SIZE),
        "sub-scale": f"{scale:.4f}",
        "sub-color": _color(style, "subtitles/color"),
        "sub-bold": "yes" if style["subtitles/bold"] else "no",
        "sub-outline-size": str(_OUTLINE_SIZES[outline]),
        "sub-outline-color": _color(style, "subtitles/outline_color"),
        "sub-shadow-offset": str(_SHADOW_OFFSET if style["subtitles/shadow"] else 0),
        "sub-shadow-color": _color(style, "subtitles/shadow_color", SHADOW_OPACITY),
        "sub-border-style": "background-box" if background else "outline-and-shadow",
        # any colour there shows with no box too, in place of the shadow's. And it's
        # all an older libmpv has to go by for whether to draw a box
        "sub-back-color": _color(
            style, "subtitles/background_color", BACKGROUND_OPACITY
        )
        if background
        else _NO_COLOR,
        # both grow with sub-scale, and only the size is to
        "sub-margin-x": str(round(min(side_margin, limits.largest_side_margin))),
        "sub-margin-y": str(round(_MARGIN_BOTTOM / size)),
        "sub-pos": f"{position:.2f}",
    }

    if not limits.has_outline_options:
        options["sub-border-size"] = options.pop("sub-outline-size")
        options["sub-border-color"] = options.pop("sub-outline-color")

    if not limits.has_border_style:
        del options["sub-border-style"]

    return options


def _color(style: dict, key: str, opacity: int | None = None) -> str:
    """As mpv spells it, or what's usual for something in a hand-edited file that
    isn't one: left to itself mpv would refuse it and keep the last."""

    digits = hex_digits(style[key]) or hex_digits(SUBTITLE_STYLE_DEFAULTS[key])

    return f"#{digits}" if opacity is None else f"#{opacity:02X}{digits}"
