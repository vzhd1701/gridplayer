# Gamepad hotkeys: plan

Status: deferred, not started. Written 2026-10-07 from reading `utils/keymap.py`,
`player/managers/actions.py`, `active_block.py`, `menu.py` and the Flatpak and
Snap packaging. Nothing has been prototyped or tested with a real controller.

## How it fits what's already there

- **Bindings:** they already hold three kinds of keys: keyboard (`QKeySequence`), mouse (`MouseButtonSequence`, looked up in `_mouse_index`) and the drag/hold keys of the "Mouse drag" folder. A gamepad becomes a fourth kind in the same `player/keymap` overrides.
  - Saved shortcuts, conflict checks, the shortcuts tree and Reset would then work without much change.
  - Nobody can have a gamepad binding yet, so no settings migration is needed.
- **Firing actions:** `ActionsManager.trigger(action_id)` already runs an action the way a keyboard shortcut would. A gamepad manager just needs a lookup table from gamepad key to action, like the mouse one.
- **Choosing the video:** "Next Active" and "Previous Active" (Tab / Shift+Tab) already exist. That covers the basics, but they only cycle through videos in layout order.

## Library choice

| Option | Verdict |
|---|---|
| **QtGamepad** | Not usable. PyQt5 doesn't wrap it, and Qt 6 dropped it. |
| **SDL2 via `pysdl2` + `pysdl2-dll`** (recommended) | Bundled SDL2 for Windows (including 32-bit, worth checking), macOS (universal2) and manylinux. SDL's game controller layer maps Xbox, PlayStation, Switch Pro and generic pads to one Xbox-style layout, and handles plugging and unplugging. |
| **ctypes binding to SDL3** | The future path, since SDL2 is in maintenance. PySDL3 downloads its libraries at runtime by default, which is bad for packaging. Keep the backend behind an interface so switching later is cheap. |
| **Separate per-OS backends** (XInput, evdev, GameController) | Three times the code. XInput only sees Xbox pads, so PlayStation pads on Windows wouldn't work. |

## Design

### 1. How a binding is written (decide first, it gets saved permanently)

- **Format:** `Pad A`, `Pad LB+A`, `Pad DPad-Left`, `Pad LT`, `Pad LS-Up`. The prefix appears once, `+` joins buttons, and the last button is the one that fires. Held buttons are written in a fixed order so each chord has one spelling.
- **Names are by position** (A = bottom face button). With SDL's `GAMECONTROLLER_USE_BUTTON_LABELS=0`, the same binding stays on the same physical button on a Switch pad. Labels change only on screen: A/B/X/Y for Xbox, ✕○□△ for PlayStation, Nintendo letters, chosen by `SDL_GameControllerGetType`.
- **No mixing with keyboard modifiers** (`Ctrl+Pad A`).
- **`normalize_shortcut`** must recognise `Pad …` before the `QKeySequence` branch, the way `HOLD_KEYS` is handled now. Otherwise `QKeySequence` rejects `Pad A`, normalisation returns None, and the binding is silently dropped.
- **Other functions to update:**
  - `split_shortcuts` returns three groups.
  - `qkeysequences_for_shortcut` returns `[]` for gamepad keys.
  - `fit_shortcuts` keeps gamepad keys off the drag and hold rows.

### 2. Input logic (`gamepad/input.py`, pure Python, no Qt timers)

- **Interface:** `update(events, now)` returns the bindings that fire. Taking `now` as an argument makes timing tests deterministic.
- **Chords use exact match,** consistent with the drag binding decision.
- **Tap vs hold:** a button that is the held part of any chord fires its own binding on release, and only if no chord used it. Every other button fires on press. This adds a little delay to those buttons, so the default bindings use no chords at all.
- **Triggers and sticks act as buttons:**
  - press at 0.5, release at 0.35, so the binding doesn't flicker on and off near the threshold;
  - a stick reports only its stronger direction, so a diagonal doesn't press two directions;
  - a dead zone.
