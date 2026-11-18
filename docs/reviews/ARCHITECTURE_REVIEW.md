# Architecture review

A read of the whole of `gridplayer/` (about 118,000 lines of its own Python, plus the vendored `vlc.py` and `mpv.py`),
done 2026-11-16 on `develop` with the Mosaic work uncommitted. It looks for the places where the structure makes the
app harder to change, and says what to do about each, with one question in mind: what would have to be true before
somebody else could write a plugin for it.

Nothing was changed. The figures are counts by `grep` and by a small AST script, so they are close, not exact.

## The short answer

The app is not a mess. It has a clear shape: a `Player` window made of managers, a command table the menu and the
keys go through, a `VideoBlock` per cell with its parts, and a video frame per driver. Several parts are already
declarative (settings fields and pages, the menu, the actions). The tests are large and there is a real-app harness.

What stands in the way of plugins is the same thing in every layer: **everything is put together in one place, by
hand, from literals**. The managers, their connections, the commands, the actions, the menu, the block's parts, the
drivers, the resolvers and the settings are each a closed list written out in one file. Adding a feature means
editing five to thirteen files that have nothing to do with it. A plugin can edit none of them.

So the refactors that pay most are the ones that turn a closed list into a registry that things add themselves to.
The core features would be the first users of those registries; a plugin would be one more.

### Ranked

Benefit is for maintainability and for plugins together. Cost is a rough guess.

| # | Finding | Benefit | Cost | Plugins need it |
| --- | --- | --- | --- | --- |
| 1 | `Player` wires 32 managers and 116 connections by hand | Very high | Medium | Yes, first |
| 2 | Commands and context: one flat, untyped namespace | Very high | Medium | Yes, first |
| 3 | `ACTIONS` and the menu are frozen literals | Very high | Medium | Yes |
| 7 | Settings: two global singletons, no change notice | Very high | High | Yes |
| 5 | `VideoBlock`'s parts are a fixed list reaching into its privates | High | Medium | Yes |
| 6 | Every driver inherits from the VLC frame | High | High | For driver plugins |
| 4 | `[ALL]`: a signal and a connection for each command | High | Low | Yes (quick win) |
| 10 | URL resolvers and list formats are hard-coded maps | High | Low | Yes (quick win) |
| 8 | One setting travels by three hand-written signal families | High | Medium | Follows 7 |
| 9 | Models read global state, and are closed to extra data | High | Medium | Yes |
| 16 | No lifecycle: no teardown, no error boundary | High | Low | Yes |
| 12 | Package layers run in circles | Medium | Medium | Indirectly |
| 11 | `GridManager` is one class for six grid modes | Medium | High | For layout plugins |
| 13 | Dialogs are opened from inside logic | Medium | Medium | Helps |
| 19 | Texts are translated as modules are imported | Medium | Medium | Yes |
| 15 | Event filters: order by position in a list | Medium | Low | Helps |
| 18 | Overlay and seek-bar marks: fixed wiring | Medium | Low | Yes |
| 14 | 160 platform checks in 57 files | Medium | Medium | No |
| 17 | Five ways to do work off the GUI thread | Low | Medium | Helps |
| 20 | A few very large UI files | Low | Medium | No |

If only five things are done, do **1, 2, 3, 7 and 5**, with **4, 10 and 16** on the way because they are cheap. That
set is what turns "a plugin would have to patch the source" into "a plugin registers a manager, some commands, some
actions, some settings and a block part".

---

## Findings

### 1. `Player` wires everything by hand

**Where:** `gridplayer/player/player.py`, `gridplayer/player/manager.py`.

`Player.__init__` holds the whole app in three literals:

- `self.managers`: 32 managers by name, one more by platform.
- `self.connections`: 116 `("signal", "manager.slot")` pairs as strings.
- `self.event_filters` and `self.global_event_filters`: two ordered lists of manager names.

What is wrong with it:

- A manager does not say what it needs or what it gives. That knowledge is in `player.py`, away from the manager.
- Order matters and is kept by comments: "after the playlist's own: the cells close before their bookmarks are
  cleared away". Qt calls slots in the order they were connected, so the order of the dict is part of the behaviour.
- Managers are made in dict order and put values on the context as they are made. One made earlier cannot read what a
  later one sets. `VideoBlocksManager.sync_pause` already guards for this with
  `getattr(self._ctx, "is_single_mode", False)`.
- A name that is misspelt fails only when `Player` is made.
- A new feature always edits `player.py`. A plugin cannot.

**Suggested refactor:** let each manager carry its own wiring.

```python
class BookmarksManager(ManagerBase):
    name = "bookmarks"
    after = ("playlist",)  # made, and connected, after these
    connects = (
        ("playlist.bookmarks_loaded", "set_bookmarks"),
        ("playlist.playlist_closed", "clear"),
    )
    event_filter = None  # or FilterSpec(scope="app", priority=40)
```

