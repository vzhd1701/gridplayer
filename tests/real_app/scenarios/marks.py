"""What marks the seek bar: chapters, bookmarks and SponsorBlock segments."""

from gridplayer.models.sponsor_segment import SponsorSegment

SETTINGS = {
    "sponsorblock/enabled": True,
    "sponsorblock/sponsor": "skip",
    "sponsorblock/intro": "show",
}

SEGMENTS = (
    SponsorSegment(start_ms=2_000, end_ms=5_000, category="intro"),
    SponsorSegment(start_ms=40_000, end_ms=44_000, category="sponsor"),
)


def scenario(d):
    d.open(d.media.feature)
    b = d.wait_for_cell("feature.mkv")

    chapters(d, b)
    bookmarks(d, b)
    sponsorblock(d, b)

    d.note("end", b)


def chapters(d, b):
    d.check(
        "the chapters, named and timed",
        d.menu(b, "menu_generator_chapters")
        == ["Intro\t00:00", "Part One\t00:15", "Part Two\t00:30", "Credits\t00:45"],
    )

    d.act(b, "Next Chapter")
    # the chapter goes by where the seek is arriving, the time once it has
    d.wait_until(
        lambda: b.chapters.playing == 1 and 15_000 <= b.time < 17_500,
        "at the start of Part One",
    )
    d.act(b, "Next Chapter")
    d.wait_until(lambda: b.chapters.playing == 2, "in Part Two")
    d.act(b, "Previous Chapter")
    d.wait_until(lambda: b.chapters.playing == 1, "back in Part One")

    d.choose(b, "menu_generator_chapters", "Credits")
    d.wait_until(lambda: b.chapters.playing == 3, "in the Credits")

    d.choose(b, "menu_generator_chapters", "Part Two")
    d.wait_until(lambda: b.chapters.playing == 2, "in Part Two again")
    d.act(b, "Loop Chapter")
    d.check("the loop is the chapter", (b.loop_start, b.loop_end) == (30_000, 45_000))
    d.act(b, "Loop Reset")


def bookmarks(d, b):
    for at, near in (("10%", 6_000), ("50%", 30_000)):
        d.act(b, at)
        d.wait_until(lambda near=near: abs(b.time - near) < 1_500, f"near {near}ms")
        d.act(b, "Add Bookmark")

    d.check("two bookmarks", len(d.menu(b, "menu_generator_bookmarks")) == 2)

    d.act(b, "0%")
    d.wait_until(lambda: b.time < 2_000, "at the start")
    for action, near in (
        ("Next Bookmark", 6_000),
        ("Next Bookmark", 30_000),
        ("Previous Bookmark", 6_000),
    ):
        d.act(b, action)
        d.wait_until(
            lambda near=near: abs(b.time - near) < 2_500, f"{action} lands near {near}"
        )


def sponsorblock(d, b):
    d.fake_sponsorblock(b, SEGMENTS)
    d.check("both are marked", len(b.sponsorblock.shown_segments) == 2)

    # 2s before the sponsor, then watch it play past
    d.run(b, "active", "manual_seek", "seek", 38_000)
    d.wait_until(lambda: 37_500 <= b.time < 40_000, "2s before the sponsor")
    seen = []
    passed = d.wait_until(
        lambda: seen.append(b.time) or b.time >= 44_000, "past the sponsor", timeout=15
    )
    inside = [t for t in seen if 40_500 <= t <= 43_500]
    d.check("the sponsor is skipped, not played", passed and not inside, seen[-20:])

    # an intro is only marked, and plays through
    d.act(b, "0%")
    d.wait_until(lambda: b.time < 1_500, "back at the start")
    seen.clear()
    d.wait_until(lambda: seen.append(b.time) or b.time >= 5_500, "past the intro")
    inside = [t for t in seen if 2_500 <= t <= 4_500]
    d.check("the intro is played", inside, seen[-20:])
