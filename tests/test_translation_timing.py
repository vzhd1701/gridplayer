"""Nothing may be translated before the app has a translator to do it.

gridplayer/__main__.py imports a good part of the app before main() gets to
init_translator(). A module among those that calls translate() while it is
being imported gets the English text back and keeps it for good, which is
how every menu entry once came out in English whatever the language: the
settings pulled in the shortcuts code, and that pulled in the actions table.
"""

import ast
import subprocess
import sys
from pathlib import Path

TRANSLATE_NAMES = {"translate", "_translate", "tr"}


def _modules_loaded_before_translator() -> list[Path]:
    probe = (
        "import sys\n"
        "import gridplayer.__main__\n"
        "for name, module in sorted(sys.modules.items()):\n"
        "    path = getattr(module, '__file__', None)\n"
        "    if name.startswith('gridplayer') and path:\n"
        "        print(path)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    return [Path(line) for line in out.splitlines() if line.endswith(".py")]


def _import_time_translations(path: Path) -> list[int]:
    """Lines where translate() runs as the module is imported."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []

    def visit(node, in_function):
        for child in ast.iter_child_nodes(node):
            deferred = in_function or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            )
            if not deferred and isinstance(child, ast.Call):
                func = child.func
                name = getattr(func, "id", getattr(func, "attr", None))
                if name in TRANSLATE_NAMES:
                    lines.append(child.lineno)
            visit(child, deferred)

    visit(tree, False)
    return lines


def test_nothing_loaded_before_the_translator_translates_on_import():
    offenders = {
        path.name: lines
        for path in _modules_loaded_before_translator()
        if (lines := _import_time_translations(path))
    }

    assert offenders == {}


def test_the_actions_table_is_not_among_them():
    """The one module that did it, named so a failure says what broke."""

    loaded = {p.as_posix() for p in _modules_loaded_before_translator()}

    assert not any(p.endswith("gridplayer/params/actions.py") for p in loaded)
