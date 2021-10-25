import logging

from PyQt5.QtCore import QMimeData, Qt
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.utils.files import drag_get_files, drag_get_video_id, drag_has_video_id
from gridplayer.utils.misc import dict_swap_items

logger = logging.getLogger(__name__)


class PlayerDragNDropMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAcceptDrops(True)

        self.drag_start_position = None

    def mouseMoveEvent(self, event):
        drag_video = self._get_drag_video(event)
        if drag_video is not None:
            drag_video.exec()

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()

        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:
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
                self.load_playlist_file(drop_files[0])
            else:
                self.add_videos(drop_files)

            event.acceptProposedAction()

        # Swap videos
        elif drag_has_video_id(drop_data):
            dst_video = self.get_hover_video_block()
            if dst_video is None:
                logger.debug("No video under cursor, discarding drop")
                return

            src_video_id = drag_get_video_id(drop_data)
            dst_video_id = dst_video.id

            logger.debug(f"Swapping {src_video_id} with {dst_video_id}")

            self._swap_videos(src_video_id, dst_video_id)

            event.acceptProposedAction()

    def _get_drag_video(self, event):
        if not event.buttons() & Qt.LeftButton:
            return None

        if not self.drag_start_position:
            return None

        drag_distance = (event.pos() - self.drag_start_position).manhattanLength()
        if drag_distance < QApplication.startDragDistance():
            return None

        if self.active_video_block is None:
            return None

        drag = QDrag(self)

        mimeData = QMimeData()
        mimeData.setData(
            "application/x-gridplayer-video-id", self.active_video_block.id.encode()
        )
        drag.setMimeData(mimeData)

        self.drag_start_position = None

        return drag

    def _swap_videos(self, src_id, dst_id):
        if src_id == dst_id:
            logger.debug("No video swap needed")
            return

        if src_id not in self.video_blocks:
            logger.debug(f"Cannot swap {src_id}, id not found")
            return

        self.video_blocks = dict_swap_items(self.video_blocks, dst_id, src_id)

        self.reload_video_grid()
