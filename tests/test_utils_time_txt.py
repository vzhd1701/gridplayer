import pytest

from gridplayer.utils.time_txt import get_time_txt


@pytest.mark.parametrize(
    "time_int,time_str",
    [
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
    pass


@pytest.mark.parametrize(
    "time_int,max_time_int,time_str",
    [
        (0, 60, "00:00"),
        (0, 3600, "00:00:00"),
        (0, 86400, "00:00:00"),
    ],
)
def test_get_time_txt_maxtime(time_int, max_time_int, time_str):
    assert get_time_txt(time_int, max_time_int) == time_str
    pass


@pytest.mark.parametrize(
    "time_int,time_str",
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
    pass
