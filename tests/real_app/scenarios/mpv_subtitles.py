"""The subtitles on the mpv driver, through the app's own menus: the file's tracks,
files kept beside a video and a VobSub pair, what's picked coming back after a
reload, delays and character sets, what they look like changing as it plays, and
staying on show and the right way round whatever the view does to the picture.
mpv's own word is what's checked for the text, the picture for the rest. How it all
compares with VLC is in docs/MPV_PLAN.md.
"""

import shutil

from PyQt5.QtCore import QRect
from PyQt5.QtGui import QColor

from gridplayer.models.subtitle_selection import SubtitleExternal, SubtitleTrackId
from gridplayer.params.static import VideoTransform
from tests.real_app.media import _ffmpeg, _pattern
from tests.real_app.scenarios.mpv_transport import _mpv
from tests.real_app.scenarios.mpv_view import (
    _close,
    _corners_clip,
    _corners_of,
    _corners_on_show,
    _open,
    _reference,
    _take_screenshot,
)
from tests.real_app.scenarios.pixel_shape import _grab

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "video_defaults/cell_view_mode": "fit",
    "video_defaults/initial_state": "playing",
}

# what's lit enough to be the line on a black picture
LIT = 300


def scenario(d):
    _the_files_tracks(d)
    _files_beside_it(d)
    _vobsub(d)
    _character_sets(d)
    _tracks_with_nothing_to_name_them(d)
    _style_as_it_plays(d)
    _kept_on_show(d)


def _says(d, b, text):
    # the lines leave half a second between them
    d.wait_until(lambda: str(_mpv(b).sub_text or "").startswith(text), f"{text} shows")


def _reload(d, b):
    b.reload()
    d.wait_until(lambda: not b.is_video_initialized, "it's reloading")
    d.wait_until(lambda: b.is_playable, "it's back")


def _the_files_tracks(d):
    b = _open(d, d.media.feature)

    d.check("nothing shows to begin with", b.subtitles.track_showing == -1)
    d.check("both tracks are listed", len(b.subtitles.tracks) == 2, b.subtitles.tracks)

    d.choose(b, "menu_generator_subtitle_track", "French")
    _says(d, b, "Francais")
    _reload(d, b)
    _says(d, b, "Francais")

    d.choose(b, "menu_generator_subtitle_track", "Off")
    d.wait_until(lambda: not _mpv(b).sub_text, "nothing shows")
    _reload(d, b)
    d.check("still off", b.subtitles.track_showing == -1, b.subtitles.track_showing)

    # the file marks the first
    d.choose(b, "menu_generator_subtitle_track", "Default")
    _says(d, b, "English")
    _reload(d, b)
    _says(d, b, "English")

    b.subtitles.set_languages("fr")
    b.subtitles.apply_preference()
    _says(d, b, "Francais")
    _reload(d, b)
    _says(d, b, "Francais")

    b.subtitles.set_languages("ja")
    d.wait_until(lambda: not _mpv(b).sub_text, "none in the language asked for")

    d.act(b, "Subtitle Delay Later")
    delay = b.video_params.subtitle_delay_ms
    d.wait_until(lambda: _is_delayed(b, delay), "mpv moves them")
    _reload(d, b)
    d.check("and after a reload", _is_delayed(b, delay), _mpv(b).sub_delay)
    d.act(b, "Subtitle Delay Reset")
    d.wait_until(lambda: _mpv(b).sub_delay == 0, "and back")

    _close(d, b)


def _is_delayed(b, delay_ms) -> bool:
    return abs(_mpv(b).sub_delay * 1000 - delay_ms) < 1


