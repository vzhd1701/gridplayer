import pytest
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QApplication

from gridplayer.utils.video_errors import ShownError
from gridplayer.widgets import video_status as status_module
from gridplayer.widgets.video_status import (
    LoadStage,
    StatusMode,
    StepState,
    VideoStatus,
    elapsed_txt,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


ROWS = (
    "_row_glyph",
    "_row_status",
    "_row_bar",
    "_row_detail",
    "_row_steps",
    "_row_error_icon",
    "_row_error_title",
    "_row_about",
    "_row_tag",
    "_row_note",
)


def _painted(status, width, height):
    """Which rows it paints at this size, in order."""

    status.resize(width, height)

    painted = []

    for name in ROWS:
        setattr(
            status,
            name,
            lambda painter, rect, name=name: painted.append(name),
        )

    rows = (
        status._error_rows()
        if status.mode is StatusMode.ERROR
        else status._loading_rows()
    )

    image = QImage(width, height, QImage.Format_ARGB32)
    painter = QPainter(image)
    status._paint_rows(painter, rows)
    painter.end()

    return painted


def _loading(status, **kwargs):
    status.show_loading(
        LoadStage.VIDEO,
        "Buffering 45%",
        detail="1080p",
        percent=45,
        steps=(
            ("List", StepState.DONE),
            ("Link", StepState.DONE),
            ("Video", StepState.CURRENT),
        ),
        **kwargs,
    )


def test_a_big_cell_says_all_of_it():
    status = VideoStatus(is_framed=True)
    _loading(status)

    # its name is the overlay's title, not said again here
    assert _painted(status, 480, 300) == [
        "_row_glyph",
        "_row_status",
        "_row_bar",
        "_row_detail",
        "_row_steps",
    ]


def test_a_smaller_cell_drops_the_steps_first():
    status = VideoStatus(is_framed=True)
    _loading(status)

    painted = _painted(status, 260, 110)

    assert "_row_glyph" in painted
    assert "_row_status" in painted
    assert "_row_steps" not in painted


def test_a_small_cell_shows_the_glyph_alone():
    status = VideoStatus(is_framed=True)
    _loading(status)

    assert _painted(status, 150, 100) == ["_row_glyph"]


def test_the_overlay_bars_kept_clear_where_there_is_room():
    status = VideoStatus(is_framed=True)

    status.resize(480, 300)
    big = status.content_rect()

    status.resize(200, 120)
    small = status.content_rect()

    # past the frame and the overlay's 23px bars
    assert big.top() > 8 + 2 + 23
    assert big.bottom() < 300 - 8 - 2 - 23
    # no room for that: inside the frame only
    assert small.top() < 23


def test_the_time_taken_said_after_a_while(monkeypatch):
    status = VideoStatus(is_framed=True)
    now = [1000.0]
    monkeypatch.setattr(status_module.time, "monotonic", lambda: now[0])

    status.show_loading(LoadStage.LINK, "Resolving the link…", "yt-dlp")

    assert status._detail_line() == "yt-dlp"

    now[0] += 4.2

    assert status._detail_line() == "yt-dlp · 4 s"


def _chain_at(monkeypatch, seconds) -> QImage:
    status = VideoStatus(is_framed=True)
    status.show_loading(LoadStage.LINK, "Resolving the link…")
    monkeypatch.setattr(status_module.time, "monotonic", lambda: seconds)

    image = QImage(80, 80, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    status._row_glyph(painter, QRectF(0, 0, 80, 80))
    painter.end()

    return image


def _ink_columns(image) -> list[int]:
    return [
        x
        for x in range(image.width())
        if any(image.pixel(x, y) >> 24 for y in range(image.height()))
    ]


def test_the_link_glyph_is_a_chain_pulling_apart_and_joining(monkeypatch):
    period = status_module.CHAIN_PERIOD_S

    joined = _chain_at(monkeypatch, 0.0)
    held = _chain_at(monkeypatch, period * status_module.CHAIN_HELD * 0.9)
    apart = _chain_at(monkeypatch, period / 2)

    assert held == joined
    assert apart != joined

    # pulled apart, it reaches further out to either side
    assert min(_ink_columns(apart)) < min(_ink_columns(joined))
    assert max(_ink_columns(apart)) > max(_ink_columns(joined))


def test_the_time_taken_counted_from_the_stage():
    status = VideoStatus(is_framed=True)
    status.show_loading(LoadStage.LINK, "Resolving the link…")
    started = status._started_at

    status.show_loading(LoadStage.LINK, "Resolving the link…", "yt-dlp")
    assert status._started_at == started

    status.show_loading(LoadStage.VIDEO, "Opening…")
    assert status._started_at >= started


def test_the_time_taken_counted_afresh_for_another_load(monkeypatch):
    """Loading again at the stage the load before it was at, a reload say,
    on screen all along or put back: not the time since that one began."""

    status = VideoStatus(is_framed=True)
    now = [1000.0]
    monkeypatch.setattr(status_module.time, "monotonic", lambda: now[0])

    status.show_loading(LoadStage.VIDEO, "Opening…")

    now[0] += 30
    status.icon = "processing"
    status.show_loading(LoadStage.VIDEO, "Opening…")

    assert status._detail_line() == ""

    # and counted on while it stays
    now[0] += 4.2
    assert status._detail_line() == "4 s"


@pytest.mark.parametrize(
    ("seconds", "said"), [(4, "4 s"), (59.9, "59 s"), (65, "1 min 5 s")]
)
def test_elapsed_said_plainly(seconds, said):
    assert elapsed_txt(seconds) == said


def test_reconnecting_counts_down():
    status = VideoStatus(is_framed=True)

    status.show_reconnect(5, 15, "Try 2 of 5")

    assert status.stage is LoadStage.RECONNECT
    assert status.status_text == "Reconnecting…"
    assert status.countdown == 5
    assert status.detail == "Try 2 of 5"
    assert "_row_bar" not in _painted(status, 480, 300)


def test_an_error_said_by_the_old_way_becomes_a_card():
    status = VideoStatus(is_framed=True)

    status.status_text = "Failed to load media"
    status.icon = "error"

    assert status.mode is StatusMode.ERROR
    assert status.error.title == "Failed to load media"

    status.status_text = "File not found"

    assert status.error.title == "File not found"


def test_loading_again_forgets_the_error():
    status = VideoStatus(is_framed=True)
    status.show_error(ShownError(title="Access denied", where="Server", code="403"))

    status.icon = "processing"
    status.status_text = "Timed out"
    status.icon = "network-error"

    assert status.error == ShownError(title="Timed out", is_network=True)


def test_an_error_card_in_full():
    status = VideoStatus(is_framed=True)
    status.show_error(
        ShownError(
            title="Access denied",
            about="The server refused. The link may have expired.",
            where="Server",
            code="HTTP 403",
        ),
        "Next file in 5 s",
    )

    assert _painted(status, 480, 300) == [
        "_row_error_icon",
        "_row_error_title",
        "_row_about",
        "_row_tag",
        "_row_note",
    ]


def test_a_small_error_cell_keeps_the_tag():
    status = VideoStatus(is_framed=True)
    status.show_error(
        ShownError(
            title="Access denied",
            about="The server refused. The link may have expired.",
            where="Server",
            code="403",
        ),
        "Next file in 5 s",
    )

    assert _painted(status, 150, 100) == ["_row_error_icon", "_row_tag"]


def test_a_long_about_wrapped_in_two_lines_at_most():
    status = VideoStatus(is_framed=True)
    status.resize(480, 300)
    _, small = status._fonts()

    lines = status._about_lines("word " * 80, 200, small)

    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_the_audio_only_placeholder_is_a_picture_alone():
    status = VideoStatus(icon="audio-only")

    assert status.mode is StatusMode.ICON
    assert not status._is_framed


def test_it_moves_only_while_loading_and_shown():
    status = VideoStatus(is_framed=True)
    status.resize(300, 200)
    status.show()
    QApplication.processEvents()

    assert status._ticker.isActive()

    status.show_error(ShownError(title="Access denied"))
    assert not status._ticker.isActive()

    status.show_loading(LoadStage.VIDEO, "Opening…")
    assert status._ticker.isActive()

    status.hide()
    assert not status._ticker.isActive()

    status.close()
