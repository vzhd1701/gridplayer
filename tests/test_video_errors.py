"""Why a video would not play: told apart by where it broke, said on its
cell with the tag of it, and in full in its Details window."""

import dataclasses
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget
from yt_dlp.utils import DownloadError

from gridplayer.dialogs.error_details import ErrorDetailsDialog, details_txt
from gridplayer.models.media_list import ListItem, MediaList
from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.models.video import Video
from gridplayer.params.static import (
    ListFailAction,
    NetworkRetryMode,
    URLResolver,
    VideoEndAction,
    VideoInitialState,
)
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.list_errors import ReadErrorKind
from gridplayer.utils.stream_proxy.server import (
    ProxyRequestHandler,
    RelayFailure,
    StreamProxyServer,
    _proxy_failure,
)
from gridplayer.utils.url_resolve.static import (
    NoResolverPlugin,
    ResolverFailed,
    StreamOfflineError,
)
from gridplayer.utils.url_resolve.url_resolve import (
    VideoURLResolver,
    VideoURLResolverWorker,
)
from gridplayer.utils.video_errors import (
    ProxyFailure,
    ShownError,
    file_error,
    player_error,
    proxy_error,
    resolve_error,
    stream_offline_error,
)
from gridplayer.vlc_player import vlc_errors
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_overlay import OverlayMode
from gridplayer.widgets.video_status import LoadStage, StatusMode

RESOLVE_URL = "gridplayer.utils.url_resolve.url_resolve.resolve_url"
PICK_RESOLVERS = "gridplayer.utils.url_resolve.url_resolve._pick_resolvers"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _http_error(status: int, url="https://cdn.example/v.mp4") -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.url = url

    error = requests.HTTPError(f"{status} Client Error", response=response)

    # what requests' own errors carry, read the way list errors are
    error.status = status

    return error


SESSION = StreamSessionOpts(service="test", session_headers=HashableDict({}))

PLAYLIST = b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\n%s\n#EXT-X-ENDLIST\n"


class _Host(BaseHTTPRequestHandler):
    """Two videos of one service, the segment of one of them refused."""

    protocol_version = "HTTP/1.1"

    REPLIES = {
        "/refused.m3u8": (200, PLAYLIST % b"refused.ts"),
        "/refused.ts": (403, b"no"),
        "/fine.m3u8": (200, PLAYLIST % b"fine.ts"),
        "/fine.ts": (200, b"segment"),
    }

    def do_GET(self):
        status, body = self.REPLIES.get(self.path, (404, b"missing"))

        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


def _url_on(server, path):
    address, port = server.server_address
    return f"http://{address}:{port}{path}"


class TestFromAResolver:
    def test_an_http_answer_is_the_servers(self):
        error = resolve_error(_http_error(403), "https://site.example/watch?v=1")

        assert error.title == "Access denied"
        assert (error.where, error.code) == ("Server", "HTTP 403")
        assert error.code_full == "HTTP 403 Forbidden"
        assert error.host == "site.example"
        assert not error.is_network

    def test_a_host_not_found_is_the_networks(self):
        raised = requests.ConnectionError("Failed to resolve")
        raised.__cause__ = socket.gaierror("getaddrinfo failed")

        error = resolve_error(raised, "https://nowhere.example/v")

        assert error.title == "Server not found"
        assert (error.where, error.code) == ("Network", "DNS")
        assert "nowhere.example" in error.about
        assert error.is_network
        assert error.icon == "network-error"

    def test_the_whole_chain_told_in_the_details(self):
        raised = RuntimeError("could not fetch")
        raised.__cause__ = TimeoutError("read timed out")

        error = resolve_error(raised, "https://slow.example/v")

        assert "RuntimeError: could not fetch" in error.raw
        assert "TimeoutError: read timed out" in error.raw

    def test_anything_else_said_as_raised(self):
        error = resolve_error(ValueError("Unsupported URL"), "https://x.example/")

        assert error.title == "Couldn't find the video"
        assert error.about == "Unsupported URL"
        assert error.where == "Link"

    def test_a_private_video_is_not_found(self):
        # as YouTube says it, capital P and all
        raised = DownloadError(
            "ERROR: [youtube] abc: Private video. Sign in if you've been"
            " granted access to this video"
        )

        error = resolve_error(raised, "https://www.youtube.com/watch?v=abc")

        assert (error.title, error.about) == (
            "Not found",
            "It may be private or deleted.",
        )
        assert (error.where, error.code) == ("Server", "Unavailable")


