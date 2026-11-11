"""The sound on the mpv driver, through the app's own menus: tracks and files
kept beside a video, what's picked coming back after a reload, ways out of the
machine, channel modes and the delay, songs with no picture, and switching the
picture off. mpv's own word is what's checked. What comes out of a speaker is
compared with VLC in docs/MPV_PLAN.md.

Everything here stays muted: nothing is to come out of the machine it runs on.
"""

import shutil

from gridplayer.models.audio_selection import AudioDisabled, AudioExternal
from gridplayer.mpv_player import player as player_module
from gridplayer.params.static import AudioChannelMode
from tests.real_app.media import _ffmpeg, _pattern, _tone
from tests.real_app.scenarios.mpv_transport import _mpv
from tests.real_app.scenarios.mpv_view import _open
from tests.real_app.scenarios.pixel_shape import _grab, _picture_box

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "video_defaults/cell_view_mode": "fit",
    "video_defaults/initial_state": "playing",
}


def scenario(d):
    _tracks_and_files(d)
    _going_round(d)
    _ways_out(d)
    _channel_modes_and_delay(d)
    _one_channel_and_surround(d)
    _no_picture(d)
    _picture_off_and_on(d)
    _longer_file(d)
    _odd_files(d)


def _audio_language(block):
    return block.audio.tracks[block.audio.track_playing].language


def _close(d, block):
    d.act(block, "Close")
    d.wait_until(lambda: not d.cells, "the cell is closed")


def _loaded(d, block, what):
    d.wait_until(lambda: block.is_video_initialized, what)


def _reload(d, block, what="loaded again"):
    block.reload()
    _loaded(d, block, what)


def _moving(block):
    start = block.time

    return lambda: block.time != start


def _has_filter(block, part) -> bool:
    filters = _mpv(block).af

    if part is None:
        return not filters

    return bool(filters) and part in str(filters)


def _sounding(block):
    """The chain was made again and something is going out."""

    return lambda: _mpv(block).audio_out_params and block.time > 0


def _tracks_and_files(d):
    b = _open(d, d.media.feature)

    d.check("two tracks", len(b.audio.tracks) == 2, b.audio.tracks)
    d.check("the file's first track", _audio_language(b) == "eng")
    d.check("muted", _mpv(b).mute is True)

    d.choose(b, "menu_generator_audio_track", "Spanish")
    d.wait_until(lambda: _mpv(b).aid == 2, "mpv plays the Spanish track")
    d.check("said to play Spanish", _audio_language(b) == "spa")

    _reload(d, b)
    d.wait_until(lambda: _mpv(b).aid == 2, "Spanish after a reload")
    d.check("said after a reload", _audio_language(b) == "spa")

    d.choose(b, "menu_generator_audio_track", "Disable Audio")
    d.wait_until(lambda: _mpv(b).aid is False, "no sound track")
    d.check("said to be off", isinstance(b.video_params.audio_selection, AudioDisabled))
    d.wait_until(_moving(b), "the video plays on")

    _reload(d, b, "loaded off")
    d.check("off after a reload", _mpv(b).aid is False, _mpv(b).aid)

    d.choose(b, "menu_generator_audio_track", "English")
    d.wait_until(lambda: _mpv(b).aid == 1, "English again")

    # a file: found, played where the video stands, its track told apart
    d.choose(b, "menu_generator_audio_track", "Detect Audio Files")
    d.wait_until(lambda: b.audio.discovered_files, "the commentary is found")

    mpv_before = _mpv(b)
    d.choose(b, "menu_generator_audio_track", "feature.commentary.m4a")
    d.wait_until(lambda: b.audio.external_track_ids, "the file brought its track")

    file_track = b.audio.external_track_ids[0]

    d.wait_until(lambda: _mpv(b).aid == file_track, "mpv plays the file")
    d.check("said to play the file", b.audio.track_playing == file_track)
    d.check(
        "the file is the choice",
        isinstance(b.video_params.audio_selection, AudioExternal),
    )
    d.check("no reload for it", _mpv(b) is mpv_before)

    # it stays on through a reload, and the delay goes with it
    d.act(b, "Audio Delay Later")
    d.wait_until(lambda: _mpv(b).audio_delay > 0, "mpv has the delay")

    _reload(d, b, "loaded with it")
    d.check("the file is back", len(b.audio.external_track_ids) == 1)
    d.wait_until(
        lambda: _mpv(b).aid == b.audio.external_track_ids[0], "it plays the file"
    )
    d.wait_until(lambda: _mpv(b).audio_delay > 0, "the delay is back")
    d.act(b, "Audio Delay Reset")
    d.wait_until(lambda: _mpv(b).audio_delay == 0, "on time again")

    # back to its own and out again
    d.choose(b, "menu_generator_audio_track", "English")
    d.wait_until(lambda: _mpv(b).aid == 1, "its own track")

    d.choose(b, "menu_generator_audio_track", "Remove External Audio")
    d.wait_until(lambda: not b.video_params.external_audio, "the file is let go")
    _loaded(d, b, "loaded without it")
    d.wait_until(lambda: not b.audio.external_track_ids, "no track from a file")
    d.wait_until(lambda: len(b.audio.tracks) == 2, "its two tracks")

    _close(d, b)


