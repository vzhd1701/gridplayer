"""What is kept so it is not downloaded again: on disk up to a size, the
things used longest ago going first, or only in memory; cleared; made to fit
the settings when they change; and where on disk it goes."""

import os
import time
from pathlib import Path

import pytest
from PyQt5.QtCore import QStandardPaths

from gridplayer.params.static import CacheMode
from gridplayer.utils import app_dir, cache

KIND = "thumbnails"


class _Settings:
    """The two settings the cache goes by, for a test to change."""

    def __init__(self):
        self.mode = CacheMode.DISK
        self.max_bytes = 64 * cache.MB


@pytest.fixture
def settings(monkeypatch):
    settings = _Settings()

    monkeypatch.setattr(cache, "_mode", lambda: settings.mode)
    monkeypatch.setattr(cache, "_max_bytes", lambda: settings.max_bytes)

    return settings


@pytest.fixture
def root(tmp_path, monkeypatch, settings):
    """A cache of its own, nothing kept in it yet in this run."""

    root = tmp_path / "cache"

    monkeypatch.setattr(cache, "cache_root", lambda: root)
    monkeypatch.setattr(cache, "_disk_bytes", None)
    monkeypatch.setattr(cache, "_memory", type(cache._memory)())
    monkeypatch.setattr(cache, "_memory_bytes", 0)

    # what is put off to a thread done at once, for a test to see
    monkeypatch.setattr(cache, "_in_background", lambda work: work())

    return root


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _put(root: Path, name: str, size: int, age: int, kind: str = KIND) -> Path:
    """A file kept before, used this many seconds ago."""

    path = root / kind / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)

    stamp = time.time() - age
    os.utime(path, (stamp, stamp))

    return path


class TestOnDisk:
    def test_kept_and_had_again(self, root):
        cache.keep(KIND, "a", b"data")

        assert cache.cached(KIND, "a") == b"data"
        assert [path.parent.name for path in _files(root)] == [KIND]

    def test_nothing_for_what_was_not_kept(self, root):
        assert cache.cached(KIND, "a") is None

    def test_used_again_it_is_kept_longer(self, root):
        cache.keep(KIND, "a", b"data")
        (path,) = _files(root)
        os.utime(path, (1, 1))

        cache.cached(KIND, "a")

        assert path.stat().st_mtime > 1

    def test_written_whole_or_not_at_all(self, root, mocker):
        mocker.patch.object(Path, "replace", side_effect=OSError("in use"))

        cache.keep(KIND, "a", b"data")

        # nor anything half written left about
        assert _files(root) == []
        assert cache.cached(KIND, "a") is None

    def test_forgotten(self, root):
        cache.keep(KIND, "a", b"data")

        cache.forget(KIND, "a")

        assert cache.cached(KIND, "a") is None
        assert _files(root) == []


class TestSizeOnDisk:
    def test_the_ones_used_longest_ago_go_first(self, root, settings):
        settings.max_bytes = 300
        for age, name in enumerate(("new", "old", "older")):
            _put(root, name, 100, age=(age + 1) * 1000)

        cache.keep(KIND, "newest", b"x" * 100)

        assert [path.name for path in _files(root)] == sorted(
            [cache._path(KIND, "newest").name, "new"]
        )

    def test_cut_as_it_grows_not_once_a_run(self, root, settings):
        settings.max_bytes = 1000

        for n in range(30):
            cache.keep(KIND, str(n), b"x" * 100)

            assert sum(path.stat().st_size for path in _files(root)) <= 1000

        assert cache.cached(KIND, "29") is not None

    def test_cut_to_less_than_its_size_not_to_it(self, root, settings):
        settings.max_bytes = 1000
        for n in range(10):
            _put(root, f"old{n}", 100, age=1000 + n)

        cache.keep(KIND, "new", b"x" * 100)

        kept = sum(path.stat().st_size for path in _files(root))
        assert kept <= 1000 * cache.TRIMMED_TO

    def test_none_cut_while_under(self, root, settings):
        settings.max_bytes = 1000
        _put(root, "old", 100, age=1000)

        cache.keep(KIND, "new", b"x" * 100)

        assert len(_files(root)) == 2

    def test_every_kind_counted_together(self, root, settings):
        settings.max_bytes = 250
        _put(root, "old", 100, age=2000, kind="other")
        _put(root, "less old", 100, age=1000)

        cache.keep(KIND, "new", b"x" * 100)

        assert (root / KIND / "less old").exists()
        assert not (root / "other" / "old").exists()


