#!/usr/bin/env python3
"""Inject Keep a Changelog notes into an AppStream appdata <release> tag."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Any

import keepachangelog

_SECTION_ORDER = (
    "added",
    "changed",
    "deprecated",
    "removed",
    "fixed",
    "security",
)
_SECTION_TITLES = {
    "added": "Added",
    "changed": "Changed",
    "deprecated": "Deprecated",
    "removed": "Removed",
    "fixed": "Fixed",
    "security": "Security",
}

_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_COMMIT_REF = re.compile(r"\s*\(([0-9a-f]{7,40})\)")
_RELEASE_TAG = re.compile(r"(^[ \t]*)<release\b([^>]*)/>", re.MULTILINE)


def latest_version(changes: dict[str, Any]) -> str:
    for version in changes:
        if version.lower() != "unreleased":
            return version
    if "unreleased" in changes:
        return "unreleased"
    raise ValueError("Changelog has no versions")


def select_release(
    changes: dict[str, Any], version: str | None
) -> tuple[str, dict[str, Any]]:
    if version:
        key = version if version in changes else version.lower()
        if key in changes:
            return key, changes[key]
        raise ValueError(f"Version {version} not found in changelog")

    selected = latest_version(changes)
    return selected, changes[selected]


def strip_markdown(text: str) -> str:
    text = _MD_LINK.sub(r"\1", text)
    text = _COMMIT_REF.sub("", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    return text.strip(" ,")


def release_description_xml(release: dict[str, Any], indent: str = "      ") -> str:
    inner = indent + "  "
    item_indent = indent + "    "
    blocks: list[str] = [f"{indent}<description>"]

    for section in _SECTION_ORDER:
        items = [strip_markdown(item) for item in release.get(section, [])]
        items = [item for item in items if item]
        if not items:
            continue

        blocks.append(f"{inner}<p>{html.escape(_SECTION_TITLES[section])}</p>")
        blocks.append(f"{inner}<ul>")
        blocks.extend(f"{item_indent}<li>{html.escape(item)}</li>" for item in items)
        blocks.append(f"{inner}</ul>")

    if len(blocks) == 1:
        return ""

    blocks.append(f"{indent}</description>")
    return "\n".join(blocks)


def inject_description(appdata_xml: str, description_xml: str) -> str:
    if not description_xml:
        return appdata_xml

    match = _RELEASE_TAG.search(appdata_xml)
    if match is None:
        raise ValueError("No self-closing <release/> tag found in appdata")

    indent, attrs = match.group(1), match.group(2)
    replacement = f"{indent}<release{attrs}>\n{description_xml}\n{indent}</release>"
    return _RELEASE_TAG.sub(replacement, appdata_xml, count=1)


def render_changelog(
    changelog_path: Path, version: str | None = None
) -> tuple[str, str]:
    changes = keepachangelog.to_dict(str(changelog_path), show_unreleased=True)
    if not changes:
        raise ValueError(f"No versions found in {changelog_path}")

    selected, release = select_release(changes, version)
    return selected, release_description_xml(release)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Insert the latest Keep a Changelog release notes into appdata XML."
    )
    parser.add_argument("appdata", type=Path, help="AppStream appdata XML to update")
    parser.add_argument(
        "changelog",
        type=Path,
        nargs="?",
        default=Path("CHANGELOG.md"),
        help="Keep a Changelog markdown file (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--version",
        help="Changelog version to insert (default: latest released version)",
    )
    args = parser.parse_args(argv)

    selected, description = render_changelog(args.changelog, args.version)
    if not description:
        print(f"No changelog notes for {selected}; leaving appdata release empty")
        return 0

    appdata_xml = args.appdata.read_text(encoding="utf-8")
    args.appdata.write_text(
        inject_description(appdata_xml, description), encoding="utf-8"
    )
    print(f"Inserted changelog for {selected} into {args.appdata}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
