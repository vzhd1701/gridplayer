"""The media the mpv scenarios play, made with libmpv's own encoder.

Kept under build/, so that only the first run pays for making it.
"""

import struct
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEDIA_DIR = REPO / "build" / "mpv-test-media"

_DONE_MARK = "done-v1"

_DURATION = 20
_VIDEO = f"testsrc2=size=640x360:rate=30:duration={_DURATION}"

# the tone in the left channel only, for the channel modes to be told apart
_LEFT_ONLY = f"aevalsrc=0.5*sin(2*PI*440*t)|0:s=48000:c=stereo:d={_DURATION}"

# the tone in a side channel, which a plain downmix keeps on one side
_SURROUND = f"aevalsrc=0|0|0|0|0.5*sin(2*PI*440*t)|0:s=48000:c=5.1:d={_DURATION}"

_SRT = "1\n00:00:00,000 --> 00:00:20,000\n{}\n"

SUBTITLES = {
    "en.srt": "ENGLISH TRACK",
    "fr.srt": "PISTE FRANCAISE",
    "ext.srt": "EXTERNAL FILE",
    "ext2.srt": "SECOND EXTERNAL",
}
CYRILLIC_TEXT = "Привет мир"


def ensure() -> Path:
    if (MEDIA_DIR / _DONE_MARK).exists():
        return MEDIA_DIR

    (MEDIA_DIR / "hls").mkdir(parents=True, exist_ok=True)

    _make_videos()
    _make_text_files()
    _make_multi_track_list()
    _make_rotated()

    (MEDIA_DIR / _DONE_MARK).touch()

    return MEDIA_DIR


def _encode(target: Path, source: str, **options) -> None:
    import mpv

    player = mpv.MPV(config=False, o=str(target), **options)
    player.play(source)
    player.wait_for_playback()
    player.terminate()


def _make_videos() -> None:
    _encode(
        MEDIA_DIR / "clip.mp4",
        f"av://lavfi:{_VIDEO}",
        ovc="libx264",
        oac="aac",
        ovcopts="g=30",
        audio_files=f"av://lavfi:{_LEFT_ONLY}",
    )

    for freq in (880, 220):
        _encode(
            MEDIA_DIR / f"tone_{freq}.m4a",
            f"av://lavfi:sine=frequency={freq}:sample_rate=48000:duration={_DURATION}",
            oac="aac",
            vid="no",
        )

    _encode(
        MEDIA_DIR / "tone_51.m4a",
        f"av://lavfi:{_SURROUND}",
        oac="aac",
        vid="no",
        audio_channels="5.1",
    )

    _encode(
        MEDIA_DIR / "hls" / "index.m3u8",
        f"av://lavfi:{_VIDEO}",
        ovc="libx264",
        oac="aac",
        ovcopts="g=60",
        of="hls",
        ofopts="hls_time=2,hls_list_size=0,hls_playlist_type=vod",
        audio_files=(
            f"av://lavfi:sine=frequency=440:sample_rate=48000:duration={_DURATION}"
        ),
    )


def _make_text_files() -> None:
    for name, text in SUBTITLES.items():
        (MEDIA_DIR / name).write_text(_SRT.format(text), encoding="utf-8")

    (MEDIA_DIR / "cyr.srt").write_bytes(_SRT.format(CYRILLIC_TEXT).encode("cp1251"))
    (MEDIA_DIR / "garbage.mp4").write_bytes(b"this is not a video at all " * 500)


def _edl_part(path: Path, *rest: str) -> str:
    text = path.as_posix()

    return ",".join([f"%{len(text.encode())}%{text}", *rest])


def _make_multi_track_list() -> None:
    """One file as far as mpv can tell, with two sound and two subtitle tracks."""

    clip = MEDIA_DIR / "clip.mp4"

    lines = [
        "# mpv EDL v0",
        _edl_part(clip, "0", "10", "title=Chapter One"),
        _edl_part(clip, "10", "10", "title=Chapter Two"),
    ]

    for name, lang, title in (
        ("tone_880.m4a", "fre", "Commentaire"),
        ("en.srt", "eng", "English subs"),
        ("fr.srt", "fre", "Sous-titres"),
    ):
        lines += [
            "!new_stream",
            "!no_clip",
            "!no_chapters",
            f"!track_meta,lang={lang},title={title}",
            _edl_part(MEDIA_DIR / name),
        ]

    # bytes: the header has to end in a bare newline to be recognized
    (MEDIA_DIR / "multi.edl").write_bytes(("\n".join(lines) + "\n").encode())


def _make_rotated() -> None:
    """The clip with its video track saying to turn it by 90 degrees."""

    data = bytearray((MEDIA_DIR / "clip.mp4").read_bytes())

    position = data.find(b"tkhd")

    while position >= 0:
        is_long = data[position + 4] == 1
        matrix = position + 8 + (32 if is_long else 20) + 16

        width = struct.unpack(">I", data[matrix + 36 : matrix + 40])[0] >> 16
        height = struct.unpack(">I", data[matrix + 40 : matrix + 44])[0] >> 16

        if width and height:
            turned = (0, 0x10000, 0, 0xFFFF0000, 0, 0, height << 16, 0, 0x40000000)
            data[matrix : matrix + 36] = struct.pack(">9I", *turned)

        position = data.find(b"tkhd", position + 4)

    (MEDIA_DIR / "rot90.mp4").write_bytes(data)
