import contextlib
import logging
import threading
from types import MappingProxyType
from typing import TYPE_CHECKING

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from gridplayer.models.resolver_patterns import ResolverPatterns
from gridplayer.params.static import URLResolver
from gridplayer.settings import Settings
from gridplayer.utils.list_progress import ReadingStopped, Throttled, reading_txt
from gridplayer.utils.off_thread import interface_first
from gridplayer.utils.qt import translate
from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    PlaylistURLError,
    ResolvedList,
    ResolvedVideo,
    StreamOfflineError,
)

if TYPE_CHECKING:
    from gridplayer.utils.url_resolve.resolver_base import ResolverBase

_log = logging.getLogger(__name__)

RESOLVER_NAMES = MappingProxyType(
    {
        URLResolver.STREAMLINK: "Streamlink",
        URLResolver.YT_DLP: "yt-dlp",
    }
)


# streamlink and yt-dlp take a good third of a second to import, so they
# are left until a URL needs resolving, on the worker thread, instead of
# holding up every startup whether it opens a URL or not
def _resolver_map() -> dict[URLResolver, type["ResolverBase"]]:
    from gridplayer.utils.url_resolve.resolver_base import DirectResolver
    from gridplayer.utils.url_resolve.resolver_streamlink import StreamlinkResolver
    from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver

    return {
        URLResolver.STREAMLINK: StreamlinkResolver,
        URLResolver.YT_DLP: YoutubeDLResolver,
        URLResolver.DIRECT: DirectResolver,
    }


def resolve_url(
    url: str, on_status=None, headers: dict[str, str] | None = None, progress=None
) -> ResolvedVideo | None:
    """Resolve a page URL into playable streams, fetched with these headers
    on top of the settings. progress is told how many videos are read of a
    list the URL turns out to be, as they are; see ResolverBase.

    Plain function on purpose: the proxy calls it from its own threads to
    renew URLs that have expired, where there is no Qt object to report to.
    """

    def status(message: str) -> None:
        if on_status is not None:
            on_status(message)

    status(translate("Video Status", "Picking URL resolvers"))

    for resolver_id, resolver in _pick_resolvers(url).items():
        status(_make_status_msg(resolver_id))

        _log.debug(f"Trying to resolve URL with {resolver.__name__}")
        with contextlib.suppress(NoResolverPlugin):
            return resolver(url, headers=headers, progress=progress).resolve()

    return None


