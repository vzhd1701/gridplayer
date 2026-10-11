"""What a cell shows in place of its video: how far it got loading it, or
why it could not play it.

Drawn as the empty and the stopped cells are, in the chrome's greys inside
the same solid frame: a glyph of its own for each stage of loading, so a
list being read is told apart from a video opening at a glance, what it is
doing, a bar, and where it is in the steps it goes through.
"""

import dataclasses
import math
import time
from enum import Enum, auto

from PyQt5.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QSizePolicy, QWidget

from gridplayer.utils.qt import translate
from gridplayer.utils.video_errors import ShownError
from gridplayer.widgets.cell_chrome import (
    CHROME_ALPHA,
    TEXT_ALPHA,
    chrome_color,
    dashed_frame,
    paint_solid_outline,
)
from gridplayer.widgets.error_tag import paint_tag, tag_widths

# the details, fainter than what it is doing, still easily read
DIM_ALPHA = 140

# the bar's groove
TRACK_ALPHA = 40

# between the frame's line and what is inside it, and between the lines
GAP = 6
LINE_GAP = 7

# the overlay's bars, room left for them above and below where there is
# room for it, so that they do not cover what is said
OVERLAY_BAR_PX = 23

# less room than this for the lines, and it is the glyph alone, and the
# tag of an error
TIGHT_WIDTH = 140
TIGHT_HEIGHT = 60

# what is kept in a tight cell, by its drop order
TIGHT_KEPT_FROM = 60

BAR_HEIGHT = 4
BAR_MAX_WIDTH = 180

TAG_HEIGHT = 18
TAG_PADDING = 6

ABOUT_MAX_WIDTH = 280

# the glyph, as a share of the room, within these; alone, a larger one
GLYPH_SHARE = 0.22
GLYPH_ALONE_SHARE = 0.45
GLYPH_MIN = 20
GLYPH_MAX = 52

# A larger cell says it all larger, the sizes above grown by its shorter
# side past this: three quarters as fast as the cell grows, up to half as
# large again, a full-screen cell's.
SCALE_FROM = 360
SCALE_RATE = 0.75
SCALE_MAX = 1.5

# What it is doing and the lines under it, this many points larger than the
# app's font in a cell of SCALE_FROM, grown from there in whole points
TITLE_POINTS = 2
DETAIL_POINTS = 1

FRAME_MS = 33

# the jumping bars of a video opening: up in 100ms, down in 900ms, each at
# its own point of that, the outer ones together, as they always have
BARS_PERIOD_MS = 1000
BARS_GROW_MS = 100
BARS_LOWEST = 0.3
BARS_OFFSETS_MS = (100, 486, 743, 486, 100)

ROWS_PERIOD_S = 1.2
ROWS_STEP_S = 0.3

# the two links of a chain pulling apart and joining again, held
# together at either end of it, the sign of a link as Add URL's is;
# the links and how far apart they pull, in a glyph 40 wide
CHAIN_PERIOD_S = 1.4
CHAIN_HELD = 0.15
CHAIN_LINK_LENGTH = 26 / 40
CHAIN_LINK_WIDTH = 13 / 40
CHAIN_LINK_OFFSET = 8 / 40
CHAIN_PULL = 3 / 40

SLIDE_PERIOD_S = 1.4

# the elapsed time said once it is this long
ELAPSED_FROM_S = 3

# The steps it goes through, a dot each joined by a short line: a dot, and
# the ring of the one it is at, larger, how thick the rings are drawn, how
# long the lines are, the room either side of them, and between a dot and
# its name.
STEP_DOT = 8
STEP_RING = 10
STEP_RING_STROKE = 2
STEP_TODO_STROKE = 1.5
STEP_LINK = 18
STEP_GAP = 6
STEP_LABEL_GAP = 5


class LoadStage(Enum):
    """What the cell is doing to get to its video."""

    # reading the list it plays from
    LIST = auto()
    # finding the video behind a link
    LINK = auto()
    # opening the video itself
    VIDEO = auto()
    # waiting to try again
    RECONNECT = auto()


class StepState(Enum):
    DONE = auto()
    CURRENT = auto()
    TODO = auto()


