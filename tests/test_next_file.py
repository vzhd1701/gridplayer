"""The files a cell steps through: which are found, in what order, and the
order random ones come in."""

import ctypes
import random
import subprocess
import sys
from pathlib import Path

import pytest

from gridplayer.utils.next_file import (
    FolderScan,
    ScanRules,
    ShuffleBag,
    natural_key,
    order_key,
    scan_folder,
)


def _touch(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        files.append(path)

    return files


def _names(scan: FolderScan) -> list[str]:
    return [path.relative_to(scan.root).as_posix() for path in scan.files]


def _scan(files: list[Path], root: Path) -> FolderScan:
    return FolderScan(
        root=root,
        files=tuple(files),
        keys=tuple(order_key(path, root) for path in files),
    )


class TestOrder:
    def test_numbers_are_counted_not_spelt(self, tmp_path):
        _touch(tmp_path, "ep10.mp4", "ep2.mp4", "ep1.mp4")

        scan = scan_folder(tmp_path, is_recursive=False)

        assert _names(scan) == ["ep1.mp4", "ep2.mp4", "ep10.mp4"]

    def test_case_is_not_minded(self, tmp_path):
        _touch(tmp_path, "b.mp4", "A.mp4", "c.mp4")

        scan = scan_folder(tmp_path, is_recursive=False)

        assert _names(scan) == ["A.mp4", "b.mp4", "c.mp4"]

    def test_a_folders_files_come_before_its_subfolders(self, tmp_path):
        _touch(
            tmp_path,
            "z.mp4",
            "a/2.mp4",
            "a/1.mp4",
            "a/sub/x.mp4",
            "b/y.mp4",
            "a.mp4",
        )

        scan = scan_folder(tmp_path, is_recursive=True)

        assert _names(scan) == [
            "a.mp4",
            "z.mp4",
            "a/1.mp4",
            "a/2.mp4",
            "a/sub/x.mp4",
            "b/y.mp4",
        ]

    def test_subfolders_are_counted_too(self, tmp_path):
        _touch(tmp_path, "Season 10/a.mp4", "Season 2/a.mp4")

        scan = scan_folder(tmp_path, is_recursive=True)

        assert _names(scan) == ["Season 2/a.mp4", "Season 10/a.mp4"]

    def test_the_keys_are_in_the_order_of_the_files(self, tmp_path):
        _touch(tmp_path, "b/1.mp4", "a.mp4", "B.mp4", "a/10.mp4", "a/9.mp4")

        scan = scan_folder(tmp_path, is_recursive=True)

        assert list(scan.keys) == sorted(scan.keys)

    def test_names_alike_but_for_the_case_are_never_equal(self):
        assert natural_key("a.mp4") != natural_key("A.mp4")
        assert natural_key("01.mp4") != natural_key("1.mp4")


class TestWhatIsFound:
    def test_only_media_files(self, tmp_path):
        _touch(tmp_path, "a.mp4", "b.MKV", "c.mp3", "notes.txt", "cover.jpg", "noext")

        scan = scan_folder(tmp_path, is_recursive=False)

        assert _names(scan) == ["a.mp4", "b.MKV", "c.mp3"]

    def test_without_subfolders_only_the_folders_own(self, tmp_path):
        _touch(tmp_path, "a.mp4", "sub/b.mp4")

        scan = scan_folder(tmp_path, is_recursive=False)

        assert _names(scan) == ["a.mp4"]

    def test_a_folder_named_like_a_video_is_not_one(self, tmp_path):
        (tmp_path / "folder.mp4").mkdir()
        _touch(tmp_path, "a.mp4")

        assert _names(scan_folder(tmp_path, is_recursive=False)) == ["a.mp4"]

    def test_a_folder_that_is_gone_has_none(self, tmp_path):
        scan = scan_folder(tmp_path / "gone", is_recursive=True)

        assert scan.files == ()

    @pytest.mark.parametrize(
        "name",
        [
            "._a.mp4",
            "$RECYCLE.BIN/a.mp4",
            "System Volume Information/a.mp4",
            "@eaDir/a.mp4",
            "#recycle/a.mp4",
            ".Trash-1000/a.mp4",
        ],
    )
    def test_system_ones_are_passed_over_everywhere(self, tmp_path, name):
        _touch(tmp_path, "keep.mp4", name)

        assert _names(scan_folder(tmp_path, is_recursive=True)) == ["keep.mp4"]

    @pytest.mark.skipif(sys.platform == "win32", reason="a dot hides nothing there")
    @pytest.mark.parametrize("name", [".hidden/a.mp4", ".a.mp4"])
    def test_a_leading_dot_hides_one(self, tmp_path, name):
        _touch(tmp_path, "keep.mp4", name)

        assert _names(scan_folder(tmp_path, is_recursive=True)) == ["keep.mp4"]

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows hides by attribute")
    def test_on_windows_a_leading_dot_hides_nothing(self, tmp_path):
        _touch(tmp_path, "keep.mp4", ".intro.mp4", ".extras/a.mp4")

        assert _names(scan_folder(tmp_path, is_recursive=True)) == [
            ".intro.mp4",
            "keep.mp4",
            ".extras/a.mp4",
        ]

    def test_hidden_ones_can_be_kept(self, tmp_path):
        _touch(tmp_path, "keep.mp4", "._b.mp4", "$RECYCLE.BIN/a.mp4")

        scan = scan_folder(
            tmp_path, is_recursive=True, rules=ScanRules(is_skip_hidden=False)
        )

        assert _names(scan) == ["._b.mp4", "keep.mp4", "$RECYCLE.BIN/a.mp4"]

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows attributes")
    def test_one_windows_hides_is_passed_over(self, tmp_path):
        _touch(tmp_path, "keep.mp4", "hidden/a.mp4")

        file_attribute_hidden = 0x2
        ctypes.windll.kernel32.SetFileAttributesW(
            str(tmp_path / "hidden"), file_attribute_hidden
        )

        assert _names(scan_folder(tmp_path, is_recursive=True)) == ["keep.mp4"]

    def test_the_limit_stops_the_looking(self, tmp_path):
        _touch(tmp_path, "1.mp4", "2.mp4", "sub/3.mp4", "sub/4.mp4")

        # the three in the folder, and none in the subfolder
        scan = scan_folder(tmp_path, is_recursive=True, rules=ScanRules(max_entries=3))

        assert _names(scan) == ["1.mp4", "2.mp4"]
        assert scan.is_truncated

    def test_files_that_are_not_videos_count_too(self, tmp_path):
        _touch(tmp_path, "sub/a.mp4", *(f"note{i}.txt" for i in range(5)))

        scan = scan_folder(tmp_path, is_recursive=True, rules=ScanRules(max_entries=6))

        assert _names(scan) == []
        assert scan.is_truncated

    def test_within_the_limit_nothing_is_cut(self, tmp_path):
        _touch(tmp_path, "1.mp4", "sub/2.mp4")

        # 1.mp4, the subfolder and 2.mp4: just enough
        scan = scan_folder(tmp_path, is_recursive=True, rules=ScanRules(max_entries=3))

        assert _names(scan) == ["1.mp4", "sub/2.mp4"]
        assert not scan.is_truncated


class TestLinks:
    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
    def test_a_link_to_a_folder_above_is_not_followed(self, tmp_path):
        _touch(tmp_path, "a.mp4", "sub/b.mp4")
        (tmp_path / "sub" / "loop").symlink_to(tmp_path, target_is_directory=True)

        assert _names(scan_folder(tmp_path, is_recursive=True)) == [
            "a.mp4",
            "sub/b.mp4",
        ]

    @pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows'")
    def test_a_junction_to_a_folder_above_is_not_followed(self, tmp_path):
        _touch(tmp_path, "a.mp4", "sub/b.mp4")
        subprocess.run(
            [
                "cmd",
                "/c",
                "mklink",
                "/J",
                str(tmp_path / "sub" / "loop"),
                str(tmp_path),
            ],
            check=True,
            capture_output=True,
        )

        assert _names(scan_folder(tmp_path, is_recursive=True)) == [
            "a.mp4",
            "sub/b.mp4",
        ]


class TestNeighbour:
    @pytest.fixture
    def scan(self, tmp_path):
        _touch(tmp_path, "a.mp4", "c.mp4", "sub/e.mp4")

        return scan_folder(tmp_path, is_recursive=True)

    def test_next_goes_into_the_subfolders(self, scan, tmp_path):
        assert scan.neighbour(tmp_path / "c.mp4", 1) == tmp_path / "sub" / "e.mp4"

    def test_next_from_the_last_goes_round_to_the_first(self, scan, tmp_path):
        assert scan.neighbour(tmp_path / "sub" / "e.mp4", 1) == tmp_path / "a.mp4"

    def test_previous_from_the_first_goes_round_to_the_last(self, scan, tmp_path):
        assert scan.neighbour(tmp_path / "a.mp4", -1) == tmp_path / "sub" / "e.mp4"

    def test_one_gone_is_counted_from_where_it_was(self, scan, tmp_path):
        gone = tmp_path / "b.mp4"

        assert scan.neighbour(gone, 1) == tmp_path / "c.mp4"
        assert scan.neighbour(gone, -1) == tmp_path / "a.mp4"

    def test_one_gone_past_the_end_goes_round(self, scan, tmp_path):
        gone = tmp_path / "sub" / "z.mp4"

        assert scan.neighbour(gone, 1) == tmp_path / "a.mp4"
        assert scan.neighbour(gone, -1) == tmp_path / "sub" / "e.mp4"

    def test_the_only_one_is_its_own_neighbour(self, tmp_path):
        (only,) = _touch(tmp_path, "a.mp4")

        scan = scan_folder(tmp_path, is_recursive=False)

        assert scan.neighbour(only, 1) == only

    def test_none_there_have_none(self, tmp_path):
        scan = scan_folder(tmp_path, is_recursive=False)

        assert scan.neighbour(tmp_path / "a.mp4", 1) is None


def _bag(seed=0):
    return ShuffleBag(rng=random.Random(seed))


def _files(count):
    return [Path(f"/videos/{i:02}.mp4") for i in range(count)]


def _exists(_path):
    return True


SCOPE = (Path("/videos"), True)


class TestShuffleBag:
    def test_every_file_once_before_any_again(self):
        files = _files(10)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        played = [bag.next(exists=_exists) for _ in range(9)]

        assert sorted(played) == files[1:]

    def test_the_order_starts_over_once_every_one_was_played(self):
        files = _files(5)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        for _ in range(4):
            bag.next(exists=_exists)

        second_round = [bag.next(exists=_exists) for _ in range(5)]

        assert sorted(second_round) == files

    @pytest.mark.parametrize("seed", range(20))
    def test_the_one_just_played_does_not_start_the_next_order(self, seed):
        files = _files(3)
        bag = _bag(seed)
        bag.sync(SCOPE, files, files[0])

        last = None
        for _ in range(30):
            pick = bag.next(exists=_exists)
            assert pick != last
            last = pick

    def test_previous_goes_back_and_next_forward_again(self):
        files = _files(6)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        first = bag.next(exists=_exists)
        second = bag.next(exists=_exists)

        assert bag.previous(exists=_exists) == first
        assert bag.previous(exists=_exists) == files[0]
        assert bag.previous(exists=_exists) is None

        assert bag.next(exists=_exists) == first
        assert bag.next(exists=_exists) == second

    def test_one_open_elsewhere_is_put_off(self):
        files = _files(4)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        avoid = {files[1], files[2]}

        assert bag.next(avoid=avoid, exists=_exists) == files[3]

    @pytest.mark.parametrize("seed", range(10))
    def test_one_open_elsewhere_waits_while_there_are_others(self, seed):
        files = _files(3)
        bag = _bag(seed)
        bag.sync(SCOPE, files, files[0])

        played = [bag.next(avoid={files[1]}, exists=_exists) for _ in range(10)]

        assert files[1] not in played

    def test_one_put_off_comes_once_it_is_closed_elsewhere(self):
        files = _files(3)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        for _ in range(4):
            bag.next(avoid={files[1]}, exists=_exists)

        assert bag.next(exists=_exists) == files[1]

    def test_with_every_one_open_elsewhere_one_still_plays(self):
        files = _files(3)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        assert bag.next(avoid=set(files), exists=_exists) in files[1:]

    def test_one_gone_is_left_out(self):
        files = _files(4)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        gone = {files[1], files[2]}

        assert bag.next(exists=lambda path: path not in gone) == files[3]

    def test_with_every_other_one_gone_the_one_playing_comes_again(self):
        files = _files(3)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        assert bag.next(exists=lambda path: path == files[0]) == files[0]

    def test_with_every_one_gone_there_is_none(self):
        files = _files(3)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        assert bag.next(exists=lambda _path: False) is None

    def test_one_added_comes_in_this_order(self):
        files = _files(3)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        added = Path("/videos/new.mp4")
        bag.sync(SCOPE, [*files, added], files[0])

        played = [bag.next(exists=_exists) for _ in range(3)]

        assert sorted(played) == sorted([files[1], files[2], added])

    def test_one_removed_does_not_come(self):
        files = _files(4)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        bag.sync(SCOPE, files[:3], files[0])

        played = [bag.next(exists=_exists) for _ in range(2)]

        assert sorted(played) == files[1:3]

    def test_one_that_came_some_other_way_counts_as_played(self):
        files = _files(4)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        bag.sync(SCOPE, files, files[2])

        played = [bag.next(exists=_exists) for _ in range(2)]

        assert sorted(played) == [files[1], files[3]]
        assert bag.previous(exists=_exists) == played[0]
        assert bag.previous(exists=_exists) == files[2]

    def test_another_folder_starts_a_new_order(self):
        files = _files(3)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])
        bag.next(exists=_exists)

        others = [Path(f"/other/{i}.mp4") for i in range(3)]
        bag.sync((Path("/other"), True), others, others[0])

        assert bag.previous(exists=_exists) is None
        assert sorted(bag.next(exists=_exists) for _ in range(2)) == others[1:]


