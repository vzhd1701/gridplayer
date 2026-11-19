import ctypes
import struct

import pytest

from gridplayer.utils import libvlc_waits as waits

NAMES_AT = 0x7000
CODE_AT = 0x1000


def _strings():
    data = bytearray(0x100)
    places = {}
    for i, name in enumerate(waits._NAMES):
        places[name] = NAMES_AT + 0x20 * i
        data[0x20 * i : 0x20 * i + len(name) + 1] = name + b"\0"
    return waits._Section(NAMES_AT, bytes(data), is_code=False), places


TEST_RAX = b"\x48\x85\xc0"


def _x64_lookup(at, name_at, slot, is_store_first):
    # lea rdx, [rip + name]; mov rcx, r12; call rbp; then test rax, rax and
    # mov [rip + slot], rax, in the order of VLC up to 3.0.21 or of 3.0.22
    lea = b"\x48\x8d\x15" + struct.pack("<i", name_at - (at + 7))
    middle = b"\x4c\x89\xe1\xff\xd5"
    store_at = at + len(lea) + len(middle) + (0 if is_store_first else 3)
    store = b"\x48\x89\x05" + struct.pack("<i", slot - (store_at + 7))
    return lea + middle + (store + TEST_RAX if is_store_first else TEST_RAX + store)


def _code(pieces):
    data = b""
    for piece in pieces:
        data += piece(CODE_AT + len(data)) + b"\x90" * 8
    return waits._Section(CODE_AT, data, is_code=True)


@pytest.mark.parametrize("is_store_first", [False, True])
def test_finds_where_each_name_is_kept(is_store_first):
    strings, places = _strings()
    slots = {name: 0x9000 + 8 * i for i, name in enumerate(waits._NAMES)}

    pieces = [
        lambda at, n=n: _x64_lookup(at, places[n], slots[n], is_store_first)
        for n in waits._NAMES
    ]

    sections = [_code(pieces), strings]

    for name in waits._NAMES:
        assert waits._slot_of(name, sections) == slots[name]


@pytest.mark.parametrize("version", ["4.0.0-dev", "2.2.8", ""])
def test_only_vlc_3_is_touched(version, monkeypatch):
    def no_reading(*_):
        raise AssertionError("read memory of a VLC it shouldn't touch")

    monkeypatch.setattr(waits, "_image", no_reading)
    monkeypatch.setattr(waits.ctypes, "WinDLL", no_reading, raising=False)

    assert waits.use_system_waits(version) is False


def test_no_lookup_found_is_no_slot():
    strings, _ = _strings()
    code = waits._Section(CODE_AT, b"\x90" * 64, is_code=True)

    with pytest.raises(ValueError, match="0 places"):
        waits._slot_of(b"WaitOnAddress", [code, strings])


def test_two_copies_of_a_name_is_no_slot():
    strings, _ = _strings()
    twice = waits._Section(NAMES_AT + 0x1000, b"WaitOnAddress\0", is_code=False)
    code = waits._Section(CODE_AT, b"\x90" * 64, is_code=True)

    with pytest.raises(ValueError, match="2 copies"):
        waits._slot_of(b"WaitOnAddress", [code, strings, twice])


def test_a_store_too_far_away_is_not_taken():
    strings, places = _strings()
    name_at = places[b"WaitOnAddress"]

    def far(at):
        lea = b"\x48\x8d\x15" + struct.pack("<i", name_at - (at + 7))
        padding = b"\x90" * waits._STORE_WITHIN
        store_at = at + 7 + len(padding) + 3
        store = b"\x48\x85\xc0\x48\x89\x05" + struct.pack("<i", 0x9000 - (store_at + 7))
        return lea + padding + store

    with pytest.raises(ValueError, match="0 places"):
        waits._slot_of(b"WaitOnAddress", [_code([far]), strings])


def test_anything_else_between_call_and_store_is_no_slot():
    strings, places = _strings()
    name_at = places[b"WaitOnAddress"]

    def other(at):
        # call rbp; mov rcx, rax; mov [rip + slot], rax: the result handed on
        # before it is kept, not VLC's lookup as known
        lea = b"\x48\x8d\x15" + struct.pack("<i", name_at - (at + 7))
        store_at = at + 7 + 2 + 3
        return (
            lea
            + b"\xff\xd5"
            + b"\x48\x89\xc1"
            + b"\x48\x89\x05"
            + struct.pack("<i", 0x9000 - (store_at + 7))
        )

    with pytest.raises(ValueError, match="0 places"):
        waits._slot_of(b"WaitOnAddress", [_code([other]), strings])


def test_reads_the_functions_a_module_imports_by_name():
    image = bytearray(0x500)
    pe = 0x40
    struct.pack_into("<I", image, 0x3C, pe)
    struct.pack_into("<H", image, pe + 24, waits._PE32_PLUS)
    struct.pack_into("<I", image, pe + 24 + 120, 0x200)
    # one DLL, then the empty entry that ends the list
    struct.pack_into("<IIIII", image, 0x200, 0x300, 0, 0, 0x280, 0x300)
    image[0x280:0x2A1] = b"api-ms-win-core-synch-l1-2-0.dll\0"
    for i, name in enumerate(waits._NAMES):
        struct.pack_into("<Q", image, 0x300 + 8 * i, 0x400 + 0x20 * i)
        image[0x402 + 0x20 * i : 0x403 + 0x20 * i + len(name)] = name + b"\0"
    # and one by ordinal, which has no name
    struct.pack_into("<Q", image, 0x300 + 8 * len(waits._NAMES), 1 << 63 | 5)

    buffer = (ctypes.c_char * len(image)).from_buffer(image)

    assert waits._imported_names(ctypes.addressof(buffer)) == set(waits._NAMES)