def _files_beside_it(d):
    folder = d.out / "beside"
    shutil.copytree(d.media.feature.parent, folder)
    video = folder / d.media.feature.name

    german = folder / "feature.de.srt"
    italian = folder / "feature.it.srt"
    italian.write_text(_srt("Italiano"), encoding="utf-8")

    # told apart by more than the name without its extension
    twin_srt, twin_vtt = folder / "twin.srt", folder / "twin.vtt"
    twin_srt.write_text(_srt("Twin srt"), encoding="utf-8")
    twin_vtt.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nTwin vtt\n", encoding="utf-8"
    )

    b = _open(d, video)

    d.choose(b, "menu_generator_subtitle_track", "Detect Subtitle Files")
    d.wait_until(lambda: b.subtitles.discovered_files, "German is found")

    at = b.time
    d.choose(b, "menu_generator_subtitle_track", "German")
    _says(d, b, "Deutsch")
    d.check("with no reload and no jump", b.time >= at, (at, b.time))
    d.check(
        "it's known by its file",
        list(b.subtitles.external_tracks.values()) == [german],
        b.subtitles.external_tracks,
    )

    _reload(d, b)
    _says(d, b, "Deutsch")

    d.choose(b, "menu_generator_subtitle_track", "French")
    _says(d, b, "Francais")
    b.subtitles.show_external(str(german))
    _says(d, b, "Deutsch")

    b.subtitles.add_external([italian])
    _says(d, b, "Italiano")
    _reload(d, b)
    _says(d, b, "Italiano")
    b.subtitles.show_external(str(german))
    _says(d, b, "Deutsch")

    d.choose(b, "menu_generator_subtitle_track", "Remove External Subtitles")
    d.wait_until(lambda: not b.video_params.external_subtitles, "they're let go of")
    d.wait_until(lambda: b.is_playable, "it plays on after the reload")
    d.check("back to its own two", len(b.subtitles.tracks) == 2, b.subtitles.tracks)

    b.subtitles.add_external([twin_srt, twin_vtt])
    d.wait_until(lambda: len(b.subtitles.external_tracks) == 2, "both on")
    b.subtitles.show_external(str(twin_vtt))
    _says(d, b, "Twin vtt")
    _reload(d, b)
    _says(d, b, "Twin vtt")
    b.subtitles.remove_external()
    d.wait_until(lambda: b.is_playable, "they're gone")

    # the video plays on as it was
    broken = folder / "broken.srt"
    broken.write_bytes(b"\x00\x01\x02 nothing anyone could read")
    b.subtitles.add_external([broken])
    d.wait(1)
    d.check("a file with no subtitles in it", not b.subtitles.external_track_ids)
    d.check("it still plays", b.is_playable)
    _reload(d, b)
    d.check("nor does it stop a load", b.is_playable)

    _close(d, b)


def _srt(text):
    return f"1\n00:00:00,000 --> 00:01:00,000\n{text}\n"


def _vobsub(d):
    folder = d.out / "vobsub"
    folder.mkdir()

    video = _black_clip(d, folder / "dvd.mkv", "640x360")
    index = folder / "dvd.idx"
    _write_vobsub(index, ("en", "de"))

    b = _open(d, video)

    b.subtitles.add_external([index])
    d.wait_until(lambda: len(b.subtitles.external_track_ids) == 2, "its two tracks")
    d.wait_until(lambda: _lit(b) > 0, "its first shows")

    _, second = b.subtitles.external_track_ids

    b.subtitles.set_track(second)
    selection = b.video_params.subtitle_selection
    d.check(
        "the second of the file is what's remembered",
        selection == SubtitleExternal(file=index, track=1),
        selection,
    )

    _reload(d, b)
    d.check("and picked again", _mpv(b).sid == second, _mpv(b).sid)
    # told only when it's opened with the video: mpv forgets it for a file added later
    d.check("it says what it is", b.subtitles.external_track_name(second) == "German")
    d.wait_until(lambda: _lit(b) > 0, "and shown")

    _close(d, b)


