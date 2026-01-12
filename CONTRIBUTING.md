# Contributing

## Setup

Dependencies:

- [Poetry](https://python-poetry.org/docs/)
- [Just](https://github.com/casey/just) (task runner)
- [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) (for release workflow)

## Dev install & run

```bash
git clone https://github.com/vzhd1701/gridplayer.git
cd gridplayer
poetry install --with dev
poetry run gridplayer
```

## Local build on Windows

Install dependencies:

```bash
choco install zip innosetup
```

Build:

```bash
just build-win-package
```

## Local build on MacOS

Install dependencies:

```bash
.\scripts\macos\_init_local_env.sh
```

Build:

```bash
just build-macos-package
```

## Release

1. State changes in `CHANGELOG.md` inside `## [Unreleased]` section. Use [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

As a guide, print changes from recent commits:

```bash
just changelog       # only important changes
just changelog-all   # full changelog
```

2. See what will be changed:

```bash
commit-and-tag-version --dry-run
```

3. Commit and create release tag:

```bash
commit-and-tag-version
```
