# Qt 6: plan and progress

The move from PyQt5 (Qt 5.15) to PyQt6 on Qt 6.12, on the `qt6` branch. This file says what changes, in what order,
and how each step is checked. Tick an item only once it has been seen working.

**Status: stages 0-8 done (2026-11-19). Left: CI's first run (the branch isn't pushed: a `dry_run` pre-release), the stage 3 hand checks.**

| | Stage | State |
|---|---|---|
| 0 | Baseline on PyQt5: tests, scenarios, benches, screenshots | **done 2026-11-18** but the Macs (before stage 5) and benches (stage 3) |
| 1 | Rewrites that work on both: full enum names, `exec()`, flag values | **done 2026-11-18** |
| 2 | The switch: PyQt6 6.12, imports, removed APIs, events; tests pass | **done 2026-11-18** |
| 3 | Windows: DPI, native windows, GL, look, input | **done 2026-11-18**; hand checks left (DPI, keys, drag and drop, tray, SMTC) |
| 4 | Linux: X11, Wayland, D-Bus | **done 2026-11-19** |
| 5 | macOS | **done 2026-11-19** on the hackintosh (`test_macos` unreachable) |
| 6 | Translations: pylupdate6 | **done 2026-11-19** |
| 7 | Packaging and CI | **done 2026-11-19** but CI itself, which runs once the branch is pushed |
| 8 | Clean-up and docs | **done 2026-11-19** |

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
  **Done as far as one 100% screen goes, 2026-11-18.** This machine has one 1920x1080 screen at 100%, so Qt's
  `QT_SCALE_FACTOR=1.5` stood in for Windows': VLC hardware, MPV Shared and MPV Direct in real windows on the away
  desktop, on both bindings, each picture where the other binding puts it. No code depends on an integer device
  pixel ratio (the three `devicePixelRatio()` calls were floats on Qt 5 too). **By hand:** Windows' own 125%, 150%,
  200%, and a window moved between screens of different scale (Qt 6 is Per-Monitor v2, Qt 5 was v1): VLC's and
  mpv's own windows, the overlay, zoom to cursor, the tray menu's place.
- 3.2 **GL.** Qt 6 puts a window with a `QOpenGLWidget` together differently. MPV Shared: the one surface, the holes,
  `repaint_now`, `gl_window_size`'s held paints, 120 fps (13.10), resize without the jump, the GL line fix, `grabbing()`.
  Benches against stage 0.
  **Done 2026-11-18.** Benches A/B, `CLIPS=mix`, 4, 9 and 16 cells, real windows on the away desktop, the same
  RTX 3060 (`build/qt6-stage3/bench*`): every frame rate the same. CPU, memory and GPU the same for VLC hardware and
  MPV Direct; MPV Shared a little less CPU and GPU on PyQt6 (16 cells: 86% CPU, 15% GPU against 100% and 28%);
  MPV Copy at 16 cells within the runs' own spread (PyQt6 103, 106, 103%; PyQt5 89, 116, 99%). GUI lateness p95
  1-2 ms on both. Shared's surface, holes and Direct's windows look the same in the captures. **Bench trap:** this
  machine's monitor is on the AMD iGPU and only one Python path is set to the RTX in Windows' graphics settings; the
  PyQt5 copy first ran on the iGPU (its venv named the other path, and `uv run --with` made another), which looked
  like PyQt5 being slower. It now runs `.venv/Scripts/python.exe` with psutil installed in it.
