"""A finished HLS video whose segments are numbered from 1, as some hosts
number them (#145, Vidmoly): played whole, from its start, and not taken for
a live stream. Taken for one, the relay kept the last 16 segments only.

Straight, and through the relay, which a network setting VLC can't be told
of takes it.
"""


def scenario(d):
    base = d.serve(d.media.from_one)

    for playlist in ("finished.m3u8", "vod.m3u8"):
        _played_whole(d, f"{base}/{playlist}", playlist)

    d.change_setting("network/force_ipv4", True)

    for playlist in ("finished.m3u8", "vod.m3u8"):
        _played_whole(d, f"{base}/{playlist}", f"{playlist}, relayed")


def _played_whole(d, url, what):
    d.open(url)
    b = d.wait_for_cell(url, timeout=60)

    d.check(
        f"{what}: all 60 s of it",
        58_000 <= b.video_driver.length <= 62_000,
        b.video_driver.length,
    )
    d.check(f"{what}: from its start", 0 <= b.time <= 4_000, b.time)

    # A slow machine takes a while to fetch the segment the seek lands in.
    # Far enough on that playing there from the start takes longer than
    # the wait: only the seek gets there in time.
    b.seek(40_000)
    d.wait_until(lambda: b.time >= 40_500, f"{what}: on from a seek to 40 s")
    d.check(f"{what}: on from near 40 s", b.time <= 44_000, b.time)

    d.act(b, "Close")
    d.wait_until(lambda: not d.cells, f"{what}: closed")
