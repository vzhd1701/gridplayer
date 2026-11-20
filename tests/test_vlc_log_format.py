import ctypes
import sys
from types import SimpleNamespace

import pytest

from gridplayer.vlc_player import instance

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the UCRT")


def _va_list(*slots):
    # On Windows, x64 and arm64 alike, a va_list points at 8-byte slots
    array = (ctypes.c_uint64 * len(slots))(*slots)
    return array, ctypes.c_void_p(ctypes.addressof(array))


@windows_only
@pytest.mark.parametrize(
    ("size", "text"), [(64, b"hi 42 world 1099511627776"), (8, b"hi 42 w")]
)
def test_the_ucrt_one_formats_as_vsnprintf_does(size, text):
    word = ctypes.c_char_p(b"world")
    _array, args = _va_list(42, ctypes.cast(word, ctypes.c_void_p).value, 2**40)
    buffer = ctypes.create_string_buffer(size)

    written = instance._ucrt_vsnprintf()(buffer, size, b"hi %d %s %zu", args)

    assert written == len(b"hi 42 world 1099511627776")
    assert buffer.value == text


def test_windows_without_msvcrt_vsnprintf_takes_the_ucrt_one(mocker):
    mocker.patch("gridplayer.params.env.IS_WINDOWS", True)
    ucrt = mocker.patch.object(instance, "_ucrt_vsnprintf")
    mocker.patch.object(instance.ctypes, "cdll", SimpleNamespace(msvcrt=object()))

    assert instance._crt_vsnprintf() is ucrt.return_value