- 3.3 **Look.** Fusion is set already, so Qt 6's Windows 11 style doesn't come in, but Fusion itself changed in Qt 6, and
  Qt 6.8 draws text with DirectWrite. Screenshots against stage 0: menus, the checked-state badges, tooltips (the
  62-character card), the status font sizes, settings cards, dialogs. Dark mode: Qt 6.5+ follows the system's colour
  scheme, which mustn't fight `theme.py`.
  **Done 2026-11-18.** `look.py` now runs with the real Windows platform and its fonts without a window on the
  screen (`LOOK_HIDDEN=1`: every window `WA_DontShowOnScreen`, a watchdog ends the run should one show), on both
  bindings, at 100% and 150%, light and dark. Side by side, the same but for Qt 6's Fusion: menus 4 px wider, the
  submenu arrow a chevron, DirectWrite's text (ClearType fringes the other way round). **Found and fixed:** with the
  system dark and the app set to Light, Qt 6 (a) fills the roles our palette left unset (`Mid`, `Dark`, `Light`,
  `Midlight`, `Shadow`) from the system's dark palette, so every `palette(mid)` border went black, and the system's
  accent colour came in through `Accent`; (b) has Fusion draw check box outlines by Qt's colour scheme, white on
  white. `fusion_palette()` now sets those roles to what they are on Qt 5 / light Windows, `Accent` to our highlight;
  `apply_theme()` tells Qt the app's scheme (`styleHints().setColorScheme`, Qt 6.8+; the system's for System). One
  visible change kept: in Dark, a check box's outline is Qt 6's lighter grey (#757575) where Qt 5's (#353535) hardly
  showed on #444444. A dark Windows itself wasn't tried (the machine's is light): Qt's scheme was set dark instead.
- 3.4 **Input.** Shortcuts (keypad, AltGr, the media keys), drag and drop (in and out, the hold-to-switch key), wheel
  notches, drag gestures, synthetic moves (`mouse_windows.py`), double-click.
  **Partly done 2026-11-18**, by Windows messages posted to the real window on the away desktop
  (scratchpad `input_checks.py`): the pointer makes the cell under it active, Wheel-Down seeks 1%, Shift+Wheel-Down
  5%, a click plays and pauses, all through Qt 6's Windows input. **By hand:** keys (Qt drops key messages to a
  window never activated, on PyQt5 too, and activating one would switch the desktop): keypad, AltGr, media keys;
  drag and drop in and out (Windows' OLE loop takes the real mouse), the hold-to-switch key, double-click.
- 3.5 **Native bits.** Tray and its menu, hidden from taskbar, SMTC, taskbar icon (the app ID), single instance,
  dark title bars, window geometry restored from a playlist saved on Qt 5.
  **Partly done 2026-11-18:** the app ID (`shell32` now) is what it was; dark title bar on and off with the scheme;
  a window geometry saved by Qt 5 restored by Qt 6 to the pixel; single instance doesn't use Qt. Windows doesn't say
  a caption colour back, on either binding. **By hand:** the tray and its menu, hidden from taskbar, SMTC (each would
  show on the user's own taskbar from here).
- 3.6 All real-app scenarios; VLC single-process freeze check (VLC SP).
  **Done:** all scenarios pass offscreen on PyQt6 (stage 2); VLC hardware single-process played 4, 9 and 16 cells in
  real windows through every bench run without a stall.
- 3.7 `/code-review` of the stage's changes.
  **Done 2026-11-18.** Fixed: Qt is told the scheme the palette is of, the app's own reading of the system's
  included, rather than left to guess it (Linux reads `GTK_THEME`, which Qt doesn't), but on macOS following the
  system, where Qt's `colorSchemeChanged` is how a switch is heard; told only when it changes; one reader of the
  setting (`darkmode.app_color_scheme`); `look.py`'s hiding from the player's first show on, its watchdog on Windows
  only and with its argument types. Kept: the pinned shades on every platform (stages 4 and 5 compare them with
  their baselines). `look.py` hidden hung once in eight runs at a submenu, not again: harness, as a hidden window
  never gets Windows' expose; watch for it.

## Stage 4: Linux

On `test_ubuntu` and `test_gpu`, X11 and Wayland.

Each item on both bindings side by side, by a scenario that reads back from the desktop what the app did (scratchpad
`linux_native.py`, run with the session bus left to it): on `test_ubuntu` (GNOME 46, Wayland and Xwayland) against a
PyQt5 venv of `2d05022` in `/tmp/gp-base`, and on `test_gpu` (sway, Intel HD 4600) against `/opt/venv` (PyQt5), with
PyQt6 in `/opt/venv6`. Outputs in `build/qt6-stage4/`.

- 4.1 X11: `QT_XCB_GL_INTEGRATION` none/xcb_egl as now, the window-type property (`utils/qt.py`), the overlays as X11
  children, skip-taskbar, compositor check, `forkserver`.
  **Done 2026-11-19.** The same on both: `none` for VLC, `xcb_egl` and `forkserver` for MPV Shared, the compositor
  found, a detached dialog `_NET_WM_WINDOW_TYPE_NORMAL`, the floating overlay's window types and its skip-taskbar,
  skip-pager and sticky states, GNOME's block on hiding the taskbar button. Hiding it under sway does nothing on
  either binding (sway's X11 doesn't take the request). **Found and fixed:** `gl_window_size`'s held paint passed
  `Qt.EventPriority` to `postEvent`, which takes an int in PyQt6: every paint held for the next refresh raised
  instead, on any platform, with MPV Shared on a real display only (offscreen paints are never held). Fixed, with a
  test; a sweep of every call passing a plain enum where PyQt6 wants an int found no other (scratchpad
  `enum_to_int_args.py`).
- 4.2 Wayland: Qt 6's fractional scaling, `wayland_frames.py` (GNOME), `utils/wayland.py`'s cursor, the pure Wayland
  tests, MPV's own EGL display.
  **Done 2026-11-19.** GNOME: Qt's own frame (margins 3,30,3,3) and the Yaru cursor from the portal on both; sway:
  the compositor's frames. MPV Shared, MPV Copy and VLC Software play on Wayland. Sway at 1.5: **Qt 6 draws at 1.5**
  (`wp_fractional_scale`), 1280x720 physical pixels for the 853x480 window, where Qt 5 draws at 2 and the compositor
  scales it down: the sharp 125%/150% the ROADMAP expected, same layout. Not tried: GNOME's own fractional scaling
  (experimental there).
  **The header on GNOME** (Wayland chosen; Auto takes X11 there): Qt 6 picks its `adwaita` decoration on GNOME
  instead of Qt 5's `bradient`, with GNOME's thin border, but its colours are its own (white over our #eeeeee, near
  black over #444444), it follows GNOME's light or dark rather than the app's, and draws no line between header and
  content; Qt has no way to give it ours (`bradient` takes our palette, with the thick border back). Decided
  2026-11-19: keep `adwaita`, and a 1 px line in the theme's border colour along the top of each window with Qt's
  header (`utils/wayland.py`, `draw_header_lines`). Our own header, for our colours and scheme, waits for after the
  move.
  **Qt 6.12's header jumps with MPV Shared** (found 2026-11-19, Wayland chosen on GNOME): as the window is resized
  its header and the top of the picture jump up 2-4 px now and then. Qt's bug, new in 6.12.0: a bare window with a
  `QOpenGLWidget` and nothing of ours, its corner dragged on `test_ubuntu` and the desktop screenshot 14 times a drag,
  jumped in 0 of 42 shots on Qt 5.15, 6.10.2 and 6.11.2, and in 9 of 42 on 6.12.0; GridPlayer on PyQt5 0 of 42, on
  PyQt6 10 of 42. Copy and plain widgets don't, nor a GL window without Qt's header (frameless, resized through
  `startSystemResize`). A frame is drawn for the new size into a buffer a few rows shorter, from the bottom up, so its
  top rows are cut off. Likely from qtbase `ed4bf9c993` (April 2026: the `wl_egl_window` resized after
  `eglMakeCurrent`, QTBUG-95817); qtbase `94f9621051` (dev, 2026-11-09: the header in subsurfaces) should end it.
  Not helped by: no vsync, a context made current on the window as it resizes, `QT_WAYLAND_DISABLE_RESIZECHECK`.
  Decided 2026-11-19: stay on 6.12 (not 6.11 on Linux, which gets no more fixes) and look again at each Qt release.
  The Flatpak, on 6.11, has no such jump, nor does Auto, which takes X11 on GNOME.
  **On X11, MPV Shared's picture lags a window being made bigger** (found 2026-11-19, `test_ubuntu`): a frame for the
  old size shows in the grown window, drawn from the bottom up, so the cells and their overlays jump down and back.
  Qt 5 does it worse; `gl_window_size` now holds Qt's paint while X11 already has a size Qt hasn't taken (asked over
  its own xcb connection), which takes most of it away. What's left was the VM's Mesa: on Ubuntu 24.04's Mesa 25.2.8
  (VMware's SVGA3D) the cells still jump, the same on Qt 6.11 and 6.12; on Mesa 26.2.6 (kisak-mesa, unpacked into
  `/opt/mesa_new`, `run.sh`) and in the Flatpak (Mesa 26.2.7 of its runtime) the resize is smooth. Not tried on a real
  GPU.
  Both are listed in `docs/findings/KNOWN_ISSUES.md`.
- 4.3 D-Bus: MPRIS with `@pyqtClassInfo`, the portal's dark mode (`darkmode_linux.py`), the tray.
  **Done 2026-11-19**, GNOME, X11 and Wayland: MPRIS named, Identity, PlaybackStatus, Metadata, PlayPause and Play
  from `gdbus` acting on the cells; GNOME's colour scheme switched and back, the app following both ways; the tray
  icon in GNOME's top bar on both. Qt 6 registers it as `<unique name>@/StatusNotifierItem` rather than Qt 5's
  `org.kde.StatusNotifierItem-<pid>-1`; Ubuntu's AppIndicator shows either.
- 4.4 Scenarios and benches against stage 0.
  **Done 2026-11-19.** Scenarios on `test_ubuntu`: 83 passed, 1 xfailed (`external_audio_jump`), as stage 0. Unit
  tests on `test_ubuntu` (Python 3.12) and `test_gpu` (Debian 13, Python 3.13) pass. Benches on `test_gpu`, `mix`,
  4, 9 and 16 cells, real X11 windows, A/B back to back: VLC hardware (multi- and single-process), MPV Copy, Shared
  and Direct at the same frame rates, CPU and memory on both; MPV Shared at 16 cells a little less CPU on PyQt6 (294
  against 352%); MPV Copy at 16 cells is past the machine (30-31.5 fps on both over three runs each).
  Look (`look.py` hidden on GNOME's X11, light and dark): the same but for text a pixel higher and some rows or
  dialogs 1-4 px shorter (Qt 6's font metrics), and the About icon's drop shadow, which Qt 6's SVG renderer draws
  (filters, Qt 6.7) and Qt 5's left out.
  **Found on the way:**
  - Qt 6's C locale writes numbers without the thousands separator (1200; Qt 5: 1,200), so tests expecting "1,200"
    failed in a container with no locale, as on GitHub's runners (`LANG=C.UTF-8`). The tests now set `en_US` as the
    default locale; the app keeps Qt's, which is right for C.
  - `test_a_file_that_isnt_a_library` passed on Windows only by luck: where libmpv loads in the run (Linux), an
    earlier import left `mpv` on its package, which `from gridplayer.mpv_player import mpv` took without loading the
    junk file. The test takes it off.
  - The PyQt5 copy's venv on `test_ubuntu` is Python 3.14, whose default start method on Linux is `forkserver`
    (3.12 and 3.13: `fork`): not Qt's.
  - `GLGridSurface.initializeGL` said it was ready by `QTimer.singleShot(0, self.ready.emit)`: a call queued apart
    from the surface, which PyQt6 makes on the signal of a surface gone meanwhile and crashes (found as the tests,
    whose windows go as each test ends, crashed once a later one ran the event loop). Now a timer of the surface's
    own; no other `singleShot` is handed a signal's `emit`.

## Stage 5: macOS

On `test_macos` (VM) and `test_macos_real` (hackintosh, real GPU).

`test_macos` didn't resolve again (2026-11-19), so all on `test_macos_real` (macOS 15.8.3, Intel HD 4600, Python
3.13): the PyQt5 baseline from `2d05022` in `~/gp-base` and the branch in `~/gp-qt6`, each with its own venv, run one
after the other in real cocoa windows (`~/gp-tests/suite_in.sh`, `ab*.sh`).

- 5.1 VLC hardware SP without `QMacCocoaViewContainer`: the native widget's NSView, resizing, the explicit resize
  after load (`video_frame_vlc_hw_sp.py`).
  **Done 2026-11-19.** A scenario reading the view from inside the app (scratchpad `mac_vlc_view.py`): on PyQt6 the
  cell's native `QWidget` is a `QNSView` in the player's `QNSWindow`, with VLC's view inside it, the widget's size
  (1284x724), smaller and back again with the window, playing on; PyQt5's container the same. VLC Hardware on the
  scenarios that use it (`playback`, `navigation`, `tracks`, `single_mode_show_big`, `aspect_ratio`, `crop_ratio`,
  `pixel_shape`): the same 4 pass on both, the same 3 fail on both, where the driver can't read the picture of a
  native view ("waiting until a picture is on show"). No screen was captured: it raised a macOS prompt before.
- 5.2 MPV Shared on OpenGL 3.2 Core (`macos_gl_format`), sharing with Qt's context.
  **Done 2026-11-19.** Hardware MPV with `mpv_output=gl` on its seven scenarios: `videotoolbox` decoding straight
  into GL (the interop the 3.2 Core context is for), the same 6 pass on both, `mpv_transport` fails on both ("plays
  at 0.5", the rate measured on this machine).
- 5.3 Cmd+Q, Now Playing, the Accessory tray mode, keep-awake.
  **Done 2026-11-19**, the same on both (scratchpad `mac_native.py`), with the menu bar icon, close to it and the Dock
  hidden: an accessory app (no Dock icon) with its icon in the menu bar; a `NoDisplaySleepAssertion` "Playing media."
  held while playing and gone while paused; the play key, posted as the media key macOS routes to the Now Playing
  app, pausing and playing again; Cmd+Q, posted to the app, quitting it for good though closing goes to the menu bar.
  `_QuitWatcher` takes `QEvent.Type.Quit` now, which PyQt5 left out (stage 8).
- 5.4 Scenarios against stage 0.
  **Done 2026-11-19.** PyQt5 baseline: 83 passed, 1 xfailed (`external_audio_jump`), 30 min. PyQt6: 82 passed, 1
  xfailed, 1 failed, `mpv_deinterlace` on MPV Software ("film, off: combed", picked from a few grabs 70 ms apart);
  run three more times on each binding, it passed all six.

## Stage 6: translations

- 6.1 `scripts/translations/build_ts.sh` on `pylupdate6 --no-obsolete`; `flatten_translate_calls.py` removed.
  **Done 2026-11-19.** Run from inside a copy of the package as before, so locations read `dialogs/about.py`, with
  `\` turned to `/` (pylupdate6 writes the system's separator). It takes an optional `.ts` to write instead of
  `resources/translations/en_US.ts`, which was used to try it and left untouched.
- 6.2 `init_translator.py`: Qt's own `qtbase_*.qm` from `PyQt6/Qt6/translations` in the Windows package.
  **Done in stage 2.** Every one of the 18 `.qm` files loads on Qt 6, with Qt's own `qtbase_` for 16 of them; Qt has
  none for `no_NO` and `vi_VN`, as Qt 5 had none.
- 6.3 A `.ts` made both ways compared; nothing uploaded (that's yours).
  **Done 2026-11-19**, on the current code: pylupdate5 with the flattening finds 1,795 messages, pylupdate6 1,798, the
  same 1,795 and three pylupdate5 dropped because the same text was already taken in another context: "Margins",
  "Proxy address" and "Verify TLS certificates" in `SettingsDialog`. Plural forms the same. pylupdate6 writes one
  message with a `<location>` for each place it's used (2,239) where pylupdate5 wrote one, and `<translation
  type="unfinished" />` where pylupdate5 wrote an open and close tag: **see what Crowdin makes of it before the
  first upload.**
- 6.4 `lrelease` (Qt 6's tools) builds the `.qm` files; the app loads a translation.
  **Done 2026-11-19.** Qt 6.12's `lrelease` (from PySide6-Essentials, in a scratch venv) and the 5.15 one in use make
  byte-identical `.qm` files of `de_DE`, `ja_JP` and `ru_RU`, so the resources needn't be made again;
  `build_resources.py` still takes `lrelease` from the PATH.

## Stage 7: packaging and CI

- 7.1 Windows: specs, `build_win.sh` without its 32-bit branch, installer x64 only, CI matrix.
  **Done 2026-11-19.** The spec excludes every PyQt6 module the app doesn't import, read from the installed wheel
  (Qt 6 has many more than Qt 5 had), and drops `d3dcompiler_47`, `opengl32sw`, the unused image formats and
  platforms, and the TUIO touch plugin with the `Qt6Network` it alone brought in: `PyQt6/Qt6/bin` holds Core, Gui,
  Widgets, OpenGL, OpenGLWidgets, Svg and SvgWidgets. PyQt6's GL version functions are in `QtOpenGL`, so the
  `_QOpenGLFunctions_*` imports went. `build_win.sh`, `build_packages.sh`, `libmpv_pins.sh` and CI are 64-bit only.
  Built here: the installer 111 MB, the portable zip 161 MB; the portable's `--self-check` passes (Qt 6.12.0, VLC
  3.0.24 and libmpv each play the clip). The 32-bit build's failure in the last pre-release (`OpenSSL internal
  error: assertion failed: lock != NULL` at the self-check) went with it.
- 7.2 macOS: specs, `build_mac.sh`'s Qt checks (`Qt6/lib`, `Versions/A`), the minimum system version in the bundle.
  **Done 2026-11-19.** The spec as Windows', `LSMinimumSystemVersion` 14.0 in the bundle, and `build_mac.sh` checks
  `Qt6/lib/QtCore.framework/Versions/A/QtCore`'s architecture, failing if it isn't there. Built on `test_macos_real`
  (x86_64, the `.app`; no DMG, which takes create-dmg and GraphicsMagick the machine hasn't got): signed and verified,
  302 MB, Qt's Core, Gui, Widgets, OpenGL, OpenGLWidgets, Svg, SvgWidgets and DBus frameworks, and its `--self-check`
  passes (Qt 6.12.0 on cocoa, VLC 3.0.24, libmpv 0.41). The first build failed at signing: dropping `QtNetwork`'s
  binary had left the framework's Info.plist, signature and links, and the bundle's own `QtNetwork` links, leading
  nowhere; all of it goes now. The last pre-release's
  arm64 DMG passed its self-check and then failed to detach ("Resource busy"): CI now tries five times, says what
  holds it, then forces it.
- 7.3 AppImage: Qt 6 blacklist, `AppRun.c`'s plugin path, `libxcb-cursor`; then the arm64 one on GitHub's arm runners.
  **The last pre-release's failure:** AppRun puts the AppImage's libraries first on `LD_LIBRARY_PATH` and ran the
  pip launcher, whose first lines are a shell's, running the system's `readlink` and `dirname`; on the runner's
  Ubuntu those are Rust coreutils, which took EL9's older `libsystemd` and stopped (`undefined symbol:
  sd_session_get_start_time`), and the runner's own Python 3.14 ran the app, without it. Now:
  - AppRun starts the AppImage's Python on the script itself, and keeps the system's value of each variable it
    changes (`GRIDPLAYER_HOST_*`); the app opens every URL (links, Open URL, a folder) with those back
    (`utils/host_env.py`), so xdg-open and what it starts get the system's libraries, not ours. Seen in an Ubuntu
    26.04 container: `readlink` fails with ours and works with the system's.
  - AppRun no longer changes into `$APPDIR/usr` (from AppImageKit's sample AppRun): a file named on the command line
    by a relative path wasn't found. CI's container check passes the clip that way.
  - Packed by appimagetool 1.9.1 with the type2 runtime (release 20251108), both pinned by SHA-256: the static
    runtime needs no `libfuse2`, which Ubuntu 22.04 and later, and Fedora, no longer have. The 2022 linuxdeploy
    still gathers the libraries; its own packing used the old runtime.
  - The Qt 6 blacklist keeps Core, Gui, Widgets, OpenGL, OpenGLWidgets, Svg, SvgWidgets, DBus, XcbQpa and Wayland
    (the app picks Wayland itself on KDE when on Auto; Qt 5's AppImage had Wayland taken out), drops the rest of
    the libraries, plugins, QML and translations but `qtbase_`. `libxcb-cursor` is bundled (Qt 6.5+ needs it), the
    stale `QT_PLUGIN_PATH` (`python3.9/.../PyQt5`) gone.
  - `libjack` joins the fallback libraries: EL9's libmpv links it and linuxdeploy leaves it to the system, so libmpv
    wouldn't load on a system without JACK.
  - The arm64 AppImage: built the same way on `manylinux_2_39_aarch64` (AlmaLinux 10; PyQt6's aarch64 wheels need
    glibc 2.39), on `ubuntu-24.04-arm` in CI; `APPIMAGE_ARCH=aarch64` builds it elsewhere under QEMU (where binfmt
    needs a rule that ignores the AppImage magic in the ELF header's padding). EL10 has all of it (EPEL's VLC 3.0.24
    and mpv 0.40, RPM Fusion's FFmpeg). Three things it needed that EL9 didn't: no strip (linuxdeploy's doesn't know
    EL10's `.relr.dyn` sections), SDL3 bundled (EL10's SDL2 is sdl2-compat, which loads SDL3 by name and aborts the
    app without it), and `libgpg-error` among the fallback libraries (EL10's `libgcrypt` needs a newer one than Ubuntu
    24.04's; linuxdeploy bundles the one and leaves the other). **Done 2026-11-19 under QEMU**: its `--self-check`
    passes in an arm64 Ubuntu 24.04 container, Qt 6.12.0, VLC 3.0.24 and libmpv 0.40 each playing. Not run on a real
    arm machine.
  - CI checks the AppImage in containers too (Ubuntu 24.04 and 26.04, Debian 13, Fedora), each with what a desktop
    has and the AppImage leaves to it (glib, fontconfig, EGL, harfbuzz, ALSA, `libgpg-error`, `p11-kit`,
    `libcom_err`, `libOpenGL`...). Seen on `test_ubuntu` the same way (`--init`: `xvfb-run` as a container's first process never
    hears Xvfb is up): **the x64 AppImage passes in all four**, Qt 6.12.0, VLC 3.0.24 and libmpv 0.39 each playing.
    Each library a bare container lacked was one linuxdeploy leaves to the system on purpose; JACK was the one a
    desktop can really lack.
  - On the GNOME desktop of `test_ubuntu`, which has `fuse3` and no `libfuse2`: started from the file, mounted
    through FUSE, two cells playing (`build/qt6-stage7/look/appimage.png`).
- 7.4 Flatpak on KDE 6.11 and the PyQt BaseApp 6.11.
  The manifest, `build.sh` and `generate_dependencies.sh` on `org.kde.Platform//6.11` and the BaseApp 6.11; `build.sh`
  installs into the user's Flatpak, as CI does, so it needs no root. `release_flatpak.yml` has a `dry_run`: the bundle
  built from the checkout and kept as the run's artifact, nothing pushed. **Done 2026-11-19**: built on `test_ubuntu`
  (VLC, libmpv and FFmpeg from source, as before; the bundle 65 MB), its `--self-check` passes on **Qt 6.11.2**, VLC
  3.0.23 and libmpv 0.42, so the code runs on 6.11 as decided; on the GNOME desktop, two cells playing.
- 7.5 Snap on core24 with libmpv (MPV_PLAN 12.1).
  core24 with the `gnome` extension (fonts, cursors, Mesa through `gpu-2404`) in place of kde-neon; Qt from PyQt6's
  wheel, with the xcb libraries it needs that the extension's runtime hasn't got; `libmpv2` from Ubuntu 24.04 (mpv
  0.37); `apt_dl.sh` (kde-neon's PyQt5 debs) gone. Built with LXD on `test_ubuntu`: snapcraft's linter found libmpv
  missing `libdvdnav`, `liblua5.2` and `libsndio`, which `blacklist_snap.txt` took out for kde-neon's sake; kept now.
  Installed, libmpv still didn't load: BLAS and LAPACK, which Ubuntu keeps in folders of their own and links in by
  update-alternatives, as a snap can't; their folders are on its `LD_LIBRARY_PATH` now. Ubuntu 24.04's `librsvg`
  was left out too, as the gnome runtime's newer one is what its pixbuf loader takes. **Done 2026-11-19**: the
  `--self-check` of the installed snap passes (Qt 6.12.0, VLC 3.0.20, libmpv 0.37); on the GNOME desktop, two cells
  playing, its icon in the dock.
- 7.6 Each package started on a clean machine: Windows, Ubuntu 24.04, Debian 13, macOS 15.
  **Done 2026-11-19, as far as there are machines:** Windows here (the portable's self-check), the AppImage in
  Ubuntu 24.04 and 26.04, Debian 13 and Fedora containers and on the Ubuntu desktop, the Snap and Flatpak on the
  Ubuntu desktop, the `.app` on macOS 15. None of it on GitHub: the branch isn't pushed, so the workflows are read,
  not run. A `dry_run` pre-release on `qt6` is the first run of them.
- 7.7 (asked 2026-11-19) The pre-release no longer runs the tests first, which run on every push and are waited for
  before it's started; `dry_run` builds everything and keeps the files as the run's artifacts, releasing and tagging
  nothing.

## Stage 8: clean-up and docs

- 8.1 Comments that speak of PyQt5 or Qt 5 bugs (`gl_context.py`, `darkmode_windows.py`, `mouse_windows.py`,
  `video_driver.py:111`, `wayland.py`, `wayland_frames.py`, `window_state.py:19`): updated, and workarounds Qt 6 made
  unnecessary removed only where seen to be so.
  **Done 2026-11-19.** PyQt6 has `QEvent.Type.Quit`, so `window_state.py`'s own number for it went. The rest kept,
  each still needed: PyQt6 gives out no Wayland display either (`gl_context.py`), wants `(filter, result)` from a
  native event filter, and Qt 6 still takes the cursor theme from `XCURSOR_*` (stage 4). The GNOME frame comments
  say what Qt 6 draws. Tests that spoke of PyQt5 reworded.
- 8.2 AGENTS.md (PyQt6, the flag trap, the event positions), README (platforms, `libxcb-cursor0`, macOS 14),
  CONTRIBUTING, CHANGELOG, ROADMAP's Qt 6 section, `MPV_PLAN.md`'s Snap notes.
  **Done 2026-11-19**, the CHANGELOG with the commits' hashes. AGENTS.md has a PyQt6 section of
  the traps met here; the README says 64-bit Windows 10 1809+, macOS 14+, `libxcb-cursor0`, the arm64 AppImage and no
  `libfuse2`, and the Snap has MPV. CONTRIBUTING had nothing of Qt 5.
- 8.3 `scripts/qt6_port/` removed. **Done 2026-11-19**; they're in git before it.
- 8.4 `/simplify` once PyQt5 is gone: `flag_value()` to `.value` where the kind is known, fallbacks for both bindings
  (`look.py`'s import among them) dropped.
  **Done 2026-11-19**, four reviews (reuse, simplification, efficiency, altitude), each change checked on PyQt6 6.12:
  - `flag_value()` gone: at every call the kind is known, so `.value` where an int is wanted (key codes, the button
    roles), the flag itself where PyQt6 takes it (`&` on a drop action, `QKeySequence(modifier | Qt.Key.Key_A)`,
    equality of wheel modifiers, `QDialogButtonBox.StandardButton(button)` from QMessageBox's IntFlag).
  - `modifiers_from_event`'s `keyboardModifiers` branch, for events PyQt6 doesn't have, gone.
  - The GL grid's ready signal: `QTimer.singleShot(0, self.ready)`, the signal itself, which PyQt ties to the
    surface and skips once it's gone; only `.emit` crashed. The timer of its own (stage 4) and AGENTS.md's advice
    changed to that; the test that crashed on `.emit` passes.
  - The header line's lookup from the widget's own `__dict__`: a `getattr` miss goes round PyQt's `__getattr__`, at
    3.4 µs for each child added anywhere on GNOME's Wayland.
  - Left as they are: a fixture deleting every top-level widget a test leaves (it would touch every test's
    teardown), the black bars by `QRegion` and a clip (the rectangles are right, the clip would change how they're
    painted), `_told_scheme` as a list (style).

## After the move (not part of it)

What Qt 6 opens up, from ROADMAP: sharp windows at 125% and 150% on Wayland (comes with the move, seen in 4.2), our own
window frame on GNOME, Wayland as Auto there. Also possible: Windows on arm64, and the system colour scheme from
`QStyleHints.colorScheme()` instead of our own watchers. Then the architecture refactor.