- **Auto-repeat:** 400 ms delay, then every 80–100 ms, for steps only (seek, frame step, volume, zoom, speed). Mark these with a `"repeat": True` flag in `ACTIONS` rather than copying the keyboard, where holding Space toggles play/pause over and over.
- **Multiple controllers** are merged and share one set of bindings.

### 3. SDL backend (`gamepad/sdl_backend.py`, imported lazily)

- **Set before `SDL_Init`:**
  - `SDL_HINT_NO_SIGNAL_HANDLERS=1`. Without it, SDL takes over SIGINT/SIGTERM.
  - `JOYSTICK_ALLOW_BACKGROUND_EVENTS=1`. We do our own focus gating.
- **Initialise late:** call `SDL_INIT_GAMECONTROLLER` after the window first shows (`QTimer.singleShot`). DirectInput device scanning on Windows is known to stall for seconds with some USB devices.
- **Polling:**
  - on the main thread from a `QTimer`, about 60 Hz while a controller is connected and about 2 Hz otherwise, just to catch plug-ins;
  - the main thread also suits macOS, where SDL reaches the controller through the main run loop.
- **Player processes must never import it.** They're spawned and re-import modules, so the import stays inside the manager.

### 4. `GamepadManager` (`player/managers/gamepad.py`)

- **Only reacts while GridPlayer is the active app.** Gamepad input is global, unlike keyboard input. An optional "Work in background" setting is useful for a second-screen setup and is off by default.
- **Menus and dialogs:** while a modal or popup is open (`is_modal_open()`, `activePopupWidget()`), bindings are suppressed. The timer still fires inside nested `exec_()` loops, so this needs an explicit check.
- **Picking a video:** if there's no active video, the first input picks the last active one, or else the first one. Otherwise "active" actions do nothing, because no pointer is hovering.
- **Feedback:** each input shows the overlay on the active video. The existing `show_overlay` does that.
- **Sharing with the editor:** a single service object parented to `qApp` (always parent Qt objects made in Python, see the style lifetime crash) feeds both the manager and the capture dialog.

### 5. Shortcuts editor

- **"Add gamepad button…":** opens an `AddGamepadShortcutDialog` that captures a chord. The chord is whatever was held at its fullest once all buttons are released. Cancelling is keyboard or mouse only, since B can be captured.
- **Notes in the dialog:** "No gamepad connected" or "Gamepad input is disabled".
- **Rows show the connected controller's labels.**

### 6. Settings

- `gamepad/enabled` and `gamepad/background`, written out literally in `settings.py`.
- A small Gamepad group in the dialog shows the enable toggle and the connected controllers. It's an edit to the `.ui` file followed by `just generate-ui`.

### 7. New actions (useful from the keyboard too)

- **"Active video ← → ↑ ↓":** moves between grid cells by position instead of layout order.
- **"Show menu":** sends a `QContextMenuEvent` at the active video's centre, so `MenuManager.contextMenuEvent` and its add-anchor logic work unchanged.

### 8. Menu and dialog navigation (phase 2)

While a popup or modal is open, the manager sends key presses to it:

| Gamepad | Key |
|---|---|
| D-pad / left stick | Arrow keys |
| A | Return |
| B | Escape |

Without this, the gamepad is stuck once a menu opens.

### 9. Sticks (phase 3)

This reuses the drag and hold setup: add a STICK type to `GestureKind`.

- The "Move picture within its cell" row accepts `Pad RS` alongside `Middle-Drag`.
- Zoom maps to the triggers or a stick axis, and scrubbing maps to the left stick's X axis.
- The folder becomes "Mouse drag and sticks", or a sibling folder.

## Suggested default bindings (no chords)

| Button | Action |
|---|---|
| A | Play/Pause (active) |
| X | Play/Pause [ALL] |
| Y | Fullscreen |
| B | Nothing (kept as "back" for menus) |
| D-pad ← → | Short seek, repeats |
| D-pad ↑ ↓ | Volume, repeats |
| LT / RT | Medium seek, repeats |
| LB / RB | Previous / next active video |
| Start | Show menu |
| Back/View | Single mode |

