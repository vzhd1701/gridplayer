from types import SimpleNamespace

import pytest

from gridplayer.utils import glibc_malloc


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
    monkeypatch.setattr(glibc_malloc.os, "environ", fake)
    return fake


@pytest.fixture
def libc(monkeypatch, environ):
    def use(mallopt):
        monkeypatch.setattr(
            glibc_malloc.ctypes, "CDLL", lambda _: SimpleNamespace(mallopt=mallopt)
        )
        return mallopt

    return use


def test_limits_this_process_and_the_ones_it_starts(libc, environ):
    mallopt = libc(_Mallopt(1))

    assert glibc_malloc.limit_malloc_arenas() is True

    assert mallopt.calls == [(-8, 8)]
    assert environ["MALLOC_ARENA_MAX"] == "8"


def test_leaves_a_limit_someone_set(libc, environ):
    mallopt = libc(_Mallopt(1))
    environ["MALLOC_ARENA_MAX"] = "1"

    assert glibc_malloc.limit_malloc_arenas() is False

    assert mallopt.calls == []
    assert environ["MALLOC_ARENA_MAX"] == "1"


def test_a_libc_that_takes_no_limit_is_left_alone(libc, environ):
    libc(_Mallopt(0))

    assert glibc_malloc.limit_malloc_arenas() is False

    assert "MALLOC_ARENA_MAX" not in environ


def test_no_mallopt_is_left_alone(libc, environ, monkeypatch):
    monkeypatch.setattr(glibc_malloc.ctypes, "CDLL", lambda _: SimpleNamespace())

    assert glibc_malloc.limit_malloc_arenas() is False

    assert "MALLOC_ARENA_MAX" not in environ


class _Trim:
    def __init__(self):
        self.calls = []

    def __call__(self, pad):
        self.calls.append(pad)
        return 1


class _Timer:
    made = []

    def __init__(self, delay, function):
        self.delay = delay
        self.function = function
        self.daemon = False
        self.is_started = False
        _Timer.made.append(self)

    def start(self):
        self.is_started = True


@pytest.fixture
def trim(monkeypatch):
    trim = _Trim()
    _Timer.made = []
    monkeypatch.setattr(glibc_malloc.sys, "platform", "linux")
    monkeypatch.setattr(glibc_malloc.threading, "Timer", _Timer)
    monkeypatch.setattr(glibc_malloc, "_pending_trim", None)
    monkeypatch.setattr(
        glibc_malloc.ctypes, "CDLL", lambda _: SimpleNamespace(malloc_trim=trim)
    )
    return trim


def test_freed_memory_given_back_a_moment_later(trim):
    glibc_malloc.give_back_freed_memory()

    (timer,) = _Timer.made
    assert timer.is_started
    assert timer.daemon
    assert timer.delay == glibc_malloc.GIVE_BACK_AFTER_S
    assert trim.calls == []

    timer.function()

    assert trim.calls == [0]


def test_videos_closing_together_give_back_once(trim):
    glibc_malloc.give_back_freed_memory()
    glibc_malloc.give_back_freed_memory()

    assert len(_Timer.made) == 1

    _Timer.made[0].function()
    glibc_malloc.give_back_freed_memory()

    assert len(_Timer.made) == 2


def test_nothing_given_back_elsewhere(trim, monkeypatch):
    monkeypatch.setattr(glibc_malloc.sys, "platform", "win32")

    glibc_malloc.give_back_freed_memory()

    assert _Timer.made == []


def test_no_malloc_trim_is_left_alone(trim, monkeypatch):
    monkeypatch.setattr(glibc_malloc.ctypes, "CDLL", lambda _: SimpleNamespace())

    glibc_malloc.give_back_freed_memory()
    _Timer.made[0].function()
