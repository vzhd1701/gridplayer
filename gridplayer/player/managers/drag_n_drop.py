from pathlib import Path

from PyQt5.QtCore import QEvent, QMimeData, Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import filter_video_uris
from gridplayer.params import env
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.drop_zone import (
    DropIndicator,
    DropZone,
    indicator_for,
    insert_index,
    zone_at,
)
from gridplayer.utils.files import (
    extract_mime_uris,
    extract_mime_video,
    get_playlist_path,
    mime_has_video,
)
from gridplayer.utils.qt import is_modal_open


class DragNDropManager(ManagerBase):
    playlist_dropped = pyqtSignal(Path)
    videos_dropped = pyqtSignal(list, object)

    videos_swapped = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag_start_position = None

        self._is_kde_drag_active = False
        self._is_kde_drop_click_pending = False

        self._drop_block = None
        self._drop_zone = None
        self._drop_is_internal = False
        self._source_block = None

    @property
    def commands(self):
        return {
            "kde_dnd_handle_event": self.kde_dnd_handle_event,
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

    # --- start drag (mouse) ---

    def mousePressEvent(self, event):
        if self._is_kde_drag_active:
            return True

        if event.button() != Qt.LeftButton:
            return

        self._is_kde_drop_click_pending = False

        if is_modal_open():
            self._drag_start_position = None
            return

        vb_under_mouse = self._ctx.commands.get_video_block_under_mouse()
        if vb_under_mouse is None:
            self._drag_start_position = None
            return

        self._drag_start_position = event.pos()

    def mouseMoveEvent(self, event):
        if is_modal_open():
            self._drag_start_position = None
            self._cancel_kde_drag()
            return

        if self._is_kde_drag_active:
            self._update_drop_target_at(QCursor.pos(), is_internal=True)
            return True

        if not self._is_drag_started(event):
            return

        if env.IS_KDE:
            self._start_kde_drag()
            return True

        source = self._ctx.active_block
        drag = self._make_qdrag(source)
        if drag is not None:
            self._ensure_drag_ui()
            self._set_source(source)
            drag.exec()
            self._end_drag_ui()

    def mouseReleaseEvent(self, event):
        if not self._is_kde_drag_active:
            return None

        if event.button() != Qt.LeftButton:
            return None

        self._finish_kde_drag()

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

    def _make_qdrag(self, block):
        if block is None:
            return None

        self._drag_start_position = None
        drag = QDrag(self.parent())
        mime_data = QMimeData()
        mime_data.setData(
            "application/x-gridplayer-video",
            block.drag_data.model_dump_json().encode("utf-8"),
        )
        drag.setMimeData(mime_data)
        return drag

    # --- KDE fake drag (KWin + Qt xcb / XWayland forbids the native cursor) ---
    # Remove when native Wayland is an option.

    def _start_kde_drag(self):
        block = self._ctx.active_block
        if block is None:
            return

        self._is_kde_drag_active = True
        self._drag_start_position = None
        QApplication.setOverrideCursor(Qt.ClosedHandCursor)
        self._ensure_drag_ui()
        self._set_source(block)

    def _finish_kde_drag(self):
        src = self._source_block
        dst = self._drop_block
        zone = self._drop_zone

        self._cancel_kde_drag()

        if src is not None and dst is not None and zone is not None:
            self._apply_internal_drop(src, dst, zone)

        self._is_kde_drop_click_pending = True

    def _cancel_kde_drag(self):
        if self._is_kde_drag_active and QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        self._is_kde_drag_active = False
        self._end_drag_ui()

    def kde_dnd_handle_event(self, event) -> bool:
        if not (
            self._is_kde_drop_click_pending
            and event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            return False

        self._is_kde_drop_click_pending = False
        return True

    def shortcutOverrideEvent(self, event):
        if not self._is_kde_drag_active:
            return None

        # Avoid play/pause if canceled while cursor was over video
        self._is_kde_drop_click_pending = True
        event.accept()
        return True

    def keyPressEvent(self, event):
        if not self._is_kde_drag_active:
            return None

        if event.key() == Qt.Key_Escape:
            self._cancel_kde_drag()

        return True

    def keyReleaseEvent(self, event):
        if not self._is_kde_drag_active:
            return None

        return True

    def applicationDeactivateEvent(self):
        # Overlay Tool windows deactivate the player on X11 HW overlays.
        # Swallow that so chrome does not flicker; do not cancel the drag
        # (hide/show of those windows would loop).
        if self._ctx.is_drag_ui:
            return True

    # --- Qt DND ---

    def dragEnterEvent(self, event, event_object):
        if not self._accept_drag(event):
            return False

        self._ensure_drag_ui()
        self._set_source(self._local_block_from_event(event))
        self._update_drop_target_from_event(event, event_object)
        return True

    def dragMoveEvent(self, event, event_object):
        if not self._accept_drag(event):
            self._clear_hover()
            return

        self._ensure_drag_ui()
        self._set_source(self._local_block_from_event(event))
        self._update_drop_target_from_event(event, event_object)

    def dropEvent(self, event, event_object):
        self._update_drop_target_from_event(event, event_object)
        dst = self._drop_block
        zone = self._drop_zone
        self._end_drag_ui()

        drop_data = event.mimeData()
        drop_files = extract_mime_uris(drop_data)
        drop_video = extract_mime_video(drop_data)

        insert_at = None
        if dst is not None and zone is not None:
            insert_at = insert_index(self._ctx.video_blocks.index(dst), zone)

        if drop_files:
            self._drop_files(drop_files, insert_at)
            event.acceptProposedAction()
            return True

        if drop_video:
            self._drop_video_block(drop_video, dst, zone, insert_at)
            event.acceptProposedAction()
            return True

    def _accept_drag(self, event):
        drag_data = event.mimeData()
        if not extract_mime_uris(drag_data) and not mime_has_video(drag_data):
            return False

        event.acceptProposedAction()
        return True

    def _local_block_from_event(self, event):
        drag_video = extract_mime_video(event.mimeData())
        if not drag_video:
            return None
        return self._ctx.video_blocks.by_id(drag_video.id)

    # --- apply drop ---

    def _drop_files(self, drop_files, insert_at):
        playlist = get_playlist_path(drop_files)

        if playlist:
            self.playlist_dropped.emit(playlist)
        else:
            videos = filter_video_uris(drop_files)
            self.videos_dropped.emit(videos, insert_at)

    def _drop_video_block(self, dropped_video, dst, zone, insert_at):
        src_video = self._ctx.video_blocks.by_id(dropped_video.id)

        if src_video:
            if dst is None or zone is None:
                self._log.debug("No video under cursor, discarding drop")
                return

            self._apply_internal_drop(src_video, dst, zone)
            return

        self._log.debug("Dropped video from another instance")
        self.videos_dropped.emit([dropped_video.video], insert_at)

    def _apply_internal_drop(self, src, dst, zone):
        if zone == DropZone.CENTER:
            self._swap_videos(src, dst)
            return

        index = insert_index(self._ctx.video_blocks.index(dst), zone)
        self._log.debug(f"Moving {src.id} to index {index} ({zone.name})")
        self._ctx.video_blocks.move(src, index)
        self.videos_swapped.emit()

    def _swap_videos(self, src, dst):
        self._log.debug(f"Swapping {src.id} with {dst.id}")

        if src == dst:
            self._log.debug("No video swap needed")
            return

        self._ctx.video_blocks.swap(dst, src)
        self.videos_swapped.emit()

    # --- hover / source glyphs ---

    def _ensure_drag_ui(self):
        if not self._ctx.is_drag_ui:
            self._ctx.commands.set_drag_ui(True)

    def _end_drag_ui(self):
        self._drop_block = None
        self._drop_zone = None
        self._drop_is_internal = False
        self._source_block = None

        if not self._ctx.is_drag_ui:
            return

        self._ctx.commands.set_drag_ui(False)
        self._ctx.commands.update_active_under_mouse()

    def _update_drop_target_from_event(self, event, event_object):
        is_internal = self._local_block_from_event(event) is not None
        self._update_drop_target_at(
            event_object.mapToGlobal(event.pos()), is_internal=is_internal
        )

    def _update_drop_target_at(self, global_pos, is_internal: bool):
        block, zone = self._hover_at(global_pos)
        self._set_hover(block, zone, is_internal)

    def _hover_at(self, global_pos):
        block = self._ctx.commands.get_video_block_at(global_pos)
        if block is None:
            return None, None

        local = block.mapFromGlobal(global_pos)
        zone = zone_at(
            local.x(),
            local.y(),
            block.width(),
            block.height(),
            self._ctx.grid_state.mode,
        )
        return block, zone

    def _set_hover(self, block, zone, is_internal):
        is_nothing_changed = (
            self._drop_block is block
            and self._drop_zone is zone
            and self._drop_is_internal is is_internal
        )

        if is_nothing_changed:
            return

        self._clear_hover_indicator_if_not(block)
        self._drop_block = block
        self._drop_zone = zone
        self._drop_is_internal = is_internal

        if block is not None and block is not self._source_block:
            block.set_drop_indicator(
                indicator_for(zone, is_internal, self._ctx.grid_state.mode)
            )

    def _set_source(self, source):
        if source is self._source_block:
            return

        if self._source_block is not None:
            self._source_block.set_drop_indicator(DropIndicator.NONE)

        self._source_block = source
        if source is not None:
            source.set_drop_indicator(DropIndicator.SOURCE)

    def _clear_hover(self):
        self._clear_hover_indicator_if_not(None)
        self._drop_block = None
        self._drop_zone = None
        self._drop_is_internal = False

    def _clear_hover_indicator_if_not(self, block):
        if (
            self._drop_block is not None
            and self._drop_block is not block
            and self._drop_block is not self._source_block
        ):
            self._drop_block.set_drop_indicator(DropIndicator.NONE)
