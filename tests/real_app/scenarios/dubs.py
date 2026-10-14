"""A stream dubbed into two languages: switching between them, and keeping
the one chosen through a change of size."""

SETTINGS = {
    # Streamlink takes only the default audio of an HLS stream; yt-dlp
    # reads each rendition and its language
    "streaming/resolver_priority": "yt_dlp",
}

NAMES = {"en": "English", "es": "Spanish"}


def scenario(d):
    d.open(f"{d.serve(d.media.dubs)}/master.m3u8")
    dubs = d.wait_for_cell("master.m3u8")

    d.check(
        "both languages",
        set(dubs.stream.audio_language_options) == {"en", "es"},
        dubs.stream.audio_language_options,
    )
    playing = dubs.stream.audio_language_playing
    other = "en" if playing == "es" else "es"
    d.menu(dubs, "menu_generator_audio_track")

    d.choose(dubs, "menu_generator_audio_track", NAMES[other])
    d.wait_until(
        lambda: dubs.stream.audio_language_playing == other and dubs.is_playable,
        f"{NAMES[other]} plays",
    )

    d.choose(dubs, "menu_generator_stream_quality", "180p")
    d.wait_until(
        lambda: dubs.stream.quality_playing.startswith("180p") and dubs.is_playable,
        "180p plays",
    )
    d.check(
        "in the language chosen",
        dubs.stream.audio_language_playing == other,
        dubs.stream.audio_language_playing,
    )

    d.note("end", dubs)
