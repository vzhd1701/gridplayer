"""Media to drive the real app with, made by ffmpeg rather than kept in git.

Made once into build/test-media/<hash of this file>/ and taken from there
until this file changes. Run it to make them and see where they are:

    uv run python -m tests.real_app.media

What there is (every video a test pattern with a tone, small and short):

    folder/a.mp4 b.mp4 c.mp4  20s each, a folder to step through
    list.m3u                  the three, as a list of "Clip A" to "Clip C"
    feature/feature.mkv       60s: chapters Intro, Part One, Part Two and
                              Credits at 0, 15, 30 and 45s; English and
                              Spanish audio; English and French subtitles
                              ("English line 1" every 5s)
    feature/feature.de.srt    German subtitles to discover beside it
    feature/feature.commentary.m4a
                              audio to discover beside it
    hls/master.m3u8           30s HLS in 360p, 180p and 90p
    dubs/master.m3u8          30s HLS in 360p and 180p, dubbed into English
                              (the default) and Spanish as audio renditions
    shapes/square.mp4         10s, 640x360 of square pixels: what the others
                              look like
    shapes/wide_pixels.mp4    the same stored 320x360, its pixels twice as
                              wide as they are tall (SAR 2:1)
    shapes/wide_pixels.ts     an MPEG-TS stream 720x576 shown 16:9 (SAR
                              64:45), as a DVB channel is: VLC says how wide
                              its pixels are only once it is decoded
    shapes/phone.mp4          wide_pixels.mp4 tagged to be turned 90 degrees
                              to show it, so 9:16 on screen

The HLS ones are for serving over HTTP; see Driver.serve.
"""

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "build" / "test-media"

CHAPTERS = (
    (0, 15_000, "Intro"),
    (15_000, 30_000, "Part One"),
    (30_000, 45_000, "Part Two"),
    (45_000, 60_000, "Credits"),
)


@dataclass(frozen=True)
class Media:
    root: Path

    @property
    def folder(self) -> Path:
        return self.root / "folder"

    @property
    def clips(self) -> tuple[Path, Path, Path]:
        return tuple(self.folder / f"{n}.mp4" for n in "abc")

    @property
    def list_m3u(self) -> Path:
        return self.root / "list.m3u"

    @property
    def feature(self) -> Path:
        return self.root / "feature" / "feature.mkv"

    @property
    def hls(self) -> Path:
        return self.root / "hls"

    @property
    def dubs(self) -> Path:
        return self.root / "dubs"

    @property
    def shapes(self) -> Path:
        return self.root / "shapes"


def is_ffmpeg_installed() -> bool:
    return shutil.which("ffmpeg") is not None


def ensure() -> Media:
    """The media, made first if this version of the recipe has not been."""

    digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
    media = Media(ROOT / digest)

    if media.root.is_dir():
        return media

    # made aside and moved in whole, so a run cut short leaves nothing that
    # looks finished
    building = ROOT / f".building-{digest}-{os.getpid()}"
    shutil.rmtree(building, ignore_errors=True)
    _make(Media(building))

    try:
        building.rename(media.root)
    except OSError:
        # another run made it first
        shutil.rmtree(building, ignore_errors=True)

    return media


def _ffmpeg(*args, cwd: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *map(str, args)],
        cwd=cwd,
        check=True,
    )


def _tone(frequency: int, seconds: int) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={seconds}"]


def _pattern(seconds: int, size="320x180", source="testsrc") -> list[str]:
    return ["-f", "lavfi", "-i", f"{source}=size={size}:rate=25:duration={seconds}"]


