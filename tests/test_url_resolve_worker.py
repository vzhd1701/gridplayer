"""What the URL resolver worker reports back for each kind of outcome."""

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.stream import Stream, Streams
from gridplayer.utils.url_resolve.static import (
    BadURLException,
    PlaylistURLError,
    ResolvedVideo,
    StreamOfflineError,
)
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolverWorker

RESOLVE_URL = "gridplayer.utils.url_resolve.url_resolve.resolve_url"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _worker():
    worker = VideoURLResolverWorker()

    resolved = []
    errors = []

    worker.url_resolved.connect(resolved.append)
    worker.error.connect(lambda: errors.append(True))

    return worker, resolved, errors


def test_a_resolved_url_is_handed_over(mocker):
    video = ResolvedVideo(
        title="t",
        is_live=False,
        streams=Streams({"best": Stream(url="http://video", protocol="direct")}),
    )

    mocker.patch(RESOLVE_URL, return_value=video)

    worker, resolved, errors = _worker()

    worker.resolve("http://page")

    assert resolved == [video]
    assert not errors


def test_a_url_nobody_could_resolve_is_reported_as_an_error(mocker):
    """No resolver claimed the URL.

    Handing that on as a resolved video raises on the way out of the worker
    thread, which used to leave the video sitting on "loading" for good.
    """

    mocker.patch(RESOLVE_URL, return_value=None)

    worker, resolved, errors = _worker()

    worker.resolve("http://page")

    assert not resolved
    assert errors


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(StreamOfflineError(), id="offline"),
        pytest.param(BadURLException("bad"), id="bad_url"),
        pytest.param(PlaylistURLError(), id="playlist"),
        pytest.param(RuntimeError("boom"), id="unexpected"),
    ],
)
def test_a_failed_resolve_is_reported_as_an_error(error, mocker):
    mocker.patch(RESOLVE_URL, side_effect=error)

    worker, resolved, errors = _worker()

    worker.resolve("http://page")

    assert not resolved
    assert errors


class TestAListTheLinkTurnsOutToBe:
    def _reading(self, mocker, counts):
        def resolve(url, headers=None, progress=None, **kwargs):
            for count in counts:
                progress("items", count)
            return None

        mocker.patch(RESOLVE_URL, side_effect=resolve)

    def test_how_far_it_is_read_said(self, mocker):
        self._reading(mocker, [1200])
        worker, _, _ = _worker()
        said = []
        worker.reading.connect(said.append)

        worker.resolve("http://page")

        assert said[0] == "Reading the list… 1,200 items"

    def test_read_no_further_once_the_video_is_let_go_of(self, mocker):
        self._reading(mocker, [1, 2])
        worker, resolved, errors = _worker()
        said = []
        worker.reading.connect(said.append)
        worker.stop.set()

        worker.resolve("http://page")

        assert said == []
        assert not resolved
        assert not errors
