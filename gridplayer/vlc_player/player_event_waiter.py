import logging
import threading
from functools import partial
from typing import Optional

from gridplayer.vlc_player.player_event_manager import EventManager


class EventWaiter(object):
    events = [
        "buffering",
        "paused",
        "snapshot_taken",
        "stopped",
        "time_changed",
        "vout",
    ]
    oneshot_events = ["vout"]

    default_timeout = 5

    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)

        self._is_abort = False

        self._wait_event = None
        self._wait_timeout = self.default_timeout

        self._events = {state: threading.Event() for state in self.events}
        self._async_wait_thread = None

    def __enter__(self):
        self._clear()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._wait()

    def subscribe(self, event_manager: EventManager):
        for event_name in self.events:
            callback = getattr(self, f"_cb_{event_name}", None)
            if callback is None:
                callback = partial(self._cb_generic, event_name)

            event_manager.subscribe(event_name, callback)

    def waiting_for(self, event: str, timeout: Optional[int] = None):
        """Context manager"""

        if event not in self.events:
            raise ValueError(f"Event type not supported: {event}")

        self._wait_event = event
        self._wait_timeout = timeout or self.default_timeout

        return self

    def wait_for(self, event: str, timeout: Optional[int] = None):
        self._clear()

        self.waiting_for(event, timeout)

        self._wait()

    def async_wait_for(self, event, on_completed, on_timeout, timeout=None):
        self._clear()

        self.waiting_for(event, timeout)

        self._async_wait_thread = threading.Thread(
            target=self._async_wait,
            args=(on_completed, on_timeout),
        )
        self._async_wait_thread.start()

    def abort(self):
        self._log.debug("Aborting waiter")

        self._is_abort = True

        for event in self._events.values():
            event.set()

        if self._async_wait_thread is not None:
            self._async_wait_thread.join()
            self._async_wait_thread = None

    def _wait(self):
        self._log.debug(f"Waiting for {self._wait_event}")

        res = self._events[self._wait_event].wait(self._wait_timeout)
        if not res:
            self._log.error(
                f"Waiting for {self._wait_event} timed out"
                f" after {self._wait_timeout} seconds"
            )
            raise TimeoutError

    def _async_wait(self, on_completed, on_timeout):
        try:
            self._wait()
        except TimeoutError:
            on_timeout()
            return

        if self._is_abort:
            return

        on_completed()

    def _clear(self):
        for event_name, event in self._events.items():
            if event_name not in self.oneshot_events:
                event.clear()

    def _cb_generic(self, event_name, event):
        if not self._events[event_name].is_set():
            if event_name == self._wait_event:
                self._log.debug(f"Waiter event set: {event_name}")

            self._events[event_name].set()

    def _cb_buffering(self, event):
        buffered_percent = int(event.u.new_cache)

        if buffered_percent == 100 and not self._events["buffering"].is_set():
            self._log.debug(f"Buffered {buffered_percent}%")

            self._events["buffering"].set()

    def _cb_time_changed(self, event):
        new_time = int(event.u.new_time)

        if new_time > 0 and not self._events["time_changed"].is_set():
            self._log.debug("Time started")

            self._events["time_changed"].set()


def async_timer(time, callback):
    return threading.Timer(time, callback)


def async_wait(time, callback):
    timer = threading.Timer(time, callback)
    timer.start()
    return timer