class TestExistingNeighbour:
    def test_ones_gone_are_passed_over(self):
        files = _files(5)
        scan = _scan(files, Path("/videos"))
        gone = {files[1], files[2]}

        assert (
            scan.existing_neighbour(files[0], 1, exists=lambda f: f not in gone)
            == files[3]
        )

    def test_going_back_passes_over_them_too(self):
        files = _files(5)
        scan = _scan(files, Path("/videos"))
        gone = {files[3], files[2]}

        assert (
            scan.existing_neighbour(files[4], -1, exists=lambda f: f not in gone)
            == files[1]
        )

    def test_with_every_other_one_gone_it_is_the_one_playing(self):
        files = _files(3)
        scan = _scan(files, Path("/videos"))

        assert (
            scan.existing_neighbour(files[0], 1, exists=lambda f: f == files[0])
            == files[0]
        )

    def test_too_many_gone_in_a_row_finds_none(self, monkeypatch):
        monkeypatch.setattr("gridplayer.utils.next_file.MAX_MISSING_FILES", 2)
        files = _files(6)
        scan = _scan(files, Path("/videos"))

        assert (
            scan.existing_neighbour(files[0], 1, exists=lambda f: f == files[0]) is None
        )


class TestShuffleBagBackThroughGoneFiles:
    def test_one_gone_since_it_played_is_passed_over(self):
        files = _files(6)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        first = bag.next(exists=_exists)
        bag.next(exists=_exists)

        assert bag.previous(exists=lambda f: f != first) == files[0]

    def test_with_every_one_before_gone_there_is_none(self):
        files = _files(6)
        bag = _bag()
        bag.sync(SCOPE, files, files[0])

        bag.next(exists=_exists)
        current = bag.next(exists=_exists)

        assert bag.previous(exists=lambda f: f == current) is None

        # and the one playing is still the one to go back from
        assert bag.previous(exists=_exists) is None


