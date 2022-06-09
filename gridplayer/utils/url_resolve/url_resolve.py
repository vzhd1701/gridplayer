import contextlib
import logging
import traceback
from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from streamlink import PluginError

from gridplayer.utils.url_resolve.resolver_streamlink import resolve_streamlink
from gridplayer.utils.url_resolve.resolver_yt_dlp import resolve_youtube_dl
from gridplayer.utils.url_resolve.static import (
    YOUTUBE_MATCH,
    BadURLException,
    NoResolverPlugin,
    ResolvedVideo,
)
from gridplayer.utils.url_resolve.stream_detect import is_http_live_stream
from gridplayer.video import VideoURL

logger = logging.getLogger(__name__)


class VideoURLResolverWorker(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    error = pyqtSignal()

    def resolve(self, url):
        try:
            self.url_resolved.emit(resolve_url(url))
        except BadURLException as e:
            logger.error(e)
            self.error.emit()
        except Exception:
            # log traceback stack
            logger.critical(traceback.format_exc())
            self.error.emit()


class VideoURLResolver(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    error = pyqtSignal()

    _resolve_url = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.thread = QThread()

        self.worker = VideoURLResolverWorker()
        self.worker.moveToThread(self.thread)

        self.worker.url_resolved.connect(self.url_resolved)
        self.worker.error.connect(self.error)

        self._resolve_url.connect(self.worker.resolve)

        self.thread.start()

    def cleanup(self):
        self.thread.terminate()
        self.thread.wait()

    def resolve(self, url):
        self._resolve_url.emit(url)


def resolve_url(url: VideoURL) -> Optional[ResolvedVideo]:
    if YOUTUBE_MATCH.match(url):
        return resolve_youtube_dl(url)

    url_resolvers = [
        resolve_streamlink,
        resolve_youtube_dl,
    ]

    for resolver in url_resolvers:
        with contextlib.suppress(NoResolverPlugin):
            return resolver(url)

    return _resolve_generic(url)


def _resolve_generic(url: VideoURL) -> Optional[ResolvedVideo]:
    try:
        is_live = is_http_live_stream(url)
    except PluginError:
        raise BadURLException(f"Cannot open URL {url}")

    return ResolvedVideo(
        title=url,
        urls={"generic": url},
        is_live=is_live,
    )
