import contextlib
import logging
from types import MappingProxyType
from typing import Dict, Optional, Type

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from yt_dlp.extractor import youtube as yt_extractor

from gridplayer.models.resolver_patterns import ResolverPatterns
from gridplayer.models.video import VideoURL
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


class VideoURLResolverWorker(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    error = pyqtSignal()
    update_status = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log = logging.getLogger(self.__class__.__name__)

    def resolve(self, url):
        try:
            self.url_resolved.emit(self.resolve_url(url))
        except StreamOfflineError:
            self._log.debug("Stream is offline")
            self._error(translate("Video Error", "Stream is offline"))
        except BadURLException as e:
            self._log.error(e)
            self._error(translate("Video Error", "Failed to resolve URL"))
        except Exception:
            self._log.exception("URL resolver exception")
            self._error(translate("Video Error", "Failed to resolve URL"))

    def resolve_url(self, url: VideoURL) -> Optional[ResolvedVideo]:
        self.update_status.emit(translate("Video Status", "Picking URL resolvers"))
        url_resolvers = _pick_resolvers(url)

        for resolver_id, resolver in url_resolvers.items():
            self.update_status.emit(_make_status_msg(resolver_id))

            self._log.debug(f"Trying to resolve URL with {resolver.__name__}")
            with contextlib.suppress(NoResolverPlugin):
                return resolver(url).resolve()

        return None

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

        self.thread = QThread()

        self.worker = VideoURLResolverWorker()
        self.worker.moveToThread(self.thread)

        self.worker.url_resolved.connect(self.url_resolved)
        self.worker.error.connect(self.error)
        self.worker.update_status.connect(self.update_status)

        self._resolve_url.connect(self.worker.resolve)

        self.thread.start()

    def cleanup(self):
        self.thread.quit()
        self.thread.wait()

    def resolve(self, url):
        self._resolve_url.emit(url)


def _make_status_msg(resolver_id: URLResolver):
    if resolver_id == URLResolver.DIRECT:
        return translate("Video Status", "Playing URL directly")

    return translate("Video Status", "Resolving URL via {RESOLVER_NAME}").format(
        RESOLVER_NAME=RESOLVER_NAMES[resolver_id]
    )


def _pick_resolvers(url) -> Dict[URLResolver, Type[ResolverBase]]:
    if _is_match_youtube(url):
        return {URLResolver.YT_DLP: YoutubeDLResolver}

    url_resolvers = _get_resolvers(url)

    for resolver_id, resolver in url_resolvers.copy().items():
        if not resolver.is_able_to_handle(url):
            url_resolvers.pop(resolver_id)

    return url_resolvers


def _get_resolvers(  # noqa: WPS210
    url: VideoURL,
) -> Dict[URLResolver, Type[ResolverBase]]:
    priority_resolver: URLResolver = Settings().get("streaming/resolver_priority")
    patterns: ResolverPatterns = Settings().get("streaming/resolver_priority_patterns")

    url_resolver = patterns.get_resolver(url) or priority_resolver

    resolvers = {url_resolver: RESOLVER_MAP[url_resolver]}
    for resolver_id, resolver in RESOLVER_MAP.items():
        if resolver_id != url_resolver:
            resolvers[resolver_id] = resolver

    return resolvers


def _is_match_youtube(url: VideoURL) -> bool:
    yt_extractors = (
        yt_extractor.YoutubeIE,
        yt_extractor.YoutubeYtBeIE,
        yt_extractor.YoutubeLivestreamEmbedIE,
        yt_extractor.YoutubeClipIE,
    )

    return any(ie.suitable(url) for ie in yt_extractors)
