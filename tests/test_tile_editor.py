import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.actions import ACTIONS
from gridplayer.params.static import TileOverlap, TileSnap
from gridplayer.player.managers.layout_edit import EDITOR_ACTIONS, SETTING_ACTIONS
from gridplayer.utils.layout.boxes import Box
from gridplayer.utils.layout.free_tiles import MOVE, FreeTiles, TileDrag
from gridplayer.widgets.settings_controls import SegmentedChoice, Switch, ToggleChips
from gridplayer.widgets.tile_editor import TileEditor, TileSettings

WIDTH, HEIGHT = 600, 400


class _Tiles:
    """The editor, and the tiles it changes, as Free Tiles would keep
    them: each change shown in it again, as TileEditManager does."""

    def __init__(self, boxes: dict[str, Box], overlap=TileOverlap.OFF, locked=()):
        self.tiles = FreeTiles(boxes, WIDTH / HEIGHT, locked)
        self.overlap = overlap
        self.changes = []

        self.editor = TileEditor(
            drag_of=self._drag_of,
            settings=TileSettings(
                overlap=lambda: self.overlap,
                set_overlap=lambda _: None,
                is_snapping=lambda: True,
                set_snapping=lambda _: None,
                snaps=frozenset,
                set_snaps=lambda _: None,
            ),
            swap_key=lambda: Qt.ShiftModifier,
            can_undo=lambda: False,
            can_redo=lambda: False,
            can_reopen=lambda: False,
        )
        self.editor.resize(WIDTH, HEIGHT)
        self.editor.tiles_changed.connect(self._changed)
        for name in (
            "change_started",
            "change_finished",
            "close_requested",
            "swap_requested",
        ):
            getattr(self.editor, name).connect(
                lambda *args, name=name: self.changes.append((name, *args))
            )
        self.show()

    def _drag_of(self, tiles, video_id, handle, width, height, at):
        return TileDrag(
            tiles,
            video_id,
            handle,
            width,
            height,
            at,
            snaps=frozenset(),
            is_over=self.overlap == TileOverlap.ON,
        )

    def _changed(self, rects, width, height):
        for video_id, rect in rects.items():
            self.tiles.set_rect(video_id, rect, width, height)
        self.show()

    def show(self):
        self.editor.set_tiles(
            self.tiles.copy(), {i: f"{i}.mp4" for i in self.tiles.tiles}
        )

    def rect(self, video_id):
        return tuple(round(v) for v in self.tiles.rects(WIDTH, HEIGHT)[video_id])


def _box(left, top, right, bottom) -> Box:
    return Box(left / WIDTH, top / HEIGHT, right / WIDTH, bottom / HEIGHT)


@pytest.fixture
def two():
    tiles = _Tiles({"a": _box(20, 20, 220, 120), "b": _box(300, 20, 500, 120)})
    yield tiles
    tiles.editor.deleteLater()


class TestWhatIsTaken:
    def test_the_middle_moves_an_edge_or_corner_sizes(self, two):
        at = two.editor._tile_at

        assert at(QPoint(120, 70)) == ("a", MOVE)
        assert at(QPoint(218, 70)) == ("a", (1, 0))
        assert at(QPoint(218, 118)) == ("a", (1, 1))
        # just outside the edge too, but not further
        assert at(QPoint(223, 70)) == ("a", (1, 0))
        assert at(QPoint(250, 70)) is None

    def test_a_locked_tile_is_only_picked(self):
        tiles = _Tiles(
            {"a": _box(20, 20, 220, 120), "b": _box(100, 60, 300, 200)},
            locked={"b"},
        )

        assert tiles.editor._tile_at(QPoint(298, 130)) == ("b", MOVE)
        # a's edge under b is not taken through it
        assert tiles.editor._tile_at(QPoint(218, 100)) == ("b", MOVE)

    def test_the_hidden_edge_of_a_tile_behind_is_taken(self):
        tiles = _Tiles({"a": _box(20, 20, 220, 120), "b": _box(100, 60, 300, 200)})

        assert tiles.editor._tile_at(QPoint(218, 100)) == ("a", (1, 0))
        assert tiles.editor._tile_at(QPoint(250, 150)) == ("b", MOVE)


