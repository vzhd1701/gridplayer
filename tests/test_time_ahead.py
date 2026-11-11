"""A mark due before the next time report is acted on the moment it's
reached: the loop's end and SponsorBlock's skips, see TimeAhead."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QObject

from gridplayer.utils.sponsorblock import SkipSpan
from gridplayer.widgets import video_block_time_ahead
from gridplayer.widgets.video_block_sponsorblock import SponsorBlockControl
from gridplayer.widgets.video_block_time_ahead import TimeAhead


class _Block(QObject):
    """What TimeAhead reads of a block, as a QObject for its timer."""

    def __init__(self, time=0, loop_end=None, rate=1.0, skip_start=None):
        super().__init__()

        self.time = time
        self.video_params = SimpleNamespace(
            is_paused=False, rate=rate, loop_end=loop_end
        )
        self.video_driver = object()
        self.is_seek_on_its_way = False
        self.is_video_initialized = True
        self.sponsorblock = Mock(next_skip_start=Mock(return_value=skip_start))
        self.reach_time = Mock()

    @property
    def loop_end(self):
        end = self.video_params.loop_end
        return 30_000 if end is None else end


class _Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(video_block_time_ahead, "time", fake)
    return fake


def _reported(block, clock, gaps_s=(0.2, 0.2)):
    """Reports this far apart, the last one just now."""

    ahead = TimeAhead(block)
    ahead.note_report()
    for gap in gaps_s:
        clock.now += gap
        ahead.note_report()
    return ahead


def _aimed(block, clock, gaps_s=(0.2, 0.2)):
    ahead = _reported(block, clock, gaps_s)
    ahead.aim()
    return ahead


def _goes_off(ahead, clock, after_s):
    clock.now += after_s
    ahead._timer.timeout.emit()


def test_the_loops_end_is_reached_when_due(clock):
    ahead = _aimed(_Block(time=2_900, loop_end=3_000), clock)

    assert ahead._timer.isActive()
    assert ahead._timer.interval() == 101

    _goes_off(ahead, clock, 0.101)

    ahead._block.reach_time.assert_called_once_with(3_001)


@pytest.mark.parametrize(
    ("time", "rate", "is_aimed"),
    [(2_400, 1.0, False), (2_000, 2.0, True)],
)
def test_as_far_as_the_next_report_could_be(clock, time, rate, is_aimed):
    ahead = _aimed(_Block(time=time, loop_end=3_000, rate=rate), clock)

    assert ahead._timer.isActive() is is_aimed


def test_the_videos_own_end_has_an_event_of_its_own(clock):
    assert not _aimed(_Block(time=29_900), clock)._timer.isActive()


def test_a_skip_coming_first(clock):
    ahead = _aimed(_Block(time=2_900, loop_end=3_000, skip_start=2_950), clock)

    _goes_off(ahead, clock, 0.051)

    ahead._block.reach_time.assert_called_once_with(2_951)


def test_not_before_reports_say_how_far_apart_they_come(clock):
    assert not _aimed(
        _Block(time=2_900, loop_end=3_000), clock, gaps_s=()
    )._timer.isActive()


@pytest.mark.parametrize("state", ["is_paused", "is_seek_on_its_way"])
def test_nothing_while_paused_or_seeking(clock, state):
    block = _Block(time=2_900, loop_end=3_000)
    if state == "is_paused":
        block.video_params.is_paused = True
    else:
        block.is_seek_on_its_way = True

    assert not _aimed(block, clock)._timer.isActive()


def test_paused_since_it_was_aimed(clock):
    block = _Block(time=2_900, loop_end=3_000)
    ahead = _aimed(block, clock)

    block.video_params.is_paused = True
    _goes_off(ahead, clock, 0.101)

    block.reach_time.assert_not_called()


def test_a_late_report_may_be_buffering(clock):
    """Reports 200 ms apart, and none for 500: it may have stopped to buffer,
    and where it would be by now isn't where it is."""

    block = _Block(time=2_500, loop_end=3_000)
    ahead = _aimed(block, clock)

    _goes_off(ahead, clock, 0.501)

    block.reach_time.assert_not_called()


def test_reports_far_apart_are_waited_for_as_far(clock):
    """VLC's, at times 500 ms apart."""

    block = _Block(time=2_500, loop_end=3_000)
    ahead = _aimed(block, clock, gaps_s=(0.25, 0.5, 0.25))

    _goes_off(ahead, clock, 0.501)

    block.reach_time.assert_called_once_with(3_001)


def test_a_pause_is_no_gap_between_reports(clock):
    block = _Block(time=2_500, loop_end=3_000)
    ahead = _reported(block, clock, gaps_s=(0.2, 5.0, 0.2))
    ahead.aim()

    _goes_off(ahead, clock, 0.501)

    block.reach_time.assert_not_called()


def test_not_on_another_video(clock):
    block = _Block(time=2_900, loop_end=3_000)
    ahead = _aimed(block, clock)

    block.video_driver = object()
    _goes_off(ahead, clock, 0.101)

    block.reach_time.assert_not_called()


def test_forgotten_with_the_video(clock):
    block = _Block(time=2_900, loop_end=3_000)
    ahead = _aimed(block, clock)

    ahead.forget_reports()

    assert not ahead._timer.isActive()
    ahead.aim()
    assert not ahead._timer.isActive()


def test_a_report_puts_it_off(clock):
    block = _Block(time=2_900, loop_end=3_000)
    ahead = _aimed(block, clock)

    ahead.note_report()

    assert not ahead._timer.isActive()
    ahead._reached()
    block.reach_time.assert_not_called()


def _sponsorblock(spans, left_alone=None):
    part = SponsorBlockControl.__new__(SponsorBlockControl)
    part._skip_spans = tuple(spans)
    part._span_left_alone = left_alone
    return part


def test_the_next_skip_starts_after_the_time():
    first = SkipSpan(10_000, 13_000, "sponsor")
    second = SkipSpan(20_000, 22_000, "intro")

    assert _sponsorblock([second, first]).next_skip_start(9_000) == 10_000
    assert _sponsorblock([first, second]).next_skip_start(11_000) == 20_000
    assert _sponsorblock([first]).next_skip_start(13_000) is None


def test_one_left_alone_isnt_waited_for():
    span = SkipSpan(10_000, 13_000, "sponsor")

    assert _sponsorblock([span], left_alone=span).next_skip_start(9_000) is None


def _block_at(time_ms, loop_end):
    block = Mock(is_live=False, is_stopped=False, is_seek_on_its_way=False)
    block.time = time_ms
    block.loop_end = loop_end
    return block


def test_reached_the_loops_end_turns_back():
    from gridplayer.widgets.video_block import VideoBlock

    block = _block_at(2_900, 3_000)

    def seek_back():
        block.is_seek_on_its_way = True
        block.time = 2_000

    block.loop_end_action.side_effect = seek_back

    VideoBlock.reach_time(block, 3_001)

    block.loop_end_action.assert_called_once()
    assert block.time == 2_000


def test_reached_with_nothing_coming_of_it_keeps_the_players_time():
    """A skip too short to take, say: the time shown stays the reported one."""

    from gridplayer.widgets.video_block import VideoBlock

    block = _block_at(9_950, 30_000)

    VideoBlock.reach_time(block, 10_001)

    block.sponsorblock.skip_if_played_into.assert_called_once()
    assert block.time == 9_950