def _going_round(d):
    """Round the end of the file, the track picked stays."""

    b = _open(d, d.media.feature)

    d.choose(b, "menu_generator_audio_track", "Spanish")
    d.wait_until(lambda: _mpv(b).aid == 2, "mpv plays the Spanish track")

    b.seek(59000)
    d.wait_until(lambda: b.time < 5000 and b.time > 0, "it goes round")
    d.check("still Spanish", _mpv(b).aid == 2, _mpv(b).aid)

    _close(d, b)


def _ways_out(d):
    b = _open(d, d.media.clips[0])

    devices = b.audio.devices

    d.note(f"ways out: {[(one.id, one.name) for one in devices]}")

    if not devices:
        d.note("no way out on this machine to choose from")
        _close(d, b)
        return

    last = devices[-1]

    b.audio.set_device(last)
    d.wait_until(lambda: _mpv(b).audio_device == last.id, "mpv goes that way")

    _reload(d, b)
    d.wait_until(lambda: _mpv(b).audio_device == last.id, "the same way after a reload")

    b.audio.set_device(None)
    d.wait_until(lambda: _mpv(b).audio_device == "auto", "the machine's own again")

    _reload(d, b)
    d.check("left alone", _mpv(b).audio_device == "auto", _mpv(b).audio_device)

    # moved about while it's seeking: told in the middle of starting the sound, mpv
    # can stop at the load, see MpvPlayer._on_preloaded
    for index in range(8):
        b.seek(1000 + index * 1000)
        b.audio.set_device(devices[index % len(devices)])
        d.wait(0.05)

    b.audio.set_device(None)
    b.seek(1000)
    d.wait_until(lambda: b.time >= 1000 and b.time < 3000, "it lands")
    d.wait_until(_moving(b), "it plays on")

    _close(d, b)


def _channel_modes_and_delay(d):
    b = _open(d, d.media.clips[1])

    for mode, in_filter in (
        (AudioChannelMode.RSTEREO, "c0=c1|c1=c0"),
        (AudioChannelMode.LEFT, "c0=c0|c1=c0"),
        (AudioChannelMode.RIGHT, "c0=c1|c1=c1"),
        (AudioChannelMode.STEREO, None),
        (AudioChannelMode.DOLBYS, None),
        (AudioChannelMode.HEADPHONES, None),
        (AudioChannelMode.MONO, "c0=0.5*c0"),
    ):
        b.audio.set_channel_mode(mode)
        d.wait_until(
            lambda in_filter=in_filter: _has_filter(b, in_filter),
            f"{mode.name} has its filter",
        )
        d.wait_until(_sounding(b), f"{mode.name} plays")

    b.audio.set_channel_mode(AudioChannelMode.RIGHT)
    d.wait_until(lambda: _has_filter(b, "c0=c1|c1=c1"), "picked once more")

    _reload(d, b)
    d.wait_until(lambda: _has_filter(b, "c0=c1|c1=c1"), "the mode after a reload")
    d.wait_until(_sounding(b), "plays after a reload")

    b.audio.set_channel_mode(AudioChannelMode.UNSET)
    d.wait_until(lambda: _has_filter(b, None), "no filter left")
    # this clip's track has one channel, which goes out on two whatever the mode
    d.check("still two", _mpv(b).audio_channels == "stereo", _mpv(b).audio_channels)

    b.audio.set_delay(1200)
    d.wait_until(lambda: abs(_mpv(b).audio_delay - 1.2) < 0.001, "the sound is late")

    b.audio.set_delay(-300)
    d.wait_until(lambda: abs(_mpv(b).audio_delay + 0.3) < 0.001, "the sound is early")

    _reload(d, b)
    d.wait_until(lambda: abs(_mpv(b).audio_delay + 0.3) < 0.001, "the same after that")

    b.audio.set_delay(0)
    d.wait_until(lambda: _mpv(b).audio_delay == 0, "on time")

    b.audio.set_volume(0.5)
    d.wait_until(lambda: _mpv(b).volume == 50, "half way up")
    b.audio.set_volume(1.0)

    _close(d, b)


