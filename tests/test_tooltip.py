import math
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QHelpEvent,
    QKeyEvent,
    QTextDocument,
)
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gridplayer.main.init_resources import init_resources
from gridplayer.params.static import FONT_SIZE_MAIN
from gridplayer.widgets import tooltip as tooltip_module
from gridplayer.widgets.bookmark_colors import text_marker_html
from gridplayer.widgets.tooltip import (
    COLD_SETTLE_MS,
    GRACE_MS,
    SETTLE_MS,
    TIP_CURSOR_HEIGHT,
    TIP_CURSOR_INDENT,
    TIP_GAP,
    TIP_MAX_CHARS,
    TIP_PADDING_X,
    TIP_PADDING_Y,
    TipWindow,
    bottom_padding,
    fit_text_width,
    install_tooltips,
    tip_position,
)

LONG = (
    "Lets you move the playlist together with its videos. Links, and"
    " paths on another drive, are kept as they are. Lets you move the"
    " playlist together with its videos."
)


def _doc(text):
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setPlainText(text)
    return doc


class TestFitTextWidth:
    def test_a_short_text_keeps_its_own_width(self):
        doc = _doc("Reset")

        width = fit_text_width(doc, 400)

        doc.setTextWidth(-1)
        assert width == math.ceil(doc.idealWidth())

    def test_a_long_one_wraps_within_the_limit(self):
        assert fit_text_width(_doc(LONG), 300) <= 300

    def test_on_as_many_lines_as_at_the_limit_as_narrow_as_that_goes(self):
        doc = _doc(LONG)
        doc.setTextWidth(300)
        at_limit = doc.size().height()

        width = fit_text_width(doc, 300)

        doc.setTextWidth(width)
        assert doc.size().height() == at_limit
        doc.setTextWidth(width - 1)
        assert doc.size().height() > at_limit

    def test_lines_that_may_not_wrap_keep_their_width(self):
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setHtml("<p style='white-space:pre'>" + "word " * 40 + "</p>")
        doc.setTextWidth(-1)
        natural = math.ceil(doc.idealWidth())

        assert fit_text_width(doc, 200) >= natural


AREA = QRect(0, 0, 1920, 1040)
BOX = QSize(300, 60)
LINE = 15


class TestTipPosition:
    def test_under_the_row_a_little_left_of_the_mouse(self):
        row = QRect(100, 200, 400, 23)

        pos = tip_position(row, QPoint(250, 210), BOX, AREA, LINE)

        assert pos.y() == row.bottom() + 1 + TIP_GAP
        assert pos.x() == 250 - TIP_CURSOR_INDENT

    def test_at_the_same_height_wherever_the_mouse_is_on_the_row(self):
        row = QRect(100, 200, 400, 23)

        top = tip_position(row, QPoint(250, 201), BOX, AREA, LINE)
        bottom = tip_position(row, QPoint(250, 221), BOX, AREA, LINE)

        assert top.y() == bottom.y()

    def test_over_the_row_where_the_screen_ends_below(self):
        row = QRect(100, 1000, 400, 23)

        pos = tip_position(row, QPoint(250, 1010), BOX, AREA, LINE)

        assert pos.y() + BOX.height() + TIP_GAP == row.top()

    def test_under_the_mouse_for_a_tall_thing(self):
        cell = QRect(0, 0, 800, 450)

        pos = tip_position(cell, QPoint(400, 100), BOX, AREA, LINE)

        assert pos.y() == 100 + TIP_CURSOR_HEIGHT

    def test_kept_on_the_screen(self):
        row = QRect(1700, 200, 200, 23)

        pos = tip_position(row, QPoint(1900, 210), BOX, AREA, LINE)

        assert pos.x() + BOX.width() == AREA.right() + 1


MARKER_COLOR = "#ff00ff"


def _near(color, other):
    return all(
        abs(a - b) < 60
        for a, b in zip(color.getRgb()[:3], other.getRgb()[:3], strict=True)
    )


def _rows(image, box, is_ink):
    """The rows of the box with a pixel of ink in them, top to bottom."""

    return [
        y
        for y in range(box.top(), box.bottom() + 1)
        if any(
            image.pixelColor(x, y).alpha() > 200 and is_ink(image.pixelColor(x, y))
            for x in range(box.left(), box.right() + 1)
        )
    ]


