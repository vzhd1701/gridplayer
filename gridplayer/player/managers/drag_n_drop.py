from pathlib import Path

from PyQt5.QtCore import QEvent, QMimeData, Qt, pyqtSignal
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import filter_video_uris
from gridplayer.params import env
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.files import (
    extract_mime_uris,
    extract_mime_video,
    get_playlist_path,
    mime_has_video,
)
from gridplayer.utils.qt import is_modal_open


class DragNDropManager(ManagerBase):
    playlist_dropped = pyqtSignal(Path)
    videos_dropped = pyqtSignal(list)

    videos_swapped = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag_start_position = None

        self._internal_drag_block = None
        self._internal_drop_click_pending = False

    @property
    def commands(self):
        return {
            "internal_dnd_handle_event": self.internal_dnd_handle_event,
        }

    @property
    def event_map(self):
        return {
            QEvent.MouseMove: self.mouseMoveEvent,
            QEvent.MouseButtonPress: self.mousePressEvent,
            QEvent.MouseButtonRelease: self.mouseReleaseEvent,
            QEvent.KeyPress: self.keyPressEvent,
            QEvent.KeyRelease: self.keyReleaseEvent,
            QEvent.ShortcutOverride: self.shortcutOverrideEvent,
            QEvent.ApplicationDeactivate: self.applicationDeactivateEvent,
            QEvent.DragEnter: self.dragEnterEvent,
            QEvent.Drop: self.dropEvent,
            QEvent.DragMove: self.dragMoveEvent,
        }

    def mouseMoveEvent(self, event):
        if is_modal_open():
            self._drag_start_position = None
            self._clear_internal_drag()
            return

        if self._internal_drag_block is not None:
            self._internal_drag_block.show_overlay()
            self._ctx.commands.update_active_under_mouse()
            return True

        if not self._is_drag_started(event):
            return

        # KWin + Qt xcb (XWayland)
        # cursor always forbidden while drag, using fake drag
        # remove this and other _internal_drag/drop stuff
        # when native wayland becomes an option
        if env.IS_KDE:
            self._start_internal_drag()
            return True

        drag = self._get_drag_video()
        if drag is not None:
            drag.exec()

    def mousePressEvent(self, event):
        if self._internal_drag_block is not None:
            return True

        if event.button() != Qt.LeftButton:
            return

        self._internal_drop_click_pending = False

        if is_modal_open():
            self._drag_start_position = None
            return

        vb_under_mouse = self._ctx.commands.get_video_block_under_mouse()
        if vb_under_mouse is None:
            self._drag_start_position = None
            return

        self._drag_start_position = event.pos()

    def mouseReleaseEvent(self, event):
        if self._internal_drag_block is None:
            return None

        if event.button() != Qt.LeftButton:
            return None

        self._finish_internal_drag()

    def internal_dnd_handle_event(self, event) -> bool:
        if not (
            self._internal_drop_click_pending
            and event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            return False

        self._internal_drop_click_pending = False
        return True

    def shortcutOverrideEvent(self, event):
        # Disable hotkeys while dragging

        if self._internal_drag_block is None:
            return None

        # Avoid play/pause if canceled while cursor was over video
        self._internal_drop_click_pending = True

        event.accept()
        return True

    def keyPressEvent(self, event):
        if self._internal_drag_block is None:
            return None

        if event.key() == Qt.Key_Escape:
            self._clear_internal_drag()

        return True

    def keyReleaseEvent(self, event):
        if self._internal_drag_block is None:
            return None

        return True

    def applicationDeactivateEvent(self):
        if self._internal_drag_block is not None:
            self._clear_internal_drag()

    def dragEnterEvent(self, event):
        return self._accept_drag(event)

    def dropEvent(self, event):
        drop_data = event.mimeData()
        drop_files = extract_mime_uris(drop_data)
        drop_video = extract_mime_video(drop_data)

        # Add new video
        if drop_files:
            return self._drop_files(event, drop_files)

        # Swap videos or transfer from another instance
        elif drop_video:
            return self._drop_video_block(event, drop_video)

    def dragMoveEvent(self, event):
        if not self._accept_drag(event):
            return

        drag_video = extract_mime_video(event.mimeData())
        if not drag_video:
            return

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

    def _accept_drag(self, event):
        drag_data = event.mimeData()
        if not extract_mime_uris(drag_data) and not mime_has_video(drag_data):
            return False

        event.acceptProposedAction()
        return True

    def _is_drag_started(self, event):
        if is_modal_open():
            return False

        if not event.buttons() & Qt.LeftButton:
            return False

        if self._drag_start_position is None:
            return False

        drag_distance = (event.pos() - self._drag_start_position).manhattanLength()
        if drag_distance < QApplication.startDragDistance():
            return False

        return self._ctx.active_block is not None

    def _start_internal_drag(self):
        block = self._ctx.active_block
        if block is None:
            return

        self._internal_drag_block = block
        self._drag_start_position = None
        QApplication.setOverrideCursor(Qt.ClosedHandCursor)
        block.show_overlay()

    def _finish_internal_drag(self):
        src = self._internal_drag_block
        dst = self._ctx.active_block

        self._clear_internal_drag()

        if src is not None and dst is not None:
            self._swap_videos(src, dst)

        self._internal_drop_click_pending = True

    def _clear_internal_drag(self):
        if (
            self._internal_drag_block is not None
            and QApplication.overrideCursor() is not None
        ):
            QApplication.restoreOverrideCursor()

        self._internal_drag_block = None

    def _get_drag_video(self):
        block = self._ctx.active_block
        if not block:
            return None

        self._drag_start_position = None
        return self._make_qdrag(block)

    def _make_qdrag(self, block):
        if block is None:
            return None

        drag = QDrag(self.parent())
        mime_data = QMimeData()
        mime_data.setData(
            "application/x-gridplayer-video",
            block.drag_data.model_dump_json().encode("utf-8"),
        )
        drag.setMimeData(mime_data)
        return drag

    def _swap_videos(self, src, dst):
        self._log.debug(f"Swapping {src.id} with {dst.id}")

        if src == dst:
            self._log.debug("No video swap needed")
            return

        self._ctx.video_blocks.swap(dst, src)

        self.videos_swapped.emit()
