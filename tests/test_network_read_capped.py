from types import SimpleNamespace

from gridplayer.utils import network


class _Response:
    """What came, a chunk at a time, and how much of it came over the wire:
    less than it is, where it came compressed."""

    def __init__(self, chunks, headers=None, wire_ratio=None):
        self._chunks = chunks
        self.headers = headers or {}
        self._sent = 0
        self._wire_ratio = wire_ratio

        if wire_ratio is not None:
            self.raw = SimpleNamespace(tell=lambda: self._sent)

    def iter_content(self, _size):
        for chunk in self._chunks:
            self._sent += int(len(chunk) * self._wire_ratio) if self._wire_ratio else 0
            yield chunk


def _told(response, limit=10**9):
    told = []

    read = network._read_capped(
        response, limit, on_read=lambda count, of: told.append((count, of))
    )

    return read, told


def test_how_much_of_how_much_is_told():
    response = _Response([b"a" * 10, b"b" * 10], {"Content-Length": "20"}, 1)

    read, told = _told(response)

    assert read == b"a" * 10 + b"b" * 10
    assert told == [(10, 20), (20, 20)]


def test_what_came_compressed_is_counted_as_it_was_sent():
    response = _Response(
        [b"a" * 100, b"b" * 100],
        {"Content-Length": "50", "Content-Encoding": "gzip"},
        0.25,
    )

    _read, told = _told(response)

    assert told == [(25, 50), (50, 50)]


def test_of_how_much_is_not_known_where_it_is_not_said():
    response = _Response([b"a" * 10], {}, 1)

    _read, told = _told(response)

    assert told == [(10, None)]


def test_what_was_read_into_is_counted_where_the_wire_is_out_of_sight():
    response = _Response([b"a" * 10, b"b" * 5], {"Content-Length": "15"})

    _read, told = _told(response)

    assert told == [(10, 15), (15, 15)]


def test_a_length_that_makes_no_sense_is_no_length():
    response = _Response([b"a"], {"Content-Length": "lots"}, 1)

    _read, told = _told(response)

    assert told == [(1, None)]
