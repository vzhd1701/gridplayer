"""What the mpv drivers have to do, checked against the real libmpv.

Each scenario_ function is reported as a test of its own, see test_scenarios.py.
"""

import math
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from PyQt5.QtGui import QImage

import gridplayer.mpv_player.player as player_module
from gridplayer.models.audio_device import AudioDevice
from gridplayer.models.audio_selection import (
    AudioDisabled,
    AudioExternal,
    AudioLanguage,
    AudioPreferred,
)
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleExternal,
    SubtitleLanguage,
    SubtitlePreferred,
    SubtitleTrackId,
)
from gridplayer.mpv_player.performance import QUALITY_OPTIONS
from gridplayer.params.static import (
    AudioChannelMode,
    GpuChoice,
    HardwareDecoding,
    SubtitleOutline,
    VideoQuality,
    VideoTransform,
)
from gridplayer.params.subtitle_style import mpv_subtitle_style_options
from gridplayer.settings import Settings
from gridplayer.utils import item_info
from gridplayer.utils.gpu_adapters import gpu_adapters
from tests.mpv_player.harness import (
    Session,
    changed_pixels,
    is_red,
    make_input,
    measure_sound,
    pcm_options,
)
from tests.mpv_player.media import CYRILLIC_TEXT, SUBTITLES

LOOP_TOLERANCE = 0.2


def _near(value, target, tolerance=LOOP_TOLERANCE):
    return abs(value - target) <= target * tolerance


# --- subtitles


def scenario_subtitle_tracks(ctx):
    s = Session(ctx.out)
    media = s.load(make_input(ctx.media / "multi.edl"))

    ctx.check("loads", media is not None)
    if media is None:
        return s.close()

    ctx.check("two tracks of each", len(media.audio_tracks) == 2)
    ctx.check("two subtitle tracks", len(media.subtitle_tracks) == 2)
    ctx.check("languages read", media.subtitle_tracks[1].language == "eng")
    ctx.check("titles read", media.subtitle_tracks[2].description == "Sous-titres")
    ctx.check("length", abs(media.length - 20000) < 100, media.length)
    ctx.check(
        "chapters named",
        [c.name for c in media.chapters] == ["Chapter One", "Chapter Two"],
        media.chapters,
    )
    ctx.check("second chapter's start", media.chapters[1].start_ms == 10000)
    ctx.check("none shown when off", s.prop("sid") is False, s.prop("sid"))

    bare = s.screenshot()

    s.cmd("set_subtitle_track", 1)
    s.pump(0.6)
    ctx.check(
        "track one", s.prop("sub-text") == SUBTITLES["en.srt"], s.prop("sub-text")
    )
    english = s.screenshot()
    ctx.check("drawn on the picture", changed_pixels(bare, english) > 20)

    s.cmd("set_subtitle_track", 2)
    s.pump(0.6)
    ctx.check(
        "track two", s.prop("sub-text") == SUBTITLES["fr.srt"], s.prop("sub-text")
    )

    s.cmd("set_subtitle_delay", 1500)
    s.pump(0.3)
    ctx.check("delay", abs(s.prop("sub-delay") - 1.5) < 0.001)
    s.cmd("set_subtitle_delay", 0)

    mark = s.mark()
    s.cmd("add_subtitle_slave", (ctx.media / "ext.srt").as_uri())
    got = s.wait("tracks_changed_emit", 5, after=mark)
    s.pump(0.3)

    ctx.check("added file is listed", got and len(got[0].subtitle_tracks) == 3)
    ctx.check("it counts as external", got and got[0].external_subtitle_ids == (3,))
    ctx.check("and is shown", s.prop("sid") == 3, s.prop("sid"))
    ctx.check(
        "the file's own default stays",
        got and got[0].default_subtitle_track_id is None,
    )

    s.pump(1.2)
    s.cmd("add_subtitle_slave", (ctx.media / "ext2.srt").as_uri())
    s.cmd("add_subtitle_slave", (ctx.media / "cyr.srt").as_uri())
    s.pump(0.8)
    ctx.check("first of several picked is shown", s.prop("sid") == 4, s.prop("sid"))

    s.cmd("set_subtitle_track", -1)
    s.pump(0.5)
    ctx.check("off again", s.prop("sid") is False)

    s.close()
    ctx.check("no crash", s.crashed is None, s.crashed)