class TestTipWindow:
    def test_as_much_room_under_the_baseline_as_over_the_capitals(self):
        metrics = QFontMetrics(TipWindow().font())

        over = TIP_PADDING_Y + metrics.ascent() - metrics.capHeight()
        under = metrics.descent() + bottom_padding(metrics)

        assert abs(over - under) <= 2

    def test_a_bookmark_s_marker_stands_level_with_the_digits(self):
        # in the app's own font, which its marker is drawn to match
        init_resources()
        tip = TipWindow()
        tip.setFont(QFont("Hack", FONT_SIZE_MAIN))
        marker = text_marker_html(MARKER_COLOR, QColor("#000000"), 1)
        tip.set_text(f'<div style="white-space: pre">00:30.000 {marker}Goal</div>')

        image = tip.grab().toImage()
        box = tip.box_geometry().translated(-tip.pos()).adjusted(2, 2, -2, -2)

        # the time only, left of the marker and its rim
        text = QColor(tooltip_module.current_colors()["tooltip_text"])
        time_box = QRect(
            box.topLeft(), QSize(tip.fontMetrics().width("00:30"), box.height())
        )
        digits = _rows(image, time_box, lambda c: _near(c, text))
        markers = _rows(image, box, lambda c: c.name() == MARKER_COLOR)

        assert markers[0] == digits[0]

    def test_and_makes_its_line_no_taller(self):
        tip = TipWindow()
        plain = tip.set_text("00:30.000").height()

        marker = text_marker_html(MARKER_COLOR, QColor("#000000"), 1)
        with_marker = tip.set_text(
            f'<div style="white-space: pre">00:30.000 {marker}Goal</div>'
        ).height()

        assert with_marker == plain

    def test_wraps_at_the_most_characters_it_takes(self):
        tip = TipWindow()
        one_line = tip.set_text("Reset").height()

        box = tip.set_text(LONG)

        char = QFontMetricsF(tip.font()).averageCharWidth()
        assert box.width() <= math.ceil(TIP_MAX_CHARS * char) + 2 * TIP_PADDING_X + 2
        assert box.height() > 2 * one_line

    def test_keeps_its_line_breaks(self):
        tip = TipWindow()
        one = tip.set_text("On").height()

        two = tip.set_text("On\nOff").height()

        assert two > one

    def test_takes_rich_text_as_such(self):
        tip = TipWindow()

        tip.set_text("<b>Bold</b>")

        assert tip._doc.toPlainText() == "Bold"

    def test_its_box_is_where_it_is_put(self):
        tip = TipWindow()
        tip.set_text("Reset")

        tip.move_box(QPoint(100, 200))

        assert tip.box_geometry().topLeft() == QPoint(100, 200)


@pytest.fixture
def manager():
    app = QApplication.instance()
    manager = install_tooltips(app)

    yield manager

    app.removeEventFilter(manager)
    manager._poll.stop()
    manager._hide_now()


@pytest.fixture
def form(mocker):
    window = QWidget()
    layout = QVBoxLayout(window)

    first = QLabel("Proportional zoom")
    first.setToolTip("Zooms by the same share of what's on screen.")
    second = QLabel("File limit")
    second.setToolTip("The most files and folders to scan.")
    plain = QLabel("No tip")

    rows = QListWidget()
    item = QListWidgetItem("Episode 01")
    item.setToolTip("D:/Videos/Episode 01.mp4")
    rows.addItem(item)

    for widget in (first, second, plain, rows):
        layout.addWidget(widget)

    window.resize(400, 300)
    window.show()

    # no window is active on the offscreen platform
    mocker.patch.object(
        tooltip_module.TooltipManager,
        "_is_window_active",
        staticmethod(lambda w: w is window),
    )
    mocker.patch.object(
        tooltip_module.QApplication, "activeWindow", side_effect=lambda: window
    )

    yield SimpleNamespace(
        window=window, first=first, second=second, plain=plain, rows=rows, item=item
    )

    window.close()


@pytest.fixture
def clock(mocker):
    now = {"t": 1000.0}

    mocker.patch.object(tooltip_module, "monotonic", side_effect=lambda: now["t"])

    def _advance(ms):
        now["t"] += ms / 1000

    return _advance


@pytest.fixture
def mouse(mocker):
    at = {"pos": QPoint()}

    mocker.patch.object(
        tooltip_module.QCursor, "pos", side_effect=lambda: QPoint(at["pos"])
    )

    def _move_to(widget, local=None):
        local = widget.rect().center() if local is None else local
        at["pos"] = widget.mapToGlobal(local)

    return _move_to


