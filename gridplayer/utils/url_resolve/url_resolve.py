import contextlib
import logging
from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from yt_dlp.extractor import youtube as yt_extractor

from gridplayer.models.video import VideoURL
from gridplayer.utils.qt import translate
from gridplayer.utils.url_resolve.resolver_base import GenericResolver
from gridplayer.utils.url_resolve.resolver_streamlink import StreamlinkResolver
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver
from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    ResolvedVideo,
    StreamOfflineError,
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

        for resolver_name, resolver in url_resolvers.items():
            status_msg = translate("Video Status", "Resolving URL via {RESOLVER_NAME}")
            self.update_status.emit(status_msg.format(RESOLVER_NAME=resolver_name))

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


def _pick_resolvers(url):
    url_resolvers = {
        "streamlink": StreamlinkResolver,
        "yt-dlp": YoutubeDLResolver,
        "generic": GenericResolver,
    }

    if _is_match_youtube(url):
        return {"yt-dlp": YoutubeDLResolver}

    for resolver_name, resolver in url_resolvers.copy().items():
        if not resolver.is_able_to_handle(url):
            url_resolvers.pop(resolver_name)

    return url_resolvers


def _is_match_youtube(url: VideoURL) -> bool:
    yt_extractors = (
        yt_extractor.YoutubeIE,
        yt_extractor.YoutubeYtBeIE,
        yt_extractor.YoutubeLivestreamEmbedIE,
        yt_extractor.YoutubeClipIE,
    )

    return any(ie.suitable(url) for ie in yt_extractors)
