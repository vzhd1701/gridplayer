from types import SimpleNamespace
from uuid import uuid4

import pytest

from gridplayer.models.grid_state import GridCell
from gridplayer.models.media_list import MediaList
from gridplayer.models.video import Video
from gridplayer.player.managers.closed_videos import KEPT_CLOSES, ClosedVideosManager
from gridplayer.utils.layout.grid_layout import GridLayout


class _Lists:
    def __init__(self, *lists):
        self.lists = {media_list.id: media_list for media_list in lists}

    def get(self, list_id):
        return self.lists.get(list_id)

    def add(self, media_list):
        self.lists[media_list.id] = media_list
        return media_list


def _block(name="a.mp4", **params):
    # named by its title, as a cell renamed is
    video = Video(uri=f"/videos/{name}", title=name, **params)
    return SimpleNamespace(video_params=video, video_id=str(video.id))


@pytest.fixture
def ctx():
    reopened = []
    ctx = SimpleNamespace(
        lists=_Lists(),
        reopened=reopened,
        room=None,
        warnings=[],
    )
    ctx.commands = SimpleNamespace(
        grid_place_of=lambda video_id: f"place of {video_id}",
        grid_free_capacity=lambda: ctx.room,
        put_back_videos=lambda videos, places: reopened.append((videos, places)),
    )
    return ctx


@pytest.fixture
def manager(ctx):
    manager = ClosedVideosManager(context=ctx)
    manager.warning.connect(ctx.warnings.append)
    return manager


def test_the_last_close_comes_back_first(ctx, manager):
    first, second = _block("a.mp4"), _block("b.mp4")
    manager.remember([first])
    manager.remember([second])

    manager.reopen()
    manager.reopen()

    assert [videos[0].uri for videos, _ in ctx.reopened] == [
        second.video_params.uri,
        first.video_params.uri,
    ]
    assert not manager.commands["is_any_video_closed"]()


def test_a_video_comes_back_as_it_was_where_it_was(ctx, manager):
    block = _block(current_position=61_000, is_muted=True)
    manager.remember([block])
    # what it does after, nothing of what comes back
    block.video_params.current_position = 0

    manager.reopen()

    ((video,), (place,)) = ctx.reopened[0]
    assert video.id == block.video_params.id
    assert video.current_position == 61_000
    assert video.is_muted
    assert place == f"place of {block.video_id}"


def test_closed_together_they_come_back_together(ctx, manager):
    blocks = [_block("a.mp4"), _block("b.mp4"), _block("c.mp4")]
    manager.remember(blocks)

    manager.reopen()

    videos, places = ctx.reopened[0]
    assert [v.id for v in videos] == [b.video_params.id for b in blocks]
    assert len(places) == 3


def test_only_the_last_closes_are_kept(ctx, manager):
    blocks = [_block(f"{i}.mp4") for i in range(KEPT_CLOSES + 3)]
    for block in blocks:
        manager.remember([block])

    while manager.commands["is_any_video_closed"]():
        manager.reopen()

    assert len(ctx.reopened) == KEPT_CLOSES
    assert ctx.reopened[-1][0][0].id == blocks[3].video_params.id


def test_with_no_room_it_stays_closed_and_says_so(ctx, manager):
    manager.remember([_block("a.mp4"), _block("b.mp4")])
    ctx.room = 1

    manager.reopen()

    assert not ctx.reopened
    assert ctx.warnings
    assert manager.commands["is_any_video_closed"]()


def test_a_cell_still_waiting_for_its_list_is_not_kept(ctx, manager):
    manager.remember([_block("folder", read_as_list=True)])

    assert not manager.commands["is_any_video_closed"]()


def test_the_playlist_closed_forgets_them(ctx, manager):
    changes = []
    manager.changed.connect(lambda: changes.append(1))
    manager.remember([_block()])

    manager.forget()

    assert not manager.commands["is_any_video_closed"]()
    assert len(changes) == 2


def test_its_list_let_go_of_meanwhile_is_kept_again(ctx, manager):
    media_list = MediaList()
    ctx.lists = _Lists(media_list)
    block = _block(list_id=media_list.id, list_index=0)
    manager.remember([block])
    # a save forgets the lists no cell plays from
    ctx.lists.lists.clear()

    manager.reopen()

    ((video,), _) = ctx.reopened[0]
    assert ctx.lists.get(video.list_id) is media_list


def _grid(*cells):
    layout = GridLayout(max_rows=2, max_cols=3)
    layout.cells = list(cells)
    return layout


def test_a_cell_goes_back_where_it_was_with_its_span():
    layout = _grid(GridCell(video_id="b", row=0, col=2))
    big = GridCell(video_id=str(uuid4()), row=0, col=0, rowspan=2, colspan=2)

    assert layout.put_back(big)

    assert layout.id_at(1, 1) == big.video_id


def test_a_cell_whose_place_is_taken_does_not_go_back():
    layout = _grid(GridCell(video_id="b", row=1, col=1))
    big = GridCell(video_id="a", row=0, col=0, rowspan=2, colspan=2)

    assert not layout.put_back(big)
    assert layout.id_at(0, 0) is None


def test_a_cell_out_of_a_grid_made_smaller_does_not_go_back():
    layout = _grid()

    assert not layout.put_back(GridCell(video_id="a", row=2, col=0))


def test_the_menu_lists_the_closes_the_last_first(manager):
    manager.remember([_block("a.mp4", current_position=102_000)])
    manager.remember([_block("b & c.mp4")])
    manager.remember([_block("d.mp4"), _block("e.mp4"), _block("f.mp4")])

    titles = [item["title"] for item in manager.menu_generator()]

    assert titles == ["d.mp4 and 2 more", "b && c.mp4", "a.mp4\t01:42"]


def test_one_from_the_menu_comes_back_and_the_others_stay(ctx, manager):
    first, second, third = _block("a.mp4"), _block("b.mp4"), _block("c.mp4")
    for block in (first, second, third):
        manager.remember([block])

    manager.reopen(1)

    assert ctx.reopened[0][0][0].id == second.video_params.id
    assert [item["title"] for item in manager.menu_generator()] == ["c.mp4", "a.mp4"]
    assert [item["func"] for item in manager.menu_generator()] == [
        ("reopen_closed_video", 0),
        ("reopen_closed_video", 1),
    ]