class TestKeys:
    def test_arrows_move_the_picked_tile_as_one_change(self, two):
        two.editor.pick("a")

        for _ in range(3):
            QTest.keyClick(two.editor, Qt.Key_Right)
        QTest.keyClick(two.editor, Qt.Key_Down, Qt.ShiftModifier)

        assert two.rect("a") == (23, 30, 223, 130)
        assert two.changes == [("change_started",)]

        two.editor._end_nudge()
        assert two.changes == [("change_started",), ("change_finished",)]

    def test_ctrl_moves_the_right_or_bottom_edge(self, two):
        two.editor.pick("a")

        QTest.keyClick(two.editor, Qt.Key_Left, Qt.ControlModifier)
        QTest.keyClick(two.editor, Qt.Key_Down, Qt.ControlModifier)

        assert two.rect("a") == (20, 20, 219, 121)

    def test_a_tile_in_the_way_stops_it(self, two):
        two.editor.pick("a")

        for _ in range(10):
            QTest.keyClick(two.editor, Qt.Key_Right, Qt.ShiftModifier)

        assert two.rect("a") == (100, 20, 300, 120)

    def test_a_locked_tile_is_not_moved(self):
        tiles = _Tiles({"a": _box(20, 20, 220, 120)}, locked={"a"})
        tiles.editor.pick("a")

        QTest.keyClick(tiles.editor, Qt.Key_Right)

        assert tiles.rect("a") == (20, 20, 220, 120)
        assert tiles.changes == []

    def test_tab_picks_the_next_as_they_are_read(self, two):
        two.editor.pick("a")

        QTest.keyClick(two.editor, Qt.Key_Tab)
        assert two.editor.picked() == "b"
        QTest.keyClick(two.editor, Qt.Key_Tab)
        assert two.editor.picked() == "a"
        QTest.keyClick(two.editor, Qt.Key_Backtab)
        assert two.editor.picked() == "b"

    def test_delete_closes_the_picked_video(self, two):
        two.editor.pick("b")

        QTest.keyClick(two.editor, Qt.Key_Delete)

        assert two.changes == [("close_requested", "b")]

    def test_the_keys_are_the_players_with_nothing_picked(self, two):
        pressed = []
        two.editor.key_pressed.connect(pressed.append)

        QTest.keyClick(two.editor, Qt.Key_Right)

        assert len(pressed) == 1
        assert two.changes == []

    @pytest.mark.parametrize("how", ["key", "button"])
    def test_undo_right_after_the_arrows_ends_their_change_first(self, two, how):
        # the grid takes no undo while a change is going on
        two.editor.pick("a")
        QTest.keyClick(two.editor, Qt.Key_Right)
        two.editor.key_pressed.connect(
            lambda e: e.key() == Qt.Key_Z and two.changes.append(("key",))
        )
        two.editor.undo_requested.connect(lambda: two.changes.append(("undo",)))

        if how == "key":
            QTest.keyClick(two.editor, Qt.Key_Z, Qt.ControlModifier)
        else:
            two.editor._action_buttons["undo"].setEnabled(True)
            two.editor._action_buttons["undo"].click()

        assert two.changes == [
            ("change_started",),
            ("change_finished",),
            ("key",) if how == "key" else ("undo",),
        ]


def _drag(editor, start, end, modifiers=Qt.NoModifier):
    QTest.mousePress(editor, Qt.LeftButton, modifiers, start)
    for at in (start + QPoint(10, 0), end):
        QApplication.sendEvent(
            editor,
            QMouseEvent(
                QEvent.MouseMove, QPointF(at), Qt.NoButton, Qt.LeftButton, modifiers
            ),
        )
    QTest.mouseRelease(editor, Qt.LeftButton, modifiers, end)


class TestSwap:
    def test_a_tile_dragged_with_shift_onto_another_swaps(self, two):
        _drag(two.editor, QPoint(120, 70), QPoint(400, 70), Qt.ShiftModifier)

        assert two.changes == [("swap_requested", "a", "b")]
        # left where it was, for the swap
        assert two.rect("a") == (20, 20, 220, 120)

    def test_a_locked_tile_swaps_too(self):
        tiles = _Tiles(
            {"a": _box(20, 20, 220, 120), "b": _box(300, 20, 500, 120)},
            locked={"a"},
        )

        _drag(tiles.editor, QPoint(120, 70), QPoint(400, 70), Qt.ShiftModifier)

        assert tiles.changes == [("swap_requested", "a", "b")]

    def test_dropped_on_no_tile_nothing(self, two):
        _drag(two.editor, QPoint(120, 70), QPoint(120, 300), Qt.ShiftModifier)

        assert two.changes == []
        assert not two.editor.is_dragging()

    def test_without_the_key_it_moves(self, two):
        _drag(two.editor, QPoint(120, 70), QPoint(120, 300))

        assert two.changes == [("change_started",), ("change_finished",)]
        assert two.rect("a")[1] > 20


