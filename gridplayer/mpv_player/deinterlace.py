"""The deinterlace settings, in what mpv has.

Left to itself mpv picks what suits the decoder, on the GPU where it can. VLC's modes by
name are filters here, so hardware decoded frames come back to the CPU for them. They
keep the picture's height, as half of it would be the view's size changing too, but for
a row on an odd height. Those that halve it leave mpv thinking the pixels are twice as
wide, which shows nowhere: the picture is drawn by the size from before the filters.

Bob and Linear can't start on an odd height, and only a log line says so. Not seen on a
video that's really interlaced, so that's left: see docs/plans/MPV_PLAN.md.
"""

from gridplayer.params.static import VideoDeinterlace, VideoDeinterlaceMode

# A line goes half with itself and a quarter each with the ones above and below it
_BLEND_LINES = "0 1 0 0 2 0 0 1 0"

# X and Phosphor have nothing like them in mpv, so these are what's nearest: one picture
# for each frame, and one for each field.
_MODE_FILTERS = {
    VideoDeinterlaceMode.DISCARD: "field=top,scale=h=ih*2:flags=neighbor",
    VideoDeinterlaceMode.BLEND: (
        f"convolution={_BLEND_LINES}:{_BLEND_LINES}:{_BLEND_LINES}"
        ":0 0 0 0 1 0 0 0 0:0.25:0.25:0.25:1"
    ),
    VideoDeinterlaceMode.MEAN: "scale=h=ih/2:flags=area,scale=h=ih*2:flags=bilinear",
    VideoDeinterlaceMode.BOB: "separatefields,scale=h=ih*2:flags=neighbor",
    VideoDeinterlaceMode.LINEAR: "separatefields,scale=h=ih*2:flags=bilinear",
    VideoDeinterlaceMode.X: "bwdif=mode=send_frame",
    VideoDeinterlaceMode.YADIF: "yadif=mode=send_frame",
    VideoDeinterlaceMode.YADIF2X: "yadif=mode=send_field",
    VideoDeinterlaceMode.PHOSPHOR: "bwdif=mode=send_field",
    VideoDeinterlaceMode.IVTC: "fieldmatch=combmatch=full,yadif=deint=interlaced,decimate",
}


def unavailable_modes(abilities) -> frozenset[VideoDeinterlaceMode]:
    """The modes whose filters this libmpv's FFmpeg hasn't got: Discard, Blend,
    Bob, Linear and IVTC in MPVKit's. None of them while that's not known."""

    if abilities is None:
        return frozenset()

    return frozenset(
        mode
        for mode, chain in _MODE_FILTERS.items()
        if not abilities.has_filters(_filter_names(chain))
    )


def _filter_names(chain: str) -> set[str]:
    return {part.split("=", 1)[0] for part in chain.split(",")}


def deinterlace_options(
    deinterlace: VideoDeinterlace,
    mode: VideoDeinterlaceMode,
    has_auto: bool,
    is_interlaced: bool,
) -> dict[str, str]:
    """All mpv is to be told, so that going back from any of it gets there too."""

    # mpv goes by what each frame says itself: only from 0.40, and only for a
    # deinterlacer of its own choosing
    if (
        deinterlace == VideoDeinterlace.AUTO
        and mode == VideoDeinterlaceMode.AUTO
        and has_auto
    ):
        return {"deinterlace": "auto", "vf": ""}

    if deinterlace == VideoDeinterlace.OFF or (
        deinterlace == VideoDeinterlace.AUTO and not is_interlaced
    ):
        return {"deinterlace": "no", "vf": ""}

    mode_filter = _MODE_FILTERS.get(mode)

    if mode_filter is None:
        return {"deinterlace": "yes", "vf": ""}

    return {"deinterlace": "no", "vf": f"lavfi=[{mode_filter}]"}