@pytest.mark.skipif(sys.platform != "win32", reason="case counts elsewhere")
class TestNamesAlikeButForTheCase:
    @pytest.fixture
    def scan(self, tmp_path):
        _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")

        return scan_folder(tmp_path, is_recursive=False)

    def test_named_in_capitals_it_is_still_the_one_on_disk(self, scan, tmp_path):
        current = tmp_path / "B.mp4"

        assert scan.neighbour(current, 1) == tmp_path / "c.mp4"
        assert scan.neighbour(current, -1) == tmp_path / "a.mp4"

    def test_named_in_small_letters_it_is_still_the_one_on_disk(self, tmp_path):
        _touch(tmp_path, "A.mp4", "B.mp4", "C.mp4")
        scan = scan_folder(tmp_path, is_recursive=False)

        current = tmp_path / "b.mp4"

        assert scan.neighbour(current, 1) == tmp_path / "C.mp4"
        assert scan.neighbour(current, -1) == tmp_path / "A.mp4"


def test_without_subfolders_none_is_asked_whether_to_go_in(tmp_path, mocker):
    from gridplayer.utils import next_file

    _touch(tmp_path, "a.mp4", "sub/b.mp4")
    asked = mocker.spy(next_file, "_is_folder_to_enter")

    scan = scan_folder(tmp_path, is_recursive=False)

    assert _names(scan) == ["a.mp4"]
    asked.assert_not_called()
