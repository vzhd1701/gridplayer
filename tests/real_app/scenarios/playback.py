"""Playing a file: pause, seek, the loop, sound, zoom and a screenshot, and
the same commands sent to every cell at once."""


def scenario(d):
    clip, other = d.media.clips[0], d.media.clips[1]
    d.open(clip, other)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")

    d.act(a, "Play / Pause")
    d.wait_until(lambda: a.video_params.is_paused, "a is paused")
    d.check("b plays on", not b.video_params.is_paused)
    d.act(a, "Play / Pause")
    d.wait_until(lambda: not a.video_params.is_paused, "a plays again")

    d.act(a, "50%")
    d.wait_until(lambda: 9_500 <= a.time <= 12_500, "a is halfway")

    d.act(a, "Set Loop Start")
    start = a.loop_start
    d.check("the loop starts where it was set", 9_500 <= start <= 12_500, start)
    d.wait(1)
    d.act(a, "Set Loop End")
    d.check("the loop ends after it starts", a.loop_end > start, a.loop_end)
    d.note("a with a loop", a)
    d.act(a, "Loop Reset")
    d.check("the loop is reset", a.loop_start == 0, (a.loop_start, a.loop_end))

    volume = a.video_params.volume
    d.act(a, "Audio Volume - Decrease")
    d.check("quieter", a.video_params.volume < volume, a.video_params.volume)
    muted = a.video_params.is_muted
    d.act(a, "Audio Volume - Mute / Unmute")
    d.check("mute toggled", a.video_params.is_muted is not muted)
    d.act(a, "Audio Volume - Mute / Unmute")
    d.check("mute toggled back", a.video_params.is_muted is muted)

    d.act(a, "Zoom In")
    d.check("zoomed in", a.video_params.scale > 1, a.video_params.scale)
    d.shot("zoomed")
    d.act(a, "Zoom Reset")
    d.check("zoom reset", a.video_params.scale == 1, a.video_params.scale)

    d.act(a, "Take Screenshot")
    saved = d.out / "screenshots"
    d.wait_until(lambda: any(saved.glob("a_*")), "the screenshot is saved")

    d.run(a, "all", "scale_increase")
    d.check("all zoomed", all(c.video_params.scale > 1 for c in d.cells))
    d.run(a, "all", "scale_reset")
    d.run(a, "all", "set_muted", True)
    d.check("all muted", all(c.video_params.is_muted for c in d.cells))

    d.note("end")
    d.shot("end")