class TestFromThePlayer:
    def test_an_http_status_vlc_was_given(self):
        error = player_error(
            "Failed to load media",
            ("http: HTTP 404 error", "main: Your input can't be opened"),
            url="https://cdn.example/v.mp4",
        )

        assert error.title == "Not found"
        assert (error.where, error.code) == ("Server", "HTTP 404")
        assert error.host == "cdn.example"
        assert "http: HTTP 404 error" in error.raw

    def test_otherwise_what_vlc_said_first(self):
        error = player_error(
            "Player error",
            ("main decoder: Codec `prores' is not supported", "main: other"),
        )

        assert error.title == "Player error"
        assert error.about == "Codec `prores' is not supported"
        assert (error.where, error.code) == ("Player", "VLC")

    def test_with_nothing_said_by_vlc(self):
        error = player_error("Video stopped before initialization")

        assert error.about == ""
        assert error.raw == "Video stopped before initialization"

    def test_a_file_gone(self, tmp_path):
        error = file_error(ReadErrorKind.MISSING, tmp_path / "gone.mp4")

        assert error.title == "File not found"
        assert (error.where, error.code) == ("File", "Missing")


class TestFromTheProxy:
    def test_what_the_server_answered(self):
        failure = ProxyFailure(
            url="https://cdn.example/seg1.ts", status=429, reason="Too Many Requests"
        )

        error = proxy_error(failure, ("http: HTTP 429 error",))

        assert error.title == "Too many requests"
        assert (error.where, error.code) == ("Server", "HTTP 429")
        assert error.code_full == "HTTP 429 Too Many Requests"
        assert error.host == "cdn.example"
        assert "http: HTTP 429 error" in error.raw

    def test_what_broke_on_the_way(self):
        failure = _proxy_failure(
            RelayFailure(error=ConnectionResetError("reset by peer")),
            "https://cdn.example/live.m3u8",
        )

        error = proxy_error(failure)

        assert (error.where, error.code) == ("Network", "Reset")
        assert "reset by peer" in error.raw

    def test_kept_for_the_video_whose_stream_it_was(self, serving):
        """Not for every video of the service: they share one session."""

        host = serving(ThreadingHTTPServer(("127.0.0.1", 0), _Host))
        proxy = serving(StreamProxyServer(("127.0.0.1", 0), ProxyRequestHandler))

        mine, theirs = (
            proxy.add_stream(
                Stream(url=_url_on(host, path), protocol="hls_proxy", session=SESSION)
            )
            for path in ("/refused.m3u8", "/fine.m3u8")
        )

        # the segment its playlist was served with, as VLC asks for it
        playlist = requests.get(mine, timeout=10).text
        segment = next(line for line in playlist.splitlines() if "://" in line)

        assert requests.get(segment, timeout=10).status_code == 403

        assert proxy.failure_of(mine).status == 403
        assert proxy.failure_of(theirs) is None


class TestWorthAReload:
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 429, 451])
    def test_not_what_a_server_turns_down_for_good(self, status):
        error = resolve_error(_http_error(status), "https://site.example/watch")

        assert not error.is_retryable

    @pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
    def test_what_a_server_may_answer_otherwise(self, status):
        error = resolve_error(_http_error(status), "https://site.example/watch")

        assert error.is_retryable

    def test_not_a_video_a_site_has_taken_down(self):
        error = resolve_error(
            DownloadError("ERROR: [youtube] abc: Private video"),
            "https://www.youtube.com/watch?v=abc",
        )

        assert not error.is_retryable

    def test_a_connection_that_failed(self):
        error = resolve_error(
            requests.ConnectionError("Connection aborted"), "https://site.example/v"
        )

        assert error.is_retryable

    def test_not_a_stream_with_nothing_on(self):
        assert not stream_offline_error("https://site.example/live").is_retryable

    def test_by_what_the_proxy_was_answered(self):
        refused = ProxyFailure(url="https://cdn.example/seg.ts", status=410)
        broken = _proxy_failure(
            RelayFailure(error=ConnectionResetError("reset by peer")),
            "https://cdn.example/live.m3u8",
        )

        assert not proxy_error(refused).is_retryable
        assert proxy_error(broken).is_retryable

    def test_by_what_vlc_was_answered(self):
        refused = player_error("Failed to load media", ("http: HTTP 404 error",))
        broken = player_error("Player error", ("main decoder: Codec not supported",))

        assert not refused.is_retryable
        assert broken.is_retryable

    def test_not_a_file_gone(self, tmp_path):
        assert not file_error(ReadErrorKind.MISSING, tmp_path / "a.mp4").is_retryable


class TestASiteRefusing:
    def test_too_many_requests(self):
        error = resolve_error(_http_error(429), "https://site.example/watch")

        assert error.is_refused

    def test_a_bot_check(self):
        error = resolve_error(
            DownloadError("ERROR: [youtube] abc: Sign in to confirm you're not a bot"),
            "https://www.youtube.com/watch?v=abc",
        )

        assert error.is_refused

    def test_too_many_requests_vlc_was_answered(self):
        error = player_error("Failed to load media", ("http: HTTP 429 error",))

        assert error.is_refused

    @pytest.mark.parametrize("status", [403, 404, 503])
    def test_not_what_else_a_server_answers(self, status):
        error = resolve_error(_http_error(status), "https://site.example/watch")

        assert not error.is_refused


