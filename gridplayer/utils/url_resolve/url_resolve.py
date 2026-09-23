import contextlib
import logging
from types import MappingProxyType

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from yt_dlp.extractor import youtube as yt_extractor

from gridplayer.models.resolver_patterns import ResolverPatterns
from gridplayer.params.static import URLResolver
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.utils.url_resolve.resolver_base import DirectResolver, ResolverBase
from gridplayer.utils.url_resolve.resolver_streamlink import StreamlinkResolver
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver
from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    ResolvedVideo,
    StreamOfflineError,
)

_log = logging.getLogger(__name__)

RESOLVER_NAMES = MappingProxyType(
    {
        URLResolver.STREAMLINK: "Streamlink",
        URLResolver.YT_DLP: "yt-dlp",
    }
)

RESOLVER_MAP = MappingProxyType(
    {
        URLResolver.STREAMLINK: StreamlinkResolver,
        URLResolver.YT_DLP: YoutubeDLResolver,
        URLResolver.DIRECT: DirectResolver,
    }
)


def resolve_url(url: str, on_status=None) -> ResolvedVideo | None:
    """Resolve a page URL into playable streams.

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
            return resolver(url).resolve()

    return None


class VideoURLResolverWorker(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    error = pyqtSignal()
    update_status = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log = logging.getLogger(self.__class__.__name__)

    def resolve(self, url):
        try:
            resolved = resolve_url(url, on_status=self.update_status.emit)
        except StreamOfflineError:
            self._log.debug("Stream is offline")
            return self._error(translate("Video Error", "Stream is offline"))
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

    def _error(self, message: str) -> None:
        self.update_status.emit(message)
        self.error.emit()


class VideoURLResolver(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    error = pyqtSignal()
    update_status = pyqtSignal(str)

    _resolve_url = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_busy = False
        self._is_closed = False

        self.thread = QThread()

        self.worker = VideoURLResolverWorker()
        self.worker.moveToThread(self.thread)

        self.worker.url_resolved.connect(self._on_resolved)
        self.worker.error.connect(self._on_error)
        self.worker.update_status.connect(self._on_status)

        self._resolve_url.connect(self.worker.resolve)

        self.thread.start()

    def cleanup(self):
        if self._is_closed:
            return

        self._is_closed = True

        self.worker.url_resolved.disconnect()
        self.worker.error.disconnect()
        self.worker.update_status.disconnect()

        self.thread.quit()

        # a resolver can't be interrupted, and yt-dlp on a slow host can
        # take its time, so waiting for it here freezes whoever is closing
        if self._is_busy:
            _abandon(self.thread, self.worker)
        else:
            self.thread.wait()

    def resolve(self, url):
        if self._is_closed:
            return

        self._is_busy = True
        self._resolve_url.emit(url)

    # results posted just before cleanup still arrive after it
    def _on_resolved(self, video: ResolvedVideo):
        self._is_busy = False
        if not self._is_closed:
            self.url_resolved.emit(video)

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


def _pick_resolvers(url) -> dict[URLResolver, type[ResolverBase]]:
    if _is_match_youtube(url):
        return {URLResolver.YT_DLP: YoutubeDLResolver}

    url_resolvers = _get_resolvers(url)

    for resolver_id, resolver in url_resolvers.copy().items():
        if not resolver.is_able_to_handle(url):
            url_resolvers.pop(resolver_id)

    return url_resolvers


def _get_resolvers(
    url: str,
) -> dict[URLResolver, type[ResolverBase]]:
    priority_resolver: URLResolver = Settings().get("streaming/resolver_priority")
    patterns: ResolverPatterns = Settings().get("streaming/resolver_priority_patterns")

    url_resolver = patterns.get_resolver(url) or priority_resolver

    resolvers = {
        resolver_id: resolver
        for resolver_id, resolver in RESOLVER_MAP.items()
        if resolver_id != url_resolver
    }

    return {
        url_resolver: RESOLVER_MAP[url_resolver],
        **resolvers,
    }


def _is_match_youtube(url: str) -> bool:
    yt_extractors = (
        yt_extractor.YoutubeIE,
        yt_extractor.YoutubeYtBeIE,
        yt_extractor.YoutubeLivestreamEmbedIE,
        yt_extractor.YoutubeClipIE,
    )

    return any(ie.suitable(url) for ie in yt_extractors)
