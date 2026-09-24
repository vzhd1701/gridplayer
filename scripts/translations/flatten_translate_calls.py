"""Put every multi-line translate() or tr() call on one line, for pylupdate5.

pylupdate5 only picks up a call whose context and text start on the line it
opens on, and it loses string literals that are joined across lines. This
rewrites such calls in place, in a scratch copy of the code: the lines a call
used to span are kept as newlines before its closing parenthesis, so every
line number pylupdate5 records still matches the real source.

usage: flatten_translate_calls.py <source dir>
"""

import ast
import sys
from pathlib import Path

# _translate is what pyuic5 names QCoreApplication.translate in *_ui.py
FUNC_NAMES = {"translate", "_translate", "tr"}


def _func_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_flattenable(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and _func_name(node.func) in FUNC_NAMES
        and node.end_lineno != node.lineno
        and bool(node.args)
        and not node.keywords
        and all(
            isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args
        )
    )


def _literal(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _char_offset(lines: list[str], lineno: int, col_offset: int) -> int:
    # ast counts columns in UTF-8 bytes
    line = lines[lineno - 1]
    col = len(line.encode("utf-8")[:col_offset].decode("utf-8"))
    return sum(len(x) for x in lines[: lineno - 1]) + col


def flatten(source: str) -> str:
    lines = source.splitlines(keepends=True)
    edits = []

    for node in ast.walk(ast.parse(source)):
        if not _is_flattenable(node):
            continue

        start = _char_offset(lines, node.lineno, node.col_offset)
        end = _char_offset(lines, node.end_lineno, node.end_col_offset)

        func = ast.get_source_segment(source, node.func)
        args = ", ".join(_literal(a.value) for a in node.args)
        newlines = "\n" * (node.end_lineno - node.lineno)

        edits.append((start, end, f"{func}({args}{newlines})"))

    # the arguments are all plain strings, so no call sits inside another
    for start, end, text in sorted(edits, reverse=True):
        source = source[:start] + text + source[end:]

    return source


def main(source_dir: Path) -> None:
    for path in source_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        flattened = flatten(source)
        if flattened != source:
            path.write_text(flattened, encoding="utf-8", newline="")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
