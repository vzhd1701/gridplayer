"""A widget with a style of its own outlives being deleteLater()'d.

A widget never owns the style it is given. One left to its Python wrapper
could be freed before the widget when the widget was deleteLater()'d with
no Python reference left, and with a stylesheet set, the widget then read
the freed style on the way out: an access violation that took the process
down. Run in a process of its own, so a crash fails the test rather than
the whole run.
"""

import os
import subprocess
import sys

import pytest

_PROBE = """
import faulthandler
faulthandler.enable()

from PyQt5.QtWidgets import QApplication

app = QApplication([])

from {module} import {widget}


def make():
    widget = {widget}()
    widget.setStyleSheet("* {{ color: black; }}")
    widget.deleteLater()


make()
app.processEvents()
print("survived")
"""


@pytest.mark.parametrize(
    ("module", "widget"),
    [
        ("gridplayer.widgets.keymap_tree_view", "KeymapTreeView"),
        ("gridplayer.widgets.keymap_tree_view", "KeymapEditor"),
        ("gridplayer.widgets.resolver_patterns_list", "ResolverPatternsList"),
    ],
)
def test_deleted_later_with_no_reference_left(module, widget):
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module, widget=widget)],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "survived" in result.stdout
