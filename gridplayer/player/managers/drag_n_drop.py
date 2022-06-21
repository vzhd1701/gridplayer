from pathlib import Path

from PyQt5.QtCore import QEvent, QMimeData, Qt, pyqtSignal
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import filter_video_uris
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.files import (
    drag_get_uris,
    drag_get_video,
    drag_has_video,
    get_playlist_path,
)


class DragNDropManager(ManagerBase):
    playlist_dropped = pyqtSignal(Path)
    videos_dropped = pyqtSignal(list)

    videos_swapped = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag_start_position = None

    @property
    def event_map(self):
        return {
            QEvent.MouseMove: self.mouseMoveEvent,
            QEvent.MouseButtonPress: self.mousePressEvent,
            QEvent.DragEnter: self.dragEnterEvent,
            QEvent.Drop: self.dropEvent,
            QEvent.DragMove: self.dragMoveEvent,
        }

    def mouseMoveEvent(self, event):
        if self._is_drag_started(event):
            drag_video = self._get_drag_video()
            if drag_video is not None:
                drag_video.exec()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_position = event.pos()

    def dragEnterEvent(self, event):
        drag_data = event.mimeData()

        if not drag_get_uris(drag_data) and not drag_has_video(drag_data):
            return

        event.setDropAction(Qt.MoveAction)
        event.accept()

    def dropEvent(self, event):
        drop_data = event.mimeData()
        drop_files = drag_get_uris(drop_data)
        drop_video = drag_get_video(drop_data)

        # Add new video
        if drop_files:
            return self._drop_files(event, drop_files)

        # Swap videos or transfer from another instance
        elif drop_video:
            return self._drop_video_block(event, drop_video)

    def dragMoveEvent(self, event):
        drag_video = drag_get_video(event.mimeData())

        if drag_video:
            src_video = self._ctx.video_blocks.by_id(drag_video.id)
            if src_video:
                src_video.show_overlay()

    def _drop_files(self, event, drop_files):
        playlist = get_playlist_path(drop_files)

        if playlist:
            self.playlist_dropped.emit(playlist)
        else:
            videos = filter_video_uris(drop_files)
            self.videos_dropped.emit(videos)

        event.acceptProposedAction()

        return True

    def _drop_video_block(self, event, dropped_video):
        src_video = self._ctx.video_blocks.by_id(dropped_video.id)

        # Local video, swapping
        if src_video:
            dst_video = self._ctx.active_block
            if dst_video is None:
                self._log.debug("No video under cursor, discarding drop")
                return False

            self._swap_videos(src_video, dst_video)

        # Video from other player instance, adding as new
        else:
            self._log.debug("Dropped video from another instance")
            self.videos_dropped.emit([dropped_video.video])

        event.acceptProposedAction()

        return True

    def _is_drag_started(self, event):
        if not event.buttons() & Qt.LeftButton:
            return False

        if not self._drag_start_position:
            return False

        drag_distance = (event.pos() - self._drag_start_position).manhattanLength()
        if drag_distance < QApplication.startDragDistance():
            return False

        return self._ctx.active_block is not None

    def _get_drag_video(self):
        if not self._ctx.active_block:
            return None

        drag_data = self._ctx.active_block.drag_data.json()

        drag = QDrag(self)

        mimeData = QMimeData()
        mimeData.setData(
            "application/x-gridplayer-video",
            drag_data.encode("utf-8"),
        )
        drag.setMimeData(mimeData)

        self._drag_start_position = None

        return drag

    def _swap_videos(self, src, dst):
        self._log.debug(f"Swapping {src.id} with {dst.id}")

        if src == dst:
            self._log.debug("No video swap needed")
            return

        self._ctx.video_blocks.swap(dst, src)

        self.videos_swapped.emit()