def _one_channel_and_surround(d):
    """What a track has to go by: how many channels it has."""

    _ffmpeg(
        *_pattern(20),
        *_tone(500, 20),
        *_tone(700, 20),
        "-filter_complex",
        "[2]pan=5.1|c0=c0|c1=c0|c2=c0|c3=c0|c4=c0|c5=c0[surround]",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-map",
        "[surround]",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "flac",
        "both.mkv",
        cwd=d.out,
    )

    b = _open(d, d.out / "both.mkv")

    def raised():
        return "rematrix_volume" in str(_mpv(b).audio_swresample_o)

    d.wait_until(raised, "one channel keeps its level")

    b.audio.set_track(2)
    d.wait_until(lambda: _mpv(b).aid == 2, "the surround track")
    d.wait_until(lambda: not raised(), "not raised")
    d.wait_until(_sounding(b), "it plays")

    b.audio.set_channel_mode(AudioChannelMode.HEADPHONES)
    d.wait_until(lambda: _mpv(b).audio_channels == "stereo", "goes out on two")

    room_file = player_module._room_file()

    d.note(f"the file for the room effect: {room_file}")

    def has_the_mix():
        # a libmpv without the filter, as Homebrew's, gives way to the plain mix
        if player_module._ROOM_FILTER_BROKE.is_set():
            return _has_filter(b, None)

        return _has_filter(b, "sofalizer" if room_file else None)

    d.wait_until(has_the_mix, "the mix")
    if room_file and player_module._ROOM_FILTER_BROKE.is_set():
        d.note("this libmpv has no room filter: the plain mix")
        room_file = None
    d.wait_until(_moving(b), "it plays on")

    if room_file:
        d.wait_until(
            lambda: (
                _mpv(b).audio_out_params
                and _mpv(b).audio_out_params["channel-count"] == 2
            ),
            "the room effect plays",
        )

    # it can't be told beforehand that the filter won't start
    player_module._room_file = lambda: "nothing here.sofa"
    b.audio.set_channel_mode(AudioChannelMode.STEREO)
    d.wait_until(lambda: _has_filter(b, None), "the plain mix")
    b.audio.set_channel_mode(AudioChannelMode.HEADPHONES)

    broke = player_module._ROOM_FILTER_BROKE

    d.wait_until(broke.is_set, "the filter wouldn't start")
    d.wait_until(lambda: _has_filter(b, None), "the plain mix again")
    d.wait_until(lambda: _mpv(b).audio_out_params, "sound again")
    d.wait_until(_moving(b), "it plays on")

    broke.clear()
    player_module._room_file = lambda: room_file

    b.audio.set_channel_mode(AudioChannelMode.UNSET)
    d.wait_until(lambda: _mpv(b).audio_channels == "auto-safe", "back to the default")

    # told at load the same way, the track being known by then
    b.audio.set_track(1)
    d.wait_until(raised, "raised again")

    _reload(d, b)
    d.wait_until(lambda: _mpv(b).aid == 1 and raised(), "after a reload")

    _close(d, b)


def _no_picture(d):
    b = _open(d, d.media.feature.with_name("feature.commentary.m4a"))

    d.check("no picture to show", b.video_driver.media.is_audio_only)
    d.check("the placeholder", b.video_driver.audio_only_placeholder.isVisible())
    d.wait_until(_moving(b), "it plays")
    d.check("nothing to render", _mpv(b).vid in (False, None, "no"), _mpv(b).vid)

    d.act(b, "Play / Pause")
    d.wait_until(lambda: b.video_params.is_paused, "paused")

    b.seek(4000)
    d.wait_until(lambda: abs(b.time - 4000) < 500, "seeks")

    # saved with its sound off, it has nothing else to play
    d.act(b, "Play / Pause")
    d.wait_until(lambda: not b.video_params.is_paused, "playing")
    b.video_params.audio_selection = AudioDisabled()

    _reload(d, b, "loaded with its sound off")
    d.check("no error", not b.status.last_error, b.status.last_error)
    d.wait_until(_moving(b), "it plays all the same")

    _close(d, b)