def scenario_subtitle_selection_at_load(ctx):
    for label, selection, kwargs, wanted in (
        ("by language", SubtitleLanguage(tag="fr"), {}, 2),
        ("by id", SubtitleTrackId(id=1), {}, 1),
        ("preferred", SubtitlePreferred(), {"subtitle_languages": "fr,en"}, 2),
        (
            "preferred, no match",
            SubtitlePreferred(),
            {"subtitle_languages": "de"},
            False,
        ),
        ("container default", SubtitleDefault(), {}, False),
    ):
        s = Session(ctx.out)
        media = s.load(make_input(ctx.media / "multi.edl", sub=selection, **kwargs))
        s.pump(0.4)
        ctx.check(label, media is not None and s.prop("sid") == wanted, s.prop("sid"))
        s.close()


def scenario_external_subtitles_at_load(ctx):
    first = ctx.media / "ext2.srt"
    second = ctx.media / "ext.srt"

    s = Session(ctx.out)
    media = s.load(
        make_input(
            ctx.media / "clip.mp4",
            sub=SubtitleExternal(file=first, track=0),
            sub_slaves=(first.as_uri(), second.as_uri()),
        )
    )
    s.pump(0.5)

    ctx.check("listed", media is not None and media.external_subtitle_ids == (1, 2))
    ctx.check("selection honoured", s.prop("sid") == 1, s.prop("sid"))
    ctx.check(
        "named after the file", media.subtitle_tracks[1].description == "ext2.srt"
    )
    ctx.check(
        "its text", s.prop("sub-text") == SUBTITLES["ext2.srt"], s.prop("sub-text")
    )
    s.close()


def scenario_subtitle_encoding(ctx):
    cyrillic = ctx.media / "cyr.srt"

    s = Session(ctx.out)
    media = s.load(
        make_input(
            ctx.media / "clip.mp4",
            subtitle_encoding="Windows-1251",
            sub=SubtitleExternal(file=cyrillic, track=0),
            sub_slaves=(cyrillic.as_uri(),),
        )
    )
    s.pump(0.5)

    ctx.check("loads", media is not None)
    ctx.check("read as asked", s.prop("sub-text") == CYRILLIC_TEXT, s.prop("sub-text"))
    s.close()

    # mpv would guess that one right by itself: only a wrong one shows it obeys
    s = Session(ctx.out)
    s.load(
        make_input(
            ctx.media / "clip.mp4",
            subtitle_encoding="KOI8-R",
            sub=SubtitleExternal(file=cyrillic, track=0),
            sub_slaves=(cyrillic.as_uri(),),
        )
    )
    s.pump(0.5)

    ctx.check(
        "the setting is what is obeyed",
        s.prop("sub-text") not in {None, "", CYRILLIC_TEXT},
        s.prop("sub-text"),
    )
    s.close()


def scenario_subtitle_style(ctx):
    external = ctx.media / "ext.srt"
    picked = SubtitleExternal(file=external, track=0)

    def picture(extra, sub=None, slaves=()):
        s = Session(ctx.out, extra)
        media = s.load(make_input(ctx.media / "clip.mp4", sub=sub, sub_slaves=slaves))
        s.pump(0.5)
        shot = s.screenshot()
        s.close()
        ctx.check("loads", media is not None)
        return shot

    style = mpv_subtitle_style_options(
        {
            "subtitles/size_scale": 180,
            "subtitles/color": "#ffff00",
            "subtitles/bold": True,
            "subtitles/outline": SubtitleOutline.THICK,
            "subtitles/outline_color": "#ff0000",
            "subtitles/background": True,
            "subtitles/background_color": "#0000ff",
        }
    )

    s = Session(ctx.out)
    s.load(make_input(ctx.media / "clip.mp4"))
    s.pump(0.5)
    bare = s.screenshot()
    s.close()

    plain = picture({}, picked, (external.as_uri(),))
    styled = picture(style, picked, (external.as_uri(),))

    plain_change = changed_pixels(bare, plain)
    styled_change = changed_pixels(bare, styled)

    ctx.check("plain subtitles draw", plain_change > 20, plain_change)
    ctx.check(
        "style changes what is drawn",
        styled_change > plain_change * 2,
        f"{plain_change} -> {styled_change}",
    )


