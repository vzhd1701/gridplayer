from PyQt5 import sip
from PyQt5.QtCore import pyqtSignal

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params import env
from gridplayer.params.settings_bindings import GRID_STATE_ATTR
from gridplayer.params.sponsorblock import SPONSORBLOCK_SETTINGS
from gridplayer.params.subtitle_style import SUBTITLE_STYLE_SETTINGS
from gridplayer.params.theme import apply_theme
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings, grid_values_from_state
from gridplayer.settings import Settings
from gridplayer.utils import cache
from gridplayer.utils.qt import translate
from gridplayer.utils.video_driver import is_mpv_gl_output, qt_platform_for

# what puts the tray icon up and takes the taskbar button away; the rest are
# read as they are needed
TRAY_SETTINGS = ("player/tray_icon", "player/hide_taskbar")


class SettingsManager(ManagerBase):
    reload = pyqtSignal()
    set_screensaver = pyqtSignal(int)
    set_media_keys_background = pyqtSignal(bool)
    set_log_level = pyqtSignal(int)
    set_log_level_vlc = pyqtSignal(int)
    set_log_level_mpv = pyqtSignal(int)
    set_mpv_skip_frames = pyqtSignal(bool)
    set_mpv_picture_quality = pyqtSignal(object)  # MpvPictureQuality
    subtitle_style_changed = pyqtSignal()
    set_recent_list_enabled = pyqtSignal(bool)
    keymap_changed = pyqtSignal(object)  # KeymapOverrides
    set_disable_mouse_click_events = pyqtSignal(bool)
    set_disable_mouse_wheel_events = pyqtSignal(bool)
    set_disable_overlay = pyqtSignal(bool)
    set_pause_background_videos = pyqtSignal(bool)
    set_single_mode_strip = pyqtSignal(object)  # StripMode
    set_single_mode_strip_side = pyqtSignal(object)  # StripSide
    set_single_mode_crop = pyqtSignal(int)
    set_pause_minimized = pyqtSignal(bool)
    set_show_overlay_border = pyqtSignal(bool)
    set_overlay_hide_on_timeout = pyqtSignal(bool)
    set_overlay_timeout = pyqtSignal(int)
    set_subtitle_encoding = pyqtSignal(str)
    set_bookmarks_shared = pyqtSignal(bool)
    sponsorblock_changed = pyqtSignal()
    tray_settings_changed = pyqtSignal()

    @property
    def commands(self):
        return {"settings": self.cmd_settings}

    def cmd_settings(self):
        previous_settings = Settings().get_all()

        dialog = SettingsDialog(self.parent())
        dialog.exec_()
        # gone at once, not with deleteLater: the theme is applied below, and
        # it styles over every widget there is, a closed dialog's too
        sip.delete(dialog)

        self._apply_settings(previous_settings)

        if self._is_restart_needed(previous_settings):
            QCustomMessageBox.information(
                self.parent(),
                translate("Dialog - Settings apply restart", "Settings", "Header"),
                translate("Dialog - Settings apply restart", "Restart to apply"),
                info=translate(
                    "Dialog - Settings apply restart",
                    "Some of the new settings work after you restart GridPlayer.",
                ),
            )

        if self._is_reload_needed(previous_settings):
            self.reload.emit()

    def _apply_settings(self, previous_settings):
        checks = {
            "logging/log_level": self.set_log_level,
            "logging/log_level_vlc": self.set_log_level_vlc,
            "logging/log_level_mpv": self.set_log_level_mpv,
            "player/mpv_skip_frames": self.set_mpv_skip_frames,
            "player/mpv_picture_quality": self.set_mpv_picture_quality,
            "player/inhibit_screensaver": self.set_screensaver,
            "player/media_keys_background": self.set_media_keys_background,
            "player/recent_list_enabled": self.set_recent_list_enabled,
            "player/keymap": self.keymap_changed,
            "playlist/disable_mouse_click_events": self.set_disable_mouse_click_events,
            "playlist/disable_mouse_wheel_events": self.set_disable_mouse_wheel_events,
            "playlist/disable_overlay": self.set_disable_overlay,
            "playlist/pause_background_videos": self.set_pause_background_videos,
            "playlist/single_mode_strip": self.set_single_mode_strip,
            "playlist/single_mode_strip_side": self.set_single_mode_strip_side,
            "playlist/single_mode_crop": self.set_single_mode_crop,
            "playlist/pause_minimized": self.set_pause_minimized,
            "playlist/show_overlay_border": self.set_show_overlay_border,
            "playlist/overlay_hide_on_timeout": self.set_overlay_hide_on_timeout,
            "playlist/overlay_timeout": self.set_overlay_timeout,
            "video_defaults/subtitle_encoding": self.set_subtitle_encoding,
            "playlist/bookmarks_shared": self.set_bookmarks_shared,
        }

        changes = self._setting_changes(previous_settings, tuple(checks))

        for c in changes:
            if PlaylistSettings().is_overridden(c):
                continue
            if c == "playlist/bookmarks_shared" and not self._is_sharing_confirmed(
                previous_settings[c]
            ):
                continue
            checks[c].emit(Settings().get(c))

        if self._setting_changes(previous_settings, SUBTITLE_STYLE_SETTINGS):
            self.subtitle_style_changed.emit()

        # one signal for the lot: the videos read what they need themselves
        if self._setting_changes(previous_settings, SPONSORBLOCK_SETTINGS):
            self.sponsorblock_changed.emit()

        if self._setting_changes(previous_settings, TRAY_SETTINGS):
            self.tray_settings_changed.emit()

        if self._is_setting_changed(previous_settings, "player/color_scheme"):
            apply_theme()

        if self._setting_changes(previous_settings, cache.CACHE_SETTINGS):
            cache.apply_settings()

        if self._setting_changes(previous_settings, GRID_STATE_ATTR):
            live = self._ctx.grid_state
            applied = PlaylistSettings().applied_grid_state(live)
            if grid_values_from_state(applied) != grid_values_from_state(live):
                self._ctx.commands.apply_grid_config(applied)

    def _is_sharing_confirmed(self, was_shared) -> bool:
        """Whether the open playlist's bookmarks follow the new default: a
        viewer who thinks better of it keeps them there as they were."""

        if self._ctx.commands.confirm_bookmarks_shared(not was_shared):
            return True

        PlaylistSettings().set("playlist/bookmarks_shared", was_shared)

        return False

    def _is_reload_needed(self, previous_settings):
        checks = {
            "player/video_driver",
            "player/video_driver_players",
            # Copy and Direct: what's open is made again for the new one
            "player/mpv_output",
            "internal/opaque_hw_overlay",
            "internal/fake_overlay_invisibility",
            "misc/vlc_options",
        }

        # with no video open, that only lets go of any VLC process left waiting
        videos = list(self._ctx.video_blocks)

        if not videos or any(
            video.driver_class.must_reload_for_subtitle_style for video in videos
        ):
            checks.update(SUBTITLE_STYLE_SETTINGS)

        return self._setting_changes(previous_settings, checks)

    def _is_restart_needed(self, previous_settings):
        checks = {
            "player/language",
            "logging/log_limit",
            "logging/log_limit_size",
            "logging/log_limit_backups",
            "player/stay_on_top",
        }

        # with no GL output this session, there's nothing for it to fix yet
        if env.MPV_GL_OUTPUT:
            checks.add("internal/gl_line_fix")

        return (
            self._is_gl_output_due(previous_settings)
            or self._is_qt_platform_due(previous_settings)
            or bool(self._setting_changes(previous_settings, checks))
        )

    def _is_qt_platform_due(self, previous_settings) -> bool:
        """A change to what picks X11 or Wayland, the Window system, or the
        decoder or MPV's output on Auto, and the pick isn't what the session
        runs on: asked again for a restart put off. Not if --platform said
        which."""

        if not env.IS_QT_PLATFORM_PICKED:
            return False

        if _qt_platform(Settings().get) == env.QT_PLATFORM:
            return False

        return any(
            previous_settings[key] != Settings().get(key) for key in _PLATFORM_KEYS
        )

    def _is_gl_output_due(self, previous_settings) -> bool:
        """Changed to drawing MPV's frames by GL or not, which the session
        didn't start with: Qt's GL is set up as the app starts, see init_app_env.
        """

        is_wanted = _is_gl_output(Settings().get)
        is_changed = is_wanted != _is_gl_output(previous_settings.__getitem__)

        return is_changed and is_wanted != env.MPV_GL_OUTPUT

    def _setting_changes(self, previous_settings, checks):
        return {k for k in checks if previous_settings[k] != Settings().get(k)}

    def _is_setting_changed(self, previous_settings, check):
        return previous_settings[check] != Settings().get(check)


def _is_gl_output(get) -> bool:
    return is_mpv_gl_output(get("player/mpv_output"), get("player/video_driver"))


# what qt_platform_for picks by
_PLATFORM_KEYS = ("player/display_server", "player/video_driver", "player/mpv_output")


def _qt_platform(get) -> str | None:
    return qt_platform_for(*map(get, _PLATFORM_KEYS))
