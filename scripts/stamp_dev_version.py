#!/usr/bin/env python3
"""Stamp a dev snapshot version into gridplayer/version.py and print it.

X.Y.Z becomes X.Y.Z.dev.<short sha> and the version date becomes the
commit date, so every job building the same commit stamps the same thing.
Stamping an already stamped file starts over from X.Y.Z.
"""

import re
import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "gridplayer" / "version.py"

VERSION_RE = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)[^"]*"$', re.MULTILINE)
VERSION_DATE_RE = re.compile(r'^__version_date__ = "[^"]*"$', re.MULTILINE)


def git(*args):
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def main():
    text = VERSION_FILE.read_text(encoding="utf-8")

    version_m = VERSION_RE.search(text)
    if not version_m or not VERSION_DATE_RE.search(text):
        sys.exit(f"Cannot parse version in {VERSION_FILE}")

    version = f"{version_m.group(1)}.dev.{git('rev-parse', '--short=7', 'HEAD')}"
    version_date = git("log", "-1", "--format=%cs")

    text = VERSION_RE.sub(f'__version__ = "{version}"', text)
    text = VERSION_DATE_RE.sub(f'__version_date__ = "{version_date}"', text)

    VERSION_FILE.write_text(text, encoding="utf-8", newline="\n")

    print(version)


if __name__ == "__main__":
    main()