def scenario_screenshot_of_a_zoomed_view(ctx):
    s = Session(ctx.out)
    media_input = make_input(ctx.media / "clip.mp4")
    media = s.load(media_input)
    s.pump(0.3)

    view = media_input.view._replace(scale=3.0)
    s.cmd("adjust_view", (640, 360), view)
    s.pump(0.6)

    shot = QImage(s.screenshot())

    ctx.check("loads", media is not None)
    ctx.check(
        "cropped to the view", s.prop("video-crop") != "0x0+0+0", s.prop("video-crop")
    )
    ctx.check("screenshot is of the view", shot.width() == 214, shot.width())
    s.close()


# --- sound


def _sound_run(ctx, setup=None, source="clip.mp4", **kwargs):
    target = ctx.out / "sound.pcm"

    s = Session(ctx.out, pcm_options(target))
    media = s.load(make_input(ctx.media / source, paused=False, position=0, **kwargs))

    if media is None:
        s.close()
        return None, None, s

    s.cmd("audio_set_mute", False)
    s.cmd("audio_set_volume", 1.0)

    if setup is not None:
        setup(s)

    s.pump(2.2)
    s.close()

    return measure_sound(target), media, s


def scenario_sound_tracks(ctx):
    sound, media, _ = _sound_run(ctx)
    ctx.check("default track", sound and _near(sound.left_freq, 440), sound)
    ctx.check("tone left only", sound and sound.right < 0.01, sound)

    sound, _, _ = _sound_run(
        ctx, lambda s: s.cmd("set_audio_track", 2), source="multi.edl"
    )
    ctx.check("switching tracks", sound and _near(sound.left_freq, 880), sound)

    sound, media, _ = _sound_run(
        ctx, source="multi.edl", audio=AudioPreferred(), audio_languages="fr"
    )
    ctx.check("preferred language", sound and _near(sound.left_freq, 880), sound)
    ctx.check("is the current track", media and media.cur_audio_track_id == 2)
    ctx.check(
        "the file's own default stays", media and media.default_audio_track_id == 1
    )

    sound, media, _ = _sound_run(
        ctx, source="multi.edl", audio=AudioLanguage(tag="fre")
    )
    ctx.check("by language", sound and _near(sound.left_freq, 880), sound)

    sound, media, _ = _sound_run(ctx, audio=AudioDisabled())
    ctx.check("disabled is silent", sound and sound.left < 0.001, sound)
    ctx.check("with no current track", media and media.cur_audio_track_id is None)


def scenario_sound_levels(ctx):
    full, _, _ = _sound_run(ctx)
    ctx.check("plays", full and full.left > 0.1, full)

    muted, _, _ = _sound_run(ctx, lambda s: s.cmd("audio_set_mute", True))
    ctx.check("muted is silent", muted and muted.left < 0.001, muted)

    half, _, _ = _sound_run(ctx, lambda s: s.cmd("audio_set_volume", 0.5))
    ctx.check("half is quieter", half and 0.02 < half.left < full.left * 0.8, half)

    loud, _, _ = _sound_run(ctx, lambda s: s.cmd("audio_set_volume", 1.3))
    ctx.check("past 100% is louder", loud and loud.left > full.left * 1.3, loud)


def scenario_channel_modes(ctx):
    for mode, test in (
        (AudioChannelMode.UNSET, lambda a: a.left > 0.1 and a.right < 0.01),
        (AudioChannelMode.STEREO, lambda a: a.left > 0.1 and a.right < 0.01),
        (AudioChannelMode.RSTEREO, lambda a: a.left < 0.01 and a.right > 0.1),
        (AudioChannelMode.LEFT, lambda a: a.left > 0.1 and a.right > 0.1),
        (AudioChannelMode.RIGHT, lambda a: a.left < 0.01 and a.right < 0.01),
        (
            AudioChannelMode.MONO,
            lambda a: a.left > 0.05 and _near(a.left, a.right, 0.1),
        ),
        (
            AudioChannelMode.HEADPHONES,
            lambda a: a.left > 0.1 and 0.005 < a.right < a.left,
        ),
    ):
        sound, _, s = _sound_run(
            ctx, lambda s, m=mode: s.cmd("set_audio_channel_mode", m)
        )
        ctx.check(mode.name, sound and test(sound), sound)
        ctx.check(
            f"{mode.name} filter holds",
            not any("Disabling filter" in line for line in s.lines),
        )