def _picture_off_and_on(d):
    b = _open(d, d.media.clips[2])

    d.choose(b, "menu_generator_video_track", "Disable Video")
    d.wait_until(lambda: _mpv(b).vid is False, "mpv draws nothing")
    d.check("the placeholder is up", b.video_driver.audio_only_placeholder.isVisible())
    d.wait_until(_moving(b), "it plays on")
    d.shot("picture_off")

    _reload(d, b, "loaded off")
    d.check("off after a reload", b.video_driver.media.is_audio_only)
    d.check(
        "the placeholder is back", b.video_driver.audio_only_placeholder.isVisible()
    )

    b.set_video_track(1)
    d.wait_until(lambda: _mpv(b).vid == 1, "mpv draws again")
    d.wait_until(
        lambda: b.video_driver.video_surface.frame_size()[0] > 0, "there is a frame"
    )
    d.check(
        "the placeholder is gone", not b.video_driver.audio_only_placeholder.isVisible()
    )
    d.wait_until(lambda: _grab(b) is not None, "the picture is back")
    d.shot("picture_on")

    # paused, it has to come back too
    b.set_video_track(-1)
    d.wait_until(lambda: _mpv(b).vid is False, "mpv draws nothing")
    d.act(b, "Play / Pause")
    d.wait_until(lambda: b.video_params.is_paused, "paused")
    b.set_video_track(1)
    d.wait_until(lambda: _mpv(b).vid == 1, "mpv draws again")
    d.wait_until(lambda: _picture_box(_grab(b)) is not None, "the picture, paused")
    d.shot("picture_on_paused")

    # the player in the tray does this
    d.act(b, "Play / Pause")
    d.wait_until(lambda: not b.video_params.is_paused, "playing")
    b.set_video_decoding_stopped(True)
    d.wait_until(lambda: _mpv(b).vid is False, "nothing decoded in the tray")
    d.check("still its own track", b.video_params.video_track_id == 1)
    b.set_video_decoding_stopped(False)
    d.wait_until(lambda: _mpv(b).vid == 1, "back from the tray")

    # nothing left to play: not allowed
    d.choose(b, "menu_generator_audio_track", "Disable Audio")
    d.wait_until(lambda: _mpv(b).aid is False, "no sound track")
    b.video_driver.video_driver.set_video_track(-1)
    d.wait(0.5)
    d.check("the picture stays", _mpv(b).vid == 1, _mpv(b).vid)

    _close(d, b)


def _keeps_to_the_video(d, block, when):
    """It's the video's length that counts: round it goes at the end of that."""

    length = block.video_driver.length

    d.check(f"the length stays the video's, {when}", abs(length - 4000) < 300, length)

    latest = 0

    def went_round():
        nonlocal latest
        latest = max(latest, block.time)
        return latest > 2500 and block.time < 1500

    d.wait_until(went_round, f"it goes back to the start, {when}", timeout=15)
    d.check(f"not past its end, {when}", latest < 4600, latest)


def _longer_file(d):
    """A file that outlasts the video."""

    _ffmpeg(*_pattern(4), "short.mp4", cwd=d.out)
    _ffmpeg(*_tone(500, 20), "short.sound.m4a", cwd=d.out)

    b = _open(d, d.out / "short.mp4")

    b.audio.add_external([d.out / "short.sound.m4a"])
    d.wait_until(lambda: b.audio.external_track_ids, "the long file is on")
    _keeps_to_the_video(d, b, "added")

    _reload(d, b, "loaded with it")
    _keeps_to_the_video(d, b, "opened with it")

    _close(d, b)


def _odd_files(d):
    """A name a URI has to spell out, and a file mpv can't read."""

    folder = d.out / "кино #1 [x]"
    folder.mkdir(exist_ok=True)

    video = folder / "фильм 100%.mp4"
    shutil.copy(d.media.clips[0], video)

    sound = folder / "фильм 100%.звук #2;a%20b.m4a"
    shutil.copy(d.media.feature.with_name("feature.commentary.m4a"), sound)

    # mpv can't read it, and the video plays on as it was
    broken = folder / "broken.m4a"
    broken.write_bytes(b"not sound at all")

    b = _open(d, video)

    mpv_before = _mpv(b)
    b.audio.add_external([broken])
    d.wait(1)
    d.check("no reload for it", _mpv(b) is mpv_before)
    d.check("no track from it", not b.audio.external_track_ids, b.audio.tracks)
    d.wait_until(_moving(b), "plays on")

    _close(d, b)

    b = _open(d, video)

    b.audio.add_external([sound])
    d.wait_until(lambda: b.audio.external_track_ids, "the file opens, added")

    _reload(d, b, "loaded with it")
    d.check("the file opens, at load", len(b.audio.external_track_ids) == 1)

    # swapped for it, it's loaded again without a file to go by
    b.audio.play_external(str(broken))
    _loaded(d, b, "plays without")
    d.wait(1)
    d.check("no track from it", not b.audio.external_track_ids, b.audio.tracks)
    d.check("no error", not b.status.last_error, b.status.last_error)
    d.wait_until(_moving(b), "plays on")

    _close(d, b)
