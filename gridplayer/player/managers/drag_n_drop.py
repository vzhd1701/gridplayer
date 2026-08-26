from pathlib import Path

from PyQt5.QtCore import QEvent, QMimeData, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor, QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import filter_video_uris
from gridplayer.params import env
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.drag_n_drop import drop_is_replace, query_drop_modifiers
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

# X11 XDND Enter is a later client message, not already queued. timer(0)
# ends drag UI (and overlay input passthrough) before the player gets Enter.
# KWin then drops onto a window Qt is no longer tracking — no XdndFinished,
# Dolphin keeps the + cursor, and this process never accepts another drop.
_DRAG_LEAVE_GRACE_MS = 250 if env.IS_LINUX else 0


class DragNDropManager(ManagerBase):
    playlist_dropped = pyqtSignal(Path)
    videos_dropped = pyqtSignal(list, object, bool)
    videos_swapped = pyqtSignal()
    set_drag_ui = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._drag_start_position = None

        self._is_fake_drag_active = False
        self._is_swallow_click_after_fake_drag = False

        self._drop_block = None
        self._drop_zone = None
        self._drop_is_internal = False
        self._drop_is_replace = False
        self._source_block = None

        # Overlay Tool windows (and overlay ↔ player) emit DragLeave before
        # the next target's DragEnter. End drag UI on the next tick so a
        # cancel / leave-window still resets chrome and glyphs.
        self._drag_leave_timer = QTimer(self)
        self._drag_leave_timer.setSingleShot(True)
        self._drag_leave_timer.timeout.connect(self._end_drag_ui_after_leave)

    @property
    def commands(self):
        return {
            "handle_fake_drag_click": self.handle_fake_drag_click,
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
            QEvent.DragLeave: self.dragLeaveEvent,
        }

    # --- start drag (mouse) ---

    def mousePressEvent(self, event):
        if self._is_fake_drag_active:
            return True

        self._is_swallow_click_after_fake_drag = False

        if is_modal_open():
            self._drag_start_position = None
            return

        vb_under_mouse = self._ctx.commands.get_video_block_under_mouse()
        if vb_under_mouse is None:
            self._drag_start_position = None
            return

        # Overlay Tool windows eat X11 focus. Activate the player so Shift
        # is delivered if the click started while another app was focused.
        self._ctx.commands.activate_window()

        if event.button() != Qt.LeftButton:
            return

        self._drag_start_position = event.pos()

    def mouseMoveEvent(self, event):
        if is_modal_open():
            self._drag_start_position = None
            self._cancel_fake_drag()
            return

        if self._is_fake_drag_active:
            self._update_drop_target(QCursor.pos(), is_internal=True)
            return True

        if not self._is_drag_started(event):
            return

        # Native QDrag on xcb/XWayland freezes modifiers (pointer grab) and
        # GNOME does not forward keys to an unfocused X11 window.
        if env.IS_LINUX and not Settings().get("internal/force_native_drag_events"):
            self._start_fake_drag()
            return True

        source = self._ctx.active_block
        drag = self._make_qdrag(source)
        if drag is not None:
            self._ensure_drag_ui()
            self._set_source(source)
            drag.exec()
            self._end_drag_ui()

    def mouseReleaseEvent(self, event):
        if not self._is_fake_drag_active:
            return None

        if event.button() != Qt.LeftButton:
            return None

        self._finish_fake_drag()

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

    # --- Fake drag (Linux xcb / XWayland) ---
    # KWin forbids the native QDrag cursor. GNOME/XWayland also swallows
    # modifier keys during QDrag.exec(). Remove when native Wayland is an option.

    def _start_fake_drag(self):
        block = self._ctx.active_block
        if block is None:
            return

        self._is_fake_drag_active = True
        self._drag_start_position = None
        QApplication.setOverrideCursor(Qt.ClosedHandCursor)
        self._ensure_drag_ui()
        self._set_source(block)
        self._update_drop_target(QCursor.pos(), is_internal=True)

    def _finish_fake_drag(self):
        src = self._source_block
        dst = self._drop_block
        zone = self._drop_zone
        is_replace = self._drop_is_replace

        self._cancel_fake_drag()

        insert_at = None
        if dst is not None:
            if is_replace:
                insert_at = self._ctx.video_blocks.index(dst)
            elif zone is not None:
                insert_at = insert_index(self._ctx.video_blocks.index(dst), zone)

        if src:
            self._drop_video_block(src, dst, zone, insert_at, is_replace)

        self._is_swallow_click_after_fake_drag = True

    def _cancel_fake_drag(self):
        if self._is_fake_drag_active and QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        self._is_fake_drag_active = False
        self._end_drag_ui()

    def handle_fake_drag_click(self, event) -> bool:
        if not (
            self._is_swallow_click_after_fake_drag
            and event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            return False

        self._is_swallow_click_after_fake_drag = False
        return True

    def shortcutOverrideEvent(self, event):
        if not self._is_fake_drag_active:
            return None

        # Avoid play/pause if canceled while cursor was over video
        self._is_swallow_click_after_fake_drag = True
        self._update_drop_target(QCursor.pos(), is_internal=True)
        event.accept()
        return True

    def keyPressEvent(self, event):
        if not self._is_fake_drag_active:
            return None

        if event.key() == Qt.Key_Escape:
            self._cancel_fake_drag()
            return True

        self._update_drop_target(QCursor.pos(), is_internal=True)
        return True

    def keyReleaseEvent(self, event):
        if not self._is_fake_drag_active:
            return None

        self._update_drop_target(QCursor.pos(), is_internal=True)
        return True

    def applicationDeactivateEvent(self):
        # Overlay Tool windows deactivate the player on X11 HW overlays.
        # Swallow that so chrome does not flicker; do not cancel the drag
        # (hide/show of those windows would loop).
        if self._ctx.is_drag_ui:
            return True

    # --- Qt DND ---

    def dragEnterEvent(self, event, event_object):
        self._drag_leave_timer.stop()

        if not self._accept_drag(event):
            return False

        self._ensure_drag_ui()
        self._keep_player_active()
        self._set_source(self._local_block_from_event(event))
        self._update_drop_target_from_event(event, event_object)
        return True

    def dragMoveEvent(self, event, event_object):
        self._drag_leave_timer.stop()

        if not self._accept_drag(event):
            self._clear_hover()
            return

        self._ensure_drag_ui()
        self._keep_player_active()
        self._set_source(self._local_block_from_event(event))
        self._update_drop_target_from_event(event, event_object)

    def dragLeaveEvent(self, event):
        if (
            self._is_fake_drag_active
            or self._drop_is_internal
            or not self._ctx.is_drag_ui
        ):
            return

        self._drag_leave_timer.start(_DRAG_LEAVE_GRACE_MS)

    def dropEvent(self, event, event_object):
        self._drag_leave_timer.stop()

        self._update_drop_target_from_event(event, event_object)
        dst = self._drop_block
        zone = self._drop_zone
        is_replace = self._drop_is_replace

        drop_files = extract_mime_uris(event.mimeData())
        drop_video = extract_mime_video(event.mimeData())

        insert_at = None
        if dst is not None:
            if is_replace:
                insert_at = self._ctx.video_blocks.index(dst)
            elif zone is not None:
                insert_at = insert_index(self._ctx.video_blocks.index(dst), zone)

        # Always accept so Qt sends XdndFinished. Rejecting from a filter
        # without that leaves Dolphin and QXcbDrag stuck until restart.
        event.acceptProposedAction()
        QTimer.singleShot(
            0,
            lambda: self._finish_drop(
                drop_files, drop_video, dst, zone, insert_at, is_replace
            ),
        )
        return True

    def _finish_drop(self, drop_files, drop_video, dst, zone, insert_at, is_replace):
        self._end_drag_ui()

        if drop_files:
            self._drop_files(drop_files, insert_at, is_replace)
            return

        if drop_video:
            self._drop_video_block(drop_video, dst, zone, insert_at, is_replace)

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

    def _drop_files(self, drop_files, insert_at, is_replace):
        playlist = get_playlist_path(drop_files)

        if playlist:
            self.playlist_dropped.emit(playlist)
            return

        videos = filter_video_uris(drop_files)
        self.videos_dropped.emit(videos, insert_at, is_replace)

    def _drop_video_block(self, dropped_video, dst, zone, insert_at, is_replace):
        src_video = self._ctx.video_blocks.by_id(dropped_video.id)

        if src_video:
            if dst is None:
                self._log.debug("No video under cursor, discarding drop")
                return

            if is_replace:
                self._ctx.commands.replace_with_block(dst, src_video)
                return

            if zone is None:
                self._log.debug("No video under cursor, discarding drop")
                return

            if zone == DropZone.CENTER:
                self._log.debug(f"Swapping {src_video.id} with {dst.id}")
                self._swap_videos(src_video, dst)
                return

            self._log.debug(f"Moving {src_video.id} to index {insert_at} ({zone.name})")
            self._move_video_to_idx(src_video, insert_at)
            return

        self._log.debug("Dropped video from another instance")
        self.videos_dropped.emit([dropped_video.video], insert_at, is_replace)

    def _move_video_to_idx(self, src, index):
        self._ctx.video_blocks.move(src, index)
        self.videos_swapped.emit()

    def _swap_videos(self, src, dst):
        if src == dst:
            self._log.debug("No video swap needed")
            return

        self._ctx.video_blocks.swap(dst, src)
        self.videos_swapped.emit()

    # --- hover / source glyphs ---

    def _ensure_drag_ui(self):
        if not self._ctx.is_drag_ui:
            self.set_drag_ui.emit(True)

    def _keep_player_active(self):
        # Overlay Tool windows are the XDND target in HW mode. KWin treats
        # that as a focus change; GNOME keeps focus at the drag origin.
        if env.IS_KDE:
            self._ctx.commands.activate_window()

    def _is_replace(self, is_internal: bool, event=None) -> bool:
        action_key = (
            "playlist/drop_action_internal"
            if is_internal
            else "playlist/drop_action_external"
        )
        return drop_is_replace(
            query_drop_modifiers(event),
            Settings().get(action_key),
            Settings().get("playlist/drop_modifier"),
        )

    def _end_drag_ui_after_leave(self):
        if self._is_fake_drag_active:
            return

        # Overlay Tool windows are 0-alpha click-through except the glyph, so
        # crossing the circle (or another overlay) is Leave then Enter. Do not
        # tear down drag UI while the pointer is still over the player.
        # Skip on Linux: QCursor.pos() is stale during X11 XDND.
        if self._is_pointer_over_player():
            return

        self._end_drag_ui()

    def _is_pointer_over_player(self):
        if env.IS_LINUX:
            return False

        player = self.parent()
        if player is None:
            return False

        return player.rect().contains(player.mapFromGlobal(QCursor.pos()))

    def _end_drag_ui(self):
        self._drag_leave_timer.stop()

        self._clear_hover()
        self._set_source(None)

        if not self._ctx.is_drag_ui:
            return

        self.set_drag_ui.emit(False)

    def _update_drop_target_from_event(self, event, event_object):
        if event_object is None:
            return

        # event.pos() + mapToGlobal: QCursor.pos() is stale during X11 XDND
        self._update_drop_target(
            event_object.mapToGlobal(event.pos()),
            is_internal=self._local_block_from_event(event) is not None,
            event=event,
        )

    def _update_drop_target(self, global_pos, is_internal: bool, event=None):
        block, zone = self._hover_at(global_pos)
        self._set_hover(block, zone, is_internal, self._is_replace(is_internal, event))

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

    def _set_hover(self, block, zone, is_internal, is_replace):
        is_nothing_changed = (
            self._drop_block is block
            and self._drop_zone is zone
            and self._drop_is_internal is is_internal
            and self._drop_is_replace is is_replace
        )

        if is_nothing_changed:
            return

        self._clear_hover_indicator_if_not(block)
        self._drop_block = block
        self._drop_zone = zone
        self._drop_is_internal = is_internal
        self._drop_is_replace = is_replace

        if block is not None and block is not self._source_block:
            block.set_drop_indicator(
                indicator_for(
                    zone,
                    is_internal,
                    self._ctx.grid_state.mode,
                    is_replace=is_replace,
                )
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
        self._drop_is_replace = False

    def _clear_hover_indicator_if_not(self, block):
        if (
            self._drop_block is not None
            and self._drop_block is not block
            and self._drop_block is not self._source_block
        ):
            self._drop_block.set_drop_indicator(DropIndicator.NONE)