@pytest.fixture(autouse=True)
def _no_fades(monkeypatch):
    # the swap fades out before it shows the next one, and a test spins no
    # event loop to see a fade through
    monkeypatch.setattr(tooltip_module, "SWAP_OUT_MS", 0)


def _hover(widget, local=None):
    local = widget.rect().center() if local is None else local
    event = QHelpEvent(QEvent.ToolTip, local, widget.mapToGlobal(local))
    return QApplication.sendEvent(widget, event)


def _shown_text(manager):
    return manager._shown.text if manager.is_shown else None


class TestInPlaceOfQts:
    def test_it_takes_qt_s_tooltip_event(self, manager, form, mouse):
        mouse(form.first)

        assert _hover(form.first)

        assert manager._tip.isVisible()
        assert manager._tip.text() == form.first.toolTip()

    def test_under_the_widget_it_is_about(self, manager, form, mouse):
        mouse(form.first)

        _hover(form.first)

        bottom = form.first.mapToGlobal(QPoint(0, form.first.height())).y()
        assert manager._tip.box_geometry().top() == bottom + TIP_GAP

    def test_a_widget_without_one_is_left_to_qt(self, manager, form, mouse):
        mouse(form.plain)

        _hover(form.plain)

        assert not manager.is_shown

    def test_a_list_row_has_its_own(self, manager, form, mouse):
        viewport = form.rows.viewport()
        rect = form.rows.visualItemRect(form.item)
        mouse(viewport, rect.center())

        _hover(viewport, rect.center())

        assert _shown_text(manager) == "D:/Videos/Episode 01.mp4"
        bottom = viewport.mapToGlobal(rect.bottomLeft()).y()
        assert manager._tip.box_geometry().top() == bottom + 1 + TIP_GAP

    def test_a_key_hides_it_at_once(self, manager, form, mouse):
        mouse(form.first)
        _hover(form.first)

        QApplication.sendEvent(
            form.first, QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier)
        )

        assert not manager.is_shown
        assert not manager._tip.isVisible()


class TestBetweenRows:
    @pytest.fixture
    def shown(self, manager, form, mouse, clock):
        mouse(form.first)
        _hover(form.first)

        return manager

    def test_moving_on_the_row_keeps_it(self, shown, form, mouse, clock):
        mouse(form.first, QPoint(2, 2))
        shown._on_poll()
        clock(SETTLE_MS * 3)
        shown._on_poll()

        assert _shown_text(shown) == form.first.toolTip()

    def test_it_moves_to_another_row_only_once_the_mouse_rests(
        self, shown, form, mouse, clock
    ):
        mouse(form.second)
        shown._on_poll()
        clock(SETTLE_MS - 10)
        shown._on_poll()

        assert _shown_text(shown) == form.first.toolTip()

        clock(20)
        shown._on_poll()

        assert _shown_text(shown) == form.second.toolTip()
        assert shown._tip.text() == form.second.toolTip()

    def test_it_goes_a_moment_after_the_mouse_leaves_every_tip(
        self, shown, form, mouse, clock
    ):
        mouse(form.plain)
        shown._on_poll()
        clock(GRACE_MS - 10)
        shown._on_poll()

        assert shown.is_shown

        clock(20)
        shown._on_poll()

        assert not shown.is_shown

    def test_and_the_next_one_comes_sooner(self, shown, form, mouse, clock):
        mouse(form.plain)
        shown._on_poll()
        clock(GRACE_MS + 10)
        shown._on_poll()

        mouse(form.second)
        shown._on_poll()
        clock(SETTLE_MS + 1)
        shown._on_poll()

        assert _shown_text(shown) == form.second.toolTip()

    def test_after_a_click_not_again_until_the_mouse_was_elsewhere(
        self, shown, form, mouse, clock
    ):
        QApplication.sendEvent(
            form.first, QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier)
        )
        _hover(form.first)
        clock(COLD_SETTLE_MS + 1)
        shown._on_poll()

        assert not shown.is_shown

        mouse(form.plain)
        shown._on_poll()
        mouse(form.first)
        shown._on_poll()
        clock(COLD_SETTLE_MS + 1)
        shown._on_poll()

        assert _shown_text(shown) == form.first.toolTip()