class TestVLCSaid:
    @pytest.fixture(autouse=True)
    def _said(self, monkeypatch):
        monkeypatch.setattr(vlc_errors, "_said", type(vlc_errors._said)(maxlen=64))
        monkeypatch.setattr(vlc_errors, "_counted", {})
        monkeypatch.setattr(vlc_errors, "_heard", {})
        monkeypatch.setattr(vlc_errors, "_video_threads", set())

    def test_a_flood_kept_a_few_a_second(self, monkeypatch):
        """A stream gone bad says the same over and over, each put
        together to be kept: past a few a second, they are let be."""

        now = [100.0]
        monkeypatch.setattr(vlc_errors.time, "monotonic", lambda: now[0])

        kept = [vlc_errors.is_keeping_vlc_errors() for _ in range(50)]

        assert kept.count(True) == vlc_errors.KEPT_A_SECOND

        now[0] += 1

        assert vlc_errors.is_keeping_vlc_errors()

    def test_since_the_video_began_to_open(self):
        vlc_errors.keep_vlc_error("before")
        began = time.time()
        time.sleep(0.01)
        vlc_errors.keep_vlc_error("after")

        assert vlc_errors.vlc_errors_since(began, {threading.get_ident()}) == ["after"]

    def test_on_its_own_threads_alone(self):
        """One log for every video of the process: what VLC said on
        another video's threads is not this one's."""

        elsewhere = threading.Thread(target=vlc_errors.keep_vlc_error, args=["theirs"])
        elsewhere.start()
        elsewhere.join()
        vlc_errors.keep_vlc_error("mine")

        assert vlc_errors.vlc_errors_since(0, {threading.get_ident()}) == ["mine"]

    def test_the_last_few(self):
        for n in range(20):
            vlc_errors.keep_vlc_error(str(n))

        said = vlc_errors.vlc_errors_since(0, {threading.get_ident()})

        assert len(said) == vlc_errors.TOLD
        assert said[-1] == "19"

    def test_a_player_tells_what_was_said_on_its_video_s_threads(self):
        player = _Player()
        player._timeout_init_start = time.time() - 1

        # another video of the process, its thread still about
        theirs_said, mine_done = threading.Event(), threading.Event()

        def theirs():
            vlc_errors.keep_vlc_error("http: HTTP 403 error")
            theirs_said.set()
            mine_done.wait(10)

        def mine():
            vlc_errors.keep_vlc_error("http: HTTP 404 error")
            player._event_manager._notify_subscribers("encountered_error", None)

        other = threading.Thread(target=theirs)
        other.start()
        theirs_said.wait(10)

        own = threading.Thread(target=mine)
        own.start()
        own.join()

        mine_done.set()
        other.join()

        assert player.errors == [("Player error", ("http: HTTP 404 error",))]

    def test_once_it_plays_what_was_said_just_before(self):
        player = _Player()
        player._timeout_init_start = time.time() - 3600
        player._vlc_threads.add(threading.get_ident())
        player.is_video_initialized = True

        vlc_errors._said.append((time.time() - 3000, threading.get_ident(), 0, "old"))
        vlc_errors.keep_vlc_error("now")

        player.error("Video stopped unexpectedly")

        assert player.errors == [("Video stopped unexpectedly", ("now",))]

    def test_what_its_segments_fetched_elsewhere_said(self):
        """The segments of a stream are fetched on a thread of their own,
        that no event comes on, by an object that speaks on the video's
        threads as well."""

        demux = 0x7F01
        began = time.time()
        vlc_errors.note_video_thread()
        vlc_errors.note_vlc_object(demux)

        _on_a_thread(lambda: vlc_errors.keep_vlc_error("http: HTTP/1.1 403", demux))

        assert vlc_errors.vlc_errors_since(began, {threading.get_ident()}) == [
            "http: HTTP/1.1 403"
        ]

    def test_another_video_s_threads_left_to_it_whoever_speaks(self):
        """An object of the whole process, heard on this video's thread,
        says something on another video's: that is the other one's."""

        shared = 0x7F02
        vlc_errors.note_vlc_object(shared)

        def theirs():
            vlc_errors.note_video_thread()
            vlc_errors.keep_vlc_error("audio output: theirs", shared)

        _on_a_thread(theirs)

        assert vlc_errors.vlc_errors_since(0, {threading.get_ident()}) == []

    def test_an_object_heard_before_the_video_opened_left_out(self):
        """The ids of VLC's objects are used again once they are gone."""

        reused = 0x7F03
        vlc_errors.note_vlc_object(reused)
        time.sleep(0.01)
        opened_at = time.time()

        _on_a_thread(lambda: vlc_errors.keep_vlc_error("someone else's", reused))

        said = vlc_errors.vlc_errors_since(
            opened_at, {threading.get_ident()}, opened_at=opened_at
        )

        assert said == []

    def test_once_it_plays_its_objects_heard_since_it_opened(self):
        """Heard as it opened, long before what went wrong while it played."""

        demux = 0x7F04
        opened_at = time.time() - 600
        vlc_errors._heard[threading.get_ident()] = {demux: opened_at + 1}
        now = time.time()

        _on_a_thread(lambda: vlc_errors.keep_vlc_error("adaptive: gone", demux))

        said = vlc_errors.vlc_errors_since(
            now - 10, {threading.get_ident()}, opened_at=opened_at
        )

        assert said == ["adaptive: gone"]

    @pytest.mark.parametrize(
        ("fmt", "is_its_own"),
        [
            (b"INPUT_CONTROL_SET_POSITION %2.1f%% failed", True),
            (b"HTTP %d error", False),
            (None, False),
        ],
    )
    def test_what_vlc_says_of_itself_told_apart(self, fmt, is_its_own):
        """Rewinding a dead stream, each time :input-repeat starts it over:
        thousands of times a second, of nothing but VLC's own doing."""

        assert vlc_errors.is_said_of_vlc_itself(fmt) is is_its_own

    @pytest.mark.parametrize(
        ("said", "refusal"),
        [
            (
                "http: incoming response:\nHTTP/1.0 403 Forbidden\nServer: x",
                "http: HTTP/1.0 403 Forbidden",
            ),
            (
                "http: incoming response:\nHTTP/1.1 503 Service Unavailable\n",
                "http: HTTP/1.1 503 Service Unavailable",
            ),
            ("http: incoming response:\nHTTP/1.1 200 OK\nServer: x", None),
            ("http: incoming response:\nHTTP/2 404 \n", "http: HTTP/2 404"),
        ],
    )
    def test_a_server_turning_vlc_away(self, said, refusal):
        assert vlc_errors.is_http_answer(b"incoming response:\n%s")
        assert vlc_errors.http_refusal(said) == refusal

    def test_a_server_turning_vlc_away_tells_the_card(self):
        error = player_error(
            "Video stopped before initialization",
            ("http: HTTP/1.1 403 Forbidden", "adaptive: Failed to create demuxer"),
        )

        assert (error.where, error.code) == ("Server", "HTTP 403")


