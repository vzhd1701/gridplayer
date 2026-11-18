"""Switch imports from PyQt5 to PyQt6, moving each class to the module that has
it in PyQt6 (QAction to QtGui, QOpenGLWidget to QtOpenGLWidgets, ...).

    uv run python scripts/qt6_port/switch_imports.py [--dry-run] [PATH ...]

Runs on PyQt6 (stage 2 of docs/plans/QT6_PLAN.md): every name imported from a Qt
module is looked up there, and when it isn't, in the other modules. What PyQt6 has
nowhere is listed for doing by hand, as is a moved class reached through its module
(`QtWidgets.QAction`). Run `ruff check --fix` (imports) and `ruff format` after.
"""

import argparse
import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDORED = {"gridplayer/vlc_player/vlc.py", "gridplayer/mpv_player/mpv.py"}
SELF = {
    "scripts/qt6_port/scope_enums.py",
    "scripts/qt6_port/switch_imports.py",
    "scripts/qt6_port/look.py",  # takes either binding
}

MODULES = [
    "QtCore",
    "QtGui",
    "QtWidgets",
    "QtOpenGL",
    "QtOpenGLWidgets",
    "QtSvg",
    "QtSvgWidgets",
    "QtDBus",
    "QtNetwork",
    "QtTest",
]


def _load():
    loaded = {}
    for name in MODULES:
        try:
            loaded[name] = importlib.import_module(f"PyQt6.{name}")
        except ImportError:
            pass
    return loaded


LOADED = _load()


def home_of(name: str, module: str) -> str | None:
    """The PyQt6 module that has `name`, the one it was imported from first."""

    if module in LOADED and hasattr(LOADED[module], name):
        return module
    for other, mod in LOADED.items():
        if hasattr(mod, name):
            return other
    return None


def _import_line(indent: str, module: str, names: list[str]) -> str:
    return f"{indent}from PyQt6.{module} import {', '.join(names)}\n"


def switch(path: Path, problems: list[str]) -> str | None:
    source = path.read_text(encoding="utf-8")
    if "PyQt5" not in source:
        return None
    original = source

    # imports, and module paths in strings ("PyQt5.QtGui.QDesktopServices.openUrl");
    # comments that speak of PyQt5 wait for stage 8
    source = re.sub(r"\b(from|import)(\s+)PyQt5\b", r"\1\2PyQt6", source)
    source = re.sub(r"([\"'])PyQt5\.", r"\1PyQt6.", source)
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    rel = path.relative_to(ROOT).as_posix()

    replacements = []  # (first line index, last line index, new text)
    module_aliases = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "PyQt6":
            for alias in node.names:
                module_aliases[alias.asname or alias.name] = alias.name
            continue

        if not (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("PyQt6.")
        ):
            continue

        module = node.module.split(".", 1)[1]
        by_home: dict[str, list[str]] = {}
        moved = False
        for alias in node.names:
            spelled = alias.name + (f" as {alias.asname}" if alias.asname else "")
            home = home_of(alias.name, module)
            if home is None:
                problems.append(f"{rel}:{node.lineno}: {module}.{alias.name} is gone")
                home = module  # left where it was, to fail loudly
            moved |= home != module
            by_home.setdefault(home, []).append(spelled)

        if not moved:
            continue

        first = lines[node.lineno - 1]
        indent = first[: len(first) - len(first.lstrip())]
        text = "".join(
            _import_line(indent, home, names) for home, names in by_home.items()
        )
        replacements.append((node.lineno - 1, node.end_lineno - 1, text))

    # a moved class reached through its module: QtWidgets.QAction
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in module_aliases
            and node.attr[:1] == "Q"
        ):
            module = module_aliases[node.value.id]
            home = home_of(node.attr, module)
            if home != module:
                problems.append(
                    f"{rel}:{node.lineno}: {module}.{node.attr} is in {home} now"
                )

    for first, last, text in sorted(replacements, reverse=True):
        lines[first : last + 1] = [text]

    new = "".join(lines)
    return None if new == original else new


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
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
        files = [ROOT / f for f in listed if f not in VENDORED | SELF]

    problems, changed = [], 0
    for path in files:
        new = switch(path, problems)
        if new is None:
            continue
        changed += 1
        if not args.dry_run:
            path.write_text(new, encoding="utf-8", newline="")

    print(f"{changed} files")
    print("\n".join(problems))


if __name__ == "__main__":
    sys.exit(main())
