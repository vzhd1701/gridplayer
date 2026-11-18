# Qt 6: plan and progress

The move from PyQt5 (Qt 5.15) to PyQt6 on Qt 6.12, on the `qt6` branch. This file says what changes, in what order,
and how each step is checked. Tick an item only once it has been seen working.

**Status: planned 2026-11-18, nothing built yet.**

| | Stage | State |
|---|---|---|
| 0 | Baseline on PyQt5: tests, scenarios, benches, screenshots | **done 2026-11-18** but the Macs (before stage 5) and benches (stage 3) |
| 1 | Rewrites that work on both: full enum names, `exec()`, flag values | **done 2026-11-18** |
| 2 | The switch: PyQt6 6.12, imports, removed APIs, events; tests pass | **done 2026-11-18**, uncommitted |
| 3 | Windows: DPI, native windows, GL, look, input | not started |
| 4 | Linux: X11, Wayland, D-Bus | not started |
| 5 | macOS | not started |
| 6 | Translations: pylupdate6 | not started |
| 7 | Packaging and CI | not started |
| 8 | Clean-up and docs | not started |

## Decisions

- **Your call (2026-11-18): PyQt6**, not PySide6, and no layer that runs on both (`qtpy`). The code is shaped for PyQt
  (`pyqtSignal`, `sip.isdeleted`, a slot's exception ending the run as AGENTS.md says), and the app is GPL already.
- **Your call (2026-11-18): Qt 6.12**, the newest, which is also an LTS (released 2026-09-30, five years of maintenance;
  Qt's blog). The LTS label matters less with PyQt6: PyPI's PyQt6-Qt6 6.8 stopped at 6.8.2 (Feb 2025), PyQt6 6.8 at 6.8.1,
  as later LTS fixes are Qt's paid ones, and Riverbank fixes only the newest PyQt6. Pinned exactly (`PyQt6==6.12.1`,
  `PyQt6-Qt6==6.12.0` at the start), moved to each 6.12 patch as it comes.
- **6.11 for everything was looked at and turned down (2026-11-18).** For 6.11: macOS 13 instead of 14, and one Qt for
  every package. Against: 6.11 isn't an LTS, its open-source patches end now that 6.12 is out, and PyQt6 6.11 had one
  release (6.11.0) and gets no more. What 6.12 changes for this app is small (What's New in Qt 6.12): on Windows, text
  antialiasing by each font's GASP table and a colour space per screen; on macOS, `grabWindow` by ScreenCaptureKit (the
  app doesn't grab, only `tests/real_app/composed.py`, and not on macOS) and native embedding fixes; on Linux,
  `openUrl` through the portal and X11 tooltips not recreated each time. No changes to QtDBus, OpenGL or Fusion are listed.
- **Your call (2026-11-18): macOS 14 and up**, from PyQt6 6.12.1's `macosx_14_0` wheel (Qt's own page: 14.4).
- **Your call (2026-11-18): the Snap takes PyQt6 and Qt from the wheels**, as the AppImage does. Ubuntu 24.04's
  `python3-pyqt6` is built for Qt 6.4, so the Qt 5 way (PyQt from debs against the kde-neon extension's Qt) doesn't carry
  over. The extension stays only if it's still needed for themes and fonts (seen in stage 7).
- **Your call (2026-11-18): the rewrite scripts are kept in `scripts/qt6_port/`** while the move goes on, so a commit can
  be checked by running its script again, and removed in stage 8.
- **Your call (2026-11-18): 32-bit Windows goes.** Qt 6 has no 32-bit Windows build.
- **Your call (2026-11-18): all on `qt6`**, nothing on `master`. The rewrites that work on PyQt5 too come first, and are
  tested on PyQt5, so a later break is Qt 6's and not the rewrite's.
- **Your call (2026-11-18): the translation scripts may change** for this move (`scripts/translations/*`), an exception
  to the AGENTS.md rule. The `.ts`/`.qm` files themselves still aren't touched, and no `just translations-*` recipe is run.
- Taken over from `MPV_PLAN.md` 12.1: **the Snap moves to core24 with Qt 6** (and gets libmpv then), and **an arm64
  AppImage comes with Qt 6** (PyQt6 has `manylinux_2_39_aarch64` wheels).
- **Your call (2026-11-18): the Flatpak on Qt 6.11** (KDE runtime and PyQt BaseApp 6.11) until Flathub has a 6.12
  branch; the other packages on 6.12. So **the code uses nothing newer than Qt 6.11**; 6.12 adds nothing this app needs.

## Rules that hold in every stage

- Each stage ends with the app working: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and the
  stage's real-app scenarios. From stage 2 on, that's on PyQt6; stage 1 on PyQt5.
- No commits unless you ask; one or more per stage when you do.
- `vlc.py` and `mpv.py` stay as they are (vendored). `gridplayer/resources/` is regenerated, never edited.
- No new features in the move. What Qt 6 makes possible (below, "After the move") waits until it's done, and the
  architecture refactor waits for it too (ROADMAP).
- Test windows stay off your desktop: offscreen, the away desktop on Windows, the Linux and macOS machines.
- Code works on Qt 6.11 and 6.12 (the Flatpak's).

## What the review found (2026-11-18)

Checked against PyQt6 6.12.1 on Qt 6.12.0 installed beside the project, not from memory: every name imported from PyQt5
looked up in PyQt6, every `QClass.Name` resolved, and the PyQt5 and PyQt6 class members compared and matched against the
calls in the code.

### Size

- 687 Python files; 369 import PyQt5 (167 in `gridplayer/`, 202 in `tests/`). Import lines: QtCore 312, QtWidgets 262,
  QtGui 172, QtTest 29, QtDBus 7, QtWinExtras 2, QtSvg 1.
- **Enums: 2,484 uses of 402 names** need their full name (`Qt.AlignLeft` → `Qt.AlignmentFlag.AlignLeft`). Each name
  belongs to exactly one enum, so a script can do it. All but one full name already work on PyQt5 5.15 (the exception:
  `QLibraryInfo.LibraryPath.TranslationsPath`). About 40 more go through an instance or a module, which the script must
  also catch: `selection.Rows`, `selection.NoUpdate`, `event.PaletteChange`, `dialog.Accepted`,
  `QtWidgets.QSizePolicy.Fixed` (`color_palette.py`, `cookie_store_list.py`, `resolver_patterns_list.py`, `checkup.py`,
  the two rename dialogs).
- `exec_()`: 62 uses, some on our own classes that define `exec_`.

### Moved

| PyQt5 | PyQt6 |
|---|---|
| `QtWidgets.QAction`, `QShortcut` | `QtGui` |
| `QtWidgets.QOpenGLWidget` | `QtOpenGLWidgets` |
| `QtGui.QOpenGLFramebufferObject`, `QOpenGLTextureBlitter`, `QOpenGLVersionProfile` | `QtOpenGL` |
| `QtSvg.QSvgWidget` | `QtSvgWidgets` |
| `from PyQt5 import sip` | `from PyQt6 import sip` (same functions) |

### Gone, each with its replacement

| Where | What | Instead |
|---|---|---|
| `main/init_app_env.py:133` | `QtWin.setCurrentProcessExplicitAppUserModelID` | `shell32` through ctypes |
| `utils/win32_tray.py:323` | `QtWin.toHICON` | `QImage.toHICON()` (in PyQt6, checked) |
| `utils/media_session_linux.py:76,158` | `Q_CLASSINFO` (MPRIS) | `@pyqtClassInfo` |
| `widgets/video_frame_vlc_hw_sp.py:388` | `QMacCocoaViewContainer` (VLC's view on macOS) | a native `QWidget`; its `winId()` is an NSView |
| `dialogs/add_urls.py`, `player/managers/add_videos.py` | `qApp` | `QApplication.instance()` |
| `main/init_icons.py:14` | `QApplication.desktop()` | the primary screen's `devicePixelRatio()` |
| `main/init_app.py:71` | `QApplication.paletteChanged` | `ApplicationPaletteChange` event, careful not to loop on our own `setPalette` |
| `main/init_app_env.py:138-139` | `AA_EnableHighDpiScaling`, `AA_UseHighDpiPixmaps` | nothing: always on |
| `main/init_app.py:67` | `AA_DisableWindowContextHelpButton` | nothing: no "?" button by default |
| `main/init_translator.py:23` | `QLibraryInfo.location` | `QLibraryInfo.path` |
| `mpv_player/gl_context.py:677` | `QOpenGLContext.versionFunctions` | `QOpenGLVersionFunctionsFactory.get` |
| `widgets/video_surface_sw.py:138` | `QRegion.rects()` | the bands worked out (PyQt6 can't list a region's rects; see 2.3) |
| `params/settings_fields/choices.py:499` | `QFontDatabase().families()` | `QFontDatabase.families()` |
| `utils/drag_n_drop.py`, `utils/keymap.py`, `widgets/settings_controls.py:241` | `Qt.KeyboardModifiers`, `Qt.Orientations` | `Qt.KeyboardModifier`, `Qt.Orientation` |

### Changed without an error (the traps)

- **Flags aren't ints.** `int()` raises on the enums PyQt6 makes `enum.Flag`: `KeyboardModifier`, `MouseButton`,
  `DropAction`, `StandardButton`, `WindowState`, `ItemFlag` (`.value` instead). `AlignmentFlag` and `WindowType` are
  `IntFlag`; `Key`, `QEvent.Type`, `ItemDataRole` are `IntEnum`: these still act as ints. A Flag never equals an int:
  `Qt.MouseButton.LeftButton == 1` is `False`, silently. Sites: `dialogs/bookmarks.py:137-138,503`,
  `dialogs/media_list.py:597,661,1174`, `dialogs/messagebox.py:152,396`, `utils/drag_n_drop.py:92,94`,
  `utils/keymap.py:55,665`, `widgets/layout_editor.py:1064`.
- **Keys.** `Qt.SHIFT | Qt.Key_F2` is a `QKeyCombination` now, not an int, and `QKeySequence(...)[0]` is one too
  (`.toCombined()` gives the int). Keymaps are saved as text (`PortableText`), so saved shortcuts aren't affected; the
  code that builds them from ints is.
- **Font weights.** `QFont.setWeight(75)` is accepted and means nearly Thin on Qt 6's 1–1000 scale. The code only uses
  `QFont.Bold` (`widgets/empty_cell.py:55`), which is fine; the trap stays for new code.
- **Events.** About 60 calls on events. `QMouseEvent` keeps `pos()` but loses `globalPos()`, `x()`, `y()`, `localPos()`;
  drop and drag-move events lose `pos()`, `mouseButtons()`, `keyboardModifiers()`; hover and enter events lose `pos()`;
  the wheel event loses `pos()` and `globalPos()`. `enterEvent` gets a `QEnterEvent` (2 handlers). Positions come back
  as `QPointF` (`position()`), so integer sums need `.toPoint()`.
- **Native hooks.** `nativeEventFilter` returns `(bool, voidptr)` now (`utils/darkmode_windows.py:56`,
  `utils/mouse_windows.py:53`). `winId()` returns a `sip.voidptr`; every use already wraps it in `int()`.
- **Into Qt's own library.** `utils/gl_window_size.py` calls the private
  `QWindowSystemInterface::flushWindowSystemEvents` by its symbol. Qt 6.12's `Qt6Gui.dll` has the same symbol (checked);
  the library names change (`Qt6Gui.dll`, `libQt6Gui.so.6`, and on macOS `QtGui.framework/Versions/A/QtGui`).
- **What doesn't change:** settings are all stored as text, so `settings.ini` needs no migration. A `QEvent.Type` made
  from an int still works (`window_state.py`'s Quit). `QTest` calls stay as they are.

### Tests

- Event constructors in about 20 test files (`QMouseEvent(...)` and others).
- `QFontMetrics.width` → `horizontalAdvance` (`tests/test_tooltip.py:188`), `QImage.byteCount` → `sizeInBytes`
  (`tests/real_app/scenarios/live.py:19`), `setTimestamp` gone (`tests/test_wheel_notches.py:29`).

### Translations

- **pylupdate6 finds the same 1,795 strings** as today's pylupdate5 with `flatten_translate_calls.py`, compared on
  2026-11-18, and the same with or without flattening. So the flattening step can go.
- Its `.ts` is written differently (480 KB against 402 KB for the same strings): see what Crowdin makes of it before
  the first upload.
- `lrelease` isn't in the wheels: it comes from Qt's tools, as now. The `.qm` format didn't change.
- `resources/translations/en_US.ts` in the repo has 292 strings, so it's out of date, not a baseline.

### Packaging

| | Today | With Qt 6 |
|---|---|---|
| Windows | x64 and x86, Qt 5.15.2 | x64 only (arm64 wheels exist: later, if wanted) |
| macOS | x86_64 and arm64 DMGs | the same, macOS 14 and up |
| AppImage | `manylinux_2_34`, x64 | the same base (PyQt6's x64 wheel is `manylinux_2_34` too); plus arm64 on `manylinux_2_39` |
| Flatpak | KDE 5.15-25.08, PyQt BaseApp | KDE 6.11, PyQt BaseApp 6.11, until a 6.12 branch |
| Snap | core22, kde-neon, PyQt5 debs, VLC only | core24, wheels, libmpv |

Files: `pyproject.toml` (pins, keywords, classifiers), `scripts/pyinstaller/pyinstaller_{win,mac}.spec` (module lists),
`scripts/pyinstaller/build_{win,mac}.sh` (the 32-bit branch, Qt framework checks), `scripts/windows/build_packages.sh`
(x86 installer), `scripts/_helpers/blacklist_pyqt.txt` (Qt 5 library names), `scripts/appimage/AppRun.c:280` (a stale
`python3.9`/`PyQt5` plugin path), `scripts/appimage/build_docker.sh`, `scripts/flatpak/*`, `scripts/snap/*`,
`scripts/chocolatey/template.nuspec` (tags), `.github/workflows/build.yml` (x86 matrix), `release_flatpak.yml` (SDK).

Linux: Qt 6.5 and up needs `libxcb-cursor0` for X11; the README's `libxcb-xinerama0` line becomes that.

## Stage 0: baseline on PyQt5

So every later difference can be told from one that was there before. Numbers taken on different days don't
compare well, so beside what's recorded here there is **a PyQt5 copy to run side by side** with any later stage:
`build/qt6-baseline/pyqt5`, a detached worktree of `2d05022` with its own `.venv` (64-bit Python 3.14.6, PyQt5 5.15.11,
Qt 5.15.2; made with `uv sync --python cpython-3.14.6-windows-x86_64-none`, as uv otherwise took a 32-bit Python
there). Outputs go to `build/qt6-baseline/` (not in git).

- 0.1 Unit tests on Windows: **done 2026-11-18**, 8,838 passed, 7 skipped, 84 real-app deselected, in 2 min 42 s
  (Python 3.14.6, PyQt5 5.15.11, Qt 5.15.2).
- 0.2 Real-app scenarios (`just test-real-app`):
  - **Windows, done 2026-11-18.** VLC: 36 passed, 1 xfailed (`external_audio_jump`, in `KNOWN_BUGS`), in 7 min 27 s.
    MPV needs `GP_LIBMPV_PATH=build/libmpv-win64/libmpv-2.dll` here, or its 47 runs are skipped ("needs libmpv"): 46
    passed, 1 failed, in 15 min. **Already there, not Qt 6's:** `mpv_audio` fails 2 runs of 3 alone, at "the picture,
    paused" (`mpv_audio.py:412`): with the video paused, turning its track back on draws no picture within 20 s.
    Not put in `KNOWN_BUGS`, whose xfail is strict: a flaky run would fail it when it passes.
  - **`test_ubuntu`, done 2026-11-18** (the VM's venv synced to `uv.lock` first): 83 passed, 1 xfailed
    (`external_audio_jump`), in 19 min 21 s. `mpv_audio` passed there.
  - `test_macos` and `test_macos_real` weren't reachable that day (the VM's name didn't resolve, the hackintosh
    refused the key): their baseline is taken before stage 5, from `2d05022`.
- 0.3 Benches (`tests/real_app/bench`) with `CLIPS=mix`: VLC hardware, MPV Copy, Shared and Direct, on Windows and
  `test_gpu`. Frame rates, CPU, memory, and `churn.py`'s checkpoints. Run in stage 3 against the PyQt5 copy, back to
  back on the same day, rather than now.
- 0.4 Screenshots: **done 2026-11-18**, `scripts/qt6_port/look.py`, a scenario that pauses four cells and shoots the
  player, the context menu and each submenu, every page of Settings and of the Playlist window, and ten dialogs: 42
  PNGs, at 100% (`look_100`) and 150% (`look_150`, `QT_SCALE_FACTOR=1.5`), all offscreen. It stubs Add - Clipboard's
  check, as offscreen has no clipboard. The offscreen screen is 800x600, so the long context menu is cut off at the
  bottom, the same way each run. A real window's text (DirectWrite) is compared in stage 3.3.

## Stage 1: rewrites that work on both (still PyQt5)

Scripted where it's mechanical, every one checked with the tests on PyQt5.

- 1.1 Full enum names: **done 2026-11-18.** `scripts/qt6_port/scope_enums.py` wrote 2,509 uses of 407 members in
  254 files, then `ruff format`. By hand, the ones reached through an object, scoped through the same object so no
  import is added: `selection.SelectionFlag.Rows` (bookmarks, media list, playlist bookmarks and their tests),
  `event.Type.PaletteChange` and its kin (`media_list.py`), `dialog.DialogCode.Accepted` (two tests), and the
  `getattr(QMessageBox.ButtonRole, role)` of the `grid_own_templates` scenario. A test's fake `QKeySequence` now
  copies `SequenceFormat`. `QLibraryInfo.TranslationsPath` waits for stage 2.
- 1.2 `exec_()` → `exec()`: **done**, 99 in 51 files, our own `QCustomMessageBox.exec` and the tests' mocks with them.
- 1.3 **Done:** `qApp.clipboard()` → `QApplication.clipboard()` (static on both); `Qt.KeyboardModifiers` as a return
  type → `Qt.KeyboardModifier`; `Qt.Orientations()` → `Qt.Orientation(0)`. **Moved to stage 2:**
  `QFontDatabase().families()` (`choices.py`), as PyQt5's `families` isn't static.
- 1.4 Flag values: **done.** `flag_value()` in `utils/qt.py` (`int(getattr(flag, "value", flag))`) at 16 sites:
  `bookmarks.py` (the two keys and the key handler), `media_list.py` (alignment, key handler), `messagebox.py` (role,
  button, `_standard_buttons`), `drag_n_drop.py` (proposed action), `keymap.py` (wheel, key sequence),
  `layout_editor.py` (`modifier_name`). No flag compared with an int literal was found. Of the kinds PyQt6 makes a
  plain `Enum` or `Flag` (no int), our code uses `KeyboardModifier`,
  `MouseButton`, `DropAction`, `ItemFlag`, `Orientation`, `WindowState`, `QDialogButtonBox.StandardButton`,
  `ButtonRole`, `Modifier` and the like; `DialogCode`, `QMessageBox.StandardButton`, `Key`, `AlignmentFlag` and
  `ItemDataRole` are int kinds there. A key built as `flag_value(Qt.Modifier.SHIFT) | Qt.Key.Key_F2` stays an int on
  PyQt6, which `QKeySequence(int)` still takes, so 2.5 may need less than planned.

Done when: tests, ruff and the scenarios pass on PyQt5. **All as the baseline, 2026-11-18:**

- Tests: 8,838 passed, 7 skipped. Ruff clean.
- Scenarios on Windows, VLC and MPV together: 82 passed, 1 xfailed, `mpv_audio` failed (the flaky one of 0.2).
- Scenarios on `test_ubuntu`: 82 passed, 1 xfailed, `marks` failed: "the intro is played: [0, 0, 0, 0, 43990]", the
  clock reading 0 after "0%" and then the old time again. **Already there:** the untouched `2d05022` (a `git archive`
  in `/tmp/gp-base` on the VM, the same venv) fails it 3 runs in 6, stage 1 2 in 4; VLC only, the MPV runs pass. Not
  put in `KNOWN_BUGS` (strict xfail), as with `mpv_audio`.
- Screenshots (`look.py`): 40 of 42 the same to the pixel at 100% and at 150%. The other two are the player, whose
  videos paused on another frame, and a text cursor's blink.

## Stage 2: the switch

One step, as both bindings can't run in one process. Done when the app starts on Windows with VLC and MPV, and
`uv run pytest` passes.

- 2.1 `pyproject.toml`: `PyQt6==6.12.1`, `PyQt6-Qt6==6.12.0`, PyQt5 pins gone; `uv.lock` (sip 13.13.1). **Done.**
- 2.2 Imports: **done** by `scripts/qt6_port/switch_imports.py`, which looks every imported name up in PyQt6 and moves
  it to the module that has it; it changes imports and module paths in strings only, so comments about PyQt5 are left
  for 8.1. By hand: `log_config.py`'s `QtCore.QtDebugMsg` and kin (`QtCore.QtMsgType.QtDebugMsg`, enum members
  reached through the module).
- 2.3 The "Gone" table: **done.** App ID through `shell32.SetCurrentProcessExplicitAppUserModelID`; the tray's HICON
  from `pixmap.toImage().toHICON()`; MPRIS with `@pyqtClassInfo`; VLC's view on macOS a plain native `QWidget` (to see
  in 5.1); `app.primaryScreen()`; `styleHints().colorSchemeChanged` for `paletteChanged`, which our own `setPalette`
  doesn't fire; `QLibraryInfo.path(LibraryPath.TranslationsPath)` and the package's `PyQt6/Qt6/translations` (from
  6.2, as the old call is gone); `QOpenGLVersionFunctionsFactory.get`; `QFontDatabase.families()`; the two removed
  attributes gone. **The review was wrong on `QRegion`:** PyQt6 can't list a region's rectangles at all (no
  `rects()`, not iterable), so `video_surface_sw.py`'s black bars are worked out as the four bands around the picture,
  checked against the region's own subtraction.
- 2.4 Events: **done.** Six calls: drop and drag-move positions (`position().toPoint()`) in `media_list.py`,
  `active_block.py`, `drag_n_drop.py`, `resolver_patterns_list.py`; mouse `globalPos()` in `drag_n_drop.py` and
  `keymap_tree_view.py`. Context menu, tooltip (`QHelpEvent`) and move events keep `globalPos()`/`oldPos()`. No
  `enterEvent` reads a position.
- 2.5 Keys: **nothing more needed.** Keys built with `flag_value()` stay ints, which `QKeySequence(int)` takes;
  `QKeySequence[i]` is a `QKeyCombination`, so `keymap.py` takes `.toCombined()`.
- 2.6 Native: **done.** `nativeEventFilter` returning `(False, 0)` is accepted as it is (checked);
  `gl_window_size.py` on `Qt6Gui.dll`, `libQt6Gui.so.6` and `Versions/A`, and the flush symbol resolves on Windows.
- 2.7 GL: **done**, see 2.3.
- 2.8 Tests: **done.** Event constructors take `QPointF`; the wheel tests use a `QWheelEvent` subclass that answers
  `timestamp()` (no `setTimestamp`); `horizontalAdvance`; `sizeInBytes` (`live.py`).
- **Found on the way, not in the review:**
  - **An enum through an int signal.** A plain `Enum`/`Flag` value emitted by a `pyqtSignal(int)` arrives as a
    memory address, silently. `WindowsTrayIcon.activated` was one: tray clicks would have done nothing. Declared with
    `QSystemTrayIcon.ActivationReason` now; every other int signal's emits checked, none carries a Qt enum.
  - **`QDBusArgument` takes the type id as an int**: `QMetaType.Type.QStringList.value` (MPRIS, show in folder,
    keep-awake).
  - **`QMessageBox.ButtonRole` and `QDialogButtonBox.ButtonRole` are two enums**, never equal: `QCustomMessageBox`
    gives back `QMessageBox`'s roles and buttons.
  - **Objects tests leave behind live longer.** A test that drops a `QWidget` parent, or calls `deleteLater()` with
    no event loop running, leaves its children's timers firing into later tests, which raise in a slot and abort the
    run (exit 127, no output). `test_managers_playlist.py` and `test_sync.py` delete theirs at once now
    (`sip.delete`).
  - Qt 6's offscreen screen has a device pixel ratio of 1.0, Qt 5's 1.04, so stage 0's screenshots are 4% bigger.
  - `test_ubuntu` got `libxcb-cursor0`, without which Qt 6's xcb plugin doesn't load.
- **Results, 2026-11-18:** tests 8,838 passed, 7 skipped (as PyQt5); ruff clean. The app, offscreen, through every
  menu, settings page and dialog of `look.py` with nothing in its log. Scenarios, Windows (VLC and MPV) and
  `test_ubuntu`: 76 passed, 1 xfailed, 7 failed, all in the drag helpers of `free_tiles.py` and `grid_lines.py`
  (mouse events made from `QPoint`); fixed, the ten that use them pass on both. `mpv_audio` and `marks` passed this
  time.
- 2.9 `/code-review` of the stage's hand-made changes, the scripted import rename left out: events, native filters, GL,
  keys and `winId()` can run and still be wrong, which tests often miss.
  **Done 2026-11-18**, 21 files. Fixed:
  - a bug, `int()` on `Qt.ItemFlag` in the patterns list's drop (a row dropped on another raised): flags compared as
    flags, and a test of dropping a row there;
  - Qt's `colorSchemeChanged` now only where we have no theme watcher of our own (macOS), as on Windows and Linux it
    made a second repaint of the whole app on every switch, reading the system's answer too early;
  - QtOpenGL's import inside the fallback's `try` (some distributions package it apart);
  - no screen at all at start (`primaryScreen()` is None);
  - the message box's return types, and the GL fallback's docstring.

  Left: VLC's view on macOS as a plain native widget, to check in 5.1; `QMouseEvent.pos()`, which PyQt6 still has, as
  it is all over the code (8.4 can take it).

## Stage 3: Windows

The main platform and the one Qt 6 changes most under us. Each item against the stage 0 baseline.

- 3.1 **DPI.** Qt 6 makes the process Per-Monitor v2. At 100%, 125%, 150%, 200%, and a window moved between two screens
  of different scale: VLC's window (`win32_vlc_vout.py`), the overlay as a layered child window, MPV Direct's window, zoom
  and pan, zoom to cursor, the tray's position mapping (`win32_tray.py:305`).
- 3.2 **GL.** Qt 6 puts a window with a `QOpenGLWidget` together differently. MPV Shared: the one surface, the holes,
  `repaint_now`, `gl_window_size`'s held paints, 120 fps (13.10), resize without the jump, the GL line fix, `grabbing()`.
  Benches against stage 0.
- 3.3 **Look.** Fusion is set already, so Qt 6's Windows 11 style doesn't come in, but Fusion itself changed in Qt 6, and
  Qt 6.8 draws text with DirectWrite. Screenshots against stage 0: menus, the checked-state badges, tooltips (the
  62-character card), the status font sizes, settings cards, dialogs. Dark mode: Qt 6.5+ follows the system's colour
  scheme, which mustn't fight `theme.py`.
- 3.4 **Input.** Shortcuts (keypad, AltGr, the media keys), drag and drop (in and out, the hold-to-switch key), wheel
  notches, drag gestures, synthetic moves (`mouse_windows.py`), double-click.
- 3.5 **Native bits.** Tray and its menu, hidden from taskbar, SMTC, taskbar icon (the app ID), single instance,
  dark title bars, window geometry restored from a playlist saved on Qt 5.
- 3.6 All real-app scenarios; VLC single-process freeze check (VLC SP).
- 3.7 `/code-review` of the stage's changes.

## Stage 4: Linux

On `test_ubuntu` and `test_gpu`, X11 and Wayland.

- 4.1 X11: `QT_XCB_GL_INTEGRATION` none/xcb_egl as now, the window-type property (`utils/qt.py`), the overlays as X11
  children, skip-taskbar, compositor check, `forkserver`.
- 4.2 Wayland: Qt 6's fractional scaling, `wayland_frames.py` (GNOME), `utils/wayland.py`'s cursor, the pure Wayland
  tests, MPV's own EGL display.
- 4.3 D-Bus: MPRIS with `@pyqtClassInfo`, the portal's dark mode (`darkmode_linux.py`), the tray.
- 4.4 Scenarios and benches against stage 0.

## Stage 5: macOS

On `test_macos` (VM) and `test_macos_real` (hackintosh, real GPU).

- 5.1 VLC hardware SP without `QMacCocoaViewContainer`: the native widget's NSView, resizing, the explicit resize
  after load (`video_frame_vlc_hw_sp.py`).
- 5.2 MPV Shared on OpenGL 3.2 Core (`macos_gl_format`), sharing with Qt's context.
- 5.3 Cmd+Q, Now Playing, the Accessory tray mode, keep-awake.
- 5.4 Scenarios against stage 0.

## Stage 6: translations

- 6.1 `scripts/translations/build_ts.sh` on `pylupdate6 --no-obsolete`; `flatten_translate_calls.py` removed.
- 6.2 `init_translator.py`: Qt's own `qtbase_*.qm` from `PyQt6/Qt6/translations` in the Windows package.
- 6.3 A `.ts` made both ways compared; nothing uploaded (that's yours).
- 6.4 `lrelease` (Qt 6's tools) builds the `.qm` files; the app loads a translation.

## Stage 7: packaging and CI

- 7.1 Windows: specs, `build_win.sh` without its 32-bit branch, installer x64 only, CI matrix.
- 7.2 macOS: specs, `build_mac.sh`'s Qt checks (`Qt6/lib`, `Versions/A`), the minimum system version in the bundle.
- 7.3 AppImage: Qt 6 blacklist, `AppRun.c`'s plugin path, `libxcb-cursor`; then the arm64 one on GitHub's arm runners.
- 7.4 Flatpak on KDE 6.11 and the PyQt BaseApp 6.11.
- 7.5 Snap on core24 with libmpv (MPV_PLAN 12.1).
- 7.6 Each package started on a clean machine: Windows, Ubuntu 24.04, Debian 13, macOS 15.

## Stage 8: clean-up and docs

- 8.1 Comments that speak of PyQt5 or Qt 5 bugs (`gl_context.py`, `darkmode_windows.py`, `mouse_windows.py`,
  `video_driver.py:111`, `wayland.py`, `wayland_frames.py`, `window_state.py:19`): updated, and workarounds Qt 6 made
  unnecessary removed only where seen to be so.
- 8.2 AGENTS.md (PyQt6, the flag trap, the event positions), README (platforms, `libxcb-cursor0`, macOS 14),
  CONTRIBUTING, CHANGELOG, ROADMAP's Qt 6 section, `MPV_PLAN.md`'s Snap notes.
- 8.3 `scripts/qt6_port/` removed.
- 8.4 `/simplify` once PyQt5 is gone: `flag_value()` to `.value` where the kind is known, fallbacks for both bindings
  (`look.py`'s import among them) dropped.

## After the move (not part of it)

What Qt 6 opens up, from ROADMAP: sharp windows at 125% and 150% on Wayland (comes with the move, seen in 4.2), our own
window frame on GNOME, Wayland as Auto there. Also possible: Windows on arm64, and the system colour scheme from
`QStyleHints.colorScheme()` instead of our own watchers. Then the architecture refactor.