def _on_a_thread(said):
    thread = threading.Thread(target=said)
    thread.start()
    thread.join()


class _Player(VlcPlayerBase):
    """A player of no video, its errors kept as they are told."""

    def __init__(self):
        super().__init__(vlc_instance=None)

        self.errors = []

    def notify_error(self, error, vlc_lines=()):
        self.errors.append((error, vlc_lines))

    def notify_update_status(self, status, percent=0): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def notify_snapshot_taken(self, snapshot_path): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class TestTheWorker:
    @pytest.mark.parametrize(
        ("raised", "title"),
        [
            (StreamOfflineError(), "Stream is offline"),
            (_http_error(410), "Not found"),
        ],
    )
    def test_says_why_it_failed(self, mocker, raised, title):
        mocker.patch(RESOLVE_URL, side_effect=raised)
        worker = VideoURLResolverWorker()
        failed = []
        worker.failed.connect(failed.append)

        worker.resolve("https://site.example/v")

        (error,) = failed
        assert isinstance(error, ShownError)
        assert error.title == title

    def test_the_resolver_named_as_it_is_tried(self, mocker):
        def resolve(url, headers=None, progress=None, **kwargs):
            kwargs["on_resolver"]("yt-dlp")
            return None

        mocker.patch(RESOLVE_URL, side_effect=resolve)
        worker = VideoURLResolverWorker()
        named = []
        worker.resolving.connect(named.append)

        worker.resolve("https://site.example/v")

        assert named == ["yt-dlp"]

    def test_what_the_resolver_that_took_the_link_ran_into(self, mocker):
        """Not that none could take it: the one that did says why it failed,
        the rest tried after it all the same."""

        class _Took:
            def __init__(self, url, **kwargs): ...

            def resolve(self):
                raise ResolverFailed from DownloadError(
                    "ERROR: [youtube] abc: Video unavailable"
                )

        class _NotItsKind(_Took):
            def resolve(self):
                tried.append("next")
                raise NoResolverPlugin

        tried = []
        mocker.patch(
            PICK_RESOLVERS,
            return_value={URLResolver.YT_DLP: _Took, URLResolver.DIRECT: _NotItsKind},
        )
        worker = VideoURLResolverWorker()
        failed = []
        worker.failed.connect(failed.append)

        worker.resolve("https://site.example/v")

        (error,) = failed
        assert (error.title, error.code) == ("Not found", "Unavailable")
        assert tried == ["next"]


