"""What subtitles look like, and what VLC draws unless it is told otherwise.

Every knob here is an instance option. The text renderer hangs off the
media player rather than the input, so the same option offered per media
is read by nobody -- a style is settled once, for every video a VLC
process plays, when that process starts.

The defaults are VLC's own, taken by rendering a subtitled frame and
comparing it against one rendered with the option passed by hand: an
outline of 4 and a shadow opacity of 128 reproduce an untouched VLC
exactly, and a background opacity of 0 leaves it alone. A setting still
at its default is left out, so an install nobody has touched asks for
nothing and plays in the same process it always did.

Text subtitles only. ASS and SSA carry their own styling and are drawn
by libass, which reads none of this; only the margin reaches them.
"""

import string
from collections.abc import Iterator

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

# what VLC takes for the rim around a glyph, none of it a pixel count
OUTLINE_THICKNESS = {
    SubtitleOutline.NONE: 0,
    SubtitleOutline.THIN: 2,
    SubtitleOutline.NORMAL: 4,
    SubtitleOutline.THICK: 6,
}

# VLC's own, so that turning a thing back on restores what it looked like
SHADOW_OPACITY = 128
BACKGROUND_OPACITY = 255

OPAQUE = 255
TRANSPARENT = 0


def subtitle_style_options(style: dict) -> list[str]:
    """The options a style asks for, leaving out whatever VLC does anyway."""

    return list(_iter_options({**SUBTITLE_STYLE_DEFAULTS, **style}))


def _iter_options(style: dict) -> Iterator[str]:
    if _is_set(style, "subtitles/font"):
        font = style["subtitles/font"]
        yield f"--freetype-font={font}"

    if _is_set(style, "subtitles/size_scale"):
        scale = style["subtitles/size_scale"]
        yield f"--sub-text-scale={scale}"

    yield from _color(style, "subtitles/color", "--freetype-color")

    if style["subtitles/bold"]:
        yield "--freetype-bold"

    if _is_set(style, "subtitles/outline"):
        thickness = OUTLINE_THICKNESS[style["subtitles/outline"]]
        yield f"--freetype-outline-thickness={thickness}"

    if style["subtitles/outline"] is not SubtitleOutline.NONE:
        yield from _color(style, "subtitles/outline_color", "--freetype-outline-color")

    if style["subtitles/shadow"]:
        yield from _color(style, "subtitles/shadow_color", "--freetype-shadow-color")
    else:
        yield f"--freetype-shadow-opacity={TRANSPARENT}"

    if style["subtitles/background"]:
        yield f"--freetype-background-opacity={BACKGROUND_OPACITY}"
        yield from _color(
            style, "subtitles/background_color", "--freetype-background-color"
        )

    if _is_set(style, "subtitles/margin"):
        margin = style["subtitles/margin"]
        yield f"--sub-margin={margin}"


def _is_set(style: dict, key: str) -> bool:
    """Whether this is something other than what VLC would do by itself."""

    return style[key] != SUBTITLE_STYLE_DEFAULTS[key]


def _color(style: dict, key: str, option: str) -> Iterator[str]:
    if not _is_set(style, key):
        return

    color = _as_vlc_color(style[key])

    if color is not None:
        yield f"{option}={color}"


def _as_vlc_color(color: str) -> str | None:
    """A colour as VLC takes it, or nothing at all where it is not one.

    Anything but six hex digits is somebody's hand-edited settings file,
    and passing it on would have VLC read it as black -- which looks
    like a colour that was asked for rather than one that was dropped.
    """

    digits = color.lstrip("#")

    is_hex = len(digits) == 6 and all(digit in string.hexdigits for digit in digits)

    return f"0x{digits}" if is_hex else None
