from types import SimpleNamespace

import pytest

from gridplayer.utils import malloc_arenas


class _Mallopt:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, option, value):
        self.calls.append((option, value))
        return self.result


@pytest.fixture
def environ(monkeypatch):
    fake = {}
    monkeypatch.setattr(malloc_arenas.os, "environ", fake)
    return fake


@pytest.fixture
def libc(monkeypatch, environ):
    def use(mallopt):
        monkeypatch.setattr(
            malloc_arenas.ctypes, "CDLL", lambda _: SimpleNamespace(mallopt=mallopt)
        )
        return mallopt

    return use


def test_limits_this_process_and_the_ones_it_starts(libc, environ):
    mallopt = libc(_Mallopt(1))

    assert malloc_arenas.limit_malloc_arenas() is True

    assert mallopt.calls == [(-8, 8)]
    assert environ["MALLOC_ARENA_MAX"] == "8"


def test_leaves_a_limit_someone_set(libc, environ):
    mallopt = libc(_Mallopt(1))
    environ["MALLOC_ARENA_MAX"] = "1"

    assert malloc_arenas.limit_malloc_arenas() is False

    assert mallopt.calls == []
    assert environ["MALLOC_ARENA_MAX"] == "1"


def test_a_libc_that_takes_no_limit_is_left_alone(libc, environ):
    libc(_Mallopt(0))

    assert malloc_arenas.limit_malloc_arenas() is False

    assert "MALLOC_ARENA_MAX" not in environ


def test_no_mallopt_is_left_alone(libc, environ, monkeypatch):
    monkeypatch.setattr(malloc_arenas.ctypes, "CDLL", lambda _: SimpleNamespace())

    assert malloc_arenas.limit_malloc_arenas() is False

    assert "MALLOC_ARENA_MAX" not in environ
