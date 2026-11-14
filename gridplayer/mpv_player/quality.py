"""Picture quality: how Hardware MPV scales the picture to the size it's drawn at.

Each level names every option either of them sets, so going from one to the other
leaves nothing of the last behind. They can change while a video plays.

Measured in docs/MPV_PERFORMANCE.md, "Picture quality": High costs nothing in
frames for one big video, on NVIDIA or an AMD iGPU, but on the iGPU it cost 4
cells of 1080p a sixth of their frames and 4 of 4K three quarters, and one 4K
video shrunk into the whole window a tenth. Hence Auto.
"""

from gridplayer.params.static import MpvPictureQuality

# mpv's `fast` profile: bilinear both ways, nothing done in linear light, no dither
FAST = {
    "scale": "bilinear",
    "dscale": "bilinear",
    "dither": "no",
    "correct-downscaling": "no",
    "linear-downscaling": "no",
    "sigmoid-upscaling": "no",
    "hdr-compute-peak": "no",
    "allow-delayed-peak-detect": "yes",
}

# Auto: High for a picture drawn at least this big, about a 720p screen's worth:
# one video over a 1080p window is 2 MP, one of 4 there 0.5
AUTO_HIGH_FROM_PX = 1_000_000
# ...unless shrunk from more than this many times the pixels, where High's
# downscaling costs the most
AUTO_HIGH_SHRUNK_UP_TO = 2.5
# Once High, it holds this far past either line, so a size going to and fro over
# one, as a window is dragged, doesn't have mpv build its shaders each time
AUTO_HIGH_HOLDS = 0.8


def high_options(option_info) -> dict[str, str]:
    """mpv's own defaults of the options FAST sets, as this libmpv has them, and
    Fast's for any it doesn't say."""

    options = dict(FAST)

    for name in FAST:
        default = (option_info(name) or {}).get("default-value")

        if isinstance(default, bool):
            options[name] = "yes" if default else "no"
        elif default is not None:
            options[name] = str(default)

    return options


def is_high(
    quality: MpvPictureQuality,
    drawn_px: int | None,
    source_px: int | None,
    was_high: bool = False,
) -> bool:
    """Pixels drawn on the screen and of the video they're drawn from, None while
    not known, which Auto takes for small."""

    if quality == MpvPictureQuality.HIGH:
        return True

    if quality == MpvPictureQuality.FAST or not drawn_px or not source_px:
        return False

    give = AUTO_HIGH_HOLDS if was_high else 1
    is_big = drawn_px >= AUTO_HIGH_FROM_PX * give
    is_shrunk_a_lot = source_px > drawn_px * AUTO_HIGH_SHRUNK_UP_TO / give

    return is_big and not is_shrunk_a_lot