def scenario_surround(ctx):
    file = ctx.media / "tone_51.m4a"
    kwargs = {"audio": AudioExternal(file=file, track=0), "audio_slave": file.as_uri()}

    sound, _, _ = _sound_run(ctx, **kwargs)
    ctx.check(
        "a plain downmix keeps a side channel on its side",
        sound and sound.right < 0.005,
        sound,
    )

    sound, _, _ = _sound_run(
        ctx,
        lambda s: s.cmd("set_audio_channel_mode", AudioChannelMode.DOLBYS),
        **kwargs,
    )
    ctx.check(
        "Dolby Surround matrixes it into both", sound and sound.right > 0.02, sound
    )


def scenario_external_sound(ctx):
    file = ctx.media / "tone_220.m4a"

    sound, media, _ = _sound_run(
        ctx, audio=AudioExternal(file=file, track=0), audio_slave=file.as_uri()
    )
    ctx.check("at load", sound and _near(sound.left_freq, 220), sound)
    ctx.check("counts as external", media and media.external_audio_ids == (2,))

    sound, _, _ = _sound_run(ctx, lambda s: s.cmd("add_audio_slave", file.as_uri()))
    ctx.check("added while playing", sound and _near(sound.left_freq, 220), sound)


def scenario_sound_output(ctx):
    s = Session(ctx.out)
    media = s.load(make_input(ctx.media / "clip.mp4"))

    ctx.check("devices listed", media is not None and len(media.audio_devices) > 0)

    s.cmd("set_audio_delay", -700)
    s.pump(0.3)
    ctx.check("delay", abs(s.prop("audio-delay") + 0.7) < 0.001)

    if media is not None and media.audio_devices:
        device = media.audio_devices[0]

        s.cmd("set_audio_device", device)
        s.pump(0.5)
        ctx.check("picking a device", s.prop("audio-device") == device.id)

        s.cmd("set_audio_device", AudioDevice(id="nonsense", name="gone"))
        s.pump(0.5)
        ctx.check(
            "one that has gone is left alone", s.prop("audio-device") == device.id
        )

        s.cmd("set_audio_device", None)
        s.pump(0.5)
        ctx.check("back to the system's", s.prop("audio-device") == "auto")

    s.close()

    s = Session(ctx.out)
    s.load(make_input(ctx.media / "clip.mp4", paused=False, position=0))
    s.cmd("audio_set_mute", False)
    s.cmd("audio_set_volume", 0.3)
    s.pump(1.5)
    ctx.check(
        "the real output opens", s.prop("current-ao") is not None, s.prop("current-ao")
    )
    s.close()


# --- streams


class _Server(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    media = None
    seen = {}
    live_start = 0.0
    is_live_ended = False

    def log_message(self, *args): ...

    def _send(self, body, content_type, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        _Server.seen.setdefault(self.path, dict(self.headers))

        if self.path == "/hang.mp4":
            time.sleep(30)
            return

        if self.path.startswith("/live/"):
            self._send_live()
            return

        path = _Server.media / self.path.lstrip("/")

        if not path.is_file():
            self._send(b"nope", "text/plain", 404)
            return

        data = path.read_bytes()
        wanted = self.headers.get("Range")

        if wanted:
            start = int(wanted.split("=")[1].split("-")[0])
            self._send(
                data[start:],
                "video/mp4",
                206,
                {"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"},
            )
            return

        is_list = path.suffix == ".m3u8"
        self._send(data, "application/vnd.apple.mpegurl" if is_list else "video/mp4")

    def _send_live(self):
        segments = sorted((_Server.media / "hls").glob("*.ts"))
        name = self.path.rsplit("/", 1)[-1]

        if name.endswith(".ts"):
            self._send(
                segments[int(name[:-3]) % len(segments)].read_bytes(), "video/mp2t"
            )
            return

        sequence = int((time.monotonic() - _Server.live_start) / 2)

        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-TARGETDURATION:3",
            f"#EXT-X-MEDIA-SEQUENCE:{sequence}",
        ]

        for number in range(sequence, sequence + 4):
            lines += ["#EXTINF:2.0,", f"{number}.ts"]

        if _Server.is_live_ended:
            lines.append("#EXT-X-ENDLIST")

        self._send("\n".join(lines).encode(), "application/vnd.apple.mpegurl")


class _Serving:
    def __init__(self, media):
        _Server.media = media
        _Server.seen = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Server)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()


