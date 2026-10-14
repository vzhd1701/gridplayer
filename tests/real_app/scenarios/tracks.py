"""Audio and subtitle tracks: the file's own, files found beside it, and
their delays."""


def scenario(d):
    d.open(d.media.feature)
    b = d.wait_for_cell("feature.mkv")

    def audio_language():
        return b.audio.tracks[b.audio.track_playing].language

    def subtitle_language():
        return b.subtitles.tracks[b.subtitles.track_showing].language

    # audio

    d.menu(b, "menu_generator_audio_track")
    d.choose(b, "menu_generator_audio_track", "Spanish")
    d.wait_until(lambda: audio_language() == "spa", "Spanish plays")

    d.choose(b, "menu_generator_audio_track", "Detect Audio Files")
    d.wait_until(lambda: b.audio.discovered_files, "the commentary is found")
    # Attached within a moment of the switch above, under load VLC now and
    # then never plays it; nobody clicks that fast
    d.wait(1)
    d.choose(b, "menu_generator_audio_track", "feature.commentary.m4a")
    d.wait_until(
        lambda: b.video_params.external_audio and b.audio.track_playing not in (1, 2),
        "the commentary plays",
    )

    d.act(b, "Audio Delay Later")
    d.check("audio later", b.video_params.audio_delay_ms > 0)
    d.act(b, "Audio Delay Reset")
    d.check("audio on time", b.video_params.audio_delay_ms == 0)

    d.choose(b, "menu_generator_audio_track", "English")
    d.wait_until(lambda: audio_language() == "eng", "English plays")
    # it moves the video on a track change; see external_audio_jump
    at = b.time
    d.choose(b, "menu_generator_audio_track", "Remove External Audio")
    d.wait_until(lambda: not b.video_params.external_audio, "the commentary is gone")
    # which takes a reload, back to where it was
    d.wait_until(lambda: b.is_playable and b.time >= at, "it plays on after the reload")

    # subtitles

    d.wait(3)
    before = b.time
    d.choose(b, "menu_generator_subtitle_track", "French")
    d.wait_until(lambda: subtitle_language() == "fre", "French shows")
    # VLC's clock steps back a little on a track change
    d.check("it plays on from where it was", b.time > before - 500, (before, b.time))

    d.act(b, "Subtitle Delay Later")
    d.check("subtitles later", b.video_params.subtitle_delay_ms > 0)
    d.act(b, "Subtitle Delay Reset")
    d.check("subtitles on time", b.video_params.subtitle_delay_ms == 0)

    d.choose(b, "menu_generator_subtitle_track", "Detect Subtitle Files")
    d.wait_until(lambda: b.subtitles.discovered_files, "German is found")
    d.choose(b, "menu_generator_subtitle_track", "German")
    d.wait_until(
        lambda: b.subtitles.track_showing not in (-1, 3, 4), "the German file shows"
    )
    d.wait(1)
    d.shot("german_subtitles")

    d.choose(b, "menu_generator_subtitle_track", "Off")
    d.wait_until(lambda: b.subtitles.track_showing == -1, "no subtitles")
    d.choose(b, "menu_generator_subtitle_track", "Remove External Subtitles")
    # found beside it still, and offered again, but no longer attached
    d.wait_until(lambda: not b.video_params.external_subtitles, "German is detached")

    d.note("end", b)