class TestInMemory:
    def test_nothing_on_disk(self, root, settings):
        settings.mode = CacheMode.MEMORY

        cache.keep(KIND, "a", b"data")

        assert cache.cached(KIND, "a") == b"data"
        assert _files(root) == []

    def test_up_to_a_size_of_its_own(self, root, settings, monkeypatch):
        settings.mode = CacheMode.MEMORY
        monkeypatch.setattr(cache, "MAX_MEMORY_BYTES", 250)

        for key in ("a", "b", "c"):
            cache.keep(KIND, key, b"x" * 100)

        assert cache.cached(KIND, "a") is None
        assert cache.cached(KIND, "c") is not None

    def test_used_again_it_is_kept_longer(self, root, settings, monkeypatch):
        settings.mode = CacheMode.MEMORY
        monkeypatch.setattr(cache, "MAX_MEMORY_BYTES", 250)

        cache.keep(KIND, "a", b"x" * 100)
        cache.keep(KIND, "b", b"x" * 100)
        cache.cached(KIND, "a")
        cache.keep(KIND, "c", b"x" * 100)

        assert cache.cached(KIND, "a") is not None
        assert cache.cached(KIND, "b") is None

    def test_forgotten(self, root, settings):
        settings.mode = CacheMode.MEMORY
        cache.keep(KIND, "a", b"data")

        cache.forget(KIND, "a")

        assert cache.cached(KIND, "a") is None
        assert cache.kept_bytes() == 0


class TestCleared:
    def test_what_it_comes_to_on_disk_and_in_memory(self, root, settings):
        cache.keep(KIND, "a", b"x" * 100)
        settings.mode = CacheMode.MEMORY
        cache.keep(KIND, "b", b"x" * 50)

        assert cache.kept_bytes() == 150

    def test_emptied_on_disk_and_in_memory(self, root, settings):
        cache.keep(KIND, "a", b"x" * 100)
        settings.mode = CacheMode.MEMORY
        cache.keep(KIND, "b", b"x" * 50)

        cache.clear()

        assert _files(root) == []
        assert cache.cached(KIND, "b") is None
        assert cache.kept_bytes() == 0

    def test_nothing_there_nothing_done(self, root):
        cache.clear()

        assert cache.kept_bytes() == 0


class TestSettingsChanged:
    def test_kept_in_memory_the_disk_emptied(self, root, settings):
        cache.keep(KIND, "a", b"data")
        settings.mode = CacheMode.MEMORY

        cache.apply_settings()

        assert _files(root) == []

    def test_a_smaller_size_cut_to_at_once(self, root, settings):
        for n in range(10):
            _put(root, f"old{n}", 100, age=1000 + n)
        settings.max_bytes = 500

        cache.apply_settings()

        kept = sum(path.stat().st_size for path in _files(root))
        assert kept <= 500 * cache.TRIMMED_TO
        # the ones used last are the ones left
        assert (root / KIND / "old0").exists()

    def test_on_disk_again_the_memory_let_go_of(self, root, settings):
        settings.mode = CacheMode.MEMORY
        cache.keep(KIND, "a", b"data")
        settings.mode = CacheMode.DISK

        cache.apply_settings()

        assert cache.kept_bytes() == 0


class TestWhere:
    def test_the_systems_folder_for_caches(self, monkeypatch):
        monkeypatch.delenv(app_dir.ENV_USER_DATA_DIR, raising=False)
        monkeypatch.setattr(app_dir, "is_portable", lambda: False)

        expected = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)

        assert app_dir.get_app_cache_dir() == Path(expected)

    def test_in_the_data_folder_when_that_was_moved(self, tmp_path, monkeypatch):
        monkeypatch.setenv(app_dir.ENV_USER_DATA_DIR, str(tmp_path))

        assert app_dir.get_app_cache_dir() == tmp_path / "cache"

    def test_in_the_data_folder_when_portable(self, tmp_path, monkeypatch):
        monkeypatch.delenv(app_dir.ENV_USER_DATA_DIR, raising=False)
        monkeypatch.setattr(app_dir, "is_portable", lambda: True)
        monkeypatch.setattr(app_dir, "get_app_data_dir", lambda: tmp_path)

        assert app_dir.get_app_cache_dir() == tmp_path / "cache"