def scenario_http(ctx):
    with _Serving(ctx.media) as serving:
        s = Session(ctx.out)
        media = s.load(
            make_input(
                f"{serving.base}/clip.mp4",
                position=0,
                paused=False,
                headers={"User-Agent": "GP-Test/1", "Referer": "http://example.test/"},
            )
        )

        ctx.check("loads", media is not None and abs(media.length - 20000) < 100)

        headers = _Server.seen.get("/clip.mp4", {})
        ctx.check("user agent sent", headers.get("User-Agent") == "GP-Test/1", headers)
        ctx.check(
            "referer sent", headers.get("Referer") == "http://example.test/", headers
        )

        mark = s.mark()
        s.cmd("set_time", 12000)
        s.pump(1.5)

        times = [a[0] for n, a in s.events[mark:] if n == "time_changed_emit"]
        ctx.check("seeks", times and 12000 <= times[-1] < 14500, times[-3:])
        s.close()


def scenario_hls(ctx):
    with _Serving(ctx.media) as serving:
        s = Session(ctx.out)
        media = s.load(make_input(f"{serving.base}/hls/index.m3u8", position=3000))

        ctx.check("has its length", media is not None and 19000 < media.length < 21000)
        position = (s.prop("time-pos") or 0) * 1000
        ctx.check("starts where asked", 2900 < position < 3600, position)
        s.close()


def scenario_live_stream(ctx):
    with _Serving(ctx.media) as serving:
        _Server.live_start = time.monotonic()
        _Server.is_live_ended = False

        s = Session(ctx.out)
        media = s.load(
            make_input(f"{serving.base}/live/index.m3u8", position=0, paused=False)
        )

        ctx.check("taken for live", media is not None and media.is_live)
        if media is None:
            return s.close()

        ctx.check("does not loop", s.prop("loop-file") is False, s.prop("loop-file"))

        s.pump(1.5)
        mark = s.mark()
        s.cmd("snapshot")
        snapshot = s.wait("snapshot_taken_emit", 6, after=mark)
        ctx.check("snapshot for a pause", snapshot and snapshot[0], snapshot)

        s.cmd("set_pause", True)
        got = s.wait("playback_status_changed_emit", 4, after=mark)
        ctx.check("pause is reported", got is not None and bool(got[0]), got)

        s.pump(1.0)
        mark = s.mark()
        s.cmd("set_pause", False)
        got = s.wait("playback_status_changed_emit", 4, after=mark)
        ctx.check("resume is reported", got is not None and not got[0], got)

        s.pump(1.0)
        _Server.is_live_ended = True

        got = s.wait("error_state", 25)
        ctx.check("its end is reported", got and got[0] == "Live stream ended", got)
        s.close()


def scenario_what_will_not_play(ctx):
    failed = "Failed to load media"

    with _Serving(ctx.media) as serving:
        for label, uri in (
            ("404", f"{serving.base}/missing.mp4"),
            ("connection refused", "http://127.0.0.1:9/none.mp4"),
            ("not a video", ctx.media / "garbage.mp4"),
            ("missing file", ctx.media / "does_not_exist.mp4"),
        ):
            is_missing = label == "missing file"

            s = Session(ctx.out)
            media_input = make_input(
                ctx.media / "clip.mp4" if is_missing else uri, position=0
            )
            media_input.uri = str(uri)
            s.cmd("load_video", media_input)
            got = s.wait("error_state", 12)
            ctx.check(label, got and got[0] == failed, got)
            s.close()

        real_settings = player_module.Settings

        player_module.Settings = lambda: SimpleNamespace(
            sync_get=lambda key: (
                3
                if key == "player/video_init_timeout"
                else real_settings().sync_get(key)
            )
        )

        try:
            s = Session(ctx.out)
            s.cmd("load_video", make_input(f"{serving.base}/hang.mp4", position=0))
            got = s.wait("error_state", 10)
            ctx.check("no answer times out", got and got[0] == "Buffering timeout", got)

            started = time.monotonic()
            s.close()
            ctx.check("and closes at once", time.monotonic() - started < 3)
        finally:
            player_module.Settings = real_settings


# --- the software driver