`ManagersManager` then collects the classes from a registry, sorts them by `after`, makes them, and connects them.
`Player` becomes a list of classes, and later not even that. Connections that only name other managers
(`"settings.reload" -> "video_blocks.reload_videos"`) go to the receiving side.

Do it in two steps: first move each block of `self.connections` into its manager as a class attribute, with `Player`
still reading them in the same order (no behaviour change, easy to review); then replace dict order with `after`.

**For plugins:** this is the door. A plugin that adds a service to the app is a manager class registered with the
same registry.

### 2. Commands and context are one flat, untyped namespace

**Where:** `gridplayer/player/manager.py` (`Commands`, `Context`), every `commands` property in
`gridplayer/player/managers/`.

- More than 350 commands live in one dict, keyed by bare strings. `GridManager` gives 107, `VideoBlocksManager` 60,
  `ActiveBlockManager` 56.
- The one table mixes four different things: actions for the user (`add_videos`), yes/no questions for the menu
  (`is_grid_free`), menu builders (`menu_generator_chapters`), and calls between managers that no menu ever uses
  (`remember_closed`, `set_add_anchor`, `video_count_batch`). There are 151 `self._ctx.commands.x(...)` call sites;
  140 are managers calling each other. So the command table is also the app's internal service locator.
- `Context` holds 30 loose variables set by whichever manager owns them (`is_disable_overlay`, `synced_view`,
  `video_blocks`, `lists`, `bookmarks`, `actions_manager`...). Reading one calls it if it is callable
  (`Context.__getattr__`), so `ctx.video_driver` is a hidden function call.
- Nothing is typed. No editor can jump from `self._ctx.commands.get_cell_at` to its code, rename it, or say what it
  takes. `tests/test_dotted_commands.py` exists to catch what a type checker would.
- Names collide only by luck. `_register_commands` raises on a clash, which is right for the core and fatal for two
  plugins that pick the same word.

**Suggested refactor:** split the two jobs.

1. **Services, typed.** What managers ask of each other becomes plain attributes with types:
   `self._app.grid.cell_at(pos)`, `self._app.video_blocks.all`. A small `App` (or `Services`) object with a typed
   attribute per manager replaces the `ctx.commands` calls between managers, and the 30 context variables move back
   onto the manager that owns them as properties. This can go one manager at a time.
2. **Commands, registered.** What the menu and keys can name stays a string table, but with a record for each:

   ```python
   @command("grid.arrange_tiles")            # an action
   @query("grid.is_free")                    # a predicate for show_if / check_if
   @menu_source("chapters.menu")             # a menu generator
   ```

   A dotted prefix per owner (`grid.`, `playlist.`, later `plugin_id.`) ends collisions. The old bare names can stay
   as aliases while `actions.py` is moved over.

**For plugins:** a plugin gets a typed, documented surface to call (`app.video_blocks`, `app.playlist`) and a
namespaced way to add commands. Without this, the plugin API would be 350 undocumented strings.

### 3. `ACTIONS` and the menu are frozen literals

**Where:** `gridplayer/params/actions.py` (3,432 lines), `gridplayer/params/menu.py` (893 lines),
`gridplayer/player/managers/actions.py`, `gridplayer/utils/keymap.py`.

- `ACTIONS` is one `MappingProxyType` literal with more than 425 entries. `SECTIONS` and `SUBMENUS` are the same.
  They are read-only on purpose, and nothing can add to them.
- An action's key is its old English title (`"Play / Pause"`, `"Single Mode ON / OFF"`, `"Crop When Big 20%"`). That
  string is also what the keymap stores in the user's ini. Renaming a menu item means a migration
  (`_migrate_aspect_to_cell_view_mode` moves shortcuts from `"Aspect Fit"` to `"View Mode Fill"`).
- 114 entries are `("all", ...)` and 147 are `("active", ...)`: most `[ALL]` actions are a second, hand-written copy
  of a single-video one with a different prefix.
- A feature's actions sit in this file, far from the feature. Grid modes alone are named 42 times in it.

**Suggested refactor:**

- An `ActionRegistry` that features add to: `actions.add(Action(id="playback.play_pause", title=..., keys=...))`.
  Start by splitting `actions.py` into one module per domain (`actions/playback.py`, `actions/grid.py`,
  `actions/audio.py`...), each still a literal, joined at start. That alone makes the file workable.
- Give actions stable ids that are not titles, with the old key kept as `legacy_id` so stored keymaps still load.
  New actions never need a migration again.
- Make the `[ALL]` twin from the single one: `Action(..., also_for_all=True)` builds both. That removes about a
  hundred entries.
- Give the menu named places to add to (`menu.contribute("video_active/after:Zoom", ...)`) instead of one nested
  tuple.

**For plugins:** an action with a key binding and a menu place is the most common thing a plugin wants. The keymap
editor, the tray and media keys all read the same registry, so a plugin's action would show up in all of them for
free.

### 4. `[ALL]`: a signal and a connection for each command

