"""A known bug: with an audio file playing beside the video, choosing a
subtitle track moves the video back to about where the audio file was
added. GridPlayer only asks VLC for the track; VLC does the moving, and
only while it has the audio file as a slave.

Expected to fail (see test_scenarios.py) until it is fixed.
"""


def scenario(d):
    d.open(d.media.feature)
    b = d.wait_for_cell("feature.mkv")

    d.wait(1)
    d.choose(b, "menu_generator_audio_track", "Detect Audio Files")
    d.wait_until(lambda: b.audio.discovered_files, "the commentary is found")
    d.choose(b, "menu_generator_audio_track", "feature.commentary.m4a")
    d.wait_until(lambda: b.video_params.external_audio, "the commentary plays")

    d.wait(4)
    before = b.time
    d.choose(b, "menu_generator_subtitle_track", "French")
    d.wait(1.5)

    # VLC's clock steps back a little on any track change; this is seconds
    d.check("it plays on from where it was", b.time > before - 500, (before, b.time))