class VideoURLResolverWorker(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    list_resolved = pyqtSignal(ResolvedList)
    error = pyqtSignal()
    update_status = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log = logging.getLogger(self.__class__.__name__)

        # set once the video is let go of: a list the link turns out to be,
        # still being read, is read no further than its next video
        self.stop = threading.Event()

    def resolve(self, url, headers=None):
        progress = Throttled(self._tell_reading, stop=self.stop)

        try:
            with interface_first():
                resolved = resolve_url(
                    url,
                    on_status=self.update_status.emit,
                    headers=headers,
                    progress=progress,
                )
        except ReadingStopped:
            self._log.debug(f"Stopped reading the list behind {url}")
            return None
        except StreamOfflineError:
            self._log.debug("Stream is offline")
            return self._error(translate("Video Error", "Stream is offline"))
        except PlaylistURLError as e:
            return self._list(url, e.info)
        except BadURLException as e:
            self._log.error(e)
            return self._error(translate("Video Error", "Failed to resolve URL"))
        except Exception:
            self._log.exception("URL resolver exception")
            return self._error(translate("Video Error", "Failed to resolve URL"))

        # no resolver claimed the URL. Emitting this would raise on the way
        # out of the worker thread and leave the video stuck on "loading"
        if resolved is None:
            self._log.error(f"No resolver was able to handle {url}")
            return self._error(translate("Video Error", "Failed to resolve URL"))

        self.url_resolved.emit(resolved)

    def _tell_reading(self, what: str, count: int, of: int | None = None) -> None:
        self.update_status.emit(reading_txt(what, count, of)[0])

    def _error(self, message: str) -> None:
        self.update_status.emit(message)
        self.error.emit()

    def _list(self, url: str, info: dict) -> None:
        from gridplayer.utils.web_lists import web_list_items

        items = web_list_items(info)

        if not items:
            self._log.error(f"Link to a playlist with nothing to play on it: {url}")
            return self._error(translate("Video Error", "This link is a playlist"))

        self._log.debug(f"Link to a playlist of {len(items)}: {url}")

        self.list_resolved.emit(
            ResolvedList(title=info.get("title") or url, items=items)
        )


class VideoURLResolver(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    # the link leads to a list of videos rather than to one
    list_resolved = pyqtSignal(ResolvedList)
    error = pyqtSignal()
    update_status = pyqtSignal(str)

    _resolve_url = pyqtSignal(str, object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_busy = False
        self._is_closed = False

        self.thread = QThread()

        self.worker = VideoURLResolverWorker()
        self.worker.moveToThread(self.thread)

        self.worker.url_resolved.connect(self._on_resolved)
        self.worker.list_resolved.connect(self._on_list)
        self.worker.error.connect(self._on_error)
        self.worker.update_status.connect(self._on_status)

        self._resolve_url.connect(self.worker.resolve)

        self.thread.start()

    def cleanup(self):
        if self._is_closed:
            return

        self._is_closed = True
        self.worker.stop.set()

        self.worker.url_resolved.disconnect()
        self.worker.list_resolved.disconnect()
        self.worker.error.disconnect()
        self.worker.update_status.disconnect()

        self.thread.quit()

        # a resolver can't be interrupted, and yt-dlp on a slow host can
        # take its time, so waiting for it here freezes whoever is closing
        if self._is_busy:
            _abandon(self.thread, self.worker)
        else:
            self.thread.wait()

    def resolve(self, url, headers=None):
        if self._is_closed:
            return

        self._is_busy = True
        self._resolve_url.emit(url, headers)

    # results posted just before cleanup still arrive after it
    def _on_resolved(self, video: ResolvedVideo):
        self._is_busy = False
        if not self._is_closed:
            self.url_resolved.emit(video)

    def _on_list(self, resolved_list: ResolvedList):
        self._is_busy = False
        if not self._is_closed:
            self.list_resolved.emit(resolved_list)

    def _on_error(self):
        self._is_busy = False
        if not self._is_closed:
            self.error.emit()

    def _on_status(self, message: str):
        if not self._is_closed:
            self.update_status.emit(message)


# resolver threads whose video went away mid-resolve, left to run out on
# their own. They are held here until they do: a QThread dropped while it
# is still running takes the whole app down with it.
_abandoned: set[tuple[QThread, QObject]] = set()


def _abandon(thread: QThread, worker: QObject) -> None:
    _log.debug("Leaving URL resolve to finish in the background")

    entry = (thread, worker)
    _abandoned.add(entry)

    def release():
        thread.wait()
        _abandoned.discard(entry)

    thread.finished.connect(release)

    # it may have stopped before there was anyone to tell
    if thread.isFinished():
        release()


def _make_status_msg(resolver_id: URLResolver):
    if resolver_id == URLResolver.DIRECT:
        return translate("Video Status", "Playing URL directly")

    return translate("Video Status", "Resolving URL via {RESOLVER_NAME}").format(
        RESOLVER_NAME=RESOLVER_NAMES[resolver_id]
    )


def _pick_resolvers(url) -> dict[URLResolver, type["ResolverBase"]]:
    if _is_match_youtube(url):
        return {URLResolver.YT_DLP: _resolver_map()[URLResolver.YT_DLP]}

    url_resolvers = _get_resolvers(url)

    for resolver_id, resolver in url_resolvers.copy().items():
        if not resolver.is_able_to_handle(url):
            url_resolvers.pop(resolver_id)

    return url_resolvers


def _get_resolvers(
    url: str,
) -> dict[URLResolver, type["ResolverBase"]]:
    resolver_map = _resolver_map()

    priority_resolver: URLResolver = Settings().get("streaming/resolver_priority")
    patterns: ResolverPatterns = Settings().get("streaming/resolver_priority_patterns")

    url_resolver = patterns.get_resolver(url) or priority_resolver

    resolvers = {
        resolver_id: resolver
        for resolver_id, resolver in resolver_map.items()
        if resolver_id != url_resolver
    }

    return {
        url_resolver: resolver_map[url_resolver],
        **resolvers,
    }


def _is_match_youtube(url: str) -> bool:
    from yt_dlp.extractor import youtube as yt_extractor

    from gridplayer.utils.percent_re import untangle_percent_re

    # yt-dlp patches urllib3 as it is imported; see utils/percent_re.py
    untangle_percent_re()

    # the playlist and channel ones too: Streamlink knows nothing of lists,
    # and a video opened from a playlist is one of its links
    yt_extractors = (
        yt_extractor.YoutubeIE,
        yt_extractor.YoutubeYtBeIE,
        yt_extractor.YoutubeLivestreamEmbedIE,
        yt_extractor.YoutubeClipIE,
        yt_extractor.YoutubeTabIE,
        yt_extractor.YoutubePlaylistIE,
    )

    return any(ie.suitable(url) for ie in yt_extractors)
