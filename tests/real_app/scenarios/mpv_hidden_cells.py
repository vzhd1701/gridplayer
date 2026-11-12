"""Cells out of sight on the MPV driver, as Single Mode leaves them when background
videos aren't paused: they play on at their own pace with their frames not drawn,
and on show again their picture is the one they're at, at once. One paused and
moved meanwhile shows where it was moved to. The same for every cell with the window
minimized or in the tray."""

import collections
import time

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "playlist/pause_background_videos": False,
    "playlist/pause_minimized": False,
    "player/tray_stop_video": False,
}

HIDDEN_S = 4

# a hidden video that crawls, mpv waiting on its frames, gets a fifth of this
PLAYED_AT_LEAST_MS = 3000

MOVED_TO_MS = 10_000

# from on show again to its picture drawn: a render round and no more
DRAWN_WITHIN_S = 0.5


def scenario(d):
    d.open(*d.media.clips)
    d.wait_until(lambda: len(d.cells) == 3, "three cells")
    first, second, third = d.cells

    d.wait_until(
        lambda: all(cell.is_playable and cell.time > 1000 for cell in d.cells),
        "all playing",
        timeout=30,
    )

    drawn = _count_draws(first)

    third.set_pause(True)
    d.wait_until(lambda: third.video_params.is_paused, "third paused")
    d.pump(0.5)
    third_before = _picture(third)

    d.act(first, "Single Mode ON / OFF")
    d.wait_until(
        lambda: not second.isVisible() and not third.isVisible(), "the others hidden"
    )
    d.pump(0.5)

    second_at, length = second.time, second.video_driver.length
    drawn_before = {cell: drawn(cell) for cell in d.cells}

    d.pump(HIDDEN_S)

    # On Direct mpv counts what it puts in a hidden window as shown, and has no
    # frames of ours to count: what hidden cells cost there is the bench's (EXP=single)
    is_counted = not _is_direct(first)

    if is_counted:
        d.check(
            "out of sight, they're not drawn",
            drawn(second) == drawn_before[second]
            and drawn(third) == drawn_before[third],
            {cell.id: drawn(cell) - drawn_before[cell] for cell in d.cells},
        )
    d.check(
        "the one on show is",
        drawn(first) - drawn_before[first] > HIDDEN_S * 10,
        drawn(first) - drawn_before[first],
    )

    played = (second.time - second_at) % length
    d.check(
        "and the others play on at their pace", played >= PLAYED_AT_LEAST_MS, played
    )

    third.seek(MOVED_TO_MS)
    d.wait_until(
        lambda: abs(third.time - MOVED_TO_MS) < 500, "the paused one moved", timeout=10
    )
    d.pump(0.5)

    second_drawn, third_drawn = drawn(second), drawn(third)
    shown_at = time.monotonic()

    d.act(first, "Single Mode ON / OFF")
    if is_counted:
        d.wait_until(
            lambda: drawn(second) > second_drawn and drawn(third) > third_drawn,
            "drawn again",
            timeout=5,
        )
        took_s = time.monotonic() - shown_at

        d.check("on show again, they're drawn at once", took_s < DRAWN_WITHIN_S, took_s)

    d.pump(0.3)
    third_shown = _picture(third)
    d.check(
        "the paused one shows where it was moved to",
        third_shown != third_before,
    )

    d.pump(1)
    d.check(
        "with nothing more to come",
        _picture(third) == third_shown,
    )

    d.shot("shown again")

    window = d.player
    _away_and_back(d, drawn, "minimized", window.showMinimized, window.showNormal)

    d.ctx.is_tray_shown = True
    _away_and_back(
        d,
        drawn,
        "in the tray",
        d.ctx.commands.toggle_window,
        d.ctx.commands.toggle_window,
    )

    d.note("end", second)


def _away_and_back(d, drawn, how, go, come_back):
    go()
    d.wait_until(d.ctx.commands.is_window_away, f"the window {how}")
    d.pump(0.5)

    cell = d.cells[0]
    cell_at, length = cell.time, cell.video_driver.length
    drawn_before = {cell: drawn(cell) for cell in d.cells}

    d.pump(HIDDEN_S)

    # see scenario
    is_counted = not _is_direct(cell)

    if is_counted:
        d.check(
            f"{how}, none is drawn",
            all(drawn(cell) == drawn_before[cell] for cell in d.cells),
            {cell.id: drawn(cell) - drawn_before[cell] for cell in d.cells},
        )

    played = (cell.time - cell_at) % length
    d.check(f"{how}, they play on at their pace", played >= PLAYED_AT_LEAST_MS, played)

    come_back()
    d.wait_until(
        lambda: not d.ctx.commands.is_window_away(), f"the window back from {how}"
    )
    # timed from when it's seen: macOS animates a minimized window back first, for
    # 2 s on a Mac with no GPU
    d.wait_until(d.player.windowHandle().isExposed, f"seen again from {how}")

    if not is_counted:
        return

    shown_at = time.monotonic()
    d.wait_until(
        lambda: all(
            drawn(cell) > drawn_before[cell]
            for cell in d.cells
            if not cell.video_params.is_paused
        ),
        "drawn again",
        timeout=5,
    )
    took_s = time.monotonic() - shown_at

    d.check(f"back from {how}, they're drawn at once", took_s < DRAWN_WITHIN_S, took_s)


def _rendered(cell):
    return cell.video_driver.video_driver._rendered


def _is_direct(cell) -> bool:
    """MPV's Direct output: mpv draws into its own window, no render thread."""

    return type(cell.video_driver).__name__ == "VideoFrameMpvWindow"


def _count_draws(cell):
    """How many frames a cell's video has drawn, by cell: counted on the render
    thread, or on Direct, mpv's frames less those its output dropped."""

    if _is_direct(cell):

        def drawn_by_mpv(one) -> int:
            mpv = one.video_driver.video_driver._player.mpv
            return (mpv.estimated_frame_number or 0) - (mpv.frame_drop_count or 0)

        return drawn_by_mpv

    renderer = cell.video_driver.video_driver._render_service._renderer
    render = renderer._render
    draws = collections.Counter()

    def counted(video, size):
        draws[id(video)] += 1
        render(video, size)

    renderer._render = counted

    return lambda one: draws[id(_rendered(one))]


def _picture(cell):
    if _is_direct(cell):
        from tests.real_app.composed import grab_composed

        return grab_composed(cell.video_driver)

    return cell.video_driver.video_surface.frame_image().copy()