**Where:** `gridplayer/player/managers/video_blocks.py`.

`cmd_all(command, *args)` does `getattr(self, f"all_{command}").emit(*args)`. So every command that can be sent to
all videos needs:

1. a `pyqtSignal` on `VideoBlocksManager` (57 of them),
2. a line in `_add_video_block` connecting it to the block or the right part (57 lines),
3. the entry in `actions.py`.

AGENTS.md has a paragraph only to explain this route. The signal carries no information the command name does not
already have: `("active", "chapters.next")` reaches the method by `attrgetter`, and `("all", "next_chapter")` could do
the same.

**Suggested refactor:** one loop.

```python
def cmd_all(self, command, *args):
    for vb in self._ctx.video_blocks:
        attrgetter(command)(vb)(*args)
```

with the same dotted names `active` takes. The 57 signals and 57 connections go, the two name styles
(`all_next_chapter` and `chapters.next`) become one, and `tests/test_dotted_commands.py` checks both the same way.
Check two things first: commands whose "all" form differs from the single one (`seek` vs sync), and that nothing
relies on a closed block having been disconnected.

**For plugins:** a plugin's block part would work with `[ALL]` without touching the manager. Low cost, and it removes
a rule people have to remember.

### 5. `VideoBlock`'s parts are a fixed list reaching into its privates

**Where:** `gridplayer/widgets/video_block.py` (2,442 lines, 150 methods), the 14 `video_block_<part>.py` files,
`gridplayer/player/managers/active_block.py`.

Splitting the block into parts was the right move and it is half done:

- The parts are named in four places: `VideoBlock.__init__`, `_block_parts()` in `tests/conftest.py`, the connections
  in `VideoBlocksManager._add_video_block`, and AGENTS.md.
- `VideoBlockPart` is only `self._block = block`. Parts use the block as an open bag: `self._block._x` 58 times,
  21 of them `self._block._ctx`, and private methods such as `_start_load`, `_load_and_play`, `_ensure_video_driver`,
  `_step_at_end`. Parts also call each other through the block (35 places).
- There are no hooks. The block calls its parts by name at the right moments (`self.chapters.clear()`,
  `self.sponsorblock.forget_shown()`, `self.time_ahead.forget_reports()` inside `_destroy_video_driver`). A new part
  means editing those methods.
- Rules about a part's commands are kept elsewhere: `LOADING_COMMANDS` in `active_block.py` lists 37
  `"part.method"` strings that may run while a video loads.
- Whether something is on the menu for a block is asked through 40-odd `is_active_*` methods on
  `ActiveBlockManager`, each a thin wrapper over a part.

**Suggested refactor:**

- A real base class with a lifecycle the block drives: `on_video_set`, `on_driver_ready`, `on_driver_gone`,
  `on_time`, `on_close`. `_destroy_video_driver` becomes `for part in self.parts: part.on_driver_gone()`.
- A narrow, public face of the block for parts (`block.playback`, `block.params`, `block.driver`, `block.services`)
  in place of `_block._anything`. Make what parts need public, and stop the rest.
- Put the rule on the method: `@block_command(while_loading=True)` replaces `LOADING_COMMANDS`, and the guards in
  `video_block_guards.py` already work this way.
- A part registry: `VideoBlock` makes whatever is registered, in order. The test helper reads the same registry.
- A generic query `("active_is", "audio.has_tracks")` replaces most of the `is_active_*` wrappers.

**For plugins:** "do something for each video" (stats panel, auto-skip rules, a scrobbler, per-video filters) is a
block part. With hooks and a registry it is one class. This is the second door after managers.

### 6. Every driver inherits from the VLC frame

**Where:** `gridplayer/widgets/video_frame_vlc_base.py`, `video_frame_mpv.py`, `video_frame_dummy.py`,
`gridplayer/vlc_player/static.py`, `gridplayer/vlc_player/video_driver_base.py`,
`gridplayer/player/managers/video_driver.py`.

MPV was added by standing on the VLC classes:

- `VideoFrameMpv(MpvFrame, PaintedVideoFrame, VideoFrameVLC)` and `VideoFrameDummy(VideoFrameVLC)`. The base has 117
  methods; the driver-neutral ones (view maths, placement, signals) sit beside VLC-only ones (`_vlc_picture_rect`,
  first-picture polling, the pause snapshot).
- `VideoDriverMpv(VLCVideoDriver)`.
- The types every driver shares are in the VLC package: `Media`, `MediaInput`, `VideoTrack`, `AudioTrack`,
  `DISABLED_TRACK`, `SeekLanding`, `seek_landing`. `mpv_player/player.py` imports from `vlc_player.static`.
- `VideoBlock.init_video_driver` calls `get_vlc_options(...)` and passes `vlc_options=` to whatever driver it has.
  Its field is typed `VideoFrameVLC | None`.
- What a driver can do is said by class attributes found with `getattr` (`is_native_surface`,
  `must_reload_for_subtitle_style`, `is_late_with_subtitles`, `has_adaptive_demuxer`...) and, in places, by
  `hasattr(driver, "set_log_level_vlc")`.