def scenario_software_driver(ctx):
    s = Session(ctx.out, is_software=True)
    media = s.load(make_input(ctx.media / "multi.edl"))

    ctx.check("loads", media is not None)
    if media is None:
        return s.close()

    s.pump(0.6)

    sizes = [a for n, a in s.events if n == "init_frame"]
    ctx.check(
        "says the frame's size", sizes and sizes[-1][:2] == (640, 360), sizes[-1:]
    )
    ctx.check("frames arrive", any(n == "process_image" for n, _ in s.events))
    ctx.check("decodes in software", s.prop("hwdec-current") in {None, "no"})

    before = ctx.out / "sw_before.png"
    s.software_frame().save(str(before))

    s.cmd("set_subtitle_track", 2)
    s.pump(0.8)

    after = ctx.out / "sw_after.png"
    s.software_frame().save(str(after))

    ctx.check("draws subtitles", changed_pixels(before, after) > 20)

    shot = s.screenshot()
    ctx.check("takes a screenshot", bool(shot), shot)

    mark = s.mark()
    s.cmd("set_pause", False)
    s.pump(1.0)

    frames = sum(1 for n, _ in s.events[mark:] if n == "process_image")
    ctx.check("plays at the frame rate", 15 <= frames <= 45, frames)

    mark = s.mark()
    s.cmd("set_time", 9000)
    s.pump(0.6)
    s.cmd("set_pause", True)
    s.pump(0.5)

    times = [a[0] for n, a in s.events[mark:] if n == "time_changed_emit"]
    ctx.check("seeks", times and 8900 <= times[-1] < 11000, times[-2:])

    s.close()
    ctx.check("no crash", s.crashed is None, s.crashed)


def _software_picture(ctx, source, transform=VideoTransform.NONE):
    s = Session(ctx.out, is_software=True)
    media = s.load(make_input(ctx.media / source, transform=transform))
    s.pump(0.8)

    image = s.software_frame() if media is not None else None

    s.close()

    return image


def scenario_software_rotation(ctx):
    """The clip's red bar is down its left side: where it ends up says it all."""

    plain = _software_picture(ctx, "clip.mp4")
    ctx.check("as it is", is_red(plain, 30, 180))

    turned = _software_picture(ctx, "rot90.mp4")
    ctx.check("the file's turn", (turned.width(), turned.height()) == (360, 640))
    ctx.check("red bar along the top", is_red(turned, 180, 30))

    picked = _software_picture(ctx, "clip.mp4", VideoTransform.ROTATE_90)
    ctx.check("the viewer's stays squeezed", picked.width() == 640)
    ctx.check("turned all the same", is_red(picked, 320, 20))

    flipped = _software_picture(ctx, "clip.mp4", VideoTransform.HFLIP)
    ctx.check("a flip", is_red(flipped, 610, 180))

    both = _software_picture(ctx, "rot90.mp4", VideoTransform.VFLIP)
    ctx.check("a flip of a turned picture", is_red(both, 180, 610))


# --- the hardware driver


def scenario_hardware_transforms(ctx):
    s = Session(ctx.out)
    media = s.load(
        make_input(ctx.media / "clip.mp4", paused=False, transform=VideoTransform.HFLIP)
    )
    s.pump(1.0)

    ctx.check("a flip loads", media is not None)
    ctx.check(
        "the filter holds",
        not any("Disabling filter" in line for line in s.lines),
        [line for line in s.lines if "filter" in line][:2],
    )
    ctx.check("is applied", _filters(s) == ["hflip"], _filters(s))
    s.close()

    # a filter runs before mpv turns the picture
    s = Session(ctx.out)
    media = s.load(make_input(ctx.media / "rot90.mp4", transform=VideoTransform.HFLIP))
    s.pump(0.5)
    ctx.check("swapped on a turned picture", _filters(s) == ["vflip"], _filters(s))
    s.close()

    s = Session(ctx.out)
    media_input = make_input(ctx.media / "clip.mp4", transform=VideoTransform.ROTATE_90)
    s.load(media_input)
    s.pump(0.5)
    ctx.check("turned by mpv", s.prop("video-rotate") == 90, s.prop("video-rotate"))
    ctx.check(
        "and not cropped", s.prop("video-crop") == "0x0+0+0", s.prop("video-crop")
    )
    s.close()


def _filters(session):
    return [item.get("name") for item in session.prop("vf") or []]


# --- performance


@contextmanager
def _setting(key, value):
    Settings().set(key, value)

    try:
        yield
    finally:
        Settings().reset(key)


