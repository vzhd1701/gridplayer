import contextlib
import logging
import traceback
from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from streamlink import PluginError

from gridplayer.models.video import VideoURL
from gridplayer.utils.qt import translate
from gridplayer.utils.url_resolve.resolver_streamlink import resolve_streamlink
from gridplayer.utils.url_resolve.resolver_yt_dlp import resolve_youtube_dl
from gridplayer.utils.url_resolve.static import (
    YOUTUBE_MATCH,
    BadURLException,
    NoResolverPlugin,
    ResolvedVideo,
)
from gridplayer.utils.url_resolve.stream_detect import is_http_live_stream

logger = logging.getLogger(__name__)


class VideoURLResolverWorker(QObject):
    url_resolved = pyqtSignal(ResolvedVideo)
    error = pyqtSignal()
    update_status = pyqtSignal(str)

    def resolve(self, url):
        try:
            self.url_resolved.emit(self.resolve_url(url))
        except BadURLException as e:
            self.update_status.emit(translate("Video Error", "Failed to resolve URL"))
            logger.error(e)
            self.error.emit()
        except Exception:
            # log traceback stack
            self.update_status.emit(translate("Video Error", "Failed to resolve URL"))
            logger.critical(traceback.format_exc())
            self.error.emit()

    def resolve_url(self, url: VideoURL) -> Optional[ResolvedVideo]:
        url_resolvers = {
            "streamlink": resolve_streamlink,
            "yt-dlp": resolve_youtube_dl,
        }

        if YOUTUBE_MATCH.match(url):
            url_resolvers = {"yt-dlp": resolve_youtube_dl}

        for resolver_name, resolver in url_resolvers.items():
            status_msg = translate("Video Status", "Resolving URL via {RESOLVER_NAME}")
            self.update_status.emit(status_msg.format(RESOLVER_NAME=resolver_name))

            logger.debug(f"Trying to resolve URL with {resolver.__name__}")
            with contextlib.suppress(NoResolverPlugin):
                return resolver(url)

        return _resolve_generic(url)


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