- `VideoDriverManager` knows every driver by name and has a method per library (`set_mpv_skip_frames`,
  `set_log_level_vlc`...), each wired from `SettingsManager` in `player.py`.
- The code that runs inside the decoder process is in the widget modules: `InstanceProcessVLCSW` and
  `PlayerProcessSingleVLCSW` are defined in `widgets/video_frame_vlc_sw.py`. A child process that is spawned imports
  the widget stack to find its own class.
- Managers and the settings form reach past the frame into the libraries: `active_block.py` imports
  `mpv_player.abilities` and `vlc_player.static`, `params/settings_fields/choices.py` loads libmpv.

**Suggested refactor:**

- A `gridplayer/drivers/` package: `base.py` with the neutral `VideoFrame` (signals, view placement, the abstract
  playback calls) and a `DriverCapabilities` dataclass; `vlc/` and `mpv/` beside it, each with its frame, its driver
  and its process-side player in separate modules.
- Move `Media`, `MediaInput`, the tracks and the seek helpers to `gridplayer/models/media.py`.
- A driver registry: `DriverSpec(id, library, make_frame, options_from(video), settings_hooks)`. The driver manager
  picks from it. Per-driver settings changes go to `driver.apply_setting(key, value)` in place of one method and one
  connection each.
- `VideoBlock` asks `driver.options_for(video)` for whatever that driver calls its options.

This is the largest job on the list and the riskiest, because the two libraries are full of measured quirks. Do it by
moving code without changing it: first the shared types, then the neutral base lifted out from under `VideoFrameVLC`,
then the files.

**For plugins:** needed only for a third backend (GStreamer, a browser view, a capture card). But note one limit for
any plugin that wants to touch the player: with the multi-process VLC drivers the player object is in another
process. A plugin API has to stop at the frame's interface, never hand out the libvlc or mpv handle.

### 7. Settings: two global singletons, no change notice

**Where:** `gridplayer/settings.py`, `gridplayer/playlist_settings.py`, `gridplayer/player/managers/settings.py`.

- `Settings()` is called at 176 places in 63 files; `PlaylistSettings()` at 88 places in 20. Models, utils, widgets,
  resolvers and both player libraries all read the user's ini directly.
- `_default_settings` is one closed dict of 168 keys. The type of the default is the schema. There is nowhere for a
  key that the core does not know.
- A setting has no way to say "I changed". After the dialog closes, `SettingsManager._apply_settings` compares a
  snapshot of everything from before with what is there now, and emits one of 26 hand-written signals from a
  key-to-signal table. `_is_reload_needed` and `_is_restart_needed` are two more hand-kept sets of keys. A setting
  missing from these tables simply does nothing until restart, with no error.
- Tests cannot give code a settings object, so they patch: `FakeSettings` in `conftest.py`, and over a thousand
  `patch` calls in `tests/`.
- The declarative side is good: `params/settings_fields/` and `settings_pages.py` describe fields and pages well.
  The runtime side does not use them.

**Suggested refactor:**

- One `SettingsStore` object, made once and passed in (to managers through the app object, to the rest by argument).
  The module-level `Settings()` can stay as a thin wrapper while call sites move.
- It emits `changed(key, value)`. Whoever cares subscribes: `settings.on("playlist/overlay_timeout", self.set_timeout)`.
  `SettingsManager`'s table and its 26 signals go.
- Put "what a change needs" on the field definition, where the rest about the field already is:
  `Field(..., applies=Apply.LIVE | Apply.RELOAD | Apply.RESTART)`. The reload and restart sets are then read from the
  registry, and the existing registry test can require every key to say.
- Let a namespace register keys: `settings.register("plugins/<id>/...", default, field)`. The form already builds
  pages from data, so a registered page appears in the dialog and in the search.

**For plugins:** a plugin needs settings, a page for them, and to hear when they change. All three are closed today.

### 8. One setting travels by three hand-written signal families

**Where:** `gridplayer/player/managers/playlist.py`, `settings.py`, `video_blocks.py`, `player/player.py`.

Follow `playlist/disable_overlay` through the code. It is named in 13 files:

1. the default in `settings.py`,
2. the field in `params/settings_fields/playlist.py`,
3. its place in `params/settings_pages.py`,
4. the binding in `params/settings_bindings.py`,
5. the field on the `Playlist` model,
6. `PlaylistManager.disable_overlay_loaded` signal, emitted when a playlist opens,
7. `SettingsManager.set_disable_overlay` signal, emitted when the dialog changes it,
8. two connections in `player.py`, one for each of those,
9. `self._ctx.is_disable_overlay`, a copy on the context,
10. `set_disable_overlay` and `toggle_disable_overlay` on `VideoBlocksManager`, the toggle writing
    `PlaylistSettings()`,
