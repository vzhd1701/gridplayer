"""VLC 3 on Windows, made to wait the way Windows does it, as VLC 4 does.

libvlccore 3.0.x looks WaitOnAddress, WakeByAddressAll and WakeByAddressSingle
up in kernel32.dll, as it loads. kernel32 doesn't have them (KernelBase does),
so it always falls back to a stand-in of its own: 32 wait slots for the whole
process, each a lock and a condition variable, where waking any one thread
wakes every thread waiting in its slot. All the VLC threads of a process share
those 32 slots. With a dozen videos in one process, a few hundred threads,
that came to millions of wake-ups a second and up to 13 cores busy doing
nothing. VLC 4 fixed the lookup (commit 905561532d); VLC 3 never got it.

Fixing the name in the DLL isn't enough: the official builds also look up
the condition variable functions only when WaitOnAddress isn't found, and
crash using them otherwise. So VLC is left to load as it always has, and its
three pointers are then pointed at the real functions, before any VLC
instance is made, which is before any thread can be waiting in a slot.

The pointers are found in VLC's own code, each where the result of looking
up its name is stored, and changed only when what they hold is exactly the
stand-in. See docs/findings/VLC_WAITS.md.

The arm64 build, made for Windows 10 1809 and up, imports the three from
Windows itself, as its import table shows: nothing to change there.
"""

import ctypes
import logging
import re
import struct
from typing import NamedTuple

_log = logging.getLogger(__name__)

_NAMES = (b"WaitOnAddress", b"WakeByAddressAll", b"WakeByAddressSingle")

# how far after the name the code stores what GetProcAddress gave
_STORE_WITHIN = 48

_IMAGE_SCN_MEM_EXECUTE = 0x20000000
_MACHINE_AMD64 = 0x8664
_PE32_PLUS = 0x20B


class _Section(NamedTuple):
    start: int
    data: bytes
    is_code: bool


def use_system_waits(vlc_version: str, module_name: str = "libvlccore.dll") -> bool:
    """Point the loaded libvlccore's waits at Windows' own. Whether it did."""

    # VLC 4 looks them up where they are
    if not vlc_version.startswith("3.0."):
        _log.info(f"VLC waits left as they are: VLC {vlc_version}")
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
    kernel32.GetProcAddress.restype = ctypes.c_void_p
    kernel32.GetProcAddress.argtypes = (ctypes.c_void_p, ctypes.c_char_p)

    base = kernel32.GetModuleHandleW(module_name)
    kernelbase = kernel32.GetModuleHandleW("kernelbase.dll")
    if not base or not kernelbase:
        _log.warning(f"VLC waits left as they are: {module_name} not loaded")
        return False

    real = [kernel32.GetProcAddress(kernelbase, name) for name in _NAMES]
    if not all(real):
        # Windows 7: VLC's own slots are all there is
        _log.info("VLC waits left as they are: no WaitOnAddress here")
        return False

    try:
        if set(_NAMES) <= _imported_names(base):
            _log.info("VLC waits on Windows' own WaitOnAddress: VLC imports it")
            return True

        size, sections = _image(base)
        slots = [_slot_of(name, sections) for name in _NAMES]
    except ValueError as err:
        _log.warning(f"VLC waits left as they are: {err}")
        return False

    pointers = [ctypes.c_void_p.from_address(slot) for slot in slots]
    held = [p.value for p in pointers]

    if held == real:
        return True

    # the stand-in: one wake function for both, all three VLC's own code
    is_stand_in = (
        len(set(slots)) == len(slots)
        and held[1] == held[2]
        and held[0] != held[1]
        and all(v is not None and base <= v < base + size for v in held)
    )
    if not is_stand_in:
        _log.warning("VLC waits left as they are: not what VLC 3 sets them to")
        return False

    for pointer, function in zip(pointers, real):
        pointer.value = function

    _log.info("VLC waits on Windows' own WaitOnAddress")

    return True


