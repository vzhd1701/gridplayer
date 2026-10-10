"""Pictures of the videos on a list read from a site, as the List window
shows them: fetched as they come to be shown, the way the rest of the app
reaches out, and kept in the cache for the next time.
"""

import contextlib
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Collection
from concurrent.futures import Future, ThreadPoolExecutor

from PyQt5.QtCore import (
    QBuffer,
    QIODevice,
    QObject,
    QRect,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QImage, QImageReader

from gridplayer.utils import cache

_log = logging.getLogger(__name__)

# their folder in the cache
THUMBNAILS_DIR = "thumbnails"

# a picture larger than this is not one to show in a row
MAX_THUMBNAIL_BYTES = 1024 * 1024

# how many are fetched at once
THUMBNAILS_AT_ONCE = 4

# how many are kept in memory, ready to be shown again as the list is
# scrolled back up: a window shows a dozen or so at a time
THUMBNAILS_KEPT = 200

_session_local = threading.local()


def fetch_thumbnail(url: str) -> bytes:
    """A picture, from the cache, or else from the site and then kept."""

    data = cache.cached(THUMBNAILS_DIR, url)

    if data is not None:
        if _is_picture(data):
            return data

        # no picture after all: fetched again
        cache.forget(THUMBNAILS_DIR, url)

    data = _download(url)

    cache.keep(THUMBNAILS_DIR, url, data)

    return data


def _is_picture(data: bytes) -> bool:
    """Whether it reads as a picture: how it starts is enough to tell."""

    buffer = QBuffer()
    buffer.setData(data)
    buffer.open(QIODevice.ReadOnly)

    return QImageReader(buffer).canRead()


def _download(url: str) -> bytes:
    from gridplayer.utils.network import HTTPStatusError, fetch_capped

    status, data = fetch_capped(_session(), url, MAX_THUMBNAIL_BYTES + 1)

    if status >= 400:
        raise HTTPStatusError(status)

    if len(data) > MAX_THUMBNAIL_BYTES:
        raise ValueError("too large for a thumbnail")

    # say a page a site answered with: not one to keep
    if not _is_picture(data):
        raise ValueError("not a picture")

    return data


def _session():
    """A session for each thread fetching, made again when the network
    settings or the cookies have changed since."""

    from streamlink import Streamlink

    from gridplayer.utils.network import configure_session, session_stamp

    stamp = session_stamp()

    if getattr(_session_local, "stamp", None) != stamp:
        session = Streamlink()
        configure_session(session)

        _session_local.session = session
        _session_local.stamp = stamp

    return _session_local.session


class ThumbnailLoader(QObject):
    """Pictures fetched as they are asked for, a few at a time, each made the
    size it is shown at; the last few hundred kept."""

    # a picture came, or turned out not to be had
    loaded = pyqtSignal(str)

    # from the threads fetching, to this one
    _came = pyqtSignal(str, object)

    def __init__(self, fetch: Callable[[str], bytes], size: QSize, parent=None):
        super().__init__(parent)

        self._fetch = fetch
        self._size = QSize(size)

        self._pool = ThreadPoolExecutor(
            max_workers=THUMBNAILS_AT_ONCE, thread_name_prefix="thumbnail"
        )
        self._is_stopped = False

        self._pictures: OrderedDict[str, QImage] = OrderedDict()
        self._asked: set[str] = set()
        self._missing: set[str] = set()

        # the fetches asked for, until their pictures come: the ones not
        # started yet can be let go of
        self._fetches: dict[str, Future] = {}

        self._came.connect(self._on_came)

    def picture(self, url: str) -> QImage | None:
        """The picture, if it has come."""

        picture = self._pictures.get(url)

        if picture is not None:
            self._pictures.move_to_end(url)

        return picture

    def fetch(self, url: str):
        """The picture fetched, unless it has come, is coming or cannot be
        had."""

        if self.is_to_fetch(url) and not self._is_stopped:
            self._asked.add(url)
            self._fetches[url] = self._pool.submit(self._load, url)

    def let_go_except(self, urls: Collection[str]):
        """The fetches waiting their turn let go of, but for these: the rows
        scrolled away from wait no longer ahead of the ones scrolled to."""

        for url, fetch in list(self._fetches.items()):
            if url not in urls and fetch.cancel():
                del self._fetches[url]
                self._asked.discard(url)

    def is_to_fetch(self, url: str) -> bool:
        """Whether a picture is still to be asked for."""

        return (
            url not in self._pictures
            and url not in self._asked
            and url not in self._missing
        )

    def is_missing(self, url: str) -> bool:
        """Whether a picture could not be had: none to wait for."""

        return url in self._missing

    def stop(self):
        """No more fetched; what is under way let go of."""

        self._is_stopped = True
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _load(self, url: str):
        if self._is_stopped:
            return

        try:
            image = QImage.fromData(self._fetch(url))
        except Exception as e:
            _log.debug(f"Thumbnail not fetched: {url}: {e}")
            image = None

        if image is not None and not image.isNull():
            image = fitted(image, self._size)
        else:
            image = None

        if self._is_stopped:
            return

        # the window may have closed meanwhile
        with contextlib.suppress(RuntimeError):
            self._came.emit(url, image)

    def _on_came(self, url: str, image: QImage | None):
        self._asked.discard(url)
        self._fetches.pop(url, None)

        if image is None:
            self._missing.add(url)
        else:
            self._pictures[url] = image

            while len(self._pictures) > THUMBNAILS_KEPT:
                self._pictures.popitem(last=False)

        self.loaded.emit(url)


def fitted(image: QImage, size: QSize) -> QImage:
    """A picture filling a box of this size, cut to its shape in the middle
    rather than squeezed: a 4:3 one in a 16:9 box loses its top and bottom."""

    scaled = image.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    cut = QRect(
        (scaled.width() - size.width()) // 2,
        (scaled.height() - size.height()) // 2,
        size.width(),
        size.height(),
    )

    return scaled.copy(cut)