11. three commands (`is_`, `set_`, `toggle_`) in its `commands`,
12. the action in `params/actions.py`,
13. the readers in `video_block.py`.

There are 23 `*_loaded` signals on `PlaylistManager` and 26 `set_*` on `SettingsManager` doing this, each paired by
hand in `player.py`. The same value is then held three times: in `Settings`, in `PlaylistSettings` and on the
context.

**Suggested refactor:** once finding 7 gives a store that notifies, a playlist opening is just the session layer
changing many keys, and each emits the same `changed` as an edit in the dialog would. Then:

- both signal families and their connections in `player.py` go,
- the context copies go: read `session.get(key)` where it is needed, or keep a cached attribute fed by one
  subscription,
- a generic `("toggle_setting", key)` / `("is_setting", key)` pair of commands replaces the per-setting triples for
  plain booleans.

A new playlist-level switch would then be: default, field, place on a page, binding, model field, one subscriber. Six
places, all declarative but the last.

### 9. Models read global state, and are closed to extra data

**Where:** `gridplayer/models/video.py`, `models/playlist.py`, `models/grid_state.py`, `gridplayer/settings.py`.

- `Video` fields default through `session_field(...)`, a `default_factory` that calls `PlaylistSettings().get(...)`.
  So `Video(uri=...)` gives a different object depending on which playlist is open and what the ini says. A model
  cannot be built or compared in a test without that global state.
- It makes an import cycle the code already works around: `models` imports `settings` and `playlist_settings`, which
  import `models`. `playlist_settings.py` passes a plain dict "which keeps this module importable without
  models.playlist (import cycle)".
- `Video`, `Playlist` and `GridState` are fixed schemas. Pydantic drops keys it does not know, so anything a newer
  version or a plugin wrote into a playlist is lost on the next save.
- Format changes are handled by `mode="before"` validators inside the models (`_migrate_legacy_fields`,
  `_migrate_legacy_mouse_flags`...), and again in `Settings` (`_migrate_*`). The playlist has a `version`, but the
  migrations are not keyed by it; each one sniffs for old keys.
- `Playlist` lists every playlist-level setting as its own field (about 50), a third copy of the list in
  `settings.py` and `settings_bindings.py`.

**Suggested refactor:**

- Build videos through a factory that is given the defaults: `VideoFactory(session).new(uri)`. The model itself has
  plain defaults or required fields. The cycle goes with it.
- Add `extras: dict[str, dict]` to `Video` and `Playlist`, keyed by owner id, kept as read and written back
  untouched. That is the whole of plugin data storage, and it also protects users who open a new playlist in an
  older build.
- Keep playlist settings as a `dict[str, Any]` validated against the field registry, in place of 50 model fields.
- Move migrations to a chain by version: `MIGRATIONS = {1: to_v2, 2: to_v3}` run on the raw dict before validation.

**For plugins:** a plugin that keeps anything per video or per playlist needs `extras`. Nothing else on this list
gives it somewhere to put data.

### 10. URL resolvers and list formats are hard-coded maps

**Where:** `gridplayer/utils/url_resolve/url_resolve.py`, `resolver_base.py`, `gridplayer/utils/list_files.py`,
`gridplayer/utils/sponsorblock.py`.

- `ResolverBase` is already a clean interface (`is_able_to_handle`, `streams`, `title`, `chapters`, `details`).
  But `_resolver_map()` is a literal of three, keyed by the `URLResolver` enum, and that enum is also the value of a
  setting and of the per-URL patterns list. A fourth resolver means a new enum member, new choices, new texts.
- `_pick_resolvers` has YouTube written in (`_is_match_youtube`), and `ResolverBase` has a `youtube_id` property.
  Site-specific knowledge is in the generic path.
- List files: `_kind_of` in `list_files.py` chooses between `parse_m3u`, `parse_pls` and `parse_xspf` by `if`.
- SponsorBlock is the only source of skip segments, and its control is built into the block.

**Suggested refactor:** three small registries, each a few dozen lines:

- `resolvers.register(id, cls, priority, title)`; the setting stores the id string; "which resolver first" reads the
  registry.
- `list_formats.register(extensions, sniff, parse, write=None)`.
- A `SegmentProvider` interface that SponsorBlock implements; the block part asks all providers.

