from typing import Dict

from PyQt5.QtCore import pyqtSignal

from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Snapshot
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import translate


class SnapshotsManager(ManagerBase):
    warning = pyqtSignal(str)
    grid_state_loaded = pyqtSignal(GridState)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._snapshots: Dict[int, Snapshot] = {}

        self._ctx.snapshots = self.snapshots

    def snapshots(self):
        return self._snapshots

    @property
    def commands(self):
        return {
            "save_snapshot": self.cmd_save_snapshot,
            "delete_snapshot": self.cmd_delete_snapshot,
            "load_snapshot": self.cmd_load_snapshot,
            "is_snapshot_exists": self.is_snapshot_exists,
        }

    def cmd_save_snapshot(self, _id):
        if not self._ctx.video_blocks.is_all_initialized:
            self.warning.emit(
                translate(
                    "Warning", "Cannot save snapshot unless all videos are initialized"
                )
            )
            return

        self._snapshots[_id] = Snapshot(
            grid_state=self._ctx.grid_state.copy(),
            videos=[v.video_params.copy() for v in self._ctx.video_blocks],
        )

    def cmd_delete_snapshot(self, _id):
        self._snapshots.pop(_id, None)

    def cmd_load_snapshot(self, _id):
        if _id not in self._snapshots:
            return

        if not self._ctx.video_blocks.is_all_initialized:
            self.warning.emit(
                translate(
                    "Warning", "Cannot load snapshot unless all videos are initialized"
                )
            )
            return

        snapshot = self._snapshots[_id]

        if len(snapshot.videos) != len(self._ctx.video_blocks):
            raise RuntimeError(
                "Snapshot has different number of videos than current playlist"
            )

        for vs in snapshot.videos:
            cur_video = self._ctx.video_blocks.by_video_id(vs.id)
            if cur_video is None:
                raise RuntimeError(f"Snapshot video with id {vs.id} not found")
            cur_video.apply_snapshot(vs)

        new_order = [v.id for v in snapshot.videos]
        self._ctx.video_blocks.reorder_by_video_ids(new_order)

        self.grid_state_loaded.emit(snapshot.grid_state)

    def is_snapshot_exists(self, _id):
        return _id in self._snapshots

    def set_snapshots(self, snapshots):  # noqa: WPS615
        self._snapshots = snapshots

    def clear_snapshots(self):
        self._snapshots.clear()
