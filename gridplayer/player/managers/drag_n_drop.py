import logging

from PyQt5.QtCore import QEvent, QMimeData, Qt, pyqtSignal
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.files import drag_get_files, drag_get_video_id, drag_has_video_id
from gridplayer.video import Video

logger = logging.getLogger(__name__)


class DragNDropManager(ManagerBase):
    playlist_dropped = pyqtSignal(str)
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

        if not drag_get_files(drag_data) and not drag_has_video_id(drag_data):
            return

        event.setDropAction(Qt.MoveAction)
        event.accept()

    def dropEvent(self, event):
        drop_data = event.mimeData()
        drop_files = drag_get_files(drop_data)

        # Add new video
        if drop_files:
            if drop_files[0].endswith("gpls"):
                self.playlist_dropped.emit(drop_files[0])
            else:
                videos = [Video(file_path=f) for f in drop_files]
                self.videos_dropped.emit(videos)

            event.acceptProposedAction()

            return True

        # Swap videos
        elif drag_has_video_id(drop_data):
            dst_video = self._ctx.active_block
            if dst_video is None:
                logger.debug("No video under cursor, discarding drop")
                return False

            src_video = self._ctx.video_blocks.by_id(drag_get_video_id(drop_data))

            self._swap_videos(src_video, dst_video)

            event.acceptProposedAction()

            return True

    def dragMoveEvent(self, event):
        drop_data = event.mimeData()

        if drag_has_video_id(drop_data):
            src_video = self._ctx.video_blocks.by_id(drag_get_video_id(drop_data))
            src_video.show_overlay()

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
        drag = QDrag(self)

        mimeData = QMimeData()
        mimeData.setData(
            "application/x-gridplayer-video-id",
            self._ctx.active_block.id.encode(),
        )
        drag.setMimeData(mimeData)

        self._drag_start_position = None

        return drag

    def _swap_videos(self, src, dst):
        logger.debug(f"Swapping {src.id} with {dst.id}")

        if src == dst:
            logger.debug("No video swap needed")
            return

        self._ctx.video_blocks.swap(dst, src)

        self.videos_swapped.emit()