**For plugins:** this is the cheapest real plugin point and the most likely first request ("support site X", "read
format Y"). It can ship before any of the larger work and would prove the registry pattern.

### 11. `GridManager` is one class for six grid modes

**Where:** `gridplayer/player/managers/grid.py` (2,703 lines, 193 methods, 107 commands), `utils/layout/`.

The layout engines themselves are well separated and pure (`GridLayout`, `FlowLayout`, `FreeTiles`, `arrange.py`,
`lines.py`, `strip.py`), which is the hard part done. The manager above them is not:

- It holds all three engines at once and picks by `self._mode` in method after method.
- It also owns the undo and redo stacks, empty cells, the add anchor, tile stacking and overlay cutting, Mosaic's
  hold and rest timers, Single Mode's strip, and templates.
- Four more managers (`grid_lines`, `free_tiles`, `grid_edit`, `tile_edit`) exist beside it and reach in through
  commands.
- Each mode's switches are commands on this one class (`is_grid_fit`, `tile_crop`, `is_grid_preallocate`...), and
  the mode enum is tested 28 times here and 42 times in `actions.py`.

**Suggested refactor:** a `GridModeController` per mode family (rows/columns/shapes, fixed, tiles) behind one
interface: `place(videos)`, `drop(...)`, `state()`, `restore(state)`, `commands()`, `menu()`. `GridManager` keeps what
is common: the `CellLayout`, the current controller, undo as its own small class, empty cells. Each controller
brings its own commands and actions (findings 2 and 3 make that possible).

Leave this until the registries exist. It is a large move in the part of the app that is changing fastest, and the
uncommitted Mosaic work is in exactly these files.

**For plugins:** a layout mode as a plugin would need it. Few plugins will want that.

### 12. Package layers run in circles

**Where:** the whole tree. Top-level imports between packages, counted:

| From | To | Imports |
| --- | --- | --- |
| `utils` | `params` | 55 |
| `params` | `utils` | 20 |
| `dialogs` | `widgets` | 29 |
| `widgets` | `dialogs` | 16 |
| `settings` | `models` | 5 |
| `models` | `settings`, `playlist_settings` | 3 |
| `widgets` | `vlc_player` | 31 |
| `utils` | `settings` | 12 |
| `params` | `main` | 1 (`theme.py` imports `init_icons`) |
| `utils` | `dialogs` | 1 (`excepthook.py`) |

- `utils` has 111 modules of at least four kinds: pure helpers (`time_txt`, `aspect_calc`), domain logic (`bookmarks`,
  `next_file`, `list_refresh`, `media_import`), platform services (`win32_tray`, `wayland`, `darkmode_linux`,
  `media_session_macos`) and infrastructure (`cache`, `network`, `cookies`, `stream_proxy`, `url_resolve`).
- `params` holds both plain constants and enums (`static.py`, `env.py`) and UI assembly that needs the translator
  loaded (`actions.py`, `menu.py`, `settings_fields/`).
- The cycles are kept from failing by function-level imports (about 40 of them) and by import order.

**Suggested refactor:** name the layers and check them.

```text
core/       enums, constants, models, pure maths (layout, aspect) - no Qt widgets, no settings
services/   settings, cache, network, resolvers, proxy, lists     - Qt core at most
platform/   one backend per OS behind small interfaces
drivers/    vlc, mpv (finding 6)
ui/         widgets, dialogs, overlay, settings form
app/        player, managers, actions, menu, start-up
```

Moving 300 files at once is not worth the churn. The cheap version: write the rules down, add
[import-linter](https://github.com/seddonym/import-linter) to CI with today's violations listed as known, and let
the list only shrink. New code lands in the right layer; old code moves when it is touched.

**For plugins:** a plugin API is a promise about which modules are safe to import. Without layers there is no
smaller set to promise.

### 13. Dialogs are opened from inside logic

**Where:** block parts and managers. About 17 modal calls in `widgets/` and 16 in `player/managers/`.

`AudioControl`, `SubtitleControl`, `RecoveryControl`, `StreamControl` and `Bookmarker` import dialog classes and call
`.exec_()` or `QCustomSpinboxInput.get_int(...)` in the middle of a command. `VideoBlocksManager` does the same for
`[ALL]`. This is the cause of the `widgets` to `dialogs` cycle in finding 12. It also means a part cannot be driven
in a test without patching a dialog, and that the "ask, then apply" pair is written twice, once for one video and
once for all.

**Suggested refactor:** an `Interaction` service on the app object with the few shapes there are: `ask_int`,
`ask_text`, `ask_time`, `confirm`, `pick_file`, `warn`. Parts call `self._ui.ask_int(...)`. Tests give a fake that
answers. Many commands then split cleanly into "ask" (in the action) and "apply" (in the part), and the `[ALL]` form
reuses the same ask.

**For plugins:** plugins get dialogs that look like the app's without importing its dialog classes.

### 14. Platform checks are scattered

**Where:** 160 `env.IS_WINDOWS` / `IS_LINUX` / `IS_MACOS` / `IS_KDE` / `IS_FLATPAK` checks in 57 files.

Some features already do this well: `media_session_{linux,macos,windows}.py`, `darkmode_{linux,windows}.py`,
`keepawake_macos.py`. Others branch inline in the middle of shared code: `video_frame_vlc_hw.py` (9),
`video_frame_vlc_hw_sp.py` (8), `tray.py`, `drag_n_drop.py`, `single_instance.py`, `theme.py`.

**Suggested refactor:** carry on with the pattern that is there. A `platform/` package with one small interface per
concern (window chrome, tray, single instance, native video surface, file manager) and a backend per OS, picked once.
Inline checks inside drivers that are about measured driver quirks can stay; they are data, not structure.

Not needed for plugins. It pays in testing: a Linux-only branch can be unit-tested on Windows when it is a class.

### 15. Event filters: order by position in a list

**Where:** `gridplayer/player/manager.py`, `gridplayer/player/managers/base.py`, `player.py`.

- Six managers filter every event of the application, in the order they were appended to `global_event_filters`,
  each with a comment on why it must come before the next ("takes its press before a drag would move the video").
  Seven more filter the player window.
- Which gesture wins is therefore spread over list order, each manager's own checks, and `is_elsewhere`.
- `ManagerBase.eventFilter` calls `inspect.signature` on the handler for every event it handles, to see how many
  arguments it wants.

**Suggested refactor:** give each filter a declared priority and scope (finding 1's `event_filter` attribute), and
resolve the handler's arity once when `event_map` is built. Longer term the mouse gestures (pan, zoom-select, tile
drag, line drag, drag and drop) would be clearer as one gesture arbiter that asks each candidate "do you claim this
press?" in priority order.

**For plugins:** a plugin that handles input needs a place in that order that does not depend on when it was loaded.

### 16. No lifecycle, no teardown, no error boundary

**Where:** `gridplayer/player/manager.py`, `gridplayer/utils/misc.py`, `player.py`.

- A manager's life is `__init__`, then `init()` if it has one (found by `getattr`). There is no `stop`.
- Cleanup is opt-in by wiring: five managers have `("window_state.closing", "cleanup")` written in `player.py`.
  One that forgets is never told.
- The process ends with `os._exit`, so anything not flushed by hand is lost. `PlaylistManager.remember_last_playlist`
  calls `Settings().sync()` for that reason.
- An exception raised in a Qt slot aborts the process (AGENTS.md notes it kills a whole test run). A driver crash is
  reported by raising `PlayerException` from a slot on purpose.

For the core this is livable. For plugins it is not: one plugin's bug in a slot takes the app down, and there is no
moment at which a plugin is told to save or let go.

**Suggested refactor:**

- `ManagerBase.start()` and `ManagerBase.stop()`, called by `ManagersManager` in order and in reverse order. `stop`
  runs on close before `os._exit`. Low cost, and it removes the `closing -> cleanup` wiring.
- A guarded call at every point where the core calls code it does not own (plugin hooks, command handlers of
  plugins): catch, log with the plugin's id, disable that plugin after repeated failures. The core's own slots can
  stay as they are.
- A crash signal in place of raising from a slot: `driver.crashed -> app.fatal(traceback)`.

### 17. Five ways to do work off the GUI thread

**Where:** about 20 modules.

`QThread` with a worker object (`url_resolve`, `list_info`, `add_videos`), bare `threading.Thread` (`thumbnails`,
`file_checks`, `sponsorblock`, `folder_index`), `OffThread` (`utils/off_thread.py`), `CommandLoopThreaded` for the
players, and a module-level `_abandoned` set that keeps unfinished resolver threads alive. Each has its own answer
to "the asker went away" and "stop".

**Suggested refactor:** one small task service built on what `OffThread` already does: run a function, deliver the
result on the GUI thread, drop it if the owner is gone, pass a stop flag. Move users over as they are touched.
`interface_first()` then lives in one place.

**For plugins:** the single most common plugin bug is touching Qt from a worker thread. A task service is the safe
way to offer.

### 18. Overlay and seek-bar marks have fixed wiring

**Where:** `VideoBlock.init_overlay`, `VideoBlock.update_seek_marks`, `widgets/video_overlay*.py`.

- `init_overlay` connects 33 signal pairs between the block and its overlay, one per button and per label. The
  overlay's buttons are a fixed set.
- `update_seek_marks` builds the bar's marks by asking three parts by name: chapters, SponsorBlock, bookmarks.
- There are four overlay classes for the ways a window can sit over a native video surface, chosen in the block.

**Suggested refactor:**

- Marks: each part may implement `seek_marks() -> Iterable[SeekMark]`; the block joins whatever its parts give.
  A few lines, and the block stops knowing the three by name.
- Overlay: let parts contribute controls to named slots (`top_right`, `bottom_bar`, `status`) through a small
  description (icon, tooltip, action id, visible-when). The four overlay classes keep handling the windowing.

**For plugins:** "show something on the video" and "mark something on the bar" are what per-video plugins do after
they compute anything.

### 19. Texts are translated as modules are imported

**Where:** `gridplayer/params/actions.py` (431 `translate` calls at import), `menu.py`, `settings_pages.py`,
`settings_fields/*.py`, `gestures.py`, `sponsorblock.py`.

The literal tables call `translate(...)` while the module loads. So these modules must be imported after
`init_translator()`, which `tests/test_translation_timing.py` guards and AGENTS.md warns about. It also means the
language cannot change without a restart, and that import order is part of correctness.

**Suggested refactor:** keep the literal context and text at the definition, as `pylupdate5` requires, but translate
when the text is shown. `QT_TRANSLATE_NOOP("Actions", "Play")` marks a string for extraction without translating it
(check that `pylupdate5` picks it up in this layout before committing to it); the action and field records keep the
pair and a `title` property translates on read. `QDynamicAction.adapt` already reads the title each time a menu is
built, so the menu side needs no other change.

**For plugins:** a plugin loads at some later, unknown moment and ships its own `.qm`. Titles resolved on read work
whenever that is. It needs its own translation context too; the registry can require one per plugin.

### 20. A few very large UI files

**Where:** `dialogs/media_list.py` (4,319 lines: model, delegate, view and dialog together),
`widgets/video_overlay_elements.py` (2,709), `widgets/keymap_tree_view.py` (2,005), `dialogs/bookmarks.py` (1,828).

These are big more than they are tangled. `media_list.py` would split along its own class lines
(`ListItemsModel`, `_RowDelegate`, `ItemList`, `MediaListDialog`) into a small package with no change of behaviour.
Low priority: it helps reading and review, not extension.

---

## What is already right

Worth saying, because the refactors above should copy these, not replace them:

- **Settings fields and pages.** What a setting is and where it is shown are data, with tests that the three lists
  agree. The same idea, applied to the runtime side, is finding 7.
- **`VideoBlockPart`.** The split is the right one. It needs an interface, not a redesign.
- **The layout engines** in `utils/layout/` are pure and tested without Qt widgets.
- **`ResolverBase`** is a ready-made plugin interface missing only a registry.
- **Asking the library what it can do** (`mpv_player/abilities.py`, `option_info`) instead of guessing from the
  version or platform. A driver capabilities object is the same habit made uniform.
- **`settings_bindings.py`** has no presentation imports, on purpose. That is a layer rule already being kept.
- **`tests/real_app`** drives the real player through its menus. Every refactor here moves wiring, and this harness
  is what makes that safe to do.

## What a plugin system would look like after

Not a design, only the shape the findings point at.

A plugin is a Python package found by an entry point group (`gridplayer.plugins`) or in a folder under the user data
directory. It exposes one function:

```python
def register(api: PluginAPI) -> None:
    api.resolvers.register(...)  # finding 10
    api.list_formats.register(...)  # finding 10
    api.settings.register(...)  # finding 7
    api.actions.add(...)  # finding 3
    api.commands.add(...)  # finding 2
    api.block_parts.register(...)  # finding 5
    api.managers.register(...)  # finding 1
```

`PluginAPI` is a small facade with a version number. It is the only thing a plugin may import besides `core`
(finding 12). Data goes in `extras` (finding 9). Calls into the plugin are guarded (finding 16). Texts are resolved
on read under the plugin's own context (finding 19).

Things to decide before building it, none of which this review settles:

- **Trust.** A Python plugin runs in the process with every right the app has. That is how mpv scripts and most
  desktop players work, but it should be said to the user when one is installed.
- **Packaged builds.** PyInstaller, Flatpak and Snap builds carry their own Python. A plugin can only use what is
  bundled, or pure-Python code it brings itself.
- **The player handle.** With the multi-process VLC drivers there is no player in the GUI process. The API has to
  stop at the frame interface (finding 6).
- **Stability.** The moment one outside plugin exists, renaming a command or an action id breaks somebody. Stable
  ids (findings 2 and 3) have to come before the first release of the API, not after.

## A possible order

Each step leaves the app working and is worth having even if the next never happens.

1. **Guard rails.** import-linter with today's violations recorded (12). No behaviour change.
2. **Quick registries.** `[ALL]` as a loop (4); resolver and list-format registries (10); `seek_marks()` on parts
   (18). Small, each removes a rule from AGENTS.md.
3. **Managers describe themselves.** Connections and filters move onto the managers; `start`/`stop` (1, 15, 16).
4. **Actions and commands.** Split `actions.py` by domain, stable ids with legacy aliases, namespaced commands,
   typed services between managers (2, 3). Titles resolved on read (19) fits here, since the same records change.
5. **Settings store.** Injected, notifying, with `applies` on fields; then drop the `*_loaded` / `set_*` signal
   families and the context copies (7, 8).
6. **Block parts.** Lifecycle hooks, public block face, part registry, `Interaction` service (5, 13).
7. **Models.** Video factory, `extras`, migrations by version (9).
8. **Plugin loader and `PluginAPI` v0**, with one or two of the app's own small features moved onto it as the test
   (SponsorBlock is a good candidate: a resolver-like lookup, a block part, settings, seek marks and actions).
9. **Later, as needed:** driver package and registry (6), grid mode controllers (11), platform backends (14), task
   service (17), large files (20).

Steps 1 to 3 are a few days each and carry little risk. Steps 4 to 6 are where most of the benefit is and most of
the diff. Step 9's items are the most expensive and the least needed for plugins; do them for their own sake when
the area is being worked on anyway.
