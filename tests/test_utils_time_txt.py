import pytest

from gridplayer.utils.time_txt import (
    get_time_txt,
    ms_time_txt,
    parse_time_txt,
    timestamp_txt,
)


@pytest.mark.parametrize(
    ("time_int", "time_str"),
    [
        (-100000, "0:00"),
        (-1, "0:00"),
        (0, "0:00"),
        (59, "0:59"),
        (60, "01:00"),
        (3599, "59:59"),
        (3600, "01:00:00"),
        (86399, "23:59:59"),
        (86400, "1d 0:00"),
        (86400 + 60, "1d 01:00"),
        (86400 * 2 - 1, "1d 23:59:59"),
        (86400 * 2, "2d 0:00"),
    ],
)
def test_get_time_txt(time_int, time_str):
    assert get_time_txt(time_int) == time_str


@pytest.mark.parametrize(
    ("time_int", "max_time_int", "time_str"),
    [
        (0, 60, "00:00"),
        (0, 3600, "00:00:00"),
        (0, 86400, "00:00:00"),
    ],
)
def test_get_time_txt_maxtime(time_int, max_time_int, time_str):
    assert get_time_txt(time_int, max_time_int) == time_str


@pytest.mark.parametrize(
    ("time_int", "time_str"),
    [
        (0, "0:00"),
        (59, "0:59"),
        (60, "1:00"),
        (3599, "59:59"),
        (3600, "1:00:00"),
        (86399, "23:59:59"),
        (86400, "1d 0:00"),
        (86400 + 60, "1d 1:00"),
        (86400 * 2 - 1, "1d 23:59:59"),
        (86400 * 2, "2d 0:00"),
    ],
)
def test_get_time_txt_strip(time_int, time_str):
    assert get_time_txt(time_int, strip=True) == time_str


@pytest.mark.parametrize(
    ("time_str", "time_ms"),
    [
        ("3:27", 207_000),
        ("03:27.4", 207_400),
        ("03:27,45", 207_450),
        (" 3:27 ", 207_000),
        ("1:02:03", 3_723_000),
        ("1:02:03.456", 3_723_456),
        ("45", 45_000),
        ("90", 90_000),
        ("0", 0),
        # as shown, and as typed back unchanged
        (ms_time_txt(207_412, 596_000), 207_412),
    ],
)
def test_parse_time_txt(time_str, time_ms):
    assert parse_time_txt(time_str) == time_ms


@pytest.mark.parametrize(
    "time_str", ["", "x", "3:60", "1:60:00", "3:27:", ":27", "-5", "3.27.4", "1:2:3:4"]
)
def test_parse_time_txt_not_a_time(time_str):
    assert parse_time_txt(time_str) is None


@pytest.mark.parametrize(
    ("time_ms", "length_ms", "time_str"),
    [
        (207_400, 596_000, "3:27"),
        (6_000, 596_000, "0:06"),
        (6_000, 4_000_000, "0:00:06"),
        (3_723_000, 4_000_000, "1:02:03"),
        # past the end of a shorter cut, still in hours
        (3_723_000, 596_000, "1:02:03"),
    ],
)
def test_timestamp_txt(time_ms, length_ms, time_str):
    assert timestamp_txt(time_ms, length_ms) == time_str


@pytest.mark.parametrize(
    ("time_ms", "length_ms", "time_str"),
    [
        (207_400, 596_000, "3:27.400"),
        (6_005, 596_000, "0:06.005"),
        (6_000, 4_000_000, "0:00:06.000"),
        (3_723_999, 4_000_000, "1:02:03.999"),
    ],
)
def test_timestamp_txt_to_the_millisecond(time_ms, length_ms, time_str):
    assert timestamp_txt(time_ms, length_ms, is_precise=True) == time_str


@pytest.mark.parametrize(
    ("time_ms", "length_ms", "strip", "time_str"),
    [
        (207_412, 596_000, False, "03:27.412"),
        (207_412, None, True, "3:27.412"),
        (5, 596_000, False, "00:00.005"),
        (3_723_999, 4_000_000, False, "01:02:03.999"),
        (-20, 596_000, False, "00:00.000"),
    ],
)
def test_ms_time_txt(time_ms, length_ms, strip, time_str):
    assert ms_time_txt(time_ms, length_ms, strip=strip) == time_str