def _character_sets(d):
    folder = d.out / "sets"
    folder.mkdir()

    video = _black_clip(d, folder / "text.mkv", "320x180")

    for name, codec, encoding, text in (
        ("cyrillic.srt", "cp1251", "Windows-1251", "Привет"),
        ("japanese.srt", "iso2022_jp_2", "ISO-2022-JP-2", "こんにちは"),
    ):
        file = folder / name
        file.write_bytes(_srt(text).encode(codec))

        _in_character_set(d, video, file, encoding, text)


def _in_character_set(d, video, file, encoding, text):
    b = _open(d, video)

    b.subtitles.add_external([file])
    d.wait_until(lambda: b.subtitles.external_track_ids, f"{file.name} is on")
    b.subtitles.set_encoding(encoding)
    d.wait_until(
        lambda: b.is_playable and encoding in _mpv(b).sub_codepage, "read again"
    )
    _says(d, b, text)

    _close(d, b)


def _tracks_with_nothing_to_name_them(d):
    folder = d.out / "unnamed"
    folder.mkdir()

    for number in (1, 2):
        (folder / f"{number}.srt").write_text(_srt(f"Track {number}"), encoding="utf-8")

    _ffmpeg(
        *_pattern(60, "320x180", "color"),
        "-i", "1.srt", "-i", "2.srt", "-map", "0:v", "-map", "1", "-map", "2",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:s", "srt", "plain.mkv",
        cwd=folder,
    )  # fmt: skip

    b = _open(d, folder / "plain.mkv")

    second = list(b.subtitles.tracks)[1]
    b.subtitles.set_track(second)
    _says(d, b, "Track 2")

    selection = b.video_params.subtitle_selection
    d.check(
        "it's where it comes that's kept",
        isinstance(selection, SubtitleTrackId) and selection.position == 1,
        selection,
    )

    _reload(d, b)
    _says(d, b, "Track 2")

    # what a playlist saved on VLC has, which counts every kind of track together
    b.video_params.subtitle_selection = SubtitleTrackId(id=4, position=1)
    _reload(d, b)
    _says(d, b, "Track 2")

    _close(d, b)


def _showing_the_line(d, size):
    folder = d.out / f"line_{size}"
    folder.mkdir(exist_ok=True)

    b = _open(d, _black_clip(d, folder / "line.mkv", size, "A line of text"))
    b.subtitles.set_track(next(iter(b.subtitles.tracks)))
    d.wait_until(lambda: _lit(b) > 0, "the line shows")

    return b


def _style_as_it_plays(d):
    b = _showing_the_line(d, "640x360")
    mpv_before = _mpv(b)

    d.change_setting("subtitles/color", "#ff0000")
    d.wait_until(lambda: _is_line(b, QColor("#ff0000")), "it turns red")
    d.check("with no reload", _mpv(b) is mpv_before)

    d.change_setting("subtitles/color", "#ffffff")
    d.wait_until(lambda: _is_line(b, QColor("#ffffff")), "and back")

    small = _lit(b)
    d.change_setting("subtitles/size_scale", 200)
    d.wait_until(lambda: _lit(b) > small * 2, "bigger")
    d.change_setting("subtitles/size_scale", 100)

    d.check("still with no reload", _mpv(b) is mpv_before)

    _close(d, b)