def _srt(text: str, seconds: int) -> str:
    cues = []
    for i in range(seconds // 5):
        start = i * 5
        cues.append(
            f"{i + 1}\n00:00:{start:02d},000 --> 00:00:{start + 4:02d},500\n"
            f"{text} line {i + 1}\n"
        )
    return "\n".join(cues)


def _make(media: Media) -> None:
    media.folder.mkdir(parents=True)

    for name, frequency in zip("abc", (440, 550, 660)):
        _ffmpeg(
            *_pattern(20),
            *_tone(frequency, 20),
            "-metadata",
            f"title=Clip {name.upper()}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            f"{name}.mp4",
            cwd=media.folder,
        )

    media.list_m3u.write_text(
        "#EXTM3U\n"
        + "".join(f"#EXTINF:20,Clip {n.upper()}\nfolder/{n}.mp4\n" for n in "abc"),
        encoding="utf-8",
    )

    _make_feature(media.feature.parent)
    _make_hls(media.hls)
    _make_dubs(media.dubs)
    _make_shapes(media.shapes)


def _make_feature(where: Path) -> None:
    where.mkdir()

    (where / "en.srt").write_text(_srt("English", 60), encoding="utf-8")
    (where / "fr.srt").write_text(_srt("Francais", 60), encoding="utf-8")
    (where / "feature.de.srt").write_text(_srt("Deutsch", 60), encoding="utf-8")

    chapters = [";FFMETADATA1", "title=Feature"]
    for start, end, title in CHAPTERS:
        chapters += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}"]
        chapters.append(f"title={title}")
    (where / "chapters.txt").write_text("\n".join(chapters) + "\n", encoding="utf-8")

    _ffmpeg(
        *_pattern(60),
        *_tone(440, 60),
        *_tone(660, 60),
        "-i",
        "en.srt",
        "-i",
        "fr.srt",
        "-i",
        "chapters.txt",
        *("-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3", "-map", "4"),
        *("-map_metadata", "5", "-map_chapters", "5"),
        *("-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-c:s", "srt"),
        *("-metadata:s:a:0", "language=eng", "-metadata:s:a:0", "title=English"),
        *("-metadata:s:a:1", "language=spa", "-metadata:s:a:1", "title=Spanish"),
        *("-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=fre"),
        "feature.mkv",
        cwd=where,
    )
    _ffmpeg(*_tone(880, 60), "-c:a", "aac", "feature.commentary.m4a", cwd=where)

    for scratch in ("en.srt", "fr.srt", "chapters.txt"):
        (where / scratch).unlink()


def _make_hls(where: Path) -> None:
    where.mkdir()

    _ffmpeg(
        *_pattern(30, size="640x360", source="testsrc2"),
        *_tone(330, 30),
        "-filter_complex",
        "[0:v]split=3[a][b][c];[a]scale=640:360[o0];[b]scale=320:180[o1];"
        "[c]scale=160:90[o2]",
        *("-map", "[o0]", "-map", "[o1]", "-map", "[o2]"),
        *("-map", "1:a", "-map", "1:a", "-map", "1:a"),
        *("-c:v", "libx264", "-preset", "ultrafast", "-g", "25", "-c:a", "aac"),
        *("-b:v:0", "800k", "-b:v:1", "300k", "-b:v:2", "100k"),
        *("-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod"),
        *("-master_pl_name", "master.m3u8"),
        *("-var_stream_map", "v:0,a:0 v:1,a:1 v:2,a:2"),
        "v%v/index.m3u8",
        cwd=where,
    )


def _make_dubs(where: Path) -> None:
    where.mkdir()

    _ffmpeg(
        *_pattern(30, size="640x360", source="testsrc2"),
        *_tone(330, 30),
        *_tone(550, 30),
        "-filter_complex",
        "[0:v]split=2[a][b];[a]scale=640:360[o0];[b]scale=320:180[o1]",
        *("-map", "[o0]", "-map", "[o1]", "-map", "1:a", "-map", "2:a"),
        *("-c:v", "libx264", "-preset", "ultrafast", "-g", "25", "-c:a", "aac"),
        *("-b:v:0", "800k", "-b:v:1", "300k"),
        *("-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod"),
        *("-master_pl_name", "master.m3u8"),
        "-var_stream_map",
        "v:0,agroup:aud v:1,agroup:aud"
        " a:0,agroup:aud,language:en,default:yes,name:english"
        " a:1,agroup:aud,language:es,name:spanish",
        "v%v/index.m3u8",
        cwd=where,
    )


def _make_shapes(where: Path) -> None:
    where.mkdir()

    h264 = ("-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p")

    _ffmpeg(
        *_pattern(10, size="640x360", source="testsrc2"), *h264, "square.mp4", cwd=where
    )
    _ffmpeg(
        *_pattern(10, size="640x360", source="testsrc2"),
        *("-vf", "scale=320:360,setsar=2/1"),
        *h264,
        "wide_pixels.mp4",
        cwd=where,
    )
    _ffmpeg(
        *_pattern(10, size="720x576", source="testsrc2"),
        *("-vf", "setsar=64/45"),
        *h264,
        *("-f", "mpegts"),
        "wide_pixels.ts",
        cwd=where,
    )
    _ffmpeg(
        *("-display_rotation:v:0", "90"),
        *("-i", "wide_pixels.mp4", "-c", "copy"),
        "phone.mp4",
        cwd=where,
    )


if __name__ == "__main__":
    print(ensure().root)
