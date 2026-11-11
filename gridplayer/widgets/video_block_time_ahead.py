"""The loop's end and SponsorBlock's skips on time, not at the next report.

The players report the time a few times a second: MPV every 200 ms, VLC every
250 ms and at times 500. The loop's end and SponsorBlock's skips are checked as
it comes, so a loop played up to half a second past its end on VLC, and a
sponsor showed for a third of a second, before they were seen to.

With a mark due before the next report, a timer goes off at the moment it's
reached, worked out from the last report and the rate, and the block checks
the mark then (VideoBlock.reach_time). Any report, seek, pause, change of rate
or of video puts it off, and so does a report that's late: the video may have
stopped to buffer, and acting on where it would be by now would loop or skip
early.
"""

import collections
import time

from PyQt5.QtCore import Qt, QTimer

from gridplayer.widgets.video_block_guards import VideoBlockPart

# Farther off than this, a report comes before it does and aims again. VLC's
# can be 500 ms apart.
REACH_MS = 600

# a report this much later than the latest gaps between them is overdue
_OVERDUE_FACTOR = 1.25

# the gaps between reports gone by that say how far apart they come
_GAPS_KEPT = 6
# longer than this is no gap between reports but a stop: buffering, a pause
_GAP_MAX_S = 2 * REACH_MS / 1000

# past the mark: the loop's end is passed once the time is beyond it
_PAST_MS = 1


class TimeAhead(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        self._timer = QTimer(block)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._reached)

        self._due_ms: int | None = None
        # what it was aimed for, which a new video or a reload isn't
        self._aimed_at = None

        self._last_report_s: float | None = None
        self._gaps_s = collections.deque(maxlen=_GAPS_KEPT)

    def note_report(self) -> None:
        """A report from the player, which puts off what was aimed for."""

        self.cancel()

        now = time.monotonic()

        if self._last_report_s is not None:
            gap = now - self._last_report_s
            if gap <= _GAP_MAX_S:
                self._gaps_s.append(gap)

        self._last_report_s = now

    def forget_reports(self) -> None:
        """Another video, or the same one played anew: it reports afresh."""

        self.cancel()
        self._last_report_s = None
        self._gaps_s.clear()

    def aim(self) -> None:
        """After a report that changed nothing: wait for the next mark, if it
        comes before the next report would."""

        self.cancel()

        block = self._block
        params = block.video_params

        if params.is_paused or block.is_seek_on_its_way:
            return

        # how far apart they come isn't known yet
        if not self._gaps_s:
            return

        due = self._next_mark()
        if due is None:
            return

        wait_ms = (due - block.time) / params.rate
        if wait_ms > REACH_MS:
            return

        self._due_ms = due
        self._aimed_at = (params, block.video_driver)
        self._timer.start(max(0, round(wait_ms)))

    def cancel(self) -> None:
        self._timer.stop()
        self._due_ms = None
        self._aimed_at = None

    def _next_mark(self) -> int | None:
        block = self._block
        now = block.time

        marks = []

        # one the viewer set: the video's own end has an event of its own
        if block.video_params.loop_end is not None and now <= block.loop_end:
            marks.append(block.loop_end + _PAST_MS)

        skip_start = block.sponsorblock.next_skip_start(now)
        if skip_start is not None:
            marks.append(skip_start + _PAST_MS)

        return min(marks, default=None)

    def _is_report_overdue(self) -> bool:
        if self._last_report_s is None or not self._gaps_s:
            return True

        since = time.monotonic() - self._last_report_s

        return since > max(self._gaps_s) * _OVERDUE_FACTOR

    def _reached(self) -> None:
        due, aimed_at = self._due_ms, self._aimed_at
        self.cancel()

        block = self._block

        if due is None or not block.is_video_initialized:
            return

        params, driver = aimed_at
        if params is not block.video_params or driver is not block.video_driver:
            return

        if block.video_params.is_paused or block.is_seek_on_its_way:
            return

        # stopped to buffer, it may be: the report says when it's there
        if self._is_report_overdue():
            return

        block.reach_time(due)