def _is_set_to(session, name, value):
    shown = session.prop(name)

    if isinstance(shown, bool):
        return shown == (value == "yes")

    if isinstance(shown, float):
        # mpv keeps these in single precision
        return math.isclose(shown, float(value), rel_tol=1e-5)

    return str(shown) == value


def scenario_quality_presets(ctx):
    for quality, options in QUALITY_OPTIONS.items():
        with _setting("player/video_quality", quality):
            s = Session(ctx.out)
            media = s.load(make_input(ctx.media / "clip.mp4"))
            s.pump(0.3)

            wrong = {
                name: s.prop(name)
                for name, value in options.items()
                if not _is_set_to(s, name, value)
            }

            ctx.check(f"{quality.value} plays", media is not None)
            ctx.check(f"{quality.value} is what mpv ended up with", not wrong, wrong)
            s.close()


def scenario_automatic_quality(ctx):
    s = Session(ctx.out)
    media_input = make_input(ctx.media / "clip.mp4")
    s.load(media_input)
    s.pump(0.3)
    ctx.check("small is fast", s.prop("scale") == "bilinear", s.prop("scale"))

    s.cmd("adjust_view", (1280, 720), media_input.view)
    s.pump(0.3)
    ctx.check("medium is balanced", s.prop("scale") == "catmull_rom", s.prop("scale"))

    s.cmd("adjust_view", (2560, 1440), media_input.view)
    s.pump(0.3)
    ctx.check("big is high", s.prop("scale") == "lanczos", s.prop("scale"))

    real = player_module.is_falling_behind
    player_module.is_falling_behind = lambda *_args: True

    try:
        s.cmd("on_quality_check")
        s.pump(0.2)
        ctx.check(
            "the first check only starts counting",
            s.prop("scale") == "lanczos",
            s.prop("scale"),
        )

        s.cmd("on_quality_check")
        s.pump(0.2)
        ctx.check(
            "one that can't keep up steps down",
            s.prop("scale") == "catmull_rom",
            s.prop("scale"),
        )
    finally:
        player_module.is_falling_behind = real

    s.cmd("adjust_view", (640, 360), media_input.view)
    s.pump(0.2)
    s.cmd("adjust_view", (2560, 1440), media_input.view)
    s.pump(0.3)
    ctx.check(
        "shown bigger it gets another try",
        s.prop("scale") == "lanczos",
        s.prop("scale"),
    )
    s.close()

    with _setting("player/video_quality", VideoQuality.HIGH):
        s = Session(ctx.out)
        s.load(make_input(ctx.media / "clip.mp4"))
        s.pump(0.3)
        ctx.check(
            "a preset picked holds at any size",
            s.prop("scale") == "lanczos",
            s.prop("scale"),
        )
        s.close()


def scenario_typed_options_win(ctx):
    with _setting("misc/mpv_options", "--hwdec=no"):
        s = Session(ctx.out)
        s.load(make_input(ctx.media / "clip.mp4", paused=False))
        s.pump(0.5)
        ctx.check(
            "hwdec typed stays",
            s.prop("hwdec-current") in {"no", None},
            s.prop("hwdec-current"),
        )
        s.close()

    with (
        _setting("misc/mpv_options", "--profile=fast"),
        _setting("player/video_quality", VideoQuality.HIGH),
    ):
        s = Session(ctx.out)
        s.load(make_input(ctx.media / "clip.mp4"))
        s.pump(0.3)
        ctx.check(
            "a profile typed beats the preset",
            s.prop("scale") == "bilinear",
            s.prop("scale"),
        )
        s.close()

    with (
        _setting("misc/mpv_options", "--scale=spline36"),
        _setting("player/video_quality", VideoQuality.FAST),
    ):
        s = Session(ctx.out)
        s.load(make_input(ctx.media / "clip.mp4"))
        s.pump(0.3)
        ctx.check(
            "an option typed beats that option",
            s.prop("scale") == "spline36",
            s.prop("scale"),
        )
        ctx.check(
            "and the rest of the preset still applies",
            s.prop("dscale") == "bilinear",
            s.prop("dscale"),
        )
        s.close()