class StatusMode(Enum):
    LOADING = auto()
    ERROR = auto()
    # a picture and nothing else, the audio-only placeholder's
    ICON = auto()


def step_label(stage: LoadStage) -> str:
    return {
        LoadStage.LIST: translate("Video Status", "List"),
        LoadStage.LINK: translate("Video Status", "Link"),
        LoadStage.VIDEO: translate("Video Status", "Video"),
    }.get(stage, "")


def elapsed_txt(seconds: float) -> str:
    seconds = int(seconds)

    if seconds < 60:
        return translate("Video Status", "{SECONDS} s").format(SECONDS=seconds)

    return translate("Video Status", "{MINUTES} min {SECONDS} s").format(
        MINUTES=seconds // 60, SECONDS=seconds % 60
    )


class VideoStatus(QWidget):
    def __init__(self, icon="processing", is_framed=False, **kwargs):
        super().__init__(**kwargs)

        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Due to VLC video block glitch, cannot hide video block
        # workaround - make overlay loading screen 99% opaque
        # so it will appear visually solid while video block is invisible
        effect = QGraphicsOpacityEffect(self)
        almost_opaque = 0.99
        effect.setOpacity(almost_opaque)
        self.setGraphicsEffect(effect)

        # the cell's own status, in its frame; the audio-only placeholder
        # over a playing video is not
        self._is_framed = is_framed
        self._is_active = False

        # the frame alone, while something dragged over the cell says what
        # dropping it there does
        self._is_content_shown = True

        self._mode = StatusMode.LOADING
        self._icon_name = None

        self._stage = LoadStage.VIDEO
        self._text = ""
        self._detail = ""
        self._percent = 0
        self._is_progress_known = False
        self._steps: tuple[tuple[str, StepState], ...] = ()

        # why it could not play, and what happens next
        self._error: ShownError | None = None
        self._note = ""

        # the countdown to trying again: from what, and from when
        self._countdown_total = 0
        self._countdown_left = 0
        self._countdown_told_at = 0.0

        self._started_at = time.monotonic()

        # the fonts and colours it says it in, worked out again only once
        # the font, the size or the palette it has them from is another
        self._fonts_of: tuple[tuple, tuple[QFont, QFont]] | None = None
        self._colors_of: tuple[int, tuple[QColor, ...]] | None = None

        self._ticker = QTimer(self)
        self._ticker.setInterval(FRAME_MS)
        self._ticker.timeout.connect(self._tick)

        self.icon = icon

    # --- the old way of being told, kept for the audio-only placeholder

    @property
    def icon(self):
        return self._icon_name

    @icon.setter
    def icon(self, icon):
        """processing: loading; error, network-error: failed; anything else
        a picture of its own."""

        self._icon_name = icon

        if icon == "processing":
            # a load begun, over again maybe at the stage the one before it
            # was at: the time said is this one's
            self._mode = StatusMode.LOADING
            self._error = None
            self._started_at = time.monotonic()
        elif icon in {"error", "network-error"}:
            self._mode = StatusMode.ERROR

            is_network = icon == "network-error"

            if self._error is None:
                self._error = ShownError(title=self._text, is_network=is_network)
                self._note = ""
            else:
                self._error = dataclasses.replace(self._error, is_network=is_network)
        else:
            self._mode = StatusMode.ICON

        self._sync_ticker()
        self.update()

    @property
    def status_text(self) -> str:
        if self._mode is StatusMode.ERROR:
            return self._error.title

        return self._text

    @status_text.setter
    def status_text(self, text: str):
        self._text = text

        if self._mode is StatusMode.ERROR:
            self._error = dataclasses.replace(self._error, title=text)

        self.update()

    @property
    def percent(self) -> int:
        return self._percent

    @percent.setter
    def percent(self, percent):
        self._percent = min(max(int(percent), 0), 100)
        self._is_progress_known = self._percent > 0
        self.update()

    # --- what it is told now

    @property
    def mode(self) -> StatusMode:
        return self._mode

    @property
    def stage(self) -> LoadStage:
        return self._stage

    @property
    def detail(self) -> str:
        return self._detail

    @property
    def steps(self) -> tuple[tuple[str, StepState], ...]:
        return self._steps

    @property
    def countdown(self) -> int:
        """The seconds left to trying again, while it waits to."""

        if self._stage is not LoadStage.RECONNECT:
            return 0

        return self._countdown_left

    @property
    def error(self) -> ShownError | None:
        return self._error if self._mode is StatusMode.ERROR else None

    @property
    def note(self) -> str:
        """What happens next, under the error."""

        return self._note if self._mode is StatusMode.ERROR else ""

    def show_loading(
        self,
        stage: LoadStage,
        text: str,
        detail: str = "",
        percent: int | None = None,
        steps: tuple[tuple[str, StepState], ...] = (),
    ):
        """Loading, at this stage; a bar for a percent, a sliding one for
        None. The time it has taken is said after the detail."""

        if self._mode is not StatusMode.LOADING or stage is not self._stage:
            self._started_at = time.monotonic()

        self._mode = StatusMode.LOADING
        self._icon_name = "processing"
        self._stage = stage
        self._text = text
        self._detail = detail
        self._steps = steps
        self._percent = 0 if percent is None else min(max(int(percent), 0), 100)
        self._is_progress_known = percent is not None
        self._error = None

        self._sync_ticker()
        self.update()

    def show_reconnect(self, seconds_left: int, seconds_total: int, detail: str):
        """Waiting to try again: a ring running down to it, the seconds
        left in it, said there only, the glyph being all of it a small
        cell shows."""

        self.show_loading(
            LoadStage.RECONNECT,
            translate("Video Status", "Reconnecting…"),
            detail,
        )

        self._countdown_left = seconds_left
        self._countdown_total = max(seconds_total, 1)
        self._countdown_told_at = time.monotonic()

    def show_error(self, error: ShownError, note: str = ""):
        self._mode = StatusMode.ERROR
        self._icon_name = error.icon
        self._text = error.title
        self._error = error
        self._note = note

        self._sync_ticker()
        self.update()

    def set_is_active(self, is_active: bool):
        if self._is_active != is_active:
            self._is_active = is_active
            self.update()

    def set_is_content_shown(self, is_shown: bool):
        if self._is_content_shown != is_shown:
            self._is_content_shown = is_shown
            self.update()

    # --- painting

    def showEvent(self, event):
        self._sync_ticker()

    def hideEvent(self, event):
        self._ticker.stop()

    def _tick(self):
        # what moves is inside the frame: the frame left be, and the overlay
        # over the cell painted again only where it is over what moves
        self.update(self.content_rect().toAlignedRect())

    def _sync_ticker(self):
        is_moving = self._mode is StatusMode.LOADING and self.isVisible()

        if is_moving and not self._ticker.isActive():
            self._ticker.start()
        elif not is_moving:
            self._ticker.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_framed:
            paint_solid_outline(self, painter, is_active=self._is_active)

        if not self._is_content_shown:
            return

        if self._mode is StatusMode.ICON:
            self._paint_icon_only(painter)
        elif self._mode is StatusMode.ERROR:
            self._paint_rows(painter, self._error_rows())
        else:
            self._paint_rows(painter, self._loading_rows())

    def content_rect(self) -> QRectF:
        """Inside the frame, and between the overlay's bars where there is
        room for them."""

        if not self._is_framed:
            return QRectF(self.rect()).adjusted(
                self.width() * 0.1,
                self.height() * 0.1,
                -self.width() * 0.1,
                -self.height() * 0.1,
            )

        rect, stroke, _ = dashed_frame(self)
        inset = stroke / 2 + GAP
        inner = rect.adjusted(inset, inset, -inset, -inset)

        bars = OVERLAY_BAR_PX + GAP

        if inner.height() - bars * 2 >= GLYPH_MIN * 3:
            inner.adjust(0, bars, 0, -bars)

        return inner

    def _paint_icon_only(self, painter):
        if not self._icon_name:
            return

        room = self.content_rect()
        side = min(room.width(), room.height())
        rect = QRectF(0, 0, side, side)
        rect.moveCenter(room.center())

        painter.save()
        painter.setOpacity(0.5)
        QIcon.fromTheme(self._icon_name).paint(painter, rect.toRect())
        painter.restore()

    # Each row: (height, paint(painter, rect), drop order). Rows that do not
    # fit are dropped lowest order first; the glyph is never dropped.

    def scale(self) -> float:
        """How much larger than in a cell of SCALE_FROM it says it all."""

        if not self._is_framed:
            return 1.0

        side = min(self.width(), self.height())
        grown = 1 + SCALE_RATE * (side / SCALE_FROM - 1)

        return min(max(grown, 1.0), SCALE_MAX)

    def _px(self, size: float) -> float:
        return size * self.scale()

    def _fonts(self) -> tuple[QFont, QFont]:
        key = (self.font().key(), self.scale())

        if self._fonts_of is None or self._fonts_of[0] != key:
            points = self.font().pointSizeF()

            bold = QFont(self.font())
            bold.setPointSizeF(math.floor(self._px(points + TITLE_POINTS) + 0.5))
            bold.setBold(True)

            small = QFont(self.font())
            small.setPointSizeF(math.floor(self._px(points + DETAIL_POINTS) + 0.5))

            self._fonts_of = (key, (bold, small))

        return self._fonts_of[1]

    @staticmethod
    def _is_tight(room: QRectF) -> bool:
        return room.width() < TIGHT_WIDTH or room.height() < TIGHT_HEIGHT

    def _glyph_size(self, room: QRectF) -> float:
        share = GLYPH_ALONE_SHARE if self._is_tight(room) else GLYPH_SHARE
        side = min(room.width(), room.height()) * share

        return min(max(side, GLYPH_MIN), self._px(GLYPH_MAX))

    def _loading_rows(self):
        room = self.content_rect()
        bold, small = self._fonts()
        bold_height = QFontMetrics(bold).height()
        small_height = QFontMetrics(small).height()

        rows = []

        glyph = self._glyph_size(room)
        rows.append((glyph, self._row_glyph, 100))

        if self._text:
            rows.append((bold_height, self._row_status, 50))

        if self._stage is not LoadStage.RECONNECT:
            rows.append((self._px(BAR_HEIGHT), self._row_bar, 40))

        if self._detail_line():
            rows.append((small_height, self._row_detail, 3))

        if len(self._steps) > 1:
            rows.append((small_height, self._row_steps, 2))

        return rows

    def _error_rows(self):
        error = self._error

        room = self.content_rect()
        bold, small = self._fonts()
        bold_height = QFontMetrics(bold).height()
        small_height = QFontMetrics(small).height()

        rows = [(self._glyph_size(room), self._row_error_icon, 100)]

        if error.title:
            rows.append((bold_height, self._row_error_title, 30))

        if error.about:
            lines = self._about_lines(error.about, room.width(), small)
            rows.append((small_height * len(lines), self._row_about, 5))

        if error.where or error.code:
            rows.append((self._px(TAG_HEIGHT), self._row_tag, 60))

        if self._note:
            rows.append((small_height, self._row_note, 10))

        return rows

    def _paint_rows(self, painter, rows):
        room = self.content_rect()

        if self._is_tight(room):
            rows = [row for row in rows if row[2] >= TIGHT_KEPT_FROM]

        line_gap = self._px(LINE_GAP)

        def total(rows):
            return sum(row[0] for row in rows) + line_gap * max(len(rows) - 1, 0)

        while total(rows) > room.height():
            droppable = [row for row in rows if row[2] < 100]

            if not droppable:
                break

            rows.remove(min(droppable, key=lambda row: row[2]))

        top = room.top() + max((room.height() - total(rows)) / 2, 0)

        for height, paint, _ in rows:
            # the glyph alone, shrunk to fit a cell too small for it
            height = min(height, room.height())
            paint(painter, QRectF(room.left(), top, room.width(), height))
            top += height + line_gap

    # --- the rows

    def _colors(self) -> tuple[QColor, ...]:
        key = self.palette().cacheKey()

        if self._colors_of is None or self._colors_of[0] != key:
            colors = (
                chrome_color(self, CHROME_ALPHA),
                chrome_color(self, TEXT_ALPHA),
                chrome_color(self, DIM_ALPHA),
                chrome_color(self, TRACK_ALPHA),
            )

            self._colors_of = (key, colors)

        return self._colors_of[1]

    def _draw_line(self, painter, rect, text, font, color):
        metrics = QFontMetrics(font)
        shown = metrics.elidedText(text, Qt.ElideMiddle, int(rect.width()))

        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, shown)

    def _row_status(self, painter, rect):
        bold, _ = self._fonts()
        _, text, _, _ = self._colors()
        self._draw_line(painter, rect, self._text, bold, text)

    def _detail_line(self) -> str:
        parts = [self._detail] if self._detail else []

        elapsed = time.monotonic() - self._started_at

        if self._stage is not LoadStage.RECONNECT and elapsed >= ELAPSED_FROM_S:
            parts.append(elapsed_txt(elapsed))

        return " · ".join(parts)

    def _row_detail(self, painter, rect):
        _, small = self._fonts()
        _, _, dim, _ = self._colors()
        self._draw_line(painter, rect, self._detail_line(), small, dim)

    def _row_bar(self, painter, rect):
        _, text, _, track = self._colors()

        height = self._px(BAR_HEIGHT)
        width = min(self._px(BAR_MAX_WIDTH), rect.width() * 0.6)
        bar = QRectF(0, 0, width, height)
        bar.moveCenter(rect.center())

        radius = height / 2

        # what runs along it is kept to its rounded ends, not cut square
        # where it runs in and out of them
        groove = QPainterPath()
        groove.addRoundedRect(bar, radius, radius)

        painter.fillPath(groove, track)

        if self._is_progress_known:
            done = QRectF(bar)
            done.setWidth(bar.width() * self._percent / 100)
        else:
            phase = (time.monotonic() % SLIDE_PERIOD_S) / SLIDE_PERIOD_S
            phase = 0.5 - math.cos(phase * math.pi) / 2
            part = bar.width() * 0.4
            left = bar.left() - part + (bar.width() + part) * phase

            done = QRectF(left, bar.top(), part, height)

        # the shape shared, not clipped to: a clip path is drawn jagged
        moving = QPainterPath()
        moving.addRoundedRect(done, radius, radius)
        painter.fillPath(groove.intersected(moving), text)

    def _row_steps(self, painter, rect):
        """Where it is in its steps: a dot each, joined by a line, named
        beside it. Filled for a step done, a ring for the one it is at, a
        faint ring for those to come; the line on from a step done drawn
        as it is."""

        _, small = self._fonts()
        bold_small = QFont(small)
        bold_small.setBold(True)

        chrome, text, dim, track = self._colors()

        dot = self._px(STEP_DOT)
        ring = self._px(STEP_RING)
        link = self._px(STEP_LINK)
        gap = self._px(STEP_GAP)
        label_gap = self._px(STEP_LABEL_GAP)

        steps = []

        for label, state in self._steps:
            font = bold_small if state is StepState.CURRENT else small
            marker = ring if state is StepState.CURRENT else dot
            advance = QFontMetrics(font).horizontalAdvance(label)
            steps.append((label, state, font, marker, advance))

        width = sum(marker + label_gap + advance for *_, marker, advance in steps)
        width += (len(steps) - 1) * (gap + link + gap)

        if width > rect.width():
            return

        middle = rect.center().y()
        left = rect.center().x() - width / 2

        painter.save()

        for index, (label, state, font, marker, advance) in enumerate(steps):
            if index:
                was_done = steps[index - 1][1] is StepState.DONE
                line = QRectF(left + gap, middle - self._px(1), link, self._px(2))
                painter.setPen(Qt.NoPen)
                painter.setBrush(dim if was_done else track)
                painter.drawRoundedRect(line, line.height() / 2, line.height() / 2)
                left += gap + link + gap

            center = QPointF(left + marker / 2, middle)

            if state is StepState.DONE:
                painter.setPen(Qt.NoPen)
                painter.setBrush(dim)
                painter.drawEllipse(center, dot / 2, dot / 2)
                color = dim
            elif state is StepState.CURRENT:
                stroke = self._px(STEP_RING_STROKE)
                painter.setPen(QPen(text, stroke))
                painter.setBrush(Qt.NoBrush)
                radius = (ring - stroke) / 2
                painter.drawEllipse(center, radius, radius)
                color = text
            else:
                stroke = self._px(STEP_TODO_STROKE)
                painter.setPen(QPen(chrome, stroke))
                painter.setBrush(Qt.NoBrush)
                radius = (dot - stroke) / 2
                painter.drawEllipse(center, radius, radius)
                color = chrome

            left += marker + label_gap

            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(
                QRectF(left, rect.top(), advance + 1, rect.height()),
                Qt.AlignVCenter | Qt.AlignLeft,
                label,
            )
            left += advance

        painter.restore()

    def _row_glyph(self, painter, rect):
        side = min(rect.height(), rect.width())
        box = QRectF(0, 0, side, side)
        box.moveCenter(rect.center())

        chrome, text, _, track = self._colors()

        if self._stage is LoadStage.LIST:
            self._paint_list_glyph(painter, box, chrome)
        elif self._stage is LoadStage.LINK:
            self._paint_chain_glyph(painter, box, chrome)
        elif self._stage is LoadStage.RECONNECT:
            self._paint_countdown_glyph(painter, box, chrome, text, track)
        else:
            self._paint_bars_glyph(painter, box, chrome)

    def _paint_bars_glyph(self, painter, box, color):
        count = len(BARS_OFFSETS_MS)
        width = box.width() * 1.1
        bar_width = max(width * 0.13, 2.0)
        step = (width - bar_width) / (count - 1)
        left = box.center().x() - width / 2

        now_ms = time.monotonic() * 1000

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)

        for index, offset in enumerate(BARS_OFFSETS_MS):
            phase = (now_ms + offset) % BARS_PERIOD_MS

            if phase < BARS_GROW_MS:
                share = BARS_LOWEST + (1 - BARS_LOWEST) * phase / BARS_GROW_MS
            else:
                wane = (phase - BARS_GROW_MS) / (BARS_PERIOD_MS - BARS_GROW_MS)
                share = 1 - (1 - BARS_LOWEST) * wane

            height = box.height() * share
            bar = QRectF(
                left + step * index,
                box.center().y() - height / 2,
                bar_width,
                height,
            )
            radius = bar_width / 2
            painter.drawRoundedRect(bar, radius, radius)

        painter.restore()

    def _paint_list_glyph(self, painter, box, color):
        row_height = max(box.height() * 0.16, 2.0)
        bullet = box.width() * 0.2
        gap = box.width() * 0.12
        radius = row_height / 2

        top = box.top() + box.height() * 0.1
        step = (box.height() * 0.8 - row_height) / 2

        now = time.monotonic()

        painter.save()
        painter.setPen(Qt.NoPen)

        for row in range(3):
            phase = ((now - row * ROWS_STEP_S) % ROWS_PERIOD_S) / ROWS_PERIOD_S
            pulse = 1 - min(phase, 1 - phase) * 2

            painter.setOpacity(0.35 + 0.65 * pulse)
            painter.setBrush(color)

            y = top + step * row
            painter.drawRoundedRect(
                QRectF(box.left(), y, bullet, row_height), radius, radius
            )
            painter.drawRoundedRect(
                QRectF(
                    box.left() + bullet + gap,
                    y,
                    box.width() - bullet - gap,
                    row_height,
                ),
                radius,
                radius,
            )

        painter.restore()

    def _paint_chain_glyph(self, painter, box, color):
        side = box.width()
        stroke = max(side * 0.07, 1.5)

        phase = (time.monotonic() % CHAIN_PERIOD_S) / CHAIN_PERIOD_S
        pulling = (phase - CHAIN_HELD) / (1 - CHAIN_HELD * 2)
        pull = 0.0

        if 0 < pulling < 1:
            pull = (1 - math.cos(pulling * 2 * math.pi)) / 2

        offset = side * (CHAIN_LINK_OFFSET + CHAIN_PULL * pull)
        length = side * CHAIN_LINK_LENGTH - stroke
        width = side * CHAIN_LINK_WIDTH - stroke
        radius = width / 2

        painter.save()
        painter.translate(box.center())
        painter.rotate(-45)
        painter.setPen(QPen(color, stroke))
        painter.setBrush(Qt.NoBrush)

        for sign in (-1, 1):
            link = QRectF(0, 0, length, width)
            link.moveCenter(QPointF(sign * offset, 0))
            painter.drawRoundedRect(link, radius, radius)

        painter.restore()

    def _paint_countdown_glyph(self, painter, box, chrome, text, track):
        stroke = max(box.width() * 0.08, 2.0)
        ring = box.adjusted(stroke / 2, stroke / 2, -stroke / 2, -stroke / 2)

        # down a second's worth smoothly between ticks
        since = min(time.monotonic() - self._countdown_told_at, 1.0)
        left = max(self._countdown_left - since, 0)
        share = left / self._countdown_total if self._countdown_total else 0

        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(track, stroke))
        painter.drawEllipse(ring)

        pen = QPen(chrome, stroke)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(ring, 90 * 16, int(share * 360 * 16))

        bold = QFont(self._fonts()[0])
        bold.setPointSizeF(max(bold.pointSizeF(), box.height() * 0.3 * 0.75))
        painter.setFont(bold)
        painter.setPen(text)
        painter.drawText(ring, Qt.AlignCenter, str(self._countdown_left))
        painter.restore()

    def _row_error_icon(self, painter, rect):
        side = min(rect.height(), rect.width())
        box = QRect(0, 0, int(side), int(side))
        box.moveCenter(rect.center().toPoint())

        icon = self._error.icon

        painter.save()
        painter.setOpacity(TEXT_ALPHA / 255)
        QIcon.fromTheme(icon).paint(painter, box)
        painter.restore()

    def _row_error_title(self, painter, rect):
        bold, _ = self._fonts()
        _, text, _, _ = self._colors()
        self._draw_line(painter, rect, self._error.title, bold, text)

    def _about_lines(self, about: str, width: float, font) -> list[str]:
        """The line on what it means, wrapped in two at most."""

        metrics = QFontMetrics(font)
        width = int(min(width, self._px(ABOUT_MAX_WIDTH)))

        if metrics.horizontalAdvance(about) <= width:
            return [about]

        words = about.split()
        first = ""

        for index, word in enumerate(words):
            candidate = f"{first} {word}".strip()

            if metrics.horizontalAdvance(candidate) > width and first:
                rest = " ".join(words[index:])
                return [first, metrics.elidedText(rest, Qt.ElideRight, width)]

            first = candidate

        return [metrics.elidedText(about, Qt.ElideRight, width)]

    def _row_about(self, painter, rect):
        _, small = self._fonts()
        _, _, dim, _ = self._colors()

        lines = self._about_lines(self._error.about, rect.width(), small)
        height = rect.height() / len(lines)

        for index, line in enumerate(lines):
            self._draw_line(
                painter,
                QRectF(rect.left(), rect.top() + height * index, rect.width(), height),
                line,
                small,
                dim,
            )

    def _row_tag(self, painter, rect):
        """Where it broke and its code, in a tag of two parts: the first
        filled in the frame's grey."""

        _, small = self._fonts()
        chrome, text, _, _ = self._colors()
        background = self.palette().color(self.backgroundRole())

        where, code = self._error.where, self._error.code
        widths = tag_widths(QFontMetrics(small), where, code, self._px(TAG_PADDING))
        width = sum(widths)

        if width > rect.width():
            return

        tag = QRectF(
            rect.center().x() - width / 2, rect.top(), width, self._px(TAG_HEIGHT)
        )

        painter.save()
        painter.setFont(small)
        paint_tag(
            painter, tag, where, code, widths, self._px(3), chrome, background, text
        )
        painter.restore()

    def _row_note(self, painter, rect):
        _, small = self._fonts()
        _, _, dim, _ = self._colors()
        self._draw_line(painter, rect, self._note, small, dim)
