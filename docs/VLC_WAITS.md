# VLC 3's waits on Windows: why one process with many videos burns the CPU

Found 2026-11-09 on the `mpv` branch, from Software VLC in a single process taking about 80% of a 16-thread CPU with a dozen small
videos, where multi-process took 15-20%. That gap is why GridPlayer got its multi-process drivers in the first place. Fixed by
`gridplayer/utils/libvlc_waits.py` (plan item 10.26 in `MPV_PLAN.md`).

## What happens

VLC 3's threads (reading, decoding, video and audio output, timers) sleep and wake each other through `vlc_addr_wait` and
`vlc_addr_broadcast`, VLC's futex. On Windows those call `WaitOnAddress`, `WakeByAddressAll` and `WakeByAddressSingle`, which libvlccore
looks up in its `DllMain` as it loads (`src/win32/thread.c`):

```c
HANDLE h = GetModuleHandle(TEXT("kernel32.dll"));
...
if (!LOOKUP(WaitOnAddress) || !LOOKUP(WakeByAddressAll) || !LOOKUP(WakeByAddressSingle))
{
    if (!LOOKUP(InitializeConditionVariable) || ...)   /* builds for Windows XP */
    ...
    vlc_wait_addr_init();
    WaitOnAddress_ = WaitOnAddressFallback;
    WakeByAddressAll_ = WakeByAddressFallback;
    WakeByAddressSingle_ = WakeByAddressFallback;
}
```

