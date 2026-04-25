#!/bin/bash

set -euo pipefail

# Run this once before building the native Apple Silicon macOS package locally.

check() {
    command -v "$1" >/dev/null 2>&1
}

if ! check brew; then
    printf '%s\n' "Homebrew is required to install macOS build dependencies." >&2
    exit 1
fi

brew install gnu-sed wget node graphicsmagick imagemagick just poetry

if ! check create-dmg; then
    npm install --global create-dmg
fi

python3 -m pip install --upgrade pip

printf '%s\n' "macOS build prerequisites installed."
printf '%s\n' "Use a native Apple Silicon shell and run: just build-macos-package-arm64"
