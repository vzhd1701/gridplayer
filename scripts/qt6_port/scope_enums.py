"""Write every Qt enum member with its enum's name: `Qt.AlignLeft` becomes
`Qt.AlignmentFlag.AlignLeft`, as PyQt6 requires and PyQt5 5.15 accepts.

    uv run python scripts/qt6_port/scope_enums.py [--dry-run] [--map FILE] [PATH ...]

Runs on PyQt5 (stage 1 of docs/plans/QT6_PLAN.md): there `type(Qt.AlignLeft)` is
`Qt.AlignmentFlag`, so the enum is read off the binding itself. Only `QClass.Member`
on a name imported from PyQt5, or through its module (`QtWidgets.QSizePolicy.Fixed`),
is changed; one reached through an instance (`selection.Rows`, `event.PaletteChange`)
is done by hand.
Run `ruff format` on the files after.
"""

import argparse
import ast
import importlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PyQt5.QtCore import Qt

# sip's enum metaclass, which PyQt5.sip doesn't name
ENUM_TYPE = type(type(Qt.AlignLeft))

ROOT = Path(__file__).resolve().parents[2]
VENDORED = {"gridplayer/vlc_player/vlc.py", "gridplayer/mpv_player/mpv.py"}

# enums whose PyQt6 name differs from PyQt5's: left for the switch (stage 2)
LEFT_FOR_STAGE_2 = {("QLibraryInfo", "TranslationsPath")}


def enum_name(cls, member: str) -> str | None:
    """The name of the enum `cls.member` belongs to, as reached from cls, or
    None when it isn't an enum member."""

    try:
        value = getattr(cls, member)
    except AttributeError:
        return None

    kind = type(value)
    if not isinstance(kind, ENUM_TYPE):
        return None

    name = kind.__name__
    # reachable from the class it was written on (QLabel.Shape from QFrame)
    if getattr(cls, name, None) is not kind:
        return None
    return name


def qt_imports(tree) -> dict[str, object]:
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "PyQt5."
        ):
            module = importlib.import_module(node.module)
            for alias in node.names:
                obj = getattr(module, alias.name, None)
                if isinstance(obj, type):
                    names[alias.asname or alias.name] = obj
    return names


def rewrite(path: Path, uses: Counter) -> str | None:
    source = path.read_text(encoding="utf-8")
    if "PyQt5" not in source:
        return None

    tree = ast.parse(source)
    names = qt_imports(tree)
    lines = source.splitlines(keepends=True)
    inserts = defaultdict(list)  # line index -> [(col, text)]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue

        base = node.value
        if isinstance(base, ast.Name) and base.id in names:
            cls = names[base.id]
            enum = enum_name(cls, node.attr)
            if enum is None or (cls.__name__, node.attr) in LEFT_FOR_STAGE_2:
                continue
            inserts[base.end_lineno - 1].append((base.end_col_offset, f".{enum}"))
            uses[
                f"{cls.__name__}.{node.attr} -> {cls.__name__}.{enum}.{node.attr}"
            ] += 1
        elif (
            node.attr[:1].isupper()
            and not isinstance(base, ast.Name)
            and isinstance(base, ast.Attribute)
            and base.attr.startswith("Q")
        ):
            # QtWidgets.QSizePolicy.Fixed and the like
            owner = ast.unparse(base)
            module = owner.split(".")[0]
            if module.startswith("Qt"):
                cls = getattr(
                    importlib.import_module(f"PyQt5.{module}"), base.attr, None
                )
                enum = cls is not None and enum_name(cls, node.attr)
                if enum:
                    inserts[base.end_lineno - 1].append(
                        (base.end_col_offset, f".{enum}")
                    )
                    uses[
                        f"{cls.__name__}.{node.attr} -> {cls.__name__}.{enum}.{node.attr}"
                    ] += 1

    if not inserts:
        return None

    for index, items in inserts.items():
        line = lines[index]
        # byte offsets in ast are of UTF-8; lines here are str
        encoded = line.encode("utf-8")
        for col, text in sorted(items, reverse=True):
            encoded = encoded[:col] + text.encode("utf-8") + encoded[col:]
        lines[index] = encoded.decode("utf-8")

    return "".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--map", help="write the member -> full name table as JSON")
    args = parser.parse_args()

    if args.paths:
        files = [Path(p).resolve() for p in args.paths]
    else:
        listed = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        files = [ROOT / f for f in listed if f not in VENDORED]

    uses, changed = Counter(), []
    for path in files:
        new = rewrite(path, uses)
        if new is None:
            continue
        changed.append(path)
        if not args.dry_run:
            path.write_text(new, encoding="utf-8", newline="")

    print(f"{sum(uses.values())} uses of {len(uses)} members in {len(changed)} files")
    if args.map:
        Path(args.map).write_text(
            json.dumps(dict(sorted(uses.items())), indent=1), encoding="utf-8"
        )


if __name__ == "__main__":
    sys.exit(main())
