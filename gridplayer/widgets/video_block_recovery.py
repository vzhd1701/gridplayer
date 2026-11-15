"""What a video block does when its video will not play: tries a network
video again a while later, and goes on past an item of its list that
failed, to the next one. And when one that was playing stops, or starts
over long before its end, which neither player says.

Showing what went wrong is the block's (see VideoBlock.network_error and
VideoBlock.error); this only decides what comes after, and when.
"""

import time

from PyQt5.QtCore import Qt, QTimer

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput
from gridplayer.params.static import (
    MAX_LIST_FAIL_WAIT_SEC,
    ListFailAction,
    NetworkRetryMode,
    VideoEndAction,
)
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.widgets.video_block_guards import VideoBlockPart
from gridplayer.widgets.video_status import LoadStage

MAX_NETWORK_RETRIES = 1000

# how long to wait before trying a failed network video again. A host that
# just turned us away is unlikely to change its mind within a second, and
# retrying forever at full speed would be indistinguishable from an attack
NETWORK_RETRY_DELAYS_S = (1, 2, 5, 15, 30)

# how many items of a list in a row may fail for the network, or a site
# turning requests away, before it is left at that
MAX_NETWORK_FAILURES_IN_A_ROW = 10

# A network video playing that stops moving is told by nothing: its link refused
# from then on, VLC tries again once a minute and MPV plays out what it has, the
# picture held and no word of it. With the proxy having been turned away fetching
# it, it's tried again this soon; with nothing said of why, after the buffering
# timeout of the settings.
STALL_CHECK_MS = 1000
STALLED_AFTER_FAILURE_S = 10

# Moving is a second of it in a second, at its rate: VLC stuck on a file whose
# connection was cut crept on, 1.8 s in two minutes.
STALL_MOVE_MS = 1000

# where it stops of itself: the end, the end action left to the block
STALL_END_MARGIN_MS = 1000

# Or it starts over by itself, short of the end: a YouTube video VLC had a minute
# of, the next bit refused, was played from the start again, the minute over and
# over, and a file whose connection was cut, opened again, from 2.6 s. Back to this
# near the start, by this much, with no seek on its way and this far from the end.
CUT_SHORT_START_MS = 5000
CUT_SHORT_JUMP_MS = 5000
CUT_SHORT_END_MARGIN_MS = 10_000

# How long a video loaded again has to play before the reloads it took are
# forgotten. Loading is no proof: VLC loaded a YouTube video at the minute it was
# refused past, and started over at once, every 7 s for as long as it was let.
PLAYED_ON_MS = 30_000

# what one time report on from the last can be and still be playing, not a seek
PLAYED_STEP_MS = 2000


def list_fail_wait_txt(wait_sec: int) -> str:
    if not wait_sec:
        return translate("When Video Fails", "At once")

    return translate("When Video Fails", "{SECONDS} s").format(SECONDS=wait_sec)


class RecoveryControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # reloads of the video tried so far, and the one counted down to:
        # how long is left of the wait, and how long it was
        self._retries = 0
        self._countdown = 0
        self._delay = 0

        self._retry_timer = QTimer(block)
        self._retry_timer.setInterval(1000)
        self._retry_timer.timeout.connect(self._retry_tick)

        # items of the list that would not play, one after the other: a
        # list that has none that will is not gone round for ever; and of
        # them, the ones that failed for the network or a site refusing
        self._failures_in_a_row = 0
        self._network_failures_in_a_row = 0

        self._skip_timer = QTimer(block)
        self._skip_timer.setSingleShot(True)
        self._skip_timer.setTimerType(Qt.PreciseTimer)
        self._skip_timer.timeout.connect(self._skip)

        # the note under a failed item's card counting down to the next one;
        # precise, as the wait it counts down: a coarse timer on Linux runs
        # up to 5% long, and 2 s left said "3 s"
        self._note_timer = QTimer(block)
        self._note_timer.setTimerType(Qt.PreciseTimer)
        self._note_timer.setInterval(1000)
        self._note_timer.timeout.connect(self.refresh_skip_note)

        # where the time last moved from, and when, for as long as it is watched;
        # where it was last, and where it got to before it started over, told once
        self._moved_from_ms = 0
        self._moved_at = 0.0
        self._last_time_ms = 0
        self._cut_short_at_ms: int | None = None

        # how much of it has played since it was loaded
        self._played_ms = 0

        self._stall_timer = QTimer(block)
        self._stall_timer.setInterval(STALL_CHECK_MS)
        self._stall_timer.timeout.connect(self._check_stall)

    @property
    def retries(self) -> int:
        """Reloads tried since the video last played on for a while."""

        return self._retries

    def note_played(self):
        """The video plays: the list is not one without anything that will. The
        reloads it took are forgotten once it has played on, see PLAYED_ON_MS."""

        self._failures_in_a_row = 0
        self._network_failures_in_a_row = 0

    def stop(self):
        """Count down to nothing: the block is letting its player go."""

        self._retry_timer.stop()
        self._skip_timer.stop()
        self._stall_timer.stop()

    def watch_stalls(self):
        """The video has just loaded: watched from where it is, for it stopping
        or starting over."""

        self._last_time_ms = self._block.time
        self._cut_short_at_ms = None
        self._played_ms = 0

        self._moved_from(self._block.time)

    def note_time(self, time_ms: int):
        """Where the video is now, before a seek on its way is let go of: a move
        if it's a second on or a jump."""

        last_time_ms, self._last_time_ms = self._last_time_ms, time_ms

        if self._has_started_over(last_time_ms, time_ms):
            self._cut_short_at_ms = last_time_ms
            self._stall_timer.stop()

            self._block._log.debug(f"Started over at {time_ms}, from {last_time_ms}")

            # not from in here: the driver reports the time, and the error lets it go
            QTimer.singleShot(0, self._tell_cut_short)
            return

        rate = self._block.video_params.rate

        if 0 < time_ms - last_time_ms <= PLAYED_STEP_MS * rate:
            self._played_ms += time_ms - last_time_ms

            if self._played_ms >= PLAYED_ON_MS:
                self._retries = 0

        if abs(time_ms - self._moved_from_ms) >= STALL_MOVE_MS * rate:
            self._moved_from(time_ms)

    def _has_started_over(self, last_time_ms: int, time_ms: int) -> bool:
        block = self._block

        return (
            self._cut_short_at_ms is None
            and self._is_stall_watched()
            and not block.is_seek_on_its_way
            and time_ms < CUT_SHORT_START_MS
            and last_time_ms - time_ms >= CUT_SHORT_JUMP_MS
            and last_time_ms < block.video_driver.length - CUT_SHORT_END_MARGIN_MS
        )

    def _tell_cut_short(self):
        if not self._is_stall_watched():
            return

        # loaded again from where it got to, not from where it started over
        self._block.video_params.current_position = self._cut_short_at_ms

        # marked for translation where the players say it
        self._block.video_driver_error("Video stopped unexpectedly")

    def _moved_from(self, time_ms: int):
        self._moved_from_ms = time_ms
        self._moved_at = time.monotonic()

        if not self._stall_timer.isActive():
            self._stall_timer.start()

    def _check_stall(self):
        block = self._block

        if self._is_sound_lost():
            self._stall_timer.stop()

            block._log.debug("The sound's link failed")

            # loaded again, with links fresh, as for a failed video: the alternative
            # was the picture playing on without a word, the sound gone
            block.video_driver_error(translate("Video Error", "Can't play the sound"))
            return

        if not self._is_stall_watched():
            self._stall_timer.stop()
            return

        # held by the viewer, or where it stops anyway: from when it goes on
        if block.video_params.is_paused or block.time >= (
            block.loop_end - STALL_END_MARGIN_MS
        ):
            self._moved_at = time.monotonic()
            return

        stalled_s = time.monotonic() - self._moved_at

        # turned away fetching it since it loaded: the next bit of it, most
        # likely, the link of no more use
        if block.stream.proxy_failure() is not None:
            is_stalled = stalled_s >= STALLED_AFTER_FAILURE_S
        else:
            is_stalled = stalled_s >= Settings().get("network/buffering_timeout")

        if not is_stalled:
            return

        self._stall_timer.stop()

        block._log.debug(f"Stopped moving at {block.time} for {stalled_s:.0f} s")

        # what the proxy was told goes with it, see VideoBlockStatus.player_error;
        # marked for translation where the players say it
        block.video_driver_error("Buffering timeout")

    def _is_sound_lost(self) -> bool:
        block = self._block

        return (
            block.video_driver is not None
            and block.is_video_initialized
            and not block.is_error
            and not block.is_stopped
            and block.stream.sound_failure() is not None
        )

    def _is_stall_watched(self) -> bool:
        """A network video playing, of a length: a live stream's time is no
        measure (see VLC's cb_playing), and the drivers wait on it themselves
        after a pause."""

        block = self._block

        return (
            block.video_driver is not None
            and block.is_video_initialized
            and not block.is_error
            and not block.is_stopped
            and not block.is_live
            and not block.video_params.is_local_file
            # with none known, there is no telling the end from a stop
            and block.video_driver.length > 0
        )

    def stop_retry_countdown(self):
        """The reload counted down to is being made now, the tries kept."""

        self._retry_timer.stop()

    @property
    def is_skip_counting(self) -> bool:
        return self._skip_timer.isActive()

    def stop_skip(self):
        """Go on to no other item: the viewer did something else."""

        self._skip_timer.stop()

    def stop_skip_note(self):
        self._note_timer.stop()

    def skip_note(self) -> str:
        if not self._skip_timer.isActive():
            return self._given_up_txt()

        if self._skip_timer.interval() == 0:
            return ""

        seconds = max(1, -(-self._skip_timer.remainingTime() // 1000))

        if self.is_going_back:
            return translate("Video Status", "Previous file in {SECONDS} s").format(
                SECONDS=seconds
            )

        return translate("Video Status", "Next file in {SECONDS} s").format(
            SECONDS=seconds
        )

    def refresh_skip_note(self):
        if not self._skip_timer.isActive():
            self._note_timer.stop()

        if self._block.is_error and self._block.status.last_error is not None:
            self._block.video_status.show_error(
                self._block.status.last_error, self.skip_note()
            )

    def schedule_retry(self) -> bool:
        """Try the video again later instead of giving up on it.

        Streams break for reasons that pass: a host hiccups, a laptop wakes
        up with no network yet, a signed URL runs out. Showing the error is
        the last resort, not the first answer.
        """

        retry_limit = self.retry_limit

        if retry_limit == 0:
            return False

        if retry_limit > 0 and self._retries >= retry_limit:
            self._block._log.debug(f"Giving up after {self._retries} retries")
            return False

        self._retries += 1

        delay_idx = min(self._retries - 1, len(NETWORK_RETRY_DELAYS_S) - 1)
        self._countdown = NETWORK_RETRY_DELAYS_S[delay_idx]
        self._delay = self._countdown

        self._block._log.debug(
            f"Network error, retry {self._retries} in {self._countdown}s"
        )

        self._block._is_error = False
        self._block._is_state_change_in_progress = False

        # the driver is of no use until the video is loaded again, and
        # holding on to it keeps a VLC player busy for the whole wait
        self._block.cleanup()

        self._block.status.load_stage = LoadStage.RECONNECT
        self._block.status.show("processing")
        self._show_retry_status()

        self._retry_timer.start()

        return True

    def drop_retries(self):
        self._retry_timer.stop()
        self._retries = 0

    def _retry_tick(self):
        self._countdown -= 1

        if self._countdown > 0:
            self._show_retry_status()
            return

        self._retry_timer.stop()

        if self._block.is_closing or self._block.video_params is None:
            return

        self._block.reload()

    def _show_retry_status(self):
        detail = self._attempt_txt

        # what went wrong the last time, in short
        error = self._block.status.last_error

        if error is not None and (error.where or error.code):
            tag = " ".join(part for part in (error.where, error.code) if part)
            detail = f"{detail} · {tag}"

        self._block.video_status.show_reconnect(self._countdown, self._delay, detail)

    @property
    def _attempt_txt(self) -> str:
        retry_limit = self.retry_limit

        if retry_limit < 0:
            return translate("Video Status", "Try {ATTEMPT}").format(
                ATTEMPT=self._retries
            )

        return translate("Video Status", "Try {ATTEMPT} of {LIMIT}").format(
            ATTEMPT=self._retries, LIMIT=retry_limit
        )

    @property
    def can_skip(self) -> bool:
        media_list = self._block.media_list

        return media_list is not None and len(media_list.items) > 1

    @property
    def is_going_back(self) -> bool:
        # on to the item before, at the end of each: Next, and the count
        # down to it, go back
        return (
            self._block.video_params is not None
            and self._block.video_params.end_action == VideoEndAction.PREVIOUS_FILE
        )

    def skip_now(self):
        """On to the item that comes next, now rather than in a moment: the
        way the list goes by itself where it does, at its end as well."""

        self._skip_timer.stop()

        if self._block.is_closing or self._block.media_list is None:
            return

        if not self._block._step_at_end(self._block.video_params.end_action):
            self._block.navigation.next()

    def set_retry_mode(self, mode):
        self._block.video_params.network_retry_mode = mode

        # a new policy starts with a full budget rather than what is left
        self._retries = 0

        if not self._retry_timer.isActive():
            return

        if self.retry_limit != 0:
            return

        # the reload this video was counting down to has just been called off
        self._retry_timer.stop()
        self._block.network_error()

    def retry_times_dialog(self):
        times = QCustomSpinboxInput.get_int(
            parent=self._block.parent(),
            title=translate(
                "Dialog - Set reload attempts", "Set reload attempts", "Header"
            ),
            initial_value=self._block.video_params.network_retry_times,
            _min=1,
            _max=MAX_NETWORK_RETRIES,
        )

        self._block.video_params.network_retry_times = times

        self._retries = 0

    def get_retry_times(self):
        return str(self._block.video_params.network_retry_times)

    @property
    def retry_limit(self) -> int:
        """How many times this video may be reloaded, -1 for no limit."""

        if self._block.video_params is None:
            return 0

        mode = self._block.video_params.network_retry_mode

        if mode == NetworkRetryMode.INFINITE:
            return -1

        if mode == NetworkRetryMode.TIMES:
            return max(self._block.video_params.network_retry_times, 0)

        return 0

    def set_fail_action(self, list_fail_action: ListFailAction):
        """What to do when an item of the list won't play. Kept for a cell
        with no list too, for when it has one."""

        self._block.video_params.list_fail_action = list_fail_action

        self._restart_skip_count()

    def fail_wait_dialog(self):
        wait_sec = QCustomSpinboxInput.get_int(
            parent=self._block.parent(),
            title=translate("When Video Fails", "Play next after (sec)"),
            special_text=translate("When Video Fails", "At once"),
            initial_value=self._block.video_params.list_fail_wait_sec,
            _min=0,
            _max=MAX_LIST_FAIL_WAIT_SEC,
            cancel_value=None,
        )

        if wait_sec is not None:
            self.set_fail_wait(wait_sec)

    def set_fail_wait(self, wait_sec: int):
        self._block.video_params.list_fail_wait_sec = wait_sec

        self._restart_skip_count()

    def get_fail_wait(self) -> str:
        return list_fail_wait_txt(self._block.video_params.list_fail_wait_sec)

    def schedule_skip(self):
        """Go on to the next item of the list in a moment, where this one
        will not play and the cell is set to.

        Not for ever: a list on which nothing plays is gone round once, and
        one that fails for the network or a site refusing is left sooner.
        """

        if self._block.media_list is None or self._block.is_closing:
            return

        self._failures_in_a_row += 1

        if not self._is_item_dead:
            self._network_failures_in_a_row += 1

        if self._is_skipped:
            self.start_skip_count()

    @property
    def _is_item_dead(self) -> bool:
        """Failed for itself: a file that won't play, or a server that
        answered it has nothing there. Not the network down or a site
        turning requests away, which the next item would fail for too."""

        if self._block.video_params.is_local_file:
            return True

        error = self._block.status.last_error

        return error is not None and not error.is_retryable and not error.is_refused

    def _given_up_txt(self) -> str:
        """Why the list no longer goes on past the item failed, if it
        doesn't."""

        media_list = self._block.media_list

        if (
            media_list is None
            or self._block.video_params is None
            or self._block.video_params.list_fail_action != ListFailAction.PLAY_NEXT
        ):
            return ""

        # so many in a row is the network, or a site turning every one of
        # them away, rather than the videos: asking again for one after the
        # other only makes a site that limits how often it is asked say no
        # for longer
        if self._network_failures_in_a_row > MAX_NETWORK_FAILURES_IN_A_ROW:
            return translate("Video Status", "Stopped: {COUNT} failed in a row").format(
                COUNT=self._failures_in_a_row
            )

        if self._failures_in_a_row > len(media_list.items):
            return translate("Video Status", "Stopped: nothing on the list plays")

        return ""

    @property
    def _is_skipped(self) -> bool:
        if self._block.media_list is None or self._block.is_closing:
            return False

        if self._block.video_params.list_fail_action != ListFailAction.PLAY_NEXT:
            return False

        return not self._given_up_txt()

    @property
    def is_reload_futile(self) -> bool:
        """An item that never played, failing for what a reload would only
        be told again, where the next one is to be played instead."""

        error = self._block.status.last_error

        return (
            error is not None
            and not error.is_retryable
            and not self._block._has_item_played
            and self._is_skipped
        )

    def start_skip_count(self):
        self._skip_timer.start(self._block.video_params.list_fail_wait_sec * 1000)

        if self._skip_timer.interval() > 0:
            self._note_timer.start()

    def _restart_skip_count(self):
        """The count to the next item after a failed one, once what is done
        then was changed: started over, or called off."""

        if not self._block.is_error:
            return

        if self._is_skipped:
            self.start_skip_count()
        else:
            self._skip_timer.stop()

        self.refresh_skip_note()

    def _skip(self):
        if self._block.is_closing or self._block.media_list is None:
            return

        # along the list the way it goes by itself; on to the next where it
        # doesn't
        if not self._block._step_at_end(self._block.video_params.end_action):
            self._block.navigation.next(is_end=True)