# --- the cell


class _Frame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=60000
        )


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings
    PlaylistSettings().clear()


@pytest.fixture
def make_cell(mocker):
    mocker.patch.object(VideoURLResolver, "resolve")
    made = []

    def _make(uri, media_list=None, lists=None, **video_kwargs):
        context = MagicMock()
        context.is_overlay_hide_on_timeout = False
        context.is_drag_ui = False
        context.is_disable_overlay = False
        context.is_show_overlay_border = False
        context.overlay_timeout = 1
        context.synced_view = None
        context.lists = lists or MediaListsRegistry()
        context.bookmarks = BookmarksRegistry()
        context.video_blocks = []
        context.commands.stream_failure.return_value = None

        parent = QWidget()
        block = VideoBlock(video_driver=_Frame, context=context, parent=parent)
        context.video_blocks.append(block)

        video_kwargs.setdefault("playback_state", VideoInitialState.PAUSED)

        if media_list is not None:
            video_kwargs.update(list_id=media_list.id, list_index=0)

        block.set_video(Video(uri=uri, **video_kwargs))

        made.append((block, parent))

        return block

    yield _make

    for block, _parent in made:
        block.cleanup()
        block.url_resolver.cleanup()


class TestOnTheCell:
    def test_a_failed_file_says_why_with_its_tag(self, make_cell, tmp_path):
        video = tmp_path / "a.mp4"
        video.touch()
        block = make_cell(video)

        block.video_driver_error(
            "Player error", ("main decoder: Codec `prores' is not supported",)
        )

        card = block.video_status.error
        assert block.video_status.mode is StatusMode.ERROR
        assert card.title == "Player error"
        assert card.about == "Codec `prores' is not supported"
        assert (card.where, card.code) == ("Player", "VLC")
        assert block.overlay.mode is OverlayMode.ERROR
        assert not block.overlay.details_button.isHidden()

    def test_a_file_gone_since(self, make_cell, tmp_path):
        video = tmp_path / "a.mp4"
        video.touch()
        block = make_cell(video)
        video.unlink()

        block.video_driver_error("Failed to load media")

        assert block.video_status.error.title == "File not found"

    def test_a_stream_says_what_the_proxy_was_told(self, make_cell):
        block = make_cell(
            "https://site.example/live", network_retry_mode=NetworkRetryMode.OFF
        )
        block.stream._proxied_url = "http://127.0.0.1:1/?session_id=s"
        block.stream._loaded_at = time.monotonic() - 1
        block._ctx.commands.stream_failure.return_value = ProxyFailure(
            url="https://cdn.example/seg.ts", status=403, reason="Forbidden"
        )

        block.video_driver_error("Video stopped before initialization")

        card = block.video_status.error
        assert card.title == "Access denied"
        assert (card.where, card.code) == ("Server", "HTTP 403")

    def test_what_the_proxy_was_told_before_this_load_left_alone(self, make_cell):
        block = make_cell(
            "https://site.example/live", network_retry_mode=NetworkRetryMode.OFF
        )
        block.stream._proxied_url = "http://127.0.0.1:1/?session_id=s"
        block._ctx.commands.stream_failure.return_value = ProxyFailure(
            url="https://cdn.example/seg.ts", status=403, at=time.monotonic() - 60
        )
        block.stream._loaded_at = time.monotonic()

        block.video_driver_error("Video stopped before initialization")

        assert block.video_status.error.where == "Player"

    def test_a_link_says_what_the_resolver_ran_into(self, make_cell):
        block = make_cell(
            "https://site.example/watch", network_retry_mode=NetworkRetryMode.OFF
        )

        block.url_resolver.failed.emit(
            resolve_error(_http_error(429), "https://site.example/watch")
        )
        block.url_resolver.error.emit()

        card = block.video_status.error
        assert card.title == "Too many requests"
        assert (card.where, card.code) == ("Server", "HTTP 429")

    def test_reconnecting_says_what_went_wrong(self, make_cell):
        block = make_cell(
            "https://site.example/watch",
            network_retry_mode=NetworkRetryMode.TIMES,
            network_retry_times=3,
        )

        block.url_resolver.failed.emit(
            resolve_error(_http_error(503), "https://site.example/watch")
        )
        block.url_resolver.error.emit()

        assert block.video_status.mode is StatusMode.LOADING
        assert block.video_status.detail == "Try 1 of 3 · Server HTTP 503"
        assert block.overlay.mode is OverlayMode.LOADING

        block.recovery._retry_timer.stop()

    def test_a_list_item_says_when_the_next_one_comes(self, make_cell, tmp_path):
        files = [tmp_path / name for name in ("a.mp4", "b.mp4")]
        for file in files:
            file.touch()

        lists = MediaListsRegistry()
        media_list = lists.add(MediaList(items=[ListItem(uri=f) for f in files]))
        block = make_cell(
            files[0],
            media_list=media_list,
            lists=lists,
            end_action=VideoEndAction.NEXT_FILE,
        )

        block.video_driver_error("Player error")

        assert block.video_status.note == "Next file in 2 s"
        assert not block.overlay.next_button.isHidden()
        assert block.overlay.next_button.text == "Next"

        block.recovery.stop_skip()

    def test_a_list_played_back_to_front_says_the_one_before_comes(
        self, make_cell, tmp_path
    ):
        block, _ = _failed_list_item(
            make_cell, tmp_path, end_action=VideoEndAction.PREVIOUS_FILE
        )

        assert block.video_status.note == "Previous file in 2 s"
        assert not block.overlay.next_button.isHidden()
        assert block.overlay.next_button.text == "Previous"

        block.recovery.stop_skip()

    def test_its_details_in_full(self, make_cell, mocker):
        block = make_cell(
            "https://site.example/watch", network_retry_mode=NetworkRetryMode.OFF
        )
        block.title = "Deep Sea"
        block.url_resolver.failed.emit(
            resolve_error(_http_error(403), "https://site.example/watch")
        )
        block.url_resolver.error.emit()

        shown = []
        mocker.patch(
            "gridplayer.widgets.video_block.ErrorDetailsDialog.exec_",
            lambda dialog: shown.append(dialog),
        )

        block.overlay.details_button.clicked.emit()

        (dialog,) = shown
        error = dialog._error
        rows = dict(dialog._rows)
        assert error.title == "Access denied"
        assert rows["Video"] == "Deep Sea"
        assert rows["Link"] == "https://site.example/watch"
        assert rows["Step"] == "Resolving the link"
        assert rows["Code"] == "HTTP 403 Forbidden"
        assert rows["Server"] == "site.example"
        assert "403 Client Error" in error.raw
        assert "Access denied" in details_txt(error, dialog._rows)

    def test_forgotten_once_it_plays(self, make_cell, tmp_path):
        video = tmp_path / "a.mp4"
        video.touch()
        block = make_cell(video)
        block.video_driver_error("Player error")

        block.reload()

        assert block._last_error is None

    def test_held_on_the_item_while_its_details_are_read(
        self, make_cell, tmp_path, mocker
    ):
        block, _ = _failed_list_item(make_cell, tmp_path)
        while_read = []
        mocker.patch(
            "gridplayer.widgets.video_block.ErrorDetailsDialog.exec_",
            side_effect=lambda: while_read.append(block.recovery.is_skip_counting),
        )

        block.show_error_details()

        assert while_read == [False]
        # closed with nothing done in it: on through the list as before
        assert block.recovery.is_skip_counting
        assert block.video_status.note == "Next file in 2 s"

        block.recovery.stop_skip()

    def test_its_try_again_for_the_item_that_failed(self, make_cell, tmp_path, mocker):
        block, files = _failed_list_item(make_cell, tmp_path)
        mocker.patch(
            "gridplayer.widgets.video_block.ErrorDetailsDialog.exec_",
            lambda dialog: dialog.try_again.emit(),
        )

        block.show_error_details()

        assert block.video_params.uri == files[0]
        assert not block._is_error
        assert not block.recovery.is_skip_counting

    def test_next_goes_the_way_the_list_goes_by_itself(
        self, make_cell, tmp_path, mocker
    ):
        block, _ = _failed_list_item(
            make_cell, tmp_path, end_action=VideoEndAction.PREVIOUS_FILE
        )
        stepped = []
        mocker.patch.object(
            block, "previous_video", lambda is_end: stepped.append(("back", is_end))
        )

        block.overlay.next_clicked.emit()

        assert stepped == [("back", True)]

    def test_stopped_it_is_a_stopped_one_like_any_other(self, make_cell, tmp_path):
        video = tmp_path / "a.mp4"
        video.touch()
        block = make_cell(video)
        block.video_driver_error("Player error")

        block.stop_playback()

        assert not block._is_error
        assert block.overlay.mode is OverlayMode.STOPPED

    def test_not_named_by_how_far_it_loaded(self, make_cell, tmp_path):
        video = tmp_path / "a.mp4"
        video.touch()
        block = make_cell(video)
        block._show_stage(LoadStage.VIDEO, "Opening…")
        video.unlink()

        # the only file of its folder gone, none to go on to
        block.switch_video(None)

        assert block.video_status.error.title == "File not found"

    def test_its_list_read_before_it_was_stopped_no_step_of_the_next_load(
        self, make_cell, tmp_path
    ):
        video = tmp_path / "a.mp4"
        video.touch()
        block = make_cell(video)
        block._show_stage(LoadStage.LIST, "Reading the list…")

        block.stop_playback()
        block._start_load()

        assert LoadStage.LIST not in block._load_steps

    def test_stopped_from_the_menu_it_reconnects_no_more(self, make_cell):
        """Stop and Stop All in the menu stop it as its own Stop does: the
        reconnect counting down started it loading again once at 0."""

        block = make_cell(
            "https://site.example/watch",
            network_retry_mode=NetworkRetryMode.TIMES,
            network_retry_times=3,
        )
        block.url_resolver.failed.emit(
            resolve_error(_http_error(503), "https://site.example/watch")
        )
        block.url_resolver.error.emit()
        assert block.recovery._retry_timer.isActive()

        block.stop_playback()

        assert not block.recovery._retry_timer.isActive()
        assert block.recovery._retries == 0
        assert block.overlay.mode is OverlayMode.STOPPED

    def test_stopped_from_the_menu_its_list_goes_on_no_further(
        self, make_cell, tmp_path
    ):
        block, files = _failed_list_item(make_cell, tmp_path)

        block.stop_playback()

        assert not block.recovery.is_skip_counting
        assert block.video_params.uri == files[0]

    def test_stopped_while_its_link_resolves_what_it_finds_is_let_go(self, make_cell):
        block = make_cell("https://site.example/watch")
        resolving = block.url_resolver
        resolving._is_busy = True

        block.stop_playback()

        assert block.url_resolver is not resolving
        assert resolving._is_closed

    def test_stopped_while_its_list_is_read_it_waits_for_it_no_more(
        self, make_cell, tmp_path, mocker
    ):
        block, _ = _failed_list_item(make_cell, tmp_path)
        block._is_waiting_for_list_read = True

        block.stop_playback()
        start_load = mocker.patch.object(block, "_start_load")
        block._on_list_reading(block.video_params.list_id)

        start_load.assert_not_called()

    def test_its_overlay_goes_from_stopped_straight_to_loading(self, make_cell):
        """What the overlay shows is the cell's alone to say: told by the cell
        it was no longer stopped, it went to a video's on its own first."""

        block = make_cell("https://site.example/watch")
        block.stop_playback()

        assert block.overlay.mode is OverlayMode.STOPPED
        assert block.overlay._is_on_chrome

        modes = []
        set_mode = block.overlay.set_mode
        block.overlay.set_mode = lambda mode: (modes.append(mode), set_mode(mode))

        block.set_pause(False)

        assert block.is_loading
        assert OverlayMode.VIDEO not in modes
        assert block.overlay.mode is OverlayMode.LOADING
        assert block.overlay._is_on_chrome

    def test_the_menu_stops_it_while_it_loads(self, make_cell):
        """The menu's Stop, and its key, as well as its own: it was there
        only once the video played."""

        block = make_cell("https://site.example/watch")
        menu = _menu_on(block)

        assert block.is_loading
        assert menu.is_active_stoppable()

        menu.cmd_active("stop_playback")

        assert block.overlay.mode is OverlayMode.STOPPED
        assert not menu.is_active_stoppable()

    def test_the_menu_stops_it_while_it_reconnects(self, make_cell):
        block = make_cell(
            "https://site.example/watch",
            network_retry_mode=NetworkRetryMode.TIMES,
            network_retry_times=3,
        )
        block.url_resolver.failed.emit(
            resolve_error(_http_error(503), "https://site.example/watch")
        )
        block.url_resolver.error.emit()
        menu = _menu_on(block)

        assert menu.is_active_stoppable()

        menu.cmd_active("stop_playback")

        assert not block.recovery._retry_timer.isActive()
        assert block.overlay.mode is OverlayMode.STOPPED

    def test_the_menu_stops_its_list_going_on_once_it_failed(self, make_cell, tmp_path):
        block, files = _failed_list_item(make_cell, tmp_path)
        menu = _menu_on(block)

        assert menu.is_active_stoppable()

        menu.cmd_active("stop_playback")

        assert not block.recovery.is_skip_counting
        assert block.video_params.uri == files[0]
        assert block.overlay.mode is OverlayMode.STOPPED

    @pytest.mark.parametrize(
        ("command", "index"), [("next_video", 1), ("previous_video", 2)]
    )
    def test_the_menu_steps_along_its_list_while_it_loads(
        self, make_cell, command, index
    ):
        uris = [f"https://site.example/{name}" for name in ("a", "b", "c")]
        lists = MediaListsRegistry()
        media_list = lists.add(MediaList(items=[ListItem(uri=u) for u in uris]))
        block = make_cell(uris[0], media_list=media_list, lists=lists)
        menu = _menu_on(block)

        assert block.is_loading
        assert not menu.is_active_playable()

        menu.cmd_active(command)

        assert block.video_params.uri == uris[index]