def scenario_hardware_decoding_modes(ctx):
    def decoder(mode, is_software=False, **kwargs):
        with _setting("player/hardware_decoding", mode):
            s = Session(ctx.out, is_software=is_software)
            s.load(make_input(ctx.media / "clip.mp4", paused=False, **kwargs))
            s.pump(0.6)
            current = s.prop("hwdec-current")
            s.close()

            return current

    plain = decoder(HardwareDecoding.AUTO)
    ctx.check("auto is on the GPU", plain not in {"no", None}, plain)
    ctx.check("and not copied", "copy" not in str(plain), plain)

    copied = decoder(HardwareDecoding.COPY)
    ctx.check("copied", "copy" in str(copied), copied)

    off = decoder(HardwareDecoding.OFF)
    ctx.check("off", off in {"no", None}, off)

    flipped = decoder(HardwareDecoding.OFF, transform=VideoTransform.HFLIP)
    ctx.check("off stays off for a flip", flipped in {"no", None}, flipped)

    software = decoder(HardwareDecoding.AUTO, is_software=True)
    ctx.check("software's auto is the CPU", software in {"no", None}, software)

    software_copied = decoder(HardwareDecoding.COPY, is_software=True)
    ctx.check(
        "software can be helped by the GPU",
        "copy" in str(software_copied),
        software_copied,
    )


def scenario_graphics_card_choice(ctx):
    adapters = gpu_adapters()

    ctx.check("cards are found", bool(adapters), adapters)

    choices = [
        GpuChoice.AUTO,
        GpuChoice.HIGH_PERFORMANCE,
        GpuChoice.POWER_SAVING,
        *(item.name for item in adapters),
        "A Card Since Taken Out",
    ]

    for choice in choices:
        with _setting("player/gpu_adapter", choice):
            s = Session(ctx.out)
            media = s.load(make_input(ctx.media / "clip.mp4"), timeout=25)
            s.pump(0.3)

            ctx.check(f"plays on {choice or 'auto'!r}", media is not None, s.lines[-3:])
            ctx.check(
                f"draws on {choice or 'auto'!r}",
                s.prop("current-gpu-context") == "d3d11",
                s.prop("current-gpu-context"),
            )
            s.close()


def scenario_keyframe_seeks(ctx):
    s = Session(ctx.out)
    s.load(make_input(ctx.media / "clip.mp4"))
    s.pump(0.3)

    s.cmd("set_time_keyframe", 5400)
    s.pump(0.6)
    landed = s.prop("time-pos")
    ctx.check("lands on a keyframe", abs(landed - round(landed)) < 0.05, landed)

    s.cmd("set_time", 5400)
    s.pump(0.6)
    landed = s.prop("time-pos")
    ctx.check("the exact one lands where asked", abs(landed - 5.4) < 0.05, landed)

    # a drag sends them far faster than frames come
    sent = []
    real_seek = s.player._seek_ms

    def counted(seek_ms, mode="absolute+exact"):
        sent.append(seek_ms)
        real_seek(seek_ms, mode)

    s.player._seek_ms = counted

    for seek_ms in range(1000, 15000, 50):
        s.cmd("set_time_keyframe", seek_ms)

    s.pump(1.0)

    ctx.check("a flood comes down to a few seeks", 0 < len(sent) < 100, len(sent))
    ctx.check(
        "and ends where it was going",
        sent and sent[-1] == 14950,
        sent[-3:],
    )
    landed = s.prop("time-pos")
    ctx.check("the picture got there", abs(landed - 14.95) < 1.1, landed)

    # the exact one at the end of a drag wins over any still waiting
    s.cmd("set_time_keyframe", 3000)
    s.cmd("set_time_keyframe", 9000)
    s.cmd("set_time", 12300)
    s.pump(0.8)
    landed = s.prop("time-pos")
    ctx.check("letting go lands exactly", abs(landed - 12.3) < 0.05, landed)
    s.close()


def scenario_file_lengths(ctx):
    media = ctx.media

    lengths = item_info.lengths_in_process(
        [
            str(media / "clip.mp4"),
            str(media / "tone_220.m4a"),
            str(media / "garbage.mp4"),
            str(media / "nope.mp4"),
        ]
    )

    ctx.check("a video's", lengths[0] and abs(lengths[0] - 20000) < 150, lengths)
    ctx.check("a sound file's", lengths[1] and abs(lengths[1] - 20000) < 150, lengths)
    ctx.check("none for what is no video", lengths[2] is None, lengths)
    ctx.check("none for what is not there", lengths[3] is None, lengths)
