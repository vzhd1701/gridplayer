"""Pictures of the videos on a list: fetched once, kept in the cache, and
made the size they are shown at."""

import threading
import time

import pytest
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtTest import QTest

from gridplayer.params.static import CacheMode
from gridplayer.utils import cache, thumbnails
from gridplayer.utils.thumbnails import (
    ThumbnailLoader,
    fetch_thumbnail,
    fitted,
)

URL = "https://i.ytimg.com/vi/a/mqdefault.jpg"


def _jpeg(width=320, height=180, color=Qt.red) -> bytes:
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(color))

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "JPG")

    return bytes(data)


def _wait_until(condition, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QTest.qWait(10)
        if condition():
            return True
    return False


@pytest.fixture
def kept_in(tmp_path, monkeypatch):
    """A cache of its own, on disk."""

    monkeypatch.setattr(cache, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(cache, "_mode", lambda: CacheMode.DISK)
    monkeypatch.setattr(cache, "_max_bytes", lambda: 64 * cache.MB)
    monkeypatch.setattr(cache, "_disk_bytes", None)

    return tmp_path / thumbnails.THUMBNAILS_DIR


class TestFetched:
    def test_from_the_site_once_then_from_the_cache(self, kept_in, mocker):
        jpeg = _jpeg()
        download = mocker.patch.object(thumbnails, "_download", return_value=jpeg)

        assert fetch_thumbnail(URL) == jpeg
        assert fetch_thumbnail(URL) == jpeg

        download.assert_called_once_with(URL)
        assert len(list(kept_in.iterdir())) == 1

    def test_one_kept_that_is_no_picture_fetched_again(self, kept_in, mocker):
        jpeg = _jpeg()
        download = mocker.patch.object(thumbnails, "_download", return_value=jpeg)
        fetch_thumbnail(URL)
        (path,) = kept_in.iterdir()
        path.write_bytes(b"")

        assert fetch_thumbnail(URL) == jpeg

        assert download.call_count == 2
        assert path.read_bytes() == jpeg

    def test_what_could_not_be_had_is_not_kept(self, kept_in, mocker):
        mocker.patch.object(thumbnails, "_download", side_effect=OSError("HTTP 404"))

        with pytest.raises(OSError, match="404"):
            fetch_thumbnail(URL)

        assert not kept_in.exists() or not list(kept_in.iterdir())

    def test_an_answer_of_no_is_not_a_picture(self, mocker):
        mocker.patch(
            "gridplayer.utils.network.fetch_capped", return_value=(404, b"Not Found")
        )
        mocker.patch.object(thumbnails, "_session")

        with pytest.raises(OSError, match="404"):
            thumbnails._download(URL)

    def test_nor_what_is_no_picture(self, mocker):
        mocker.patch(
            "gridplayer.utils.network.fetch_capped",
            return_value=(200, b"<!doctype html><p>Sign in</p>"),
        )
        mocker.patch.object(thumbnails, "_session")

        with pytest.raises(ValueError, match="picture"):
            thumbnails._download(URL)

    def test_nor_one_too_large(self, mocker):
        too_large = b"x" * (thumbnails.MAX_THUMBNAIL_BYTES + 1)
        mocker.patch(
            "gridplayer.utils.network.fetch_capped", return_value=(200, too_large)
        )
        mocker.patch.object(thumbnails, "_session")

        with pytest.raises(ValueError, match="large"):
            thumbnails._download(URL)


class TestMadeTheSizeShown:
    def test_a_wider_one_cut_at_the_sides(self):
        image = QImage(400, 180, QImage.Format_RGB32)
        image.fill(Qt.white)

        assert fitted(image, QSize(160, 90)).size() == QSize(160, 90)

    def test_a_4_3_one_loses_its_top_and_bottom(self):
        image = QImage(480, 360, QImage.Format_RGB32)
        image.fill(Qt.black)
        # bars, as a 4:3 picture of a 16:9 video has them
        for y in range(45):
            for x in range(480):
                image.setPixelColor(x, y, QColor(Qt.white))
                image.setPixelColor(x, 359 - y, QColor(Qt.white))

        cut = fitted(image, QSize(160, 90))

        assert cut.size() == QSize(160, 90)
        assert cut.pixelColor(80, 2).lightness() < 128
        assert cut.pixelColor(80, 87).lightness() < 128


class TestLoader:
    def test_none_until_it_is_fetched(self):
        fetched = []
        loader = ThumbnailLoader(fetched.append, QSize(160, 90))

        assert loader.picture(URL) is None
        QTest.qWait(50)

        assert fetched == []
        assert loader.is_to_fetch(URL)

        loader.stop()

    def test_fetched_it_comes_the_size_shown(self):
        loader = ThumbnailLoader(lambda url: _jpeg(), QSize(160, 90))
        said = []
        loader.loaded.connect(said.append)

        loader.fetch(URL)

        assert _wait_until(lambda: loader.picture(URL) is not None)
        assert loader.picture(URL).size() == QSize(160, 90)
        assert said == [URL]
        assert not loader.is_to_fetch(URL)

        loader.stop()

    def test_asked_again_before_it_came_it_is_fetched_once(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            time.sleep(0.05)
            return _jpeg()

        loader = ThumbnailLoader(fetch, QSize(160, 90))

        loader.fetch(URL)
        assert not loader.is_to_fetch(URL)
        loader.fetch(URL)
        _wait_until(lambda: loader.picture(URL) is not None)
        loader.fetch(URL)

        assert fetched == [URL]

        loader.stop()

    def test_one_that_cannot_be_had_is_not_asked_for_again(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            raise OSError("HTTP 404")

        loader = ThumbnailLoader(fetch, QSize(160, 90))
        said = []
        loader.loaded.connect(said.append)

        loader.fetch(URL)

        assert _wait_until(lambda: loader.is_missing(URL))
        assert said == [URL]
        assert not loader.is_to_fetch(URL)

        loader.fetch(URL)
        QTest.qWait(50)
        assert fetched == [URL]

        loader.stop()

    def test_nor_what_is_no_picture(self):
        loader = ThumbnailLoader(lambda url: b"not a picture", QSize(160, 90))

        loader.fetch(URL)

        assert _wait_until(lambda: loader.is_missing(URL))

        loader.stop()

    def test_stopped_it_fetches_nothing_more(self):
        fetched = []
        loader = ThumbnailLoader(fetched.append, QSize(160, 90))

        loader.stop()
        loader.fetch(URL)
        QTest.qWait(50)

        assert fetched == []

    def test_only_the_last_few_hundred_kept(self, mocker):
        mocker.patch.object(thumbnails, "THUMBNAILS_KEPT", 2)
        loader = ThumbnailLoader(lambda url: _jpeg(), QSize(16, 9))

        for n in range(3):
            loader.fetch(f"{URL}?{n}")
            _wait_until(lambda n=n: loader.picture(f"{URL}?{n}") is not None)

        assert len(loader._pictures) == 2
        assert loader.picture(f"{URL}?0") is None
        # let go of, it is to be fetched again
        assert loader.is_to_fetch(f"{URL}?0")

        loader.stop()

    def test_the_ones_waiting_their_turn_let_go_of(self):
        gate = threading.Event()
        fetched = []

        def fetch(url):
            fetched.append(url)
            gate.wait(5)
            return _jpeg()

        loader = ThumbnailLoader(fetch, QSize(16, 9))
        urls = [f"{URL}?{n}" for n in range(thumbnails.THUMBNAILS_AT_ONCE + 2)]

        for url in urls:
            loader.fetch(url)
        _wait_until(lambda: len(fetched) == thumbnails.THUMBNAILS_AT_ONCE)

        loader.let_go_except(urls[:-2] + urls[-1:])
        gate.set()

        assert _wait_until(lambda: loader.picture(urls[-1]) is not None)
        assert urls[-2] not in fetched
        # let go of, it is to be fetched again
        assert loader.is_to_fetch(urls[-2])

        loader.stop()