class TestAListOfLinks:
    """An item that would not play: reloaded, or the next one played."""

    def test_one_gone_is_not_reloaded_but_the_next_played(self, make_cell):
        block = _failed_link(make_cell, _http_error(404))

        assert not block.recovery._retry_timer.isActive()
        assert block.recovery.is_skip_counting
        assert block.video_status.error.code == "HTTP 404"

        block.recovery._skip_timer.timeout.emit()

        assert block.video_params.uri == "https://site.example/1"

    def test_one_that_may_answer_otherwise_is_reloaded_first(self, make_cell):
        block = _failed_link(make_cell, _http_error(503))

        assert block.recovery._retry_timer.isActive()
        assert not block.recovery.is_skip_counting

    def test_reloaded_where_set_to_show_the_error(self, make_cell):
        block = _failed_link(
            make_cell, _http_error(404), list_fail_action=ListFailAction.SHOW_ERROR
        )

        assert block.recovery._retry_timer.isActive()

    def test_reloaded_once_it_played(self, make_cell):
        """A link that ran out, while it played, may come back with a new
        one: it is found again on a reload."""

        block = _failed_link(make_cell, None)
        block._has_item_played = True

        _fail(block, _http_error(403))

        assert block.recovery._retry_timer.isActive()

    def test_the_next_one_is_not_taken_to_have_played(self, make_cell):
        block = _failed_link(make_cell, None)
        block._has_item_played = True
        block.next_video()

        _fail(block, _http_error(403))

        assert not block.recovery._retry_timer.isActive()

    def test_one_with_no_list_is_reloaded(self, make_cell):
        block = make_cell(
            "https://site.example/0",
            network_retry_mode=NetworkRetryMode.TIMES,
            network_retry_times=3,
        )

        _fail(block, _http_error(404))

        assert block.recovery._retry_timer.isActive()

    def test_its_menu_is_there_once_it_failed(self, make_cell):
        block = _failed_link(make_cell, _http_error(404))
        menu = _menu_on(block)

        menu.cmd_active("recovery.set_fail_action", ListFailAction.SHOW_ERROR)

        assert block.video_params.list_fail_action is ListFailAction.SHOW_ERROR
        assert not block.recovery.is_skip_counting
        assert menu.cmd_active("recovery.get_fail_wait") == "2 s"


