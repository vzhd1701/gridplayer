import argparse
import re
from pathlib import Path

import keepachangelog


def extract_version(version_file: Path):
    version_file_text = version_file.read_text()
    version_match = re.search(
        r"^__version__ = ['\"]([^'\"]+)['\"]", version_file_text, re.M
    )
    if version_match is None:
        raise ValueError("Could not find version in version.py")
    return version_match.group(1)


def ensure_unix_newlines(file: Path):
    file_bytes = file.read_bytes()
    file_bytes = file_bytes.replace(b"\r\n", b"\n")
    file.write_bytes(file_bytes)


def main():
    parser = argparse.ArgumentParser(
        description="Manipulate CHANGELOG.md according to keep-a-changelog standard"
    )

    parser.add_argument("version_file", help="Path to version.py", type=Path)
    parser.add_argument("changelog", help="Path to CHANGELOG.md file", type=Path)

    args = parser.parse_args()

    new_version = extract_version(args.version_file)
    keepachangelog.release(args.changelog, new_version)

    ensure_unix_newlines(args.changelog)


if __name__ == "__main__":
    main()