class TestName:
    def test_a_picked_tile_has_its_buttons_under_its_name(self, two):
        two.editor.pick("a")

        label = two.editor._label_of("a")

        assert label.close is not None
        assert set(label.tools) == {"lock", "front", "back"}
        assert all(t.top() > label.box.bottom() for t in label.tools.values())
        assert two.editor._label_of("b").tools == {}

    def test_a_long_name_is_cut_in_the_middle(self, two):
        two.editor._names["a"] = "a very long name of a video, much longer.mp4"

        name = two.editor._label_of("a").name

        assert name.startswith("a v")
        assert name.endswith(".mp4")
        assert "…" in name

    def test_a_name_goes_where_the_tile_shows(self):
        tiles = _Tiles({"a": _box(20, 20, 220, 120), "b": _box(20, 60, 220, 200)})

        box = tiles.editor._label_of("a").box

        assert box.bottom() <= 60

    @pytest.mark.parametrize("top", [30, 90, 150])
    def test_a_tile_that_only_touches_it_moves_no_name(self, top):
        # b in front, its left edge on a's right one
        alone = _Tiles({"a": _box(20, 20, 220, 220)})
        beside = _Tiles(
            {"a": _box(20, 20, 220, 220), "b": _box(220, top, 420, top + 60)}
        )

        assert beside.editor._label_of("a").box == alone.editor._label_of("a").box

    def test_a_name_goes_in_the_biggest_part_left(self):
        # b over a's right half, not as tall: the left half, all of its height
        tiles = _Tiles({"a": _box(20, 20, 220, 220), "b": _box(120, 60, 320, 180)})

        box = tiles.editor._label_of("a").box

        assert box.right() <= 120
        assert box.center().y() == pytest.approx(120, abs=1)


class TestPopups:
    @pytest.fixture
    def settings(self):
        """Tile Overlap, Snap Tiles and Snap To as the editor reads them."""

        return {"overlap": TileOverlap.OFF, "snapping": True, "snaps": frozenset()}

    @pytest.fixture
    def editor(self, settings):
        editor = TileEditor(
            drag_of=lambda *_: None,
            settings=TileSettings(
                overlap=lambda: settings["overlap"],
                set_overlap=lambda v: settings.update(overlap=v),
                is_snapping=lambda: settings["snapping"],
                set_snapping=lambda v: settings.update(snapping=v),
                snaps=lambda: settings["snaps"],
                set_snaps=lambda v: settings.update(snaps=v),
            ),
            swap_key=lambda: None,
            can_undo=lambda: False,
            can_redo=lambda: False,
            can_reopen=lambda: False,
        )
        editor.resize(WIDTH, HEIGHT)
        yield editor
        if editor._popup is not None:
            editor._popup.dismiss()
        editor.deleteLater()

    def test_snap_to_follows_its_settings_while_up(self, editor, settings):
        editor._snap.click()
        switch = editor._popup.findChild(Switch)
        chips = editor._popup.findChild(ToggleChips)
        assert switch.isChecked()

        # turned by their keys
        settings.update(snapping=False, snaps=frozenset({TileSnap.TILE_EDGES}))
        editor.update_settings()

        assert not switch.isChecked()
        assert not chips.isEnabled()
        assert chips.picked() == frozenset({TileSnap.TILE_EDGES})
        assert settings["snapping"] is False

    def test_tile_overlap_follows_its_setting_while_up(self, editor, settings):
        editor._overlap.click()
        choice = editor._popup.findChild(SegmentedChoice)

        settings["overlap"] = TileOverlap.ON
        editor.update_settings()

        assert choice.currentData() == TileOverlap.ON

    def test_a_popup_passes_the_players_keys_on(self, editor):
        pressed = []
        editor.key_pressed.connect(lambda e: pressed.append(e.key()))
        editor._snap.click()

        QTest.keyClick(editor._popup, Qt.Key_S, Qt.ControlModifier)

        assert Qt.Key_S in pressed
        assert editor._popup is not None


def test_the_keys_taken_in_the_editors_are_the_players_actions():
    for name in (*EDITOR_ACTIONS.values(), *SETTING_ACTIONS):
        assert name in ACTIONS, name