def _failed_link(make_cell, error, **video_kwargs):
    """The first of three links of a list, failed with what is given."""

    links = [f"https://site.example/{n}" for n in range(3)]

    lists = MediaListsRegistry()
    media_list = lists.add(MediaList(items=[ListItem(uri=link) for link in links]))
    block = make_cell(
        links[0],
        media_list=media_list,
        lists=lists,
        end_action=VideoEndAction.NEXT_FILE,
        network_retry_mode=NetworkRetryMode.TIMES,
        network_retry_times=3,
        **video_kwargs,
    )

    if error is not None:
        _fail(block, error)

    return block


def _fail(block, error):
    block.url_resolver.failed.emit(resolve_error(error, str(block.video_params.uri)))
    block.url_resolver.error.emit()


def _menu_on(block) -> ActiveBlockManager:
    """What the menu asks, and does, of the cell it is shown for."""

    menu = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    menu._ctx.active_block = block

    return menu


def _failed_list_item(make_cell, tmp_path, end_action=VideoEndAction.NEXT_FILE):
    """The first of two files of a list, failed, on to the next in a moment."""

    files = [tmp_path / name for name in ("a.mp4", "b.mp4")]
    for file in files:
        file.touch()

    lists = MediaListsRegistry()
    media_list = lists.add(MediaList(items=[ListItem(uri=f) for f in files]))
    block = make_cell(
        files[0], media_list=media_list, lists=lists, end_action=end_action
    )

    block.video_driver_error("Player error")

    assert block.recovery.is_skip_counting

    return block, files


def test_the_path_type_kept(tmp_path):
    # a file's error names its path as given
    error = file_error(ReadErrorKind.NO_ACCESS, Path(tmp_path) / "locked.mp4")

    assert (error.where, error.code) == ("File", "No access")
    assert error.raw.endswith("locked.mp4")


def test_the_details_tag_never_a_window_of_its_own():
    """Shown before its dialog is, it was one: a frameless window that came
    and went as the dialog was laid out."""

    dialog = ErrorDetailsDialog(
        ShownError(title="Access denied", where="Server", code="HTTP 403")
    )

    assert not dialog.tag.isWindow()

    dialog.deleteLater()