`kernel32.dll` doesn't have them: they are in `KernelBase.dll` (and the `api-ms-win-core-synch-l1-2-0` API set). So the lookup always
fails, on every Windows, and VLC always uses its stand-in: 32 slots for the whole process, each a critical section and a condition
variable, an address going to slot `(address >> 3) % 32`. A wake on any address wakes every thread sleeping in that slot
(`WakeAllConditionVariable`; VLC's own comment: "Since there are more than one wait address per bucket, all threads must be woken up
:-/"). They each check their own address, find nothing changed, and go back to sleep.

All the VLC threads of a process share the 32 slots. A VLC process of the multi-process drivers holds 4 videos (`player/video_driver_players`),
so a slot holds a thread or two. A single process with 15 videos holds about 270 VLC threads, 8 or more to a slot, and every wake there
wakes them all.

**Seen**, 15 of the user's clips (720x960 16 fps and 1056x608 24 fps, 6 with sound), Software VLC in a single process, real window:

- About 2.5 million context switches a second in the process, every kind of VLC thread waking 40,000-60,000 times a second, all in
  `SleepConditionVariableCS` called from libvlccore. A low run: about 100,000.
- 300-450% of a core in the kernel alone.
- Real work, not an accounting artifact: the CPU cycles the process used (`QueryProcessCycleTime`) match the time Windows charged it.
- Uneven from run to run, the same code and clips: 185% to 1370% of a core (1300% is the 80% of 16 threads), 7 runs of 13 above 600%.
  Each run kept its level from start to end. Which addresses share a slot changes with where things land in memory, run to run.
- Multi-process, the same clips: 210-270%.

**Only Windows.** Linux uses futexes, macOS pthreads. Every VLC driver on Windows has it, Hardware too (a Hardware single-process run:
517%); multi-process keeps it small by keeping the threads of a process few. Raising "videos per process" would bring it back.

## VLC 4

Fixed upstream in commit `905561532d` (2021-09-24, "win32: thread: use the proper DLL to get the system WaitOnAddress"): it looks them up
in `api-ms-win-core-synch-l1-2-0.dll`, and says so: "We won't be limited to 32 futeces on platforms that have the API… MSDN says it's in
Kernel32.dll but it's not." It was never brought to 3.0.x: the 3.0.21 and 3.0.24 tags still ask `kernel32.dll`. VLC 4 isn't released, and
its libvlc API differs from VLC 3's, which our vendored bindings are for.

## What doesn't work

- **Renaming the module in the DLL** (`kernel32.dll` to `kernelbase`, which fits in the same space; Windows adds the `.dll`). The lookup
  then works, and `DllMain` crashes ("A dynamic link library (DLL) initialization routine failed"). The official 3.0.24 builds target
  Windows XP, so the condition variable functions are pointers too, looked up only inside the branch above, when `WaitOnAddress` *isn't*
  found. Found, they stay empty, and `InitializeConditionVariable(&super_variable)` a few lines on calls nothing. That path has never run
  in a VLC 3 Windows build, which is likely why nobody noticed the wrong DLL. Making it work needs a change to the code, per build.
- **Changing the name in memory before VLC uses it**: the lookup is in `DllMain`, done before Python gets the module back.
- **Building VLC ourselves**: a MinGW cross-build with all its contribs, for every architecture and every VLC security release, for a
  one-line change.
- **One VLC instance for all single-process videos**: the slots are per process, not per instance. Tried: still 1368%.
- **Fewer decoder threads** (`--avcodec-threads=2`): ffmpeg's threads use their own condition variables, not VLC's slots. Looked
  lower over 4 runs, but the runs are too uneven to tell.

## The fix

VLC loads as it always has: the stand-in branch runs and fills every pointer, the condition variable ones too. Then, before any VLC
instance is made, so before any VLC thread can be asleep in a slot, `use_system_waits()` points `WaitOnAddress_`, `WakeByAddressAll_` and
`WakeByAddressSingle_` at the real functions in `KernelBase.dll`. It runs on Windows in every process that loads VLC, right after the
import (`gridplayer/utils/libvlc_fixer.py`), and logs "VLC waits on Windows' own WaitOnAddress".

**Finding the three pointers** without addresses known in advance, in the loaded module:

- The section table is read from memory. Each name, `"WaitOnAddress\0"` and the others, must be found exactly once in the data.
- In the code, the instruction that hands that name to `GetProcAddress`, then the first call within 48 bytes, then the store of its
  result: where the pointer lives. Between the call and the store only the `test` of the result may come (and on 32-bit `sub esp, 8`),
  as the compilers have put them either way. 64-bit: `lea rdx, [rip+name]` … `call` … `mov [rip+slot], rax`. 32-bit:
  `mov dword ptr [esp+4], name` … `call` … `mov [slot], eax`. Exactly one place each.

**Only VLC 3.0.x**, by `libvlc_get_version()`, which answers before any instance is made: VLC 4 looks them up where they are.

**Changing them only when they hold the stand-in:** three different places, both wake pointers holding the same function (VLC sets both
to `WakeByAddressFallback`), the wait pointer another, all three inside libvlccore. Anything else, a VLC built differently or one that
already has it right, is left alone, with a warning in the log. So a VLC whose code no longer looks like this stays as slow as it was,
and doesn't break. On Windows 7, with no `WaitOnAddress` in `KernelBase`, nothing changes.

VLC's 32 slots stay made and unused. At exit VLC doesn't free them, as they're no longer its stand-in; the process is ending.

**Which VLC versions:** every official Windows build of 3.0.0, 3.0.4, 3.0.8, 3.0.11, 3.0.12, 3.0.14, 3.0.16, 3.0.17.4, 3.0.18 to 3.0.24,
64-bit and 32-bit, has the bug, and in each the three pointers are found, three different places in `.bss`, and the stand-in branch
stores one function in both wake pointers and another in the wait one, as the check at runtime expects. 3.0.22 was built with a newer
toolchain (linker 2.39 against 2.27) that stores the result before testing it, which the first version of the matching missed. Checked
by reading the DLLs as data, `libvlccore.dll` alone fetched out of each official zip. Loaded and swapped for real: 3.0.24, 64-bit and
32-bit, and 3.0.20 64-bit (see Results). The pointers: 3.0.0 `.bss+0x1870/1868/1860` (64-bit), 3.0.4-3.0.16 `+0x17f0/17e8/17e0`, 3.0.17.4-3.0.24 `+0x1810/1808/1800`;
32-bit `+0xf48/f44/f40`, `+0xee8/ee4/ee0`, `+0xf08/f04/f00`.

## Results

The same 15 clips, Software VLC in a single process, silent, real window on another virtual desktop:

| | Runs | CPU, % of a core | Context switches a second |
|---|---:|---|---|
| Before | 13 | 185-1370, 7 runs above 600 | 100,000 to 2.9 million |
| After | 6 | 141-221 (cycles: 174-176) | 6,600-7,200 |
| Multi-process, before | 2 | 207-269 | |

All runs showed the clips' full frame rate (19.2 fps on average across them).

32-bit GridPlayer (from source, 32-bit Python 3.12) with the official 32-bit 3.0.24, the same clips and setup, swap on and off in turn:

| | Runs | CPU, % of a core | Context switches a second |
|---|---:|---|---|
| Without the swap | 4 | 335-1402 | 210,000 to 2.2 million |
| With it | 4 | 138-256 | 6,000-17,000 |

3.0.20 64-bit, the same clips, one run each: 176% of a core and about 6,400 switches a second with the swap, 480% and 580,000
without, both at the full frame rate.

Run from source, the 32-bit `python.exe` has only 2 GB of address space, and 15 videos in one process fill it: some frame buffers
failed to allocate as the videos loaded, with the swap and without (plan item 10.27). The packaged 32-bit `GridPlayer.exe` gets 4 GB,
where the same 15 peak at 2.3-2.6 GB and play.

Also with the fix:

- Hardware VLC in a single process, the same clips, 2 runs: 38-46% of a core, about 8,000 switches a second (one run before: 517%).
- Multi-process Software VLC, the 9 clips without sound, 2 runs: 135-201%. Its VLC processes wait in `RtlWaitOnAddress` too, seen
  in their stacks. Their "VLC waits on Windows' own WaitOnAddress" line doesn't reach the app's log: VLC loads in them before their
  logging is handed to the app.

## Measuring it

The runs swing so much that one or two of them tell nothing: compare several. What was used, in the session's scratchpad:

- `tests/real_app/bench/grid_bench.py` through a wrapper scenario that adds the user's log levels and, so nothing is heard, opens the app's
  own audio session with a silent clip and mutes it (`pycaw`) before any video plays. A VLC process of the multi-process drivers has an
  audio session of its own, so those were measured with clips without sound.
- A watcher logging, every 2 s, the CPU Windows charges, the CPU cycles (`QueryProcessCycleTime` over what one busy core does here),
  context switches (`psutil`) and the timer resolution.
- Per thread: context switches from `NtQuerySystemInformation(SystemProcessInformation)`, and stacks taken by suspending each thread and
  walking it with `dbghelp` (`StackWalk64`). libvlccore exports few names, so its frames are named after the nearest export, which is not
  the function; what tells is the call into `SleepConditionVariableCS` (the stand-in) or `RtlWaitOnAddress` (the real thing).