def _kept_on_show(d):
    b = _showing_the_line(d, "640x360")

    d.player.resize(1200, 300)
    d.act(b, "View Mode Fill")
    d.wait_until(lambda: _lit(b) > 0, "in a wide cell, Fill cutting off the bottom")

    # the frame's source goes by a shape the frame isn't in once turned
    b.set_transform(VideoTransform.ROTATE_90)
    d.wait_until(lambda: b.is_playable and _lit(b) > 0, "turned, and much more cut off")
    b.set_transform(VideoTransform.NONE)
    d.wait_until(lambda: b.is_playable and _lit(b) > 0, "and back")

    d.act(b, "View Mode Fit")
    d.player.resize(960, 540)
    d.wait(0.5)

    # it's only the frame's size that waits for a zoom to be over
    settle = b.video_driver._settle_timer
    settle_ms = settle.interval()
    settle.setInterval(60_000)

    for _ in range(4):
        d.act(b, "Zoom In")

    d.wait_until(lambda: _mpv(b).sub_scale < 1, "they keep up as it zooms")
    # past what it takes, mpv would refuse it and leave the line as wide as the picture
    d.wait_until(lambda: _mpv(b).sub_margin_x > 25, "kept to what's on show")
    settle.setInterval(settle_ms)
    settle.start()

    d.wait_until(lambda: _lit(b) > 0, "zoomed in")
    d.act(b, "Zoom Reset")

    _close(d, b)

    # a flip is of the picture, and the picture here is black
    b = _showing_the_line(d, "640x360")
    d.wait(0.5)
    plain = _grab(b)

    b.set_transform(VideoTransform.HFLIP)
    d.wait_until(lambda: b.is_playable and _lit(b) > 0, "flipped")
    d.wait(0.5)
    difference, lit = _difference(plain, _grab(b)), _lit(b)
    d.check("the line isn't", difference < lit / 20, (difference, lit))

    _close(d, b)

    _flips_with_a_line(d)

    # a small picture drawn big, to keep the text sharp only while there is some
    b = _showing_the_line(d, "160x90")
    surface = b.video_driver.video_surface
    d.wait_until(lambda: surface.frame_size()[0] > 160, "as big as the cell")

    d.choose(b, "menu_generator_subtitle_track", "Off")
    d.wait_until(lambda: surface.frame_size()[0] == 160, "only as big as it is")

    _close(d, b)


def _flips_with_a_line(d):
    """Whether mpv flips the picture or it's painted flipped, it comes out the same."""

    line = d.out / "corners_line.srt"
    line.write_text(_srt("A line"), encoding="utf-8")

    for file_turn in (VideoTransform.NONE, VideoTransform.ROTATE_90):
        b = _open(d, _corners_clip(d, file_turn))
        b.subtitles.add_external([line])
        d.wait_until(lambda b=b: b.subtitles.external_track_ids, "the line is on")

        for transform in (VideoTransform.HFLIP, VideoTransform.TRANSPOSE):
            what = f"file {file_turn.name}, {transform.name}"
            expected = _reference(transform, file_turn)

            b.set_transform(transform)
            d.wait_until(
                lambda b=b, t=transform: (
                    b.is_playable and b.video_params.transform == t
                ),
                f"{what} is on",
            )
            surface = b.video_driver.video_surface

            d.wait_until(lambda s=surface: s._is_flip_in_mpv, f"{what}: mpv flips it")
            d.wait_until(
                lambda b=b, e=expected: _corners_on_show(b) == e,
                f"{what}: with the line, as it should be",
            )

            image = _take_screenshot(d, b)
            whole = QRect(0, 0, image.width(), image.height())
            d.check(
                f"{what}: and the screenshot",
                _corners_of(image, whole) == expected,
                (_corners_of(image, whole), expected),
            )

            d.choose(b, "menu_generator_subtitle_track", "Off")
            d.wait_until(lambda s=surface: not s._is_flip_in_mpv, f"{what}: painted")
            d.wait_until(
                lambda b=b, e=expected: _corners_on_show(b) == e,
                f"{what}: with none, as it should be",
            )

            b.subtitles.show_external(str(line))
            d.wait_until(lambda s=surface: s._is_flip_in_mpv, f"{what}: mpv again")

        _close(d, b)


def _black_clip(d, path, size, line="A line"):
    srt = path.with_suffix(".line.srt")
    srt.write_text(_srt(line), encoding="utf-8")

    _ffmpeg(
        *_pattern(60, size, "color"),
        "-i", srt.name, "-map", "0:v", "-map", "1", "-c:v", "libx264",
        "-preset", "ultrafast", "-c:s", "srt", "-metadata:s:s:0", "language=eng",
        path.name, cwd=path.parent,
    )  # fmt: skip

    srt.unlink()

    return path


