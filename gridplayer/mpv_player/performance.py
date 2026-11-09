"""What the performance settings come to in mpv's options.

The presets were picked by measuring grids of 1080p60 video on a Radeon 610M.
Each one names every option any of them touches, so that going from one to
another leaves nothing of the last one behind.
"""

from gridplayer.params.static import HardwareDecoding, VideoQuality

_MEGAPIXEL = 1_000_000

# how big a video is shown, in real pixels, for Auto to spend more on it
AUTO_BALANCED_FROM_PX = 0.6 * _MEGAPIXEL
AUTO_HIGH_FROM_PX = 1.5 * _MEGAPIXEL

_LADDER = (VideoQuality.FAST, VideoQuality.BALANCED, VideoQuality.HIGH)

# of what should have been shown over a check, once it is this far behind it
# is worth giving something up
_DROPPED_SHARE_TO_STEP_DOWN = 0.1

# a little over the screen's rate is still every frame shown
_DISPLAY_RATE_MARGIN = 1.05

_MPV_DEFAULTS = {
    "scale": "lanczos",
    "dscale": "hermite",
    "dither": "fruit",
    "correct-downscaling": "yes",
    "linear-downscaling": "yes",
    "sigmoid-upscaling": "yes",
    "scale-antiring": "0",
    "hdr-compute-peak": "auto",
    "allow-delayed-peak-detect": "no",
    "hdr-peak-percentile": "0",
    "hdr-contrast-recovery": "0",
}

_WITHOUT_LINEAR_LIGHT = {
    "correct-downscaling": "no",
    "linear-downscaling": "no",
    "sigmoid-upscaling": "no",
}

QUALITY_OPTIONS = {
    # mpv's own "fast" profile
    VideoQuality.FAST: {
        **_MPV_DEFAULTS,
        **_WITHOUT_LINEAR_LIGHT,
        "scale": "bilinear",
        "dscale": "bilinear",
        "dither": "no",
        "hdr-compute-peak": "no",
        "allow-delayed-peak-detect": "yes",
    },
    VideoQuality.BALANCED: {
        **_MPV_DEFAULTS,
        **_WITHOUT_LINEAR_LIGHT,
        "scale": "catmull_rom",
        "dscale": "bilinear",
        "dither": "no",
    },
    VideoQuality.HIGH: _MPV_DEFAULTS,
    # mpv's own "high-quality" profile
    VideoQuality.MAXIMUM: {
        **_MPV_DEFAULTS,
        "scale": "ewa_lanczossharp",
        "scale-antiring": "0.6",
        "hdr-peak-percentile": "99.995",
        "hdr-contrast-recovery": "0.30",
    },
}


def auto_quality(pixels: float) -> VideoQuality:
    """The most worth spending on a video shown this big."""

    if pixels >= AUTO_HIGH_FROM_PX:
        return VideoQuality.HIGH

    if pixels >= AUTO_BALANCED_FROM_PX:
        return VideoQuality.BALANCED

    return VideoQuality.FAST


def is_better(quality: VideoQuality, other: VideoQuality) -> bool:
    return _LADDER.index(quality) > _LADDER.index(other)


def stepped_down(quality: VideoQuality, steps: int) -> VideoQuality:
    return _LADDER[max(_LADDER.index(quality) - steps, 0)]


def is_falling_behind(
    dropped: int,
    elapsed_s: float,
    fps: float | None,
    speed: float,
    display_fps: float | None,
) -> bool:
    """Whether frames went missing that a cheaper picture might have saved.

    Not when the video has more frames than the screen can show, as the rest
    are dropped whatever is done.
    """

    if dropped <= 0 or elapsed_s <= 0 or not fps:
        return False

    played_fps = fps * speed

    if display_fps and played_fps > display_fps * _DISPLAY_RATE_MARGIN:
        return False

    return dropped / (elapsed_s * played_fps) > _DROPPED_SHARE_TO_STEP_DOWN


def hwdec_value(mode: HardwareDecoding, needs_frames_in_memory: bool) -> str:
    """mpv's hwdec for the setting, on a driver that draws with the GPU."""

    if mode is HardwareDecoding.OFF:
        return "no"

    if mode is HardwareDecoding.COPY or needs_frames_in_memory:
        return "auto-copy-safe"

    return "auto-safe"
