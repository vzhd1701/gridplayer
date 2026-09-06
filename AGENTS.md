# AGENTS.md

## Project

GridPlayer is a cross-platform PyQt5 desktop app for playing multiple videos side-by-side, backed by VLC. Python 3.10+, using `uv` and `just`.

## Hard boundaries

* **Do not create commits or push changes unless explicitly requested by the user.**
* **Generated resources_bin is off-limits.** Do not read, modify, or regenerate `gridplayer/resources_bin.py`. Do not run `just generate-resources`.
* **Translations are managed externally.** Do not modify `.ts`/`.qm` files, `scripts/translations/*`, or run any `just translations-*` recipe.
* **Vendored VLC code:** `gridplayer/vlc_player/vlc.py` is vendored. Do not modify it.

## Setup & common commands

```bash
uv sync
uv run gridplayer
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## UI files

Files matching `*_ui.py` are generated from Qt Designer `.ui` sources. Never edit them directly. Edit the `.ui` source in `resources/ui` instead, then run:

```bash
just generate-ui
```

## Code style

* Follow the Ruff configuration in `pyproject.toml`.
* Tests live in `tests/`.