def _every_other_pixel(image):
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            yield x, y


def _lit(b) -> int:
    image = _grab(b)

    return sum(
        1
        for x, y in _every_other_pixel(image)
        if _brightness(image.pixelColor(x, y)) > LIT
    )


def _brightness(color) -> int:
    return color.red() + color.green() + color.blue()


def _is_line(b, color) -> bool:
    """Whether the brightest of what's on show is this colour."""

    image = _grab(b)
    brightest = max(
        (image.pixelColor(x, y) for x, y in _every_other_pixel(image)),
        key=_brightness,
    )

    return (
        abs(brightest.red() - color.red()) < 50
        and abs(brightest.green() - color.green()) < 50
        and abs(brightest.blue() - color.blue()) < 50
    )


def _difference(one, other) -> int:
    return sum(
        1
        for x, y in _every_other_pixel(one)
        if abs(_brightness(one.pixelColor(x, y)) - _brightness(other.pixelColor(x, y)))
        > LIT
    )


# -- a VobSub pair, by hand: ffmpeg can't make pictures out of text

_SECTOR = 2048
_PALETTE = ", ".join(["000000", "ffffff"] + ["808080"] * 14)
_BOX_AT, _BOX_W, _BOX_H = 100, 256, 32
_SHOWN_S = 60


def _picture_packet() -> bytes:
    """A white box for a minute: every line one run to its end, in colour 1."""

    lines = b"\x00\x01" * (_BOX_H // 2)
    picture_at = 4
    control_at = picture_at + len(lines) * 2
    right, bottom = _BOX_AT + _BOX_W - 1, _BOX_AT + _BOX_H - 1

    def span(first, last):
        return bytes((first >> 4, (first & 15) << 4 | last >> 8, last & 255))

    start = (
        b"\x01"  # show
        b"\x03\x11\x11"  # every colour is the palette's white
        b"\x04\xff\xff"  # all of it opaque
         b"\x05" + span(_BOX_AT, right) + span(_BOX_AT, bottom)
        + b"\x06" + picture_at.to_bytes(2, "big")
        + (picture_at + len(lines)).to_bytes(2, "big")
        + b"\xff"
    )  # fmt: skip

    stop_at = control_at + 4 + len(start)
    delay = int(_SHOWN_S * 90000 / 1024)

    body = (
        lines * 2
        + b"\x00\x00" + stop_at.to_bytes(2, "big") + start
        + delay.to_bytes(2, "big") + stop_at.to_bytes(2, "big") + b"\x02\xff"
    )  # fmt: skip

    return (picture_at + len(body)).to_bytes(2, "big") + control_at.to_bytes(2, "big") + body  # fmt: skip


def _sector(stream: int) -> bytes:
    """One packet of MPEG-PS, at time 0, padded to the size they come in."""

    pack = b"\x00\x00\x01\xba\x44\x00\x04\x00\x04\x01\x00\x00\x03\xf8"
    time_zero = b"\x21\x00\x01\x00\x01"

    payload = b"\x80\x80\x05" + time_zero + bytes((0x20 + stream,)) + _picture_packet()
    packet = pack + b"\x00\x00\x01\xbd" + len(payload).to_bytes(2, "big") + payload

    padding = _SECTOR - len(packet) - 6

    return packet + b"\x00\x00\x01\xbe" + padding.to_bytes(2, "big") + b"\xff" * padding


def _write_vobsub(index, languages) -> None:
    lines = ["# VobSub index file, v7", "size: 720x480", f"palette: {_PALETTE}", ""]
    pictures = b""

    for stream, language in enumerate(languages):
        lines += [
            f"id: {language}, index: {stream}",
            f"timestamp: 00:00:00:000, filepos: {len(pictures):09x}",
            "",
        ]
        pictures += _sector(stream)

    index.write_text("\n".join(lines), encoding="ascii")
    index.with_suffix(".sub").write_bytes(pictures)
