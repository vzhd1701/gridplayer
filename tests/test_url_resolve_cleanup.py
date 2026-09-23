"""Letting go of a URL resolver that is still in the middle of a resolve.

Closing a video used to wait for its resolve to finish, and yt-dlp on a
slow host can take many seconds, all of them with the app frozen.
"""

import threading
import time

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.stream import Stream, Streams
from gridplayer.utils.url_resolve import url_resolve
from gridplayer.utils.url_resolve.static import ResolvedVideo
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolver

RESOLVE_URL = "gridplayer.utils.url_resolve.url_resolve.resolve_url"

VIDEO = ResolvedVideo(
    title="t",
    is_live=False,
    streams=Streams({"best": Stream(url="http://video", protocol="direct")}),
)

TIMEOUT_SEC = 5


def _process_events_until(condition) -> bool:
    deadline = time.monotonic() + TIMEOUT_SEC

    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)

    return False


def _resolver():
    resolver = VideoURLResolver()

    events = []

    resolver.url_resolved.connect(lambda video: events.append(("resolved", video)))
    resolver.error.connect(lambda: events.append(("error", None)))

    return resolver, events


@pytest.fixture
def slow_resolve(mocker):
    """A resolve that holds on until the test lets it go."""

    started = threading.Event()
    release = threading.Event()

    def _resolve(url, on_status=None):
        started.set()
        release.wait(TIMEOUT_SEC)
        return VIDEO

    mocker.patch(RESOLVE_URL, side_effect=_resolve)

    yield started, release

    release.set()


def test_a_resolved_url_is_handed_over(mocker):
    mocker.patch(RESOLVE_URL, return_value=VIDEO)

    resolver, events = _resolver()

    resolver.resolve("http://page")

    assert _process_events_until(lambda: events)
    assert events == [("resolved", VIDEO)]

    resolver.cleanup()

    assert resolver.thread.isFinished()


def test_cleanup_does_not_wait_for_a_resolve_in_progress(slow_resolve):
    started, release = slow_resolve

    resolver, events = _resolver()
    thread = resolver.thread

    resolver.resolve("http://page")
    assert started.wait(TIMEOUT_SEC)

    began = time.monotonic()
    resolver.cleanup()

    assert time.monotonic() - began < 1
    assert thread.isRunning()

    release.set()

    assert _process_events_until(lambda: not url_resolve._abandoned)
    assert thread.isFinished()

    # the video it was resolving for is gone, nobody wants the answer
    assert not events


def test_cleanup_twice_is_harmless(slow_resolve):
    started, release = slow_resolve

    resolver, _ = _resolver()

    resolver.resolve("http://page")
    assert started.wait(TIMEOUT_SEC)

    resolver.cleanup()
    resolver.cleanup()

    release.set()

    assert _process_events_until(lambda: not url_resolve._abandoned)