def _imported_names(base: int) -> set[bytes]:
    """The functions the loaded 64-bit module imports by name, read from
    its import table in memory."""

    def read(rva, size):
        return ctypes.string_at(base + rva, size)

    pe = struct.unpack_from("<I", read(0x3C, 4))[0]
    if struct.unpack_from("<H", read(pe + 24, 2))[0] != _PE32_PLUS:
        raise ValueError("not a 64-bit module")

    # the optional header's data directory 1: the import table
    imports_rva = struct.unpack_from("<I", read(pe + 24 + 120, 4))[0]

    names = set()
    while imports_rva:
        lookup_rva, _, _, dll_name_rva = struct.unpack_from(
            "<IIII", read(imports_rva, 16)
        )
        if not dll_name_rva:
            break
        # the lookup table names each one; the address table beside it is
        # filled with addresses as the module loads
        entry_rva = lookup_rva
        while entry_rva:
            entry = struct.unpack_from("<Q", read(entry_rva, 8))[0]
            if not entry:
                break
            # by name, not by ordinal: a hint, then the name
            if not entry >> 63:
                names.add(ctypes.string_at(base + (entry & 0x7FFFFFFF) + 2))
            entry_rva += 8
        imports_rva += 20

    return names


def _image(base: int) -> tuple[int, list[_Section]]:
    """The loaded module's size and sections, read from memory."""

    pe = base + struct.unpack_from("<I", ctypes.string_at(base + 0x3C, 4))[0]
    machine, n_sections, _, _, _, opt_size = struct.unpack_from(
        "<HHIIIH", ctypes.string_at(pe + 4, 20)
    )
    # only VLC's x64 code is known: its arm64 build imports them
    if machine != _MACHINE_AMD64:
        raise ValueError(f"no stand-in known for machine {machine:#x}")

    opt = pe + 24
    size = struct.unpack_from("<I", ctypes.string_at(opt + 56, 4))[0]

    sections = []
    table = opt + opt_size
    for i in range(n_sections):
        raw = ctypes.string_at(table + i * 40, 40)
        v_size, v_addr = struct.unpack_from("<II", raw, 8)
        flags = struct.unpack_from("<I", raw, 36)[0]
        if v_size:
            start = base + v_addr
            sections.append(
                _Section(
                    start,
                    ctypes.string_at(start, v_size),
                    bool(flags & _IMAGE_SCN_MEM_EXECUTE),
                )
            )

    return size, sections


def _slot_of(name: bytes, sections: list[_Section]) -> int:
    """Where VLC keeps what it looked up by this name."""

    text = name + b"\0"
    found = [
        s.start + i for s in sections if not s.is_code for i in _find_all(s.data, text)
    ]
    if len(found) != 1:
        raise ValueError(f"{len(found)} copies of {name.decode()}")
    name_at = found[0]

    slots = set()
    for s in (s for s in sections if s.is_code):
        slots.update(_slots_x64(s, name_at))

    if len(slots) != 1:
        raise ValueError(f"{len(slots)} places keep {name.decode()}")

    return slots.pop()


def _slots_x64(code: _Section, name_at: int) -> list[int]:
    # lea rdx, [rip + name] ... call GetProcAddress, then the result stored:
    # mov [rip + slot], rax, with test rax, rax before or after it, as
    # compilers have had it either way
    slots = []
    data = code.data
    for i in _find_all(data, b"\x48\x8d\x15"):
        disp = struct.unpack_from("<i", data, i + 3)[0]
        if code.start + i + 7 + disp != name_at:
            continue
        store = _store_after_call(data, i + 7, _X64_CALL, _X64_SKIP, b"\x48\x89\x05")
        if store is not None:
            disp = struct.unpack_from("<i", data, store + 3)[0]
            slots.append(code.start + store + 7 + disp)
    return slots


# call reg, call [address]
_X64_CALL = re.compile(rb"\x41?\xff[\xd0-\xd7]|\xff\x15.{4}", re.DOTALL)
# what may come between the call and the store: test rax, rax
_X64_SKIP = (b"\x48\x85\xc0",)


def _store_after_call(data, start, call, skip, store) -> int | None:
    """Where the result of the first call after start is stored, if only
    the instructions in skip come between them."""

    found = call.search(data, start, start + _STORE_WITHIN)
    if found is None:
        return None

    at = found.end()
    for _ in range(len(skip) + 1):
        if data.startswith(store, at):
            return at
        step = next((s for s in skip if data.startswith(s, at)), None)
        if step is None:
            return None
        at += len(step)

    return None


def _find_all(data: bytes, needle: bytes):
    i = data.find(needle)
    while i != -1:
        yield i
        i = data.find(needle, i + 1)
