"""Folder trees looked through once for every cell, and how many are kept."""

from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.utils import folder_index as folder_index_module
from gridplayer.utils.folder_index import FolderIndex, ScanKey
from gridplayer.utils.next_file import ScanRules


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def index(mocker):
    """An index of its own, looking through folders there and then."""

    index = FolderIndex()
    mocker.patch.object(index, "_start_scan", index._scan)

    return index


def _key(root: Path) -> ScanKey:
    return ScanKey(root=root, is_recursive=True, rules=ScanRules())


def _tree(tmp_path: Path, count: int) -> list[ScanKey]:
    keys = []

    for i in range(count):
        root = tmp_path / f"tree{i}"
        root.mkdir()
        (root / "a.mp4").touch()
        keys.append(_key(root))

    return keys


def test_a_tree_is_answered_once_looked_through(index, tmp_path):
    (key,) = _tree(tmp_path, 1)

    scan = index.lookup(key)

    assert scan.files == (key.root / "a.mp4",)


def test_a_tree_still_being_looked_through_has_no_answer_yet(tmp_path, mocker):
    index = FolderIndex()
    start = mocker.patch.object(index, "_start_scan")
    (key,) = _tree(tmp_path, 1)

    assert index.lookup(key) is None
    assert index.lookup(key) is None

    # one look for any number of cells asking
    start.assert_called_once_with(key)


def test_only_the_trees_looked_up_last_are_kept(index, tmp_path, monkeypatch):
    monkeypatch.setattr(folder_index_module, "MAX_KEPT", 3)
    first, second, third, fourth = _tree(tmp_path, 4)

    for key in (first, second, third):
        index.lookup(key)

    # looked up again, the first is one of the last
    index.lookup(first)
    index.lookup(fourth)

    assert set(index._scans) == {first, third, fourth}


def test_a_tree_looked_through_lately_is_not_looked_through_again(tmp_path, mocker):
    index = FolderIndex()
    start = mocker.patch.object(index, "_start_scan", side_effect=index._scan)
    (key,) = _tree(tmp_path, 1)

    index.lookup(key)
    index.lookup(key)

    start.assert_called_once_with(key)


def test_a_look_that_is_stuck_lets_another_start(tmp_path, mocker, monkeypatch):
    index = FolderIndex()
    start = mocker.patch.object(index, "_start_scan")
    (key,) = _tree(tmp_path, 1)

    index.lookup(key)
    monkeypatch.setattr(folder_index_module, "STUCK_SEC", 0)
    index.lookup(key)

    assert start.call_count == 2
