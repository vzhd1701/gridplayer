default:
    just --list

# From the oldest Python taken up, not the one that runs this: the builds,
# the Flatpak's runtime and the Snap's each have their own
build-requirements:
    if [ ! -f build/requirements.txt ]; then mkdir -p build && uv pip compile pyproject.toml -q --universal --python-version 3.11 --no-annotate --no-header -o build/requirements.txt; fi

build:
    uv build

stamp-dev-version:
    python scripts/stamp_dev_version.py

build-wheel:
    if [ ! -f dist/*.whl ]; then uv build --wheel; fi

build-sdist:
    if [ ! -f dist/*.tar.gz ]; then uv build --sdist; fi

build-linux-meta:
    ./scripts/linux_meta/build.sh

build-linux-appimage: build-wheel build-linux-meta
    ./scripts/appimage/build.sh

build-linux-snap: build-wheel build-linux-meta
    ./scripts/snap/build.sh

build-linux-snap-no-build: build-wheel build-linux-meta
    ./scripts/snap/build.sh --no-build

build-linux-flatpak: build-requirements build-sdist build-linux-meta
    ./scripts/flatpak/build.sh

build-linux-flatpak-git: build-requirements build-sdist build-linux-meta
    ./scripts/flatpak/build_git.sh

build-win-pyinstaller: build-requirements
    ./scripts/pyinstaller/build_win.sh

build-win-package: build-win-pyinstaller
    ./scripts/windows/build_packages.sh

# on Windows on Arm, with an arm64 Python
build-win-pyinstaller-arm64: build-requirements
    BUILD_WIN_ARCH=arm64 ./scripts/pyinstaller/build_win.sh

build-win-package-arm64: build-win-pyinstaller-arm64
    BUILD_WIN_ARCH=arm64 ./scripts/windows/build_packages.sh

build-win-chocolatey:
    ./scripts/chocolatey/build.sh all

build-macos-pyinstaller: build-requirements
    BUILD_MACOS_ARCH=x86_64 ./scripts/pyinstaller/build_mac.sh

build-macos-package: build-macos-pyinstaller
    BUILD_MACOS_ARCH=x86_64 ./scripts/macos/build_dmg.sh

build-macos-pyinstaller-arm64: build-requirements
    BUILD_MACOS_ARCH=arm64 ./scripts/pyinstaller/build_mac.sh

build-macos-package-arm64: build-macos-pyinstaller-arm64
    BUILD_MACOS_ARCH=arm64 ./scripts/macos/build_dmg.sh

clean:
    rm -rf dist build

clean-pyinstaller-dist:
    find dist -maxdepth 1 -mindepth 1 -type d -exec rm -r {} \;

generate-resources:
    ./scripts/qt_resources/build_resources.sh

test-real-app:
    uv run pytest -m real_app

# the clips the screenshots show, into build/screenshot-media
screenshots-clips:
    ./scripts/screenshots/get_clips.sh

# into resources/public, in a GNOME session on Ubuntu: see scripts/screenshots/make.sh
screenshots:
    ./scripts/screenshots/make.sh

# Translations: only when updating them is the job, see docs/TRANSLATIONS.md.
# What ships: approved on Crowdin, else AI (marked for review), else English.

# en_US.ts from the code
translations-extract:
    ./scripts/translations/build_ts.sh

# en_US.ts to Crowdin
translations-upload:
    ./scripts/translations/upload.sh

# approved translations and suggestions from Crowdin
translations-pull *ARGS:
    uv run --frozen python scripts/translations/tr.py pull {{ARGS}}

# the languages rebuilt against en_US.ts
translations-merge *ARGS:
    uv run --frozen python scripts/translations/tr.py merge {{ARGS}}

# AI for what is missing: --provider claude|codex|openrouter, --lang, --limit
translations-ai *ARGS:
    uv run --frozen python scripts/translations/tr.py ai {{ARGS}}

# AI review of the AI strings, whole file in view: --lang, --report-only
translations-ai-review *ARGS:
    uv run --frozen python scripts/translations/tr.py review {{ARGS}}

# QA, report in build/translations/report.md
translations-check *ARGS:
    uv run --frozen python scripts/translations/tr.py check {{ARGS}}

# AI translations to Crowdin, for people to check
translations-push *ARGS:
    uv run --frozen python scripts/translations/tr.py push {{ARGS}}

# the shares in the language list
translations-stats:
    uv run --frozen python scripts/translations/tr.py stats

# context screenshots: --upload sends them to Crowdin
translations-screenshots *ARGS:
    uv run --frozen python scripts/translations/tr.py screenshots {{ARGS}}

translations-update-contributors:
    ./scripts/translations/update_contributors.sh

# all of it, in order; AI options as for translations-ai
translations-all *ARGS:
    just translations-extract
    just translations-upload
    just translations-pull
    just translations-merge
    just translations-ai {{ARGS}}
    just translations-check
    just translations-push
    just translations-screenshots --upload
    just translations-stats
    just translations-update-contributors
    just generate-resources

changelog:
    conventional-changelog -p conventionalcommits -u -i /dev/null --stdout

changelog-since-last:
    conventional-changelog -p conventionalcommits -u -i /dev/null --stdout --from $(git log -1 --format='%H' --grep='^docs(changelog)')

changelog-all:
    conventional-changelog -u -i /dev/null --stdout

release:
    commit-and-tag-version

release-dry:
    commit-and-tag-version --dry-run

update-actions:
    actions-up --style preserve -y