## Caveats

1. **Steam's desktop controller setup** turns the pad into a mouse and keyboard system-wide, so input would arrive twice. This goes in the docs or the dialog note.
2. **Few buttons, about 150 actions.** Chords are unavoidable for power users, and they add the release delay described above.
3. **Moving the mouse changes the active video** (`update_active_under_mouse`). A gamepad user who nudges the mouse loses their selection. This is acceptable, but needs a visible indicator: "Show overlay border" helps.
4. **COM and WinRT on Windows.** SDL's Windows.Gaming.Input backend does its own COM/WinRT setup on the main thread and tears it down again in `SDL_Quit`. With the single-process VLC drivers (`*_sp`), VLC shares the main process. That's close to the SensorsApi crash on reload that was fixed with `CoIncrementMTAUsage`, so test shutdown, and reloading with all videos, in single-process mode. If needed, turn off that backend with `SDL_HINT_JOYSTICK_WGI=0`.
5. **Packaging:**
   - **PyInstaller:** keep only `SDL2.dll`/`libSDL2`. pysdl2-dll also ships SDL2_image, mixer and ttf with their codecs, so add those to the blacklist. Check how pysdl2 finds the library in a frozen app (`PYSDL2_DLL_PATH`).
   - **macOS:** the dylib must be signed and notarised with the bundle. Check that no Input Monitoring prompt appears.
   - **Flatpak:** add `--device=input` (Flatpak ≥1.15.6). Older versions need `--device=all`, which Flathub reviewers question. The runtime should have SDL2 via sdl2-compat (worth checking).
   - **Snap:** the `joystick` plug isn't auto-connected, so it needs a store request or a `snap connect` instruction.
   - **PyPI:** platform-marked dependencies, plus a graceful "SDL2 not found" fallback that greys the feature out.
6. **Linux permissions:** SDL's HIDAPI driver needs hidraw access, often missing without udev rules. It falls back to evdev, which loses some PlayStation and Switch features (not buttons).
7. **Polling cost:** a 60 Hz main-thread timer is cheap but stops idle wake-ups, hence the adaptive rate. When the main thread is busy, input is delayed, not lost, because SDL queues it.
8. **Testing:**
   - **CI:** has no controllers, but SDL's virtual joystick (`SDL_JoystickAttachVirtualEx`) allows a real end-to-end test there.
   - **Pure-Python parts:** the input logic, the binding format and the manager's gating are fully unit-testable with a fake backend.
   - **Real hardware:** has to be done by hand, on 3 OSes × Xbox/PlayStation/Switch pads.
9. **Translations:** new strings are button names, action titles and dialog notes. Write them as literal `translate()` calls without touching `.ts` files.

## Phases

0. **Spike, about half a day:** SDL init and polling inside GridPlayer on Windows, Linux and macOS, plus the frozen builds and the Flatpak permission. This settles the dependency choice before anything depends on it.
1. **Core:**
   - binding format and input logic, with tests;
   - manager, editor capture, settings;
   - auto-pick of the active video, spatial navigation actions;
   - defaults.
2. **Menu and dialog navigation,** plus "Show menu".
3. **Sticks** in the gesture folder.
4. **Optional:** button glyph icons in the tree.

## Open decisions

1. **Library:** SDL2 via pysdl2 (recommended), your own ctypes binding to SDL3, or separate per-OS backends?
2. **Defaults:** gamepad on by default, with background mode off?
3. **Default bindings:** ship the table above, or ship none?
4. **Chords:** may any button be held in a chord (exact match, solo fires on release), or only the shoulder and trigger buttons?
5. **Phase 1 scope:** include menu navigation in phase 1 or defer it?
6. **Binding format:** is `Pad LB+A` OK?
